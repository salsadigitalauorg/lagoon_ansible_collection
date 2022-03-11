from __future__ import (absolute_import, division, print_function)
from operator import truediv
__metaclass__ = type

import time
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient

display = Display()


class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        display.v("Task args: %s" % self._task.args)

        lagoon = ApiClient(
            task_vars.get('lagoon_api_endpoint'),
            task_vars.get('lagoon_api_token'),
            {'headers': self._task.args.get('headers', {})}
        )

        type = task_vars.get('type', 'project')

        if type != "project":
            result['failed'] = True
            display.v("Only 'project' is supported")
        else:
            result['result'] = lagoon.projects_all()

        return result
