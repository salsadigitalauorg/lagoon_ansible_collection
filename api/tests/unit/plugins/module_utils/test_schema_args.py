import importlib.util
import os
import unittest

from .....plugins.module_utils.schema_args import MUTATION_ARG_TYPES, QUERY_ARG_TYPES

COLLECTION_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
)
GENERATOR = os.path.join(COLLECTION_ROOT, "scripts", "gen_schema_args.py")


def load_generator():
    spec = importlib.util.spec_from_file_location("gen_schema_args", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SchemaArgsTester(unittest.TestCase):
    """Keeps the committed map honest.

    The map is generated rather than introspected so that no schema fetch
    happens before the first useful request. The cost of that is this test: a
    schema refresh without a regeneration has to fail here, in CI, rather than
    at runtime against a real Lagoon.
    """

    def setUp(self):
        self.generator = load_generator()
        from graphql import build_ast_schema, parse

        with open(
            os.path.join(COLLECTION_ROOT, "tests", "common", "schema.graphql")
        ) as fh:
            self.schema = build_ast_schema(parse(fh.read()))

    def test_query_arg_types_match_the_schema(self):
        assert QUERY_ARG_TYPES == self.generator.arg_types(self.schema, "Query"), (
            "schema.graphql and schema_args.py have diverged; re-run "
            "python api/scripts/gen_schema_args.py"
        )

    def test_mutation_arg_types_match_the_schema(self):
        assert MUTATION_ARG_TYPES == self.generator.arg_types(
            self.schema, "Mutation"
        ), (
            "schema.graphql and schema_args.py have diverged; re-run "
            "python api/scripts/gen_schema_args.py"
        )

    def test_the_fields_phase_1_relies_on_are_present(self):
        assert QUERY_ARG_TYPES["projectByName"] == {"name": "String!"}
        assert QUERY_ARG_TYPES["allProjectsInGroup"] == {"input": "GroupInput"}
        assert QUERY_ARG_TYPES["environmentByKubernetesNamespaceName"] == {
            "kubernetesNamespaceName": "String!"
        }
        assert QUERY_ARG_TYPES["groupByName"] == {"name": "String!"}
        assert MUTATION_ARG_TYPES["updateProject"] == {"input": "UpdateProjectInput!"}

    def test_fields_without_arguments_are_omitted(self):
        """A field needing no variable declaration needs no entry."""
        assert "me" not in QUERY_ARG_TYPES

    def test_the_non_uniform_mutations_are_covered_by_the_same_map(self):
        """The handful that do not follow input: XInput! need no special case."""
        for field in [
            "invokeRegisteredTask",
            "taskDrushCacheClear",
            "updateEnvironmentDeployTarget",
            "deleteAdvancedTaskDefinition",
        ]:
            assert field in MUTATION_ARG_TYPES, field
            assert MUTATION_ARG_TYPES[field], field
