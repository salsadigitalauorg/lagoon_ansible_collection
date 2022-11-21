from os.path import dirname, realpath
from gql.dsl import dsl_gql, DSLField, DSLQuery, print_ast
from graphql import GraphQLSchema, build_ast_schema, parse

script_dir = dirname(realpath(__file__))

def load_schema() -> GraphQLSchema:
    with open(f'{script_dir}/schema.graphql') as f:
        schema_str = f.read()
        type_def_ast = parse(schema_str)
        schema = build_ast_schema(type_def_ast)
        return schema

def dsl_field_query_to_str(query: DSLField) -> str:
    return print_ast(dsl_gql(DSLQuery(query)))
