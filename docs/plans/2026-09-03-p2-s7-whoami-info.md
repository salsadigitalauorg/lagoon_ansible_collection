# P2-S7 — `whoami_info` walking skeleton + sweep extension + `graphql-mock-v3`

**Date:** 2026-09-03
**Story:** [`docs/plans/v3-phase2-stories.md`](./v3-phase2-stories.md) § P2-S7
**Parent plan:** [`docs/plans/v3-refactor.md`](./v3-refactor.md) §9 Phase 2, §12.3
**Branch:** `3.x`
**Depends on:** P2-S6 (`498d2a1`)
**Status:** Implemented, pending review

---

## Scope

```
plugins/modules/whoami_info.py                          (new)
plugins/action/whoami_info.py                           (new)
tests/unit/plugins/modules/__init__.py                  (new)
tests/unit/plugins/modules/test_whoami_info.py           (new)
tests/unit/plugins/module_utils/query_depth.py           (modified)
tests/unit/plugins/module_utils/test_query_depth.py      (modified)
tests/integration/whoami_info.yml                        (new)
.docker/Dockerfile.graphql-mock-v3                       (new)
.docker/graphql-mock/package-lock.json                   (new)
meta/runtime.yml                                          (modified)
docker-compose.yml                                        (modified)
Makefile                                                  (modified)
```

`whoami_info` is the first hand-written module in `plugins/modules/`. It
proves endpoint -> auth -> shim -> module -> client end to end before the
Phase 3 generator exists, and resolves parent-plan open item §12.3 (`*_info`
modules do need the action shim, since they require a token exactly like any
other module).

---

## The unresolved assumption, resolved

The story's own header flagged this as the one unverified assumption in
Phase 2: whether the vendored `schema/lagoon-2.33.0.graphql` loads cleanly
under the mock server's `graphql-import`/`graphql-tools` loader stack,
un-verifiable in the story-breakdown session because Docker Desktop doesn't
share `/tmp` with containers on that machine.

**It loads cleanly.** `docker compose build graphql-mock-v3 && docker
compose up -d graphql-mock-v3 && make verify-mock` succeeds: `graphql-import`
parses the vendored SDL without error and the mock resolves a real query
(`{ me { id email } }`) against it.

