from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

EXAMPLES = r'''
    - name: Fetch a Lagoon token.
      lagoon.api.token:
        ssh_options: "-q -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
      register: token
      vars:
        lagoon_ssh_host: ssh.lagoon.amazeeio.cloud
        lagoon_ssh_port: 32222
    - name: Verify the user.
      lagoon.api.whoami: {}
      vars:
        lagoon_api_token: "{{ token.token }}"
      register: whoami
    - debug: var=whoami
'''

from ansible.plugins.action import ActionBase
import ansible_collections.lagoon.api.plugins.module_utils.token as LagoonToken

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
