#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: whoami
short_description: Get information about the current user.
'''

EXAMPLES = r'''
- name: Verify the user.
  lagoon.api.whoami: {}
  register: whoami
- debug: var=whoami
'''
