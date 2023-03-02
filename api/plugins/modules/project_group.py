# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: project_group
short_description: Manage the groups for a project
options:
  project:
    description:
      - The project's name.
    required: true
    type: str
  groups:
    description:
      - The project groups.
    type: list
    required: true
    elements: str
'''

EXAMPLES = r'''
- name: Ensure project is in group
  lagoon.api.project_group:
    state: present
    project: "{{ project_name }}"
    groups:
      - my_group_name
'''
