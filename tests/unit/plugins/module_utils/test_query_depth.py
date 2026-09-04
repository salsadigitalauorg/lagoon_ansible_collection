from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import copy
import os
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from .....plugins.module_utils.client import LagoonClient
from . import query_depth
from .query_depth import (
    INVALID_BUILD_QUERY,
    PERMITTED_NESTED_SELECTIONS,
    SHADOWED_BUILD_QUERY,
    UNRESOLVED_BUILD_QUERY,
    QueryDepthError,
    ShapeViolation,
    assert_flat_query,
    assert_registry_matches_sdl,
    classify_selection_shape,
    collect_candidate_documents,
    max_selection_depth,
    parse_root_selection,
    sdl_object_type_fields,
    sdl_scalar_and_enum_names,
)

_SDL_PATH = Path(__file__).parents[4] / 'schema' / 'lagoon-2.33.0.graphql'


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
        self.assertIn('undeclared_nesting', message)

    def test_malformed_document_raises_query_depth_error_not_assertion(self):
        # An unbalanced/unterminated document is a malformed-document
        # error, not a shape violation -- assert_flat_query must let
        # QueryDepthError propagate rather than mask it as a shape
        # AssertionError.
        with self.assertRaises(QueryDepthError):
            assert_flat_query('query { a { b')


class TestParseRootSelection(unittest.TestCase):

    def test_no_selection_set_returns_none(self):
        self.assertIsNone(
            parse_root_selection(
                'mutation ($input: DeleteProjectInput!) { deleteProject('
                'input: $input) }'))

    def test_flat_selection_returns_leaf_names(self):
        selections = parse_root_selection(
            'query ($name: String!) { projectByName(name: $name) '
            '{ id name } }')
        self.assertEqual([s.name for s in selections], ['id', 'name'])
        self.assertTrue(all(s.sub is None for s in selections))

    def test_nested_selection_is_captured_as_a_sub_selection(self):
        selections = parse_root_selection(
            'query { projectByName(name: $n) { id openshift { id name '
            '} } }')
        by_name = {s.name: s for s in selections}
        self.assertIsNone(by_name['id'].sub)
        self.assertEqual(
            [s.name for s in by_name['openshift'].sub], ['id', 'name'])


class TestClassifySelectionShapeDiscriminatingPair(unittest.TestCase):
    """The pair that proves the rule measures expansion, not depth --
    same list field, same depth, opposite verdicts.
    """

    def test_environments_scalar_leaves_permitted(self):
        selections = parse_root_selection(
            'query { projectByName(name: $n) { environments { id '
            'environmentType kubernetesNamespaceName } } }')
        self.assertIsNone(classify_selection_shape(selections, 'Project'))

    def test_environments_object_leaf_rejected(self):
        selections = parse_root_selection(
            'query { projectByName(name: $n) { environments { '
            'openshift { id } } } }')
        with self.assertRaises(ShapeViolation) as ctx:
            classify_selection_shape(selections, 'Project')
        self.assertEqual(ctx.exception.reason, 'object_leaf_beneath_nesting')


