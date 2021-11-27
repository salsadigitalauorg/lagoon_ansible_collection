from __future__ import (absolute_import, division, print_function)
from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient
from ansible.plugins.lookup import LookupBase
from ansible.utils.display import Display
__metaclass__ = type

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
  debug: msg='{{ lookup('lagoon.api.var', 'vanilla-govcms9-beta', environment='master', var_name='REDIS_HOST') }}'
"""


display = Display()


class LookupModule(LookupBase):

  def run(self, terms, variables=None, **kwargs):

    ret = []

    self.set_options(var_options=variables, direct=kwargs)
    lagoon = ApiClient(
        self.get_option('lagoon_api_endpoint'),
        self.get_option('lagoon_api_token'),
        {'headers': self.get_option('headers', {})}
    )
    environment = self.get_option('environment')

    for term in terms:
      if environment:
        env_name = term + '-' + environment.replace('/', '-').replace('_', '-').replace('.', '-')
        display.v("Lagoon variable lookup environment: %s" % env_name)
        env_vars = lagoon.environment_get_variables(env_name)
      else:
        display.v("Lagoon variable lookup project: %s" % term)
        env_vars = lagoon.project_get_variables(term)

      if self.get_option('return_dict'):
        vars_dict = {}
        for var in env_vars:
          vars_dict[var['name']] = var
        ret.append(vars_dict)
      elif self.get_option('var_name'):
        display.v("Lagoon variable lookup name: %s" %
                  self.get_option('var_name'))
        for var in env_vars:
          if var['name'] == self.get_option('var_name'):
            ret.append(var)
            break
      else:
        ret.append(env_vars)

    return ret
