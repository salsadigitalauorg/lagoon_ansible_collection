from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient
from ansible.plugins.lookup import LookupBase

DOCUMENTATION = """
  name: group
  author: Yusuf Hasan Miyan <yusuf.hasanmiyan@salsadigital.com.au>
  short_description: get group for a project
  description:
      - This lookup returns the information for a Lagoon project's group.
  options:
    _terms:
      description: The group variables to fetch
      required: True
    default:
      description: An optional default value to set if the group does not exist
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
- name: retrieve a groups information
  debug: msg="{{ lookup('lagoon.api.group', 'my-group-name') }}"
"""


class LookupModule(LookupBase):

  def run(self, terms, variables=None, **kwargs):

    ret = []

    self.set_options(var_options=variables, direct=kwargs)
    lagoon = ApiClient(
        self._templar.template(self.get_option('lagoon_api_endpoint')),
        self._templar.template(self.get_option('lagoon_api_token')),
        {'headers': self.get_option('headers', {})}
    )

    for term in terms:
        ret.append(lagoon.group(term))

    return ret
