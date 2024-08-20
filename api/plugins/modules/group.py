#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r"""
module: group
short_description: Manage groups.
description:
  - Manages groups.
options:
  name:
    description:
      - The name of the group.
    required: true
    type: str
  parentGroup:
    description:
      - The name of the fact.
    required: false
    type: dict
    suboptions:
      id:
        description: The ID of the parent group.
        type: int
      name:
        description: The name of the parent group.
        type: str
  state:
    description:
      - Determines if the group should be created or deleted.
    type: str
    default: present
    choices: [ absent, present ]
"""

EXAMPLES = r"""
- name: Add a Group
  lagoon.api.group:
    name: saas

- name: Delete a Group
  lagoon.api.group:
    name: saas
    state: absent
"""
