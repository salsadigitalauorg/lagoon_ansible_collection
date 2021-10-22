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

        display.v("Task args: %s" % self._task.args)

        headers = self._task.args.get('headers', {})
        headers['Content-Type'] = 'application/json'
        headers['Authorization'] = 'Bearer ' + \
            task_vars.get('lagoon_api_token')
        self._task.args['headers'] = headers

        lagoon = ApiClient({
            'endpoint': task_vars.get('lagoon_api_endpoint'),
            'headers': headers
        })

        type = self._task.args.get('type')
        type_name = self._task.args.get('type_name')
        name = self._task.args.get('name')
        state = self._task.args.get('state', 'present')
        value = self._task.args.get('value', None)
        scope = self._task.args.get('scope', None)
        replace_existing = self._task.args.get('replace_existing', False)

        if state == 'present' and (not value or not scope):
            raise AnsibleError(
                "Value and scope are required when creating a variable")

        env_vars = None
        if (type == 'PROJECT'):
            type_id = lagoon.project(type_name)['id']
            env_vars = lagoon.project_get_variables(type_name)
            display.v("Project variables: %s" % env_vars)
        elif (type == 'ENVIRONMENT'):
            type_id = lagoon.environment(type_name)['id']
            env_vars = lagoon.environment_get_variables(type_name)
            display.v("Environment variables: %s" % env_vars)

        if not env_vars:
            raise AnsibleError(
                "Incorrect variable type: %s. Should be PROJECT or ENVIRONMENT." % type)

        existing_var = None
        for var in env_vars:
            if var['name'] != self._task.args.get('name'):
                continue
            existing_var = var

        if existing_var:
            display.v("Existing variable: %s" % existing_var)

            if state == 'absent':
                result['delete'] = lagoon.delete_variable(existing_var['id'])
                display.v("Variable delete result: %s" % result['delete'])
                result['changed'] = True
                return result

            if not replace_existing:
                result['id'] = existing_var['id']
                return result

            # No change if it's all the same.
            if (existing_var['name'] == name and
                existing_var['value'] == value and
                    existing_var['scope'].lower() == scope.lower()):
                result['id'] = existing_var['id']
                return result

            # Delete before recreating.
            lagoon.delete_variable(existing_var['id'])

        if state == 'absent':
            return result

        result['id'] = lagoon.add_variable(type, type_id, name, value, scope)
        display.v("Variable add result: %s" % result['id'])
        result['changed'] = True
        return result
