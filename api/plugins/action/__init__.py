import re

from ..module_utils.gql import GqlClient
from ..module_utils.gqlEnvironment import Environment
from ..module_utils.gqlProject import Project
from ansible.plugins.action import ActionBase
from ansible.errors import AnsibleError


class LagoonActionBase(ActionBase):

    def createClient(self, task_vars):
        self.client = GqlClient(
            self._templar.template(task_vars.get('lagoon_api_endpoint')).strip(),
            self._templar.template(task_vars.get('lagoon_api_token')).strip(),
            self._task.args.get('headers', {}),
            self._display,
        )

    def sanitiseName(self, name: str) -> str:
        return re.sub(r'[\W_-]+', '-', name)

    def getProjectIdFromName(self, name: str) -> int:
        lagoonProject = Project(self.client).byName(name, ["id"])
        if len(lagoonProject.errors):
            raise AnsibleError("Error fetching project: %s" %
                               lagoonProject.errors)
        if not len(lagoonProject.projects):
            raise AnsibleError(f"Project '{name}' not found")
        return lagoonProject.projects[0]["id"]

    def getEnvironmentIdFromNs(self, ns: str) -> int:
        lagoonEnvironment = Environment(self.client).byNs(ns, ["id"])
        if len(lagoonEnvironment.errors):
            raise AnsibleError("Error fetching environment: %s" %
                                lagoonEnvironment.errors)
        if not len(lagoonEnvironment.environments):
            raise AnsibleError(f"Environment '{ns}' not found")
        return lagoonEnvironment.environments[0]["id"]
