import re
from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient
from ansible.utils.display import Display
from gql.transport.exceptions import TransportQueryError
from typing_extensions import Self

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


class ResourceBase:

    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        self.client = client
        self.errors = []
        self.display = display

        self.options = options
        self.batch_size = options.get('batch_size', 100)

    def sanitiseForQueryAlias(self, name):
        return re.sub(r'[\W-]+', '_', name)

    def queryTopLevelFields(self, resList: list, query: str, qryType: str, args: dict[str, any] = {}, fields: list[str] = []) -> Self:
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
