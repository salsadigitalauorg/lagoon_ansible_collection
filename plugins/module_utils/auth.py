from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import hashlib
import os

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
# file-backed cache (module_utils/cache.py, P2-S4) or an explicit
# `lagoon_api_token` set once via `set_fact`. See P2-D2 in
# docs/plans/v3-phase2-stories.md -- this corrects parent plan §4's "one
# grant per play" claim.
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
        lagoon_ssh_options=dict(type='raw', default=None),
        lagoon_ssh_strict_host_key_checking=dict(
            type='str', default=_DEFAULT_STRICT_HOST_KEY_CHECKING),
        lagoon_token_cache=dict(type='bool', default=False),
    )
    if spec:
        argument_spec.update(spec)
    return argument_spec


def resolve_token(config):
    """Resolve a bearer token for ``config``, a plain dict with (at
    least): ``endpoint``, ``token`` (explicit, may be ``None``),
    ``ssh_host``, ``ssh_port``, ``ssh_user``, ``private_key``,
    ``private_key_file``, ``ssh_options``, ``strict_host_key_checking``,
    ``known_hosts_file``.

    Resolution order (plan 7.2), stopping at the first usable step:

      1. ``config['token']`` (explicit ``lagoon_api_token``) -> used
         as-is, no validation, no caching.
      2. ``LAGOON_API_TOKEN`` env var -> same.
      3. The process-scoped in-memory cache entry for this config's
         :func:`cache_key`, if :func:`.token.token_is_valid` -> used.
      4. :func:`.ssh.request_grant` -> cache the result -> use it.

    Raises :class:`.errors.LagoonConfigError` if nothing usable is
    configured (no token, no env var, no valid cache entry, and no
    ``ssh_host`` to grant a new one from, or an ``ssh_host`` with neither
    a private key nor a private key file to grant with) -- this is a
    caller configuration problem, not an auth failure, so it is
    deliberately not a :class:`.errors.LagoonAuthError`.

    Raises :class:`.errors.LagoonAuthError` if the SSH grant itself
    fails (wraps :func:`.ssh.request_grant`'s own failure modes).

    Steps 1-2 use the supplied token exactly as given and never call
    :func:`.token.token_is_valid` -- the plan does not ask the collection
    to second-guess a token the operator supplied directly.
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

    ssh_host = config.get('ssh_host')
    if not ssh_host:
        raise LagoonConfigError(
            "no usable Lagoon auth configuration: no lagoon_api_token, "
            "no LAGOON_API_TOKEN, no valid cached token, and no "
            "lagoon_ssh_host to request a new grant from")

    private_key = config.get('private_key')
    private_key_file = config.get('private_key_file')
    if bool(private_key) == bool(private_key_file):
        raise LagoonConfigError(
            "exactly one of lagoon_ssh_private_key / "
            "lagoon_ssh_private_key_file is required to request an SSH "
            "grant")

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
    )

    _cache[key] = access_token
    return access_token


def cache_key(config):
    """sha256 hex digest over (``endpoint``, ``ssh_host``, ``ssh_port``,
    ``ssh_user``, ``sha256(key_material)``) so two distinct identities
    never collide and raw key material never appears in the key itself.

    ``key_material`` is the private key content if given, else the
    ``private_key_file`` path (not its content -- the file is not read
    here).
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
