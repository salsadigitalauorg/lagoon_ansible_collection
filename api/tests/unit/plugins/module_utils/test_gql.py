import unittest
from ansible.module_utils.errors import AnsibleValidationError
from ....common import dsl_field_mutation_to_str, dsl_field_query_to_str, load_schema
from gql.dsl import DSLField, DSLSchema

import sys
sys.modules['ansible.utils.display'] = unittest.mock.Mock()
from .....plugins.module_utils.gql import GqlClient


class GqlClientTester(unittest.TestCase):

    def test_client_constructor_missing_args(self):
        with self.assertRaises(TypeError):
            _ = GqlClient()

        client = GqlClient('foo', 'bar')
        assert client.display == None

    def test_build_dynamic_query_missing_args(self):
        client = GqlClient('foo', 'bar')

        with self.assertRaises(TypeError) as e:
            client.build_dynamic_query()

        assert(str(e.exception) == "build_dynamic_query() missing 2 required positional arguments: 'query' and 'mainType'")

        with self.assertRaises(AnsibleValidationError) as e:
            client.build_dynamic_query('projectByName', 'Project')

        assert(str(e.exception) == "One of fields or subFieldsMap is required.")

    def test_build_dynamic_query(self):
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

    def test_build_dynamic_mutation_missing_args(self):
        client = GqlClient('foo', 'bar')

        with self.assertRaises(TypeError) as e:
            client.build_dynamic_mutation()

        assert(str(e.exception) == "build_dynamic_mutation() missing 2 required positional arguments: 'mutation' and 'inputArgs'")

        with self.assertRaises(TypeError) as e:
            client.build_dynamic_mutation('projectByName')

        assert(str(e.exception) == "build_dynamic_mutation() missing 1 required positional argument: 'inputArgs'")

    def test_build_dynamic_mutation_query_instead_of_mutation(self):
        client = GqlClient('foo', 'bar')
        client.ds = DSLSchema(load_schema())

        with self.assertRaises(AttributeError) as e:
            client.build_dynamic_mutation('projectByName', inputArgs={'name': 'foo'})

        assert(str(e.exception) == "Field projectByName does not exist in type Mutation.")

    def test_build_dynamic_mutation_wrong_input_format(self):
        client = GqlClient('foo', 'bar')
        client.ds = DSLSchema(load_schema())

        with self.assertRaises(KeyError) as e:
            client.build_dynamic_mutation('addProject', inputArgs={'name': 'foo'})

        assert(str(e.exception) == "'Argument name does not exist in Field: Project.'")

    def test_build_dynamic_mutation(self):
        client = GqlClient('foo', 'bar')
        client.ds = DSLSchema(load_schema())

        # No return fields - should use default ['id'].
        mutation = client.build_dynamic_mutation(
            'addProject', inputArgs={'input': {'name': 'foo'}})
        mutation_str = dsl_field_mutation_to_str(mutation)
        assert mutation_str == """mutation {
  addProject(input: {name: "foo"}) {
    id
  }
}"""

        # With return fields - inexistent args are ignored.
        mutation = client.build_dynamic_mutation(
            'addProject',
            inputArgs={'input': {'name': 'foo', 'bogusArg': 'bar'}},
            returnFields=['name', 'kubernetes'])
        mutation_str = dsl_field_mutation_to_str(mutation)
        assert mutation_str == """mutation {
  addProject(input: {name: "foo"}) {
    name
    kubernetes
  }
}"""

    def test_mutation_field_add_args(self):
        client = GqlClient('foo', 'bar')
        client.ds = DSLSchema(load_schema())

        with self.assertRaises(TypeError) as e:
            client.mutation_field_add_args()

        assert(str(e.exception) == "mutation_field_add_args() missing 3 required positional arguments: 'mutationField', 'outputType', and 'inputArgs'")

        # String passed as field.
        with self.assertRaises(TypeError) as e:
            client.mutation_field_add_args('foo', 'bar', 'baz')

        assert(str(e.exception) == "mutationField must be of type DSLField.")

        # String passed as output type.
        field: DSLField = client.ds.Mutation.addProject
        with self.assertRaises(TypeError) as e:
            client.mutation_field_add_args(field, 'bar', 'baz')

        assert(str(e.exception) == "outputType must be of type GraphQLOutputType.")

        # String passed as input args.
        field: DSLField = client.ds.Mutation.addProject
        with self.assertRaises(TypeError) as e:
            client.mutation_field_add_args(field, field.field.type, 'baz')

        assert(str(e.exception) == "inputArgs must be of type dict.")

        # Field does not exist in schema.
        field: DSLField = client.ds.Mutation.addProject
        with self.assertRaises(KeyError) as e:
            client.mutation_field_add_args(field, field.field.type, {'name': 'foo'})

        assert(str(e.exception) == "'Argument name does not exist in Field: Project.'")

        # Scalar type case.
        field: DSLField = client.ds.Mutation.deleteAdvancedTaskDefinition
        client.mutation_field_add_args(field, field.field.type, {'advancedTaskDefinition': -980})
        assert f"{field}" == 'deleteAdvancedTaskDefinition(advancedTaskDefinition: -980)'

        # Object type case.
        field: DSLField = client.ds.Mutation.addProject
        client.mutation_field_add_args(field, field.field.type, {'input': {'name': 'foo'}})
        assert f"{field}" == 'addProject(input: {name: "foo"})'

        # Enum (union) type case.
        field: DSLField = client.ds.Mutation.addProject
        client.mutation_field_add_args(field, field.field.type, {'input': {'availability': 'STANDARD'}})
        assert f"{field}" == 'addProject(input: {availability: STANDARD})'

        # List type case.
        field: DSLField = client.ds.Mutation.addFactsByName
        client.mutation_field_add_args(field, field.field.type, {
            'input': {'facts': [{'name': 'foo', 'value': 'bar'}]}})
        assert f"{field}" == 'addFactsByName(input: {facts: [{name: "foo", value: "bar"}]})'

