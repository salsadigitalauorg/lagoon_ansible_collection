from __future__ import (absolute_import, division, print_function)
# __metaclass__ = type

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient

display = Display()


class ActionModule(ActionBase):
    ''' Perform copmarisons on dictionary objects '''

    def run(self, tmp=None, task_vars=None):
        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)

        del tmp  # tmp no longer has any effect

        headers = self._task.args.get('headers', {})
        headers['Content-Type'] = 'application/json'
        headers['Authorization'] = 'Bearer ' + \
            task_vars.get('lagoon_api_token')

        self._task.args['headers'] = headers

        lagoon = ApiClient({
            'endpoint': task_vars.get('lagoon_api_endpoint'),
            'headers': headers
        })

        state = self._task.args.get('state', 'present')
        data = self._task.args.get('data', None)
        project_id = self._task.args.get('project_id', None)

        result = {}
        result['result'] = []
        result['invalid'] = []

        if state == 'present':
            for item in data:
                if 'key' not in item or 'value' not in item:
                    result['invalid'] = item
                    continue
                result['result'].append(lagoon.update_metadata(
                    project_id, item['key'], item['value']))

        elif state == 'absent':
            for item in data:
                if 'key' not in item:
                    result['invalid'] = item
                    continue
                result['result'].append(
                    lagoon.remove_metadata(project_id, item['key']))

        if len(result['result']) > 0:
            result['changed'] = True

        if len(result['invalid']) > 0:
            result['failed'] = True

        return result
