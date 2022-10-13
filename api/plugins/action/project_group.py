from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

EXAMPLES = r'''
- name: Add a fact to a Lagoon project
  lagoon.api.fact:
    environment: 1
    name: php_version
    value: 8.1.9
    description: PHP version
    type: SEMVER
    category: fact
    service: php
- debug: var=whoami
'''

from ansible.errors import AnsibleError
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient


display = Display()


def has_group(client: GqlClient, project, group):

    res = client.execute_query(
        """
        query project($name: String!) {
            projectByName(name: $name) {
                id
                groups {
                    name
                }
            }
        }
        """,
        {
            "name": project
        }
    )

    display.v(f"GraphQL query result: {res}")

    try:
        if res["projectByName"] is not None:
            for g in res["projectByName"]["groups"]:
                if g["name"] == group:
                    return True
        return False
    except KeyError:
        return False


def remove_groups_from_project(client: GqlClient, project, groups):

    res = client.execute_query(
        """
        mutation delete($name: String!, $groups: [GroupInput!]!) {
            removeGroupsFromProject(input: {
                project: { name: $name }
                groups: $groups
            }) {
                id
            }
        }
        """,
        {
            "name": project,
            "groups": groups
        }
    )

    try:
        return res["removeGroupsFromProject"]
    except KeyError:
        return False


def add_project_group(client: GqlClient, project, groups):

    res = client.execute_query(
        """
        mutation add($name: String!, $groups: [GroupInput!]!) {
            addGroupsToProject(input: {
                project: { name: $name }
                groups: $groups
            }) {
                id
            }
        }""",
        {
            "name": project,
            "groups": groups
        }
    )

    display.v(f"GraphQL mutation result: {res}")
    return res["addGroupsToProject"]


class ActionModule(ActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp

        display.v("Task args: %s" % self._task.args)

        lagoon = GqlClient(
            self._templar.template(task_vars.get('lagoon_api_endpoint')).strip(),
            self._templar.template(task_vars.get('lagoon_api_token')).strip(),
            self._task.args.get('headers', {})
        )

        # Modifier.
        state = self._task.args.get('state', 'present')

        project = self._task.args.get("project")
        groups = self._task.args.get("groups", [])

        op_groups = []

        for g in groups:
            if state == "present" and not has_group(lagoon, project, g):
                op_groups.append({"name": g})
            elif state == "absent" and has_group(lagoon, project, g):
                op_groups.append({"name": g})

        display.v("Groups args: %s" % op_groups)
        method = "remove_groups_from_project" if state == "absent" else "add_project_group"

        if len(op_groups) == 0:
            result["changed"] = False
        else:
            result["result"] = globals()[method](lagoon, project, op_groups)
            result["changed"] = True

        return result
