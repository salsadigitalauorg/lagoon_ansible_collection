from . import LagoonLookupBase
from ansible.errors import AnsibleError
from gql.dsl import DSLQuery

DOCUMENTATION = """
  name: projectIdFromName
  author: Yusuf Hasan Miyan <yusuf@salsa.digital>
  short_description: Get a lagoon project's id from its name.
  description:
    - This lookup returns the id of a project in Lagoon from its name.
  options:
    _terms:
      description: The project name.
      required: True
    fail_on_not_found:
      description: Flag to control whether to fail if the project is not found.
      type: boolean
      default: False
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
    headers:
      description: HTTP request headers
      type: dictionary
      default: {}
"""

EXAMPLES = """
- name: retrieve a project id
  debug: msg="{{ lookup('lagoon.api.projectIdFromName', project_name) }}"
"""


class LookupModule(LagoonLookupBase):

  def run(self, terms, variables=None, **kwargs):

    ret = []

    self.set_options(var_options=variables, direct=kwargs)

    self.createClient()

    for term in terms:
      with self.client:
        qry = self.client.build_dynamic_query('projectByName', 'Project', {'name': term}, ['id'])
        result = self.client.execute_query_dynamic(DSLQuery(qry))
        if 'projectByName' not in result:
          raise AnsibleError(f"Error finding project '{term}': {result}")

        if result['projectByName'] == None and self.get_option('fail_on_not_found', False):
          raise AnsibleError(f"Project '{term}' not found")
        elif isinstance(result['projectByName'], dict):
          ret.append(result['projectByName']['id'])

    return ret
