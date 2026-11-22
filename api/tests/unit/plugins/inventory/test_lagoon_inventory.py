import unittest
from unittest.mock import MagicMock, patch

from .....plugins.inventory.lagoon import ENVIRONMENT_FIELDS, InventoryModule

MODULE = "ansible_collections.lagoon.api.plugins.inventory.lagoon"

API_TOKEN = "a-very-secret-api-token"
PRIVATE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nsecret-key-material\n"


def lagoon_config(**overrides):
    config = {
        "api_endpoint": "https://api.example.com/graphql",
        "api_token": API_TOKEN,
        "ssh_private_key": PRIVATE_KEY,
        "ssh_host": "ssh.example.com",
        "ssh_port": "32222",
        "headers": {},
    }
    config.update(overrides)
    return config


def mock_api(projects=None, environments=None):
    """A client whose typed methods return fixed data."""

    api = MagicMock()
    api.errors = []
    api.listProjects.return_value = projects or [{"name": "p1"}]
    api.listProjectsInGroup.return_value = projects or [{"name": "p1"}]
    api.getProject.side_effect = lambda name, *a, **k: {
        "id": 1,
        "name": name,
        "gitUrl": f"git@example.com:{name}.git",
    }
    api.getProjectMetadata.return_value = {"tier": "gold", "weight": "1"}
    api.getProjectEnvironments.return_value = (
        environments
        if environments is not None
        else [
            {
                "id": 3,
                "name": "master",
                "kubernetesNamespaceName": "p1-master",
                "environmentType": "production",
                "route": "https://example.com",
                "routes": "https://example.com",
            }
        ]
    )
    api.getProjectGroups.return_value = [{"id": "g1", "name": "grp", "type": "null"}]
    api.getProjectVariables.return_value = [
        {"id": 1, "name": "PROJECT_VAR", "value": "v", "scope": "RUNTIME"}
    ]
    api.getEnvironmentCluster.return_value = {"id": 7, "name": "cluster-a"}
    api.getEnvironmentVariables.return_value = [
        {"id": 2, "name": "ENV_VAR", "value": "w", "scope": "RUNTIME"}
    ]
    return api


def inventory_module():
    module = InventoryModule()
    module._vars = {}
    module.display = MagicMock()
    module.all_objects = []
    return module


def fetch(config=None, projects=None, environments=None, groups=None):
    """Run fetch_objects against a mocked client, returning (module, api)."""

    module = inventory_module()
    api = mock_api(projects, environments)

    with patch(f"{MODULE}.LagoonClient", return_value=api) as client:
        with patch(f"{MODULE}.LagoonCredentials") as credentials:
            config = lagoon_config() if config is None else config
            if groups is not None:
                config["filter_groups"] = groups
            module.fetch_objects([config])

    return module, api, client, credentials


