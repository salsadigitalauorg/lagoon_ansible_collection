from .gql import GqlClient
from .gqlResourceBase import ResourceBase, GROUPS_FIELDS


from gql.dsl import DSLQuery
from typing import List


class Group(ResourceBase):
    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        super().__init__(client, options)

    def get(self, project_name: str, fields: List[str] = None) -> List[dict]:
        if not fields or not len(fields):
            fields = GROUPS_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            groups_fields = ds.Project.groups.select(
                getattr(ds.GroupInterface, fields[0])
            )
            if len(fields) > 1:
                for f in fields[1:]:
                    groups_fields.select(getattr(ds.GroupInterface, f))

            # Build the main query. No alias: a single root field per request
            # means the response is keyed by the query name itself.
            field_query = ds.Query.projectByName.args(name=project_name)
            field_query.select(groups_fields)

            resources = self.queryResources(DSLQuery(field_query))

        try:
            return resources["projectByName"]["groups"]
        except (KeyError, TypeError):
            return None
