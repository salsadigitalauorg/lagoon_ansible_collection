from __future__ import (absolute_import, division, print_function)
from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient
from ansible.plugins.lookup import LookupBase
from ansible.utils.display import Display
__metaclass__ = type

DOCUMENTATION = """
  name: project
  author: Yusuf Hasan Miyan <yusuf.hasanmiyan@salsadigital.com.au>
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
    endpoint:
      description: The Lagoon graphql endpoint
      type: string
      required: True
      vars:
        - name: lagoon_api_endpoint
    endpoint_token:
      description: The token for Lagoon graphql API
      type: string
      required: True
      vars:
        - name: graphql_token
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
  debug: msg="{{ lookup('lagoon.api.project', 'vanilla-govcms9-beta') }}"
"""


display = Display()


class LookupModule(LookupBase):

    def run(self, terms, variables=None, **kwargs):

        ret = []

        self.set_options(var_options=variables, direct=kwargs)

        headers = self.get_option('headers')
        headers['Content-Type'] = 'application/json'
        headers['Authorization'] = 'Bearer ' + \
            self.get_option('endpoint_token')
        self.set_option('headers', headers)

        lagoon = ApiClient(self._options)

        for term in terms:
            if self.get_option('from_environment'):
                project = lagoon.project_from_environment(term)
            else:
                project = lagoon.project(term)
            ret.append(project)

        return ret
