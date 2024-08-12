#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: mutation
description: Run a mutation against the Lagoon GraphQL API.
short_description: Run a mutation against the Lagoon GraphQL API.
options:
  mutation:
    description:
      - The mutation to run, e.g, addFactsByName.
    required: true
    type: str
  input:
    description:
      - Input to pass to the mutation.
    required: true
    type: dict
  select:
    description:
      - The type to select from the mutation result.
    type: str
    default: null
  subfields:
    description:
      - The subfields to select from the mutation result.
    type: list
    default: []
'''

EXAMPLES = r'''
- name: Delete a Fact via mutation before creating
  lagoon.api.mutation:
    mutation: deleteFact
    input:
      environment: "{{ environment_id }}"
      name: lagoon_logs

- name: Add a Fact for a project
  lagoon.api.mutation:
    mutation: addFact
    input:
      name: lagoon_logs
      category: Drupal Module Version
      environment: "{{ environment_id }}"
      value: 2.0.0
      source: ansible_playbook:audit:module_version
      description: The lagoon_logs module version
    select: Fact
    subfields:
      - id

- name: Delete Facts from a source via mutation before creating
  lagoon.api.mutation:
    mutation: deleteFactsFromSource
    input:
      environment: "{{ environment_id }}"
      source: ansible_playbook:audit:module_version

- name: Add multiple Facts for a project
  lagoon.api.mutation:
    mutation: addFactsByName
    input:
      project: "{{ project_name }}"
      environment: "{{ environment }}"
      fact:
        - name: admin_toolbar
          category: Drupal Module Version
          environment_id: "{{ environment_id }}"
          value: 2.3.0
          source: ansible_playbook:audit:module_version
          description: The admin_toolbar module version
        - name: panelizer
          category: Drupal Module Version
          environment_id: "{{ environment_id }}"
          value: 4.0.0
          source: ansible_playbook:audit:module_version
          description: The panelizer module version
    select: Fact
    subfields:
      - id
'''
