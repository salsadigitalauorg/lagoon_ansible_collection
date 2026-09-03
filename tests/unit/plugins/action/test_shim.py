from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import ast
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase

from .....plugins.action import LagoonActionShim
from .....plugins.module_utils.errors import LagoonAuthError, LagoonConfigError

_MODULE_PATH = (
    'ansible_collections.salsadigitalauorg.lagoon.plugins.action')
_SSH_MODULE_PATH = (
    'ansible_collections.salsadigitalauorg.lagoon.plugins'
    '.module_utils.ssh')


def _grant_response():
    return MagicMock(
        returncode=0,
        stdout=json.dumps(
            {'access_token': 'granted-token', 'expires_in': 3600}
        ).encode('utf-8'),
        stderr=b'')


def _make_shim(task_args=None, action='salsadigitalauorg.lagoon.whoami_info'):
    task = MagicMock()
    task.args = dict(task_args or {})
    task.action = action
    task.async_val = False
    task.check_mode = False

    connection = MagicMock()
    connection._shell.tmpdir = 'ignored'

    play_context = MagicMock()
    loader = MagicMock()

    templar = MagicMock()
    # Identity templating by default -- individual tests override this
    # when they need to assert a specific templated value was used.
    templar.template.side_effect = lambda value: value

    shared_loader_obj = MagicMock()

    shim = LagoonActionShim(
        task, connection, play_context, loader, templar, shared_loader_obj)
    shim._display = MagicMock()
    return shim


class ShimTestCase(unittest.TestCase):

    def setUp(self):
        # ActionBase.run() drives tmp-path/async/check-mode machinery that
        # is not this shim's concern -- the shim's own contract is what it
        # does with the (mocked) result super().run() hands back, not the
        # base class's own tmp-path bookkeeping.
        patcher = patch.object(ActionBase, 'run', return_value={})
        self.mock_super_run = patcher.start()
        self.addCleanup(patcher.stop)


