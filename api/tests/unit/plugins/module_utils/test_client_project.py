import unittest
from unittest.mock import MagicMock

from .....plugins.module_utils.client import LagoonClient
from .....plugins.module_utils.fields import PROJECT_FIELDS

ENDPOINT = "https://api.example.com/graphql"


def client(data=None) -> LagoonClient:
    lagoon = LagoonClient(ENDPOINT)
    lagoon.execute = MagicMock(return_value=data)
    return lagoon


def document(lagoon) -> str:
    return lagoon.execute.call_args.args[0]


class ListProjectsTester(unittest.TestCase):
    """The narrow default on the list queries is a load constraint, not a
    style choice.

    allProjects spans every project on the estate; widening its selection
    slows the request down and past a point fails it outright on a large
    production Lagoon. A unit test is the only place that is caught.
    """

    def test_list_projects_selects_name_and_nothing_else(self):
        lagoon = client({"allProjects": [{"name": "p1"}]})

        assert lagoon.listProjects() == [{"name": "p1"}]
        assert document(lagoon) == "query allProjects { allProjects { name } }"

    def test_list_projects_in_group_selects_name_and_nothing_else(self):
        lagoon = client({"allProjectsInGroup": [{"name": "p1"}]})

        assert lagoon.listProjectsInGroup("my-group") == [{"name": "p1"}]
        assert document(lagoon) == (
            "query allProjectsInGroup($input: GroupInput) "
            "{ allProjectsInGroup(input: $input) { name } }"
        )
        assert lagoon.execute.call_args.args[1] == {"input": {"name": "my-group"}}

    def test_a_caller_can_still_widen_the_list_query_explicitly(self):
        lagoon = client({"allProjects": []})
        lagoon.listProjects(fields=["id", "name", "gitUrl"])

        assert (
            document(lagoon) == "query allProjects { allProjects { id name gitUrl } }"
        )


class GetProjectTester(unittest.TestCase):
    def test_default_selection_omits_metadata(self):
        lagoon = client({"projectByName": {"id": 1}})
        lagoon.getProject("p1")

        rendered = document(lagoon)
        assert "metadata" not in rendered
        for field in PROJECT_FIELDS:
            if field != "metadata":
                assert field in rendered, field

    def test_metadata_is_fetched_on_its_own(self):
        lagoon = client({"projectByName": {"metadata": {"a": "b"}}})

        assert lagoon.getProjectMetadata("p1") == {"a": "b"}
        assert document(lagoon) == (
            "query projectByName($name: String!) "
            "{ projectByName(name: $name) { metadata } }"
        )

    def test_extra_fields_adds_to_the_default(self):
        lagoon = client({"projectByName": {}})
        lagoon.getProject("p1", extra_fields=["sharedBaasBucket"])

        rendered = document(lagoon)
        assert "sharedBaasBucket" in rendered
        assert "gitUrl" in rendered

    def test_extra_fields_can_add_a_nested_selection(self):
        lagoon = client({"projectByName": {}})
        lagoon.getProject(
            "p1", extra_fields=[{"deployTargetConfigs": ["id", "weight"]}]
        )

        assert "deployTargetConfigs { id weight }" in document(lagoon)

    def test_fields_replaces_the_default(self):
        lagoon = client({"projectByName": {}})
        lagoon.getProject("p1", fields=["id", "name"])

        assert document(lagoon) == (
            "query projectByName($name: String!) "
            "{ projectByName(name: $name) { id name } }"
        )

    def test_passing_both_raises(self):
        with self.assertRaises(ValueError):
            client().getProject("p1", fields=["id"], extra_fields=["name"])

    def test_a_missing_project_is_none_not_an_exception(self):
        assert client({"projectByName": None}).getProject("nope") is None
        assert client(None).getProject("nope") is None


class SubresourceTester(unittest.TestCase):
    def test_environments(self):
        lagoon = client({"projectByName": {"environments": [{"id": 3}]}})

        assert lagoon.getProjectEnvironments("p1", ["id"]) == [{"id": 3}]
        assert document(lagoon) == (
            "query projectByName($name: String!) "
            "{ projectByName(name: $name) { environments { id } } }"
        )

    def test_groups_need_no_inline_fragments(self):
        lagoon = client({"projectByName": {"groups": [{"id": "g"}]}})

        lagoon.getProjectGroups("p1")
        assert document(lagoon) == (
            "query projectByName($name: String!) "
            "{ projectByName(name: $name) { groups { id name type } } }"
        )

    def test_cluster(self):
        lagoon = client({"projectByName": {"kubernetes": {"id": 1, "name": "c"}}})

        assert lagoon.getProjectCluster("p1") == {"id": 1, "name": "c"}

    def test_a_project_with_no_environments_is_none(self):
        assert client({"projectByName": None}).getProjectEnvironments("p1") is None


class VariableReadTester(unittest.TestCase):
    def test_project_variables_are_read_with_output_muted(self):
        """The response holds every variable value for the project, none of
        them known in advance, so redacting by value cannot mask them."""

        lagoon = client({"projectByName": {"envVariables": [{"value": "s3cret"}]}})
        seen = {}

        def execute(*args, **kwargs):
            seen["display"] = lagoon.display
            return {"projectByName": {"envVariables": [{"value": "s3cret"}]}}

        lagoon.display = "a-display"
        lagoon.execute = execute

        assert lagoon.getProjectVariables("p1") == [{"value": "s3cret"}]
        assert seen["display"] is None
        assert lagoon.display == "a-display"

    def test_environment_variables_are_read_with_output_muted(self):
        lagoon = client(None)
        seen = {}

        def execute(*args, **kwargs):
            seen["display"] = lagoon.display
            return {"environmentByKubernetesNamespaceName": {"envVariables": []}}

        lagoon.display = "a-display"
        lagoon.execute = execute

        assert lagoon.getEnvironmentVariables("p1-master") == []
        assert seen["display"] is None
        assert lagoon.display == "a-display"


class EnvironmentMethodTester(unittest.TestCase):
    def test_environment_cluster(self):
        lagoon = client(
            {"environmentByKubernetesNamespaceName": {"kubernetes": {"id": 2}}}
        )

        assert lagoon.getEnvironmentCluster("p1-master") == {"id": 2}
        assert document(lagoon) == (
            "query environmentByKubernetesNamespaceName"
            "($kubernetesNamespaceName: String!) "
            "{ environmentByKubernetesNamespaceName"
            "(kubernetesNamespaceName: $kubernetesNamespaceName) "
            "{ kubernetes { id name } } }"
        )

    def test_get_environment(self):
        lagoon = client({"environmentByKubernetesNamespaceName": {"id": 4}})

        assert lagoon.getEnvironment("p1-master", ["id"]) == {"id": 4}
