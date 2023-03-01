from .gql import GqlClient
from .gql import GqlClient
from .gqlResourceBase import ResourceBase

DEFAULT_DEPLOY_TARGET_WEIGHT = 0

class DeployTargetConfig(ResourceBase):

    def __init__(self, client: GqlClient, options: dict = {}) -> None:
        super().__init__(client, options)
    
    def add(self, project: int, branches: str, target: int, pullrequests: str, weight: int = DEFAULT_DEPLOY_TARGET_WEIGHT) -> bool:
        res = self.client.execute_query(
            """
            mutation addDeployTargetConfig(
                $project: Int!
                $branches: String!
                $target: Int!
                $pullrequests: String!
                $weight: Int
            ) {
                addDeployTargetConfig(input: {
                    project: $project
                    branches: $branches
                    pullrequests: $pullrequests
                    deployTarget: $target
                    weight: $weight
                }) {
                    id
                }
            }
            """,
            {
                "project": int(project),
                "branches": branches,
                "target": int(target),
                "pullrequests": pullrequests,
                "weight": int(weight)
            }
        )

        try:
            res["addDeloyTargetConfig"]
            return True
        except KeyError:
            return False

    def delete(self, project: int, id: int) -> bool:
        res = self.client.execute_query(
            """
            mutation deleteDeployTargetConfig(
                $project: Int! 
                $id: Int!
            ) { 
                deleteDeployTargetConfig(input: {
                project: $project
                id: $id
                })
            }
            """,
            {
                "project": project,
                "id": id
            }
        )

        try:
            return res["deleteDeployTargetConfig"] == "success"
        except KeyError:
            return False