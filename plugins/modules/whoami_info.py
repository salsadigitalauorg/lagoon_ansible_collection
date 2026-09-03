#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r'''
module: whoami_info
short_description: Get information about the current Lagoon user
description:
  - Returns the identity of the user that O(lagoon_api_token), or the
    token obtained via the SSH-grant options, authenticates as.
  - Read-only. Never reports V(changed).
version_added: "3.0.0"
options: {}
extends_documentation_fragment:
  - salsadigitalauorg.lagoon.auth
author:
  - Salsa Digital (@salsadigitalauorg)
'''

EXAMPLES = r'''
- name: Look up the current user.
  salsadigitalauorg.lagoon.whoami_info:
  register: whoami

- name: Show the current user's email.
  ansible.builtin.debug:
    var: whoami.user.email
'''

RETURN = r'''
user:
  description:
  - Flat details of the authenticated user.
  - >-
    Does not include C(groups) -- a nested C(groups { name type })
    selection is forbidden under the collection's flat-query rule.
    Look up group membership with a dedicated module instead.
  returned: success
  type: dict
  contains:
    id:
      description: The user's id.
      type: str
      returned: success
    email:
      description: The user's email address.
      type: str
      returned: success
    firstName:
      description: The user's first name.
      type: str
      returned: success
    lastName:
      description: The user's last name.
      type: str
      returned: success
    created:
      description: When the user was created.
      type: str
      returned: success
    lastAccessed:
      description: When the user last accessed the Lagoon API.
      type: str
      returned: success
    has2faEnabled:
      description: Whether the user has two-factor authentication enabled.
      type: bool
      returned: success
'''

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils \
    import auth
from ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils \
    .client import LagoonClient
from ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils \
    import errors


def run_module(module):
    """Execute the module's read-only logic and return the ``user`` dict.

    Takes an already-constructed ``AnsibleModule`` (or any object exposing
    the same ``.params`` mapping) so this can be exercised directly in
    unit tests with no action shim involved, proving the module is fully
    functional when handed an explicit ``lagoon_api_token`` -- the shim's
    only job is resolving that token before this function ever runs.
    """
    lagoon_client = LagoonClient(
        endpoint=module.params['lagoon_api_endpoint'],
        token=module.params['lagoon_api_token'],
        module=module,
        validate_certs=module.params['validate_certs'],
    )

    query = LagoonClient.build_query(
        'me',
        fields=[
            'id', 'email', 'firstName', 'lastName', 'created',
            'lastAccessed', 'has2faEnabled',
        ])
    data = lagoon_client.execute(query)

    user = data.get('me')
    if user is None:
        raise errors.LagoonNotFoundError('user', query='me')

    return user


def main():
    module = AnsibleModule(
        argument_spec=auth.auth_argument_spec(),
        supports_check_mode=True,
    )

    try:
        user = run_module(module)
    except errors.LagoonError as e:
        module.fail_json(msg=str(e))
        return

    module.exit_json(changed=False, user=user)


if __name__ == '__main__':
    main()
