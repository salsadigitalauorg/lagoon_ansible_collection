import unittest

from ....common import dsl_exes_to_str, get_mock_gql_client
from .....plugins.module_utils.gqlProject import Project
from gql.dsl import DSLQuery
from unittest.mock import MagicMock

import sys

sys.modules["ansible.utils.display"] = unittest.mock.Mock()


class GqlProjectNoBatchingTester(unittest.TestCase):
    """Guards against reintroducing batched queries.

    The Lagoon API degrades sharply on a single document carrying many aliased
    root fields, so every subresource is fetched one project per request. These
    tests fail loudly if that is ever collapsed back into a batch.
    """

    def test_withEnvironments_queries_one_project_per_request(self):
        client = get_mock_gql_client(
            query_dynamic_return_value={
                "projectByName": {"environments": [{"id": 1, "name": "master"}]}
            }
        )

        lagoonProject = Project(client)
        # 'p-2' carries a hyphen: the old implementation had to sanitise that
        # into a query alias. A single un-aliased root field needs no alias, so
        # the name must appear verbatim.
        lagoonProject.projects = [{"name": "p1"}, {"name": "p-2"}, {"name": "p3"}]
        lagoonProject.withEnvironments(["id", "name"])

        assert client.execute_query_dynamic.call_count == 3, (
            f"expected 3 calls, got {client.execute_query_dynamic.call_count}"
        )

        expected = [
            """
{
  projectByName(name: "p1") {
    environments {
      id
      name
    }
  }
}""",
            """
{
  projectByName(name: "p-2") {
    environments {
      id
      name
    }
  }
}""",
            """
{
  projectByName(name: "p3") {
    environments {
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

        # Results are still distributed back onto the right projects.
        for project in lagoonProject.projects:
            assert project["environments"] == [{"id": 1, "name": "master"}], (
                f"got {project}"
            )

    def test_withCluster_queries_one_project_per_request(self):
        client = get_mock_gql_client(
            query_dynamic_return_value={
                "projectByName": {"kubernetes": {"id": 7, "name": "cluster-a"}}
            }
        )

        lagoonProject = Project(client)
        lagoonProject.projects = [{"name": "p1"}, {"name": "p2"}]
        lagoonProject.withCluster()

        assert client.execute_query_dynamic.call_count == 2, (
            f"expected 2 calls, got {client.execute_query_dynamic.call_count}"
        )

        for project in lagoonProject.projects:
            assert project["kubernetes"] == {"id": 7, "name": "cluster-a"}
            # openshift is kept as an alias of kubernetes for compatibility.
            assert project["openshift"] == {"id": 7, "name": "cluster-a"}

    def test_batch_size_is_accepted_but_warns(self):
        """
        batch_size is retained so existing playbooks keep working, but it must
        have no effect and must tell the user it is going away.
        """
        client = get_mock_gql_client(
            query_dynamic_return_value={
                "projectByName": {"kubernetes": {"id": 7, "name": "cluster-a"}}
            }
        )

        lagoonProject = Project(client)
        lagoonProject.display = MagicMock()
        lagoonProject.projects = [{"name": "p1"}, {"name": "p2"}]
        lagoonProject.withCluster(batch_size=50)

        # Still one request per project - the argument did not re-enable batching.
        assert client.execute_query_dynamic.call_count == 2, (
            f"expected 2 calls, got {client.execute_query_dynamic.call_count}"
        )

        lagoonProject.display.warning.assert_called_once()
        warned = str(lagoonProject.display.warning.call_args)
        assert "batch_size is deprecated" in warned, f"got {warned}"

    def test_no_batch_size_does_not_warn(self):
        client = get_mock_gql_client(
            query_dynamic_return_value={
                "projectByName": {"kubernetes": {"id": 7, "name": "cluster-a"}}
            }
        )

        lagoonProject = Project(client)
        lagoonProject.display = MagicMock()
        lagoonProject.projects = [{"name": "p1"}]
        lagoonProject.withCluster()

        lagoonProject.display.warning.assert_not_called()

    def test_getCluster_returns_none_when_project_missing(self):
        """
        A project that does not resolve must yield None rather than raising -
        one failed lookup should not abort a whole inventory refresh.
        """
        client = get_mock_gql_client(query_dynamic_return_value={"projectByName": None})

        assert Project(client).getCluster("nope") is None

    def test_with_methods_noop_on_empty_project_list(self):
        client = get_mock_gql_client()
        lagoonProject = Project(client)

        lagoonProject.withCluster().withEnvironments().withVariables().withGroups()

        assert client.execute_query_dynamic.call_count == 0, (
            f"expected no calls, got {client.execute_query_dynamic.call_count}"
        )
