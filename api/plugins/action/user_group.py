from . import LagoonActionBase
from ansible.errors import AnsibleError


class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.v("Task args: %s" % self._task.args)

        self.createClient(task_vars)

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
        res = self.client.execute_query(
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
        res = self.client.execute_query(
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
