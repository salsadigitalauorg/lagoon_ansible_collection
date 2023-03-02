# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: metadata
short_description: Manage a project's metadata
description:
    - Manages a project's metadata.
options:
  project_id:
    description:
      - The project's ID.
    required: true
    type: int
  state:
    description:
      - Message to display to users before shutdown.
    type: str
    default: present
    choices: [ absent, present ]
  data:
    description:
      - The metadata values.
    type: dict
    default: None
'''

EXAMPLES = r'''
- name: Add project metadata
  lagoon.api.metadata:
    state: present
    data:
      solr-version: 6
    project_id: 7
'''
