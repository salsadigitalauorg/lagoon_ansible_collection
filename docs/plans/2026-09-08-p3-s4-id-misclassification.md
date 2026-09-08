# P3-S4 follow-up: `id` is mis-classified as create-only

**Date:** 2026-09-08
**Branch:** `3.x` (all three P3-S4 commits are unpushed — this lands as a
new commit on top, not an amend)
**Status:** Ready for implementation
**Audience:** the `code` agent implementing the fix

## Finding

`plugins/modules/project.py`'s `_CREATE_ONLY = ('id', 'organization',
'addOrgOwner')` (line 401) is wrong. `id` is not a create-only field — it is
`UpdateProjectInput`'s mandatory update key (`id: Int!`, SDL:2454), supplied
by the module itself from `current['id']` in `_update()` (line 716), and
server-assigned on create. A user should never supply it on any path.

The error comes from how `_CREATE_ONLY`/`_UPDATE_ONLY` were derived: the
plan computed `AddProjectInput − UpdateProjectPatchInput` (the **patch**
type). `id` falls out of that difference only because it lives on
`UpdateProjectInput`, the **wrapper** — not on the patch. Compared against
the wrapper, `id` is not create-only; it isn't a caller-supplied field on
either mutation.

Three consequences, all in `plugins/modules/project.py`:

1. `id`'s iteration in `_check_create_only()` (line 660) is unreachable.
   `LagoonResourceModule.run()` strips every `_DIFF_IGNORE` field from
   `desired` before any create/update/delete branch runs
   (`plugins/module_utils/resource.py:111-112`), and `id` is in
   `_DIFF_IGNORE` (line 392). `field not in desired` (line 661) always
   short-circuits for it.
2. `id=dict(type='int')` (line 519) is a phantom argspec option: accepted
   from the user, then discarded on create, update and delete alike.
3. `DOCUMENTATION` (lines 38-42) states the reverse of the truth —
   "Accepted only when creating a project."

`TestCreateOnlyIdDoesNotTrip` (`tests/unit/plugins/modules/test_project.py`,
line 468) does not catch this: it only exercises the *unsupplied* `id`
case, which `_desired_from_params`'s own `None` filter
(`resource.py:194-195`) would skip regardless of how `_check_create_only`
is keyed. The supplied-`id` case — the one that would reveal the silent
drop — is untested.

Two plan documents independently re-derive the same wrong classification;
one has it right:

| Doc | Line | `create_only` for `project` |
| --- | --- | --- |
| `docs/plans/v3-refactor.md` | 252 | `[organization, addOrgOwner]` — correct |
| `docs/plans/v3-phase3-stories.md` (P3-D1) | 56 | `[id, organization, addOrgOwner]` — wrong |
| `docs/plans/2026-09-08-p3-s4-build-sequence.md` (§0) | 62 | `[id, organization, addOrgOwner]` — wrong |

`P3-D1` explicitly notes `environment` has the identical
`UpdateEnvironmentInput{id, patch}` shape. Left uncorrected, P3-S6's
wire-shaping layer and P3-S9's generator will re-derive the same phantom
option for `environment` and every future `{id, patch}` resource.

## Fix

### `plugins/modules/project.py`

- Remove `id` from `_CREATE_ONLY` (line 401) — becomes
  `('organization', 'addOrgOwner')`. Reword the comment above it: it
  currently says "Present on AddProjectInput only" (the comparison that
  caused the error) — state instead that create-only is derived against
  `UpdateProjectInput` (the wrapper), not `UpdateProjectPatchInput`.
- Delete the `id` argspec option entirely (line 519).
- Delete the `id` `DOCUMENTATION` block entirely (lines 38-42).
- Reword `_DIFF_IGNORE`'s comment (lines 391-392): `id` is the update key —
  read by `_update`/`_delete` from the raw read result, never user-supplied,
  never diffed. Not "server-assigned; excluded from diffing" alone; state
  *why* a user could never usefully supply it.
- No change to `_READ_SELECTION` (line 428) — `id` must stay selected;
  `_update`/`_delete` read `current['id']`/`current['name']` from the read
  result, and `LagoonResourceModule._do_update`/`_do_delete` pass `current`
  to those closures **unfiltered** (`resource.py:158`, `:170` — only
  `before`/`after_preview` go through `_filtered()`). Confirmed by reading
  both call sites; this is why keeping `id` in `_FIELDS`/`_DIFF_IGNORE`
  while dropping the argspec option is safe.
- No change to `_check_create_only()`'s body (lines 660-683) — it iterates
  `_CREATE_ONLY`, which simply shrinks by one entry.

### `tests/unit/plugins/modules/test_project.py`

- Amend `test_every_wire_field_has_a_derived_argspec_option` (line 585) to
  exclude `_DIFF_IGNORE` fields from the check — import `_DIFF_IGNORE`
  alongside `_FIELDS`. State in the docstring *why*: `_desired_from_params`
  skips `diff_ignore` fields before it ever consults `params`
  (`resource.py:187-189`), so the silent-drop premise this test guards
  cannot apply to them.
- Amend `test_argspec_has_no_option_without_a_wire_field` (line 600) the
  same way — `derived` must also subtract `_DIFF_IGNORE`, or removing
  `id`'s argspec option makes this test fail in the opposite direction.
- Replace `TestCreateOnlyIdDoesNotTrip` (lines 468-484). Its subject (`id`
  tripping create-only enforcement) no longer exists once `id` leaves
  `_CREATE_ONLY`. Substitute a behavioural test that supplies `id`
  explicitly (e.g. `_make_module(id=999, git_url=..., ...)` on create, and
  again on update) and asserts it appears in neither the `addProject`
  payload nor the `updateProject` patch — this is the assertion whose
  absence let the phantom option through in the first place. Prefer this
  over deleting the test outright: an argspec-absence check alone would not
  catch a future re-introduction of the option that is also wired through
  to a payload.
- Add a test asserting `'id' not in argument_spec()`, so a future change
  (hand-written or generated) that re-adds the option fails immediately
  rather than silently reintroducing the same defect.

### Plan docs

- `docs/plans/v3-phase3-stories.md` P3-D1 (line 56): correct the
  create-only list to `id`, `organization`, `addOrgOwner` → `organization`,
  `addOrgOwner`. Add a decision note: `create_only` must be derived as
  `AddInput − UpdateInput` (the wrapper type), never
  `AddInput − UpdatePatchInput` — a field present only on the wrapper
  (typically the id key) is not create-only, it is the update key and is
  never user-supplied on either mutation.
- `docs/plans/2026-09-08-p3-s4-build-sequence.md` §0 (line 62): same
  correction to the verified-findings table. Flag it as corrected on
  review — the original table was presented as verified against the real
  SDL and was not, for this one entry.
- `docs/plans/v3-refactor.md:252`: no change — already correct. Cite it as
  the authority the other two should have matched.

### Explicitly out of scope for this fix

- The `private_key` non-idempotency behaviour (documented but with an
  undocumented practical consequence: supplying it reports `changed: true`
  on every run, forever). Separate concern, arguably a design decision
  rather than a defect — track separately if it needs addressing.
- Two minor nits from the review: the dead `changed_no_log is None`
  fallback branch in `_report_diff` (`resource.py:254-259`), and the
  source-order dependency in `_module_and_class_level_literals`
  (`tests/unit/plugins/module_utils/query_depth.py`) worth a one-line
  comment. Neither is load-bearing; fold in opportunistically, don't block
  on them.
- No changelog fragment change. `changelogs/fragments/project-module.yml`
  and all three P3-S4 commits are unpushed and unreleased; `id` never
  shipped as a working option, so there is nothing user-visible to
  announce. The existing fragment's description of the module remains
  accurate.

## Verification

```sh
docker compose run --rm test-v3 units -v --requirements \
  tests/unit/plugins/modules/test_project.py
docker compose run --rm test-v3 units -v --requirements
docker compose run --rm lint-docs-v3
antsibull-changelog lint
```

`lint-docs-v3` is the gate that matters most here: `antsibull-docs` cross-
checks the argspec against `DOCUMENTATION`, so the argspec option and its
docs block must be removed together or the lint fails on the mismatch.

## Commit

One commit, `fix(v3):` scope, per this repo's one-story-one-commit
convention. Body should explain the derivation error (compared against the
patch type instead of the wrapper) and note the two plan docs corrected
alongside it — no story IDs or plan paths in the commit body itself beyond
a `Refs` line, per this repo's comment/commit conventions.
