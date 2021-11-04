from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = """
  name: metadata
  author: Yusuf Hasan Miyan <yusuf.hasanmiyan@salsadigital.com.au>
  short_description: get metadata for a project
  description:
      - This lookup returns the information for a Lagoon project's metadata.
  options:
    _terms:
      description: The metadata variables to fetch
      required: True
    project:
      description: The project name
      required: True
    default:
      description: An optional default value to set if the metadata does not exist
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
  debug: msg="{{ lookup('lagoon.api.metadata', project='vanilla-govcms8-beta', 'project-status') }}"
"""

from ansible.utils.display import Display
from ansible.plugins.lookup import LookupBase
from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient

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
    project = self.get_option('project')

    metadata = lagoon.metadata(project)
    for term in terms:
      if term in metadata:
        ret.append(metadata[term])
      elif self.has_option('default'):
        ret.append(self.get_option('default'))

    return ret
