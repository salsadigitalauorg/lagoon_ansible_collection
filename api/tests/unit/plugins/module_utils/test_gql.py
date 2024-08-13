import unittest
from ansible.module_utils.errors import AnsibleValidationError
from ....common import dsl_exes_to_str, dsl_field_mutation_field_to_str, dsl_field_query_field_to_str, load_schema
from gql.dsl import DSLField, DSLInlineFragment, DSLQuery, DSLSchema
from unittest.mock import MagicMock

import sys
sys.modules['ansible.utils.display'] = unittest.mock.Mock()
from .....plugins.module_utils.gql import (
  GetClientInstance, GqlClient, ProxyLookup, field_selector,
  input_args_to_field_list, nested_field_selector
)


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
        query_str = dsl_field_query_field_to_str(query)
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
        mutation_str = dsl_field_mutation_field_to_str(mutation)
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
        mutation_str = dsl_field_mutation_field_to_str(mutation)
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

        assert(str(e.exception) == "mutationField must be of type DSLField, got <class 'str'>.")

        # String passed as output type.
        field: DSLField = client.ds.Mutation.addProject
        with self.assertRaises(TypeError) as e:
            client.mutation_field_add_args(field, 'bar', 'baz')

        assert(str(e.exception) == "outputType must be of type GraphQLOutputType, got <class 'str'>.")

        # String passed as input args.
        field: DSLField = client.ds.Mutation.addProject
        with self.assertRaises(TypeError) as e:
            client.mutation_field_add_args(field, field.field.type, 'baz')

        assert(str(e.exception) == "inputArgs must be of type dict, got <class 'str'>.")

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


class GqlUtilsTester(unittest.TestCase):

    def test_input_args_to_field_list(self):
        assert input_args_to_field_list({
            'name': 'foo',
            'bogusArg': 'bar'
        }) == ['name', 'bogusArg', 'id']

        assert input_args_to_field_list({
            'id': 10,
            'name': 'foo',
            'bogusArg': 'bar'
        }) == ['id', 'name', 'bogusArg']

        assert input_args_to_field_list({
            'id': 10,
            'name': 'foo',
            'fact': {'name': 'foo', 'value': 'bar'},
        }) == ['id', 'name', {'fact': ['name', 'value']}]

        assert input_args_to_field_list({
            'id': 10,
            'name': 'foo',
            'ids': [1, 2, 3],
        }) == ['id', 'name', 'ids']

        assert input_args_to_field_list({
            'id': 10,
            'name': 'foo',
            'facts': [
                {'name': 'foo', 'value': 'bar'},
                {'name': 'baz', 'value': 'qux'}
            ],
        }) == ['id', 'name', {'facts': ['name', 'value']}]

    def test_field_selector(self):
        ds = DSLSchema(load_schema())

        with self.assertRaises(TypeError) as e:
            field_selector()

        assert(str(e.exception) == "field_selector() missing 3 required positional arguments: 'ds', 'selector', and 'selectorType'")

        # String passed as DSLSchema.
        with self.assertRaises(TypeError) as e:
            field_selector('foo', 'bar', 'baz', 'qux')

        assert(str(e.exception) == "ds must be of type DSLSchema, got <class 'str'>.")

        # String passed as field.
        with self.assertRaises(TypeError) as e:
            field_selector(ds, 'foo', 'bar', 'baz')

        assert(str(e.exception) == "selector must be of type DSLField, got <class 'str'>.")

        # String passed as output type.
        field: DSLField = ds.Query.projectByName
        with self.assertRaises(TypeError) as e:
            field_selector(ds, field, 'bar', 'baz')

        assert(str(e.exception) == "selectorType must be of type GraphQLOutputType, got <class 'str'>.")

        # String passed as list.
        field: DSLField = ds.Query.projectByName
        with self.assertRaises(TypeError) as e:
            field_selector(ds, field, field.field.type, 'baz')

        assert(str(e.exception) == "selectFields must be of type list, got <class 'str'>.")

        # Scalar type case.
        field: DSLField = ds.Mutation.deleteProject
        updated_field = field_selector(ds, field, field.field.type)
        assert f"{updated_field}" == 'deleteProject'

        # Enum type case.
        field: DSLField = ds.Project.availability
        updated_field = field_selector(ds, field, field.field.type)
        assert f"{updated_field}" == 'availability'

        # List type case.
        field: DSLField = ds.Project.environments
        updated_field = field_selector(ds, field, field.field.type, ['id', 'name', 'kubernetesNamespaceName'])
        assert f"{updated_field}" == """environments {
  id
  name
  kubernetesNamespaceName
}"""

        # Object type case - inexistent fields are ignored.
        field: DSLField = ds.Query.projectByName
        updated_field = field_selector(ds, field, field.field.type, ['id', 'name', 'bogusField'])
        assert f"{updated_field}" == """projectByName {
  id
  name
}"""

        # Union type case.
        field: DSLField = ds.Query.advancedTasksForEnvironment
        updated_field = field_selector(ds, field, field.field.type, ['id', 'name', 'description'])
        assert f"{updated_field}" == """advancedTasksForEnvironment {
  ... on AdvancedTaskDefinitionImage {
    id
    name
    description
  }
  ... on AdvancedTaskDefinitionCommand {
    id
    name
    description
  }
}"""

    def test_nested_field_selector(self):
        ds = DSLSchema(load_schema())

        with self.assertRaises(TypeError) as e:
            nested_field_selector()

        assert(str(e.exception) == "nested_field_selector() missing 4 required positional arguments: 'ds', 'parentType', 'selectFields', and 'leafFields'")

        # String passed as DSLSchema.
        with self.assertRaises(TypeError) as e:
            nested_field_selector('foo', 'bar', 'baz', 'qux')

        assert(str(e.exception) == "ds must be of type DSLSchema, got <class 'str'>.")

        # String passed as parent type.
        with self.assertRaises(TypeError) as e:
            nested_field_selector(ds, 'foo', 'bar', 'baz')

        assert(str(e.exception) == "parentType must be of type DSLType, got <class 'str'>.")

        # String passed as select fields.
        parent_type = ds.Project
        with self.assertRaises(TypeError) as e:
            nested_field_selector(ds, parent_type, 'bar', 'baz')

        assert(str(e.exception) == "selectFields must be of type list, got <class 'str'>.")

        # String passed as leaf fields.
        parent_type = ds.Project
        with self.assertRaises(TypeError) as e:
            nested_field_selector(ds, parent_type, ['bar'], 'baz')

        assert(str(e.exception) == "leafFields must be of type list, got <class 'str'>.")

        # Zero select fields.
        parent_type = ds.Project
        with self.assertRaises(AnsibleValidationError) as e:
            nested_field_selector(ds, parent_type, [], ['id', 'name'])

        assert(str(e.exception) == "selectFields must have at least one field.")

        # Single-level field.
        parent_type = ds.Project
        updated_field = nested_field_selector(ds, parent_type, ['environments'], ['id', 'kubernetesNamespaceName'])
        assert f"{updated_field}" == """environments {
  id
  kubernetesNamespaceName
}"""

        # Multi-level field, list.
        parent_type = ds.Project
        updated_field = nested_field_selector(ds, parent_type, ['environments', 'advancedTasks'], ['id', 'name', 'description'])
        assert f"{updated_field}" == """environments {
  advancedTasks {
    ... on AdvancedTaskDefinitionImage {
      id
      name
      description
    }
    ... on AdvancedTaskDefinitionCommand {
      id
      name
      description
    }
  }
}"""

        # Multi-level field, non-list.
        parent_type = ds.Fact
        updated_field = nested_field_selector(ds, parent_type, ['environment', 'advancedTasks'], ['id', 'name', 'description'])
        assert f"{updated_field}" == """environment {
  advancedTasks {
    ... on AdvancedTaskDefinitionImage {
      id
      name
      description
    }
    ... on AdvancedTaskDefinitionCommand {
      id
      name
      description
    }
  }
}"""

