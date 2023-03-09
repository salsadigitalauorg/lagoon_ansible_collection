from .gql import GqlClient
from .gqlResourceBase import ResourceBase, GROUPS_FIELDS


from gql.dsl import DSLQuery
from typing import List


class Group(ResourceBase):

    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        super().__init__(client, options)

    def get(self, project_names: List[str], fields: List[str] = None) -> dict:
        res = {}

        if not fields or not len(fields):
            fields = GROUPS_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            groups_fields = ds.Project.groups.select(
                getattr(ds.GroupInterface, fields[0]))
            if len(fields) > 1:
                for f in fields[1:]:
                    groups_fields.select(getattr(ds.GroupInterface, f))

            field_queries = []
            for pName in project_names:
                # Build the main query.
                field_query = ds.Query.projectByName.args(
                    name=pName).alias(self.sanitiseForQueryAlias(pName))
                field_query.select(groups_fields)
                field_queries.append(field_query)

            resources = self.queryResources(DSLQuery(*field_queries))

        for pName in project_names:
            try:
                res[pName] = resources.get(
                    self.sanitiseForQueryAlias(pName))['groups']
            except:
                res[pName] = None

        return res
