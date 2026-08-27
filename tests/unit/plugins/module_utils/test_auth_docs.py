"""Parity tests binding plugins/doc_fragments/auth.py to
auth_argument_spec().

The doc fragment and the argspec are two independent declarations of the
same option set (P2-D6): antsibull-docs cannot read a Python argspec, and
AnsibleModule cannot read a YAML docstring. Nothing but these tests stops
them drifting, which matters from Phase 3 onward when generated modules
consume both.

Comparison is structural -- the fragment's DOCUMENTATION is parsed with
yaml.safe_load and compared key by key against the argspec dict. It is
deliberately not a substring search over the raw docstring: that shape
passes vacuously (every option name appears somewhere in its own
description) and would not notice a type or default diverging at all.

The prose assertions further down are the exception, and they are scoped
to a single option's own description for the same reason -- a
whole-document search would let a warning attached to the wrong option
satisfy the requirement for another.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import copy
import re
import unittest

import yaml

from .....plugins.doc_fragments.auth import ModuleDocFragment
from .....plugins.module_utils.auth import auth_argument_spec

# Options carrying credentials. Derived from the argspec rather than
# hardcoded, so an option gaining no_log=True later is covered
# automatically instead of silently skipping the sensitivity check.
_SECRET_OPTIONS = sorted(
    name for name, spec in auth_argument_spec().items() if spec.get('no_log'))

# Any of these words in an option's description marks it as sensitive to a
# reader. Intentionally loose: the assertion is that the prose warns at
# all, not that it uses one particular phrasing.
_SENSITIVITY_RE = re.compile(r'sensitiv|secret|vault', re.IGNORECASE)


def _fragment_options():
    """The fragment's options, parsed from YAML.

    Fails loudly rather than raising a bare KeyError if the docstring is
    malformed, so a YAML syntax error reads as one clear failure instead
    of a dozen confusing ones.
    """
    parsed = yaml.safe_load(ModuleDocFragment.DOCUMENTATION)
    if not isinstance(parsed, dict):
        raise AssertionError(
            "fragment DOCUMENTATION did not parse to a mapping, got %s"
            % type(parsed).__name__)
    options = parsed.get('options')
    if not isinstance(options, dict) or not options:
        raise AssertionError(
            "fragment DOCUMENTATION has no non-empty 'options' mapping")
    return options


def _description_text(option):
    """An option's description flattened to one string for prose checks.

    Accepts the YAML list form used throughout the fragment as well as a
    bare string, since antsibull permits both.
    """
    description = option.get('description')
    if description is None:
        return ''
    if isinstance(description, str):
        return description
    return ' '.join(str(item) for item in description)


def compare(fragment_options, argument_spec):
    """Return a list of human-readable parity problems; empty means parity.

    A list of strings rather than assertions so the self-check tests at
    the bottom of this file can feed it deliberately broken input and
    assert that it complains. That is what makes "the drift test bites" a
    committed property rather than a claim.
    """
    problems = []

    fragment_names = set(fragment_options)
    spec_names = set(argument_spec)

    # Reported as two separate directions: a bare set comparison is
    # unreadable when it fires, and this is the check most likely to fire
    # in Phase 3.
    for name in sorted(spec_names - fragment_names):
        problems.append(
            "%s is in auth_argument_spec() but undocumented in the "
            "fragment" % name)
    for name in sorted(fragment_names - spec_names):
        problems.append(
            "%s is documented in the fragment but absent from "
            "auth_argument_spec()" % name)

    for name in sorted(spec_names & fragment_names):
        spec = argument_spec[name]
        option = fragment_options[name]

        # 'str' is the implicit type on both sides, so an omitted `type:`
        # must not read as a mismatch against an explicit type='str'.
        spec_type = spec.get('type', 'str')
        fragment_type = option.get('type', 'str')
        if spec_type != fragment_type:
            problems.append(
                "%s type mismatch: argspec %r, fragment %r"
                % (name, spec_type, fragment_type))

        # Compared without coercion, deliberately. Normalising through
        # str() would hide a genuine 22-vs-'22' divergence, which is
        # exactly the class of drift this test exists to catch.
        spec_default = spec.get('default')
        fragment_default = option.get('default')
        if spec_default != fragment_default:
            problems.append(
                "%s default mismatch: argspec %r, fragment %r"
                % (name, spec_default, fragment_default))

        if not _description_text(option).strip():
            problems.append("%s has an empty description" % name)

        # no_log is an argspec key, not a DOCUMENTATION key. antsibull's
        # OptionsSchema sets extra="forbid" and has no no_log field, so a
        # module extending a no_log-bearing fragment fails doc linting
        # with "Did not return correct DOCUMENTATION". Redaction is the
        # argspec's job and already works there; this guard stops a
        # well-meaning contributor mirroring it into the fragment and
        # breaking every module that extends it.
        if 'no_log' in option:
            problems.append(
                "%s declares no_log in the fragment; antsibull-docs "
                "forbids it and modules extending this fragment will "
                "fail doc linting. Redaction belongs in "
                "auth_argument_spec()." % name)

        if spec.get('no_log') and not _SENSITIVITY_RE.search(
                _description_text(option)):
            problems.append(
                "%s is no_log=True in the argspec but its description "
                "does not warn that the value is sensitive" % name)

    return problems


class AuthDocFragmentTestCase(unittest.TestCase):

    def setUp(self):
        self.fragment_options = _fragment_options()
        self.argument_spec = auth_argument_spec()

    def description_for(self, name):
        self.assertIn(
            name, self.fragment_options,
            "%s is not documented in the fragment at all" % name)
        return _description_text(self.fragment_options[name])


class TestArgspecParity(AuthDocFragmentTestCase):
    """The drift test proper."""

    def test_fragment_and_argspec_are_in_parity(self):
        problems = compare(self.fragment_options, self.argument_spec)
        self.assertEqual(
            problems, [],
            "doc fragment has drifted from auth_argument_spec():\n  %s"
            % "\n  ".join(problems))

    def test_same_option_names_in_both_directions(self):
        self.assertEqual(
            set(self.fragment_options), set(self.argument_spec))

    def test_every_option_type_agrees(self):
        for name, spec in sorted(self.argument_spec.items()):
            with self.subTest(option=name):
                self.assertEqual(
                    self.fragment_options[name].get('type', 'str'),
                    spec.get('type', 'str'))

    def test_every_option_default_agrees(self):
        for name, spec in sorted(self.argument_spec.items()):
            with self.subTest(option=name):
                self.assertEqual(
                    self.fragment_options[name].get('default'),
                    spec.get('default'))

    def test_every_option_has_a_non_empty_description(self):
        for name in sorted(self.fragment_options):
            with self.subTest(option=name):
                self.assertTrue(
                    _description_text(
                        self.fragment_options[name]).strip(),
                    "%s has an empty description" % name)

    def test_documents_every_option_the_resolver_exposes(self):
        # Guards the specific regression P2-S3a had to fix: an option
        # that resolve_token() consumes but that no module can set is
        # invisible to operators. Parity with the argspec is what keeps
        # the documented surface and the settable surface identical.
        self.assertEqual(len(self.fragment_options), 13)


class TestNoLogIsAbsentFromTheFragment(AuthDocFragmentTestCase):
    """P2-S5 AC 4 substitute (a).

    AC 4 asked for `no_log: true` in the fragment as belt and braces.
    That is unimplementable: antsibull-docs' OptionsSchema sets
    extra="forbid" and declares no no_log field, so a module extending
    such a fragment fails `antsibull-docs lint-collection-docs
    --plugin-docs` outright. no_log is valid in an argspec and not in a
    DOCUMENTATION block; the AC conflated the two schemas. Asserting its
    absence is the useful inversion -- it stops the break being
    reintroduced by someone reading AC 4 literally.
    """

    def test_no_option_declares_no_log(self):
        offenders = sorted(
            name for name, option in self.fragment_options.items()
            if 'no_log' in option)
        self.assertEqual(
            offenders, [],
            "no_log is forbidden in a doc fragment by antsibull-docs "
            "(OptionsSchema extra='forbid'); modules extending this "
            "fragment would fail doc linting. Offending options: %s"
            % offenders)

    def test_no_log_absent_from_the_raw_docstring(self):
        # Belt and braces on the parsed check above: catches a no_log
        # smuggled in somewhere yaml.safe_load does not surface as an
        # option key, e.g. nested under suboptions.
        self.assertNotIn('no_log', ModuleDocFragment.DOCUMENTATION)


class TestSecretOptionsWarnThatTheyAreSensitive(AuthDocFragmentTestCase):
    """P2-S5 AC 4 substitute (b).

    The value AC 4 was reaching for, placed where operators actually see
    it: the rendered description. Checked per option, so a warning on
    lagoon_api_token cannot satisfy the requirement for
    lagoon_ssh_private_key.
    """

    def test_secret_options_are_derived_not_assumed(self):
        self.assertEqual(
            _SECRET_OPTIONS,
            ['lagoon_api_token', 'lagoon_ssh_private_key'])

    def test_each_secret_option_description_warns(self):
        for name in _SECRET_OPTIONS:
            with self.subTest(option=name):
                self.assertRegex(self.description_for(name),
                                 _SENSITIVITY_RE)


class TestRequiredWarnings(AuthDocFragmentTestCase):
    """Prose the story requires, asserted against the owning option only."""

    def test_api_token_documents_the_environment_variable_fallback(self):
        self.assertIn(
            'LAGOON_API_TOKEN', self.description_for('lagoon_api_token'))

    def test_api_token_warns_it_is_the_exceptional_path(self):
        description = self.description_for('lagoon_api_token')
        self.assertRegex(description, r'exceptional')
        self.assertRegex(description, r'[Ss]hort-lived')

    def test_api_token_requires_vault_and_12_month_rotation(self):
        description = self.description_for('lagoon_api_token')
        self.assertRegex(description, r'Vault')
        self.assertRegex(description, r'rotate')
        self.assertRegex(description, r'12 months')

    def test_strict_host_key_checking_warns_about_interception(self):
        description = self.description_for(
            'lagoon_ssh_strict_host_key_checking')
        # The security claim, not merely the word "no": disabling
        # verification lets an attacker choose the token the whole play
        # then uses (P2-D4).
        self.assertRegex(description, r'V\(no\)')
        self.assertRegex(description, r'intercept')
        self.assertRegex(description, r'impersonate')
        self.assertRegex(description, r'token of their choosing')

    def test_strict_host_key_checking_documents_accept_new_default(self):
        self.assertRegex(
            self.description_for('lagoon_ssh_strict_host_key_checking'),
            r'accept-new')

    def test_both_key_options_document_agent_auth(self):
        # P2-D9: supplying neither key is agent auth, not an error. Both
        # options must say so -- an operator reading only one of them
        # must not conclude a key is mandatory.
        for name in ('lagoon_ssh_private_key',
                     'lagoon_ssh_private_key_file'):
            with self.subTest(option=name):
                description = self.description_for(name)
                self.assertRegex(description, r'SSH_AUTH_SOCK')
                self.assertRegex(description, r'agent')

    def test_private_key_says_neither_option_is_valid_not_an_error(self):
        self.assertRegex(
            self.description_for('lagoon_ssh_private_key'),
            r'not an error')

    def test_key_options_document_mutual_exclusion(self):
        for name in ('lagoon_ssh_private_key',
                     'lagoon_ssh_private_key_file'):
            with self.subTest(option=name):
                self.assertRegex(
                    self.description_for(name), r'[Mm]utually exclusive')

    def test_ssh_options_documents_that_it_cannot_override_defaults(self):
        # P2-D10: collection-managed -o options precede this value and
        # OpenSSH is first-wins, so this option cannot weaken them.
        description = self.description_for('lagoon_ssh_options')
        self.assertRegex(description, r'cannot override')
        self.assertRegex(description, r'StrictHostKeyChecking')
        self.assertRegex(description, r'BatchMode')
        self.assertRegex(description, r'first setting')

    def test_ssh_options_records_the_legacy_idiom_is_ignored(self):
        self.assertRegex(
            self.description_for('lagoon_ssh_options'),
            r'silently ignored')

    def test_batch_mode_explains_the_default(self):
        description = self.description_for('lagoon_ssh_batch_mode')
        self.assertRegex(description, r'BatchMode=yes')
        self.assertRegex(description, r'prompt')

    def test_token_cache_documents_its_disk_posture(self):
        # P2-D1/P2-D11: off by default, the only token-on-disk path, with
        # its directory, modes and the agent-auth collision caveat.
        description = self.description_for('lagoon_token_cache')
        self.assertRegex(description, r'[Dd]isabled by default')
        self.assertRegex(description, r'ansible-lagoon')
        self.assertRegex(description, r'0700')
        self.assertRegex(description, r'0600')

    def test_token_cache_documents_the_agent_auth_collision(self):
        description = self.description_for('lagoon_token_cache')
        self.assertRegex(description, r'agent')
        self.assertRegex(description, r'share a cached token')


class TestCompareHelperBites(AuthDocFragmentTestCase):
    """Proof the parity helper actually fails on drift.

    The story asks for this to be proven by breaking parity locally. Done
    here against deep copies instead, so the proof is committed and
    permanent rather than a claim in a commit message -- and so a
    refactor that accidentally neuters compare() into always returning []
    is caught.
    """

    def setUp(self):
        super(TestCompareHelperBites, self).setUp()
        self.assertEqual(
            compare(self.fragment_options, self.argument_spec), [],
            "baseline must be in parity for these mutations to be "
            "meaningful")

    def test_option_missing_from_fragment_is_reported(self):
        options = copy.deepcopy(self.fragment_options)
        del options['lagoon_ssh_batch_mode']
        problems = compare(options, self.argument_spec)
        self.assertEqual(len(problems), 1)
        self.assertIn('lagoon_ssh_batch_mode', problems[0])
        self.assertIn('undocumented in the fragment', problems[0])

    def test_option_missing_from_argspec_is_reported(self):
        options = copy.deepcopy(self.fragment_options)
        options['lagoon_ssh_timeout'] = {
            'description': ['Invented option.'], 'type': 'int'}
        problems = compare(options, self.argument_spec)
        self.assertEqual(len(problems), 1)
        self.assertIn('lagoon_ssh_timeout', problems[0])
        self.assertIn('absent from auth_argument_spec()', problems[0])

    def test_type_drift_is_reported(self):
        options = copy.deepcopy(self.fragment_options)
        options['lagoon_ssh_port']['type'] = 'str'
        problems = compare(options, self.argument_spec)
        self.assertEqual(len(problems), 1)
        self.assertIn('lagoon_ssh_port type mismatch', problems[0])

    def test_default_drift_is_reported(self):
        options = copy.deepcopy(self.fragment_options)
        options['lagoon_ssh_strict_host_key_checking']['default'] = 'no'
        problems = compare(options, self.argument_spec)
        self.assertEqual(len(problems), 1)
        self.assertIn(
            'lagoon_ssh_strict_host_key_checking default mismatch',
            problems[0])

    def test_stringified_default_is_reported_not_coerced_away(self):
        # The over-normalisation trap: str()-ing both sides would make
        # this pass and hide a real type divergence.
        options = copy.deepcopy(self.fragment_options)
        options['lagoon_ssh_port']['default'] = '22'
        problems = compare(options, self.argument_spec)
        self.assertEqual(len(problems), 1)
        self.assertIn('lagoon_ssh_port default mismatch', problems[0])

    def test_injected_no_log_is_reported(self):
        options = copy.deepcopy(self.fragment_options)
        options['lagoon_api_token']['no_log'] = True
        problems = compare(options, self.argument_spec)
        self.assertEqual(len(problems), 1)
        self.assertIn('declares no_log in the fragment', problems[0])

    def test_empty_description_is_reported(self):
        options = copy.deepcopy(self.fragment_options)
        options['lagoon_api_endpoint']['description'] = ['']
        problems = compare(options, self.argument_spec)
        self.assertEqual(len(problems), 1)
        self.assertIn('empty description', problems[0])

    def test_missing_description_key_is_reported(self):
        options = copy.deepcopy(self.fragment_options)
        del options['lagoon_api_endpoint']['description']
        problems = compare(options, self.argument_spec)
        self.assertEqual(len(problems), 1)
        self.assertIn('empty description', problems[0])

    def test_secret_option_losing_its_warning_is_reported(self):
        options = copy.deepcopy(self.fragment_options)
        options['lagoon_ssh_private_key']['description'] = [
            'Contents of the SSH private key used to obtain a token.']
        problems = compare(options, self.argument_spec)
        self.assertEqual(len(problems), 1)
        self.assertIn('does not warn', problems[0])

    def test_multiple_problems_are_all_reported(self):
        options = copy.deepcopy(self.fragment_options)
        del options['lagoon_ssh_host']
        options['lagoon_ssh_port']['type'] = 'str'
        problems = compare(options, self.argument_spec)
        self.assertEqual(len(problems), 2)


if __name__ == '__main__':
    unittest.main()
