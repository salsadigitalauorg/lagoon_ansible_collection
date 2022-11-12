from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient
from ansible_collections.lagoon.api.plugins.module_utils.gqlProject import Project
from ansible.plugins.lookup import LookupBase
from ansible.utils.display import Display
from ansible.errors import AnsibleError

DOCUMENTATION = """
  name: all_projects
  author: Yusuf Hasan Miyan <yusuf@salsa.digital>
  short_description: get all lagoon projects
  description:
      - This lookup returns the information for all Lagoon projects.
  options:
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
- name: retrieve all projects.
  debug: msg="{{ lookup('lagoon.api.all_projects') }}"
"""

display = Display()

class LookupModule(LookupBase):

  def run(self, _, variables=None, **kwargs):

    ret = []

    self.set_options(var_options=variables, direct=kwargs)

    lagoon = GqlClient(
        self._templar.template(self.get_option('lagoon_api_endpoint')),
        self._templar.template(self.get_option('lagoon_api_token')),
        self.get_option('headers', {})
    )

    lagoonProject = Project(lagoon, {'batch_size': 20}).all().withCluster().withEnvironments()
    ret = lagoonProject.projects

    return ret
