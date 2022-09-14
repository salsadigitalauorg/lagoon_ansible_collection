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


def get_facts(client: GqlClient, environment_id):
    res = client.execute_query(
        """
        query env($environment_id: Int!) {
            environmentById(id: $environment_id) {
                facts {
                    name
                    value
                    id
                }
            }
        }""",
        {
            "environment_id": environment_id
        }
    )
    display.v(f"GraphQL query result: {res}")

    try:
        return res["environmentById"]["facts"]
    except KeyError:
        return dict()


def delete_fact(client: GqlClient, environment_id, name):
    res = client.execute_query(
        """
        mutation df(
            $environment_id: Int!
            $name: String!
        ) {
            deleteFact(input: {
                environment: $environment_id
                name: $name
            })
        }""",
        {
            "environment_id": environment_id,
            "name": name
        }
    )

    try:
        return res["deleteFact"] == "success"
    except KeyError:
        return False


def add_fact(client: GqlClient, environment_id, name, value, source = "ansible", type = "TEXT", description = "Provided by Lagoon Ansible collection") -> dict:

    if type is None:
        type = "TEXT"
    if description is None:
        description = "Provided by Lagoon Ansible collection"
    if source is None:
        source = "ansible"

    if type not in ["TEXT", "SEMVER", "URL"]:
        raise AnsibleError(f"Invalid fact type {type}, must be TEXT, SEMVER or URL")

    if type == "TEXT" and not isinstance(value, str):
        value = f"{value}"

    res = client.execute_query(
        """
        mutation addFact(
            $environment_id: Int!
            $name: String!
            $value: String!
            $source: String!
            $type: FactType!
            $description: String!
        ) {
            addFact(input: {
                environment: $environment_id
                name: $name
                value: $value
                source: $source
                type: $type
                description: $description
            }) {
                id
            }
        }""",
        {
            "environment_id": environment_id,
            "name": name,
            "value": value,
            "source": source,
            "type": type,
            "description": description
        }
    )

    display.v(f"GraphQL mutation result: {res}")
    return res["addFact"]


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

        environment_id = int(self._task.args.get("environment"))
        name = self._task.args.get("name")
        value = self._task.args.get("value")
        source = self._task.args.get("source", None)
        type = self._task.args.get("type", None)
        description = self._task.args.get("description", None)

        # modifiers
        state = self._task.args.get('state', None)

        found_fact = False

        facts = get_facts(lagoon, environment_id)
        for fact in facts:
            if fact["name"] == name:
                found_fact = fact

        if not found_fact and state == "absent":
            result["changed"] = False
        elif found_fact and state == "absent":
            result["changed"] = True
            result["result"] = delete_fact(lagoon, environment_id, name)
        elif found_fact:
            if value != found_fact["value"]:
                result["changed"] = True
                delete_fact(lagoon, environment_id, name)
                result["result"] = add_fact(
                    lagoon, environment_id, name, value, source, type, description)
            else:
                result["changed"] = False
        else:
            result["changed"] = True
            result["result"] = add_fact(
                lagoon, environment_id, name, value, source, type, description)

        return result
