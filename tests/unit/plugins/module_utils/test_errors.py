from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import ast
import os
import pickle
import unittest

from .....plugins.module_utils.errors import (
    LagoonAmbiguousResultError,
    LagoonAPIError,
    LagoonAuthError,
    LagoonConfigError,
    LagoonError,
    LagoonNotFoundError,
    LagoonTransportError,
)


class TestTaxonomy(unittest.TestCase):

    def test_all_classes_inherit_from_lagoon_error(self):
        for cls in (LagoonConfigError, LagoonAuthError, LagoonTransportError,
                    LagoonAPIError, LagoonNotFoundError,
                    LagoonAmbiguousResultError):
            self.assertTrue(issubclass(cls, LagoonError))

        self.assertTrue(issubclass(LagoonError, Exception))

    def test_no_ansible_imports(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..',
            'plugins', 'module_utils', 'errors.py')
        path = os.path.normpath(path)
        tree = ast.parse(open(path).read())
        bad = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                bad += [a.name for a in n.names
                        if a.name.split('.')[0] in
                        ('ansible', 'gql', 'graphql', 'requests')]
            if isinstance(n, ast.ImportFrom) and n.module:
                if n.module.split('.')[0] in \
                        ('ansible', 'gql', 'graphql', 'requests'):
                    bad.append(n.module)
        self.assertEqual(bad, [])


class TestLagoonAPIErrorMessages(unittest.TestCase):

    def test_well_formed_payload(self):
        e = LagoonAPIError([{'message': 'a'}, {'message': 'b'}])
        self.assertEqual(e.messages, ['a', 'b'])

    def test_list_of_bare_strings(self):
        e = LagoonAPIError(['plain string error'])
        self.assertEqual(e.messages, ['plain string error'])

    def test_dict_missing_message_key(self):
        e = LagoonAPIError([{'path': ['x']}])
        self.assertEqual(e.messages, [])

    def test_none_entry_in_list(self):
        e = LagoonAPIError([None, {'message': 'ok'}])
        self.assertEqual(e.messages, ['ok'])

    def test_empty_list(self):
        e = LagoonAPIError([])
        self.assertEqual(e.messages, [])

    def test_errors_none(self):
        e = LagoonAPIError(None)
        self.assertEqual(e.errors, [])
        self.assertEqual(e.messages, [])

    def test_never_raises(self):
        # A grab-bag of malformed entries in one payload; none of this
        # should raise when accessing .messages.
        e = LagoonAPIError([
            {'message': 'ok'},
            None,
            'bare string',
            {'path': ['x']},
            42,
        ])
        self.assertEqual(e.messages, ['ok', 'bare string', '42'])


class TestLagoonAPIErrorStr(unittest.TestCase):

    def test_single_message(self):
        e = LagoonAPIError([{'message': 'auth failed'}])
        self.assertEqual(str(e), "Lagoon API error: auth failed")

    def test_multiple_messages(self):
        e = LagoonAPIError([{'message': 'a'}, {'message': 'b'}])
        self.assertEqual(str(e), "Lagoon API errors (2): a; b")

    def test_no_messages(self):
        e = LagoonAPIError([])
        self.assertEqual(str(e), "Lagoon API error: unknown error")

    def test_variables_not_in_str(self):
        secret = 'SUPER_SECRET_TOKEN_XYZ'
        e = LagoonAPIError([{'message': 'auth failed'}],
                            variables={'token': secret})
        self.assertNotIn(secret, str(e))

    def test_variables_not_in_repr(self):
        secret = 'SUPER_SECRET_TOKEN_XYZ'
        e = LagoonAPIError([{'message': 'auth failed'}],
                            variables={'token': secret})
        self.assertNotIn(secret, repr(e))

    def test_variables_kept_as_attribute(self):
        variables = {'token': 'abc123'}
        e = LagoonAPIError([{'message': 'auth failed'}], variables=variables)
        self.assertEqual(e.variables, variables)

    def test_query_kept_as_attribute(self):
        e = LagoonAPIError([{'message': 'auth failed'}], query='query { me }')
        self.assertEqual(e.query, 'query { me }')

    def test_explicit_message_overrides_summary(self):
        e = LagoonAPIError([{'message': 'x'}], message='custom message')
        self.assertEqual(str(e), 'custom message')