class GqlProxyLookup(unittest.TestCase):

    def test_constructor(self):
        with self.assertRaises(TypeError) as e:
            _ = ProxyLookup()

        assert(str(e.exception) == "__init__() missing 1 required positional argument: 'query'")

    def test_hasInputArgs(self):
        GetClientInstance('foo', 'bar').ds = DSLSchema(load_schema())

        lookup = ProxyLookup('projectByName')
        assert lookup.hasInputArgs({}) == False

        lookup = ProxyLookup('projectByName')
        assert lookup.hasInputArgs({'fooArg': 'bar'}) == False

        lookup = ProxyLookup('projectByName', inputArgFields={'fooArg': 'name'})
        assert lookup.hasInputArgs({'fooArg': 'bar'}) == True

        lookup = ProxyLookup('projectByName')
        assert lookup.hasInputArgs({'name': 'foo'}) == True

    def test_execute(self):
        client = GetClientInstance('foo', 'bar')
        client.ds = DSLSchema(load_schema())

        lookup = ProxyLookup('projectByName')
        with self.assertRaises(TypeError) as e:
            lookup.execute()

        assert(str(e.exception) == "execute() missing 2 required positional arguments: 'inputArgs' and 'lookupCompareFields'")

        # String passed as dict.
        lookup = ProxyLookup('projectByName')
        with self.assertRaises(TypeError) as e:
            lookup.execute('foo', 'bar')

        assert(str(e.exception) == "inputArgs must be of type dict, got <class 'str'>.")

        # String passed as list.
        lookup = ProxyLookup('projectByName')
        with self.assertRaises(TypeError) as e:
            lookup.execute({'name': 'foo'}, 'bar')

        assert(str(e.exception) == "lookupCompareFields must be of type list, got <class 'str'>.")

        # No input args.
        lookup = ProxyLookup('projectByName')
        with self.assertRaises(AnsibleValidationError) as e:
            lookup.execute({}, ['name'])

        assert(str(e.exception) == "inputArgs must have at least one key-value pair.")

        # No lookup compare fields.
        lookup = ProxyLookup('projectByName')
        with self.assertRaises(AnsibleValidationError) as e:
            lookup.execute({'name': 'foo'}, [])

        assert(str(e.exception) == "lookupCompareFields must have at least one field.")

        # No select fields.
        client.execute_query_dynamic = MagicMock()
        lookup = ProxyLookup('projectByName',
                             inputArgFields={'projectName': 'name'})
        lookup.hasInputArgs({'projectName': 'foo'})
        lookup.execute({'projectName': 'foo'}, ['name'])
        expectedQry = DSLQuery(
            client.ds.Query.projectByName(name='foo').select(
                client.ds.Project.id, # id is automatically selected.
                client.ds.Project.name, # name is selected because it's in lookupCompareFields.
            ))
        query_args = client.execute_query_dynamic.call_args.args
        actualQry = query_args[0]
        assert dsl_exes_to_str(expectedQry) == dsl_exes_to_str(actualQry)

        # With select fields.
        client.execute_query_dynamic = MagicMock()
        lookup = ProxyLookup('projectByName',
                             inputArgFields={'projectName': 'name'},
                             selectFields=['environments', 'advancedTasks'])
        lookup.hasInputArgs({'projectName': 'foo'})
        lookup.execute({'projectName': 'foo'}, ['name'])
        expectedQry = DSLQuery(
            client.ds.Query.projectByName(name='foo').select(
                client.ds.Project.environments.select(
                    client.ds.Environment.advancedTasks.select(
                        DSLInlineFragment().on(client.ds.AdvancedTaskDefinitionImage).select(
                            client.ds.AdvancedTaskDefinitionImage.id,
                            client.ds.AdvancedTaskDefinitionImage.name),
                        DSLInlineFragment().on(client.ds.AdvancedTaskDefinitionCommand).select(
                            client.ds.AdvancedTaskDefinitionImage.id,
                            client.ds.AdvancedTaskDefinitionImage.name)))))
        query_args = client.execute_query_dynamic.call_args.args
        actualQry = query_args[0]
        assert dsl_exes_to_str(expectedQry) == dsl_exes_to_str(actualQry)

        # No select fields, with return values: None.
        client.execute_query_dynamic = MagicMock(
            return_value={'projectByName': None})
        lookup = ProxyLookup('projectByName',
                             inputArgFields={'projectName': 'name'})
        lookup.hasInputArgs({'projectName': 'foo'})
        result = lookup.execute({'projectName': 'foo'}, ['name'])
        assert result == None

        # No select fields, with return values: Single value.
        client.execute_query_dynamic = MagicMock(
            return_value={'projectByName': {'id': 78, 'name': 'foo'}})
        lookup = ProxyLookup('projectByName',
                             inputArgFields={'projectName': 'name'})
        lookup.hasInputArgs({'projectName': 'foo'})
        result = lookup.execute({'projectName': 'foo'}, ['name'])
        assert result == {'id': 78, 'name': 'foo'}

        # No select fields, with return values: Multiple values.
        client.execute_query_dynamic = MagicMock(
            return_value={'projectByName': [
                {'id': 78, 'name': 'foo'}, {'id': 79, 'name': 'bar'}]})
        lookup = ProxyLookup('projectByName',
                             inputArgFields={'projectName': 'name'})
        lookup.hasInputArgs({'projectName': 'foo'})
        result = lookup.execute({'projectName': 'foo'}, ['name'])
        assert result == [{'id': 78, 'name': 'foo'}, {'id': 79, 'name': 'bar'}]

        # With select fields, with return values: None.
        client.execute_query_dynamic = MagicMock(
            return_value={'projectByName': None})
        lookup = ProxyLookup('projectByName',
                             inputArgFields={'projectName': 'name'},
                             selectFields=['environments', 'advancedTasks'])
        lookup.hasInputArgs({'projectName': 'foo'})
        result = lookup.execute({'projectName': 'foo'}, ['name'])
        assert result == None

        # With select fields, with return values: Single value but not found.
        client.execute_query_dynamic = MagicMock(
            return_value={
                'projectByName': {
                    'environments': [{
                        'advancedTasks': [
                            {'id': 12, 'name': 'zoom'},
                            {'id': 13, 'name': 'zap'},
                        ]
                    }],
                }})
        lookup = ProxyLookup('projectByName',
                             inputArgFields={'projectName': 'name'},
                             selectFields=['environments', 'advancedTasks'])
        lookup.hasInputArgs({'projectName': 'foo', 'name': 'poof'})
        result = lookup.execute({'projectName': 'foo', 'name': 'poof'}, ['name'])
        assert result == None

        # With select fields, with return values: Single value, found.
        client.execute_query_dynamic = MagicMock(
            return_value={
                'projectByName': {
                    'environments': [{
                        'advancedTasks': [
                            {'id': 12, 'name': 'zoom'},
                            {'id': 13, 'name': 'zap'},
                        ]
                    }],
                }})
        lookup = ProxyLookup('projectByName',
                             inputArgFields={'projectName': 'name'},
                             selectFields=['environments', 'advancedTasks'])
        lookup.hasInputArgs({'projectName': 'foo', 'name': 'zap'})
        result = lookup.execute({'projectName': 'foo', 'name': 'zap'}, ['name'])
        assert result == {'id': 13, 'name': 'zap'}