class TestClassifySelectionShape(unittest.TestCase):

    def test_scalar_enum_leaf_no_nesting_permitted(self):
        # restrictions: [Restriction] -- a scalar-list leaf, no
        # selection set at all, needs no registry entry.
        selections = parse_root_selection(
            'query { projectByName(name: $n) { restrictions } }')
        self.assertIsNone(classify_selection_shape(selections, 'Project'))

    def test_bounded_object_hop_autogenerated_route_config_permitted(self):
        selections = parse_root_selection(
            'query { projectByName(name: $n) { autogeneratedRouteConfig '
            '{ enabled } } }')
        self.assertIsNone(classify_selection_shape(selections, 'Project'))

    def test_bounded_object_hop_openshift_permitted(self):
        selections = parse_root_selection(
            'query { projectByName(name: $n) { openshift { id } } }')
        self.assertIsNone(classify_selection_shape(selections, 'Project'))

    def test_two_list_selections_in_one_document_rejected(self):
        selections = parse_root_selection(
            'query { projectByName(name: $n) { environments { id } '
            'envVariables { name } } }')
        # envVariables is deliberately not in the registry for Project --
        # this document is rejected on the first violation the classifier
        # reaches either way, but proves the intent even before
        # envVariables would need its own entry to test the cap in
        # isolation, so use two registry-declared list fields instead.
        registry = {
            'Project': dict(
                PERMITTED_NESTED_SELECTIONS['Project'],
                envVariables=('list', ('id', 'name'))),
        }
        with self.assertRaises(ShapeViolation) as ctx:
            classify_selection_shape(selections, 'Project', registry)
        self.assertEqual(ctx.exception.reason, 'multiple_list_selections')

    def test_organization_details_object_leaf_beneath_bounded_hop_rejected(
            self):
        selections = parse_root_selection(
            'query { projectByName(name: $n) { organizationDetails { '
            'owners { id } } } }')
        registry = {
            'Project': dict(
                PERMITTED_NESTED_SELECTIONS['Project'],
                organizationDetails=('single', ('id', 'name', 'owners'))),
        }
        with self.assertRaises(ShapeViolation) as ctx:
            classify_selection_shape(selections, 'Project', registry)
        self.assertEqual(
            ctx.exception.reason, 'object_leaf_beneath_nesting')

    def test_v1_project_info_query_rejected_for_object_beneath_list(self):
        selections = parse_root_selection(V1_PROJECT_INFO_QUERY)
        with self.assertRaises(ShapeViolation) as ctx:
            classify_selection_shape(selections, 'Project')
        self.assertEqual(
            ctx.exception.reason, 'object_leaf_beneath_nesting')

    def test_v1_project_info_query_rejected_for_multiple_lists_too(self):
        # V1_PROJECT_INFO_QUERY nests an object leaf (openshift/
        # kubernetes) beneath both of its list selections
        # (environments, deployTargetConfigs), so classify_selection_shape
        # always hits the object-beneath-list check first for that exact
        # document -- see
        # test_v1_project_info_query_rejected_for_object_beneath_list.
        # This proves the *second*, independent reason v1's breadth
        # would still be rejected even with every individual leaf legal:
        # a synthetic document with the same two-list shape but only
        # scalar leaves beneath each list (no object nesting at all) is
        # still rejected, and for the multi-list reason specifically --
        # not masked by, or dependent on, the object-leaf check.
        document = (
            'query { projectByName(name: $n) { '
            'environments { name environmentType } '
            'deployTargetConfigs { id weight branches pullrequests } '
            '} }')
        selections = parse_root_selection(document)
        registry = {
            'Project': {
                'environments': ('list', ('name', 'environmentType')),
                'deployTargetConfigs': ('list', (
                    'id', 'weight', 'branches', 'pullrequests')),
            },
        }
        with self.assertRaises(ShapeViolation) as ctx:
            classify_selection_shape(selections, 'Project', registry)
        self.assertEqual(ctx.exception.reason, 'multiple_list_selections')

    def test_undeclared_single_valued_nesting_field_rejected(self):
        selections = parse_root_selection(
            'query { projectByName(name: $n) { clone { id } } }')
        with self.assertRaises(ShapeViolation) as ctx:
            classify_selection_shape(selections, 'Project')
        self.assertEqual(ctx.exception.reason, 'undeclared_nesting')

    def test_undeclared_list_valued_nesting_field_rejected(self):
        selections = parse_root_selection(
            'query { projectByName(name: $n) { deployTargetConfigs { '
            'id } } }')
        with self.assertRaises(ShapeViolation) as ctx:
            classify_selection_shape(selections, 'Project')
        self.assertEqual(ctx.exception.reason, 'undeclared_nesting')

    def test_no_nested_selections_at_all_permitted_with_no_parent_type(
            self):
        selections = parse_root_selection(
            'query { me { id email } }')
        self.assertIsNone(classify_selection_shape(selections, None))


