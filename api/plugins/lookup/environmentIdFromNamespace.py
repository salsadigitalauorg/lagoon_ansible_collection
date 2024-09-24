from . import LagoonLookupBase
from ansible.errors import AnsibleError
from gql.dsl import DSLQuery

DOCUMENTATION = """
  name: environmentIdFromNamespace
  author: Yusuf Hasan Miyan <yusuf@salsa.digital>
  short_description: Get a lagoon environment's id from its namespace.
  description:
    - This lookup returns the id of an environment in Lagoon from its k8s namespace.
  options:
    _terms:
      description: The namespace.
      required: True
    fail_on_not_found:
      description: Flag to control whether to fail if the environment is not found.
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
- name: retrieve an environment id
  debug: msg="{{ lookup('lagoon.api.environmentIdFromNamespace', environment_ns) }}"
"""


class LookupModule(LagoonLookupBase):

  def run(self, terms, variables=None, **kwargs):

    ret = []

    self.set_options(var_options=variables, direct=kwargs)

    self.createClient()

    for term in terms:
      with self.client:
        qry = self.client.build_dynamic_query(
          'environmentByKubernetesNamespaceName',
          'Environment',
          {'kubernetesNamespaceName': term},
          ['id'])
        result = self.client.execute_query_dynamic(DSLQuery(qry))
        if 'environmentByKubernetesNamespaceName' not in result:
          raise AnsibleError(f"Error finding environment '{term}': {result}")

        if result['environmentByKubernetesNamespaceName'] == None and self.get_option('fail_on_not_found', False):
          raise AnsibleError(f"Environment '{term}' not found")
        elif isinstance(result['environmentByKubernetesNamespaceName'], dict):
          ret.append(result['environmentByKubernetesNamespaceName']['id'])

    return ret
