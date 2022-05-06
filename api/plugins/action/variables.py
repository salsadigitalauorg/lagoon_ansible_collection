from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient
from ansible.module_utils._text import to_native
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

        lagoon = ApiClient(
            task_vars.get('lagoon_api_endpoint'),
            task_vars.get('lagoon_api_token'),
            options
        )

        if type == "project":
            result['data'] = lagoon.project_get_variables(name)

        elif type == "environment":
            result['data'] = lagoon.environment_get_variables(name)

        else:
            raise AnsibleError("Invalid 'type' provided.")

        return result
