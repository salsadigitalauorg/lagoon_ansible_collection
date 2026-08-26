from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import hashlib
import os

from .cache import read_cached_token, write_cached_token
from .errors import LagoonConfigError
from .ssh import request_grant
from .token import token_is_valid

# Module-level, process-scoped cache: {cache_key(): token}.
#
# This is deliberately NOT play-scoped. Ansible forks a WorkerProcess per
# (host, task) pair and action plugins execute only in the child, so this
# dict is visible across every iteration of a `loop:` on ONE task -- which
# is where Lagoon's N+1 grant pattern actually bites -- but a fresh
# interpreter (and therefore a fresh, empty cache) starts for every new
# task. Cross-task reuse within a play requires either the opt-in
# file-backed cache (module_utils/cache.py, enabled via
# `lagoon_token_cache`, off by default) or an explicit
# `lagoon_api_token` set once via `set_fact`. See P2-D2 in
# docs/plans/v3-phase2-stories.md -- this corrects parent plan §4's "one
# grant per play" claim.
#
# SSH_AUTH_SOCK note: when neither private_key nor private_key_file is
# supplied, resolve_token() requests a grant via the SSH agent (P2-D9).
# This works only because .ssh.request_grant() passes no `env=` kwarg to
# subprocess.run(), so the collection's own environment -- including
# SSH_AUTH_SOCK -- is inherited by the ssh child process unmodified. If a
# future change ever adds an explicit `env=` there, agent auth breaks
# silently. This is the path AWX/ansible-runner (which loads the grant
# key into an agent socket rather than a file) and a locally mounted
# SSH_AUTH_SOCK both rely on.
_cache = {}

_DEFAULT_SSH_PORT = 22
_DEFAULT_SSH_USER = 'lagoon'
_DEFAULT_STRICT_HOST_KEY_CHECKING = 'accept-new'
_DEFAULT_SSH_TIMEOUT = 30

_LAGOON_API_TOKEN_ENV = 'LAGOON_API_TOKEN'


def auth_argument_spec(spec=None):
    """Canonical argspec fragment for auth-related module options.

    Merged with an optional caller-supplied ``spec`` dict; keys in
    ``spec`` win on conflict. This is the single source of truth for the
    auth option set (P2-D6) -- ``plugins/doc_fragments/auth.py`` is a
    second, independent declaration of the same options for
    ``antsibull-docs``, and a drift test (P2-S5) binds the two together
    so they cannot silently diverge.

    Note for callers using :class:`.client.LagoonClient` with an
    ``AnsibleModule`` instance: ``client.py``'s ``_fetch_url_call`` reads
    ``module.params['validate_certs']`` directly. Any module doing this
    must declare ``validate_certs`` in its own argument_spec (which this
    fragment provides) or the client synthesises the key at runtime and
    it never appears in ``ansible-doc`` output.
    """
    argument_spec = dict(
        lagoon_api_token=dict(type='str', no_log=True, default=None),
        lagoon_api_endpoint=dict(type='str', default=None),
        validate_certs=dict(type='bool', default=True),
        lagoon_ssh_host=dict(type='str', default=None),
        lagoon_ssh_port=dict(type='int', default=_DEFAULT_SSH_PORT),
        lagoon_ssh_user=dict(type='str', default=_DEFAULT_SSH_USER),
        lagoon_ssh_private_key=dict(type='str', no_log=True, default=None),
        lagoon_ssh_private_key_file=dict(type='path', default=None),
        lagoon_ssh_known_hosts_file=dict(type='path', default=None),
        lagoon_ssh_options=dict(type='raw', default=None),
        lagoon_ssh_strict_host_key_checking=dict(
            type='str', default=_DEFAULT_STRICT_HOST_KEY_CHECKING),
        lagoon_ssh_batch_mode=dict(type='bool', default=True),
        lagoon_token_cache=dict(type='bool', default=False),
    )
    if spec:
        argument_spec.update(spec)
    return argument_spec


