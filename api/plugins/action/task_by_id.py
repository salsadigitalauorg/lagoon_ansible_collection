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

        task_id = self._task.args.get("id")

        if not task_id:
            raise AnsibleOptionsError("Task ID is required")

        fields = ['id', 'name', 'taskName', 'created', 'started', 'completed', 'service', 'status']

        # Retrieve the task.
        result["changed"] = True
        result['data'] = Task(self.client).byId(task_id, fields)
        return result
