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

        environment_name = self._task.args.get('environment')
        environment_id = self._task.args.get('environment_id')
        patch_values = self._task.args.get('values')

        if not environment_name and not environment_id:
            raise AnsibleError("Environment name or id is required.")

        if not patch_values:
            raise AnsibleError("No value to update.")

        lagoon = ApiClient(
            task_vars.get('lagoon_api_endpoint'),
            task_vars.get('lagoon_api_token'),
            {'headers': self._task.args.get('headers', {})}
        )

        if environment_name:
            environment = lagoon.environment(environment_name)
        else:
            environment = lagoon.environment_by_id(environment_name)

        update_required = False
        for key, value in patch_values.items():
            if not key in environment:
                update_required = True
                break
            if key in ['openshift', 'kubernetes']:
                if str(value) != str(environment[key]['id']):
                    update_required = True
                    break
            elif str(value) != str(environment[key]):
                update_required = True
                break

        if not update_required:
            result['update'] = environment
            return result

        result['update'] = lagoon.environment_update(environment['id'], patch_values)
        result['changed'] = True
        display.v("Update: %s" % result['update'])

        return result
