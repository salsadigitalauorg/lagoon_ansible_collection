# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: token
short_description: Fetches a Lagoon token using ssh
'''

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
