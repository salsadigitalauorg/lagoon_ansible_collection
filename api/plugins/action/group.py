from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import time
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient
from ansible.module_utils._text import to_native
from ansible.errors import AnsibleError

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

        state = self._task.args.get('state')
        name = self._task.args.get('name')
        # parent = self._task.args.get('parent')

        if not name:
            raise AnsibleError("Missing required parameter 'name'.")

        group = lagoon.group(name)

        if (state == "present"):
            if group['id']:
                result['changed'] = False
                result['group'] = group
            else:
                try:
                    result['group'] = lagoon.group_add(name)
                except AnsibleError as e:
                    result['failed'] = True
                    result['msg'] = to_native(e)

        elif (state == "absent"):
            if not group['id']:
                result['changed'] = False
            else:
                result['changed'] = True
                try:
                    result['group'] = lagoon.group_remove(group['id'])
                except AnsibleError as e:
                    result['failed'] = True
                    result['msg'] = to_native(e)
        else:
            raise AnsibleError("Invalid state '%s' operation." % (state))

        return result
