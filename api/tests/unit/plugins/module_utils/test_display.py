import unittest

from .....plugins.module_utils.display import (
    REDACTED,
    Display,
    collect_no_log_values,
    redact_keys,
    redact_value,
    redacting,
)
from unittest.mock import MagicMock

SENTINEL = "sup3r-s3cret-sentinel"


class DisplayTester(unittest.TestCase):
    def test_display_set_correctly_on_init(self):
        # Display is not available by default
        display = Display()

        assert display.display == None

    def test_silenced_mutes_then_restores(self):
        display = Display()
        display.display = MagicMock()
        display.display.verbosity = 3
        original = display.display

        with display.silenced():
            display.v("muted")
            display.vvv("muted")
            display.info("muted")
            display.debug("muted")
            assert display.display is None

        # Restored, and output flows again - which also proves the mock is
        # wired up, so the assertions above are not passing vacuously.
        assert display.display is original
        display.v("emitted")

        assert original.verbose.call_count == 1
        assert original.display.call_count == 0
        assert original.debug.call_count == 0

    def test_silenced_restores_on_exception(self):
        # The GraphQL layer raises TransportQueryError on some paths, so the
        # display must come back regardless.
        display = Display()
        display.display = MagicMock()
        original = display.display

        with self.assertRaises(ValueError):
            with display.silenced():
                raise ValueError("boom")

        assert display.display is original


class RedactingTester(unittest.TestCase):
    """redacting() scrubs by value, across every output method."""

    def emitted(self, display):
        return "\n".join(
            str(c)
            for c in display.display.verbose.call_args_list
            + display.display.display.call_args_list
            + display.display.debug.call_args_list
        )

    def test_redacting_scrubs_every_output_method(self):
        display = Display()
        display.display = MagicMock()
        display.display.verbosity = 3

        with redacting({SENTINEL}):
            display.v("v: %s" % SENTINEL)
            display.vvv("vvv: %s" % SENTINEL)
            # info() is the check mode path, and is not verbosity gated.
            display.info("info: %s" % SENTINEL)
            display.debug("debug: %s" % SENTINEL)

        output = self.emitted(display)
        assert SENTINEL not in output
        # The surrounding message survives, so this is redaction not muting -
        # errors stay diagnosable (ISM-1911).
        assert "info:" in output
        assert "debug:" in output
        assert display.display.verbose.call_count == 2

    def test_redacting_block_state_is_restored(self):
        # Asserts this module's own block state, not end-to-end behaviour: on
        # ansible-core >= 2.22 register_secret is permanent and process wide,
        # so the real Display keeps masking after the block exits. Here the
        # underlying display is a mock, so only scrub() is exercised.
        display = Display()
        display.display = MagicMock()
        display.display.verbosity = 3

        with redacting({SENTINEL}):
            display.v("inside %s" % SENTINEL)

        display.v("outside %s" % SENTINEL)

        calls = [str(c) for c in display.display.verbose.call_args_list]
        assert SENTINEL not in calls[0]
        # Guards against a vacuous pass: with the block state restored the
        # message emits unchanged, so the mock and format above are live.
        assert SENTINEL in calls[1]

    def test_redacting_nests(self):
        display = Display()
        display.display = MagicMock()
        display.display.verbosity = 3
        inner = "inner-s3cret"

        with redacting({SENTINEL}):
            with redacting({inner}):
                display.v("both %s %s" % (SENTINEL, inner))
            display.v("after inner %s %s" % (SENTINEL, inner))

        calls = [str(c) for c in display.display.verbose.call_args_list]
        # Both masked while both blocks are open.
        assert SENTINEL not in calls[0]
        assert inner not in calls[0]
        # The outer value must still be masked once the inner block exits.
        # Whether the inner value is also still masked is version dependent
        # (register_secret cannot be undone) and over-masking is acceptable,
        # so that is deliberately not asserted either way.
        assert SENTINEL not in calls[1]

    def test_redacting_restores_on_exception(self):
        # The GraphQL layer raises TransportQueryError on some paths.
        display = Display()
        display.display = MagicMock()
        display.display.verbosity = 3

        with self.assertRaises(ValueError):
            with redacting({SENTINEL}):
                raise ValueError("boom")

        display.v("after %s" % SENTINEL)
        assert SENTINEL in str(display.display.verbose.call_args_list[0])

    def test_redacting_ignores_empty_values(self):
        # A falsey value must not become an empty-string replacement, which
        # would corrupt every message it touched.
        display = Display()
        display.display = MagicMock()
        display.display.verbosity = 3

        with redacting({None, "", SENTINEL}):
            display.v("kept intact: %s" % SENTINEL)

        output = str(display.display.verbose.call_args_list[0])
        assert SENTINEL not in output
        assert "kept intact:" in output


