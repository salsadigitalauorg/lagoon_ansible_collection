import unittest
from unittest.mock import MagicMock

from .....plugins.module_utils.client import LagoonClient

ENDPOINT = "https://api.example.com/graphql"


def client(data=None) -> LagoonClient:
    lagoon = LagoonClient(ENDPOINT)
    lagoon.execute = MagicMock(return_value=data)
    return lagoon


def document(lagoon) -> str:
    return lagoon.execute.call_args.args[0]


def variables(lagoon) -> dict:
    return lagoon.execute.call_args.args[1]


class EnvironmentDeploymentsTester(unittest.TestCase):
    def test_document_declares_limit_and_namespace(self):
        lagoon = client(
            {"environmentByKubernetesNamespaceName": {"deployments": [{"id": 1}]}}
        )

        lagoon.getEnvironmentDeployments("p1-master", limit=1)

        assert document(lagoon) == (
            "query environmentDeployments"
            "($kubernetesNamespaceName: String!, $limit: Int) "
            "{ environmentByKubernetesNamespaceName"
            "(kubernetesNamespaceName: $kubernetesNamespaceName) "
            "{ deployments(limit: $limit) { "
            "bulkId bulkName completed created id name started status uiLink"
            " } } }"
        )
        assert variables(lagoon) == {
            "kubernetesNamespaceName": "p1-master",
            "limit": 1,
        }

    def test_limit_none_is_sent_as_a_null_variable_not_dropped(self):
        lagoon = client({"environmentByKubernetesNamespaceName": {"deployments": []}})

        lagoon.getEnvironmentDeployments("p1-master")

        assert variables(lagoon) == {
            "kubernetesNamespaceName": "p1-master",
            "limit": None,
        }
        assert "$limit: Int" in document(lagoon)

    def test_a_missing_environment_is_none(self):
        lagoon = client({"environmentByKubernetesNamespaceName": None})
        assert lagoon.getEnvironmentDeployments("nope") is None

    def test_an_environment_with_no_deployments_is_an_empty_list(self):
        lagoon = client({"environmentByKubernetesNamespaceName": {"deployments": []}})
        assert lagoon.getEnvironmentDeployments("p1-master") == []

    def test_custom_fields_are_used(self):
        lagoon = client(
            {
                "environmentByKubernetesNamespaceName": {
                    "deployments": [{"status": "complete"}]
                }
            }
        )

        result = lagoon.getEnvironmentDeployments("p1-master", fields=["status"])

        assert result == [{"status": "complete"}]
        assert "deployments(limit: $limit) { status }" in document(lagoon)


if __name__ == "__main__":
    unittest.main()
