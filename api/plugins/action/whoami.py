EXAMPLES = r'''
- name: Verify the user.
  lagoon.api.whoami: {}
  register: whoami
- debug: var=whoami
'''

from ansible.errors import AnsibleError
from ansible.utils.display import Display
from ansible_collections.lagoon.api.plugins.action import LagoonActionBase
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient

display = Display()


def whoAmI(client: GqlClient) -> dict:

    res = client.execute_query(
        """
        query whoAmI {
            me {
                id
                email
                firstName
                lastName
                groups {
                    name
                    type
                }
            }
        }
"""
    )
    display.v(f"GraphQL query result: {res}")
    if res['me'] == None:
        raise AnsibleError(f"Unable to get user information.")
    return res['me']


class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.v("Task args: %s" % self._task.args)

        self.createClient(task_vars)

        result['result'] = whoAmI(self.client)
        return result
