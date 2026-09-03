from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.errors import AnsibleError
from ansible.module_utils.parsing.convert_bool import boolean
from ansible.plugins.action import ActionBase

from ..module_utils import auth
from ..module_utils.errors import LagoonConfigError, LagoonError

# Task-arg/task-vars key -> resolve_token() config key.
_STR_KEYS = (
    ('lagoon_api_token', 'token'),
    ('lagoon_api_endpoint', 'endpoint'),
    ('lagoon_ssh_host', 'ssh_host'),
    ('lagoon_ssh_user', 'ssh_user'),
    ('lagoon_ssh_private_key', 'private_key'),
    ('lagoon_ssh_private_key_file', 'private_key_file'),
    ('lagoon_ssh_known_hosts_file', 'known_hosts_file'),
    ('lagoon_ssh_options', 'ssh_options'),
    ('lagoon_ssh_strict_host_key_checking', 'strict_host_key_checking'),
)
_INT_KEYS = (
    ('lagoon_ssh_port', 'ssh_port'),
)
_BOOL_KEYS = (
    ('lagoon_ssh_batch_mode', 'batch_mode'),
    ('lagoon_token_cache', 'token_cache'),
    ('validate_certs', 'validate_certs'),
)


def _to_bool(arg_key, value):
    """Coerce a resolved option to a real ``bool``.

    Delegates to Ansible's own ``boolean()`` rather than a hand-rolled
    truthy set, so e.g. ``lagoon_ssh_batch_mode: 'y'`` is treated exactly
    as any other Ansible boolean option would be -- including rejecting a
    typo like ``'tru'`` instead of silently resolving it to ``False``.
    Raises :class:`.errors.LagoonConfigError` (naming the option, never
    its value) rather than letting ``boolean()``'s bare ``TypeError``
    escape untyped.
    """
    try:
        return boolean(value)
    except TypeError:
        raise LagoonConfigError(
            "%s is not a valid boolean value" % arg_key)


def _to_int(arg_key, value):
    """Coerce a resolved option to a real ``int``.

    Raises :class:`.errors.LagoonConfigError` (naming the option, never
    its value) rather than letting a bare ``ValueError`` from ``int()``
    escape untyped -- a malformed ``lagoon_ssh_port`` is a caller
    configuration problem, the same category :func:`.auth.resolve_token`
    already uses for e.g. supplying both SSH key options at once.
    """
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except ValueError:
        raise LagoonConfigError(
            "%s is not a valid integer value" % arg_key)


class LagoonActionShim(ActionBase):
    """Controller-side base class that resolves a Lagoon API bearer token
    and injects it into the delegated module's args, then hands off to the
    real module via :meth:`_execute_module`.

    Token resolution and injection is this shim's only responsibility. It
    holds no resource-specific logic: if a change here only makes sense for
    one particular module's business logic, it does not belong in this
    file.

    This is a base class, not a single collection-wide action plugin --
    ``action_groups`` only affects ``module_defaults`` sharing, not
    action-plugin dispatch. Ansible dispatches to an action plugin only
    when a same-named file exists under ``plugins/action/``, so every
    module needs its own one-line subclass file under
    ``plugins/action/<name>.py``. Subclasses need only set ``module_name``
    if it differs from ``self._task.action`` -- the default is correct for
    the common case.

    ``module_utils`` never imports ``ansible.errors``. This class is the
    seam where a :class:`.module_utils.errors.LagoonError` becomes an
    :class:`ansible.errors.AnsibleError`.
    """

    def run(self, tmp=None, task_vars=None):
        task_vars = task_vars or {}
        result = super(LagoonActionShim, self).run(tmp, task_vars)
        del tmp

        try:
            config = self._build_auth_config(task_vars)
            token = auth.resolve_token(config, warn=self._display.warning)
        except LagoonError as e:
            raise AnsibleError(str(e))

        module_args = dict(self._task.args)
        module_args['lagoon_api_token'] = token
        if 'endpoint' in config:
            module_args.setdefault('lagoon_api_endpoint', config['endpoint'])
        if 'validate_certs' in config:
            module_args.setdefault('validate_certs', config['validate_certs'])

        result.update(self._execute_module(
            module_name=self._task.action,
            module_args=module_args,
            task_vars=task_vars))
        return result

    def _build_auth_config(self, task_vars):
        """Build the plain dict :func:`.module_utils.auth.resolve_token`
        expects, applying the precedence order:
        explicit task args -> ``task_vars`` (templated) -> module/argspec
        defaults (left to ``resolve_token`` itself, via ``.get()``
        fallbacks -- this method never invents a default of its own).

        An option that resolves to nothing is **omitted from the dict
        entirely**, never inserted as ``None``. ``resolve_token`` reads
        some keys with a two-argument ``config.get(key, default)`` (e.g.
        ``batch_mode``), which only applies that default when the key is
        *absent* -- an explicit ``None`` would defeat it silently. Every
        loop below must preserve this "resolved or absent" shape; do not
        "simplify" it back to always setting a key.

        Task args arrive already templated by Ansible; only values pulled
        from ``task_vars`` are passed through ``self._templar.template()``
        before use, matching v1's ``createClient`` convention. Never
        mutates ``self._task.args``.
        """
        config = {}

        for arg_key, config_key in _STR_KEYS:
            value = self._resolve_value(arg_key, task_vars)
            if value is not None:
                config[config_key] = value

        for arg_key, config_key in _INT_KEYS:
            value = self._resolve_value(arg_key, task_vars)
            if value is not None:
                config[config_key] = _to_int(arg_key, value)

        for arg_key, config_key in _BOOL_KEYS:
            value = self._resolve_value(arg_key, task_vars)
            if value is not None:
                config[config_key] = _to_bool(arg_key, value)

        return config

    def _resolve_value(self, key, task_vars):
        if key in self._task.args:
            return self._task.args[key]
        if key in task_vars:
            return self._templar.template(task_vars[key])
        return None
