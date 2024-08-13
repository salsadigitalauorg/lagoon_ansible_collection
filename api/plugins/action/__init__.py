from __future__ import annotations

import re

from ..module_utils.argspec import auth_argument_spec, generate_argspec_from_mutation
from ..module_utils.gql import GetClientInstance, ProxyLookup, input_args_to_field_list
from ..module_utils.gqlEnvironment import Environment
from ..module_utils.gqlProject import Project
from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase
from gql.dsl import DSLMutation
from typing import List


class LagoonActionBase(ActionBase):

  def run(self, tmp=None, task_vars=None):
    if task_vars is None:
      task_vars = dict()

    result = super(LagoonActionBase, self).run(tmp, task_vars)
    del tmp

    self._display.v("Task args: %s" % self._task.args)
    return result

  def createClient(self, task_vars):
    if not task_vars.get('lagoon_api_endpoint'):
      raise AnsibleError("lagoon_api_endpoint is required")
    if not task_vars.get('lagoon_api_token'):
      raise AnsibleError("lagoon_api_token is required")

    self.client = GetClientInstance(
      self._templar.template(task_vars.get('lagoon_api_endpoint')).strip(),
      self._templar.template(task_vars.get('lagoon_api_token')).strip(),
      self._task.args.get('headers', {}),
      self._task.check_mode
    )

  def sanitiseName(self, name: str) -> str:
    return re.sub(r'[\W_-]+', '-', name)

  def getProjectIdFromName(self, name: str) -> int:
    lagoonProject = Project(self.client).byName(name, ["id"])
    if len(lagoonProject.errors):
      raise AnsibleError("Error fetching project: %s" % lagoonProject.errors)
    if not len(lagoonProject.projects):
      raise AnsibleError(f"Project '{name}' not found")
    return lagoonProject.projects[0]["id"]

  def getEnvironmentIdFromNs(self, ns: str) -> int:
    lagoonEnvironment = Environment(self.client).byNs(ns, ["id"])
    if len(lagoonEnvironment.errors):
      raise AnsibleError("Error fetching environment: %s" %
                         lagoonEnvironment.errors)
    if not len(lagoonEnvironment.environments):
      raise AnsibleError(f"Environment '{ns}' not found")
    return lagoonEnvironment.environments[0]["id"]


class MutationConfig:

  # The name of the mutation field, e.g, addAdvancedTaskDefinition.
  field: str

  # The name of the mutation field to update an
  # existing record, e.g, updateAdvancedTaskDefinition.
  updateField: str

  # Additional argspec map to process the action plugin input.
  # E.g: dict(project_name=dict(type="str")) will add a project_name
  # argument to the action plugin. This could then ben used to query
  # the GraphQL API for the project ID, for example, in the proxyLookups.
  inputFieldAdditionalArgs: dict

  # Aliases for the input field arguments, e.g, dict(type=["task_type"])
  # will allow the task_type argument to be passed as type.
  inputFieldArgsAliases: dict

  # Proxy lookups to find existing records. The plugin will use the
  # input arguments to query the GraphQL API and find an existing record.
  # The first matching lookup will be used.
  proxyLookups: List[ProxyLookup]

  # Fields to compare when looking for an existing record.
  lookupCompareFields: List[str]

  # Fields to compare when checking if an existing record is the same as the
  # desired record. If any of these fields differ, the record will be updated.
  diffCompareFields: List[str]

  def __init__(self, field: str, updateField: str = None,
               inputFieldAdditionalArgs: dict = None,
               inputFieldArgsAliases: dict = None,
               proxyLookups: List[ProxyLookup] = None,
               lookupCompareFields: List[str] = None,
               diffCompareFields: List[str] = None) -> None:

    self.field = field
    self.updateField = updateField
    self.inputFieldAdditionalArgs = inputFieldAdditionalArgs
    self.inputFieldArgsAliases = inputFieldArgsAliases
    self.proxyLookups = proxyLookups
    self.lookupCompareFields = lookupCompareFields
    self.diffCompareFields = diffCompareFields


class MutationActionConfig:

  # The name of the action, e.g, task_definition.
  # Not used anywhere at the moment.
  name: str

  # The configuration for the create mutation.
  add: MutationConfig

  # The configuration for the delete mutation.
  delete: MutationConfig

  # Whether the action plugin should have the common Ansible state field with
  # 'present' and 'absent' choices. This depends on which of the add or delete
  # mutation configurations are set.
  hasStateField: bool = False

  def __init__(self, name: str, add: MutationConfig, delete: MutationConfig) -> None:
    self.name = name
    self.add = add
    self.delete = delete

  def validate(self):
    if self.add is None and self.delete is None:
      raise AnsibleError("No mutation configuration found")

    if self.add is not None and self.delete is not None:
      self.hasStateField = True

  def fromState(self, state: str) -> MutationConfig:
    if state == "add":
      return self.add
    elif state == "delete":
      return self.delete
    raise AnsibleError(f"Unknown state: {state}")

  def findExistingRecord(self, action: str, inputArgs: dict) -> dict|None:
    pluginConfig = self.fromState(action)

    if not pluginConfig.proxyLookups or not pluginConfig.lookupCompareFields:
      return None

    foundLookup: ProxyLookup = None
    for lookup in pluginConfig.proxyLookups:
      if not lookup.hasInputArgs(inputArgs):
        continue
      foundLookup = lookup

    if foundLookup == None:
      return None

    return foundLookup.execute(inputArgs, pluginConfig.lookupCompareFields)

  def diffExistingRecord(self, record: dict, inputArgs: dict) -> bool:
    pluginConfig = self.fromState('add')

    if not pluginConfig.diffCompareFields:
      return False

    for field in pluginConfig.diffCompareFields:
      if field not in record or field not in inputArgs:
        continue

      if record[field] != inputArgs[field]:
        return True

    return False


