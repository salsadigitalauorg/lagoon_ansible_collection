from .display import SENSITIVE_FIELD_NAMES
from .gql import DSLSchema
from gql.dsl import DSLField
from graphql import (
  GraphQLEnumType,
  GraphQLInputField,
  GraphQLInputObjectType,
  GraphQLInputType,
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

def mark_no_log(fieldName: str, fieldSpec: dict) -> dict:
  """Flag a sensitive string field so its value can be scrubbed from output.

  LagoonMutationActionBase reads the flag back via
  ValidationResult._no_log_values to build the redaction set.

  Only applied to type='str': flagging an Int field would put its stringified
  value (e.g. "42") into the no-log set and star out that substring
  everywhere, including unrelated IDs.

  SENSITIVE_FIELD_NAMES is matched exactly, not by substring, so 'token'/'key'
  don't catch the booleans deployTokenInjection and projectKeyInjection.
  """
  if fieldName in SENSITIVE_FIELD_NAMES and fieldSpec.get('type') == 'str':
    fieldSpec['no_log'] = True
  return fieldSpec

def generate_argspec_from_mutation(
    ds: DSLSchema, mutation: str,
    additionalArgs: dict = {}, aliases: dict = {}) -> dict:

  mutationField: DSLField = getattr(ds.Mutation, mutation)
  argSpec = dict()
  arg: GraphQLArgument
  for fieldName, arg in mutationField.field.args.items():
    argSpec[fieldName] = mark_no_log(
      fieldName, generate_argspec_for_input_type(arg.type, aliases))

  if 'input' in argSpec and additionalArgs:
    argSpec['input']['options'].update(additionalArgs)
  elif additionalArgs:
    argSpec.update(additionalArgs)
  return argSpec

def generate_argspec_from_input_object_type(
    objType: GraphQLInputObjectType, aliases: dict) -> dict:

  argSpec = dict()
  fields = objType.fields
  field: GraphQLInputField
  for fieldName, field in fields.items():
    argSpec[fieldName] = mark_no_log(
      fieldName, generate_argspec_for_input_type(field.type, aliases))
    if aliases and fieldName in aliases:
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
    return dict(type='list', elements='dict')
  elif is_input_object_type(inputType):
    objType = cast(GraphQLInputObjectType, inputType)
    return dict(
      type='dict',
      options=generate_argspec_from_input_object_type(objType, aliases))
  else:
    print('inputType', inputType.to_kwargs(), "\n")
    raise Exception("Unsupported input type found when generating argspec")
