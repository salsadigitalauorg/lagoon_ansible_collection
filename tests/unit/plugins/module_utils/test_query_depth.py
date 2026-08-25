from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import tempfile
import unittest

from .....plugins.module_utils.client import LagoonClient
from .query_depth import (
    QueryDepthError,
    assert_flat_query,
    collect_candidate_documents,
    max_selection_depth,
)


# The real v1 four-level nested document this guardrail exists to prevent.
# Copied verbatim from api/plugins/module_utils/api_client.py::project()
# (lines 64-106) -- do not paraphrase or shorten it, the point is to prove
# the guardrail catches the actual historical pattern, not a toy stand-in.
V1_PROJECT_INFO_QUERY = """query projectInfo($name: String!) {
                projectByName(name: $name) {
                    id
                    name
                    autoIdle
                    branches
                    gitUrl
                    metadata
                    developmentEnvironmentsLimit
                    openshift {
                        id
                        name
                    }
                    kubernetes {
                        id
                        name
                    }
                    environments {
                        name
                        openshift {
                            id
                            name
                        }
                        kubernetes {
                            id
                            name
                        }
                    }
                    deployTargetConfigs {
                        id
                        weight
                        branches
                        pullrequests
                        deployTarget {
                            name
                            id
                        }
                        project{
                            name
                        }
                    }
                }
            }"""


class TestMaxSelectionDepthPasses(unittest.TestCase):

    def test_operation_with_no_selection_set(self):
        self.assertEqual(max_selection_depth('query { me }'), 1)

    def test_query_with_field_selection(self):
        self.assertEqual(
            max_selection_depth(
                'query ($name: String!) { projectByName(name: $name) '
                '{ id name } }'),
            2)

    def test_mutation_with_field_selection(self):
        self.assertEqual(
            max_selection_depth(
                'mutation ($input: AddProjectInput!) { addProject(input: '
                '$input) { id name } }'),
            2)

    def test_mutation_returning_scalar(self):
        self.assertEqual(
            max_selection_depth(
                'mutation ($input: DeleteProjectInput!) { deleteProject('
                'input: $input) }'),
            1)

    def test_braces_inside_string_literal_are_ignored(self):
        self.assertEqual(
            max_selection_depth(
                'query { search(q: "a { b }") { id } }'),
            2)

    def test_escaped_quote_in_string_literal_is_ignored(self):
        # The \" must not terminate the literal early -- if it did, the
        # following "{ b }" would be counted as a selection set and the
        # trailing quote would unbalance the scan.
        document = 'query { search(q: "a \\" { b }") { id } }'
        self.assertEqual(max_selection_depth(document), 2)

    def test_braces_inside_comment_are_ignored(self):
        document = (
            'query { me { id } }\n'
            '# comment { with a brace }\n'
        )
        self.assertEqual(max_selection_depth(document), 2)

    def test_braces_inside_block_string_are_ignored(self):
        document = 'query { me """{ }""" { id } }'
        self.assertEqual(max_selection_depth(document), 2)


class TestMaxSelectionDepthFails(unittest.TestCase):

    def test_three_levels_raises_on_assert(self):
        document = (
            'query { projectByName(name: $n) { id openshift { id name '
            '} } }')
        self.assertEqual(max_selection_depth(document), 3)
        with self.assertRaises(AssertionError):
            assert_flat_query(document)

    def test_v1_four_level_document_raises_on_assert(self):
        depth = max_selection_depth(V1_PROJECT_INFO_QUERY)
        self.assertGreater(depth, 2)
        with self.assertRaises(AssertionError):
            assert_flat_query(V1_PROJECT_INFO_QUERY, source='v1 fixture')


class TestMaxSelectionDepthErrors(unittest.TestCase):

    def test_unterminated_unbalanced_raises(self):
        with self.assertRaises(QueryDepthError):
            max_selection_depth('query { a')

    def test_unterminated_unbalanced_is_value_error(self):
        with self.assertRaises(ValueError):
            max_selection_depth('query { a')

    def test_stray_closing_brace_raises(self):
        with self.assertRaises(QueryDepthError):
            max_selection_depth('query { a } }')

    def test_stray_closing_brace_is_value_error(self):
        with self.assertRaises(ValueError):
            max_selection_depth('query { a } }')


class TestAssertFlatQueryMessage(unittest.TestCase):

    def test_failure_message_includes_source_and_document(self):
        document = 'query { a { b { c } } }'
        with self.assertRaises(AssertionError) as ctx:
            assert_flat_query(document, source='some/file.py:SOME_QUERY')
        message = str(ctx.exception)
        self.assertIn('some/file.py:SOME_QUERY', message)
        self.assertIn(document, message)
        self.assertIn('max selection depth of 2', message)
        self.assertIn('found depth 3', message)


class TestBuildQueryIntegration(unittest.TestCase):
    """Ties P1-S4's LagoonClient.build_query to this guardrail -- a future
    regression that starts emitting nested selections must fail here too.
    """

    def test_query_with_args_is_flat(self):
        q = LagoonClient.build_query(
            'projectByName', fields=['id', 'name', 'gitUrl'],
            args={'name': 'String!'})
        assert_flat_query(q, source='build_query:projectByName')

    def test_mutation_with_scalar_return_is_flat(self):
        q = LagoonClient.build_query(
            'deployEnvironmentBranch',
            fields=[],
            args={'project': 'String!', 'branch': 'String!'},
            operation_type='mutation')
        assert_flat_query(q, source='build_query:deployEnvironmentBranch')

    def test_query_without_args_is_flat(self):
        q = LagoonClient.build_query('me', fields=['id', 'email'])
        assert_flat_query(q, source='build_query:me')


class TestSweep(unittest.TestCase):

    def _plugins_dir(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..', 'plugins')
        return os.path.normpath(path)

    def test_sweep_runs_clean_against_current_plugins_tree(self):
        candidates = collect_candidate_documents(self._plugins_dir())
        for source, document in candidates:
            assert_flat_query(document, source=source)

    def test_vacuous_pass_guard(self):
        """The sweep must not silently match zero documents once
        plugins/modules/ is populated with real module files. In Phase 1
        plugins/modules/ is genuinely empty, so this guard is currently
        inert -- it activates automatically the moment Phase 3+ adds
        modules, with no further changes required here.
        """
        modules_dir = os.path.join(self._plugins_dir(), 'modules')
        has_module_files = any(
            f.endswith('.py') and f != '__init__.py'
            for f in os.listdir(modules_dir))
        if has_module_files:
            candidates = collect_candidate_documents(self._plugins_dir())
            self.assertTrue(
                candidates,
                "collect_candidate_documents found zero GraphQL "
                "documents under plugins/ even though plugins/modules/ "
                "is non-empty -- the sweep is not matching real modules "
                "and must be fixed before it can be trusted")

    def test_sweep_detects_nested_document_in_temp_fixture(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture_path = os.path.join(tmp_dir, 'fixture_module.py')
            with open(fixture_path, 'w', encoding='utf-8') as f:
                f.write(
                    "BAD_QUERY = ("
                    "'query { projectByName(name: $n) { id openshift "
                    "{ id name } } }'"
                    ")\n")

            candidates = collect_candidate_documents(tmp_dir)
            self.assertTrue(candidates)

            found_violation = False
            for source, document in candidates:
                try:
                    assert_flat_query(document, source=source)
                except AssertionError:
                    found_violation = True
            self.assertTrue(
                found_violation,
                "sweep did not detect the nested document in the "
                "temp fixture")


if __name__ == '__main__':
    unittest.main()
