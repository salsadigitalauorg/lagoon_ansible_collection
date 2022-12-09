import unittest
from ansible.module_utils.errors import AnsibleValidationError
from ansible_collections.lagoon.api.tests.common import dsl_field_query_to_str, load_schema
from gql.dsl import DSLSchema

import sys
sys.modules['ansible.utils.display'] = unittest.mock.Mock()
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient


class GqlTester(unittest.TestCase):

    def test_client_constructor_missing_args(self):
        with self.assertRaises(TypeError):
            _ = GqlClient()

        client = GqlClient('foo', 'bar')
        assert client.display == None

    def test_build_dynamic_query_missing_args(self):
        client = GqlClient('foo', 'bar')

        with self.assertRaises(TypeError):
            client.build_dynamic_query()

        with self.assertRaises(AnsibleValidationError):
            client.build_dynamic_query('projectByName', 'Project')

    def test_build_dynamic_query_missing_args(self):
        client = GqlClient('foo', 'bar')
        client.ds = DSLSchema(load_schema())
        query = client.build_dynamic_query('projectByName', 'Project', fields=['id', 'name'])
        query_str = dsl_field_query_to_str(query)
        print(f"GraphQL built query: \n{query_str}")
        assert query_str == """{
  projectByName {
    id
    name
  }
}"""
