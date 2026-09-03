from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import ast
import os
import unittest
from unittest.mock import MagicMock

from .....plugins.module_utils.errors import (
    LagoonAmbiguousResultError,
    LagoonConfigError,
    LagoonNotFoundError,
)
from .....plugins.module_utils.lookup import invalidate_lookup, resolve_lookup

_PROJECT_LOOKUP = {'query': 'projectByName', 'arg': 'name', 'returns': 'id'}
_ENV_LOOKUP = {
    'query': 'environmentByKubernetesNamespaceName',
    'arg': 'kubernetesNamespaceName',
    'returns': 'id',
}


def _client(data=None):
    client = MagicMock()
    client.execute = MagicMock(return_value=data or {})
    return client


class TestCacheHit(unittest.TestCase):

    def test_two_calls_same_key_execute_once(self):
        client = _client({'projectByName': {'id': 42}})
        cache = {}
        first = resolve_lookup(client, _PROJECT_LOOKUP, 'my-project',
                                cache=cache)
        second = resolve_lookup(client, _PROJECT_LOOKUP, 'my-project',
                                 cache=cache)
        self.assertEqual(first, 42)
        self.assertEqual(second, 42)
        client.execute.assert_called_once()

    def test_no_cache_dict_never_caches(self):
        client = _client({'projectByName': {'id': 42}})
        resolve_lookup(client, _PROJECT_LOOKUP, 'my-project', cache=None)
        resolve_lookup(client, _PROJECT_LOOKUP, 'my-project', cache=None)
        self.assertEqual(client.execute.call_count, 2)


class TestCacheMiss(unittest.TestCase):

    def test_different_value_calls_twice(self):
        client = _client({'projectByName': {'id': 42}})
        cache = {}
        resolve_lookup(client, _PROJECT_LOOKUP, 'project-a', cache=cache)
        resolve_lookup(client, _PROJECT_LOOKUP, 'project-b', cache=cache)
        self.assertEqual(client.execute.call_count, 2)

    def test_different_query_same_value_calls_twice(self):
        client = _client({
            'projectByName': {'id': 1},
            'environmentByKubernetesNamespaceName': {'id': 2},
        })
        cache = {}
        resolve_lookup(client, _PROJECT_LOOKUP, 'same-value', cache=cache)
        resolve_lookup(client, _ENV_LOOKUP, 'same-value', cache=cache)
        self.assertEqual(client.execute.call_count, 2)

    def test_different_arg_same_query_and_value_calls_twice(self):
        lookup_a = {'query': 'q', 'arg': 'a', 'returns': 'id'}
        lookup_b = {'query': 'q', 'arg': 'b', 'returns': 'id'}
        client = _client({'q': {'id': 1}})
        cache = {}
        resolve_lookup(client, lookup_a, 'same-value', cache=cache)
        resolve_lookup(client, lookup_b, 'same-value', cache=cache)
        self.assertEqual(client.execute.call_count, 2)


class TestCacheKeysOnValueNotJustLookupName(unittest.TestCase):

    def test_second_project_never_resolves_to_first_id(self):
        client = MagicMock()
        client.execute = MagicMock(side_effect=[
            {'projectByName': {'id': 1}},
            {'projectByName': {'id': 2}},
        ])
        cache = {}
        first = resolve_lookup(client, _PROJECT_LOOKUP, 'project-a',
                                cache=cache)
        second = resolve_lookup(client, _PROJECT_LOOKUP, 'project-b',
                                 cache=cache)
        self.assertEqual(first, 1)
        self.assertEqual(second, 2)
        self.assertNotEqual(first, second)


class TestNotFound(unittest.TestCase):

    def test_null_result_raises_not_found(self):
        client = _client({'projectByName': None})
        with self.assertRaises(LagoonNotFoundError) as ctx:
            resolve_lookup(client, _PROJECT_LOOKUP, 'missing-project')
        self.assertEqual(ctx.exception.resource, 'projectByName')
        self.assertEqual(ctx.exception.query, 'projectByName')
        self.assertEqual(ctx.exception.arg, 'name')
        self.assertEqual(ctx.exception.value, 'missing-project')

    def test_resource_override_used_in_error(self):
        lookup_config = dict(_PROJECT_LOOKUP, resource='project')
        client = _client({'projectByName': None})
        with self.assertRaises(LagoonNotFoundError) as ctx:
            resolve_lookup(client, lookup_config, 'missing-project')
        self.assertEqual(ctx.exception.resource, 'project')

    def test_returns_field_null_raises_not_found(self):
        client = _client({'projectByName': {'id': None}})
        with self.assertRaises(LagoonNotFoundError):
            resolve_lookup(client, _PROJECT_LOOKUP, 'my-project')

    def test_never_returns_none(self):
        client = _client({'projectByName': None})
        try:
            resolve_lookup(client, _PROJECT_LOOKUP, 'missing-project')
            self.fail("expected LagoonNotFoundError")
        except LagoonNotFoundError:
            pass


