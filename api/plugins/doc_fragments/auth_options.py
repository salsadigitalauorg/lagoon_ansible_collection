# -*- coding: utf-8 -*-

# Options for authenticating with the API.

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


class ModuleDocFragment(object):

    DOCUMENTATION = r'''
options:
  lagoon_api_endpoint:
    description:
    - Provide a URL for accessing the API.
    type: str
  lagoon_api_token:
    description:
    - Token used to authenticate with the API.
    type: str
'''