def resolve_token(config, warn=None):
    """Resolve a bearer token for ``config``, a plain dict with (at
    least): ``endpoint``, ``token`` (explicit, may be ``None``),
    ``ssh_host``, ``ssh_port``, ``ssh_user``, ``private_key``,
    ``private_key_file``, ``ssh_options``, ``strict_host_key_checking``,
    ``known_hosts_file``, ``batch_mode`` (defaults ``True`` if absent --
    see :func:`.ssh.request_grant`'s docstring for why), ``token_cache``
    (defaults ``False`` if absent -- see step 3b below).

    ``warn``, if supplied, is a callable taking a single string message
    (the same shape as Ansible's ``AnsibleModule.warn``/action plugin
    ``_display.warning`` methods), used **only** to surface a degraded
    file-cache write -- see step 4 below. It is never required for a
    resolution to succeed: defaults to a no-op, and any exception it
    itself raises is swallowed rather than allowed to fail a task that
    already has a working token.

    Resolution order (plan 7.2), stopping at the first usable step:

      1. ``config['token']`` (explicit ``lagoon_api_token``) -> used
         as-is, no validation, no caching.
      2. ``LAGOON_API_TOKEN`` env var -> same.
      3. The process-scoped in-memory cache entry for this config's
         :func:`cache_key`, if :func:`.token.token_is_valid` -> used.
      3b. The cross-process file cache, **only** when
         ``config['token_cache']`` is true -> used if
         :func:`.cache.read_cached_token` returns a token (it applies the
         same validity check internally, plus ownership/permission
         checks).
      4. :func:`.ssh.request_grant` -> cache the result in memory, and in
         the file cache when enabled -> use it. The in-memory cache is
         always populated at this step regardless of whether the file
         write succeeds, so a broken opt-in file cache degrades to
         "behaves as if it were disabled for this call", not a failure --
         see the ``warn`` note below.

    Step 3b is opt-in (``lagoon_token_cache``, default ``False``) and is
    the only path in the collection that persists a bearer token to disk;
    see ``module_utils/cache.py``'s docstring for the credential-at-rest
    reasoning, the directory/permission posture, and the agent-auth
    cache-key caveat (P2-D11). When the flag is off, this function makes
    no filesystem calls whatsoever.

    A file-cache write failure (:func:`.cache.write_cached_token` returning
    ``False`` -- a read-only ``$HOME``, a full disk, an unset ``$HOME`` in
    a minimal container) never fails this call: the grant already
    succeeded and is already in the in-memory cache, so the task
    proceeds on a token that is simply not persisted this time. ``warn``
    is called with a message describing the failure (never the token
    value) so the operator can see their opt-in feature is not actually
    caching, rather than discovering it only when a later task re-grants
    unexpectedly. This does not fully restore cross-task reuse for *this*
    task -- there is nothing to read back -- but every subsequent
    ``resolve_token()`` call in the same process still hits the in-memory
    cache as normal, and a future process may simply retry the file
    write on its own next grant.

    Note the deliberate asymmetry: a file-cache hit back-fills the
    in-memory cache (so a ``loop:`` over one task reads the file once
    rather than N times), but the in-memory cache is never written
    *through* to disk. Only a token this function granted itself is
    written, and only at step 4 -- a token supplied via steps 1-2 never
    reaches disk, because the operator supplied it directly and did not
    ask the collection to persist it. This is the same
    "don't second-guess an explicit token" boundary that keeps steps 1-2
    away from :func:`.token.token_is_valid`.

    Raises :class:`.errors.LagoonConfigError` if nothing usable is
    configured (no token, no env var, no valid cache entry, and no
    ``ssh_host`` to grant a new one from) or if both ``private_key`` and
    ``private_key_file`` are supplied (ambiguous -- caller must pick
    one) -- this is a caller configuration problem, not an auth
    failure, so it is deliberately not a :class:`.errors.LagoonAuthError`.

    Raises :class:`.errors.LagoonAuthError` if the SSH grant itself
    fails (wraps :func:`.ssh.request_grant`'s own failure modes).

    Steps 1-2 use the supplied token exactly as given and never call
    :func:`.token.token_is_valid` -- the plan does not ask the collection
    to second-guess a token the operator supplied directly.

    Supplying **neither** ``private_key`` nor ``private_key_file`` is
    valid, not an error (P2-D9): it means "authenticate via the SSH
    agent". :func:`.ssh.request_grant` then omits ``-i`` entirely and
    ``ssh`` falls back to agent identities offered over the inherited
    ``SSH_AUTH_SOCK``. This is the path a locally mounted agent socket,
    and AWX/ansible-runner (which loads the grant key into an agent
    socket rather than a file), both rely on. v1 supported this too --
    its ``fetch_token`` action only wrote a key file when
    ``lagoon_ssh_private_key`` was actually set.
    """
    token = config.get('token')
    if token:
        return token

    env_token = os.environ.get(_LAGOON_API_TOKEN_ENV)
    if env_token:
        return env_token

    key = cache_key(config)
    cached_token = _cache.get(key)
    if cached_token is not None and token_is_valid(cached_token):
        return cached_token

    token_cache_enabled = bool(config.get('token_cache'))
    if token_cache_enabled:
        # Opt-in only: read_cached_token() creates the cache directory as a
        # side effect of resolving it, so reaching it while the flag is off
        # would break "zero filesystem activity when disabled".
        file_cached_token = read_cached_token(key)
        if file_cached_token is not None:
            # Back-fill the in-memory cache so subsequent resolutions in
            # this process (loop: iterations on one task) hit the dict
            # rather than re-reading and re-validating the file.
            _cache[key] = file_cached_token
            return file_cached_token

    ssh_host = config.get('ssh_host')
    if not ssh_host:
        raise LagoonConfigError(
            "no usable Lagoon auth configuration: no lagoon_api_token, "
            "no LAGOON_API_TOKEN, no valid cached token, and no "
            "lagoon_ssh_host to request a new grant from")

    private_key = config.get('private_key')
    private_key_file = config.get('private_key_file')
    if private_key and private_key_file:
        raise LagoonConfigError(
            "lagoon_ssh_private_key and lagoon_ssh_private_key_file are "
            "mutually exclusive")

    access_token, _expires_in = request_grant(
        ssh_host,
        config.get('ssh_port') or _DEFAULT_SSH_PORT,
        private_key=private_key,
        private_key_file=private_key_file,
        ssh_options=config.get('ssh_options'),
        strict_host_key_checking=(
            config.get('strict_host_key_checking') or
            _DEFAULT_STRICT_HOST_KEY_CHECKING),
        known_hosts_file=config.get('known_hosts_file'),
        timeout=config.get('timeout') or _DEFAULT_SSH_TIMEOUT,
        ssh_user=config.get('ssh_user') or _DEFAULT_SSH_USER,
        batch_mode=config.get('batch_mode', True),
    )

    _cache[key] = access_token
    if token_cache_enabled:
        # Opportunistic: a False return means the write failed for an
        # environmental reason (read-only HOME, full disk, unset HOME).
        # The grant already succeeded and is already in the in-memory
        # cache above, so this must never fail the task -- it only
        # degrades this call to "the file cache behaved as if disabled".
        # Surface it via warn() so the operator can see their opt-in
        # cache is not actually persisting, rather than only noticing
        # when a later, separate process re-grants unexpectedly.
        if not write_cached_token(key, access_token) and warn is not None:
            _safe_warn(
                warn,
                "lagoon_token_cache is enabled but the token could not "
                "be written to the cache file -- check that the cache "
                "directory is writable. Continuing without the "
                "cross-process cache for this task.")
    return access_token


