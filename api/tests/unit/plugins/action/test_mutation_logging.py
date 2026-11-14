"""Argument values must never reach output from the shared mutation base.

LagoonMutationActionBase leaks differently from the single-purpose plugins:
build_dynamic_mutation inlines values into the GraphQL AST rather than using
query variables, and gql prints that AST through info(), which is not
verbosity gated. A mutation plugin run under --check therefore printed every
argument value with no -v flag at all.

Two mechanisms cover that, and which one does the work depends on the
ansible-core version:

  * core >= 2.22 registers no_log values as process-wide secrets inside
    ArgumentSpecValidator.validate(), and masks them in all Display output.
    Marking the generated argspec is enough there.
  * core <= 2.21 has no such thing, so redacting() plus the scrubbing in
    module_utils.display is what masks the values.

These tests assert the outcome rather than the mechanism, so they hold on
both. Each one also asserts that non-sensitive arguments are still visible,
which is the guard against a vacuous pass: if output were not being captured
at all, those assertions would fail too.
"""

import contextlib
import unittest

from ....common import load_schema
from ansible.plugins.action import ActionBase
from gql.dsl import DSLSchema
from unittest.mock import MagicMock, patch

from .....plugins.action.task_definition import ActionModule
from .....plugins.module_utils import display as display_module
from .....plugins.module_utils import gql as gql_module
from .....plugins.module_utils.argspec import generate_argspec_from_mutation
from .....plugins.module_utils.display import REDACTED, SENSITIVE_FIELD_NAMES

SENTINEL = "sup3r-s3cret-sentinel"
STORED_SENTINEL = "st0red-s3cret-sentinel"

TASK_ARGS = {
    "name": "test-task",
    "type": "COMMAND",
    "service": "cli",
    "project": 1,
    "command": SENTINEL,
}


def schema():
    return DSLSchema(load_schema())


def make_sink(verbosity=3):
    sink = MagicMock()
    sink.verbosity = verbosity
    return sink


def emitted(sink):
    """Everything written through any Display method, as one string.

    Uses mock_calls rather than named methods because two different APIs are
    in play: module_utils Display calls verbose()/display()/debug() on the
    underlying object, while the action plugin calls v()/vvv() on ansible's
    Display directly.
    """
    return "\n".join(str(c) for c in sink.mock_calls)


def make_module(args, sink, check_mode=False):
    """A task_definition ActionModule wired to mocks, with no transport.

    All output is funnelled into one sink: the plugin's own _display, the
    GqlClient that prints the mutation AST, and the bare Display() instances
    in diffExistingRecord and valueDiffers. Capturing through a mock rather
    than stdout keeps this independent of import order - another test module
    in this directory replaces ansible.utils.display in sys.modules with a
    Mock when it is imported, which would otherwise swallow the output and
    make these assertions pass for the wrong reason.
    """

    ds = schema()

    client = gql_module.GqlClient("foo", "bar", checkMode=check_mode)
    client.client = MagicMock()
    client.client.session.execute.return_value = {
        "addAdvancedTaskDefinition": {"id": 5}
    }
    client.ds = ds
    client.display = sink
    # ProxyLookup resolves the client through the module global.
    gql_module.globalClient = client

    module = ActionModule.__new__(ActionModule)
    module._task = MagicMock()
    module._task.args = dict(args)
    module._task.check_mode = check_mode
    module._display = sink
    module.createClient = MagicMock(
        side_effect=lambda task_vars: setattr(module, "client", client)
    )

    return module, client, ds


@contextlib.contextmanager
def captured(module, ds, sink, record=None):
    """Run with the transport stubbed and every Display routed to the sink."""

    stack = [
        patch.object(ActionBase, "run", return_value={}),
        patch.object(gql_module.GqlClient, "__enter__", return_value=(MagicMock(), ds)),
        patch.object(gql_module.GqlClient, "__exit__", return_value=False),
        # Catches the bare Display() instances in diffExistingRecord and
        # valueDiffers, which hold no reference we could inject.
        patch.object(display_module, "OrigDisplay", return_value=sink, create=True),
        patch.object(display_module, "HAS_DISPLAY", True),
    ]
    if record is not None:
        stack.append(
            patch.object(
                type(module.actionConfig), "findExistingRecord", return_value=record
            )
        )

    with contextlib.ExitStack() as es:
        for cm in stack:
            es.enter_context(cm)
        yield


