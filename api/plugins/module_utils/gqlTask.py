from .gql import GqlClient
from .gqlResourceBase import ResourceBase

from gql.dsl import DSLQuery
from gql.transport.exceptions import TransportQueryError
from typing import List


TASK_FIELDS_COMMON = [
    'id',
    'name',
    'taskName',
    'service',
    'status',
    'started',
    'completed',
]

class Task(ResourceBase):

    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        super().__init__(client, options)

    def get(self, env_names: List[str], fields: List[str] = None, limit: int = 50) -> dict:

        if not fields or not len(fields):
            fields = TASK_FIELDS_COMMON

        res = {}
        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            fragment_fields = ds.Environment.tasks(limit=limit).select(
                getattr(ds.Task, fields[0]))
            if len(fields) > 1:
                for f in fields[1:]:
                    if f == 'files':
                        continue
                    fragment_fields.select(getattr(ds.Task, f))

                if 'files' in fields:
                    fragment_fields.select(ds.Task.files.select(
                        ds.File.id,
                        ds.File.filename,
                        ds.File.download,
                    ))

            field_queries = []
            for ns in env_names:
                # Build the main query.
                field_query = ds.Query.environmentByKubernetesNamespaceName.args(
                    kubernetesNamespaceName=ns).alias(self.sanitiseForQueryAlias(ns))
                field_query.select(fragment_fields)
                field_queries.append(field_query)

            resources = self.queryResources(DSLQuery(*field_queries))

        for ns in env_names:
            try:
                res[ns] = resources.get(
                    self.sanitiseForQueryAlias(ns))['tasks']
            except:
                res[ns] = None

        return res

    def byId(self, id: int, fields: List[str] = None) -> dict:
        """
        Get the top-level information for a Lagoon task by id.
        """

        if not fields:
            fields = TASK_FIELDS_COMMON

        joined_fields = "\n        ".join(fields)

        query = f"""query {{
    taskById (id: { id }) {{
        { joined_fields }
    }}
}}"""

        res = self.client.execute_query(query)
        if res['taskById'] != None:
            return res['taskById']

        return res

    def byTaskName(self, task_name: str, fields: List[str] = None) -> dict:
        """
        Get the top-level information for a Lagoon task by taskName.
        """

        if not fields:
            fields = TASK_FIELDS_COMMON

        joined_fields = "\n        ".join(fields)

        query = f"""query {{
    taskByTaskName (taskName: "{ task_name }") {{
        { joined_fields }
    }}
}}"""

        res = self.client.execute_query(query)
        if res['taskByTaskName'] != None:
            return res['taskByTaskName']

        return res

    def invoke(self, env_id: int, task_id: int, task_arguments: list) -> int:
        res = self.client.execute_query(
            f"""
            mutation InvokeTask(
                $env_id: Int!
                $task_id: Int!
                $task_arguments: [AdvancedTaskDefinitionArgumentValueInput]
            ) {{
                invokeRegisteredTask(
                    environment: $env_id,
                    advancedTaskDefinition: $task_id,
                    argumentValues: $task_arguments,
                ) {{ id }}
            }}""",
            {
                "env_id": env_id,
                "task_id": task_id,
                "task_arguments": task_arguments,
            }
        )
        return res['invokeRegisteredTask']['id']

