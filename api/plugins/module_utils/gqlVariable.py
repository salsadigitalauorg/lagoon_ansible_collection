from .gql import GqlClient
from .gqlResourceBase import ResourceBase

class Variable(ResourceBase):

    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        super().__init__(client, options)

    def add(self, type: str, type_id: int, name: str, value: str, scope: str) -> dict:
        res = self.client.execute_query(
            """
            mutation addEnvVariable(
                $type: EnvVariableType!
                $type_id: Int!
                $name: String!
                $value: String!
                $scope: EnvVariableScope!
            ) {
                addEnvVariable(input: {
                    type: $type
                    typeId: $type_id
                    scope: $scope
                    name: $name
                    value: $value
                }) {
                    id
                }
            }""",
            {
                "type": type,
                "type_id": int(type_id),
                "scope": scope,
                "name": name,
                "value": str(value),
            }
        )
        return res['addEnvVariable']

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
