import json
from ansible_collections.lagoon.api.plugins.module_utils.gqlProject import Project
from ansible_collections.lagoon.api.plugins.lookup import LagoonLookupBase
from ansible.errors import AnsibleError

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
- name: retrieve a project's metadata
  debug: msg="{{ lookup('lagoon.api.metadata', project=project_name) }}"

- name: retrieve a project's status
  debug: msg="{{ lookup('lagoon.api.metadata', 'project-status', project=project_name) }}"
"""

class LookupModule(LagoonLookupBase):

  def run(self, terms, variables=None, **kwargs):

    ret = []

    self.set_options(var_options=variables, direct=kwargs)

    self.createClient()

    project = self.get_option('project')

    lagoonProject = Project(self.client).byName(project, ['metadata'])
    if not len(lagoonProject.projects):
        raise AnsibleError(f"Unable to get metadata for project {project}; please make sure the project name is correct")

    try:
      metadata = lagoonProject.projects[0]['metadata']
    except (IndexError, KeyError, ValueError) as e:
      raise AnsibleError(f"Unable to get metadata for project {project}; please make sure the project name is correct")

    if type(metadata) is str:
      metadata = json.loads(metadata)

    self._display.v(f"metadata: {metadata}")

    if not len(terms):
      for k in metadata:
        ret.append({k: metadata[k]})

    for term in terms:
      if term in metadata:
        ret.append({term: metadata[term]})
      elif self.has_option('default'):
        ret.append({term: self.get_option('default')})

    return ret
