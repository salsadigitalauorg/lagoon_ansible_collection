from . import LagoonActionBase
from ..module_utils.gqlEnvironment import Environment
from ..module_utils.gqlProject import Project
from ansible.errors import AnsibleError


class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.v("Task args: %s" % self._task.args)

        name = self._task.args.get('name')
        type = self._task.args.get('type', 'project')

        self.createClient(task_vars)

        if type == "project":
            lagoonProject = Project(self.client).byName(name, ['id', 'name'])
            if not len(lagoonProject.projects):
                raise AnsibleError("Project not found.")

            lagoonProject.withVariables()
            result['data'] = lagoonProject.projects[0]['envVariables']

        elif type == "environment":
            lagoonEnvironment = Environment(self.client).byNs(
                name, ['id', 'kubernetesNamespaceName'])
            if not len(lagoonEnvironment.environments):
                raise AnsibleError("Environment not found.")

            lagoonEnvironment.withVariables()
            result['data'] = lagoonEnvironment.environments[0]['envVariables']

        else:
            raise AnsibleError("Invalid 'type' provided.")

        return result
