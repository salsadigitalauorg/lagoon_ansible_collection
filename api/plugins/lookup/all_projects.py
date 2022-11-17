from ansible.errors import AnsibleError
from ansible_collections.lagoon.api.plugins.lookup import LagoonLookupBase
from ansible_collections.lagoon.api.plugins.module_utils.gqlProject import Project

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


class LookupModule(LagoonLookupBase):

  def run(self, _, variables=None, **kwargs):

    ret = []

    self.set_options(var_options=variables, direct=kwargs)

    self.createClient()

    lagoonProject = Project(self.client, {'batch_size': 20}).all()
    if not len(lagoonProject.projects):
      if len(lagoonProject.errors):
        raise AnsibleError(
            f"Unable to fetch projects; encountered the following errors: {lagoonProject.errors}")
      return ret

    lagoonProject.withCluster().withEnvironments()
    if len(lagoonProject.errors):
      self._display.warning(
          f"The query partially succeeded, but the following errors were encountered:\n{ lagoonProject.errors }")
    ret = lagoonProject.projects

    return ret
