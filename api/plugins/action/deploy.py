from ansible_collections.lagoon.api.plugins.action import LagoonActionBase
from ansible_collections.lagoon.api.plugins.module_utils.gqlEnvironment import Environment
from time import sleep


class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.v("Task args: %s" % self._task.args)

        self.createClient(task_vars)
        lagoonEnvironment = Environment(self.client)

        result['deploy_status'] = lagoonEnvironment.deployBranch(
            self._task.args.get('project'),
            self._task.args.get('branch'),
            self._task.args.get('wait', False),
            self._task.args.get('delay', 60),
            self._task.args.get('retries', 30)
        )
        self._display.v("Deploy status: %s" % result['deploy_status'])

        # This is a way to delay concurrent deployments to Lagoon.
        stagger = self._task.args.get('stagger', 0)
        if stagger > 0:
            sleep(stagger)

        return result
