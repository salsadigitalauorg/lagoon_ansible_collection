import inspect
import unittest

from .....plugins.module_utils.client import LagoonClient, is_type_reference

ENDPOINT = "https://api.example.com/graphql"


def client() -> LagoonClient:
    """A client with no credentials, so constructing it performs no I/O."""
    return LagoonClient(ENDPOINT)


class BuildDocumentTester(unittest.TestCase):
    def test_query_with_one_argument(self):
        assert client().build_document(
            "query", "projectByName", {"name": "my-project"}, ["id", "name"]
        ) == (
            "query projectByName($name: String!) "
            "{ projectByName(name: $name) { id name } }"
        )

    def test_query_with_a_nested_selection(self):
        assert client().build_document(
            "query",
            "projectByName",
            {"name": "my-project"},
            ["id", {"kubernetes": ["id", "name"]}],
        ) == (
            "query projectByName($name: String!) "
            "{ projectByName(name: $name) { id kubernetes { id name } } }"
        )

    def test_query_with_no_arguments_declares_none(self):
        assert (
            client().build_document("query", "allProjects", None, ["name"])
            == "query allProjects { allProjects { name } }"
        )

    def test_query_with_an_input_object_argument(self):
        assert client().build_document(
            "query", "allProjectsInGroup", {"input": {"name": "g"}}, ["name"]
        ) == (
            "query allProjectsInGroup($input: GroupInput) "
            "{ allProjectsInGroup(input: $input) { name } }"
        )

    def test_mutation_declares_its_input_type(self):
        assert client().build_document(
            "mutation", "updateProject", {"input": {"id": 1}}, ["id"]
        ) == (
            "mutation updateProject($input: UpdateProjectInput!) "
            "{ updateProject(input: $input) { id } }"
        )

    def test_mutation_with_several_arguments(self):
        document = client().build_document(
            "mutation",
            "taskDrushCacheClear",
            {"environment": 3},
            ["id"],
        )
        assert document == (
            "mutation taskDrushCacheClear($environment: Int!) "
            "{ taskDrushCacheClear(environment: $environment) { id } }"
        )

    def test_no_selection_set_when_fields_are_omitted(self):
        assert (
            client().build_document("query", "allProjects", None, None)
            == "query allProjects { allProjects }"
        )

    def test_values_never_reach_the_document(self):
        """The whole point of declaring variables.

        A value that would alter the query as GraphQL text has no effect on it,
        because the text only ever names the variable.
        """

        hostile = 'x") { id } mutation { deleteProject(input: {project: "y"'
        document = client().build_document(
            "query", "projectByName", {"name": hostile}, ["id"]
        )
        assert hostile not in document
        assert document == (
            "query projectByName($name: String!) { projectByName(name: $name) { id } }"
        )


class ArgTypesTester(unittest.TestCase):
    def test_arg_types_override_is_used(self):
        assert client().build_document(
            "query",
            "someFutureField",
            {"thing": 1},
            ["id"],
            arg_types={"thing": "Int!"},
        ) == (
            "query someFutureField($thing: Int!) "
            "{ someFutureField(thing: $thing) { id } }"
        )

    def test_unmapped_field_fails_clearly(self):
        with self.assertRaises(ValueError) as caught:
            client().build_document("query", "someFutureField", {"thing": 1}, ["id"])

        message = str(caught.exception)
        assert "someFutureField" in message
        assert "arg_types" in message

    def test_unknown_argument_on_a_known_field_fails(self):
        with self.assertRaises(ValueError) as caught:
            client().build_document("query", "projectByName", {"nmae": "x"}, ["id"])

        assert "nmae" in str(caught.exception)

    def test_a_mutation_field_is_not_resolved_from_the_query_map(self):
        with self.assertRaises(ValueError):
            client().build_document("mutation", "projectByName", {"name": "x"}, ["id"])

    def test_rejects_an_argument_name_that_is_not_a_name(self):
        with self.assertRaises(ValueError):
            client().build_document(
                "query",
                "someFutureField",
                {'name: "x") { id } #': 1},
                ["id"],
                arg_types={'name: "x") { id } #': "String!"},
            )

    def test_rejects_a_type_that_is_not_a_type_reference(self):
        with self.assertRaises(ValueError):
            client().build_document(
                "query",
                "someFutureField",
                {"thing": 1},
                ["id"],
                arg_types={
                    "thing": 'String!) { id } mutation x { deleteProject(e: "y"'
                },
            )

    def test_is_type_reference(self):
        for good in [
            "String",
            "String!",
            "Int",
            "[EnvType]",
            "[String!]!",
            "GroupInput",
        ]:
            assert is_type_reference(good), good

        for bad in ["String!) {", "String x", "", None, 'name: "x"', "String;"]:
            assert not is_type_reference(bad), bad


class CertificateVerificationTester(unittest.TestCase):
    """Guards the Critical finding that the previous client shipped with
    certificate verification off by default.

    Every request carries a Lagoon bearer token in an Authorization header, so
    an unverified connection hands that token to anything on the path. There
    must be no way to ask this client for one.
    """

    def test_constructor_takes_no_verification_option(self):
        parameters = inspect.signature(LagoonClient.__init__).parameters
        for name in ("validate_certs", "verify", "insecure", "verify_ssl"):
            assert name not in parameters, f"LagoonClient accepts {name}"

    def test_passing_validate_certs_is_rejected(self):
        with self.assertRaises(TypeError):
            LagoonClient(ENDPOINT, validate_certs=False)

    def test_requests_are_not_sent_with_verification_disabled(self):
        lagoon = client()
        sent = {}

        def post(url, **kwargs):
            sent.update(kwargs)
            raise AssertionError("stop here")

        lagoon.session.post = post
        with self.assertRaises(AssertionError):
            lagoon.execute("query { me }")

        assert "verify" not in sent or sent["verify"] is True
        assert lagoon.session.verify is True
