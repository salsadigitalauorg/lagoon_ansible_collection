from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = """
  name: environment
  author: Yusuf Hasan Miyan <yusuf.hasanmiyan@salsadigital.com.au>
  short_description: get a lagoon environment
  description:
      - This lookup returns the information for a Lagoon environment.
  options:
    _terms:
      description: The project to query (or environment if from_environment is True)
      required: True
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
- name: retrieve a environment's information
  debug: msg="{{ lookup('lagoon.api.environment', 'vanilla-govcms9-beta-master') }}"
"""

from ansible.errors import AnsibleError
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient
from ansible.plugins.lookup import LookupBase
from ansible.utils.display import Display

display = Display()

def get_environment(client: GqlClient, env_name: str) -> dict:
    res = client.execute_query(
        """
        query env($env_name: String!) {
            environmentByKubernetesNamespaceName(kubernetesNamespaceName: $env_name) {
                id
                name
                autoIdle
                route
                routes
                deployments {
                    name
                    status
                    started
                    completed
                }
                project {
                    id
                }
                openshift {
                    id
                    name
                }
                kubernetes {
                    id
                    name
                }
            }
        }""",
        {
            "env_name": env_name
        }
    )
    display.v(f"GraphQL query result: {res}")

    if 'errors' in res:
        raise AnsibleError("Unable to get environments.", res['errors'])
    return res['environmentByKubernetesNamespaceName']

class LookupModule(LookupBase):

    def run(self, terms, variables=None, **kwargs):

        ret = []

        self.set_options(var_options=variables, direct=kwargs)

        lagoon = GqlClient(
            self.get_option('lagoon_api_endpoint'),
            self.get_option('lagoon_api_token'),
            self.get_option('headers', {})
        )

        for term in terms:
            ret.append(get_environment(lagoon, term))

        return ret
