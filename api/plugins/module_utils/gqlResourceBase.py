import re
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient
from ansible.utils.display import Display
from gql.transport.exceptions import TransportQueryError
from typing import Dict, List

display = Display()

PROJECT_FIELDS = [
    'autoIdle',
    'availability',
    'branches',
    'created',
    'deploymentsDisabled',
    'developmentBuildPriority',
    'developmentEnvironmentsLimit',
    'gitUrl',
    'id',
    'metadata',
    'name',
    'openshiftProjectName',
    'openshiftProjectPattern',
    'productionAlias',
    'productionBuildPriority',
    'productionEnvironment',
    'productionRoutes',
    'pullrequests',
    'routerPattern',
    'standbyAlias',
    'standbyProductionEnvironment',
    'standbyRoutes',
]

VARIABLES_FIELDS = [
    'id',
    'name',
    'value',
    'scope',
]

CLUSTER_FIELDS = [
    'id',
    'name',
]

ENVIRONMENTS_FIELDS = [
    'autoIdle',
    'created',
    'environmentType',
    'id',
    'kubernetesNamespaceName',
    'name',
    'route',
    'routes',
    'updated',
]

DEPLOYMENTS_FIELDS = [
    'bulkId',
    'bulkName',
    'completed',
    'created',
    'id',
    'name',
    'started',
    'status',
    'uiLink',
]

DEFAULT_BATCH_SIZE = 100


class ResourceBase:

    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        self.client = client
        self.errors = []
        self.display = display
        self.options = options

    def sanitisedName(self, name):
        return re.sub(r'[\W_-]+', '-', name)

    def sanitiseForQueryAlias(self, name):
        return re.sub(r'[\W-]+', '_', name)

    def queryTopLevelFields(self, resList: list, query: str, qryType: str, args: Dict[str, any] = {}, fields: List[str] = []):
        with self.client:
            queryObj = self.client.build_dynamic_query(query, qryType, args, fields)
            try:
                res = self.client.execute_query_dynamic(queryObj)
                if isinstance(res[query], list):
                    resList.extend(res[query])
                elif isinstance(res[query], dict):
                    resList.append(res[query])
            except TransportQueryError as e:
                if isinstance(e.data[query], list):
                    resList.extend(e.data[query])
                    self.errors.extend(e.errors)
                elif isinstance(e.data[query], dict):
                    resList.append(e.data[query])
                    self.errors.extend(e.errors)
                else:
                    raise
            except Exception:
                raise

            return self
