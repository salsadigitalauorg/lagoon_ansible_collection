"""Opt-in, cross-process file-backed cache for Lagoon bearer tokens.

**Off by default.** ``auth.resolve_token()`` only calls into this module
when the caller's config sets ``lagoon_token_cache: true``; when the flag
is off there is *zero* filesystem activity -- no directory created,
nothing probed. This is the only place in the whole collection where a
bearer token touches disk, which is precisely why it is opt-in: the
always-on in-memory cache in ``auth.py`` has no credential-at-rest
exposure at all, and most operators do not need more than it offers.
Enabling this trades that posture for reuse across tasks (and across
separate ``ansible-playbook`` runs), which the in-memory cache cannot
provide because Ansible forks a fresh worker per (host, task) pair.

**A predictable path under $HOME is not the shared-temp-directory defect
this collection fixed elsewhere.** ``ssh.py``'s docstring describes v1's
Critical finding: a private key written to a fixed, predictable path
inside the system-wide temporary directory. The exploit there needs a
*world-writable* parent -- that is what lets an unrelated local user
pre-create the path as a symlink, or win a race to read it.
``$XDG_CACHE_HOME``/``~/.cache`` are not world-writable, so a stable,
predictable filename underneath one is not the same class of defect, and
this module deliberately does not try to randomise it (a random name
would make cross-process lookup impossible, which is the entire feature).
The read path's ownership and mode checks in :func:`read_cached_token`
are the backstop. Please do not flag this as that bug by pattern-matching
on "predictable path" -- the difference is the writability of the parent,
not the guessability of the name.

**No ``finally``-block deletion, deliberately.** ``ssh.py`` removes the
SSH private key in a ``finally`` block, since that key is genuinely
single-use per grant call. That requirement does **not** transfer to
this cache: a cross-process cache whose writing worker deletes it on
exit can never serve a second task or a second run, which defeats the
only reason the feature exists. Entries age out instead, via the
token's own ``exp`` claim, checked by ``token.token_is_valid()`` on
every read. Do not "fix" this by adding cleanup -- doing so reintroduces
a single-use cache that looks like it works.

**Agent auth shares one cache entry per (endpoint, host, port, user)
tuple -- accepted, with eyes open.** ``auth.cache_key()`` folds in a
hash of the private key content or the key file path, but under SSH
agent authentication (neither supplied) there is no key material to
hash, so that component is empty and the key degenerates to the
connection tuple. The in-memory cache in ``auth.py`` accepts that
collision on the grounds that the agent socket cannot change
mid-process, so a collision is not observable. **That justification
does not transfer to this cache**, which outlives the process: a later
``ansible-playbook`` run, whose agent holds a *different* identity, can
read an entry written by an earlier one.

The residual risk, stated plainly: within a single OS user account, a run
may be served a token minted for a different Lagoon identity that the
same OS user also controls. The consequences are mis-attribution in
Lagoon's audit trail, and -- if the two identities differ in privilege --
a run acting as the wrong one until the cached token expires.

Accepted anyway, because the trust boundary here is the OS user account.
Both agent identities are already reachable by that account (they are
loaded in its agent), so this is wrong-identity *selection* within a
boundary, not privilege escalation across one. The cache is off by
default, and an operator who turns it on is choosing to persist a bearer
token under their own ``$HOME``.

Not disambiguated, and the alternatives were considered: the only sound
discriminator is the agent's loaded-key fingerprint set (``ssh-add -l``),
which would put a new external binary, its output parsing, and its
failure modes inside a security-sensitive key-derivation path -- a poor
trade for a within-boundary mix-up. ``SSH_AUTH_SOCK`` itself is not
usable as a discriminator: it is typically a random per-run temp path,
so hashing it in would defeat cache reuse rather than protect it.

Operators who need the identities kept apart have two options today, both
better than a fingerprint hash: supply ``lagoon_ssh_private_key_file``,
whose path participates in ``auth.cache_key()``, or grant once and
``set_fact`` the token for the play.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json
import os
import re
import stat
import tempfile

from .errors import LagoonConfigError
from .token import token_is_valid

# NOTE: this module must never import .auth -- auth.py imports this one.
# The `key` argument to the public functions below is always the value
# auth.cache_key() produced, passed in by the caller rather than
# recomputed here, which is what keeps the dependency acyclic.

_CACHE_DIR_NAME = 'ansible-lagoon'
_XDG_CACHE_HOME_ENV = 'XDG_CACHE_HOME'

# auth.cache_key() can only ever return a lowercase hex sha256 digest, so
# a positive allowlist is both stricter and simpler than blocklisting the
# path separators and '..' that a traversal attempt would need. Anything
# failing this means a caller bypassed cache_key(), which is a programming
# defect rather than a cache state -- hence LagoonConfigError, not a miss.
#
# \A/\Z rather than ^/$: `$` matches immediately before a trailing '\n' as
# well as at the true end of the string, so '^[0-9a-f]{64}$' would accept
# 64 hex characters followed by a newline. cache_key() itself can never
# produce that (it is a bare hexdigest()), but this check exists
# specifically to catch a caller that bypassed cache_key() -- a caller
# that has already done that is not one you can assume is well-behaved.
_KEY_RE = re.compile(r'\A[0-9a-f]{64}\Z')

_DIR_MODE = 0o700
_FILE_MODE = 0o600

# Any permission bit for group or other. A credential file carrying these
# is refused on read.
_FORBIDDEN_FILE_BITS = 0o077


def cache_dir():
    """Return the cache directory path, creating it at mode 0700 if absent.

    ``$XDG_CACHE_HOME/ansible-lagoon`` when ``XDG_CACHE_HOME`` is set and
    non-empty, else ``~/.cache/ansible-lagoon``. Never the system-wide
    temporary directory -- see the module docstring for why a predictable
    path under ``$HOME`` is not the defect ``ssh.py`` fixed.

    The directory is **created** by this call, so it must only ever be
    reached from the opt-in path: ``auth.resolve_token()`` calls the
    readers/writers below only when ``lagoon_token_cache`` is true, which
    is what makes "zero filesystem activity when disabled" true.
    """
    xdg = os.environ.get(_XDG_CACHE_HOME_ENV)
    if xdg:
        base = xdg
    else:
        base = os.path.join(os.path.expanduser('~'), '.cache')

    path = os.path.join(base, _CACHE_DIR_NAME)

    # makedirs()'s mode is umask-affected, and is ignored entirely when the
    # directory already exists -- so an explicit chmod is required to
    # guarantee 0700 in both cases, not just on first creation.
    os.makedirs(path, mode=_DIR_MODE, exist_ok=True)
    os.chmod(path, _DIR_MODE)
    return path


def read_cached_token(key):
    """Return the cached token string for ``key``, or ``None`` on a miss.

    A miss is any of: no cache file, an unreadable one, one not owned by
    the current effective uid, one carrying any group/other permission
    bit, malformed JSON, a payload without a usable ``token``, or a token
    that :func:`.token.token_is_valid` cannot prove fresh. None of these
    raise -- a cache miss is not an error, it just means the caller falls
    through to an SSH grant.

    A malformed ``key`` **does** raise :class:`.errors.LagoonConfigError`.
    That is deliberately a different category from the misses above: it is
    not a cache state, it is a caller that bypassed
    ``auth.cache_key()``. Degrading it to a miss would produce a cache
    that appears to work while silently caching nothing. Do not "fix" this
    into a miss.
    """
    _validate_key(key)

    try:
        path = os.path.join(cache_dir(), _file_name(key))
        st = os.stat(path)
    except OSError:
        # Two categories collapse into a miss here, both correctly:
        # cache_dir() failing to resolve or create the directory (a
        # read-only filesystem, an unset or unwritable $HOME -- common in
        # minimal containers), and stat() failing on the entry itself
        # (ENOENT for no entry yet, EACCES for one we cannot even stat).
        # Neither is an error worth failing a task over: the caller simply
        # falls through to an SSH grant. This is also what keeps a bare
        # OSError from escaping resolve_token() untyped and bypassing the
        # collection's error taxonomy.
        return None

    if not _ownership_is_safe(st) or stat.S_IMODE(st.st_mode) & \
            _FORBIDDEN_FILE_BITS:
        # Refuse, do not repair: no chmod, no unlink. A credential file
        # with the wrong owner or wider-than-0600 permissions is evidence
        # that something other than this collection has touched it, and
        # silently normalising it would erase that signal. Treating it as
        # a miss costs one SSH grant; "helpfully" fixing it costs the only
        # indication an operator would ever get.
        return None

    try:
        with open(path, 'r') as f:
            payload = json.loads(f.read())
    except (OSError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None

    token = payload.get('token')
    if not isinstance(token, str) or not token:
        return None

    # This is what ages entries out, in place of the finally-block
    # deletion ssh.py uses for the SSH key (see the module docstring).
    if not token_is_valid(token):
        return None

    return token


def write_cached_token(key, token):
    """Atomically write ``token`` to ``token-<key>.json`` at mode 0600.

    Returns ``True`` on success and ``False`` if the write failed for an
    environmental reason -- a read-only or absent ``$HOME``, a full disk,
    a permissions problem on the cache directory. Caching is
    opportunistic: the caller has already obtained a working token by the
    time this runs, so a failure here must never turn a successful grant
    into a failed task. The caller is free to ignore the return value.

    Raises :class:`.errors.LagoonConfigError` for a malformed ``key``,
    which -- as in :func:`read_cached_token` -- is a caller defect rather
    than an environmental failure, and so is deliberately not swallowed.

    The payload is a JSON object (``{"token": ...}``) rather than a bare
    string so a future field can be added without a format break.
    Deliberately does **not** store ``expires_in``: freshness is read from
    the token's own ``exp`` claim, and a second copy of that fact would be
    a divergence waiting to happen.
    """
    _validate_key(key)

    fd = None
    tmp_path = None
    try:
        directory = cache_dir()
        final_path = os.path.join(directory, _file_name(key))

        # dir=directory keeps the temp file on the same filesystem, which
        # is what makes the os.replace() below atomic rather than a
        # cross-device copy. The dotted prefix and .tmp suffix keep an
        # orphaned temp from ever matching _file_name()'s read pattern.
        fd, tmp_path = tempfile.mkstemp(
            dir=directory, prefix='.token-', suffix='.tmp')

        # Set the mode explicitly rather than relying on mkstemp's
        # documented 0600 -- the guarantee we want asserted is this line,
        # and it holds before any token bytes are written.
        os.fchmod(fd, _FILE_MODE)
        os.write(fd, json.dumps({'token': token}).encode('utf-8'))
        os.close(fd)
        fd = None

        os.replace(tmp_path, final_path)
        return True
    except OSError:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path is not None:
            # Remove the orphan. This is not the finally-block deletion the
            # module docstring rules out -- that rule protects the *final*
            # cache entry, which is the thing later processes need. A temp
            # file that never became an entry is just a mode-0600 file
            # holding a live bearer token with nothing to read it, so it
            # gets cleaned up.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False


def _file_name(key):
    return 'token-%s.json' % key


def _ownership_is_safe(st):
    # os.geteuid() is absent on Windows. Ansible controllers are not
    # supported on Windows and this module is controller-side only, so the
    # guard is defensive tidiness rather than a support claim -- do not
    # read it as one, and do not build further Windows accommodation on
    # top of it. Where the check cannot run, the mode check still applies.
    if not hasattr(os, 'geteuid'):
        return True
    return st.st_uid == os.geteuid()


def _validate_key(key):
    """Raise :class:`.errors.LagoonConfigError` unless ``key`` is a
    lowercase hex sha256 digest, as ``auth.cache_key()`` produces.

    Runs before any path construction or filesystem call, so a
    traversal-shaped key cannot reach the filesystem even momentarily.
    The message describes the shape of the problem and never echoes the
    offending value back -- the same discipline ``token.py`` and
    ``ssh.py`` apply to secrets, kept here for consistency even though a
    cache key is not itself sensitive.
    """
    if not isinstance(key, str):
        raise LagoonConfigError(
            "invalid cache key: expected a string, got %s" %
            type(key).__name__)

    if not _KEY_RE.match(key):
        raise LagoonConfigError(
            "invalid cache key: expected a 64-character lowercase hex "
            "sha256 digest as produced by auth.cache_key(), got a "
            "%d-character value" % len(key))
