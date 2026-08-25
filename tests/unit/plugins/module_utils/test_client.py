from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json
import socket
import ssl
import unittest
from unittest.mock import MagicMock, patch

from ansible.module_utils.six.moves.urllib.error import HTTPError, URLError
from ansible.module_utils.urls import (
    ConnectionError as AnsibleURLConnectionError,
    SSLValidationError,
)

from .....plugins.module_utils.client import LagoonClient
from .....plugins.module_utils.errors import (
    LagoonAPIError,
    LagoonAuthError,
    LagoonConfigError,
    LagoonTransportError,
)


def _http_response(status, body):
    response = MagicMock()
    response.getcode.return_value = status
    response.read.return_value = body
    return response


def _http_error(code, body=b''):
    e = HTTPError('https://example.test/graphql', code, 'error', {}, None)
    e.read = MagicMock(return_value=body)
    return e


class TestBuildQuery(unittest.TestCase):

    def test_query_with_args(self):
        q = LagoonClient.build_query(
            'projectByName', fields=['id', 'name', 'gitUrl'],
            args={'name': 'String!'})
        self.assertEqual(
            q,
            "query projectByName($name: String!) { "
            "projectByName(name: $name) { id name gitUrl } }")

    def test_mutation_with_args(self):
        q = LagoonClient.build_query(
            'deployEnvironmentBranch',
            fields=[],
            args={'project': 'String!', 'branch': 'String!'},
            operation_type='mutation')
        # Arg order is deterministic (sorted), not insertion order.
        self.assertEqual(
            q,
            "mutation deployEnvironmentBranch($branch: String!, "
            "$project: String!) { deployEnvironmentBranch(branch: "
            "$branch, project: $project) }")

    def test_query_without_args(self):
        q = LagoonClient.build_query('me', fields=['id', 'email'])
        self.assertEqual(q, "query me { me { id email } }")

    def test_fields_empty_scalar_return(self):
        q = LagoonClient.build_query(
            'deleteProject', fields=[], args={'input': 'DeleteProjectInput!'},
            operation_type='mutation')
        self.assertEqual(
            q,
            "mutation deleteProject($input: DeleteProjectInput!) { "
            "deleteProject(input: $input) }")

    def test_explicit_operation_name(self):
        q = LagoonClient.build_query(
            'projectByName', fields=['id'], args={'name': 'String!'},
            operation_name='getProject')
        self.assertEqual(
            q,
            "query getProject($name: String!) { "
            "projectByName(name: $name) { id } }")

    def test_rejects_field_with_brace(self):
        with self.assertRaises(LagoonConfigError):
            LagoonClient.build_query('me', fields=['id { nested }'])

    def test_rejects_field_with_space(self):
        with self.assertRaises(LagoonConfigError):
            LagoonClient.build_query('me', fields=['id name'])

    def test_rejects_field_with_paren(self):
        with self.assertRaises(LagoonConfigError):
            LagoonClient.build_query('me', fields=['id(foo: 1)'])

    def test_rejects_bad_operation_name(self):
        with self.assertRaises(LagoonConfigError):
            LagoonClient.build_query('bad-name!', fields=['id'])

    def test_rejects_bad_arg_name(self):
        with self.assertRaises(LagoonConfigError):
            LagoonClient.build_query(
                'me', fields=['id'], args={'bad-arg!': 'String!'})

    def test_rejects_bad_operation_type(self):
        with self.assertRaises(LagoonConfigError):
            LagoonClient.build_query(
                'me', fields=['id'], operation_type='subscription')

    def test_deterministic(self):
        q1 = LagoonClient.build_query(
            'projectByName', fields=['id', 'name'],
            args={'name': 'String!', 'group': 'String'})
        q2 = LagoonClient.build_query(
            'projectByName', fields=['id', 'name'],
            args={'name': 'String!', 'group': 'String'})
        self.assertEqual(q1, q2)


class TestConstructor(unittest.TestCase):

    def test_missing_endpoint(self):
        with self.assertRaises(LagoonConfigError):
            LagoonClient('', 'token')

    def test_missing_token(self):
        with self.assertRaises(LagoonConfigError):
            LagoonClient('https://example.test/graphql', '')

    def test_headers_not_dict(self):
        with self.assertRaises(LagoonConfigError):
            LagoonClient('https://example.test/graphql', 'tok',
                         headers='not-a-dict')

    def test_validate_certs_defaults_true(self):
        c = LagoonClient('https://example.test/graphql', 'tok')
        self.assertTrue(c.validate_certs)


class TestReprRedaction(unittest.TestCase):

    def test_token_not_in_repr(self):
        c = LagoonClient('https://example.test/graphql', 'super-secret-token')
        self.assertNotIn('super-secret-token', repr(c))


