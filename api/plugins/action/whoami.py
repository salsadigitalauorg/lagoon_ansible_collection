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

        res = self.client.execute_query(
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
            }""")
        self._display.v(f"GraphQL query result: {res}")
        if res['me'] == None:
            raise AnsibleError(f"Unable to get user information.")
        result['result'] = res['me']
        return result
