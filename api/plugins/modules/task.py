#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: task
description: Invoke a task on an environment.
short_description: Invoke a task on an environment.
options:
  environment:
    description:
      - The environment name. Required if environment_id is not provided.
    type: str
  environment_id:
    description:
      - The environment id. Required if environment is not provided.
    type: int
  name:
    description:
      - Name of the task to invoke.
    type: str
    required: true
  arguments:
    description:
      - The arguments to execute the command with
    type: list
    elements: dict
    suboptions:
      advancedTaskDefinitionArgumentName:
        description:
          - The name of the argument.
        required: true
        type: string
      value:
        description:
          - The value of the argument.
        required: true
        type: string

'''

EXAMPLES = r'''
- name: Invoke a task
  lagoon.api.task:
    environment: test-shipshape-master
    name: AUDIT - Admin shipshape
    arguments:
      - advancedTaskDefinitionArgumentName: ARG1
        value: VALUE1
      - advancedTaskDefinitionArgumentName: ARG2
        value: VALUE2
  register: task_result
- name: Display the task id
  debug: var=task_result.task_id
'''
