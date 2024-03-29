from ansible.errors import AnsibleError
from ansible_collections.lagoon.api.plugins.lookup import LagoonLookupBase
from ansible_collections.lagoon.api.plugins.module_utils.gqlProject import Project
from ansible_collections.lagoon.api.plugins.module_utils.gqlEnvironment import Environment

DOCUMENTATION = """
  name: project
  author: Yusuf Hasan Miyan <yusuf@salsa.digital>
  short_description: get a lagoon project
  description:
      - This lookup returns the information for a Lagoon project.
  options:
    _terms:
      description: The project to query (or environment if from_environment is True)
      required: True
    from_environment:
      description: Flag to lookup the project from an environment.
      type: boolean
      default: False
    lagoon_api_endpoint:
      description: The Lagoon graphql endpoint
      type: string
      required: True
      vars:
        - name: lagoon_api_endpoint
    lagoon_api_token:
      description: The token for Lagoon graphql API
      type: string
      required: True
      vars:
        - name: lagoon_api_token
    validate_certs:
      description: Flag to control SSL certificate validation
      type: boolean
      default: False
    headers:
      description: HTTP request headers
      type: dictionary
      default: {}
    timeout:
      description: How long to wait for the server to send data before giving up
      type: float
      default: 10
      vars:
          - name: ansible_lookup_url_timeout
      env:
          - name: ANSIBLE_LOOKUP_URL_TIMEOUT
      ini:
          - section: url_lookup
            key: timeout
"""

EXAMPLES = """
- name: retrieve a project's information
  debug: msg="{{ lookup('lagoon.api.project', project_name) }}"

- name: retrieve a project's information from an environment
  debug: msg="{{ lookup('lagoon.api.project', environment_ns, from_environment=true) }}"
"""


class LookupModule(LagoonLookupBase):

  def run(self, terms, variables=None, **kwargs):

    ret = []

    self.set_options(var_options=variables, direct=kwargs)

    self.createClient()

    lagoonProject = Project(self.client)
    lagoonEnvironment = Environment(self.client)

    for term in terms:
      if self.get_option('from_environment'):
        lagoonEnvironment.byNs(term, ['id'])
        if not len(lagoonEnvironment.environments):
          raise AnsibleError(
              f"Unable to fetch environment {term}; errors: {lagoonEnvironment.errors}")

        lagoonEnvironment.withProject()
        lagoonProject.projects = [lagoonEnvironment.environments[0]['project']]
      else:
        lagoonProject.byName(term)
        if not len(lagoonProject.projects):
            return ret

      lagoonProject.withCluster().withEnvironments()
      lagoonProject.withDeployTargetConfigs().withVariables().withGroups()
      if len(lagoonProject.errors):
        self._display.warning(
            f"The query partially succeeded, but the following errors were encountered:\n{ lagoonProject.errors }")
      ret.extend(lagoonProject.projects)

    return ret
