from ansible_collections.lagoon.api.plugins.lookup import LagoonLookupBase
from ansible_collections.lagoon.api.plugins.module_utils.gqlEnvironment import Environment
from ansible.errors import AnsibleError

DOCUMENTATION = """
  name: all_environments
  author: Yusuf Hasan Miyan <yusuf@salsa.digital>
  short_description: get all lagoon environments
  description:
      - This lookup returns the information for all Lagoon environments.
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
- name: retrieve all environments.
  debug: msg="{{ lookup('lagoon.api.all_environments') }}"
"""


class LookupModule(LagoonLookupBase):

  def run(self, _, variables=None, **kwargs):

    ret = []

    self.set_options(var_options=variables, direct=kwargs)

    self.createClient()

    lagoonEnvironment = Environment(self.client).all()
    if not len(lagoonEnvironment.environments):
      if len(lagoonEnvironment.errors):
        raise AnsibleError(
            f"Unable to fetch environments; encountered the following errors: {lagoonEnvironment.errors}")
      return ret

    lagoonEnvironment.withCluster(batch_size=50).withVariables(batch_size=50)
    if len(lagoonEnvironment.errors):
      self._display.warning(
          f"The query partially succeeded, but the following errors were encountered:\n{ lagoonEnvironment.errors }")
    ret = lagoonEnvironment.environments

    return ret
