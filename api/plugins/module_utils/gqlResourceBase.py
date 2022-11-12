import re

from ansible_collections.lagoon.api.plugins.module_utils.gql import GqlClient
from ansible.utils.display import Display

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
