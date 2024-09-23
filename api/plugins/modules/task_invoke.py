#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: task_invoke
short_description: Invoke an advanced task.
description:
    - Invokes an advanced task in a project.
options:
    project:
        description:
            - The ID of the project.
            - Required.
        type: int
    task:
        description:
            - The ID of the task.
            - Required.
        type: int
    arguments:
        description:
            - The arguments to execute the command with
        type list
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
- name: Invoke an advanced task
  lagoon.api.task_invoke:
    project: 123
    task: 456

- name: Invoke an advanced task with multiple arguments
  lagoon.api.task_invoke:
    project: 123
    task: 456
    arguments:
        - name: ARG1
          value: VALUE1
        - name: ARG2
          value: VALUE2
'''
