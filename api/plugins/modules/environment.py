#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = r'''
---
module: environment

short_description: Manage a project's environments.

version_added: "1.0.1"

description:
    - Allows creating, updating, replacing and deleting environments.

options:
    project:
        description: The name of the project.
        required: true
        type: str
    environment:
        description: The name of the environment.
        required: true
        type: str
    definition: (TODO)
        description: Values for the environment creation, as a dict.
        type: dict
        suboptions:
            deployBaseRef:
                type: str
                description: The version control base ref for deployments (e.g., branch name, tag, or commit id).
            deployHeadRef:
                type: str
                description: The version control head ref for deployments (e.g., branch name, tag, or commit id).
            deployType:
                type: str
                description: Which Deployment Type this environment is, can be BRANCH, PULLREQUEST, PROMOTE.
                choices: [ BRANCH, PULLREQUEST, PROMOTE ]
            environmentType:
                type: str
                description: Which Environment Type this environment is, can be PRODUCTION, DEVELOPMENT.
                choices: [ PRODUCTION, DEVELOPMENT ]
            kubernetes:
                type: int
                description: Target cluster for this environment.
                aliases:
                    - openshift
            kubernetesNamespaceName:
                type: str
                description: Name of the Kubernetes Namespace this environment is deployed into.
                aliases:
                    - openshiftProjectName

    state:
        description:
        - Determines if the environment should be created, updated, or deleted. When set to C(present), the environment will be
        created, if it does not already exist. If set to C(absent), an existing environment will be deleted. If set to
        C(present), an existing environment will be updated, if its attributes differ from those specified using
        I(definition).
        type: str
        default: present
        choices: [ absent, present ]

extends_documentation_fragment:
  - lagoon.api.auth_options

author:
    - Yusuf Hasan Miyan (@yusufhm)

'''

EXAMPLES = r'''
- name: Delete Lagoon environment.
  lagoon.api.environment:
    project: 'foobar'
    environment: 'feature/baz'
    state: absent
'''
