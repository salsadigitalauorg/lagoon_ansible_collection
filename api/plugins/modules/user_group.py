#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: user_group
description: Manage the groups for a user
short_description: Manage the groups for a user
options:
  email:
    description:
      - The user email.
    required: true
    type: str
  group:
    description:
      - The group to add the user to.
    type: str
    required: true
  role:
    description:
      - The role to assign the user.
    type: str
    required: true
    choices: [ GUEST, REPORTER, DEVELOPER, MAINTAINER, OWNER ]
'''

EXAMPLES = r'''
- name: Add user to group.
  lagoon.api.user_group:
    email: user@example.com
    group: test-group
    role: GUEST
  register: group_add
- debug: var=group_add
'''