class TestOpenUrlTransport(unittest.TestCase):
    """Exercise execute() via the open_url transport (module=None)."""

    def _client(self, **kwargs):
        kwargs.setdefault('retries', 0)
        return LagoonClient('https://example.test/graphql', 'tok', **kwargs)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_happy_path(self, mock_open_url):
        mock_open_url.return_value = _http_response(
            200, json.dumps({'data': {'me': {'id': 1}}}).encode())
        c = self._client()
        data = c.execute('query { me { id } }')
        self.assertEqual(data, {'me': {'id': 1}})

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_open_url_called_when_no_module(self, mock_open_url):
        mock_open_url.return_value = _http_response(
            200, json.dumps({'data': {}}).encode())
        c = self._client()
        c.execute('query { me }')
        self.assertTrue(mock_open_url.called)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_validate_certs_passed_through(self, mock_open_url):
        mock_open_url.return_value = _http_response(
            200, json.dumps({'data': {}}).encode())
        c = self._client(validate_certs=False)
        c.execute('query { me }')
        self.assertEqual(
            mock_open_url.call_args.kwargs['validate_certs'], False)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_401_raises_auth_error(self, mock_open_url):
        mock_open_url.side_effect = _http_error(401)
        c = self._client()
        with self.assertRaises(LagoonAuthError):
            c.execute('query { me }')

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_403_raises_auth_error(self, mock_open_url):
        mock_open_url.side_effect = _http_error(403)
        c = self._client()
        with self.assertRaises(LagoonAuthError):
            c.execute('query { me }')

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_400_raises_api_error_no_retry(self, mock_open_url):
        mock_open_url.side_effect = _http_error(400)
        c = self._client(retries=3)
        with self.assertRaises(LagoonAPIError):
            c.execute('query { me }')
        self.assertEqual(mock_open_url.call_count, 1)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_404_raises_api_error(self, mock_open_url):
        mock_open_url.side_effect = _http_error(404)
        c = self._client()
        with self.assertRaises(LagoonAPIError):
            c.execute('query { me }')

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_409_raises_api_error(self, mock_open_url):
        mock_open_url.side_effect = _http_error(409)
        c = self._client()
        with self.assertRaises(LagoonAPIError):
            c.execute('query { me }')

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_422_raises_api_error(self, mock_open_url):
        mock_open_url.side_effect = _http_error(422)
        c = self._client()
        with self.assertRaises(LagoonAPIError):
            c.execute('query { me }')

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_non_json_200_body_raises_api_error(self, mock_open_url):
        mock_open_url.return_value = _http_response(200, b'not json at all')
        c = self._client()
        with self.assertRaises(LagoonAPIError):
            c.execute('query { me }')

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_200_with_errors_raises_api_error_with_payload(self, mock_open_url):
        payload = {'errors': [{'message': 'bad thing', 'path': ['me']}]}
        mock_open_url.return_value = _http_response(
            200, json.dumps(payload).encode())
        c = self._client()
        with self.assertRaises(LagoonAPIError) as ctx:
            c.execute('query { me }')
        self.assertEqual(ctx.exception.errors, payload['errors'])

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_200_with_data_and_errors_raises(self, mock_open_url):
        payload = {
            'data': {'me': None},
            'errors': [{'message': 'partial failure'}],
        }
        mock_open_url.return_value = _http_response(
            200, json.dumps(payload).encode())
        c = self._client()
        with self.assertRaises(LagoonAPIError):
            c.execute('query { me }')

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_200_with_neither_data_nor_errors_raises(self, mock_open_url):
        mock_open_url.return_value = _http_response(
            200, json.dumps({'something': 'else'}).encode())
        c = self._client()
        with self.assertRaises(LagoonAPIError):
            c.execute('query { me }')

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.time.sleep', return_value=None)
    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_5xx_then_5xx_then_200_retries_and_succeeds(self, mock_open_url,
                                                          mock_sleep):
        mock_open_url.side_effect = [
            _http_response(200, b''),  # placeholder, overwritten below
        ]
        # Simulate: first two calls return 500 (as an HTTPError raise),
        # third succeeds.
        mock_open_url.side_effect = [
            _http_error(500),
            _http_error(500),
            _http_response(200, json.dumps({'data': {'ok': True}}).encode()),
        ]
        c = self._client(retries=3)
        data = c.execute('query { me }')
        self.assertEqual(data, {'ok': True})
        self.assertEqual(mock_open_url.call_count, 3)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.time.sleep', return_value=None)
    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_5xx_always_raises_transport_error_after_retries(
            self, mock_open_url, mock_sleep):
        mock_open_url.side_effect = _http_error(500)
        c = self._client(retries=3)
        with self.assertRaises(LagoonTransportError):
            c.execute('query { me }')
        self.assertEqual(mock_open_url.call_count, 4)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.time.sleep', return_value=None)
    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_retries_zero_means_one_attempt(self, mock_open_url, mock_sleep):
        mock_open_url.side_effect = _http_error(500)
        c = self._client(retries=0)
        with self.assertRaises(LagoonTransportError):
            c.execute('query { me }')
        self.assertEqual(mock_open_url.call_count, 1)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.time.sleep', return_value=None)
    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_urlerror_retries_then_raises_transport_error(
            self, mock_open_url, mock_sleep):
        mock_open_url.side_effect = URLError('connection refused')
        c = self._client(retries=2)
        with self.assertRaises(LagoonTransportError):
            c.execute('query { me }')
        self.assertEqual(mock_open_url.call_count, 3)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.time.sleep', return_value=None)
    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_connection_error_retries_then_raises_transport_error(
            self, mock_open_url, mock_sleep):
        mock_open_url.side_effect = AnsibleURLConnectionError('failed to connect')
        c = self._client(retries=2)
        with self.assertRaises(LagoonTransportError):
            c.execute('query { me }')
        self.assertEqual(mock_open_url.call_count, 3)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.time.sleep', return_value=None)
    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_socket_timeout_retries_then_raises_transport_error(
            self, mock_open_url, mock_sleep):
        mock_open_url.side_effect = socket.timeout('timed out')
        c = self._client(retries=2)
        with self.assertRaises(LagoonTransportError):
            c.execute('query { me }')
        self.assertEqual(mock_open_url.call_count, 3)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.time.sleep', return_value=None)
    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_ssl_validation_error_no_retry(self, mock_open_url, mock_sleep):
        mock_open_url.side_effect = SSLValidationError('cert invalid')
        c = self._client(retries=3)
        with self.assertRaises(LagoonTransportError):
            c.execute('query { me }')
        self.assertEqual(mock_open_url.call_count, 1)
        self.assertFalse(mock_sleep.called)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.time.sleep', return_value=None)
    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_urlerror_wrapping_ssl_error_no_retry(self, mock_open_url,
                                                    mock_sleep):
        err = URLError(ssl.SSLError('cert problem'))
        mock_open_url.side_effect = err
        c = self._client(retries=3)
        with self.assertRaises(LagoonTransportError):
            c.execute('query { me }')
        self.assertEqual(mock_open_url.call_count, 1)
        self.assertFalse(mock_sleep.called)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_caller_headers_cannot_override_authorization(self, mock_open_url):
        mock_open_url.return_value = _http_response(
            200, json.dumps({'data': {}}).encode())
        c = self._client(headers={'Authorization': 'Bearer evil-token'})
        c.execute('query { me }')
        sent_headers = mock_open_url.call_args.kwargs['headers']
        self.assertEqual(sent_headers['Authorization'], 'Bearer tok')

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_variables_in_body_not_in_query_string(self, mock_open_url):
        captured = {}

        def _capture(*args, **kwargs):
            captured['data'] = kwargs.get('data')
            return _http_response(200, json.dumps({'data': {}}).encode())

        mock_open_url.side_effect = _capture
        c = self._client()
        c.execute('query projectByName($name: String!) { projectByName(name: $name) { id } }',
                  variables={'name': 'secret-project-name'})
        body = json.loads(captured['data'])
        self.assertEqual(body['variables'], {'name': 'secret-project-name'})
        self.assertNotIn('secret-project-name', body['query'])

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_token_never_in_exception_str_auth_error(self, mock_open_url):
        secret_token = 'the-actual-secret-token-value'
        mock_open_url.side_effect = _http_error(401)
        c = LagoonClient('https://example.test/graphql', secret_token,
                         retries=0)
        with self.assertRaises(LagoonAuthError) as ctx:
            c.execute('query { me }')
        self.assertNotIn(secret_token, str(ctx.exception))
        self.assertNotIn(secret_token, repr(c))

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_token_never_in_exception_str_api_error(self, mock_open_url):
        secret_token = 'the-actual-secret-token-value'
        mock_open_url.side_effect = _http_error(404)
        c = LagoonClient('https://example.test/graphql', secret_token,
                         retries=0)
        with self.assertRaises(LagoonAPIError) as ctx:
            c.execute('query { me }')
        self.assertNotIn(secret_token, str(ctx.exception))
        self.assertNotIn(secret_token, repr(c))

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.time.sleep', return_value=None)
    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_token_never_in_exception_str_transport_error(
            self, mock_open_url, mock_sleep):
        secret_token = 'the-actual-secret-token-value'
        mock_open_url.side_effect = URLError('connection refused')
        c = LagoonClient('https://example.test/graphql', secret_token,
                         retries=0)
        with self.assertRaises(LagoonTransportError) as ctx:
            c.execute('query { me }')
        self.assertNotIn(secret_token, str(ctx.exception))
        self.assertNotIn(secret_token, repr(c))

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_token_never_in_exception_str_ssl_error(self, mock_open_url):
        secret_token = 'the-actual-secret-token-value'
        mock_open_url.side_effect = SSLValidationError('cert invalid')
        c = LagoonClient('https://example.test/graphql', secret_token,
                         retries=0)
        with self.assertRaises(LagoonTransportError) as ctx:
            c.execute('query { me }')
        self.assertNotIn(secret_token, str(ctx.exception))
        self.assertNotIn(secret_token, repr(c))

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    def test_token_never_in_config_error(self, mock_open_url):
        secret_token = 'the-actual-secret-token-value'
        with self.assertRaises(LagoonConfigError) as ctx:
            LagoonClient('https://example.test/graphql', secret_token,
                        headers='not-a-dict')
        self.assertNotIn(secret_token, str(ctx.exception))


