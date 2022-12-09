EXAMPLES = r'''
- name: Get an environment.
  lagoon.api.info:
    resource: environment
    name: test-environment
  register: env_info
'''

from ansible.errors import AnsibleError
from ansible_collections.lagoon.api.plugins.action import LagoonActionBase
from ansible_collections.lagoon.api.plugins.module_utils.gqlEnvironment import Environment

class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.v("Task args: %s" % self._task.args)

        self.createClient(task_vars)

        resource = self._task.args.get('resource', 'environment')
        name = self._task.args.get('name')

        if not name:
            raise AnsibleError("Environment name is required")

        self._display.v(f"Looking up info for {resource} {name}")
        if resource != "environment":
            result['failed'] = True
            self._display.v("Only 'environment' is currently supported")
            return result

        lagoonEnvironment = Environment(self.client)
        if not len(lagoonEnvironment.environments):
            result['failed'] = True
            result['notFound'] = True
            return result

        lagoonEnvironment.withCluster().withProject()
        if len(lagoonEnvironment.errors):
            self._display.warning(
                f"The query partially succeeded, but the following errors were encountered:\n{ lagoonEnvironment.errors }")

        result['result'] = lagoonEnvironment.environments[0]
        return result
