from contextlib import contextmanager

try:
    from ansible.utils.display import Display as OrigDisplay
    HAS_DISPLAY = True
except:
    HAS_DISPLAY = False
    pass

# ansible-core >= 2.22 masks registered secrets in every Display call,
# including ansible's own. Older cores need remove_values (deprecated in
# 2.22, removed in 2.25). Prefer the native API, fall back when absent.
#
# register_secret/mask_secrets/remove_values stay bound as module-level names
# even on fallback, with behaviour matching the real API (register, then
# mask on replay). Production never hits the fallback - the HAS_* flags are
# only True when the real import succeeded - but this lets a test force a
# given backend by patching the flag alone, on any ansible-core version.
try:
    from ansible.module_utils.secrets import mask_secrets, register_secret
    HAS_NATIVE_SECRETS = True
except ImportError:
    HAS_NATIVE_SECRETS = False

    _fallback_registered_secrets = set()

    def register_secret(value):
        _fallback_registered_secrets.add(str(value))

    def mask_secrets(value):
        for secret in _fallback_registered_secrets:
            value = value.replace(secret, "*" * 8)
        return value

try:
    from ansible.module_utils.common.parameters import remove_values
    HAS_REMOVE_VALUES = True
except ImportError:
    HAS_REMOVE_VALUES = False

    def remove_values(value, no_log_strings):
        for secret in no_log_strings:
            value = value.replace(str(secret), "*" * 8)
        return value

REDACTED = "VALUE_REDACTED"

# Exact GraphQL input field names whose values must never reach output.
# Matched exactly, not by substring: 'token'/'key' would wrongly catch the
# booleans deployTokenInjection and projectKeyInjection.
#
# Lives here, not in argspec.py, to avoid a circular import: argspec.py
# imports gql.py, which imports this module.
SENSITIVE_FIELD_NAMES = frozenset({
    "value",
    "command",
    "webhook",
    "keyValue",
    "privateKey",
    "token",
    "password",
    "newPassword",
    "secret",
})

# Secret values to scrub from every Display instance's output. Module-scoped,
# not per-instance, because callers construct Display() on demand with no
# shared attribute to carry the set. Not thread-safe; matches the existing
# globalClient singleton pattern and Ansible's per-fork process model.
_no_log_values = set()


@contextmanager
def redacting(values):
    """Scrub these values from all Display output within the block.

    For write paths where the secret is known up front: task arguments,
    mutation variables, inlined mutation AST values. Redacts by value
    instead of muting, so errors stay visible (ISM-1911) while the secret
    stays hidden (ISM-2052).

    Nests: restores the outer block's values on exit, even if it raises.
    """
    global _no_log_values
    previous = _no_log_values
    added = {str(v) for v in values if v}

    if HAS_NATIVE_SECRETS:
        # Process-wide and permanent - there is no unregister. That is safe
        # (it only ever masks more, never less) and matches how ansible-core
        # treats vault secrets, but it does mean the block scoping below is
        # belt-and-braces on these versions.
        for value in added:
            register_secret(value)

    _no_log_values = previous | added
    try:
        yield
    finally:
        _no_log_values = previous


def scrub(msg):
    """Remove the active no-log values from an already-formatted message.

    Takes a string, never an object: ansible's _remove_values_conditions
    raises TypeError on types it does not recognise, so handing it a DSL
    object or a GraphQL type would crash the task rather than log it.
    """
    if not _no_log_values:
        return msg

    if not isinstance(msg, str):
        msg = str(msg)

    if HAS_NATIVE_SECRETS:
        return mask_secrets(msg)

    if HAS_REMOVE_VALUES:
        return remove_values(msg, _no_log_values)

    # Neither is importable (target-side test group with no ansible).
    for value in _no_log_values:
        msg = msg.replace(value, "*" * 8)
    return msg


def redact_keys(obj, names=SENSITIVE_FIELD_NAMES):
    """Copy of obj with the values of the named keys replaced.

    For read paths: values that arrived from the API, so are not in the
    no-log set and redacting() can't mask them. Matches key names exactly;
    see SENSITIVE_FIELD_NAMES.
    """
    if isinstance(obj, dict):
        return {k: REDACTED if k in names else redact_keys(v, names)
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_keys(i, names) for i in obj]
    if isinstance(obj, tuple):
        return tuple(redact_keys(i, names) for i in obj)
    return obj


def redact_value(name, value, names=SENSITIVE_FIELD_NAMES):
    """REDACTED if this field name is sensitive, else value with any
    sensitive keys nested inside it redacted."""
    if name in names:
        return REDACTED
    return redact_keys(value, names)


def collect_no_log_values(argSpec, args):
    """Secret values in args, per the no_log flags in argSpec.

    Fallback for when ValidationResult._no_log_values is unavailable - it's
    a private, documented-as-unstable ansible-core attribute.

    Strings only, matching argspec.mark_no_log: an int value would add e.g.
    "42" to the set and star out that substring in unrelated IDs too.
    """
    values = set()

    if not isinstance(argSpec, dict) or not isinstance(args, dict):
        return values

    for name, spec in argSpec.items():
        if not isinstance(spec, dict) or name not in args:
            continue

        value = args[name]

        if spec.get("no_log") and isinstance(value, str) and value:
            values.add(value)

        subSpec = spec.get("options")
        if subSpec:
            entries = value if isinstance(value, list) else [value]
            for entry in entries:
                values |= collect_no_log_values(subSpec, entry)

    return values


class Display:

    def __init__(self) -> None:
        self.display = OrigDisplay() if HAS_DISPLAY else None

    def info(self, msg, color=None, stderr=False, screen_only=False,
             log_only=False, newline=True):
        if self.display:
            self.display.display(scrub(msg), color, stderr,
                                 screen_only, log_only, newline)

    def v(self, msg, host=None):
        return self.verbose(msg, host=host, caplevel=0)

    def vv(self, msg, host=None):
        return self.verbose(msg, host=host, caplevel=1)

    def vvv(self, msg, host=None):
        return self.verbose(msg, host=host, caplevel=2)

    def vvvv(self, msg, host=None):
        return self.verbose(msg, host=host, caplevel=3)

    def vvvvv(self, msg, host=None):
        return self.verbose(msg, host=host, caplevel=4)

    def vvvvvv(self, msg, host=None):
        return self.verbose(msg, host=host, caplevel=5)

    def debug(self, msg, host=None):
        if self.display:
            self.display.debug(scrub(msg), host)

    def verbose(self, msg, host=None, caplevel=2):
        if self.display:
            self.display.verbose(scrub(msg), host, caplevel)

    @contextmanager
    def silenced(self):
        """Mute all output from this object for the duration of the block.

        For read paths whose results carry secrets that are not known in
        advance, such as a bulk environment variable query - redacting()
        cannot help there, because it only knows the values being sent.

        Every method on this class no-ops when the underlying display is None.
        """
        original = self.display
        self.display = None
        try:
            yield self
        finally:
            self.display = original
