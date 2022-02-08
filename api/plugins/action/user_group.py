from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient

display = Display()


class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        display.v("Task args: %s" % self._task.args)

        lagoon = ApiClient(
            task_vars.get('lagoon_api_endpoint'),
            task_vars.get('lagoon_api_token'),
            {'headers': self._task.args.get('headers', {})}
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

            result['result'] = lagoon.user_add_group(email, group_name, role)

        if state == 'absent':
            result = lagoon.user_remove_group(email, group_name)

            if 'error' in result:
                result['changed'] = False

        if 'changed' not in result:
            result['changed'] = True

        return result