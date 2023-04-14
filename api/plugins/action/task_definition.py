from . import LagoonActionBase
from ..module_utils.gqlEnvironment import Environment
from ..module_utils.gqlProject import Project
from ..module_utils.gqlTaskDefinition import TaskDefinition
from ansible.errors import AnsibleError, AnsibleOptionsError


class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp

        self._display.v("Task args: %s" % self._task.args)

        self.createClient(task_vars)

        task_type = self._task.args.get("task_type")
        permission = self._task.args.get("permission")
        project = self._task.args.get("project")
        environment = self._task.args.get("environment")
        name = self._task.args.get("name")
        description = self._task.args.get("description")
        service = self._task.args.get("service")
        image = self._task.args.get("image")
        command = self._task.args.get("command")
        arguments = self._task.args.get("arguments")
        state = self._task.args.get("state")

        project_id = None
        environment_id = None

        if state == "absent" and not project:
            raise AnsibleOptionsError("Project name is required when deleting")

        if environment:
            self._display.warning(
                "Environment-specific tasks are not currently supported; "+
                "skipping environment name.")
            environment = None

        lagoonTaskDefinition = TaskDefinition(self.client)

        existing_task_definitions = {}
        # Fetch all task definitions.
        if not project and not environment:
            existing_task_definitions = lagoonTaskDefinition.get_definitions()
        # Fetch definitions only for the specific project's environment.
        elif project and environment:
            project_id = self.get_project_id(project)
            environment_id = self.getEnvironmentIdFromNs(
                self.sanitiseName(f"{project}-{environment}"))
            existing_task_definitions = lagoonTaskDefinition.get_definitions(
                project_id=project_id, environment_id=environment_id)
        elif project:
            project_id = self.get_project_id(project)
            existing_task_definitions = lagoonTaskDefinition.get_definitions(
                project_id=project_id)
        else:
            environment_id = self.getEnvironmentIdFromNs(
                self.sanitiseName(f"{project}-{environment}"))
            existing_task_definitions = lagoonTaskDefinition.get_definitions(
                environment_ids=environment_id)

        found_def = False
        for existing_task_def in existing_task_definitions:
            if existing_task_def["name"] == name:
                found_def = existing_task_def

        if not found_def and state == "absent":
            result["changed"] = False
        elif found_def and state == "absent":
            result["changed"] = True
            result["result"] = lagoonTaskDefinition.delete(found_def["id"])
        # Update existing if required.
        elif found_def:
            if self.def_has_changed(
                found_def,
                {
                    "type": task_type,
                    "permission": permission,
                    "description": description,
                    "service": service,
                    "command": command,
                    "image": image,
                    "arguments": arguments,
                }
            ):
                result["changed"] = True
                result["result"] = lagoonTaskDefinition.update(
                    found_def["id"],
                    task_type,
                    permission,
                    project_id if project_id else None,
                    environment_id if environment_id else None,
                    name,
                    description,
                    service,
                    image,
                    command,
                    arguments
                )
            else:
                result["changed"] = False
        # Create new.
        else:
            result["changed"] = True
            result["result"] = lagoonTaskDefinition.add(
                task_type,
                permission,
                project_id if project_id else None,
                environment_id if environment_id else None,
                name,
                description,
                service,
                image,
                command,
                arguments
            )

        return result

    def get_project_id(self, name: str):
        lagoonProject = Project(self.client).byName(name, ["id"])
        if len(lagoonProject.errors):
            raise AnsibleError("Error fetching project: %s" % lagoonProject.errors)
        if not len(lagoonProject.projects):
            raise AnsibleError(f"Project '{name}' not found")
        return lagoonProject.projects[0]["id"]

    def def_has_changed(self, current: dict, desired: dict) -> bool:
        compare_fields = [
            "type",
            "permission",
            "description",
            "service",
            "arguments",
        ]
        for field in compare_fields:
            if field == "arguments":
                if self.args_have_changed(current["advancedTaskDefinitionArguments"], desired["arguments"]):
                    return True
                continue
            if current[field] != desired[field]:
                return True

        if current["type"] == "COMMAND" and current["command"] != desired["command"]:
            return True

        if current["type"] == "IMAGE" and current["image"] != desired["image"]:
            return True

        return False

    def args_have_changed(self, current: list, desired: list) -> bool:
        if not len(current) and not len(desired):
            return False

        if len(current) != len(desired):
            return True

        compare_fields = [
            "name",
            "displayName",
            "type"
        ]

        for i in range(len(current)):
            for field in compare_fields:
                if current[i][field] != desired[i][field]:
                    return True

        return False
