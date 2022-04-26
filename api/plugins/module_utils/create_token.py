from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import paramiko
from ansible.errors import AnsibleError

class CreateToken:
    def __init__(self, ssh_host, ssh_port, ssh_username) -> None:
        self.token = ''
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            key_filename = os.getenv('SOURCE_SSH_KEY')

            # If we don't have a key filename value we assume that the host has ssh config or has
            # added the key to the keychain and we can connect with host config.

            if not key_filename:
                ssh.connect(hostname=ssh_host,
                            username=ssh_username, port=ssh_port)
            else:
                ssh.connect(hostname=ssh_host,
                            username=ssh_username, port=ssh_port, key_filename=key_filename)

            ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("token")
            self.token = ssh_stdout.readlines()[0].strip()
        except Exception as ex:
            raise AnsibleError('Error: %s - %s' % (ex, key_filename))

    def get_token(self) -> str:
      return self.token
