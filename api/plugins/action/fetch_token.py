import time
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

        grant = self._task.args.get("grant", False)

        if lagoon_ssh_private_key:
            self._display.vvvv("writing private key to file")
            if not lagoon_ssh_private_key_file:
                lagoon_ssh_private_key_file = '/tmp/lagoon_ssh_private_key'
            try:
                LagoonToken.write_ssh_key(lagoon_ssh_private_key, lagoon_ssh_private_key_file)
            except IOError as e:
                result['failed'] = True
                result['error'] = e
                return result

        ssh_host = self._templar.template(task_vars.get('lagoon_ssh_host'))
        ssh_port = self._templar.template(task_vars.get('lagoon_ssh_port'))
        self._display.vvvv(f"lagoon_ssh_private_key_file: {lagoon_ssh_private_key_file}")
        self._display.vvvv(f"lagoon ssh host/port: {ssh_host}:{ssh_port}")

        rc, grant_token, result['error'] = LagoonToken.fetch_token(
            ssh_host,
            ssh_port,
            self._task.args.get('ssh_options', ""),
            lagoon_ssh_private_key_file
        )
        result['rc'] = rc

        if rc > 0:
            result['failed'] = True
            result['msg'] = result['error']
        elif grant:
            grant_token['expiry_time'] = time.time() + grant_token['expires_in']
            result['token'] = grant_token
        else:
            result['token'] = grant_token['access_token']

        return result