class TestFetchUrlTransport(unittest.TestCase):
    """Exercise execute() via the fetch_url transport (module given)."""

    def _module(self):
        module = MagicMock()
        module.params = {}
        return module

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.fetch_url')
    def test_fetch_url_called_when_module_given(self, mock_fetch_url):
        mock_fetch_url.return_value = (
            _http_response(200, json.dumps({'data': {}}).encode()),
            {'status': 200})
        module = self._module()
        c = LagoonClient('https://example.test/graphql', 'tok',
                         module=module, retries=0)
        c.execute('query { me }')
        self.assertTrue(mock_fetch_url.called)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.open_url')
    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.fetch_url')
    def test_open_url_not_called_when_module_given(self, mock_fetch_url,
                                                      mock_open_url):
        mock_fetch_url.return_value = (
            _http_response(200, json.dumps({'data': {}}).encode()),
            {'status': 200})
        module = self._module()
        c = LagoonClient('https://example.test/graphql', 'tok',
                         module=module, retries=0)
        c.execute('query { me }')
        self.assertFalse(mock_open_url.called)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.fetch_url')
    def test_validate_certs_passed_through_module_params(self, mock_fetch_url):
        mock_fetch_url.return_value = (
            _http_response(200, json.dumps({'data': {}}).encode()),
            {'status': 200})
        module = self._module()
        c = LagoonClient('https://example.test/graphql', 'tok',
                         module=module, validate_certs=False, retries=0)
        c.execute('query { me }')
        self.assertEqual(module.params.get('validate_certs'), False)

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.fetch_url')
    def test_happy_path(self, mock_fetch_url):
        mock_fetch_url.return_value = (
            _http_response(200, json.dumps({'data': {'me': {'id': 1}}}).encode()),
            {'status': 200})
        module = self._module()
        c = LagoonClient('https://example.test/graphql', 'tok',
                         module=module, retries=0)
        data = c.execute('query { me { id } }')
        self.assertEqual(data, {'me': {'id': 1}})

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.fetch_url')
    def test_401_raises_auth_error(self, mock_fetch_url):
        mock_fetch_url.return_value = (None, {
            'status': 401, 'msg': 'HTTP Error 401: Unauthorized', 'body': b''})
        module = self._module()
        c = LagoonClient('https://example.test/graphql', 'tok',
                         module=module, retries=0)
        with self.assertRaises(LagoonAuthError):
            c.execute('query { me }')

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.fetch_url')
    def test_connection_failure_no_response_raises_transport_error(
            self, mock_fetch_url):
        mock_fetch_url.return_value = (
            None, {'status': -1, 'msg': 'Request failed: connection refused'})
        module = self._module()
        c = LagoonClient('https://example.test/graphql', 'tok',
                         module=module, retries=0)
        with self.assertRaises(LagoonTransportError):
            c.execute('query { me }')

    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.time.sleep', return_value=None)
    @patch('ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client.fetch_url')
    def test_ssl_failure_no_response_no_retry(self, mock_fetch_url, mock_sleep):
        mock_fetch_url.return_value = (
            None, {'status': -1,
                   'msg': "Request failed: <urlopen error [SSL: "
                          "CERTIFICATE_VERIFY_FAILED] certificate verify "
                          "failed>"})
        module = self._module()
        c = LagoonClient('https://example.test/graphql', 'tok',
                         module=module, retries=3)
        with self.assertRaises(LagoonTransportError):
            c.execute('query { me }')
        self.assertEqual(mock_fetch_url.call_count, 1)
        self.assertFalse(mock_sleep.called)


if __name__ == '__main__':
    unittest.main()