# AGENTS.md

Conventions for working in this repository. Read this before making changes.

## What this repo is

The collection root **is** the repo root: `galaxy.yml`, `plugins/`, `schema/`
and `meta/` are all top-level. The built collection is
`salsadigitalauorg.lagoon` (v3), a ground-up rewrite of the v1 `lagoon.api`
collection.

- `requires_ansible: '>=2.16'`
- Python 3.11, 3.12, 3.13
- **Zero runtime dependencies beyond `ansible-core`**

Design and rationale live in [`docs/plans/v3-refactor.md`](docs/plans/v3-refactor.md).
Work is broken into phases: see `docs/plans/v3-phase*-stories.md` for the
current phase's stories, and `docs/plans/YYYY-MM-DD-*.md` for per-story
implementation plans.

## `api/` is frozen — do not touch, do not imitate

`api/` holds the v1 `lagoon.api` collection. It is excluded from the built
artifact via `build_ignore` in `galaxy.yml` and will be deleted after Phase 8.
**Do not change anything under `api/` unless explicitly asked.**

More importantly: **its conventions are not this collection's.** It is the
largest body of code in the repo and it contains an action-plugin base class
that looks authoritative. It is not. Concretely, `api/` uses:

| `api/` (v1) | `plugins/` (v3) |
| --- | --- |
| 2-space indent | 4-space indent |
| `gql` / `graphql-core` at runtime | no runtime deps beyond `ansible-core` |
| camelCase methods (`createClient`, `getProjectIdFromName`) | snake_case |
| raises `AnsibleError` from `module_utils` | forbidden — see below |

Reading `api/` to understand *what v3 replaces* is fine. Copying its patterns
into `plugins/` is not.

## Layout

```
plugins/
├── module_utils/      # client, auth, ssh, cache, token, errors
├── action/            # LagoonActionShim base + per-module subclasses
├── modules/           # generated + hand-written modules
├── doc_fragments/     # shared DOCUMENTATION fragments
└── inventory/         # (planned, not yet present)
schema/                # vendored SDL, pinned per Lagoon version
codegen/               # (planned, not yet present) not shipped in the artifact
tests/unit/plugins/    # mirrors plugins/
docs/plans/            # design docs and phase stories
```

## Architectural boundaries

These are enforced by tests. Breaking one is a defect, not a style choice.

- **Modules hold 100% of the business logic.** A module invoked with an
  explicit `lagoon_api_token` and no action plugin must be fully functional
  standalone.
- **The action shim does only token resolution** (and, from Phase 4, lookup
  injection). No resource-specific logic. If a line only makes sense for one
  particular module, it does not belong in the shim.
- **`module_utils` never imports `ansible.errors`.** Modules convert the
  `errors.py` taxonomy via `fail_json()`; action and inventory plugins convert
  to `AnsibleError`. Guard:
  `tests/unit/plugins/action/test_shim.py::TestNoForbiddenImportsElsewhere`.
- **Every module needs its own `plugins/action/<name>.py`.** Ansible
  dispatches to an action plugin only when a same-named file exists there.
  `action_groups` only shares `module_defaults` — it does not affect dispatch.
- **No `gql`, `graphql-core`, `requests` or `urllib3` at runtime.** Per-file
  AST guard tests enforce this.
- **GraphQL selections are shape-bound, not depth-bound.** A document may
  select scalar leaves, a bounded single-valued object hop, and at most **one**
  list hop — each with scalar/enum leaves only. One further bounded
  scalar-leaf list is permitted beneath a single-valued hop, never beneath a
  list hop, and never a third level. Every nesting field must be declared in
  `PERMITTED_NESTED_SELECTIONS`; adding one is a reviewable diff. Enforced by
  `tests/unit/plugins/module_utils/query_depth.py`.
- **All user data passes through the GraphQL `variables` map.** Never
  interpolate user data into a query document — v1 did, and that is injection.

## Code style

- Every plugin file carries this header, immediately after any module
  docstring or leading comment block:
  ```python
  from __future__ import (absolute_import, division, print_function)
  __metaclass__ = type
  ```
  (Empty `__init__.py` files are exempt.)
- 4-space indent. Lines ≤ 79 characters.
- snake_case functions and variables; `_`-prefixed module-private helpers.
- Raise the typed exceptions from `errors.py`. Never a bare `Exception`.

## Comments and docstrings

**Do not refer to stories, plans, phases, or decision IDs in code.** No
`P2-D3`, no `docs/plans/...` paths, no "Phase 4's job", no "the story
mandates", no "parent plan §7.2".

Comments and docstrings must be **standalone, terse, and about the code as it
is now**. Keep the *why*; drop the *where it was decided*. If a constraint is
non-obvious, state the constraint and its reason, so a reader never needs a
planning document to understand the code in front of them.

```
✗  Per P2-D3, this is a base class (see docs/plans/v3-phase2-stories.md).

✓  Ansible dispatches to an action plugin only when a same-named file
   exists under plugins/action/, so each module needs its own subclass file.
```

Design history belongs in `docs/plans/` and in commit bodies. Both are correct
places for story IDs and decision references. Source files are not.

A corollary: a comment describing a shape the code no longer has is worse than
no comment at all. When you change code, update or delete the comments that
described the old shape.

## Security invariants

All of these are already enforced by tests. Do not weaken them.

- **Never** log or embed tokens or key material in exception messages,
  `repr()` output, or warnings.
- `validate_certs` defaults to `True`. v1 defaulted it to `False` — that was a
  defect, not a convention to carry forward (ISM-1552).
- Secrets on disk: create via `mkdtemp()` (mode 0700) plus
  `os.open(..., O_CREAT | O_EXCL, 0o600)` so the mode is correct from the
  instant the file exists, and remove in a `finally` block on every exit path.
  Never a predictable path under a world-writable directory.
- `subprocess` is always called with an argv **list**. Never `shell=True`,
  never a shell string.
- `no_log=True` on secret-bearing argspec options — but **never** `no_log` in a
  `DOCUMENTATION` block. `antsibull-docs`' `OptionsSchema` sets
  `extra="forbid"` and rejects it, failing the docs lint.
- SSH host key verification is on by default
  (`StrictHostKeyChecking=accept-new`). Disabling it requires an explicit,
  documented opt-in.

## Testing

```sh
docker compose run --rm test-v3 units -v --requirements   # or: make test
docker compose run --rm lint-docs-v3                      # or: make lint-docs
```

- Tests mirror plugin paths under `tests/unit/plugins/`.
- Relative imports:
  `from .....plugins.module_utils.auth import auth_argument_spec`
- `patch()` targets go through a module-level constant:
  ```python
  _MODULE_PATH = (
      'ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.auth')
  ```
- Any new `module_utils` file needs a matching AST forbidden-import guard test.
- **Assert the security property, not just the happy path.** If a requirement
  says a temp file is mode 0600 from creation, stat the real file — don't
  assert on a mocked call.

## Commits and changelogs

- Conventional Commits with a `(v3)` scope: `feat(v3):`, `fix(v3):`,
  `test(v3):`, `docs:`.
- The body explains *why*, in a terse manner.  Similar to code comments,
  commit bodies should not reference story IDs and plan paths.
- Add a `changelogs/fragments/` entry for user-visible changes. Sections are
  defined in `changelogs/config.yaml`.
- **One story, one commit.** See "How to work these stories" in the current
  phase's story document.
