from ansible.plugins.action import ActionBase
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient


class LagoonActionBase(ActionBase):

    def createClient(self, task_vars):
        self.client = GqlClient(
            self._templar.template(task_vars.get('lagoon_api_endpoint')).strip(),
            self._templar.template(task_vars.get('lagoon_api_token')).strip(),
            self._task.args.get('headers', {}),
            self._display,
        )
