"""Unit tests for whoami_info -- the auth walking skeleton.

These tests construct the module's own logic directly, with no action
shim involved at all: an explicit ``lagoon_api_token`` is set on the
(mocked) ``AnsibleModule`` params, exactly as a caller invoking the module
standalone would do. This is the concrete proof of the plugins/action/
boundary (AGENTS.md, "Architectural boundaries") -- a module invoked with
an explicit token and no action plugin must be fully functional on its
own.

``LagoonClient.execute`` is mocked at the transport boundary -- these
tests exercise ``whoami_info``'s own logic (query construction, response
handling, error translation), not the HTTP/GraphQL transport, which
module_utils/test_client.py already covers.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import unittest
from unittest.mock import MagicMock, patch

from ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils \
    .errors import LagoonNotFoundError
from ansible_collections.salsadigitalauorg.lagoon.plugins.modules \
    .whoami_info import run_module

_MODULE_PATH = (
    'ansible_collections.salsadigitalauorg.lagoon.plugins.modules'
    '.whoami_info')

_USER_FIELDS = {
    'id': '1',
    'email': 'user@example.test',
    'firstName': 'Ada',
    'lastName': 'Lovelace',
    'created': '2020-01-01 00:00:00',
    'lastAccessed': '2020-01-02 00:00:00',
    'has2faEnabled': True,
}


def _make_module(**param_overrides):
    """A minimal stand-in for AnsibleModule -- exposes only the surface
    run_module() actually reads (``.params``), so this proves the
    module's logic depends on nothing else from AnsibleModule itself.
    """
    module = MagicMock()
    module.params = dict(
        lagoon_api_token='explicit-token',
        lagoon_api_endpoint='https://api.lagoon.example.test/graphql',
        validate_certs=True,
        check_mode=False,
    )
    module.params.update(param_overrides)
    module.check_mode = module.params.get('check_mode', False)
    return module


class TestRunModuleHappyPath(unittest.TestCase):

    @patch('%s.LagoonClient.execute' % _MODULE_PATH)
    def test_returns_expected_user_dict(self, mock_execute):
        mock_execute.return_value = {'me': dict(_USER_FIELDS)}
        module = _make_module()

        user = run_module(module)

        self.assertEqual(user, _USER_FIELDS)

    @patch('%s.LagoonClient.execute' % _MODULE_PATH)
    def test_no_action_shim_involved(self, mock_execute):
        """The whole point of this test module: run_module() is called
        directly against a module carrying an explicit token, with the
        action shim never constructed, imported, or referenced anywhere
        in this test.
        """
        mock_execute.return_value = {'me': dict(_USER_FIELDS)}
        module = _make_module(lagoon_api_token='explicit-token')

        user = run_module(module)

        self.assertEqual(user['email'], 'user@example.test')

    @patch('%s.LagoonClient.execute' % _MODULE_PATH)
    def test_query_uses_build_query_for_me(self, mock_execute):
        mock_execute.return_value = {'me': dict(_USER_FIELDS)}
        module = _make_module()

        run_module(module)

        document = mock_execute.call_args.args[0]
        self.assertIn('me { me {', document)
        for field in ('id', 'email', 'firstName', 'lastName', 'created',
                      'lastAccessed', 'has2faEnabled'):
            self.assertIn(field, document)
        # Deliberately dropped -- see RETURN docs and the module
        # docstring: a nested groups { name type } selection is
        # forbidden under the flat-query rule.
        self.assertNotIn('groups', document)


class TestRunModuleNotFound(unittest.TestCase):

    @patch('%s.LagoonClient.execute' % _MODULE_PATH)
    def test_me_null_raises_not_found_error(self, mock_execute):
        mock_execute.return_value = {'me': None}
        module = _make_module()

        with self.assertRaises(LagoonNotFoundError):
            run_module(module)

    @patch('%s.LagoonClient.execute' % _MODULE_PATH)
    def test_not_found_error_names_the_resource_and_query(
            self, mock_execute):
        mock_execute.return_value = {'me': None}
        module = _make_module()

        with self.assertRaises(LagoonNotFoundError) as ctx:
            run_module(module)

        self.assertEqual(ctx.exception.resource, 'user')
        self.assertEqual(ctx.exception.query, 'me')


class TestRunModuleCheckMode(unittest.TestCase):

    @patch('%s.LagoonClient.execute' % _MODULE_PATH)
    def test_check_mode_still_executes_the_read(self, mock_execute):
        """whoami_info is read-only -- there is nothing check mode could
        meaningfully skip, so it must still perform (and return) the
        same read.
        """
        mock_execute.return_value = {'me': dict(_USER_FIELDS)}
        module = _make_module(check_mode=True)

        user = run_module(module)

        self.assertEqual(user, _USER_FIELDS)
        self.assertTrue(mock_execute.called)


class TestRunModuleClientConstruction(unittest.TestCase):

    @patch('%s.LagoonClient' % _MODULE_PATH)
    def test_client_constructed_from_module_params(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.execute.return_value = {'me': dict(_USER_FIELDS)}
        module = _make_module(
            lagoon_api_token='tok-123',
            lagoon_api_endpoint='https://endpoint.example.test/graphql',
            validate_certs=False)

        run_module(module)

        call_kwargs = mock_client_cls.call_args.kwargs
        self.assertEqual(call_kwargs['token'], 'tok-123')
        self.assertEqual(
            call_kwargs['endpoint'], 'https://endpoint.example.test/graphql')
        self.assertEqual(call_kwargs['validate_certs'], False)
        self.assertIs(call_kwargs['module'], module)


if __name__ == '__main__':
    unittest.main()
