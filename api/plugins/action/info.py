from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

EXAMPLES = r'''
- name: Get an environment.
  lagoon.api.info:
    resource: environment
    name: test-environment
  register: env_info
'''

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient

display = Display()


def getEnvironment(client: GqlClient, name: str) -> dict:

    res = client.execute_query(
        """
        query environmentByName($name: String!) {
            environmentByKubernetesNamespaceName(
                kubernetesNamespaceName: $name
            ) {
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
        {"name": name}
    )
    display.v(f"GraphQL query result: {res}")
    if 'errors' in res:
        raise AnsibleError("Unable to get environments.", res['errors'])
    return res['environmentByKubernetesNamespaceName']

class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        display.v("Task args: %s" % self._task.args)

        lagoon = GqlClient(
            task_vars.get('lagoon_api_endpoint'),
            task_vars.get('lagoon_api_token'),
            self._task.args.get('headers', {})
        )

        resource = self._task.args.get('resource', 'environment')
        name = self._task.args.get('name')

        if not name:
            raise AnsibleError("Environment name is required")

        display.v(f"Looking up info for {resource} {name}")
        if resource != "environment":
            result['failed'] = True
            display.v("Only 'environment' is currently supported")
            return result

        res = getEnvironment(lagoon, name)
        result['result'] = res
        if res == None:
            result['failed'] = True
            result['notFound'] = True
        return result
