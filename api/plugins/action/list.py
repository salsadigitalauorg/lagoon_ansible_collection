from . import LagoonActionBase
from ..module_utils.gqlEnvironment import Environment
from ..module_utils.gqlProject import Project
from ..module_utils.gqlTask import Task
from ..module_utils.gqlTaskDefinition import TaskDefinition
from ansible.errors import AnsibleError, AnsibleOptionsError


SUPPORTED_RESOURCES = ["project", "environment", "task_definition", "task"]


class ActionModule(LagoonActionBase):
    def run(self, tmp=None, task_vars=None):

        self._display.v("Task args: %s" % self._task.args)

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.v("Task args: %s" % self._task.args)

        self.createClient(task_vars)

        resource = self._task.args.get("resource")
        environment = self._task.args.get("environment")

        if self._task.args.get("batch_size") is not None:
            self._display.warning(
                "[DEPRECATION WARNING] batch_size is deprecated and has no "
                "effect; the Lagoon API is now queried one resource at a time. "
                "Remove the argument - it will be rejected in a future release."
            )

        if resource not in SUPPORTED_RESOURCES:
            result["failed"] = True
            supported_resources_str = ", ".join(SUPPORTED_RESOURCES)
            self._display.v(
                f"Resource {resource} is not currently supported - supported resources are {supported_resources_str}"
            )
            return result

        if resource == "project":
            self.fetch_projects(result)
        elif resource == "environment":
            self.fetch_environments(result)
        elif resource == "task_definition":
            self.fetch_task_definitions(result)
        elif resource == "task":
            if not environment:
                raise AnsibleOptionsError("Environment namespace is required")
            self.fetch_tasks(result, environment)

        return result

    def fetch_projects(self, result: dict):
        lagoonProject = Project(self.client).all()
        if not len(lagoonProject.projects):
            raise AnsibleError(f"Unable to get projects.")

        lagoonProject.withEnvironments()
        if len(lagoonProject.errors):
            self._display.warning(
                f"The query partially succeeded, but the following errors were encountered:\n{lagoonProject.errors}"
            )

        result["result"] = lagoonProject.projects

    def fetch_environments(self, result: dict):
        lagoonEnvironment = Environment(self.client).all()
        if not len(lagoonEnvironment.environments):
            raise AnsibleError(f"Unable to get environments.")

        lagoonEnvironment.withCluster().withProject()
        if len(lagoonEnvironment.errors):
            self._display.warning(
                f"The query partially succeeded, but the following errors were encountered:\n{lagoonEnvironment.errors}"
            )

        result["result"] = lagoonEnvironment.environments

    def fetch_task_definitions(self, result: dict):
        result["result"] = TaskDefinition(self.client).get_definitions()

    def fetch_tasks(self, result: dict, environment: str):
        # Task.get() now returns a bare list for the one environment asked for.
        # Re-wrap it in the namespace-keyed dict this module has always
        # returned, so playbooks indexing result.result[namespace] keep working.
        result["result"] = {environment: Task(self.client).get(environment)}