def walk_keys(obj):
    """Every dict key anywhere in a nested structure."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from walk_keys(value)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from walk_keys(item)


def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from walk_strings(value)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from walk_strings(item)


class CachedCredentialsTester(unittest.TestCase):
    """The cache payload is written to cache_connection in cleartext - the
    examples put it at /tmp/lagoon_inventory with a 7200 second timeout.

    The whole per-Lagoon config dict used to go in, so anyone setting
    api_token or ssh_private_key in lagoon.yml had that credential written to
    a predictable path in the clear. Only what collect_host_vars reads is
    cached now.
    """

    def test_no_credential_keys_at_any_depth(self):
        module, _, _, _ = fetch()

        keys = set(walk_keys(module.all_objects))
        for forbidden in [
            "api_token",
            "lagoon_api_token",
            "ssh_private_key",
            "ssh_private_key_file",
            "token",
            "headers",
        ]:
            assert forbidden not in keys, f"{forbidden} reached the cache payload"

    def test_no_credential_values_at_any_depth(self):
        module, _, _, _ = fetch()

        for value in walk_strings(module.all_objects):
            assert API_TOKEN not in value
            assert "secret-key-material" not in value

    def test_only_the_connection_details_host_vars_need_are_cached(self):
        module, _, _, _ = fetch()

        assert module.all_objects[0]["lagoon"] == {
            "ssh_host": "ssh.example.com",
            "ssh_port": "32222",
        }

    def test_the_payload_shape_is_unchanged(self):
        """A cache written by the previous version must stay readable, so the
        three top-level keys populate() reads are preserved."""

        module, _, _, _ = fetch()

        assert set(module.all_objects[0]) == {
            "lagoon",
            "project_list",
            "project_environments",
        }


class TokenHandlingTester(unittest.TestCase):
    def test_credentials_are_passed_through_rather_than_a_token_fetched(self):
        _, _, client, credentials = fetch()

        kwargs = credentials.call_args.kwargs
        assert kwargs["token"] == API_TOKEN
        assert kwargs["ssh_private_key"] == PRIVATE_KEY
        assert kwargs["ssh_host"] == "ssh.example.com"
        assert kwargs["ssh_port"] == "32222"

        assert client.call_args.kwargs["exit_on_error"] is True

    def test_a_missing_token_is_no_longer_an_error(self):
        """The client mints one lazily, so nothing has to be pre-fetched."""

        config = lagoon_config()
        del config["api_token"]
        del config["ssh_private_key"]

        module, _, _, credentials = fetch(config=config)

        assert credentials.call_args.kwargs["token"] is None
        assert len(module.all_objects) == 1

    def test_the_old_token_fetching_method_is_gone(self):
        assert not hasattr(InventoryModule, "fetch_lagoon_api_token")

    def test_a_missing_endpoint_still_fails(self):
        config = lagoon_config()
        del config["api_endpoint"]

        from ansible.errors import AnsibleError

        with self.assertRaises(AnsibleError):
            fetch(config=config)


class ProjectFetchingTester(unittest.TestCase):
    def test_the_list_query_is_used_only_to_enumerate_names(self):
        _, api, _, _ = fetch()

        api.listProjects.assert_called_once_with()
        api.getProject.assert_called_once_with("p1")

    def test_projects_are_de_duplicated_before_subresources_are_fetched(self):
        """A project in two filter_groups costs one set of requests, not two.

        Previously the dedupe happened on fully-populated project dicts, so
        the second copy had already been paid for.
        """

        module = inventory_module()
        api = mock_api()
        api.listProjectsInGroup.side_effect = [
            [{"name": "shared"}, {"name": "only-a"}],
            [{"name": "shared"}, {"name": "only-b"}],
        ]

        with patch(f"{MODULE}.LagoonClient", return_value=api):
            with patch(f"{MODULE}.LagoonCredentials"):
                module.fetch_objects([lagoon_config(filter_groups=["a", "b"])])

        fetched = [c.args[0] for c in api.getProject.call_args_list]
        assert fetched == ["shared", "only-a", "only-b"]
        assert len(module.all_objects[0]["project_list"]) == 3

    def test_filter_groups_as_a_comma_separated_string(self):
        module = inventory_module()
        api = mock_api()

        with patch(f"{MODULE}.LagoonClient", return_value=api):
            with patch(f"{MODULE}.LagoonCredentials"):
                module.fetch_objects([lagoon_config(filter_groups="a,b")])

        assert [c.args[0] for c in api.listProjectsInGroup.call_args_list] == ["a", "b"]

    def test_environments_are_requested_with_the_fields_the_inventory_reads(self):
        _, api, _, _ = fetch()

        api.getProjectEnvironments.assert_called_once_with("p1", ENVIRONMENT_FIELDS)

    def test_the_project_dict_carries_the_same_keys_as_before(self):
        module, _, _, _ = fetch()

        project = module.all_objects[0]["project_list"][0]
        for key in [
            "id",
            "name",
            "gitUrl",
            "metadata",
            "environments",
            "groups",
            "envVariables",
        ]:
            assert key in project, key

    def test_environments_are_keyed_by_project_name(self):
        module, _, _, _ = fetch()

        assert list(module.all_objects[0]["project_environments"]) == ["p1"]

    def test_cluster_is_set_on_both_keys(self):
        module, _, _, _ = fetch()

        environment = module.all_objects[0]["project_environments"]["p1"][0]
        assert environment["kubernetes"] == {"id": 7, "name": "cluster-a"}
        assert environment["openshift"] == {"id": 7, "name": "cluster-a"}

    def test_the_environment_still_carries_its_project_name(self):
        """Part of the lagoon_environment host var. Set locally now rather
        than fetched, since iterating projects already establishes it."""

        module, _, _, _ = fetch()

        environment = module.all_objects[0]["project_environments"]["p1"][0]
        assert environment["project"] == {"name": "p1"}

    def test_the_environment_project_is_not_queried(self):
        _, api, _, _ = fetch()

        api.getEnvironmentProject.assert_not_called()

    def test_a_project_with_no_environments_is_still_listed(self):
        module, api, _, _ = fetch(environments=[])

        assert len(module.all_objects[0]["project_list"]) == 1
        assert module.all_objects[0]["project_environments"] == {}
        api.getEnvironmentCluster.assert_not_called()

    def test_a_null_environment_is_skipped(self):
        module, _, _, _ = fetch(environments=[None])

        assert module.all_objects[0]["project_environments"] == {}

    def test_null_environments_from_the_api_are_tolerated(self):
        module, _, _, _ = fetch(environments=None)
        assert module.all_objects[0]["project_environments"]["p1"]

    def test_a_project_that_disappears_between_calls_is_skipped(self):
        module = inventory_module()
        api = mock_api()
        api.getProject.side_effect = lambda name, *a, **k: None

        with patch(f"{MODULE}.LagoonClient", return_value=api):
            with patch(f"{MODULE}.LagoonCredentials"):
                module.fetch_objects([lagoon_config()])

        assert module.all_objects[0]["project_list"] == []


class ErrorReportingTester(unittest.TestCase):
    def test_api_errors_become_an_ansible_error_naming_the_project(self):
        from ansible.errors import AnsibleError

        from .....plugins.module_utils.client import LagoonApiError

        module = inventory_module()
        api = mock_api()
        api.getProject.side_effect = LagoonApiError([{"message": "boom"}])

        with patch(f"{MODULE}.LagoonClient", return_value=api):
            with patch(f"{MODULE}.LagoonCredentials"):
                with self.assertRaises(AnsibleError) as caught:
                    module.fetch_objects([lagoon_config()])

        assert "-vvv" in str(caught.exception)
        # The failing project is named in both the operator-facing error line
        # and the raised message.
        assert "p1" in str(module.display.error.call_args)
        assert "p1" in str(caught.exception)

    def test_a_failing_project_stops_the_refresh(self):
        """Fail fast rather than build a partial inventory.

        A play running against a silently incomplete host list is worse than
        a play that does not run, so the first failing project ends it.
        """

        from ansible.errors import AnsibleError

        from .....plugins.module_utils.client import LagoonApiError

        module = inventory_module()
        api = mock_api()
        api.listProjects.return_value = [{"name": "p1"}, {"name": "p2"}]

        def getProject(name, *args, **kwargs):
            if name == "p1":
                raise LagoonApiError([{"message": "denied"}])
            return {"id": 1, "name": name, "gitUrl": "g"}

        api.getProject.side_effect = getProject

        with patch(f"{MODULE}.LagoonClient", return_value=api):
            with patch(f"{MODULE}.LagoonCredentials"):
                with self.assertRaises(AnsibleError):
                    module.fetch_objects([lagoon_config()])

        attempted = [c.args[0] for c in api.getProject.call_args_list]
        assert attempted == ["p1"], attempted
        # Nothing half-built is left behind for populate() to read.
        assert module.all_objects == []

    def test_a_failing_list_query_is_reported_separately(self):
        from ansible.errors import AnsibleError

        from .....plugins.module_utils.client import LagoonApiError

        module = inventory_module()
        api = mock_api()
        api.listProjects.side_effect = LagoonApiError([{"message": "boom"}])

        with patch(f"{MODULE}.LagoonClient", return_value=api):
            with patch(f"{MODULE}.LagoonCredentials"):
                with self.assertRaises(AnsibleError) as caught:
                    module.fetch_objects([lagoon_config()])

        assert "list of projects" in str(caught.exception)


class ValidationTester(unittest.TestCase):
    def test_lagoons_must_be_a_list(self):
        from ansible.errors import AnsibleError

        with self.assertRaises(AnsibleError):
            inventory_module().fetch_objects({"not": "a list"})

    def test_each_lagoon_must_be_a_dict(self):
        from ansible.errors import AnsibleError

        with self.assertRaises(AnsibleError):
            inventory_module().fetch_objects(["not-a-dict"])

    def test_only_ssh_transport_is_supported(self):
        from ansible.errors import AnsibleError

        with self.assertRaises(AnsibleError):
            inventory_module().fetch_objects([lagoon_config(transport="kubectl")])

    def test_no_lagoons_is_a_no_op(self):
        module = inventory_module()
        module.fetch_objects(None)
        assert module.all_objects == []


class HostVarsTester(unittest.TestCase):
    def test_collect_host_vars_consumes_what_fetch_objects_produces(self):
        """The contract between the two halves of the module, and the thing a
        change to the fetch shape would break three layers away."""

        module, _, _, _ = fetch()
        objects = module.all_objects[0]
        project = objects["project_list"][0]
        environment = objects["project_environments"]["p1"][0]

        host_vars = module.collect_host_vars(
            "p1-master", environment, project, objects["lagoon"]
        )

        assert host_vars["project_name"] == "p1"
        assert host_vars["cluster_id"] == 7
        assert host_vars["cluster_name"] == "cluster-a"
        assert host_vars["git_url"] == "git@example.com:p1.git"
        assert host_vars["project_variables"] == {"PROJECT_VAR": "v"}
        assert host_vars["environment_variables"] == {"ENV_VAR": "w"}
        assert host_vars["lagoon_groups"] == [
            {"id": "g1", "name": "grp", "type": "null"}
        ]
        # literal_eval on each value is long-standing behaviour: Lagoon
        # returns metadata as JSON-encoded strings.
        assert host_vars["metadata"] == {"tier": "gold", "weight": 1}
        assert host_vars["ansible_host"] == "ssh.example.com"
        assert host_vars["ansible_port"] == "32222"

    def test_populate_walks_the_payload(self):
        module, _, _, _ = fetch()
        module.inventory = MagicMock()

        module.populate()

        module.inventory.add_host.assert_called_once_with("p1-master")