class TestLagoonNotFoundError(unittest.TestCase):

    def test_message_includes_query_and_value(self):
        e = LagoonNotFoundError('project', query='projectByName',
                                 arg='name', value='my-project')
        self.assertIn('projectByName', str(e))
        self.assertIn('my-project', str(e))
        self.assertIn('project', str(e))

    def test_attributes_set(self):
        e = LagoonNotFoundError('project', query='projectByName',
                                 arg='name', value='my-project')
        self.assertEqual(e.resource, 'project')
        self.assertEqual(e.query, 'projectByName')
        self.assertEqual(e.arg, 'name')
        self.assertEqual(e.value, 'my-project')

    def test_message_without_query(self):
        e = LagoonNotFoundError('project')
        self.assertIn('project', str(e))
        self.assertIn('not found', str(e))

    def test_explicit_message_overrides_summary(self):
        e = LagoonNotFoundError('project', message='custom')
        self.assertEqual(str(e), 'custom')


class TestLagoonAmbiguousResultError(unittest.TestCase):

    def test_message_includes_query_and_value(self):
        e = LagoonAmbiguousResultError('project', query='projectByName',
                                        arg='name', value='my-project',
                                        count=3)
        self.assertIn('projectByName', str(e))
        self.assertIn('my-project', str(e))
        self.assertIn('project', str(e))

    def test_attributes_set(self):
        e = LagoonAmbiguousResultError('project', query='projectByName',
                                        arg='name', value='my-project',
                                        count=3)
        self.assertEqual(e.resource, 'project')
        self.assertEqual(e.query, 'projectByName')
        self.assertEqual(e.arg, 'name')
        self.assertEqual(e.value, 'my-project')
        self.assertEqual(e.count, 3)

    def test_explicit_message_overrides_summary(self):
        e = LagoonAmbiguousResultError('project', message='custom')
        self.assertEqual(str(e), 'custom')


class TestPickling(unittest.TestCase):

    def _assert_roundtrip(self, exc):
        restored = pickle.loads(pickle.dumps(exc))
        self.assertIs(type(restored), type(exc))
        self.assertEqual(str(restored), str(exc))
        return restored

    def test_lagoon_error(self):
        self._assert_roundtrip(LagoonError('boom'))

    def test_lagoon_config_error(self):
        self._assert_roundtrip(LagoonConfigError('boom'))

    def test_lagoon_auth_error(self):
        self._assert_roundtrip(LagoonAuthError('boom'))

    def test_lagoon_transport_error(self):
        self._assert_roundtrip(LagoonTransportError('boom'))

    def test_lagoon_api_error(self):
        exc = LagoonAPIError([{'message': 'a'}, {'message': 'b'}],
                              query='query { me }',
                              variables={'x': 'y'})
        restored = self._assert_roundtrip(exc)
        self.assertEqual(restored.errors, exc.errors)
        self.assertEqual(restored.query, exc.query)
        self.assertEqual(restored.variables, exc.variables)

    def test_lagoon_not_found_error(self):
        exc = LagoonNotFoundError('project', query='projectByName',
                                   arg='name', value='my-project')
        restored = self._assert_roundtrip(exc)
        self.assertEqual(restored.resource, exc.resource)
        self.assertEqual(restored.query, exc.query)
        self.assertEqual(restored.arg, exc.arg)
        self.assertEqual(restored.value, exc.value)

    def test_lagoon_ambiguous_result_error(self):
        exc = LagoonAmbiguousResultError('project', query='projectByName',
                                          arg='name', value='my-project',
                                          count=3)
        restored = self._assert_roundtrip(exc)
        self.assertEqual(restored.resource, exc.resource)
        self.assertEqual(restored.query, exc.query)
        self.assertEqual(restored.arg, exc.arg)
        self.assertEqual(restored.value, exc.value)
        self.assertEqual(restored.count, exc.count)


if __name__ == '__main__':
    unittest.main()