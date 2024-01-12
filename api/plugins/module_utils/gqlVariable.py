from .gql import GqlClient
from .gqlResourceBase import ResourceBase, VARIABLES_FIELDS


from gql.dsl import DSLQuery
from typing import List

class Variable(ResourceBase):

    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        super().__init__(client, options)

    def getForProjects(self, project_names: List[str], fields: List[str] = None) -> dict:
        res = {}

        if not fields or not len(fields):
            fields = VARIABLES_FIELDS

        resources = {}
        with self.client as (_, ds):
            # Build the fragment.
            var_fields = ds.Project.envVariables.select(
                getattr(ds.EnvKeyValue, fields[0]))
            if len(fields) > 1:
                for f in fields[1:]:
                    var_fields.select(getattr(ds.EnvKeyValue, f))

            field_queries = []
            for pName in project_names:
                # Build the main query.
                field_query = ds.Query.projectByName.args(
                    name=pName).alias(self.sanitiseForQueryAlias(pName))
                field_query.select(var_fields)
                field_queries.append(field_query)

            resources = self.queryResources(DSLQuery(*field_queries))

        for pName in project_names:
            try:
                res[pName] = resources.get(
                    self.sanitiseForQueryAlias(pName))['envVariables']
            except:
                res[pName] = None

        return res

    def addOrUpdateByName(self, projectName:str, environmentName: str, name:str, value:str, scope:str) -> dict:
        res = self.client.execute_query(
            """
            mutation addOrUpdateEnvVariableByName(
                $environment: String
                $project: String!
                $name: String!
                $value: String!
                $scope: EnvVariableScope!
            ) {
                addOrUpdateEnvVariableByName(input: {
                    project: $project
                    environment: $environment
                    scope: $scope
                    name: $name
                    value: $value
                }) {
                    id
                }
            }""",
            {
                "environment": environmentName,
                "project": projectName,
                "scope": scope,
                "name": name,
                "value": str(value),
            }
        )
        return res['addOrUpdateEnvVariableByName']

    def delete(self, id: int) -> bool:
        res = self.client.execute_query(
            """
            mutation DeleteEnvVar($id: Int!) {
                deleteEnvVariable(input: {id: $id})
            }""",
            {"id": id}
        )

        try:
            return res["deleteEnvVariable"] == "success"
        except KeyError:
            return False
