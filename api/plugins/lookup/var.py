from ansible.errors import AnsibleError
from ansible_collections.lagoon.api.plugins.lookup import LagoonLookupBase
from ansible_collections.lagoon.api.plugins.module_utils.gqlEnvironment import Environment
from ansible_collections.lagoon.api.plugins.module_utils.gqlProject import Project

DOCUMENTATION = """
  name: var
  author: Yusuf Hasan Miyan <yusuf.hasanmiyan@salsadigital.com.au>
  short_description: get lagoon variables
  description:
      - This lookup returns the variables for a Lagoon project or environment.
  options:
    _terms:
      description: The project to query
      required: True
    environment:
      description: The project environment to query
      type: string
    var_name:
      description: Specific variable name to fetch
      type: string
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
    return_dict:
      description: Return the results as a dict keyed by the variable name
      type: boolean
      default: False
"""

EXAMPLES = """
- name: lookup a project's variables
  debug: msg="{{ item }}"
  loop: "{{ lookup('lagoon.api.var', project_name) }}"

- name: retrieve a project's variables as dict
  debug: msg="{{ lookup('lagoon.api.var', project_name, return_dict=true) }}"

- name: retrieve a specific variable for a project
  debug: msg='{{ lookup('lagoon.api.var', project_name, var_name=project_var_name) }}'

- name: retrieve variables for a project environment
  debug: msg='{{ lookup('lagoon.api.var', project_name, environment='master') }}'

- name: retrieve a specific variable for a project environment
  debug: msg='{{ lookup('lagoon.api.var', project_name, environment='master', var_name=project_var_name) }}'
"""


class LookupModule(LagoonLookupBase):

  def run(self, terms, variables=None, **kwargs):

    ret = []

    self.set_options(var_options=variables, direct=kwargs)
    self.createClient()
    environment = self.get_option('environment')

    for term in terms:
      if environment:
        env_name = term + '-' + environment.replace('/', '-').replace('_', '-').replace('.', '-')
        self._display.v(f"Lagoon variable lookup environment: {env_name}")
        lagoonEnvironment = Environment(self.client).byNs(env_name, ['id', 'kubernetesNamespaceName'])
        if not len(lagoonEnvironment.environments):
          raise AnsibleError(
              f"Unable to fetch environment {env_name}; errors: {lagoonEnvironment.errors}")

        lagoonEnvironment.withVariables()
        env_vars = lagoonEnvironment.environments[0]['envVariables']
      else:
        self._display.v(f"Lagoon variable lookup project: {term}")
        lagoonProject = Project(self.client).byName(term, ['name'])
        if not len(lagoonProject.projects):
          raise AnsibleError(
              f"Unable to fetch project {term}; errors: {lagoonProject.errors}")

        lagoonProject.withVariables()
        env_vars = lagoonProject.projects[0]['envVariables']

      if self.get_option('return_dict'):
        vars_dict = {}
        for var in env_vars:
          vars_dict[var['name']] = var
        ret.append(vars_dict)
      elif self.get_option('var_name'):
        self._display.v(
            f"Lagoon variable lookup name: {self.get_option('var_name')}")
        for var in env_vars:
          if var['name'] == self.get_option('var_name'):
            ret.append(var)
            break
      else:
        ret.append(env_vars)

    return ret
