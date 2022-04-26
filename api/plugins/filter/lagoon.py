from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.errors import AnsibleFilterError
from functools import reduce

class FilterModule(object):

    def playbook_on_play_start(self, pattern):
        self.playbook = self.play.playbook
        self.inventory = self.playbook.inventory

    def environment_input_type(self, groups, hostvars=None, env_key="environment.name", project_key="project.name"):
        """
        Generate EnvironmentInput from the inventory to use for GraphQL queries.
        Examples:
        - name: Prepare environment input
          lagoon.api.bulk_deploy:
            environments: "{{ groups['filtered_inventory'] | lagoon.api.lagoon_environment_input(hostvars=ansible.hostvars) }}
        """
        environments = []

        if hostvars is None:
            raise AnsibleFilterError("'hostvars' not found")

        for item in groups:
            try:
                hv = hostvars[item]
                environments.append({
                    "name": reduce(lambda a, b: a[b], env_key.split("."), hv),
                    "project": {
                        "name": reduce(lambda a, b: a[b], project_key.split("."), hv),
                    },
                })
            except KeyError:
                raise AnsibleFilterError(f"'{item}' not in variable list")

        return environments

    def filters(self):
        return {"lagoon_environment_input": self.environment_input_type}
