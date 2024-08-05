from .gql import GqlClient
from gql.dsl import DSLField
from graphql import (
  GraphQLEnumType,
  GraphQLInputField,
  GraphQLInputObjectType,
  GraphQLInputType,
  GraphQLList,
  GraphQLNonNull
)
from graphql.type.definition import (
  GraphQLArgument,
  is_enum_type,
  is_input_object_type,
  is_list_type,
  is_non_null_type,
  is_scalar_type
)
from typing import cast

def auth_argument_spec(spec=None) -> dict:
  arg_spec = (dict(
    api_endpoint=dict(
      type='str',
      aliases=['lagoon_api_endpoint', 'lagoon_endpoint']),
    api_token=dict(
      type='str', no_log=True,
      aliases=['lagoon_api_token', 'lagoon_token']),
  ))
  if spec:
    arg_spec.update(spec)
  return arg_spec

def generate_argspec_from_mutation(
    client: GqlClient, mutation: str,
    additionalArgs: dict = {}, aliases: dict = {}) -> dict:

  with client:
    mutationField: DSLField = getattr(client.ds.Mutation, mutation)
    argSpec = dict()
    arg: GraphQLArgument
    for fieldName, arg in mutationField.field.args.items():
      argSpec[fieldName] = generate_argspec_for_input_type(arg.type, aliases)
    argSpec.update(additionalArgs)
    return argSpec

def generate_argspec_from_input_object_type(
    objType: GraphQLInputObjectType, aliases: dict) -> dict:

  argSpec = dict()
  fields = objType.fields
  field: GraphQLInputField
  for fieldName, field in fields.items():
    argSpec[fieldName] = generate_argspec_for_input_type(field.type, aliases)
    if fieldName in aliases:
      argSpec[fieldName]['aliases'] = aliases[fieldName]
  return argSpec

def generate_argspec_for_input_type(inputType: GraphQLInputType, aliases: dict) -> dict:
  if is_scalar_type(inputType):
    if inputType.name == 'Boolean':
      return dict(type='bool')
    elif inputType.name == 'Int':
      return dict(type='int')
    else:
      return dict(type='str')
  elif is_non_null_type(inputType):
    nonNullType = cast(GraphQLNonNull, inputType)
    argSpec = generate_argspec_for_input_type(nonNullType.of_type, aliases)
    argSpec['required'] = True
    return argSpec
  elif is_enum_type(inputType):
    enumType = cast(GraphQLEnumType, inputType)
    return dict(type='str', choices=[enumVal for enumVal in enumType.values.keys()])
  elif is_list_type(inputType):
    listType = cast(GraphQLList, inputType)
    return generate_argspec_for_input_type(listType.of_type, aliases)
  elif is_input_object_type(inputType):
    objType = cast(GraphQLInputObjectType, inputType)
    return dict(
      type='dict',
      elements=generate_argspec_from_input_object_type(objType, aliases))
  else:
    print('inputType', inputType.to_kwargs(), "\n")
    raise Exception("Unsupported input type found when generating argspec")
