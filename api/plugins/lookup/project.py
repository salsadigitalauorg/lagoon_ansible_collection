from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient
from ansible.plugins.lookup import LookupBase
from ansible.utils.display import Display
from ansible.errors import AnsibleError

DOCUMENTATION = """
  name: project
  author: Yusuf Hasan Miyan <yusuf.hasanmiyan@salsadigital.com.au>
  short_description: get a lagoon project
  description:
      - This lookup returns the information for a Lagoon project.
  options:
    _terms:
      description: The project to query (or environment if from_environment is True)
      required: True
    from_environment:
      description: Flag to lookup the project from an environment.
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
  debug: msg="{{ lookup('lagoon.api.project', 'vanilla-govcms9-beta') }}"

- name: retrieve a project's information from an environment
  debug: msg="{{ lookup('lagoon.api.project', 'vanilla-govcms9-beta-master', from_environment=true) }}"
"""

display = Display()


def get_project(client: GqlClient, name: str) -> dict:
  with client as (_, ds):
    res = client.execute_query(
        ds.Query.projectByName(name=name).select(
            ds.Project.id,
            ds.Project.name,
            ds.Project.autoIdle,
            ds.Project.branches,
            ds.Project.gitUrl,
            ds.Project.metadata,
            ds.Project.developmentEnvironmentsLimit,
            ds.Project.openshift.select(
                ds.Openshift.id,
                ds.Openshift.name,
            ),
            ds.Project.kubernetes.select(
                ds.Kubernetes.id,
                ds.Kubernetes.name,
            ),
            ds.Project.environments.select(
                ds.Environment.name,
                ds.Environment.openshift.select(
                    ds.Openshift.id,
                    ds.Openshift.name,
                ),
                ds.Environment.kubernetes.select(
                    ds.Kubernetes.id,
                    ds.Kubernetes.name,
                ),
            ),
            ds.Project.deployTargetConfigs.select(
                ds.DeployTargetConfig.id,
                ds.DeployTargetConfig.weight,
                ds.DeployTargetConfig.branches,
                ds.DeployTargetConfig.pullrequests,
                ds.DeployTargetConfig.deployTarget.select(
                    ds.Openshift.id,
                    ds.Openshift.name,
                ),
            ),
        )
    )

    display.v(f"GraphQL query result: {res}")
    if res['projectByName'] == None:
      raise AnsibleError(
          f"Unable to get details for project {name}; please make sure the project name is correct")
    return res['projectByName']


def get_project_from_environment(client: GqlClient, name: str) -> dict:
  with client as (_, ds):
    res = client.execute_query(
        ds.Query.environmentByKubernetesNamespaceName(kubernetesNamespaceName=name).select(
            ds.Environment.project.select(
                ds.Project.id,
                ds.Project.name,
                ds.Project.autoIdle,
                ds.Project.branches,
                ds.Project.gitUrl,
                ds.Project.metadata,
            )
        )
    )
    display.v(f"GraphQL query result: {res}")
    if res['environmentByKubernetesNamespaceName']['project'] == None:
      raise AnsibleError(
          f"Unable to get project details for environment {name}; please make sure the environment name is correct")
    return res['environmentByKubernetesNamespaceName']['project']

class LookupModule(LookupBase):

  def run(self, terms, variables=None, **kwargs):

    ret = []

    self.set_options(var_options=variables, direct=kwargs)

    client = GqlClient(
        self.get_option('lagoon_api_endpoint'),
        self.get_option('lagoon_api_token'),
        self.get_option('headers', {})
    )

    for term in terms:
      if self.get_option('from_environment'):
        project = get_project_from_environment(client, term)
      else:
        project = get_project(client, term)
      ret.append(project)

    return ret
