#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: query
short_description: Run a query against the Lagoon API.
options:
  query:
    description:
      - The query to run, e.g, allProjects.
    required: true
    type: str
  args:
    description:
      - Arguments to pass to the query.
    type: dict
    default: {}
  mainType:
    description:
      - The GraphQL type from which to retrieve the top-level fields.
    type: str
  fields:
    description:
      - List of top-level fields to fetch from the query.
    type: list
    elements: str
    default: []
  subfields:
    description:
      - A map of sub-fields to retrieve from the query.
    suboptions:
      type:
        description:
          - The GraphQL type from which to retrieve the fields.
        type: str
      fields:
        description:
          - The list of fields to retrieve from the type.
        type: list
        elements: str

'''

EXAMPLES = r'''
- name: Query specific fields for all projects.
  lagoon.api.query:
    query: allProjects
    mainType: Project
    fields:
      - id
      - name
  register: query_results

- name: Query specific fields for a project.
  lagoon.api.query:
    query: projectByName
    args:
      name: '{{ project_name }}'
    mainType: Project
    fields:
      - id
      - name
      - branches
      - metadata
    subFields:
      kubernetes:
        type: Kubernetes
        fields:
          - id
          - name
  register: query_results

- name: Query variables for a project.
  lagoon.api.query:
    query: projectByName
    args:
      name: '{{ project_name }}'
    mainType: Project
    subFields:
      envVariables:
        type: EnvKeyValue
        fields:
          - id
          - name
          - value
          - scope
  register: query_results
'''
