from . import LagoonActionBase
from ..module_utils.gqlEnvironment import Environment
from ..module_utils.gqlProject import Project
from ..module_utils.gqlVariable import Variable
from ansible.errors import AnsibleError
from time import sleep


class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.v("Task args: %s" % self._task.args)

        name = self._task.args.get('name')
        type = self._task.args.get('type')
        type_name = self._task.args.get('type_name')
        state = self._task.args.get('state', 'present')
        value = self._task.args.get('value', None)
        scope = self._task.args.get('scope', None)
        replace_existing = self._task.args.get('replace_existing', False)

        self.createClient(task_vars)

        # Setting this option will ensure the value has been set, by making
        # additional calls to the API until it matches.
        verify_value = self._task.args.get('verify_value', False)

        if state == 'present' and (value is None or not scope):
            raise AnsibleError(
                "Value and scope are required when creating a variable")

        env_vars = None
        lagoonProject = Project(self.client)
        lagoonEnvironment = Environment(self.client)
        lagoonVariable = Variable(self.client)
        if (type == 'PROJECT'):
            lagoonProject.byName(type_name, ['id', 'name'])
            if not len(lagoonProject.projects):
                raise AnsibleError("Project not found.")

            lagoonProject.withVariables()
            self._display.v(f"project: {lagoonProject.projects[0]}")
            type_id = lagoonProject.projects[0]['id']
            env_vars = lagoonProject.projects[0]['envVariables']
            self._display.v("Project variables: %s" % env_vars)
        elif (type == 'ENVIRONMENT'):
            lagoonEnvironment.byNs(
                type_name, ['id', 'kubernetesNamespaceName'])
            if not len(lagoonEnvironment.environments):
                raise AnsibleError("Environment not found.")

            lagoonEnvironment.withVariables()
            self._display.v(f"environment: {lagoonEnvironment.environments[0]}")
            type_id = lagoonEnvironment.environments[0]['id']
            env_vars = lagoonEnvironment.environments[0]['envVariables']
            self._display.v("Environment variables: %s" % env_vars)

        if env_vars == None:
            raise AnsibleError(
                "Incorrect variable type: %s. Should be PROJECT or ENVIRONMENT." % type)

        existing_var = None
        for var in env_vars:
            if var['name'] != name:
                continue
            existing_var = var

        if existing_var:
            self._display.v("Existing variable: %s" % existing_var)

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
        self._display.v("Variable add result: %s" % result['data'])

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