This is a **manual** verification -- `make verify-mock` is not wired into
`make test` or CI, so it is demonstrated by running it, not continuously
enforced. A regression here (e.g. a future SDL vendor that doesn't parse)
would only surface the next time someone runs this target by hand.

One wrinkle, not a loader incompatibility: the mock's auto-mocking layer
(`@graphql-tools/mock`) cannot synthesise a value for the schema's custom
`JSON` scalar (used by e.g. `lagoonVersion`) with no mock function
registered for it, and raises `Error: No mock defined for type "JSON"` for
any query touching such a field. This reproduces identically against the
**v1** `graphql-mock` service serving `api/tests/common/schema.graphql`, so
it is a pre-existing property of the mock tooling's scalar handling, not
something introduced by vendoring 2.33.0's SDL, and not a loader failure --
the schema parses and resolves fine for every field typed as a built-in
scalar. `make verify-mock`'s query (`me { id email }`) was chosen
deliberately to avoid a custom-scalar field for this reason, and this
paragraph is recorded here (not just in the Makefile comment) since it is
exactly the kind of finding the story asked to be raised rather than quietly
routed around.

---

## Part 1 — the module

### Query and dropped field

`LagoonClient.build_query('me', fields=[...7 scalar fields...])`, with the
`fields` list literal written inline in the call (not a module-level
constant) -- this was a deliberate choice so the AST sweep extension (Part
2) has to resolve the call site itself rather than following a name
reference, which better matches what the Phase 3 generator's templates will
actually emit.

**Deliberately drops `groups`** from v1's equivalent query. A nested
`groups { name type }` selection is forbidden under the flat-query rule
(`docs/plans/v3-refactor.md` 7.1, enforced by `query_depth.py`). Recorded
here and in the module's `RETURN` docs and commit body as a breaking change
for Phase 8's migration table.

### Absolute imports

Uses fully-qualified `ansible_collections.salsadigitalauorg.lagoon...`
imports throughout, per the story's explicit warning that the relative
`.....plugins.module_utils` style used in this repo's *test* files works
under bare pytest but not under AnsiballZ. Verified directly: a bare
`from ansible.errors import AnsibleError`-style relative import of
`plugins/action/__init__.py` fails under `ansible-test units` with
`ModuleNotFoundError: No module named 'ansible.errors'` when attempted from
a file outside the `ansible_collections` namespace tree, while the absolute
form resolves correctly in every case tried (module_utils, action base
class, and `AnsibleModule` itself) -- see the shell history for this story's
session for the throwaway fixtures used to confirm this before writing the
real files.

Import lines are wrapped across two lines (`from X.module_utils \n import
auth`) rather than a parenthesised multi-name import, to stay within the
79-column limit in `AGENTS.md` -- the single-target form reads slightly
better than `from X import (\n    name,\n)` at this line length and matches
what a short import list looks like elsewhere in `plugins/module_utils`.

### Module logic factored into `run_module(module)`

`main()` is a two-line wrapper: construct `AnsibleModule`, call
`run_module()`, translate `LagoonError` to `fail_json`. `run_module()` takes
anything exposing a `.params` mapping (not literally `AnsibleModule`) so the
unit tests construct a plain `MagicMock` with only `.params` set and never
import or construct the action shim at all -- the concrete proof, not just
an assertion, that a module invoked with an explicit `lagoon_api_token` and
no action plugin is fully functional standalone (`AGENTS.md`,
"Architectural boundaries").

`me: null` (an invalid/expired token that somehow passed the shim, or one
with insufficient scope) raises `LagoonNotFoundError('user', query='me')`,
converted to `fail_json` by `main()`'s existing `LagoonError` handling --
no new error-handling path was needed.

`supports_check_mode=True` with no check-mode branching in `run_module()`:
the read always executes and returns the same shape, since there is nothing
for check mode to meaningfully skip in a read-only module.

---

## Part 2 — the sweep extension

`whoami_info.py` contains the Python source text
`LagoonClient.build_query('me', fields=[...])` -- a function *call*, not a
string literal containing `query me { ... }`. Confirmed by running
`test_vacuous_pass_guard` against the real tree with only the pre-extension
sweep: it fails, exactly as the story predicted, because
`collect_candidate_documents()`'s original two rules (named-constant
assignment, literal-containing-"query "/"mutation "` scan) find nothing in
this file.

### Design

Added a third detection rule, `_build_query_call_sites()`:

1. `_is_build_query_call()` matches on the call's function name only --
   `.attr == 'build_query'` for the attribute form
   (`LagoonClient.build_query(...)`, or via any alias), `.id == 'build_query'`
   for the bare form (`from ... import build_query`-style). Matching on name
   only, not on the callee resolving to the *real* `LagoonClient`, is
   deliberate and matches the story spec; `TestBuildQuerySweepExtension
   .test_decoy_function_named_build_query_is_still_caught` documents the
   consequence (a same-named local function's call site is still resolved
   via the genuine implementation, not the decoy body).
2. `_literal_from_ast()` resolves an AST node to a plain Python value if,
   and only if, it is built entirely from `Constant`/`List`/`Tuple`/`Dict`
   nodes -- anything else (a `Name`, a call, a comprehension, an f-string,
   a `**`/`*` spread) raises `ValueError`, caught by the caller.
3. `_resolve_build_query_call()` resolves every positional and keyword
   argument this way, then calls the *real*
   `LagoonClient.build_query(**resolved_kwargs)` to reconstruct the actual
   document -- never a parallel reimplementation of its string-building
   logic, so the sweep cannot drift from the real function's output.
4. A call that is not fully resolvable (dynamic `fields`, a missing
   required `fields` keyword, a `TypeError`/`LagoonConfigError` from
   `build_query()` itself) is not dropped -- it is recorded with the
   `UNRESOLVED_BUILD_QUERY` placeholder string, so it still counts toward
   the vacuous-pass guard. Callers of `collect_candidate_documents()` must
   skip the depth assertion for that placeholder rather than pass it to
   `assert_flat_query()` (which would report a false violation on a
   9-character sentinel string). `test_sweep_runs_clean_against_current_plugins_tree`
   and the new `TestBuildQuerySweepExtension` tests were both updated to
   skip on the placeholder explicitly, rather than silently.

### Why call the real implementation instead of re-deriving it

`query_depth.py` now imports `module_utils.client.LagoonClient` and
`module_utils.errors.LagoonConfigError` directly. This is safe under the
existing "never `import` a module file" constraint from P1-S5: `client.py`
has no `AnsibleModule` dependency, so it imports cleanly under bare pytest,
unlike anything under `plugins/modules/`. The docstring records this
explicitly so a future contributor doesn't "fix" it into a reimplementation
that could drift from the real `build_query()`.

### Negative-path test

`TestBuildQuerySweepExtension.test_decoy_function_named_build_query_is_still_caught`
is the negative-path proof the story asked for, achieved differently than
literally specified: the real `build_query()` cannot itself produce a
nested document (it rejects `{` in field names via `_FIELD_FORBIDDEN_RE`),
so there is no way to make the *resolved* call site violate the depth
check. Instead, the fixture's decoy function body is itself a string
literal containing `query { ... { ... { nested } } }`, which the
**unrelated, pre-existing** literal-scan rule (rule 2) still catches as its
own candidate. The test asserts both properties in one place: the call site
resolves via the genuine `build_query()` (proving the extension calls
through rather than executing the decoy), and the decoy's own literal
return string is still flagged as a depth-3 violation (proving the
unrelated rule is undisturbed by having a same-named function nearby). This
is recorded in the test's docstring/inline comments so a future reader
doesn't mistake "the resolved call is flat" for "no violation was caught
here at all".

---

## Part 3 — `graphql-mock-v3`

- `Dockerfile.graphql-mock-v3` matches the story's spec exactly: `npm ci`
  (not `npm install`) against a real, generated lockfile, `schema/lagoon-2.33.0.graphql`
  copied in as `schema.graphql`.
- `.docker/graphql-mock/package-lock.json` generated via
  `npm install --package-lock-only` against the existing, **unmodified**
  `package.json` (verified via `git diff` immediately after generation --
  clean). `npm ci` against the resulting lockfile builds successfully with
  no `node_modules` artifact left in the working tree (single-layer Docker
  build; nothing generated on the host beyond the lockfile itself).
- `docker-compose.yml` gains `graphql-mock-v3`, host port `4200` (v1's
  `graphql-mock` publishes an ephemeral port only) so both can run
  simultaneously during the migration period per parent-plan D18.
- `Makefile` gains `mock-up`/`mock-down`/`verify-mock`, matching the
  story's spec with one change: the `verify-mock` query is `{ me { id
  email } }`, not `{ lagoonVersion }` -- see "The unresolved assumption,
  resolved" above for why `lagoonVersion` (a `JSON`-typed field) is the
  wrong choice for this specific check even though the schema loads
  correctly.

### End-to-end proof

`tests/integration/whoami_info.yml`, a single ad hoc playbook (the story's
own "acceptable scope creep" option, given a full integration target is
Phase 5's formal home). Run manually against `graphql-mock-v3` on the
docker-compose network with `lagoon_api_token` passed directly (no real SSH
host in the mock setup, exactly as the story specifies) -- confirmed via
`ansible-playbook tests/integration/whoami_info.yml -e
whoami_info_endpoint=http://graphql-mock-v3:4000/graphql` from inside the
`ansible-test` image on the mock's compose network, output:

```
TASK [Look up the current user via the real action shim] ***
ok: [localhost] => {"changed": false, "user": {"created": "Hello World", ...}}
TASK [Assert the module ran end to end and reported no change] ***
ok: [localhost] => { "changed": false, "msg": "All assertions passed" }
```

This exercises the real action shim (`plugins/action/whoami_info.py` exists,
so Ansible dispatches to `LagoonActionShim` rather than running the module
directly) through to the real module and the real `LagoonClient` transport,
against the real vendored schema.

---

## `meta/runtime.yml`

Adds `action_groups: {all: [whoami_info]}`, with a comment stating
explicitly that this is for `module_defaults` sharing only (P2-D3) -- the
presence of `plugins/action/whoami_info.py` is what causes dispatch to
`LagoonActionShim`, not this entry.

---

## Verification run (this session)

```
docker compose run --rm test-v3 units -v --requirements
  -> 326 passed, 1 skipped (module_utils incl. query_depth.py extension)
  -> 8 passed (modules -- test_whoami_info.py, all four Python versions)
  -> 27 passed (action/controller, unaffected)
  -> 0 FAILED/ERROR across the whole matrix (all four Python versions x 3
     groups)

docker compose run --rm lint-docs-v3
  -> exit 0

docker compose build graphql-mock-v3 && docker compose up -d graphql-mock-v3
  && make verify-mock && docker compose down graphql-mock-v3
  -> builds and serves the vendored SDL; verify-mock passes

ansible-galaxy collection build (via the ansible-test image)
  -> plugins/action/whoami_info.py and plugins/modules/whoami_info.py both
     present in the built artifact; tests/, .docker/, docker-compose.yml,
     Makefile all correctly excluded per existing build_ignore

grep -rn "import gql\|import requests\|from graphql" plugins/        -> none
grep -rln "ansible.errors" plugins/                                   -> plugins/action/__init__.py only
grep -n "/tmp\b" plugins/module_utils/ssh.py plugins/module_utils/cache.py -> none
grep -n "shell=True" plugins/module_utils/ssh.py plugins/module_utils/cache.py -> none
grep -n "^from \.\." plugins/modules/whoami_info.py                   -> none
```

---

## Deviations from the story's literal text

1. **`verify-mock`'s query** -- `{ me { id email } }` instead of
   `{ lagoonVersion }`. Documented above and in the Makefile comment. This
   is the one place this story deviated from the literal spec text; the
   *behaviour* being verified (the SDL loads under `graphql-import`) is
   unchanged, only the specific query proving it.
2. **Negative-path test for the sweep extension** achieved via the
   unrelated literal-scan rule rather than a `build_query()`-produced
   nested document, since the real implementation cannot be made to
   produce one. The story explicitly allowed for this: "If this proves
   impractical, document precisely why and instead strengthen the
   assertion that unresolvable calls are surfaced rather than silently
   skipped" -- both the impracticality and the surfaced-not-skipped
   property (`test_dynamic_fields_argument_is_unresolved_not_dropped`) are
   covered.

No other deviations. The vendored-SDL-vs-mock-loader compatibility question
the story flagged as its one unverified assumption is resolved: it loads
cleanly.