def cache_key(config):
    """sha256 hex digest over (``endpoint``, ``ssh_host``, ``ssh_port``,
    ``ssh_user``, ``sha256(key_material)``) so two distinct identities
    never collide and raw key material never appears in the key itself.

    ``key_material`` is the private key content if given, else the
    ``private_key_file`` path (not its content -- the file is not read
    here).

    Agent auth (P2-D9: neither ``private_key`` nor ``private_key_file``
    supplied) hashes to an empty ``key_material_hash``, so two distinct
    agent identities sharing the same ``(endpoint, ssh_host, ssh_port,
    ssh_user)`` collide in the cache. Accepted for this in-memory,
    process-scoped cache -- the agent socket cannot change mid-process,
    so a collision here is not observable. Deliberately not disambiguated
    by hashing ``SSH_AUTH_SOCK`` in: that path is typically a random
    per-run temp path, which would defeat cache reuse rather than protect
    it. The cross-process file cache in ``module_utils/cache.py`` (P2-S4)
    has a different lifetime, so it does not inherit this reasoning: it
    records its own decision on the same collision -- also to accept it,
    but for different reasons and with a different residual risk -- in
    that module's docstring (P2-D11).
    """
    private_key = config.get('private_key')
    private_key_file = config.get('private_key_file')

    if private_key:
        material = private_key.encode('utf-8') if \
            isinstance(private_key, str) else private_key
        key_material_hash = hashlib.sha256(material).hexdigest()
    elif private_key_file:
        key_material_hash = hashlib.sha256(
            private_key_file.encode('utf-8')).hexdigest()
    else:
        key_material_hash = ''

    parts = (
        str(config.get('endpoint') or ''),
        str(config.get('ssh_host') or ''),
        str(config.get('ssh_port') or ''),
        str(config.get('ssh_user') or ''),
        key_material_hash,
    )
    digest_input = '\x1f'.join(parts).encode('utf-8')
    return hashlib.sha256(digest_input).hexdigest()


def clear_cache():
    """Test seam: empties the module-level in-memory cache dict."""
    _cache.clear()


def _safe_warn(warn, message):
    """Call ``warn(message)``, swallowing anything ``warn`` itself raises.

    ``warn`` is caller-supplied (an ``AnsibleModule.warn``-shaped
    callable, typically) and its only job here is to surface a
    already-non-fatal degradation (a cache write that failed). A
    resolution that has already produced a working token must not be
    turned into a failure by a broken warn callback -- that would be a
    worse outcome than the thing it was trying to report.
    """
    try:
        warn(message)
    except Exception:
        pass
