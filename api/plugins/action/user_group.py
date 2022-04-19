from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

EXAMPLES = r'''
- name: Add user to group.
  lagoon.api.user_group:
    email: user@example.com
    group: test-group
    role: GUEST
  register: group_add
- debug: var=group_add
'''

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient


class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.v("Task args: %s" % self._task.args)

        self.lagoon = GqlClient(
            task_vars.get('lagoon_api_endpoint'),
            task_vars.get('lagoon_api_token'),
            self._task.args.get('headers', {})
        )

        email = self._task.args.get('email')
        group_name = self._task.args.get('group')
        role = self._task.args.get('role')

        state = self._task.args.get('state', 'present')

        result = {}

        if group_name is None:
            raise AnsibleError("Missing required parameter 'group'")

        if state == 'present':

            if role is None:
                raise AnsibleError("Missing required parameter 'role'")

            result['result'] = self.user_add_group(email, group_name, role)

        if state == 'absent':
            result = self.user_remove_group(email, group_name)

            if 'error' in result:
                result['changed'] = False

        if 'changed' not in result:
            result['changed'] = True

        return result

    def user_add_group(self, email: str, group: str, role: str) -> dict:
        res = self.lagoon.execute_query(
            """
            mutation group(
                $email: String!
                $group: String!
                $role: GroupRole!
            ) {
                addUserToGroup(input: {
                    user: { email: $email }
                    group: { name: $group }
                    role: $role
                }) {
                    id
                }
            }""",
            {
                "email": email,
                "group": group,
                "role": role,
            }
        )
        self._display.v(f"GraphQL query result: {res}")
        return res['addUserToGroup']['id']

    def user_remove_group(self, email: str, group: str):
        res = self.lagoon.execute_query(
            """
            mutation group(
                $email: String!
                $group: String!
            ) {
                removeUserFromGroup(input: {
                    user: { email: $email }
                    group: { name: $group }
                }) {
                    id
                }
            }""",
            {
                "email": email,
                "group": group,
            }
        )
        self._display.v(f"GraphQL query result: {res}")
        return res['removeUserFromGroup']['id']
