import re

from .gql import GqlClient
from .gqlError import ResourceError
from .display import Display

from gql.dsl import DSLExecutable, DSLQuery
from gql.transport.exceptions import TransportQueryError
from typing import Dict, List

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

GROUPS_FIELDS = [
    'id',
    'name',
    'type',
]

DEFAULT_BATCH_SIZE = 100


class ResourceBase(Display):

    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        super().__init__()
        self.client = client
        self.errors = []
        self.options = options

        if self.options.get('exitOnError') == None:
            self.options['exitOnError'] = False

    def sanitisedName(self, name):
        return re.sub(r'[\W_-]+', '-', name)

    def sanitiseForQueryAlias(self, name):
        return re.sub(r'[\W-]+', '_', name)

    def queryTopLevelFields(self, resList: list, query: str, qryType: str, args: Dict[str, any] = {}, fields: List[str] = []):
        with self.client:
            queryObj = self.client.build_dynamic_query(query, qryType, args, fields)
            try:
                res = self.client.execute_query_dynamic(DSLQuery(queryObj))
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

    def queryResources(self, *query_operations: DSLExecutable) -> dict:
        """
        Runs a dynamic query and captures any errors and returns the result.
        """

        try:
            resources = self.client.execute_query_dynamic(*query_operations)
        except TransportQueryError as e:
            if isinstance(e.data, dict):
                resources = e.data
                self.errors.extend(e.errors)
            else:
                raise
        except Exception:
            raise

        return resources

    def shouldStopDueToError(self) -> bool:
        """
        Determines whether we should exit due to errors.
        """

        return self.options.get('exitOnError') == True and len(self.errors) > 0

    def raiseExceptionIfRequired(self, message: str = ""):
        """
        Raises a ResourceError exception if shouldStopDueToError is true.
        """
        if self.shouldStopDueToError():
            if not message:
                message = "Unable to proceed due to previous errors"
            raise ResourceError(self.errors, message)
