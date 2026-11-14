import unittest

from ....common import dsl_exes_to_str, get_mock_gql_client
from gql.dsl import DSLQuery
from unittest.mock import MagicMock

import sys

sys.modules["ansible.utils.display"] = unittest.mock.Mock()
from .....plugins.module_utils.gqlEnvironment import Environment


class GqlEnvironmentNoBatchingTester(unittest.TestCase):
    """Guards against reintroducing batched queries for environments.

    This lives in the controller test group rather than alongside the Project
    tests in tests/unit/plugins/module_utils/, because gqlEnvironment imports
    ansible.errors, which ansible-test does not make importable in the
    target-side module_utils group.
    """

    def test_withVariables_queries_one_environment_per_request(self):
        client = get_mock_gql_client(
            query_dynamic_return_value={
                "environmentByKubernetesNamespaceName": {
                    "envVariables": [{"id": 1, "name": "SOME_VAR"}]
                }
            }
        )

        lagoonEnvironment = Environment(client)
        lagoonEnvironment.environments = [
            {"kubernetesNamespaceName": "p1-master"},
            {"kubernetesNamespaceName": "p2-dev"},
            {"kubernetesNamespaceName": "p3-stage"},
        ]
        lagoonEnvironment.withVariables(["id", "name"])

        assert client.execute_query_dynamic.call_count == 3, (
            f"expected 3 calls, got {client.execute_query_dynamic.call_count}"
        )

        expected = [
            """
{
  environmentByKubernetesNamespaceName(kubernetesNamespaceName: "p1-master") {
    envVariables {
      id
      name
    }
  }
}""",
            """
{
  environmentByKubernetesNamespaceName(kubernetesNamespaceName: "p2-dev") {
    envVariables {
      id
      name
    }
  }
}""",
            """
{
  environmentByKubernetesNamespaceName(kubernetesNamespaceName: "p3-stage") {
    envVariables {
      id
      name
    }
  }
}""",
        ]

        for call, want in zip(client.execute_query_dynamic.call_args_list, expected):
            assert len(call.args) == 1, f"expected 1 arg, got {len(call.args)}"
            assert isinstance(call.args[0], DSLQuery), (
                f"expected DSLQuery, got {type(call.args[0])}"
            )
            got = "\n" + dsl_exes_to_str(*call.args)
            assert got == want, f"got {got}"

        for environment in lagoonEnvironment.environments:
            assert environment["envVariables"] == [{"id": 1, "name": "SOME_VAR"}], (
                f"got {environment}"
            )

    def test_withProject_queries_one_environment_per_request(self):
        client = get_mock_gql_client(
            query_dynamic_return_value={
                "environmentByKubernetesNamespaceName": {
                    "project": {"name": "test-project"}
                }
            }
        )

        lagoonEnvironment = Environment(client)
        lagoonEnvironment.environments = [
            {"kubernetesNamespaceName": "p1-master"},
            {"kubernetesNamespaceName": "p2-dev"},
        ]
        lagoonEnvironment.withProject(["name"])

        assert client.execute_query_dynamic.call_count == 2, (
            f"expected 2 calls, got {client.execute_query_dynamic.call_count}"
        )

        for environment in lagoonEnvironment.environments:
            assert environment["project"] == {"name": "test-project"}

    def test_batch_size_is_accepted_but_warns(self):
        client = get_mock_gql_client(
            query_dynamic_return_value={
                "environmentByKubernetesNamespaceName": {
                    "kubernetes": {"id": 7, "name": "cluster-a"}
                }
            }
        )

        lagoonEnvironment = Environment(client)
        lagoonEnvironment.display = MagicMock()
        lagoonEnvironment.environments = [
            {"kubernetesNamespaceName": "p1-master"},
            {"kubernetesNamespaceName": "p2-dev"},
        ]
        lagoonEnvironment.withCluster(batch_size=50)

        # Still one request per environment.
        assert client.execute_query_dynamic.call_count == 2, (
            f"expected 2 calls, got {client.execute_query_dynamic.call_count}"
        )

        lagoonEnvironment.display.warning.assert_called_once()
        warned = str(lagoonEnvironment.display.warning.call_args)
        assert "batch_size is deprecated" in warned, f"got {warned}"

    def test_getDeployments_returns_none_when_environment_missing(self):
        client = get_mock_gql_client(
            query_dynamic_return_value={"environmentByKubernetesNamespaceName": None}
        )

        assert Environment(client).getDeployments("nope") is None

    def test_with_methods_noop_on_empty_environment_list(self):
        client = get_mock_gql_client()
        lagoonEnvironment = Environment(client)

        lagoonEnvironment.withCluster().withVariables().withProject().withDeployments()

        assert client.execute_query_dynamic.call_count == 0, (
            f"expected no calls, got {client.execute_query_dynamic.call_count}"
        )
