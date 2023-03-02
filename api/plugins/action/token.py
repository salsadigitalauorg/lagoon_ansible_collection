from ..module_utils import token as LagoonToken
from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp  # tmp no longer has any effect

        lagoon_ssh_private_key = task_vars.get('lagoon_ssh_private_key')
        lagoon_ssh_private_key_file = task_vars.get('lagoon_ssh_private_key_file')

        if lagoon_ssh_private_key:
            if not lagoon_ssh_private_key_file:
                lagoon_ssh_private_key_file = '/tmp/lagoon_ssh_private_key'
            LagoonToken.write_ssh_key(lagoon_ssh_private_key, lagoon_ssh_private_key_file)

        rc, result['token'], result['error'] = LagoonToken.fetch_token(
            self._templar.template(task_vars.get('lagoon_ssh_host')),
            self._templar.template(task_vars.get('lagoon_ssh_port')),
            self._task.args.get('ssh_options', ""),
            lagoon_ssh_private_key_file
        )
        if rc > 0:
            result['failed'] = True

        return result
