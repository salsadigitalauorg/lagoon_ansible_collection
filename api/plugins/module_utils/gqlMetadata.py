import json

from .gql import GqlClient
from .gqlResourceBase import ResourceBase


from gql.dsl import DSLQuery
from typing import List

class Metadata(ResourceBase):

    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        super().__init__(client, options)

    def get(self, project_names: List[str] = []) -> dict:
        res = {}

        if len(project_names) > 0:
            resources = {}
            with self.client as (_, ds):
                field_queries = []
                for pName in project_names:
                    # Build the main query.
                    field_query = ds.Query.projectByName.args(
                        name=pName).alias(self.sanitiseForQueryAlias(pName))
                    field_query.select(ds.Project.metadata)
                    field_queries.append(field_query)

                resources = self.queryResources(DSLQuery(*field_queries))

            for pName in project_names:
                try:
                    metadata = resources.get(
                        self.sanitiseForQueryAlias(pName)).get(
                            'projectByName', {}).get('metadata', None)
                    if isinstance(metadata, dict):
                        res[pName] = metadata
                    else:
                        res[pName] = json.loads(metadata)
                except:
                    res[pName] = None
        else:
            resources = self.client.execute_query(
                """
                query {
                    allProjects {
                        id
                        name
                        metadata
                    }
                }""")
            if not resources.get('allProjects'):
                return res

            for p in resources.get('allProjects'):
                if isinstance(p['metadata'], dict):
                    res[p['name']] = p['metadata']
                else:
                    res[p['name']] = json.loads(p['metadata'])

        return res

    def update(self, project_id: int, key: str, value: str) -> dict:
        res = self.client.execute_query(
            """
            mutation UpdateMetadata(
                $id: Int!,
                $key: String!,
                $value: String!
            ) {
                updateProjectMetadata(input: {
                    id: $id,
                    patch: {
                        key: $key,
                        value: $value
                    }
                }) {
                    metadata
                }
            }""",
            {
                "id": project_id,
                "key": key,
                "value": value
            }
        )
        metadata_str = res.get('updateProjectMetadata',
                               {}).get('metadata', None)
        if not metadata_str:
            return f'{key}:null'

        if isinstance(metadata_str, dict):
            metadata = metadata_str
        else:
            metadata = json.loads(metadata_str)
        return f"{key}:{metadata.get(key, 'null')}"

    def remove(self, project_id: int, key: str) -> bool:
        self.client.execute_query(
            """
            mutation RemoveMeta($id: Int!, $key: String!) {
                removeProjectMetadataByKey(input: { id: $id, key: $key }) {
                    id
                }
            }""",
            {"id": project_id, "key": key, }
        )
        return key

