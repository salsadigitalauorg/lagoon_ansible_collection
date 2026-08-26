from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import ast
import os
import unittest
from unittest.mock import patch

from .....plugins.module_utils import auth
from .....plugins.module_utils.auth import (
    auth_argument_spec,
    cache_key,
    clear_cache,
    resolve_token,
)
from .....plugins.module_utils.errors import LagoonConfigError

_MODULE_PATH = (
    'ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.auth')


def _config(**overrides):
    config = {
        'endpoint': 'https://api.example.test/graphql',
        'token': None,
        'ssh_host': 'lagoon.example.test',
        'ssh_port': 22,
        'ssh_user': 'lagoon',
        'private_key': 'key-material',
        'private_key_file': None,
        'ssh_options': None,
        'strict_host_key_checking': 'accept-new',
        'known_hosts_file': None,
        'timeout': 30,
    }
    config.update(overrides)
    return config


class AuthTestCase(unittest.TestCase):

    def setUp(self):
        clear_cache()
        os.environ.pop('LAGOON_API_TOKEN', None)

    def tearDown(self):
        clear_cache()
        os.environ.pop('LAGOON_API_TOKEN', None)


class TestResolutionOrder(AuthTestCase):

    @patch('%s.request_grant' % _MODULE_PATH)
    def test_explicit_token_short_circuits_everything(self, mock_grant):
        token = resolve_token(_config(token='explicit-token'))
        self.assertEqual(token, 'explicit-token')
        mock_grant.assert_not_called()

    @patch('%s.request_grant' % _MODULE_PATH)
    def test_env_var_short_circuits_grant(self, mock_grant):
        os.environ['LAGOON_API_TOKEN'] = 'env-token'
        token = resolve_token(_config())
        self.assertEqual(token, 'env-token')
        mock_grant.assert_not_called()

    @patch('%s.token_is_valid' % _MODULE_PATH, return_value=True)
    @patch('%s.request_grant' % _MODULE_PATH)
    def test_valid_cache_entry_short_circuits_grant(
            self, mock_grant, mock_valid):
        config = _config()
        auth._cache[cache_key(config)] = 'cached-token'
        token = resolve_token(config)
        self.assertEqual(token, 'cached-token')
        mock_grant.assert_not_called()

    @patch('%s.request_grant' % _MODULE_PATH)
    def test_all_absent_calls_grant_exactly_once_and_caches(
            self, mock_grant):
        mock_grant.return_value = ('granted-token', 3600)
        config = _config()
        token = resolve_token(config)
        self.assertEqual(token, 'granted-token')
        mock_grant.assert_called_once()
        self.assertEqual(auth._cache[cache_key(config)], 'granted-token')


class TestCacheReuse(AuthTestCase):

    @patch('%s.token_is_valid' % _MODULE_PATH, return_value=True)
    @patch('%s.request_grant' % _MODULE_PATH)
    def test_second_call_with_same_config_avoids_second_grant(
            self, mock_grant, mock_valid):
        mock_grant.return_value = ('granted-token', 3600)
        config = _config()
        resolve_token(config)
        resolve_token(config)
        mock_grant.assert_called_once()

    @patch('%s.token_is_valid' % _MODULE_PATH, return_value=False)
    @patch('%s.request_grant' % _MODULE_PATH)
    def test_expired_cache_entry_triggers_fresh_grant_and_replaces_entry(
            self, mock_grant, mock_valid):
        mock_grant.return_value = ('fresh-token', 3600)
        config = _config()
        auth._cache[cache_key(config)] = 'stale-token'

        token = resolve_token(config)

        self.assertEqual(token, 'fresh-token')
        mock_grant.assert_called_once()
        self.assertEqual(auth._cache[cache_key(config)], 'fresh-token')

    @patch('%s.request_grant' % _MODULE_PATH)
    def test_different_endpoints_produce_independent_cache_entries(
            self, mock_grant):
        mock_grant.side_effect = [
            ('token-a', 3600),
            ('token-b', 3600),
        ]
        config_a = _config(endpoint='https://a.example.test/graphql')
        config_b = _config(endpoint='https://b.example.test/graphql')

        token_a = resolve_token(config_a)
        token_b = resolve_token(config_b)

        self.assertEqual(token_a, 'token-a')
        self.assertEqual(token_b, 'token-b')
        self.assertEqual(mock_grant.call_count, 2)
        self.assertNotEqual(cache_key(config_a), cache_key(config_b))
        self.assertEqual(auth._cache[cache_key(config_a)], 'token-a')
        self.assertEqual(auth._cache[cache_key(config_b)], 'token-b')


