from . import LagoonActionBase
from ..module_utils.gqlEnvironment import Environment
from ..module_utils.gqlProject import Project
from ..module_utils.gqlTask import Task
from ansible.errors import AnsibleError


SUPPORTED_RESOURCES = [
    "project",
    "environment",
    "task",
]


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
        id = self._task.args.get('id')

        if not name and not resource in ['task']:
            raise AnsibleError("Resource name is required")
        elif not id and resource in ['task']:
            raise AnsibleError("Resource id is required")

        if resource not in SUPPORTED_RESOURCES:
            result['failed'] = True
            supported_resources_str = ", ".join(SUPPORTED_RESOURCES)
            self._display.v(
                f"Resource {resource} is not currently supported - supported resources are {supported_resources_str}")
            return result

        self._display.v(f"Looking up info for {resource} {name if name else id}")

        if resource == "project":
            self.fetch_project(name, result)
        elif resource == "environment":
            self.fetch_environment(name, result)
        elif resource == "task":
            self.fetch_task(id, result)

        return result

    def fetch_project(self, name: str, result: dict):
        lagoonProject = Project(self.client).byName(name)
        if not len(lagoonProject.projects):
            result['failed'] = True
            result['notFound'] = True
            return result

        lagoonProject.withEnvironments(batch_size=50)
        if len(lagoonProject.errors):
            self._display.warning(
                f"The query partially succeeded, but the following errors were encountered:\n{ lagoonProject.errors }")

        result['result'] = lagoonProject.projects[0]

    def fetch_environment(self, name: str, result: dict):
        lagoonEnvironment = Environment(self.client).byNs(name)
        if not len(lagoonEnvironment.environments):
            result['failed'] = True
            result['notFound'] = True
            return result

        lagoonEnvironment.withCluster().withProject()
        if len(lagoonEnvironment.errors):
            self._display.warning(
                f"The query partially succeeded, but the following errors were encountered:\n{ lagoonEnvironment.errors }")

        result['result'] = lagoonEnvironment.environments[0]

    def fetch_task(self, id: int, result: dict):
        result['result'] = Task(self.client).byId(id)
