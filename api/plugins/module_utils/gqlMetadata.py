import json

from .gql import GqlClient
from .gqlResourceBase import ResourceBase


from gql.dsl import DSLQuery
from typing import List, Union


class Metadata(ResourceBase):
    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        super().__init__(client, options)

    def getForProject(self, project_name: str) -> dict:
        """
        Get the metadata for a single project.
        """

        resources = {}
        with self.client as (_, ds):
            # Build the main query. No alias: a single root field per request
            # means the response is keyed by the query name itself.
            field_query = ds.Query.projectByName.args(name=project_name)
            field_query.select(ds.Project.metadata)

            resources = self.queryResources(DSLQuery(field_query))

        try:
            metadata = resources["projectByName"]["metadata"]
            if not isinstance(metadata, dict):
                metadata = json.loads(metadata)
            self.unpack(metadata)
            return metadata
        except (KeyError, TypeError, json.decoder.JSONDecodeError):
            return None

    def get(self, project_names: List[str] = []) -> dict:
        res = {}

        if len(project_names) > 0:
            total = len(project_names)
            self.v(f"Fetching metadata for {total} projects")

            # Hold a single session open for the whole loop so the underlying
            # requests.Session - and therefore the HTTP connection - is reused.
            with self.client:
                for i, pName in enumerate(project_names):
                    self.vv(f"Fetching metadata for {pName} ({i + 1}/{total})")
                    res[pName] = self.getForProject(pName)
        else:
            resources = self.client.execute_query(
                """
                query {
                    allProjects {
                        id
                        name
                        metadata
                    }
                }"""
            )
            if not resources.get("allProjects"):
                return res

            for p in resources.get("allProjects"):
                metadata = p["metadata"]
                if not isinstance(metadata, dict):
                    metadata = json.loads(metadata)
                self.unpack(metadata)
                res[p["name"]] = metadata

        return res

    def update(self, project_id: int, key: str, value: Union[str, list, dict]) -> dict:
        # Encode non-string values.
        if not isinstance(value, str):
            value = json.dumps(value)
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
            {"id": project_id, "key": key, "value": value},
        )
        metadata = res.get("updateProjectMetadata", {}).get("metadata", None)
        if not metadata:
            return f"{key}:null"

        if not isinstance(metadata, dict):
            metadata = json.loads(metadata)
        self.unpack(metadata)
        return f"{key}:{metadata.get(key, 'null')}"

    def remove(self, project_id: int, key: str) -> bool:
        self.client.execute_query(
            """
            mutation RemoveMeta($id: Int!, $key: String!) {
                removeProjectMetadataByKey(input: { id: $id, key: $key }) {
                    id
                }
            }""",
            {
                "id": project_id,
                "key": key,
            },
        )
        return key

    def unpack(self, metadata: dict):
        """
        Iterates through the metadata items and attempts
        to decode the values as json
        """
        for key, value in metadata.items():
            try:
                metadata[key] = json.loads(value, parse_int=str, parse_float=str)
            # Scalar values cannot be decoded and will throw the following error.
            except json.decoder.JSONDecodeError:
                continue
            # List & dict cannot be decoded either and will throw a different error.
            except TypeError:
                continue