class TestClearCacheSeam(AuthTestCase):

    @patch('%s.token_is_valid' % _MODULE_PATH, return_value=True)
    @patch('%s.request_grant' % _MODULE_PATH)
    def test_clear_cache_forces_a_fresh_grant_on_next_call(
            self, mock_grant, mock_valid):
        # Prove the seam actually works: without clear_cache() between
        # these two "isolated" calls, the second call would be a cache
        # hit and request_grant would be called only once total.
        mock_grant.side_effect = [
            ('first-token', 3600),
            ('second-token', 3600),
        ]
        config = _config()

        first = resolve_token(config)
        self.assertEqual(first, 'first-token')
        self.assertEqual(mock_grant.call_count, 1)

        clear_cache()

        second = resolve_token(config)
        self.assertEqual(second, 'second-token')
        self.assertEqual(mock_grant.call_count, 2)


class TestCacheKey(AuthTestCase):

    def test_key_material_absent_from_cache_key_output(self):
        secret_key = 'this-is-the-private-key-material'
        key = cache_key(_config(private_key=secret_key))
        self.assertNotIn(secret_key, key)

    def test_private_key_file_path_absent_from_cache_key_output(self):
        path = '/home/user/.ssh/lagoon_key'
        key = cache_key(
            _config(private_key=None, private_key_file=path))
        self.assertNotIn(path, key)

    def test_same_config_produces_same_key(self):
        config = _config()
        self.assertEqual(cache_key(config), cache_key(_config()))

    def test_different_ssh_host_produces_different_key(self):
        key_a = cache_key(_config(ssh_host='a.example.test'))
        key_b = cache_key(_config(ssh_host='b.example.test'))
        self.assertNotEqual(key_a, key_b)

    def test_agent_auth_key_is_deterministic(self):
        config = _config(private_key=None, private_key_file=None)
        self.assertEqual(
            cache_key(config),
            cache_key(_config(private_key=None, private_key_file=None)))

    def test_agent_auth_key_varies_with_ssh_host(self):
        key_a = cache_key(_config(
            private_key=None, private_key_file=None,
            ssh_host='a.example.test'))
        key_b = cache_key(_config(
            private_key=None, private_key_file=None,
            ssh_host='b.example.test'))
        self.assertNotEqual(key_a, key_b)


class TestConfigError(AuthTestCase):

    def test_missing_everything_raises_lagoon_config_error(self):
        config = _config(
            token=None, ssh_host=None, private_key=None,
            private_key_file=None)
        with self.assertRaises(LagoonConfigError):
            resolve_token(config)

    def test_both_private_key_and_private_key_file_raises_config_error(self):
        config = _config(
            private_key='key-material', private_key_file='/some/path')
        with self.assertRaises(LagoonConfigError):
            resolve_token(config)

    def test_config_error_not_lagoon_auth_error(self):
        # LagoonConfigError is not a LagoonAuthError -- caller misconfig-
        # uration must not be indistinguishable from an SSH grant failure.
        from .....plugins.module_utils.errors import LagoonAuthError
        config = _config(ssh_host=None, private_key=None,
                          private_key_file=None)
        try:
            resolve_token(config)
            self.fail("expected LagoonConfigError")
        except LagoonAuthError:
            self.fail("must not raise LagoonAuthError for misconfiguration")
        except LagoonConfigError:
            pass


class TestAgentAuth(AuthTestCase):
    """Neither private_key nor private_key_file supplied -> SSH agent
    auth via inherited SSH_AUTH_SOCK (P2-D9)."""

    @patch('%s.request_grant' % _MODULE_PATH)
    def test_neither_key_calls_grant_with_both_none_no_raise(
            self, mock_grant):
        mock_grant.return_value = ('agent-token', 3600)
        config = _config(private_key=None, private_key_file=None)

        token = resolve_token(config)

        self.assertEqual(token, 'agent-token')
        mock_grant.assert_called_once()
        self.assertIsNone(mock_grant.call_args.kwargs['private_key'])
        self.assertIsNone(mock_grant.call_args.kwargs['private_key_file'])

    @patch('%s.request_grant' % _MODULE_PATH)
    def test_both_keys_still_raises_config_error(self, mock_grant):
        config = _config(
            private_key='key-material', private_key_file='/some/path')
        with self.assertRaises(LagoonConfigError):
            resolve_token(config)
        mock_grant.assert_not_called()

    def test_both_keys_error_message_does_not_say_is_required(self):
        # The old wording ("exactly one of ... is required") was wrong
        # for this case -- supplying neither is valid (agent auth), only
        # supplying both is the actual error.
        config = _config(
            private_key='key-material', private_key_file='/some/path')
        try:
            resolve_token(config)
            self.fail("expected LagoonConfigError")
        except LagoonConfigError as e:
            self.assertNotIn('is required', str(e))
            self.assertIn('mutually exclusive', str(e))

    @patch('%s.request_grant' % _MODULE_PATH)
    def test_agent_auth_result_is_cached_and_reused(self, mock_grant):
        mock_grant.return_value = ('agent-token', 3600)
        config = _config(private_key=None, private_key_file=None)

        with patch('%s.token_is_valid' % _MODULE_PATH, return_value=True):
            first = resolve_token(config)
            second = resolve_token(config)

        self.assertEqual(first, 'agent-token')
        self.assertEqual(second, 'agent-token')
        mock_grant.assert_called_once()


