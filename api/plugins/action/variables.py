from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient
from ansible_collections.lagoon.api.plugins.module_utils.gqlEnvironment import Environment
from ansible_collections.lagoon.api.plugins.module_utils.gqlProject import Project
from ansible.errors import AnsibleError

display = Display()


class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        display.v("Task args: %s" % self._task.args)

        name = self._task.args.get('name')
        type = self._task.args.get('type', 'project')
        options = self._task.args.get('options', {})
        if not 'headers' in options:
            options['headers'] = {}

        lagoon = GqlClient(
            self._templar.template(task_vars.get('lagoon_api_endpoint')),
            self._templar.template(task_vars.get('lagoon_api_token')),
            self._task.args.get('headers', {})
        )

        if type == "project":
            lagoonProject = Project(lagoon).byName(name, ['id', 'name'])
            if not len(lagoonProject.projects):
                raise AnsibleError("Project not found.")

            lagoonProject.withVariables()
            result['data'] = lagoonProject.projects[0]['envVariables']

        elif type == "environment":
            lagoonEnvironment = Environment(lagoon).byNs(
                name, ['id', 'kubernetesNamespaceName'])
            if not len(lagoonEnvironment.environments):
                raise AnsibleError("Environment not found.")

            lagoonEnvironment.withVariables()
            result['data'] = lagoonEnvironment.environments[0]['envVariables']

        else:
            raise AnsibleError("Invalid 'type' provided.")

        return result