class TestTokenInjection(ShimTestCase):

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_token_injected_as_lagoon_api_token(self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(task_args={'other_arg': 'value'})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={})

        call_kwargs = shim._execute_module.call_args.kwargs
        self.assertEqual(
            call_kwargs['module_args']['lagoon_api_token'],
            'resolved-token')

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_other_task_args_pass_through_unmodified(self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(task_args={'name': 'my-project', 'weight': 5})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={})

        call_kwargs = shim._execute_module.call_args.kwargs
        module_args = call_kwargs['module_args']
        self.assertEqual(module_args['name'], 'my-project')
        self.assertEqual(module_args['weight'], 5)

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_task_args_dict_itself_never_mutated(self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(task_args={'name': 'my-project'})
        shim._execute_module = MagicMock(return_value={})
        original_args = dict(shim._task.args)

        shim.run(task_vars={})

        self.assertEqual(shim._task.args, original_args)
        self.assertNotIn('lagoon_api_token', shim._task.args)

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_module_name_defaults_to_task_action(self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(action='salsadigitalauorg.lagoon.whoami_info')
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={})

        call_kwargs = shim._execute_module.call_args.kwargs
        self.assertEqual(
            call_kwargs['module_name'],
            'salsadigitalauorg.lagoon.whoami_info')


class TestTaskVarsTemplating(ShimTestCase):

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_task_vars_sourced_values_are_templated(self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(task_args={})
        shim._execute_module = MagicMock(return_value={})
        shim._templar.template.side_effect = \
            lambda value: value.replace('{{ x }}', 'templated-host')

        shim.run(task_vars={'lagoon_ssh_host': '{{ x }}'})

        shim._templar.template.assert_any_call('{{ x }}')
        config = mock_resolve.call_args.args[0]
        self.assertEqual(config['ssh_host'], 'templated-host')

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_task_arg_token_takes_precedence_over_task_vars(
            self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(
            task_args={'lagoon_api_token': 'task-arg-token'})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={'lagoon_api_token': 'task-vars-token'})

        config = mock_resolve.call_args.args[0]
        self.assertEqual(config['token'], 'task-arg-token')
        # Task-arg-sourced value must not be re-templated -- it was
        # already templated by Ansible itself.
        shim._templar.template.assert_not_called()

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_task_vars_used_when_task_arg_absent(self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(task_args={})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={'lagoon_api_token': 'from-task-vars'})

        config = mock_resolve.call_args.args[0]
        self.assertEqual(config['token'], 'from-task-vars')


class TestAuthFailurePropagation(ShimTestCase):

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_lagoon_config_error_becomes_ansible_error(self, mock_resolve):
        mock_resolve.side_effect = LagoonConfigError("no usable config")
        shim = _make_shim()
        shim._execute_module = MagicMock(return_value={})

        with self.assertRaises(AnsibleError):
            shim.run(task_vars={})

        shim._execute_module.assert_not_called()

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_lagoon_auth_error_becomes_ansible_error(self, mock_resolve):
        mock_resolve.side_effect = LagoonAuthError("grant failed")
        shim = _make_shim()
        shim._execute_module = MagicMock(return_value={})

        with self.assertRaises(AnsibleError):
            shim.run(task_vars={})

        shim._execute_module.assert_not_called()

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_ansible_error_message_does_not_contain_token_value(
            self, mock_resolve):
        secret_looking_value = 'secret-shaped-key-material'
        mock_resolve.side_effect = LagoonAuthError(
            "grant failed for unrelated reasons")
        shim = _make_shim(
            task_args={'lagoon_ssh_private_key': secret_looking_value})
        shim._execute_module = MagicMock(return_value={})

        with self.assertRaises(AnsibleError) as ctx:
            shim.run(task_vars={})

        self.assertNotIn(secret_looking_value, str(ctx.exception))


class TestAuthRelatedKeyInjectionScope(ShimTestCase):

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_endpoint_setdefault_does_not_clobber_explicit_task_arg(
            self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(
            task_args={'lagoon_api_endpoint': 'https://explicit.example'})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={
            'lagoon_api_endpoint': 'https://from-vars.example'})

        module_args = shim._execute_module.call_args.kwargs['module_args']
        self.assertEqual(
            module_args['lagoon_api_endpoint'], 'https://explicit.example')

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_endpoint_injected_from_task_vars_when_absent(
            self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(task_args={})
        shim._execute_module = MagicMock(return_value={})

        shim.run(
            task_vars={'lagoon_api_endpoint': 'https://from-vars.example'})

        module_args = shim._execute_module.call_args.kwargs['module_args']
        self.assertEqual(
            module_args['lagoon_api_endpoint'],
            'https://from-vars.example')

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_validate_certs_setdefault_does_not_clobber_explicit_task_arg(
            self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(task_args={'validate_certs': False})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={'validate_certs': True})

        module_args = shim._execute_module.call_args.kwargs['module_args']
        self.assertFalse(module_args['validate_certs'])

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_only_auth_related_keys_are_added_to_module_args(
            self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(task_args={'name': 'my-project'})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={
            'lagoon_ssh_host': 'lagoon.example.test',
            'unrelated_var': 'must-not-appear',
        })

        module_args = shim._execute_module.call_args.kwargs['module_args']
        self.assertNotIn('unrelated_var', module_args)
        self.assertNotIn('lagoon_ssh_host', module_args)
        self.assertEqual(
            set(module_args) - {'name'},
            {'lagoon_api_token'})

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_only_auth_related_keys_added_when_endpoint_and_certs_present(
            self, mock_resolve):
        # Unlike the test above, this actually exercises both setdefault
        # branches (lagoon_api_endpoint and validate_certs) alongside an
        # unrelated task arg and an unrelated task_vars entry, so the
        # "only auth-related keys" claim is proven with all injection
        # paths live simultaneously, not vacuously skipped.
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(task_args={'name': 'my-project'})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={
            'lagoon_api_endpoint': 'https://from-vars.example',
            'validate_certs': False,
            'unrelated_var': 'must-not-appear',
        })

        module_args = shim._execute_module.call_args.kwargs['module_args']
        self.assertNotIn('unrelated_var', module_args)
        self.assertEqual(
            set(module_args) - {'name'},
            {'lagoon_api_token', 'lagoon_api_endpoint', 'validate_certs'})
        self.assertEqual(
            module_args['lagoon_api_endpoint'],
            'https://from-vars.example')
        self.assertFalse(module_args['validate_certs'])


class TestBoolAndIntCoercion(ShimTestCase):

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_batch_mode_string_false_from_task_vars_coerces_to_bool(
            self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(task_args={})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={'lagoon_ssh_batch_mode': 'false'})

        config = mock_resolve.call_args.args[0]
        self.assertIs(config['batch_mode'], False)

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_batch_mode_string_true_from_task_vars_coerces_to_bool(
            self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(task_args={})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={'lagoon_ssh_batch_mode': 'true'})

        config = mock_resolve.call_args.args[0]
        self.assertIs(config['batch_mode'], True)

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_batch_mode_accepts_full_ansible_boolean_set(
            self, mock_resolve):
        # 'y' and 't' are true to Ansible's own boolean() but were false
        # to the old hand-rolled truthy set -- lock in parity with the
        # real thing now that boolean() is used directly.
        mock_resolve.return_value = 'resolved-token'
        for value in ('y', 't', 'yes', 'on', '1', True):
            shim = _make_shim(task_args={})
            shim._execute_module = MagicMock(return_value={})
            shim.run(task_vars={'lagoon_ssh_batch_mode': value})
            config = mock_resolve.call_args.args[0]
            self.assertIs(
                config['batch_mode'], True,
                "expected %r to coerce to True" % (value,))

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_batch_mode_garbage_string_raises_config_error_not_silent_false(
            self, mock_resolve):
        # A typo like 'tru' must be rejected, not silently resolved to
        # False -- that would silently disable a security-relevant
        # default rather than surfacing the operator's mistake.
        shim = _make_shim(task_args={})
        shim._execute_module = MagicMock(return_value={})

        with self.assertRaises(AnsibleError) as ctx:
            shim.run(task_vars={'lagoon_ssh_batch_mode': 'tru'})

        self.assertIn('lagoon_ssh_batch_mode', str(ctx.exception))
        mock_resolve.assert_not_called()
        shim._execute_module.assert_not_called()

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_ssh_port_string_from_task_vars_coerces_to_int(
            self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(task_args={})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={'lagoon_ssh_port': '2222'})

        config = mock_resolve.call_args.args[0]
        self.assertEqual(config['ssh_port'], 2222)
        self.assertIsInstance(config['ssh_port'], int)

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_ssh_port_garbage_string_raises_ansible_error_not_bare_valueerror(
            self, mock_resolve):
        shim = _make_shim(task_args={})
        shim._execute_module = MagicMock(return_value={})

        with self.assertRaises(AnsibleError) as ctx:
            shim.run(task_vars={'lagoon_ssh_port': 'twenty-two'})

        self.assertNotIsInstance(ctx.exception, ValueError)
        self.assertIn('lagoon_ssh_port', str(ctx.exception))
        mock_resolve.assert_not_called()
        shim._execute_module.assert_not_called()

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_absent_bool_and_int_options_are_omitted_not_none(
            self, mock_resolve):
        # resolve_token() reads some keys via a two-argument
        # config.get(key, default) -- e.g. auth.py's
        # config.get('batch_mode', True) -- which only applies that
        # default when the key is genuinely ABSENT. Inserting an
        # explicit None (the pre-fix behaviour) silently defeats it.
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim(task_args={})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={})

        config = mock_resolve.call_args.args[0]
        self.assertNotIn('batch_mode', config)
        self.assertNotIn('ssh_port', config)
        self.assertNotIn('token_cache', config)
        self.assertNotIn('validate_certs', config)


class TestBatchModeDefaultReachesRequestGrant(ShimTestCase):
    """Regression coverage: an absent bool key must be omitted from the
    config dict, not inserted as an explicit ``None``.
    ``auth.resolve_token()`` reads some keys via a two-argument
    ``config.get('batch_mode', True)``, which only applies that default
    when the key is genuinely absent -- an explicit ``None`` defeats it
    silently and drops ``-o BatchMode=yes`` from the SSH grant.

    Asserting on ``config['batch_mode']`` (as the coercion tests above
    do) cannot catch this -- it goes all the way through
    resolve_token() and request_grant() to the real argv, which is the
    only place the defect is actually observable.
    """

    def setUp(self):
        super(TestBatchModeDefaultReachesRequestGrant, self).setUp()
        from .....plugins.module_utils import auth
        auth.clear_cache()
        self.addCleanup(auth.clear_cache)

    @patch('%s.subprocess.run' % _SSH_MODULE_PATH)
    def test_batch_mode_yes_present_in_argv_via_shim(self, mock_run):
        mock_run.return_value = _grant_response()
        shim = _make_shim(task_args={})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={'lagoon_ssh_host': 'lagoon.example.test'})

        argv = mock_run.call_args.args[0]
        self.assertIn('BatchMode=yes', argv)

    @patch('%s.subprocess.run' % _SSH_MODULE_PATH)
    def test_strict_host_key_checking_default_present_in_argv_via_shim(
            self, mock_run):
        mock_run.return_value = _grant_response()
        shim = _make_shim(task_args={})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={'lagoon_ssh_host': 'lagoon.example.test'})

        argv = mock_run.call_args.args[0]
        self.assertIn('StrictHostKeyChecking=accept-new', argv)

    @patch('%s.subprocess.run' % _SSH_MODULE_PATH)
    def test_explicit_batch_mode_false_omits_flag_via_shim(
            self, mock_run):
        mock_run.return_value = _grant_response()
        shim = _make_shim(task_args={})
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={
            'lagoon_ssh_host': 'lagoon.example.test',
            'lagoon_ssh_batch_mode': False,
        })

        argv = mock_run.call_args.args[0]
        self.assertNotIn('BatchMode=yes', argv)
        self.assertNotIn('BatchMode=no', argv)