class TestTokenValueRedaction(AuthTestCase):

    @patch('%s.request_grant' % _MODULE_PATH)
    def test_token_absent_from_config_error_message(self, mock_grant):
        secret_looking_token = 'secret-shaped-token-value'
        config = _config(
            ssh_host=None, private_key=None, private_key_file=None,
            token=None)
        # Seed the cache with a value that must never leak, even though
        # this particular path raises before consulting it meaningfully.
        auth._cache[cache_key(config)] = secret_looking_token
        try:
            resolve_token(config)
            self.fail("expected LagoonConfigError")
        except LagoonConfigError as e:
            self.assertNotIn(secret_looking_token, str(e))

    @patch('%s.request_grant' % _MODULE_PATH)
    def test_token_absent_from_missing_key_config_error(self, mock_grant):
        secret_key = 'secret-private-key-material'
        config = _config(private_key=secret_key)
        # Force the "exactly one of" branch by also setting a file path.
        config['private_key_file'] = '/some/path'
        try:
            resolve_token(config)
            self.fail("expected LagoonConfigError")
        except LagoonConfigError as e:
            self.assertNotIn(secret_key, str(e))


class TestAuthArgumentSpec(AuthTestCase):

    def test_secret_bearing_options_marked_no_log(self):
        spec = auth_argument_spec()
        self.assertTrue(spec['lagoon_api_token']['no_log'])
        self.assertTrue(spec['lagoon_ssh_private_key']['no_log'])

    def test_validate_certs_defaults_true(self):
        spec = auth_argument_spec()
        self.assertTrue(spec['validate_certs']['default'])

    def test_caller_supplied_spec_overrides_on_conflict(self):
        spec = auth_argument_spec({'validate_certs': {'type': 'bool',
                                                        'default': False}})
        self.assertFalse(spec['validate_certs']['default'])

    def test_caller_supplied_spec_extends_with_new_keys(self):
        spec = auth_argument_spec({'extra_option': {'type': 'str'}})
        self.assertIn('extra_option', spec)
        self.assertIn('lagoon_api_token', spec)

    def test_private_key_file_and_known_hosts_file_are_path_type(self):
        spec = auth_argument_spec()
        self.assertEqual(
            spec['lagoon_ssh_private_key_file']['type'], 'path')
        self.assertEqual(
            spec['lagoon_ssh_known_hosts_file']['type'], 'path')

    def test_private_key_file_and_known_hosts_file_not_no_log(self):
        # Paths, not key material -- redacting them would hurt
        # debuggability without protecting a secret.
        spec = auth_argument_spec()
        self.assertNotIn('no_log', spec['lagoon_ssh_private_key_file'])
        self.assertNotIn('no_log', spec['lagoon_ssh_known_hosts_file'])

    def test_batch_mode_defaults_true(self):
        spec = auth_argument_spec()
        self.assertTrue(spec['lagoon_ssh_batch_mode']['default'])


class TestBatchModeThreading(AuthTestCase):

    @patch('%s.request_grant' % _MODULE_PATH)
    def test_batch_mode_default_true_passed_to_request_grant(
            self, mock_grant):
        mock_grant.return_value = ('tok', 3600)
        resolve_token(_config())
        self.assertTrue(mock_grant.call_args.kwargs['batch_mode'])

    @patch('%s.request_grant' % _MODULE_PATH)
    def test_batch_mode_false_passed_through(self, mock_grant):
        mock_grant.return_value = ('tok', 3600)
        resolve_token(_config(batch_mode=False))
        self.assertFalse(mock_grant.call_args.kwargs['batch_mode'])


class TestNoForbiddenImports(unittest.TestCase):

    def test_forbidden_imports_absent(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..',
            'plugins', 'module_utils', 'auth.py')
        path = os.path.normpath(path)
        tree = ast.parse(open(path).read())
        bad = [n.module for n in ast.walk(tree)
               if isinstance(n, ast.ImportFrom) and n.module and
               (n.module.split('.')[0] in ('gql', 'graphql', 'requests') or
                n.module == 'ansible.errors')]
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
