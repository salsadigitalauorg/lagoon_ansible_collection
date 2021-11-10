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

        module_args = self._task.args.copy()
        module_args.update(lagoon_api_endpoint=task_vars.get('lagoon_api_endpoint'),
                           lagoon_api_token=task_vars.get('lagoon_api_token'))
        module_return = self._execute_module(module_name='lagoon.api.deploy_target_config',
                                             module_args=module_args,
                                             task_vars=task_vars)

        display.v('Module return: %s' % module_return)

        if module_return.get('failed'):
            raise AnsibleError(module_return.get('module_stderr'))

        result['changed'] = module_return['changed']
        result['result'] = module_return['result']
        return result
