from . import LagoonActionBase
from ..module_utils.gqlEnvironment import Environment
from ansible.errors import AnsibleError


class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.v("Task args: %s" % self._task.args)

        project_name = self._task.args.get('project')
        environment_name = self._task.args.get('branch')

        if not project_name or not environment_name:
            raise AnsibleError(
                "Project and environment name are required when deleting an environment")

        self.createClient(task_vars)
        lagoonEnvironment = Environment(self.client)

        result['status'] = lagoonEnvironment.delete(
            project_name,
            environment_name,
        )

        return result
