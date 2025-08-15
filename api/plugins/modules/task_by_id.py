#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: task_by_id
description: Get a task by ID.
short_description: Retrieve information of a Lagoon task by ID.
options:
  id:
    description:
      - The task ID.
    type: int
'''

EXAMPLES = r'''
- name: Get a Lagoon task
  lagoon.api.task_by_id:
    id: 113893
  register: task_result
- name: Display the task name
  debug: var=task_result.data.taskName
- name: Display the task status
  debug: var=task_result.data.status
'''