class LagoonMutationActionBase(LagoonActionBase):
  """Action plugins base class for Lagoon mutations.

  Base class for Lagoon actions that perform mutations, providing the
  ability to first verify existence, delete & recreate, or create if
  missing.

  All args for the plugin are inferred from the GraphQL schema, and
  the actionConfig must be filled with all relevant information.
  """

  # The main config for the plugin, and drives the whole process.
  actionConfig : MutationActionConfig

  # The generated argspec from the GraphQL schema.
  argSpec : dict = dict()

  """Whether the mutation has an 'input' wrapper, as in the following:
    mutation {
      addAdvancedTaskDefinition (
        input: {
          type: COMMAND,
          ...
        }
      }
    }
    The plugin will then remove the 'input' key from the module args and allow
    the rest of the arguments to be passed as is. Then it will wrap the args
    in the 'input' key when building the mutation object.
  """
  hasInputWrapper : bool = False

  # The module args after validation.
  moduleArgs : dict = dict()

  # The action to perform, either 'add' or 'delete'.
  action : str = None

  # The mutation object to execute, after being built from
  # the schema, MutationConfig's and the module args.
  mutationObj : DSLMutation = None

  def run(self, tmp=None, task_vars=None):
    result = super(LagoonMutationActionBase, self).run(tmp, task_vars)

    self.validatePluginConfig()

    self.createClient(task_vars)

    # Common auth arguments.
    self.argSpec = auth_argument_spec()

    self.determineAction()
    pluginConfig = self.actionConfig.fromState(self.action)

    with self.client as (_, ds):
      # Generate the argspec from the schema.
      genArgSpec = generate_argspec_from_mutation(
        ds,
        pluginConfig.field,
        pluginConfig.inputFieldAdditionalArgs,
        pluginConfig.inputFieldArgsAliases,
      )
      if len(genArgSpec) == 1 and 'input' in genArgSpec:
        self.hasInputWrapper = True
        genArgSpec = genArgSpec['input']['options']
      self.argSpec.update(genArgSpec)
      self._display.vvv(f"Generated argspec: {self.argSpec}")

      # Validate the arguments.
      _, moduleArgs = self.validate_argument_spec(self.argSpec)

      # Filter out None arguments.
      moduleArgs = {k: v for k, v in moduleArgs.items() if v is not None}

      self._display.vvv(f"Validated module args: {moduleArgs}")
      self.moduleArgs = moduleArgs

      # Find if there's an existing record.
      record = self.actionConfig.findExistingRecord(self.action, moduleArgs)
      if record is not None:
        changed = self.actionConfig.diffExistingRecord(record, moduleArgs)
        if not changed:
          result['changed'] = False
          result['result'] = record
          return result

      self.buildMutationObj(record)

      res = self.client.execute_query_dynamic(self.mutationObj)
      result['result'] = res[pluginConfig.field] if record is None else res[pluginConfig.updateField]
      result['changed'] = True

    return result

  def validatePluginConfig(self):
    if (self.actionConfig is None or
      not isinstance(self.actionConfig, MutationActionConfig)):
      raise AnsibleError("Invalid mutation plugin configuration")

    self.actionConfig.validate()

  def determineAction(self):
    self.action = 'add'
    if self.actionConfig.hasStateField:
      self.argSpec['state'] = dict(
        type='str',
        default='present',
        choices=['absent', 'present'],
      )

      if self._task.args.get('state', 'present') == 'absent':
        self.action = 'delete'

  def buildMutationObj(self, existingRecord: dict|None):
    mutationFieldName = self.actionConfig.fromState(self.action).field
    args = self.moduleArgs

    returnFields = input_args_to_field_list(args)

    if (self.action == 'add' and existingRecord is not None and
        self.actionConfig.fromState(self.action).updateField is not None):
      mutationFieldName = self.actionConfig.fromState(self.action).updateField

      # Generate the update mutation argspec from the schema.
      updateArgSpec = generate_argspec_from_mutation(
        self.client.ds,
        mutationFieldName)

      if len(updateArgSpec) == 1 and 'input' in updateArgSpec:
        if ('id' in updateArgSpec['input']['options'] and
            'patch' in updateArgSpec['input']['options']):
          args = {'input': {
            'id': existingRecord['id'],
            'patch': args}}

    elif self.hasInputWrapper:
      args = {'input': args}

    mutationField = self.client.build_dynamic_mutation(
      mutationFieldName, args, returnFields)

    self.mutationObj = DSLMutation(mutationField)
