from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient
from ansible_collections.lagoon.api.plugins.module_utils.gqlEnvironment import Environment
from ansible_collections.lagoon.api.plugins.module_utils.gqlProject import Project
from ansible_collections.lagoon.api.plugins.module_utils.gqlVariable import Variable
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

        lagoon = GqlClient(
            self._templar.template(task_vars.get('lagoon_api_endpoint')),
            self._templar.template(task_vars.get('lagoon_api_token')),
            self._task.args.get('headers', {})
        )

        # Setting this option will ensure the value has been set, by making
        # additional calls to the API until it matches.
        verify_value = self._task.args.get('verify_value', False)

        if state == 'present' and (not value or not scope):
            raise AnsibleError(
                "Value and scope are required when creating a variable")

        env_vars = None
        lagoonProject = Project(lagoon)
        lagoonEnvironment = Environment(lagoon)
        lagoonVariable = Variable(lagoon)
        if (type == 'PROJECT'):
            lagoonProject.byName(type_name, ['id', 'name'])
            if not len(lagoonProject.projects):
                raise AnsibleError("Project not found.")

            lagoonProject.withVariables()
            display.v(f"project: {lagoonProject.projects[0]}")
            type_id = lagoonProject.projects[0]['id']
            env_vars = lagoonProject.projects[0]['envVariables']
            display.v("Project variables: %s" % env_vars)
        elif (type == 'ENVIRONMENT'):
            lagoonEnvironment.byNs(
                type_name, ['id', 'kubernetesNamespaceName'])
            if not len(lagoonEnvironment.environments):
                raise AnsibleError("Environment not found.")

            lagoonEnvironment.withVariables()
            display.v(f"environment: {lagoonEnvironment.environments[0]}")
            type_id = lagoonEnvironment.environments[0]['id']
            env_vars = lagoonEnvironment.environments[0]['envVariables']
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
                result['changed'] = lagoonVariable.delete(existing_var['id'])
                if not verify_value:
                    return result

                var_exists = True
                while var_exists:
                    sleep(1)
                    env_vars = lagoonProject.withVariables(
                    ).projects[0]['envVariables'] if type == 'PROJECT' else lagoonEnvironment.withVariables(
                    ).environments[0]['envVariables']
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
            lagoonVariable.delete(existing_var['id'])

        if state == 'absent':
            return result

        result['data'] = lagoonVariable.add(type, type_id, name, value, scope)
        display.v("Variable add result: %s" % result['data'])

        result['changed'] = True
        if not verify_value:
            return result

        value_matches = False
        while not value_matches:
            sleep(1)
            env_vars = lagoonProject.withVariables(
            ).projects[0]['envVariables'] if type == 'PROJECT' else lagoonEnvironment.withVariables(
            ).environments[0]['envVariables']
            for var in env_vars:
                if var['name'] != name:
                    continue
                if var['value'] != value:
                    break
                value_matches = True
                break

        return result
