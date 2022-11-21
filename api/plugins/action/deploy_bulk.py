import json
from ansible_collections.lagoon.api.plugins.action import LagoonActionBase
from ansible_collections.lagoon.api.plugins.module_utils.gqlEnvironment import Environment

EXAMPLES = r'''
- name: Bulk deployment trigger by environment id.
  lagoon.api.deploy_bulk:
    name: Trigger by Ansible
    environments:
      - id: environment_id
    build_vars:
      - name: build_var_name
        value: build_var_value

- name: Bulk deployment trigger by project & env name.
  lagoon.api.deploy_bulk:
    name: Trigger by Ansible
    environments:
      - name: environment_name
        project:
          name: project_name
    build_vars:
      - name: build_var_name
        value: build_var_value
'''


def is_variable_type(i):
    if type(i) is not dict:
        return False, 'Expected "dict" type'
    keys = i.keys()

    if 'name' not in keys and 'value' not in keys:
        return False, 'Required keys "name" and "value" missing'

    return True, None

def is_environment_type(i):
    if type(i) is not dict:
        return False, 'Expected "dict" type'

    keys = i.keys()

    if 'project' not in keys and 'id' not in keys:
        return False, 'Required keys "project" or "id" missing'

    if 'project' in keys and 'id' in keys:
        return False, 'Please specify one "project" or "id" for environment input'

    if 'project' in keys:
        project_keys = i['project'].keys()

        if 'name' not in keys:
            return False, 'Project type requires environment "name"'

        if 'name' not in project_keys and 'id' not in project_keys:
            return False, 'Required keys "name" or "id" for project'

    return True, None


class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)

        self.createClient(task_vars)

        b = self._task.args.get('build_vars')
        n = self._task.args.get('name')
        e = self._task.args.get('environments')
        envs = []

        result['invalid_variable'] = []
        result['invalid_environment'] = []

        if b is None:
            b = []

        if e is None:
            result['failed'] = True
            result['message'] = 'Missing required "environments" parameter'
            return result

        for i in range(len(b)):
            valid, r = is_variable_type(b[i])
            if not valid:
                result['invalid_variable'].append(b[i])
                self._display.v(f'Invalid build variable detected: {r}')
                self._display.v(b[i])
                del b[i]

        for i in range(len(e)):
            valid, r = is_environment_type(e[i])

            if not valid:
                result['invalid_environment'].append(e[i])
                self._display.v(f'Invalid environment detected: {r}')
                self._display.v(json.dumps(e[i]))
                continue

            envs.append({
                "environment": e[i],
                # At the time of writing, build variables at the top level
                # are not working; they need to be at the environment level
                # instead.
                # Remove when https://github.com/uselagoon/lagoon/pull/3296 is released.
                "buildVariables": b
            })

        if len(envs) < 1:
            result['failed'] = True
            result['message'] = 'No environments to deploy'
            return result

        lagoonEnvironment = Environment(self.client)
        result['deploy_id'] = lagoonEnvironment.bulkDeploy(b, n, envs)
        result['changed'] = True
        return result