class TestAmbiguous(unittest.TestCase):

    def test_list_result_raises_ambiguous(self):
        client = _client({'projectByName': [{'id': 1}, {'id': 2}]})
        with self.assertRaises(LagoonAmbiguousResultError) as ctx:
            resolve_lookup(client, _PROJECT_LOOKUP, 'my-project')
        self.assertEqual(ctx.exception.count, 2)
        self.assertEqual(ctx.exception.query, 'projectByName')
        self.assertEqual(ctx.exception.arg, 'name')
        self.assertEqual(ctx.exception.value, 'my-project')

    def test_empty_list_result_raises_ambiguous_not_not_found(self):
        # An empty list is a different failure shape from a null result --
        # the query resolved to a list at all, which is itself the
        # misconfiguration this distinguishes, regardless of length.
        client = _client({'projectByName': []})
        with self.assertRaises(LagoonAmbiguousResultError) as ctx:
            resolve_lookup(client, _PROJECT_LOOKUP, 'my-project')
        self.assertEqual(ctx.exception.count, 0)


class TestMisconfiguredReturnsField(unittest.TestCase):

    def test_returns_pointing_at_a_list_field_raises_config_error(self):
        lookup_config = {
            'query': 'projectByName', 'arg': 'name', 'returns': 'branches',
        }
        client = _client({'projectByName': {'branches': ['main', 'dev']}})
        with self.assertRaises(LagoonConfigError):
            resolve_lookup(client, lookup_config, 'my-project')

    def test_returns_pointing_at_an_object_field_raises_config_error(self):
        lookup_config = {
            'query': 'projectByName', 'arg': 'name', 'returns': 'openshift',
        }
        client = _client(
            {'projectByName': {'openshift': {'id': 1, 'name': 'os'}}})
        with self.assertRaises(LagoonConfigError):
            resolve_lookup(client, lookup_config, 'my-project')


class TestVariableNotInterpolated(unittest.TestCase):

    def test_special_characters_only_in_variables(self):
        client = _client({'projectByName': {'id': 42}})
        dangerous_value = '{"} evil { nested }'
        resolve_lookup(client, _PROJECT_LOOKUP, dangerous_value)

        args, kwargs = client.execute.call_args
        document = args[0] if args else kwargs['query']
        variables = kwargs.get('variables') or (
            args[1] if len(args) > 1 else None)

        self.assertNotIn(dangerous_value, document)
        self.assertEqual(variables, {'name': dangerous_value})

    def test_document_independent_of_value(self):
        client = _client({'projectByName': {'id': 1}})
        resolve_lookup(client, _PROJECT_LOOKUP, 'plain-value')
        first_document = client.execute.call_args.args[0]

        client2 = _client({'projectByName': {'id': 1}})
        resolve_lookup(client2, _PROJECT_LOOKUP, 'a completely different '
                                                  'value { with braces }')
        second_document = client2.execute.call_args.args[0]

        self.assertEqual(first_document, second_document)


class TestArgType(unittest.TestCase):

    def test_default_arg_type_is_required_string(self):
        client = _client({'projectByName': {'id': 1}})
        resolve_lookup(client, _PROJECT_LOOKUP, 'my-project')
        document = client.execute.call_args.args[0]
        self.assertIn('String!', document)

    def test_custom_arg_type_used(self):
        lookup_config = dict(_ENV_LOOKUP, arg_type='Int!')
        client = _client(
            {'environmentByKubernetesNamespaceName': {'id': 1}})
        resolve_lookup(client, lookup_config, 123)
        document = client.execute.call_args.args[0]
        self.assertIn('Int!', document)


class TestInvalidateLookup(unittest.TestCase):

    def test_removes_exactly_the_targeted_entry(self):
        cache = {
            ('projectByName', 'name', 'project-a'): 1,
            ('projectByName', 'name', 'project-b'): 2,
            ('environmentByKubernetesNamespaceName',
             'kubernetesNamespaceName', 'project-a'): 3,
        }
        invalidate_lookup(cache, _PROJECT_LOOKUP, 'project-a')
        self.assertNotIn(('projectByName', 'name', 'project-a'), cache)
        self.assertIn(('projectByName', 'name', 'project-b'), cache)
        self.assertIn(
            ('environmentByKubernetesNamespaceName',
             'kubernetesNamespaceName', 'project-a'), cache)

    def test_missing_entry_is_a_noop(self):
        cache = {('projectByName', 'name', 'project-a'): 1}
        invalidate_lookup(cache, _PROJECT_LOOKUP, 'never-cached')
        self.assertEqual(
            cache, {('projectByName', 'name', 'project-a'): 1})

    def test_none_cache_is_a_noop(self):
        invalidate_lookup(None, _PROJECT_LOOKUP, 'project-a')

    def test_invalidated_entry_refetches_on_next_resolve(self):
        client = MagicMock()
        client.execute = MagicMock(side_effect=[
            {'projectByName': {'id': 1}},
            {'projectByName': {'id': 2}},
        ])
        cache = {}
        resolve_lookup(client, _PROJECT_LOOKUP, 'my-project', cache=cache)
        invalidate_lookup(cache, _PROJECT_LOOKUP, 'my-project')
        second = resolve_lookup(client, _PROJECT_LOOKUP, 'my-project',
                                 cache=cache)
        self.assertEqual(second, 2)
        self.assertEqual(client.execute.call_count, 2)


class TestNoForbiddenImports(unittest.TestCase):

    def test_forbidden_imports_absent(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..',
            'plugins', 'module_utils', 'lookup.py')
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
                if n.module == 'ansible.errors':
                    bad.append(n.module)
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
