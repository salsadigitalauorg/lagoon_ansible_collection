EXAMPLES = r'''
- name: Add Lagoon deploy target configs.
  lagoon.api.list:
    type: project
  register: projects
'''

from ansible.errors import AnsibleError
from ansible_collections.lagoon.api.plugins.action import LagoonActionBase
from ansible_collections.lagoon.api.plugins.module_utils.gqlProject import Project

class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.v("Task args: %s" % self._task.args)

        self.createClient(task_vars)

        resource = task_vars.get('type', 'project')

        if resource != "project":
            result['failed'] = True
            self._display.v("Only 'project' is supported")
        else:
            lagoonProject = Project(self.client, {'batch_size': 20}).all(
            ).withEnvironments()
            if len(lagoonProject.errors):
                if not len(lagoonProject.projects):
                    raise AnsibleError(f"Unable to get projects.")
                self._display.warning(
                    f"The query partially succeeded, but the following errors were encountered:\n{ lagoonProject.errors }")
            result['result'] = lagoonProject.projects

        return result
