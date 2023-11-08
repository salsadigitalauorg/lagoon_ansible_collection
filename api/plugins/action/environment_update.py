from . import LagoonActionBase
from ..module_utils.gqlEnvironment import Environment
from ansible.errors import AnsibleError


class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        self._display.vvv("Task args: %s" % self._task.args)

        environment_name = self._task.args.get('environment')
        environment_id = self._task.args.get('environment_id')
        patch_values = self._task.args.get('values')

        if not environment_name and not environment_id:
            raise AnsibleError("Environment name or id is required.")

        if not patch_values:
            raise AnsibleError("No value to update.")

        self.createClient(task_vars)
        lagoonEnvironment = Environment(self.client)

        if environment_name:
            lagoonEnvironment.byNs(environment_name).withCluster()
        else:
            lagoonEnvironment.byId(environment_id).withCluster()
        environment = lagoonEnvironment.environments[0]

        update_required = False
        for key, value in patch_values.items():
            if not key in environment:
                update_required = True
                break
            if key in ['openshift', 'kubernetes']:
                # Cast the cluster id to int here - it will be used
                # further down when updating the environment.
                value = int(value)
                if str(value) != str(environment[key]['id']):
                    update_required = True
                    break
            elif str(value) != str(environment[key]):
                update_required = True
                break

        if not update_required:
            result['update'] = environment
            return result

        result['update'] = lagoonEnvironment.update(environment['id'], patch_values)
        result['changed'] = True
        self._display.v("Update: %s" % result['update'])

        return result
