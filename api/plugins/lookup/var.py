from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient
from ansible.plugins.lookup import LookupBase
from ansible.utils.display import Display
from ansible.errors import AnsibleError

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
  loop: "{{ lookup('lagoon.api.var', 'vanilla-govcms9-beta') }}"

- name: retrieve a project's variables as dict
  debug: msg="{{ lookup('lagoon.api.var', 'vanilla-govcms9-beta', return_dict=true) }}"

- name: retrieve a specific variable for a project
  debug: msg='{{ lookup('lagoon.api.var', 'vanilla-govcms9-beta', var_name='CLAMAV_HOST') }}'

- name: retrieve variables for a project environment
  debug: msg='{{ lookup('lagoon.api.var', 'vanilla-govcms9-beta', environment='master') }}'

- name: retrieve a specific variable for a project environment
  debug: msg='{{ lookup('lagoon.api.var', 'vanilla-govcms9-beta', environment='master', var_name='GOVCMS_TEST_CANARY') }}'
"""


display = Display()

def get_vars_from_environment(client: GqlClient, name: str) -> dict:
  with client as (_, ds):
    res = client.execute_query_dynamic(
        ds.Query.environmentByKubernetesNamespaceName(kubernetesNamespaceName=name).select(
            ds.Environment.envVariables.select(
                ds.EnvKeyValue.id,
                ds.EnvKeyValue.name,
                ds.EnvKeyValue.value,
                ds.EnvKeyValue.scope,
            )
        )
    )
    display.v(f"GraphQL query result: {res}")
    if res['environmentByKubernetesNamespaceName'] == None:
        raise AnsibleError(
            f"Unable to get variables for {name}; please make sure the environment name is correct")

    return res['environmentByKubernetesNamespaceName']['envVariables']

def get_vars_from_project(client: GqlClient, name: str) -> dict:
  with client as (_, ds):
    res = client.execute_query_dynamic(
        ds.Query.projectByName(name=name).select(
            ds.Project.envVariables.select(
                ds.EnvKeyValue.id,
                ds.EnvKeyValue.name,
                ds.EnvKeyValue.value,
                ds.EnvKeyValue.scope,
            )
        )
    )
    display.v(f"GraphQL query result: {res}")
    if res['projectByName'] == None:
      raise AnsibleError(
          f"Unable to get variables for {name}; please make sure the project name is correct")

    return res['projectByName']['envVariables']

class LookupModule(LookupBase):

  def run(self, terms, variables=None, **kwargs):

    ret = []

    self.set_options(var_options=variables, direct=kwargs)
    lagoon = GqlClient(
        self.get_option('lagoon_api_endpoint'),
        self.get_option('lagoon_api_token'),
        self.get_option('headers', {})
    )
    environment = self.get_option('environment')

    for term in terms:
      if environment:
        env_name = term + '-' + environment.replace('/', '-').replace('_', '-').replace('.', '-')
        display.v(f"Lagoon variable lookup environment: {env_name}")
        env_vars = get_vars_from_environment(lagoon, env_name)
      else:
        display.v(f"Lagoon variable lookup project: {term}")
        env_vars = get_vars_from_project(lagoon, term)

      if self.get_option('return_dict'):
        vars_dict = {}
        for var in env_vars:
          vars_dict[var['name']] = var
        ret.append(vars_dict)
      elif self.get_option('var_name'):
        display.v(f"Lagoon variable lookup name: {self.get_option('var_name')}")
        for var in env_vars:
          if var['name'] == self.get_option('var_name'):
            ret.append(var)
            break
      else:
        ret.append(env_vars)

    return ret
