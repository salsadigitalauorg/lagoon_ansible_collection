from . import LagoonActionBase
from ..module_utils.gqlTask import Task
from ..module_utils.gqlTaskDefinition import TaskDefinition
from ansible.errors import AnsibleError, AnsibleOptionsError


class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self.createClient(task_vars)

        environment_ns = self._task.args.get("environment")
        environment_id = self._task.args.get("environment_id")
        task_name = self._task.args.get("name")
        task_arguments = self._task.args.get("arguments")

        if not task_name:
            raise AnsibleOptionsError("Task name is required")

        if not environment_id and not environment_ns:
            raise AnsibleOptionsError("One of environment namespace or id is required")

        # Get the environment id.
        if not environment_id:
            environment_id = self.getEnvironmentIdFromNs(environment_ns)

        # Get the list of available tasks for the environment.
        lagoonTaskDefinition = TaskDefinition(self.client)
        task_definitions = lagoonTaskDefinition.get_definitions(
            environment_id=environment_id,
            fields=['id', 'name'])

        # Get the task definition id.
        task_id = -1
        for td in task_definitions:
            if td['name'] == task_name:
                task_id = td['id']
                break
        if task_id == -1:
            raise AnsibleError(f"Task '{task_name}' not found")

        # Invoke the task.
        result["changed"] = True
        result['task_id'] = Task(self.client).invoke(environment_id, task_id, task_arguments)
        return result
