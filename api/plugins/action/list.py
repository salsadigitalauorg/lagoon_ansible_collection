from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

EXAMPLES = r'''
- name: Add Lagoon deploy target configs.
  lagoon.api.list:
    type: project
  register: projects
'''

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient

display = Display()


def getProjects(client: GqlClient) -> dict:

    res = client.execute_query(
        """
        query GetProjects {
            allProjects {
                id
                name
                gitUrl
                branches
                autoIdle
                pullrequests
                developmentEnvironmentsLimit
                activeSystemsTask
                activeSystemsMisc
                activeSystemsDeploy
                activeSystemsRemove
                productionEnvironment
                metadata
                environments { id name environmentType autoIdle updated created route }
            }
        }
"""
    )
    display.v(f"GraphQL query result: {res}")
    if res['allProjects'] == None:
        raise AnsibleError(f"Unable to get projects.")
    return res['allProjects']

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

        type = task_vars.get('type', 'project')

        if type != "project":
            result['failed'] = True
            display.v("Only 'project' is supported")
        else:
            result['result'] = getProjects(lagoon)

        return result
