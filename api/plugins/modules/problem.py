#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: problem
short_description: Manage problems for an environment.
description:
    - Manages problems for an environment.
options:
  associatedPackage:
    description:
      - Package associated to the problem.
    type: str
  data:
    description:
      - The problem data.
      - Required when state is present.
    type: str
  description:
    description:
      - A description of the problem.
    type: str
  environment:
    description:
      - The ID of the environment.
    required: true
    type: int
  fixedVersion:
    description:
      - Version in which the problem is fixed.
    type: str
  identifier:
    description:
      - The identifier of the problem.
    required: true
    type: str
  links:
    description:
      - Links relating to the problem.
    type: str
  service:
    description:
      - Service in which the problem was found.
    type: str
  severity:
    description:
      - Severity rating of the problem.
    type: str
    choices: [ NONE, UNKNOWN, NEGLIGIBLE, LOW, MEDIUM, HIGH, CRITICAL ]
  severityScore:
    description:
      - Score of the problem severity.
      - Value between 0 and 1.
    type: float
  source:
    description:
      - Source of the problem.
    type: str
  version:
    description:
      - Version in which the problem was found.
    type: str
  state:
    description:
      - Determines if the problem should be created, updated, or deleted. When set to C(present), the problem will be
        created, if it does not already exist. If set to C(absent), an existing problem will be deleted. If set to
        C(present), an existing problem will be deleted and recreated, if its data differs from the one specified using
        I(data)..
    type: str
    default: present
    choices: [ absent, present ]
'''

EXAMPLES = r'''
- name: Add a problem to a Lagoon project
  lagoon.api.problem:
    environment_id: 1
    identifier: db-permissions
    data: import configuration
    description: Users should not be able to import configuration.
    source: drupal
'''
