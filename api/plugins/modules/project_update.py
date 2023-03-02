# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: project_update
short_description: Update the values for a project
description:
    - Updates the values for a project.
options:
  project:
    description:
      - The project's name.
    required: true
    type: str
  values:
    description:
      - The project values.
    type: dict
    default: None
'''

EXAMPLES = r'''
- name: Update project environment limit.
  lagoon.api.project_update:
    project: test-project
    values:
        developmentEnvironmentsLimit: 10
'''
