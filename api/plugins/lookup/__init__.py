from ansible.plugins.lookup import LookupBase
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient


class LagoonLookupBase(LookupBase):

    def createClient(self):
        self.client = GqlClient(
            self._templar.template(self.get_option('lagoon_api_endpoint')),
            self._templar.template(self.get_option('lagoon_api_token')),
            self.get_option('headers', {}),
            self._display,
        )
