from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible_collections.lagoon.api.plugins.module_utils.api_client import ApiClient
from time import sleep

display = Display()


class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        display.v("Task args: %s" % self._task.args)

        name = self._task.args.get('name')
        type = self._task.args.get('type')
        type_name = self._task.args.get('type_name')
        state = self._task.args.get('state', 'present')
        value = self._task.args.get('value', None)
        scope = self._task.args.get('scope', None)
        replace_existing = self._task.args.get('replace_existing', False)
        options = self._task.args.get('options', {'headers': {}})

        lagoon = ApiClient(
            task_vars.get('lagoon_api_endpoint'),
            task_vars.get('lagoon_api_token'),
            options
        )

        # Setting this option will ensure the value has been set, by making
        # additional calls to the API until it matches.
        verify_value = self._task.args.get('verify_value', False)

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

        if env_vars == None:
            raise AnsibleError(
                "Incorrect variable type: %s. Should be PROJECT or ENVIRONMENT." % type)

        existing_var = None
        for var in env_vars:
            if var['name'] != name:
                continue
            existing_var = var

        if existing_var:
            display.v("Existing variable: %s" % existing_var)

            if state == 'absent':
                result['delete'] = lagoon.delete_variable(existing_var['id'])
                display.v("Variable delete result: %s" % result['delete'])
                result['changed'] = True
                if not verify_value:
                    return result

                var_exists = True
                while var_exists:
                    sleep(1)
                    env_vars = lagoon.project_get_variables(
                        type_name) if type == 'PROJECT' else lagoon.environment_get_variables(type_name)
                    var_found = False
                    for var in env_vars:
                        if var['name'] != name:
                            continue
                        var_found = True
                        break
                    var_exists = var_found

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
        if not verify_value:
            return result

        value_matches = False
        while not value_matches:
            sleep(1)
            env_vars = lagoon.project_get_variables(
                type_name) if type == 'PROJECT' else lagoon.environment_get_variables(type_name)
            for var in env_vars:
                if var['name'] != name:
                    continue
                if var['value'] != value:
                    break
                value_matches = True
                break

        return result
