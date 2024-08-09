#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: metadata
short_description: Manage a project's metadata
description:
    - Manages a project's metadata.
options:
  project_name:
    description:
      - The project's name.
    required: true
    type: string
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
      - The metadata values - can be a dict or a list of dicts.
    type: list
    default: []
'''

EXAMPLES = r'''
- name: Add project metadata (dict)
  lagoon.api.metadata:
    state: present
    data:
      solr-version: 6
    project_id: 7
    project_name: project-pheonix

- name: Add project metadata (list of dicts)
  lagoon.api.metadata:
    state: present
    data:
      - key: movie
        value: star-wars
      - key: music
        value: rock
    project_id: 7
    project_name: project-pheonix

- name: Remove project metadata (dict)
  lagoon.api.metadata:
    state: absent
    data:
      solr-version: 6
    project_id: 7
    project_name: project-pheonix

- name: Add project metadata (list of dicts)
  lagoon.api.metadata:
    state: absent
    data:
      - key: movie
        value: star-wars
      - key: music
        value: rock
    project_id: 7
    project_name: project-pheonix
'''