class MutationLoggingTester(unittest.TestCase):
    def tearDown(self):
        gql_module.globalClient = None

    def test_mutation_flow_does_not_emit_values(self):
        sink = make_sink()
        module, _, ds = make_module(TASK_ARGS, sink)

        with captured(module, ds, sink):
            result = module.run(task_vars={})

        output = emitted(sink)
        assert SENTINEL not in output
        # Non-sensitive arguments stay visible, which guards both against a
        # vacuous pass and against over-redaction.
        assert "test-task" in output
        assert "cli" in output
        # The real value still reached the API call.
        assert result["changed"] is True

    def test_check_mode_does_not_emit_values_at_verbosity_zero(self):
        # gql logs the mutation AST through info() in check mode, which is not
        # verbosity gated - so this leaked with no -v flag at all.
        sink = make_sink(verbosity=0)
        module, _, ds = make_module(TASK_ARGS, sink, check_mode=True)

        with captured(module, ds, sink):
            module.run(task_vars={})

        output = emitted(sink)
        # The AST was printed through the unconditional path, so output is
        # definitely flowing even at verbosity 0.
        assert sink.display.call_count > 0
        assert "addAdvancedTaskDefinition" in output
        assert "Check mode enabled" in output
        assert "test-task" in output
        # ... but the inlined command value was not.
        assert SENTINEL not in output

    def test_existing_record_values_are_not_emitted(self):
        # The stored value comes back from the API, so it is not in the no-log
        # set and only key-name redaction can mask it.
        record = {
            "id": 7,
            "name": "test-task",
            "service": "cli",
            "command": STORED_SENTINEL,
        }
        sink = make_sink()
        module, _, ds = make_module(TASK_ARGS, sink)

        with captured(module, ds, sink, record=record):
            module.run(task_vars={})

        output = emitted(sink)
        assert STORED_SENTINEL not in output
        assert SENTINEL not in output
        # The record was logged, with identifying detail intact.
        assert "Existing record found" in output
        assert "test-task" in output
        assert REDACTED in output

    def test_task_args_are_masked_by_key(self):
        # LagoonActionBase logs task args before the client, and so before the
        # schema-derived argspec, exists - so that line is masked by key name.
        assert "command" in ActionModule._sensitive_task_args
        assert ActionModule._sensitive_task_args == sorted(SENSITIVE_FIELD_NAMES)

        sink = make_sink()
        module, _, ds = make_module(TASK_ARGS, sink)

        with captured(module, ds, sink):
            module.run(task_vars={})

        task_arg_calls = [
            str(c) for c in sink.mock_calls if "Task args" in str(c)
        ]
        assert len(task_arg_calls) == 1
        assert SENTINEL not in task_arg_calls[0]
        assert REDACTED in task_arg_calls[0]
        # Non-sensitive args stay visible on that line.
        assert "test-task" in task_arg_calls[0]

    def test_noLogValues_reads_the_validation_result(self):
        sink = make_sink()
        module, _, _ = make_module(TASK_ARGS, sink)
        module.argSpec = {"command": dict(type="str", no_log=True)}
        module.moduleArgs = {"command": SENTINEL}

        validationResult = MagicMock()
        validationResult._no_log_values = {SENTINEL}

        assert module._noLogValues(validationResult) == {SENTINEL}

    def test_noLogValues_falls_back_when_attribute_removed(self):
        # ansible-core documents _no_log_values as a temporary holding place
        # that may move. If it does, recompute rather than silently logging
        # secrets - this test fails CI instead of the redaction going quiet.
        sink = make_sink()
        module, _, _ = make_module(TASK_ARGS, sink)
        module.argSpec = {
            "command": dict(type="str", no_log=True),
            "name": dict(type="str"),
        }
        module.moduleArgs = {"command": SENTINEL, "name": "visible"}

        class NoAttr:
            pass

        assert module._noLogValues(NoAttr()) == {SENTINEL}


class MutationArgspecNoLogTester(unittest.TestCase):
    """The generated argspec is what drives redaction on core >= 2.22."""

    def test_sensitive_string_field_is_marked(self):
        options = generate_argspec_from_mutation(schema(), "addAdvancedTaskDefinition")[
            "input"
        ]["options"]

        assert options["command"]["type"] == "str"
        assert options["command"]["no_log"] is True

    def test_non_sensitive_fields_are_not_marked(self):
        options = generate_argspec_from_mutation(schema(), "addAdvancedTaskDefinition")[
            "input"
        ]["options"]

        for field in ["name", "description", "service", "image", "groupName"]:
            assert "no_log" not in options[field], field

    def test_bool_and_int_fields_are_never_marked(self):
        # Ansible skips booleans when collecting no_log values but does
        # stringify ints, so marking an Int field would put e.g. "42" into the
        # no-log set and star out that substring everywhere - including in
        # unrelated project and environment IDs. deployTokenInjection and
        # projectKeyInjection are also exactly why SENSITIVE_FIELD_NAMES is
        # matched exactly rather than by substring.
        options = generate_argspec_from_mutation(schema(), "addAdvancedTaskDefinition")[
            "input"
        ]["options"]

        assert options["deployTokenInjection"]["type"] == "bool"
        assert "no_log" not in options["deployTokenInjection"]
        assert options["projectKeyInjection"]["type"] == "bool"
        assert "no_log" not in options["projectKeyInjection"]

        for field, spec in options.items():
            if spec.get("type") in ("bool", "int"):
                assert "no_log" not in spec, field


class MutationMaskingBackendTester(unittest.TestCase):
    """Every masking backend must redact, not just the newest one.

    CI installs whatever ansible-core the matrix python resolves, so the
    backend actually exercised there differs from a developer machine. These
    force each one in turn: the native secrets API (core >= 2.22), the
    deprecated remove_values (core <= 2.21, removed in 2.25), and the plain
    str.replace fallback used when neither is importable.
    """

    def tearDown(self):
        gql_module.globalClient = None

    def _run_with_backend(self, native, remove_values):
        sink = make_sink(verbosity=0)
        module, _, ds = make_module(TASK_ARGS, sink, check_mode=True)

        with captured(module, ds, sink), \
                patch.object(display_module, "HAS_NATIVE_SECRETS", native), \
                patch.object(display_module, "HAS_REMOVE_VALUES",
                             remove_values):
            module.run(task_vars={})

        return emitted(sink)

    def test_native_secrets_backend(self):
        output = self._run_with_backend(native=True, remove_values=True)
        assert SENTINEL not in output
        assert "addAdvancedTaskDefinition" in output

    def test_remove_values_backend(self):
        output = self._run_with_backend(native=False, remove_values=True)
        assert SENTINEL not in output
        assert "addAdvancedTaskDefinition" in output

    def test_plain_replace_backend(self):
        output = self._run_with_backend(native=False, remove_values=False)
        assert SENTINEL not in output
        assert "addAdvancedTaskDefinition" in output