class TestWarnWiring(ShimTestCase):

    @patch('%s.auth.resolve_token' % _MODULE_PATH)
    def test_warn_kwarg_is_display_warning(self, mock_resolve):
        mock_resolve.return_value = 'resolved-token'
        shim = _make_shim()
        shim._execute_module = MagicMock(return_value={})

        shim.run(task_vars={})

        self.assertEqual(
            mock_resolve.call_args.kwargs['warn'], shim._display.warning)


class TestNoForbiddenImportsElsewhere(unittest.TestCase):
    """ansible.errors must be imported here, and only here, across the
    whole plugins/ tree outside plugins/action/."""

    def test_ansible_errors_only_imported_under_plugins_action(self):
        repo_root = os.path.normpath(os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..'))
        plugins_root = os.path.join(repo_root, 'plugins')
        offenders = []
        for dirpath, _dirnames, filenames in os.walk(plugins_root):
            rel_dir = os.path.relpath(dirpath, repo_root)
            for filename in filenames:
                if not filename.endswith('.py'):
                    continue
                rel_path = os.path.join(rel_dir, filename)
                if rel_path.startswith(
                        'plugins' + os.sep + 'action' + os.sep) or \
                        rel_path == os.path.join('plugins', 'action.py'):
                    continue
                full_path = os.path.join(dirpath, filename)
                tree = ast.parse(open(full_path).read())
                for n in ast.walk(tree):
                    if isinstance(n, ast.Import):
                        if any(a.name == 'ansible.errors' or
                               a.name.startswith('ansible.errors.')
                               for a in n.names):
                            offenders.append(rel_path)
                    if isinstance(n, ast.ImportFrom) and n.module and \
                            (n.module == 'ansible.errors' or
                             n.module.startswith('ansible.errors.')):
                        offenders.append(rel_path)
        self.assertEqual(offenders, [])


if __name__ == '__main__':
    unittest.main()
