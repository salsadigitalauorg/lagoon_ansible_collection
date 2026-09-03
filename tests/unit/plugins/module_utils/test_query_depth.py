from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import tempfile
import unittest

from unittest.mock import patch

from .....plugins.module_utils.client import LagoonClient
from . import query_depth
from .query_depth import (
    INVALID_BUILD_QUERY,
    SHADOWED_BUILD_QUERY,
    UNRESOLVED_BUILD_QUERY,
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
            if document == UNRESOLVED_BUILD_QUERY:
                # No document to check depth on -- see
                # test_dynamic_fields_argument_is_unresolved_not_dropped
                # for the negative-path proof that this placeholder is
                # never silently dropped instead.
                continue
            self.assertNotEqual(
                document, INVALID_BUILD_QUERY,
                "a build_query(...) call site in %s resolves statically "
                "but is rejected by the real implementation -- this is "
                "a guaranteed runtime failure, fix the call site" % source)
            self.assertNotEqual(
                document, SHADOWED_BUILD_QUERY,
                "a call site named build_query in %s does not provably "
                "resolve to LagoonClient.build_query -- either it is "
                "genuinely shadowed (rename it) or the sweep's provenance "
                "check needs to learn this import shape" % source)
            assert_flat_query(document, source=source)

    def test_vacuous_pass_guard(self):
        """The sweep must not silently match zero documents once
        plugins/modules/ is populated with real module files.
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

    def test_vacuous_pass_guard_depends_on_the_build_query_extension(self):
        """The previous test only proves *something* was found. This
        proves the *reason* -- with the build_query extension disabled,
        the sweep must find nothing against the real tree, since
        whoami_info.py has no GraphQL string literal of its own (once
        its DOCUMENTATION/EXAMPLES/RETURN blocks are correctly excluded
        as YAML prose, not GraphQL -- see _DOC_CONSTANTS). If this ever
        starts passing with the extension disabled, the exclusion above
        has regressed and the vacuous-pass guard is inert again.
        """
        with patch.object(
                query_depth, '_build_query_call_sites',
                return_value=iter(())):
            candidates = collect_candidate_documents(self._plugins_dir())
        self.assertFalse(
            candidates,
            "collect_candidate_documents found %r with the build_query "
            "extension disabled -- something other than build_query(...) "
            "call sites is matching real plugin files, which means the "
            "vacuous-pass guard above is not actually exercising the "
            "extension it credits" % (candidates,))

    def test_doc_constants_are_not_candidates(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture_path = os.path.join(tmp_dir, 'fixture_module.py')
            with open(fixture_path, 'w', encoding='utf-8') as f:
                f.write(
                    "DOCUMENTATION = r'''\n"
                    "description: uses the flat-query rule {x}\n"
                    "'''\n"
                    "EXAMPLES = r'''\n"
                    "- name: query { a { b } }\n"
                    "'''\n"
                    "RETURN = r'''\n"
                    "user:\n"
                    "  description: >-\n"
                    "    a nested query { a { b { c } } } shape in prose\n"
                    "'''\n")

            candidates = collect_candidate_documents(tmp_dir)
            self.assertEqual(
                candidates, [],
                "DOCUMENTATION/EXAMPLES/RETURN string constants must "
                "never be reported as GraphQL document candidates -- "
                "they are YAML prose")

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


class TestBuildQuerySweepExtension(unittest.TestCase):
    """The extension that lets the sweep find LagoonClient.build_query(...)
    call sites -- see whoami_info.py, the first module with no GraphQL
    string literal at all for the original sweep to match.
    """

    def _write_fixture(self, tmp_dir, source):
        fixture_path = os.path.join(tmp_dir, 'fixture_module.py')
        with open(fixture_path, 'w', encoding='utf-8') as f:
            f.write(source)
        return fixture_path

    def test_attribute_form_call_site_is_found_and_flat(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_fixture(
                tmp_dir,
                "from ansible_collections.salsadigitalauorg.lagoon."
                "plugins.module_utils.client import LagoonClient\n\n"
                "LagoonClient.build_query('x', fields=['a', 'b'])\n")

            candidates = collect_candidate_documents(tmp_dir)
            self.assertTrue(candidates)

            resolved = [d for _, d in candidates
                        if d != UNRESOLVED_BUILD_QUERY]
            self.assertEqual(len(resolved), 1)
            assert_flat_query(resolved[0])
            self.assertEqual(resolved[0], "query x { x { a b } }")

    def test_bare_form_call_site_is_found(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_fixture(
                tmp_dir,
                "from ansible_collections.salsadigitalauorg.lagoon."
                "plugins.module_utils.client import LagoonClient\n"
                "build_query = LagoonClient.build_query\n\n"
                "build_query('me', fields=['id', 'email'])\n")

            candidates = collect_candidate_documents(tmp_dir)
            resolved = [d for _, d in candidates
                        if d != UNRESOLVED_BUILD_QUERY]
            self.assertIn("query me { me { id email } }", resolved)

    def test_call_with_args_kwarg_is_reconstructed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_fixture(
                tmp_dir,
                "from ansible_collections.salsadigitalauorg.lagoon."
                "plugins.module_utils.client import LagoonClient\n\n"
                "LagoonClient.build_query(\n"
                "    'projectByName', fields=['id', 'name'],\n"
                "    args={'name': 'String!'})\n")

            candidates = collect_candidate_documents(tmp_dir)
            resolved = [d for _, d in candidates
                        if d != UNRESOLVED_BUILD_QUERY]
            self.assertEqual(len(resolved), 1)
            self.assertEqual(
                resolved[0],
                "query projectByName($name: String!) { "
                "projectByName(name: $name) { id name } }")

    def test_whoami_info_build_query_call_is_found_by_the_real_sweep(self):
        """Ties the extension to the real file, not just a fixture --
        this is the concrete proof the vacuous-pass guard needs.
        """
        plugins_dir = os.path.normpath(os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..', 'plugins'))
        candidates = collect_candidate_documents(plugins_dir)
        whoami_candidates = [
            (source, document) for source, document in candidates
            if 'whoami_info.py' in source]
        self.assertTrue(
            whoami_candidates,
            "sweep found no build_query(...) call site in "
            "whoami_info.py")
        for _source, document in whoami_candidates:
            self.assertNotEqual(document, UNRESOLVED_BUILD_QUERY)
            assert_flat_query(document)

    def test_dynamic_fields_argument_is_unresolved_not_dropped(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_fixture(
                tmp_dir,
                "from ansible_collections.salsadigitalauorg.lagoon."
                "plugins.module_utils.client import LagoonClient\n\n"
                "def build(field_list):\n"
                "    return LagoonClient.build_query(\n"
                "        'me', fields=field_list)\n")

            candidates = collect_candidate_documents(tmp_dir)
            self.assertTrue(candidates)
            self.assertTrue(
                all(document == UNRESOLVED_BUILD_QUERY
                    for _source, document in candidates),
                "a call site with a dynamic fields argument must be "
                "recorded as unresolved, not silently dropped or "
                "mis-resolved")

    def test_locally_defined_build_query_is_marked_shadowed(self):
        """A local function named ``build_query`` must never be
        reconstructed via the real ``LagoonClient.build_query`` --
        the checker previously matched on name only, so it would
        silently check the *real* implementation's output for a call
        site that actually invokes a different function entirely,
        missing whatever that function really does.

        The decoy's nested document is built by concatenation, not a
        string literal, so rule 2's literal scan cannot independently
        catch it -- this isolates rule 3's own provenance check.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_fixture(
                tmp_dir,
                "_BRACE = chr(123)\n"
                "def build_query(operation, fields):\n"
                "    return ('q ' + _BRACE + operation + _BRACE +\n"
                "            ' '.join(fields) + _BRACE + 'nested' +\n"
                "            '}}}')\n\n"
                "build_query('me', fields=['a'])\n")

            candidates = collect_candidate_documents(tmp_dir)
            documents = [d for _, d in candidates]
            self.assertIn(SHADOWED_BUILD_QUERY, documents)
            self.assertNotIn("query me { me { a } }", documents,
                              "the shadowed call must not be silently "
                              "reconstructed via the real implementation")

    def test_aliased_build_query_via_trusted_import_still_resolves(self):
        """The alias form (``build_query = LagoonClient.build_query``,
        where ``LagoonClient`` is imported from the real
        module_utils.client) must still resolve -- provenance checking
        must not regress the legitimate bare-form case.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_fixture(
                tmp_dir,
                "from ansible_collections.salsadigitalauorg.lagoon."
                "plugins.module_utils.client import LagoonClient\n"
                "build_query = LagoonClient.build_query\n\n"
                "build_query('me', fields=['id', 'email'])\n")

            candidates = collect_candidate_documents(tmp_dir)
            documents = [d for _, d in candidates]
            self.assertNotIn(SHADOWED_BUILD_QUERY, documents)
            self.assertIn("query me { me { id email } }", documents)

    def test_statically_invalid_call_site_is_marked_invalid(self):
        """A call whose arguments resolve statically but that the real
        build_query() rejects (e.g. an invalid operation name) is a
        guaranteed runtime failure -- it must be marked INVALID, not
        silently folded into the same "not checked" bucket as a
        genuinely dynamic, uncheckable call.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_fixture(
                tmp_dir,
                "from ansible_collections.salsadigitalauorg.lagoon."
                "plugins.module_utils.client import LagoonClient\n\n"
                "LagoonClient.build_query('not a valid name!',\n"
                "    fields=['id'])\n")

            candidates = collect_candidate_documents(tmp_dir)
            documents = [d for _, d in candidates]
            self.assertIn(INVALID_BUILD_QUERY, documents)
            self.assertNotIn(UNRESOLVED_BUILD_QUERY, documents,
                              "a statically-invalid call site must not "
                              "be conflated with a genuinely unresolved "
                              "one")

    def test_args_type_string_breakout_is_caught_by_the_sweep(self):
        """LagoonClient.build_query() interpolates an ``args`` GraphQL
        *type* string unvalidated -- only argument names are checked.
        A type string containing braces produces a nested document at
        runtime. The sweep must reconstruct and catch this rather than
        pass it as flat; it is a pre-existing gap in build_query() being
        pinned here as a known, regression-guarded limitation, not
        claimed to be impossible.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_fixture(
                tmp_dir,
                "from ansible_collections.salsadigitalauorg.lagoon."
                "plugins.module_utils.client import LagoonClient\n\n"
                "LagoonClient.build_query(\n"
                "    'projectByName', fields=['id'],\n"
                "    args={'name': "
                "'String!) { evil { deeply { nested } } } #'})\n")

            candidates = collect_candidate_documents(tmp_dir)
            resolved = [d for _, d in candidates
                        if d not in (UNRESOLVED_BUILD_QUERY,
                                     INVALID_BUILD_QUERY,
                                     SHADOWED_BUILD_QUERY)]
            self.assertEqual(len(resolved), 1)
            with self.assertRaises(AssertionError):
                assert_flat_query(resolved[0])


if __name__ == '__main__':
    unittest.main()
