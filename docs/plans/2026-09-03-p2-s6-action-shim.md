# P2-S6 — `LagoonActionShim` in `plugins/action/__init__.py`

**Date:** 2026-09-03
**Story:** [`docs/plans/v3-phase2-stories.md`](./v3-phase2-stories.md) § P2-S6
**Parent plan:** [`docs/plans/v3-refactor.md`](./v3-refactor.md) §9 Phase 2, §4
**Branch:** `3.x`
**Depends on:** P2-S5 (`906b4dd`)
**Status:** Implemented, pending review

---

## Scope

Two new files, one commit:

```
plugins/action/__init__.py                    (new)
tests/unit/plugins/action/__init__.py         (new)
tests/unit/plugins/action/test_shim.py        (new)
```

`LagoonActionShim` does exactly one thing: resolve a bearer token via
`module_utils.auth.resolve_token()` and inject it into the delegated module's
args before calling `self._execute_module(...)`. Per P2-D3, this is a base
class — not a collection-wide action plugin — every generated module gets
its own one-line subclass file under `plugins/action/<name>.py` (Phase 3's
job; P2-S7 provides the first hand-written example for `whoami_info`).

Name→id lookup injection (parent plan §4's second sidecar responsibility) is
explicitly out of scope — that is Phase 4.

---

## Design

### Config precedence

Per the story: explicit task args (`lagoon_api_token:` set directly on the
task) → `task_vars` (the v1-compatible `set_fact`/`vars:` pattern,
templated via `self._templar.template()`) → environment (handled inside
`auth.resolve_token()` itself) → module argspec defaults.

Implemented as `_build_auth_config()`, which reads each auth-relevant key
first from `self._task.args`, falling back to `task_vars`, and templates
only the `task_vars`-sourced value (task args arrive already templated by
Ansible — re-templating them would be redundant and, for `no_log` values,
is exactly the kind of thing that shouldn't happen twice).

### Boolean/int coercion

`task_vars` values (e.g. `lagoon_ssh_batch_mode`, `lagoon_ssh_port`) may
arrive as templated **strings** (`"false"`, `"22"`) from `vars:`/`set_fact`,
whereas task args of an action plugin are the raw task args dict and are
not passed through argspec coercion (that only happens module-side, in
`_execute_module`). `_build_auth_config()` explicitly coerces
`ssh_port` to `int` and `batch_mode`/`token_cache` to `bool` using the same
truthy-string convention Ansible itself uses, so a `vars:`-supplied
`lagoon_ssh_batch_mode: "false"` does not silently evaluate truthy.

### Error handling

`auth.resolve_token()` raises `LagoonConfigError` or `LagoonAuthError`
(both `LagoonError`) on failure. The shim is **the only place in the
collection permitted to import `ansible.errors`** (enforced by the same
AST-import test pattern as every `module_utils` file, inverted) — it is the
seam where `LagoonError` becomes `AnsibleError`. `LagoonError.__str__` is
already redaction-safe (proven in P2-S1/S2/S3's own test suites), so
`str(e)` is safe to pass straight into `AnsibleError`.

On failure, `_execute_module` is never called — the `try` wraps only the
auth resolution, and the module delegation happens after the `try` block
returns cleanly.

### Injection scope

Only `lagoon_api_token` (always injected — it's the point of the shim),
`lagoon_api_endpoint` (via `setdefault`, so an explicit task-level value
survives), and `validate_certs` (same, `setdefault`) are touched.
`self._task.args` itself is never mutated — the shim builds `module_args =
dict(self._task.args)` and injects into the copy, per the story's explicit
requirement ("copy, don't mutate in place").

### `warn`

`auth.resolve_token()` accepts an optional `warn` callable, used only to
surface a degraded opt-in file-cache write (P2-S4). The shim wires this to
`self._display.warning`, matching the "AnsibleModule.warn/display.warning
-shaped callable" contract `resolve_token()`'s docstring describes.

### Check mode / async

No check-mode or async logic of its own — `self._execute_module(...)` and
the base `ActionBase.run()` call already ahead of it (via `super().run()`)
handle `_supports_check_mode`/`_supports_async` as normal. The shim adds no
new decision point.

---

## Testing

`tests/unit/plugins/action/test_shim.py` constructs `LagoonActionShim`
directly (it has no abstract methods of its own left unimplemented) with
mocked `task`, `connection`, `play_context`, `loader`, `templar`, and
`shared_loader_obj` — standard `ActionBase` test scaffolding. `super().run()`
itself is patched out (`ActionBase.run`) rather than fully re-mocking
`_connection._shell`/`_early_needs_tmp_path`, since the shim's own contract
under test is what it does *after* delegating to the base, not the base's
own tmp-path machinery.

Covers, per the story's testing requirements:

1. Token resolved and injected as `lagoon_api_token`.
2. All other task args pass through to `_execute_module` unmodified (dict
   equality apart from the injected keys).
3. `task_vars`-sourced values are templated via `self._templar.template()`
   — asserted on the mock templar call, not "string didn't leak".
4. Task-arg-level `lagoon_api_token` wins over `task_vars`.
5. A `LagoonError` from `resolve_token` becomes `AnsibleError`;
   `_execute_module` call count is asserted zero.
6. No token value in the raised `AnsibleError` message.
7. `_task.action` used as the default `module_name`.
8. `self._task.args` itself is never mutated (identity + content check).
9. `validate_certs`/`lagoon_api_endpoint` explicit task args are not
   clobbered by a `task_vars` value (setdefault semantics).
10. `warn` passed to `resolve_token` calls `self._display.warning`.

Plus the collection-wide import guard: `ansible.errors` appears only under
`plugins/action/`.

---

## Acceptance criteria

- [x] `ansible.errors` imported here and nowhere else in `plugins/` outside
      `plugins/action/`.
- [x] No resource-specific logic — the shim only knows about auth-related
      keys.
- [x] Auth failure never reaches `_execute_module`.
- [x] Only auth-related keys injected; everything else passed through
      unmodified; `self._task.args` itself never mutated.
- [x] Token absent from any `AnsibleError` raised.
- [x] `task_vars`-sourced values are templated before use.
- [x] Explicit task-arg precedence over `task_vars` proven by test.

## Verification commands

```sh
docker compose run --rm test-v3 units -v --requirements \
  tests/unit/plugins/action/test_shim.py

grep -rln "ansible.errors" plugins/ | grep -v '^plugins/action/' \
  && echo "FAIL: ansible.errors imported outside plugins/action" || echo "OK"

docker compose run --rm test-v3 units -v --requirements
```

## Review focus

- Is the §4 boundary actually held (no resource-specific logic), or has
  something crept in?
- Precedence order — explicit task arg really beats `task_vars`?
- Does a resolution failure genuinely short-circuit before
  `_execute_module`?
- Is the bool/int coercion for `task_vars`-sourced values documented and
  tested, not just assumed?

## Commit

```
feat(v3): add LagoonActionShim for controller-side token resolution

The shim does exactly one thing in this phase: resolve a token via
module_utils.auth and inject it into the delegated module's args.
Name-to-id lookup injection (plan 4's second sidecar responsibility)
is Phase 4, not this story.

Per P2-D3 (docs/plans/v3-phase2-stories.md), this is a base class with
a per-module one-line subclass under plugins/action/<name>.py -- not a
single collection-wide plugin, since action_groups does not affect
dispatch. The Phase 3 generator will emit one subclass file per
generated module.

This is the only file in the collection that imports ansible.errors;
module_utils never does, converting LagoonError to AnsibleError only
here.

Refs docs/plans/v3-refactor.md Phase 2, 4
Refs docs/plans/2026-09-03-p2-s6-action-shim.md
```
