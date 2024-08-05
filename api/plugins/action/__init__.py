import re

from ..module_utils.argspec import auth_argument_spec, generate_argspec_from_mutation
from ..module_utils.gql import GetClientInstance, ProxyLookup
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
  field: str
  inputFieldAdditionalArgs: dict
  inputFieldArgsAliases: dict
  proxyLookups: List[ProxyLookup]

  def __init__(self, field: str, inputFieldAdditionalArgs: dict = None,
               inputFieldArgsAliases: dict = None,
               proxyLookups: List[ProxyLookup] = None) -> None:

    self.field = field
    self.inputFieldAdditionalArgs = inputFieldAdditionalArgs
    self.inputFieldArgsAliases = inputFieldArgsAliases
    self.proxyLookups = proxyLookups


class MutationActionConfig:
  name: str
  add: MutationConfig
  delete: MutationConfig
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
    if state == "delete":
      return self.delete
    raise AnsibleError(f"Unknown state: {state}")


class LagoonMutationActionBase(LagoonActionBase):
  """Action plugins base class for Lagoon mutations.

  Base class for Lagoon actions that perform mutations, providing the
  ability to first verify existence, delete & recreate, or create if
  missing.

  All args for the plugin are inferred from the GraphQL schema, and
  the mutationInputField() method must be implemented to return the
  name of the input field for the mutation.

  Additional arguments can be provided by implementing the additionalArgs()
  method, and aliases for arguments can be provided by implementing the
  argsAliases() method.
  """

  actionConfig : MutationActionConfig
  argSpec : dict = dict()
  hasInputWrapper : bool = False
  moduleArgs : dict = dict()
  action : str = None
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

      self.buildMutationObj()

      res = self.client.execute_query_dynamic(self.mutationObj)
      result['result'] = res[pluginConfig.field]
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

  def buildMutationObj(self):
    args = self.moduleArgs
    if self.hasInputWrapper:
      args = {'input': args}

    mutationField = self.client.build_dynamic_mutation(
      self.actionConfig.fromState(self.action).field,
      args)

    self.mutationObj = DSLMutation(mutationField)
