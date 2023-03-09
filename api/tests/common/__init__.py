from os.path import dirname, realpath
from gql.client import SyncClientSession
from gql.dsl import dsl_gql, DSLExecutable, DSLField, DSLQuery, print_ast
from graphql import GraphQLSchema, build_ast_schema, parse
from unittest.mock import MagicMock

from ...plugins.module_utils.gql import GqlClient

script_dir = dirname(realpath(__file__))

def load_schema() -> GraphQLSchema:
    with open(f'{script_dir}/schema.graphql') as f:
        schema_str = f.read()
        type_def_ast = parse(schema_str)
        schema = build_ast_schema(type_def_ast)
        return schema

def dsl_field_query_to_str(query: DSLField) -> str:
    return print_ast(dsl_gql(DSLQuery(query)))

def dsl_exes_to_str(*exes: DSLExecutable) -> str:
    return print_ast(dsl_gql(*exes))

def get_mock_gql_client(
        query_return_value: any = None,
        query_dynamic_return_value: any = None) -> GqlClient:
    client = GqlClient('foo', 'bar')
    client.execute_query = MagicMock()
    if query_return_value:
        client.execute_query.return_value = query_return_value
    client.execute_query_dynamic = MagicMock()
    if query_dynamic_return_value:
        client.execute_query_dynamic.return_value = query_dynamic_return_value
    client.client.connect_sync = MagicMock()
    client.client.schema = load_schema()
    client.client.session = SyncClientSession(client=client.client)
    return client
