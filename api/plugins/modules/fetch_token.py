#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r"""
module: fetch_token
description: Fetches a Lagoon token using ssh
short_description: Fetches a Lagoon token using ssh
options:
  grant:
    description:
      - Return the full grant token object, with expiry & refresh token.
    type: bool
    default: false
"""

EXAMPLES = r"""
- name: Fetch a Lagoon token.
  lagoon.api.fetch_token: {}
  register: token
  vars:
    lagoon_ssh_host: ssh.lagoon.amazeeio.cloud
    lagoon_ssh_port: 32222
    # ssh_options is also a task arg, which overrides this when set.
    lagoon_ssh_options:
      - -o
      - ConnectTimeout=5
- name: Verify the user.
  lagoon.api.whoami: {}
  vars:
    lagoon_api_token: "{{ token.token }}"
  register: whoami
- debug: var=whoami
"""
