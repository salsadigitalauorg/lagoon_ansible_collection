from ..module_utils.api_client import ApiClient
from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.v("Task args: %s" % self._task.args)

        lagoon = ApiClient(
            task_vars.get('lagoon_api_endpoint'),
            task_vars.get('lagoon_api_token'),
            {'headers': self._task.args.get('headers', {})}
        )

        project = self._task.args.get('project')
        notification = self._task.args.get('notification')
        type = self._task.args.get('type', 'SLACK')

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
            api_result = lagoon.add_project_notification(
                project, notification, type)

            if 'errors' in api_result:
                message = api_result['errors'][0]['message']

                if 'Duplicate' in message:
                    result['changed'] = False
                    return result

                raise AnsibleError(
                    "Unable to add notification %s" % (
                        api_result['errors'][0]['message'])
                )

        elif state == 'absent':
            lagoon.remove_project_notification(project, notification, type)

        result['changed'] = True

        return result
