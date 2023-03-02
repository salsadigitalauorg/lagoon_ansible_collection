from ..module_utils.api_client import ApiClient
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

        result['deploy_status'] = lagoon.project_check_deploy_status(
            self._task.args.get('project'),
            self._task.args.get('branch'),
            self._task.args.get('wait', False),
            self._task.args.get('delay', 60),
            self._task.args.get('retries', 30)
        )
        self._display.v("Deploy status: %s" % result['deploy_status'])

        return result
