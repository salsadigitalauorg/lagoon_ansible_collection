import re

from ..module_utils.argspec import auth_argument_spec, generate_argspec_from_mutation
from ..module_utils.gql import GqlClient
from ..module_utils.gqlEnvironment import Environment
from ..module_utils.gqlProject import Project
from gql.dsl import DSLMutation
from graphql import GraphQLOutputType
from ansible.plugins.action import ActionBase
from ansible.errors import AnsibleError


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
    self.client = GqlClient(
      self._templar.template(task_vars.get('lagoon_api_endpoint')).strip(),
      self._templar.template(task_vars.get('lagoon_api_token')).strip(),
      self._task.args.get('headers', {}),
      self._display,
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

  mutationPluginConfig = dict()
  hasStateField = False
  hasInputWrapper = False
  moduleArgs = dict()
  action = None

  def run(self, tmp=None, task_vars=None):
    result = super(LagoonMutationActionBase, self).run(tmp, task_vars)

    self.validatePluginConfig()

    self.createClient(task_vars)

    # Common auth arguments.
    argSpec = auth_argument_spec()

    action = 'add'
    if self.hasStateField:
      argSpec['state'] = dict(
        type='str',
        default='present',
        choices=['absent', 'present'],
      )

      if self._task.args.get('state', 'present') == 'absent':
        action = 'delete'

    # Generate the argspec from the schema.
    genArgSpec = generate_argspec_from_mutation(
      self.client,
      self.mutationPluginConfig.get(action).get('mutation'),
      self.mutationPluginConfig.get(action).get('inputFieldAdditionalArgs', {}),
      self.mutationPluginConfig.get(action).get('inputFieldArgsAliases', {}),
    )
    if len(genArgSpec) == 1 and 'input' in genArgSpec:
      self.hasInputWrapper = True
      genArgSpec = genArgSpec['input']['elements']
    argSpec.update(genArgSpec)

    # Validate the arguments.
    _, moduleArgs = self.validate_argument_spec(argSpec)
    self.moduleArgs = moduleArgs
    self.determineAction()

    # if self.action == 'delete':
    #   mutationObj = self.client.build_dynamic_mutation(
    #     self.mutationPluginConfig.get(action).get('mutation'),
    #     moduleArgs, returnType, subfields)
    #   res = self.client.execute_query_dynamic(DSLMutation(mutationObj))

    return result

  def validatePluginConfig(self):
    if (self.mutationPluginConfig is None or
      not isinstance(self.mutationPluginConfig, dict)):
      raise AnsibleError("Invalid mutation plugin configuration")

    if len(self.mutationPluginConfig.keys()) == 0:
      raise AnsibleError("No mutation plugin configuration found")

    if self.hasAdd() and self.hasDelete():
      self.hasStateField = True

  def hasAdd(self):
    return self.mutationPluginConfig.get('add') is not None

  def hasDelete(self):
    return self.mutationPluginConfig.get('delete') is not None

  def determineAction(self):
    if self.hasStateField:
      if self.moduleArgs.get('state', 'present') == 'present':
        self.action = 'add'
      elif self.moduleArgs.get('state', 'present') == 'absent':
        self.action = 'delete'