class RedactKeysTester(unittest.TestCase):
    """redact_keys() scrubs by key name, for values read back from the API."""

    def test_redacts_nested_dicts_and_lists(self):
        record = {
            "id": 9,
            "name": "SOME_VAR",
            "command": SENTINEL,
            "args": [
                {"name": "a", "value": SENTINEL},
                {"name": "b", "value": "other"},
            ],
            "nested": {"deep": {"privateKey": SENTINEL}},
        }

        out = redact_keys(record)

        assert SENTINEL not in str(out)
        assert out["command"] == REDACTED
        assert out["args"][0]["value"] == REDACTED
        assert out["nested"]["deep"]["privateKey"] == REDACTED
        # Non-sensitive keys are untouched, so output stays useful.
        assert out["id"] == 9
        assert out["name"] == "SOME_VAR"
        assert out["args"][0]["name"] == "a"

    def test_leaves_input_unmutated(self):
        record = {"command": SENTINEL}
        redact_keys(record)
        assert record["command"] == SENTINEL

    def test_handles_scalars_and_none(self):
        assert redact_keys(None) is None
        assert redact_keys("plain") == "plain"
        assert redact_keys(42) == 42
        assert redact_keys([]) == []
        assert redact_keys({}) == {}

    def test_redact_value_by_field_name(self):
        assert redact_value("command", SENTINEL) == REDACTED
        assert redact_value("name", "SOME_VAR") == "SOME_VAR"
        # Non-sensitive name, but a sensitive key nested inside the value.
        assert redact_value("args", [{"value": SENTINEL}]) == [{"value": REDACTED}]


class CollectNoLogValuesTester(unittest.TestCase):
    """The fallback used when ValidationResult._no_log_values disappears."""

    def test_collects_strings_through_suboptions(self):
        argSpec = {
            "command": dict(type="str", no_log=True),
            "name": dict(type="str"),
            "input": dict(
                type="dict",
                options={
                    "webhook": dict(type="str", no_log=True),
                },
            ),
        }
        args = {
            "command": SENTINEL,
            "name": "visible",
            "input": {"webhook": "hook-s3cret"},
        }

        assert collect_no_log_values(argSpec, args) == {SENTINEL, "hook-s3cret"}

    def test_collects_through_list_of_dicts(self):
        argSpec = {
            "args": dict(
                type="list",
                elements="dict",
                options={
                    "value": dict(type="str", no_log=True),
                },
            ),
        }
        args = {"args": [{"value": "one"}, {"value": "two"}]}

        assert collect_no_log_values(argSpec, args) == {"one", "two"}

    def test_skips_non_string_values(self):
        # An int would contribute "42" to the no-log set, which would then be
        # starred out wherever that substring appeared, including unrelated
        # project and environment IDs.
        argSpec = {
            "n": dict(type="int", no_log=True),
            "flag": dict(type="bool", no_log=True),
            "empty": dict(type="str", no_log=True),
        }
        args = {"n": 42, "flag": True, "empty": ""}

        assert collect_no_log_values(argSpec, args) == set()

    def test_tolerates_missing_and_malformed_input(self):
        assert collect_no_log_values({}, {}) == set()
        assert collect_no_log_values(None, None) == set()
        # Arg declared in the spec but absent from the args.
        assert (
            collect_no_log_values({"command": dict(type="str", no_log=True)}, {})
            == set()
        )
