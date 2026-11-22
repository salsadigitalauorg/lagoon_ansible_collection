from ansible.plugins.lookup import LookupBase

from ..module_utils.auth import LagoonCredentials
from ..module_utils.client import LagoonClient

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
      description:
        - The token for the Lagoon graphql API.
        - Optional. When omitted, a token is fetched over SSH on first use,
          using the lagoon_ssh_* options below, or the machine's own SSH
          configuration and agent.
      type: string
      vars:
        - name: lagoon_api_token
    lagoon_ssh_private_key:
      description:
        - SSH private key content used to fetch an API token.
        - Written to a private temporary file for the duration of the call
          and removed afterwards.
      type: string
      vars:
        - name: lagoon_ssh_private_key
    lagoon_ssh_private_key_file:
      description:
        - Path to an SSH private key used to fetch an API token.
      type: string
      vars:
        - name: lagoon_ssh_private_key_file
    lagoon_ssh_host:
      description: The Lagoon SSH host used to fetch an API token.
      type: string
      vars:
        - name: lagoon_ssh_host
    lagoon_ssh_port:
      description: The Lagoon SSH port used to fetch an API token.
      type: string
      vars:
        - name: lagoon_ssh_port
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
        self.set_options(var_options=variables, direct=kwargs)

        token = self.get_option("lagoon_api_token")
        lagoon = LagoonClient(
            self._templar.template(self.get_option("lagoon_api_endpoint")).strip(),
            LagoonCredentials(
                token=self._templar.template(token).strip() if token else None,
                ssh_private_key=self.get_option("lagoon_ssh_private_key"),
                ssh_private_key_file=self.get_option("lagoon_ssh_private_key_file"),
                ssh_host=self.get_option("lagoon_ssh_host"),
                ssh_port=self.get_option("lagoon_ssh_port"),
            ),
            self.get_option("headers", {}),
        )

        default = self.get_option("default")
        return [lagoon.getGroup(term) or default for term in terms]
