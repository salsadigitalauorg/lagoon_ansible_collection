from ansible.errors import AnsibleError
from ansible_collections.lagoon.api.plugins.module_utils.gqlEnvironment import Environment
from ansible_collections.lagoon.api.plugins.lookup import LagoonLookupBase

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
  debug: msg="{{ lookup('lagoon.api.environment', environment_ns) }}"
"""


class LookupModule(LagoonLookupBase):

    def run(self, terms, variables=None, **kwargs):

        ret = []

        self.set_options(var_options=variables, direct=kwargs)

        self.createClient()

        lagoonEnvironment = Environment(self.client)

        for term in terms:
            lagoonEnvironment.byNs(term)
            if not len(lagoonEnvironment.environments):
                if len(lagoonEnvironment.errors):
                    raise AnsibleError(
                        f"Unable to fetch environment {term}; encountered the following errors: {lagoonEnvironment.errors}")
                return ret

            lagoonEnvironment.withCluster().withVariables()
            lagoonEnvironment.withProject().withDeployments()
            if len(lagoonEnvironment.errors):
                self._display.warning(
                    f"The query partially succeeded, but the following errors were encountered:\n{ lagoonEnvironment.errors }")
            ret.extend(lagoonEnvironment.environments)

        return ret
