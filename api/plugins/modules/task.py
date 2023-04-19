# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
module: task
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

'''

EXAMPLES = r'''
- name: Invoke a task
  lagoon.api.task:
    environment: test-shipshape-master
    name: AUDIT - Admin shipshape
  register: task_result
- name: Display the task id
  debug: var=task_result.id
'''
