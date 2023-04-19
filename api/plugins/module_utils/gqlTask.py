from .gql import GqlClient
from .gqlResourceBase import ResourceBase

from gql.dsl import DSLQuery
from typing import List


TASK_FIELDS_COMMON = [
    'id',
    'name',
    'taskName',
    'service',
    'command',
    'status',
    'started',
    'completed',
    'logs',
    'files',
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

    def invoke(self, env_id: int, task_id: int) -> int:
        res = self.client.execute_query(
            f"""
            mutation InvokeTask(
                $env_id: Int!
                $task_id: Int!
            ) {{
                invokeRegisteredTask(
                    environment: $env_id,
                    advancedTaskDefinition: $task_id,
                ) {{ id }}
            }}""",
            {
                "env_id": env_id,
                "task_id": task_id,
            }
        )
        return res['invokeRegisteredTask']['id']

