from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.errors import AnsibleError
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

        display.vvv("Task args: %s" % self._task.args)

        project_name = self._task.args.get('project')
        patch_values = self._task.args.get('values')

        if not project_name:
            raise AnsibleError("Project name is required.")

        if not patch_values:
            raise AnsibleError("No value to update.")

        lagoon = ApiClient(
            task_vars.get('lagoon_api_endpoint'),
            task_vars.get('lagoon_api_token'),
            {'headers': self._task.args.get('headers', {})}
        )

        project = lagoon.project(project_name)

        update_required = False
        for key, value in patch_values.items():
            if not key in project:
                update_required = True
                break
            if str(value) != str(project[key]):
                update_required = True
                break

        if not update_required:
            result['update'] = project
            return result

        result['update'] = lagoon.project_update(project['id'], patch_values)
        result['changed'] = True
        display.v("Update: %s" % result['update'])

        return result