class TestRegistryConformance(unittest.TestCase):

    def setUp(self):
        self.sdl_text = _SDL_PATH.read_text(encoding='utf-8')

    def test_real_registry_matches_real_sdl(self):
        assert_registry_matches_sdl(self.sdl_text)

    def test_bad_kind_fails(self):
        bad_registry = copy.deepcopy(PERMITTED_NESTED_SELECTIONS)
        # environments is genuinely [Environment] -- declaring it
        # 'single' must be caught, not silently accepted.
        bad_registry['Project']['environments'] = (
            'single', ('id', 'name'))
        with self.assertRaises(AssertionError) as ctx:
            assert_registry_matches_sdl(self.sdl_text, bad_registry)
        self.assertIn('kind', str(ctx.exception))

    def test_object_typed_leaf_fails(self):
        bad_registry = copy.deepcopy(PERMITTED_NESTED_SELECTIONS)
        # Environment.openshift is Openshift -- a bare object type, not
        # scalar or enum. Smuggling it in as a permitted leaf under
        # Project's own openshift hop (Project.openshift: Openshift, and
        # Openshift has no field named "openshift" itself, but it does
        # have "name") must be caught by leaf-shape validation, not by
        # the unknown-leaf check -- use a field both types share.
        bad_registry['Project']['openshift'] = (
            'single', ('id', 'name'))
        bad_registry['Environment']['project'] = (
            'single', ('id', 'openshift'))
        with self.assertRaises(AssertionError) as ctx:
            assert_registry_matches_sdl(self.sdl_text, bad_registry)
        self.assertIn('not a scalar or enum', str(ctx.exception))

    def test_unknown_parent_type_fails(self):
        bad_registry = {'NoSuchType': {'foo': ('single', ('id',))}}
        with self.assertRaises(AssertionError):
            assert_registry_matches_sdl(self.sdl_text, bad_registry)

    def test_unknown_nesting_field_fails(self):
        bad_registry = {'Project': {'noSuchField': ('single', ('id',))}}
        with self.assertRaises(AssertionError):
            assert_registry_matches_sdl(self.sdl_text, bad_registry)

    def test_unknown_leaf_fails(self):
        bad_registry = {
            'Project': {'openshift': ('single', ('noSuchLeaf',))},
        }
        with self.assertRaises(AssertionError):
            assert_registry_matches_sdl(self.sdl_text, bad_registry)


class TestSdlHelpers(unittest.TestCase):

    def setUp(self):
        self.sdl_text = _SDL_PATH.read_text(encoding='utf-8')

    def test_object_type_fields_reports_correct_types(self):
        fields = sdl_object_type_fields(self.sdl_text, 'Project')
        self.assertEqual(fields['id'], 'Int')
        self.assertEqual(fields['openshift'], 'Openshift')
        self.assertEqual(fields['environments'], '[Environment]')
        self.assertEqual(fields['restrictions'], '[Restriction]')

    def test_object_type_fields_unknown_type_returns_none(self):
        self.assertIsNone(
            sdl_object_type_fields(self.sdl_text, 'NoSuchType'))

    def test_scalar_and_enum_names_includes_builtins_and_declared(self):
        names = sdl_scalar_and_enum_names(self.sdl_text)
        self.assertIn('Int', names)
        self.assertIn('String', names)
        self.assertIn('JSON', names)
        self.assertIn('Restriction', names)
        self.assertNotIn('Project', names)
        self.assertNotIn('Openshift', names)


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

    def test_sibling_relative_import_of_lagoonclient_still_resolves(self):
        """A file living inside ``module_utils/`` itself imports
        ``LagoonClient`` via the sibling-relative shape every other
        cross-file import in that package uses (``from .client import
        LagoonClient``), not the absolute
        ``ansible_collections...module_utils.client`` shape used
        everywhere else. This must still be trusted, not marked
        shadowed -- ``lookup.py`` is the first real file to hit this
        path.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            self._write_fixture(
                tmp_dir,
                "from .client import LagoonClient\n\n"
                "LagoonClient.build_query('me', fields=['id', 'email'])\n")

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
