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

        headers = self._task.args.get('headers', {})
        headers['Content-Type'] = 'application/json'
        headers['Authorization'] = 'Bearer ' + \
            task_vars.get('lagoon_api_token')
        self._task.args['headers'] = headers

        lagoon = ApiClient({
            'endpoint': task_vars.get('lagoon_api_endpoint'),
            'headers': headers
        })

        project = self._task.args.get('notification')
        notification = self._task.args.get('notification')
        type = self._task.args.get('type', 'SLACK')
        notification = self._task.args.get('notification')
        state = self._task.args.get('state', 'present')

        result = {}

        if not notification:
            raise AnsibleError(
                "Notification name is required when adding a notification to a project"
            )

        if not project:
            raise AnsibleError(
                "Project is required when adding a notification"
            )

        # -- @TODO: Support other notification types.
        if type != 'SLACK':
            raise AnsibleError(
                "Invalid notification type"
            )

        if state == 'present':
            result['result'] = lagoon.addNotification(notification, project, type)
        elif state == 'absent':
            result['result'] = lagoon.removeNotification(notification, project, type)

        result['changed'] = True

        return result
