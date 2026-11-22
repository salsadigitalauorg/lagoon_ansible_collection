"""Short-lived Lagoon token cache, shared between Ansible's forked workers.

Ansible forks a worker per host per task and module-level state does not
survive the fork, so caching in memory alone would mean one `ssh ... grant` per
host per task - 200 SSH calls for a single task across 200 hosts. The entry is
written to a 0600 file in a user-scoped directory, keyed by endpoint and
identity, and honours the grant's own expires_in.

Caching a bearer token at rest is a deliberate, documented risk acceptance
rather than a claim of compliance: the artefact is short-lived and dynamically
issued, it replaces tokens and SSH private keys previously written in cleartext
to a predictable /tmp path, and LAGOON_TOKEN_CACHE=0 turns it off. Treat a
leaked cache file as a credential compromise requiring rotation.

Never fails a run. Every disk path degrades to the per-process memory cache.
"""

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Optional

try:
    import fcntl

    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

ENV_DISABLE = "LAGOON_TOKEN_CACHE"
ENV_DIR = "LAGOON_TOKEN_CACHE_DIR"

# Treat an entry as spent this many seconds before its stated expiry, to cover
# clock skew and the time between reading it and the API using it.
EXPIRY_SKEW = 60

# Upper bound on how long a token is kept at rest, regardless of what the
# server says its expires_in is. The "short-lived credential" argument behind
# caching a bearer token at all should not rest entirely on server
# configuration.
MAX_CACHED_LIFETIME = 4 * 3600

DISABLED_VALUES = frozenset({"0", "false", "no", "off"})

# Per-process fallback, and the write-through tier for the on-disk cache. Keyed
# the same way, holding (token, expires_at).
_memory = {}


def enabled() -> bool:
    """False when the operator has opted out of the on-disk cache."""
    return str(os.environ.get(ENV_DISABLE, "1")).strip().lower() not in DISABLED_VALUES


def fingerprint(value) -> str:
    """Short digest standing in for a credential in a cache key.

    The key has to distinguish one identity from another without recording
    either, so only this ever reaches a filename.
    """
    if not value:
        return "none"
    return hashlib.sha256(str(value).encode()).hexdigest()[:16]


def make_key(endpoint, ssh_host, ssh_port, identity) -> str:
    """Cache key for one endpoint reached with one identity.

    identity must already be a fingerprint(), not key content or a path.
    """
    canonical = "\x00".join(
        str(p or "") for p in (endpoint, ssh_host, ssh_port, identity)
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def cache_dir() -> Optional[str]:
    """The directory entries live in, or None if one cannot be determined."""
    override = os.environ.get(ENV_DIR)
    if override:
        return override

    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return os.path.join(xdg, "lagoon")

    try:
        return os.path.join(os.path.expanduser("~"), ".cache", "lagoon")
    except (OSError, RuntimeError, KeyError):
        return None


def _prepared_dir(display=None) -> Optional[str]:
    """The cache directory, created 0700, or None if it is not usable.

    Containers routinely run as an arbitrary UID with no writable HOME, so an
    unusable directory is an ordinary condition and not a warning.
    """
    path = cache_dir()
    if not path:
        return None

    try:
        os.makedirs(path, exist_ok=True)
        # chmod separately: the mode argument to makedirs is masked by umask.
        os.chmod(path, 0o700)
        return path
    except OSError as e:
        if display:
            display.vv(f"Lagoon token cache unusable at {path}, staying in memory: {e}")
        return None


def _entry_path(directory: str, key: str) -> str:
    return os.path.join(directory, f"token-{key}.json")


def _valid(expires_at) -> bool:
    try:
        return time.time() < float(expires_at) - EXPIRY_SKEW
    except (TypeError, ValueError):
        return False


def get(key: str, display=None) -> Optional[str]:
    """The cached token for this key, or None if absent, expired or unreadable."""

    cached = _memory.get(key)
    if cached and _valid(cached[1]):
        return cached[0]

    if not enabled():
        return None

    directory = _prepared_dir(display)
    if not directory:
        return None

    try:
        with open(_entry_path(directory, key)) as fh:
            entry = json.load(fh)
        token = entry["access_token"]
        expires_at = entry["expires_at"]
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as e:
        # A truncated or corrupt entry is a miss, never an exception.
        if display:
            display.vv(f"Ignoring unreadable Lagoon token cache entry: {e}")
        return None

    if not token or not _valid(expires_at):
        return None

    _memory[key] = (token, expires_at)
    return token


def put(key: str, token: str, expires_in, display=None) -> None:
    """Cache a freshly minted token, in memory and on disk where possible."""

    if not token:
        return

    try:
        expires_at = time.time() + min(float(expires_in), MAX_CACHED_LIFETIME)
    except (TypeError, ValueError):
        if display:
            display.vv(f"Not caching Lagoon token: unusable expires_in {expires_in!r}")
        return

    _memory[key] = (token, expires_at)

    if not enabled():
        return

    directory = _prepared_dir(display)
    if not directory:
        return

    payload = json.dumps({"access_token": token, "expires_at": expires_at})

    # Written to a sibling temporary file and moved into place: several forks
    # can write at once, and os.replace is atomic on POSIX, so a concurrent
    # reader never sees half a document.
    tmp_fd, tmp_path = None, None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=f"token-{key}.")
        with os.fdopen(tmp_fd, "w") as fh:
            tmp_fd = None
            fh.write(payload)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, _entry_path(directory, key))
        tmp_path = None
    except OSError as e:
        if display:
            display.vv(f"Could not write Lagoon token cache entry: {e}")
    finally:
        if tmp_fd is not None:
            os.close(tmp_fd)
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def discard(key: str, display=None) -> None:
    """Drop this entry, so the next resolve() mints a fresh token.

    For a token the API has rejected: an entry inside its stated lifetime can
    still be invalid through clock skew or server-side revocation.
    """

    _memory.pop(key, None)

    directory = cache_dir() if enabled() else None
    if not directory:
        return

    try:
        os.unlink(_entry_path(directory, key))
    except FileNotFoundError:
        pass
    except OSError as e:
        if display:
            display.vv(f"Could not remove Lagoon token cache entry: {e}")


@contextmanager
def _locked(key: str, display=None):
    """Hold an exclusive lock for this key, or proceed without one.

    Failure to lock is not an error: on a filesystem with no working flock the
    worst case is the uncached behaviour of fetching more than once.
    """

    directory = _prepared_dir(display) if enabled() else None
    if not directory or not HAS_FCNTL:
        yield
        return

    lock_path = os.path.join(directory, f"token-{key}.lock")
    handle = None
    try:
        handle = open(lock_path, "w")
        os.chmod(lock_path, 0o600)
        fcntl.flock(handle, fcntl.LOCK_EX)
    except OSError as e:
        if display:
            display.vv(f"Proceeding without the Lagoon token cache lock: {e}")
        if handle:
            handle.close()
            handle = None

    try:
        yield
    finally:
        if handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            except OSError:
                pass
            handle.close()


def resolve(
    key: str, fetch: Callable[[], tuple[str, int]], display=None
) -> Optional[str]:
    """The cached token for this key, minting one through fetch on a miss.

    fetch returns (token, expires_in) and is called under a lock, with the
    cache re-read after it is acquired, so N forks starting together cost one
    mint and N-1 cache reads rather than N mints.
    """

    token = get(key, display)
    if token:
        return token

    with _locked(key, display):
        token = get(key, display)
        if token:
            return token

        token, expires_in = fetch()
        put(key, token, expires_in, display)
        return token
