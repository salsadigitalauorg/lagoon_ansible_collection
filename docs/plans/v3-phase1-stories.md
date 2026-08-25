# v3 Phase 1 — Foundations: Implementation Stories

**Date:** 2026-08-25
**Parent plan:** [`docs/plans/v3-refactor.md`](./v3-refactor.md) §9 Phase 1
**Branch:** `3.x`
**Status:** Ready for implementation

---

## How to work these stories

1. Stories are executed **in order**. Each depends on the ones before it.
2. Each story produces **exactly one commit**. Do not batch stories into one commit.
3. After each commit, hand the commit SHA to the `review` agent. Iterate on that
   story's commit (amend or follow-up fixup, reviewer's choice) until the reviewer
   is satisfied. Only then start the next story.
4. Every story below carries its own acceptance criteria and verification commands.
   A story is not complete until its verification commands pass locally.
5. If a story's implementation reveals that the parent plan is wrong, **stop and
   raise it** rather than silently deviating. Record the deviation in the story's
   commit body.

---

## Phase 1 decisions (resolved during story breakdown)

These resolve open items from `v3-refactor.md` §12 and supersede the parent plan
where they differ. They apply to every story below.

| # | Item | Decision |
| - | ---- | -------- |
| **P1-D1** | **Repo layout** | The v3 collection lives at the **repository root**. `galaxy.yml`, `meta/`, `plugins/`, `tests/`, `schema/`, `codegen/` are all top-level. The repo will be renamed/moved to `github.com/salsadigitalauorg/ansible-lagoon` and the checkout is expected at `ansible_collections/salsadigitalauorg/lagoon`. This supersedes the `salsadigitalauorg/lagoon/` sub-tree shown in the parent plan §5. |
| **P1-D2** | **v1 coexistence** | `api/` (the v1 `lagoon.api` collection) stays in place, untouched, for the duration of phases 1–8. It is **excluded from the v3 build artifact** via `build_ignore`. It is deleted in a final cleanup story after Phase 8, along with `.docker/Dockerfile.docs` v1 paths and the v1 docker-compose services. |
| **P1-D3** | **SDL version** | Fetched live from a real Lagoon by the maintainer (see P1-S2). Path is `schema/lagoon-<version>.graphql` + `schema/VERSION`. The `2.33.1` in the parent plan is an assumption — the fetched value wins, and every reference to it (galaxy.yml, allowlist, generated-file headers) uses the real value. |
| **P1-D4** | **Support matrix** | `requires_ansible: '>=2.16'`. Tested Python: **3.11, 3.12, 3.13**. Python 3.9/3.10 (v1's floor) are dropped — this is a clean-break major and both are EOL. |
| **P1-D5** | **CI** | **Out of scope for Phase 1.** All CI wiring (`test.yml` matrix, sanity, `verify-generated` drift guard, docs) lands in Phase 8 per the parent plan. Phase 1 verification is local, via the docker-compose service added in P1-S1. Each story below states its exact local verification command. |

---

## Story index

| ID | Story | Depends on | Est. |
| -- | ----- | ---------- | ---- |
| P1-S1 | Scaffold the `salsadigitalauorg.lagoon` collection at repo root | — | M |
| P1-S2 | Vendor the Lagoon GraphQL SDL | P1-S1 | S |
| P1-S3 | `module_utils/errors.py` — exception hierarchy | P1-S1 | S |
| P1-S4 | `module_utils/client.py` — `LagoonClient` | P1-S3 | L |
| P1-S5 | Flat-query nesting-depth guardrail | P1-S4 | M |

---

# P1-S1 — Scaffold the `salsadigitalauorg.lagoon` collection at repo root

## Goal

A buildable, empty-but-valid `salsadigitalauorg.lagoon` v3.0.0 collection at the
repository root, with a working local test loop, that does **not** include the v1
`api/` collection in its build artifact.

## Context

- The v1 collection is at `api/` with its own `api/galaxy.yml` (`lagoon.api` v1.3.0).
  It must keep working. Do not modify anything under `api/`.
- Because the v3 `galaxy.yml` sits at the repo root, `ansible-galaxy collection build`
  run at the root will otherwise sweep `api/`, `.docker/`, and `docs/` into the
  tarball. `build_ignore` must prevent this.
- `docs/` already exists (`docs/plans/`). The parent plan §5 wants `docs/adr/` and
  `docs/migration-v1-to-v3.md` later — do not create those now, they belong to Phase 8.
- Existing docker-compose services (`test`, `graphql-mock`, `lint-docs`, `docs`) all
  mount `./api`. Leave them alone; add new services alongside.

## Files to create

```
galaxy.yml
meta/runtime.yml
README.md                    # replace the existing root README (see note below)
changelogs/config.yaml
CHANGELOG.rst                # antsibull-changelog seed
plugins/module_utils/__init__.py
plugins/modules/__init__.py
tests/unit/__init__.py
tests/unit/plugins/__init__.py
tests/unit/plugins/module_utils/__init__.py
tests/unit/requirements.txt
Makefile
```

## Files to modify

```
docker-compose.yml           # add v3 services
.gitignore                   # add tests/output, built collection artifacts
README.md                    # root README currently describes the repo; rework for v3
```

## Implementation notes

### `galaxy.yml`

Model it on `api/galaxy.yml` (same authors, license `GPL-2.0-or-later`, same
`repository` URL) with these changes:

```yaml
namespace: salsadigitalauorg
name: lagoon
version: 3.0.0
readme: README.md
description: An Ansible collection for interacting with the Lagoon GraphQL API.
tags:
  - lagoon
  - graphql
  - cloud
dependencies: {}
build_ignore:
  - api                    # v1 collection — removed after Phase 8 (P1-D2)
  - .docker
  - .codegraph
  - docs
  - codegen                # generator is a dev tool, not shipped (parent plan §5)
  - docker-compose*.yml
  - Makefile
  - '*.md'                 # keep README.md — see note
  - .github
```

> **Careful:** `'*.md'` in `build_ignore` would also drop `README.md`, which
> `galaxy.yml` declares as the readme and which `ansible-galaxy collection build`
> requires. Enumerate the specific top-level markdown files to exclude
> (`CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`, `NOTICE`) instead of
> globbing. Verify with the tarball listing in the acceptance criteria.

Do **not** add a `dependencies` entry and do **not** create a runtime
`requirements.txt` — dropping `gql`/`requests`/`requests-toolbelt`/`urllib3` from
the runtime is an explicit goal (parent plan D3). v3 runtime depends only on
`ansible-core`.

### `meta/runtime.yml`

```yaml
---
requires_ansible: '>=2.16'
```

No `action_groups` yet — the `LagoonActionShim` arrives in Phase 2 (P1-D4 /
parent plan §9 Phase 2). Adding an empty or speculative `action_groups` block now
would fail `ansible-doc` validation.

### `changelogs/config.yaml`

Standard `antsibull-changelog` config for a collection:

```yaml
---
changelog_filename_template: ../CHANGELOG.rst
changelog_filename_version_depth: 0
changes_file: changelog.yaml
changes_format: combined
keep_fragments: false
mention_ancestor: true
new_plugins_after_name: removed_features
notesdir: fragments
prelude_section_name: release_summary
prelude_section_title: Release Summary
sections:
  - [major_changes, Major Changes]
  - [minor_changes, Minor Changes]
  - [breaking_changes, Breaking Changes / Porting Guide]
  - [deprecated_features, Deprecated Features]
  - [removed_features, Removed Features (previously deprecated)]
  - [security_fixes, Security Fixes]
  - [bugfixes, Bugfixes]
  - [known_issues, Known Issues]
title: Salsa Digital Lagoon
trivial_section_name: trivial
```

Create `changelogs/fragments/.keep` so the directory survives git.

Seed `CHANGELOG.rst` by running `antsibull-changelog init .` if available;
otherwise a minimal valid RST stub is acceptable — the reviewer should confirm
`antsibull-changelog lint` passes either way.

### `tests/unit/requirements.txt`

The v1 file (`api/tests/unit/requirements.txt`) pins `gql`, `requests-toolbelt==0.10.1`,
`urllib3==1.26.19` as a test-breakage workaround. **None of that carries forward.**
v3 unit tests need only:

```
ansible-core
pytest
pytest-forked
```

No `graphql-core` here — it is a **generator-only** dependency and belongs in
`codegen/requirements.txt` in Phase 3.

### `Makefile`

Targets needed now. `generate` / `verify-generated` are Phase 3 — do not stub them.

```make
COLLECTION_PATH := /usr/share/ansible/collections/ansible_collections/salsadigitalauorg/lagoon

.PHONY: test build lint-docs shell

test:            ## Run unit tests in the containerised ansible-test image
	docker compose run --rm test-v3 ansible-test units -v --requirements

build:           ## Build the collection artifact and list its contents
	ansible-galaxy collection build --force --output-path ./dist

lint-docs:
	docker compose run --rm lint-docs-v3

shell:
	docker compose run --rm test-v3 bash
```

### `docker-compose.yml` additions

Add alongside the existing services. The mount is the **repo root**, because that
is the collection root (P1-D1):

```yaml
  test-v3:
    image: ghcr.io/salsadigitalauorg/ansible-test:latest
    volumes:
      - .:/usr/share/ansible/collections/ansible_collections/salsadigitalauorg/lagoon
    working_dir: /usr/share/ansible/collections/ansible_collections/salsadigitalauorg/lagoon

  lint-docs-v3:
    build:
      context: .
      dockerfile: .docker/Dockerfile.docs
      args:
        - OPERATION=lint
    volumes:
      - .:/collections/ansible_collections/salsadigitalauorg/lagoon
    working_dir: /collections/ansible_collections/salsadigitalauorg/lagoon
    command: ["antsibull-docs", "lint-collection-docs", "--plugin-docs", "."]
```

> **Known wrinkle to record, not fix:** because `api/` sits inside the v3
> collection root, `ansible-test sanity` at the root will also scan `api/`.
> `ansible-test units` is unaffected (it only collects `tests/unit`). Sanity is
> Phase 8, and `api/` is deleted before then per P1-D2. Note this in the commit
> body so Phase 8 does not rediscover it.

### `README.md`

The current root `README.md` describes the repo generally. Rework it to describe
the v3 collection (it is now the `galaxy.yml` readme), with a short section
pointing at `api/README.md` for v1 during the transition. Keep it brief — full
docs are Phase 8.

## Acceptance criteria

- [ ] `ansible-galaxy collection build` at the repo root succeeds.
- [ ] The built tarball contains `plugins/`, `meta/runtime.yml`, `README.md`,
      `MANIFEST.json`, `FILES.json` — and contains **no** path starting with
      `api/`, `.docker/`, `docs/`, `codegen/`, `.github/`, `.codegraph/`.
- [ ] `docker compose run --rm test-v3 ansible-test units -v --requirements` runs
      and reports zero tests collected without erroring on collection layout.
- [ ] `antsibull-changelog lint` passes.
- [ ] `docker compose run --rm lint-docs-v3` passes.
- [ ] The v1 collection still builds: `cd api && ansible-galaxy collection build`.
- [ ] `git status` shows no modifications under `api/`.

## Verification commands

```sh
ansible-galaxy collection build --force --output-path /tmp/v3build
tar -tzf /tmp/v3build/salsadigitalauorg-lagoon-3.0.0.tar.gz | sort
tar -tzf /tmp/v3build/salsadigitalauorg-lagoon-3.0.0.tar.gz | grep -E '^(api|docs|codegen|\.docker|\.github)/' && echo "FAIL: excluded paths present" || echo "OK: artifact clean"
docker compose run --rm test-v3 ansible-test units -v --requirements
docker compose run --rm lint-docs-v3
( cd api && ansible-galaxy collection build --force --output-path /tmp/v1build )
```

## Review focus

- Is `build_ignore` actually correct? Check the tarball listing, not the config.
- Does `README.md` survive the build despite the markdown exclusions?
- Is `requires_ansible` `>=2.16` and nothing narrower/wider?
- Zero runtime dependencies declared. No `gql` anywhere.
- Nothing under `api/` touched.

## Commit

```
feat(v3): scaffold salsadigitalauorg.lagoon collection at repo root

Adds galaxy.yml, meta/runtime.yml, changelog config and a containerised
local test loop for the v3 collection. The collection root is the repo
root; api/ (v1 lagoon.api) is excluded from the build artifact and stays
in place until after Phase 8.

Refs docs/plans/v3-refactor.md Phase 1
```

---

# P1-S2 — Vendor the Lagoon GraphQL SDL

## Goal

A committed, version-pinned GraphQL SDL that becomes the single input to the
Phase 3 generator, plus a documented, repeatable procedure for refreshing it.

## Context

- `api/tests/common/schema.graphql` (4,923 lines) is the only schema in the repo.
  It has **no version marker** and unknown provenance. It is *not* to be copied —
  the maintainer will fetch a fresh one from a live Lagoon.
- The generator relies on **SDL descriptions** for option help text (parent plan
  §6.1.5). If the fetched SDL lacks `"""..."""` descriptions, generated docs will
  be empty and the fetch must be redone. This is a hard acceptance check below.
- `.docker/Dockerfile.graphql-mock` copies `api/tests/common/schema.graphql`. The
  v3 mock target should use the new vendored schema — but integration targets are
  Phase 5, so only add the v3 mock wiring if it is trivial; otherwise defer and
  note it.

## Maintainer action required before this story can be committed

The implementing agent cannot reach a live Lagoon. **Yusuf runs this**, then hands
the resulting file and version string to the agent.

```sh
# 1. Pick the target Lagoon (use the GovCMS target to satisfy plan §12.1).
lagoon config list
lagoon login -l <target>
export LAGOON_TOKEN=$(lagoon -l <target> get token)
export LAGOON_GRAPHQL=https://api.lagoon.example.com/graphql   # the target's endpoint

# 2. Record the exact server version. This value drives the filename,
#    schema/VERSION, and every generated-file header.
curl -sS "$LAGOON_GRAPHQL" \
  -H "Authorization: Bearer $LAGOON_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ lagoonVersion }"}'
# -> {"data":{"lagoonVersion":"<VERSION>"}}

# 3. Print the SDL. gql-cli emits SDL including descriptions.
pip install 'gql[requests]'
mkdir -p schema
gql-cli "$LAGOON_GRAPHQL" --print-schema \
  --header Authorization:"Bearer $LAGOON_TOKEN" \
  > schema/lagoon-<VERSION>.graphql

# 4. Sanity-check descriptions survived introspection.
grep -c '"""' schema/lagoon-<VERSION>.graphql    # must be > 0, expect hundreds
```

If step 4 returns `0`, the server has introspection descriptions disabled. Stop —
generated docs would be empty. Try a different endpoint or raise it.

## Files to create

```
schema/lagoon-<VERSION>.graphql      # the fetched SDL, committed verbatim
schema/VERSION                       # provenance record
schema/README.md                     # the refresh procedure above
```

## Files to modify

```
Makefile                             # add a fetch-schema target
```

## Implementation notes

### `schema/VERSION`

Plain, greppable, machine-readable by the Phase 3 generator. Do not use YAML —
the generator reads `lagoon_version` from `codegen/allowlist.yml`; this file is
for humans and for CI drift messages.

```
lagoon_version=<VERSION>
endpoint=<the endpoint it was fetched from>
fetched_at=<ISO 8601 date>
fetched_by=<name>
tool=gql-cli --print-schema
```

### `Makefile` — `fetch-schema`

Codify the procedure so it is not lost in a README. It must **not** overwrite an
existing schema silently, and must refuse to run without an explicit version.

```make
.PHONY: fetch-schema
fetch-schema:            ## Fetch and vendor the Lagoon SDL. Requires LAGOON_GRAPHQL, LAGOON_TOKEN, LAGOON_VERSION
	@test -n "$(LAGOON_GRAPHQL)" || (echo "LAGOON_GRAPHQL is required" && exit 1)
	@test -n "$(LAGOON_TOKEN)"   || (echo "LAGOON_TOKEN is required" && exit 1)
	@test -n "$(LAGOON_VERSION)" || (echo "LAGOON_VERSION is required" && exit 1)
	@test ! -f schema/lagoon-$(LAGOON_VERSION).graphql || \
	  (echo "schema/lagoon-$(LAGOON_VERSION).graphql exists; remove it first" && exit 1)
	gql-cli "$(LAGOON_GRAPHQL)" --print-schema \
	  --header Authorization:"Bearer $(LAGOON_TOKEN)" \
	  > schema/lagoon-$(LAGOON_VERSION).graphql
	@grep -q '"""' schema/lagoon-$(LAGOON_VERSION).graphql || \
	  (echo "FAIL: SDL has no descriptions — generated docs would be empty" && exit 1)
```

`LAGOON_TOKEN` on a make command line is visible in the process table. Document in
`schema/README.md` that it must be exported into the environment, not passed as
`make fetch-schema LAGOON_TOKEN=...`.

### Do not

- Do not add `schema/` to `build_ignore`. The SDL ships with the collection: it is
  small, and it documents exactly which API version the modules were generated
  against. Confirm it appears in the tarball.
- Do not delete or modify `api/tests/common/schema.graphql`. v1 tests use it.
- Do not reformat, prettify, or hand-edit the fetched SDL. It is a vendored
  artifact; byte-for-byte fidelity is what makes the Phase 8 drift guard meaningful.

## Acceptance criteria

- [ ] `schema/lagoon-<VERSION>.graphql` exists, is committed, and is unmodified
      from the `gql-cli` output.
- [ ] The SDL contains `type Query` and `type Mutation`.
- [ ] The SDL contains at least 100 `"""` description delimiters.
- [ ] The SDL parses cleanly (see verification).
- [ ] `schema/VERSION` records version, endpoint, date, fetcher, tool.
- [ ] `schema/README.md` documents the refresh procedure, including the warning
      about tokens on make command lines.
- [ ] `make fetch-schema` fails with a clear message when any of the three
      required variables is missing, and when the target file already exists.
- [ ] `schema/` is present in the built collection artifact.
- [ ] `git diff --stat api/` is empty.

## Verification commands

```sh
grep -c '"""' schema/lagoon-*.graphql
grep -c '^type Query' schema/lagoon-*.graphql
grep -c '^type Mutation' schema/lagoon-*.graphql

# Parse check (graphql-core is a dev-only dep; install ad hoc, do not add to
# tests/unit/requirements.txt).
pip install graphql-core
python -c "
from graphql import build_ast_schema, parse
import glob, sys
p = glob.glob('schema/lagoon-*.graphql')
assert len(p) == 1, f'expected exactly one vendored SDL, found {p}'
s = build_ast_schema(parse(open(p[0]).read()))
assert s.query_type is not None, 'no Query type'
assert s.mutation_type is not None, 'no Mutation type'
print('OK', p[0], len(s.type_map), 'types')
"

make fetch-schema                       # must fail: missing vars
ansible-galaxy collection build --force --output-path /tmp/v3build
tar -tzf /tmp/v3build/salsadigitalauorg-lagoon-3.0.0.tar.gz | grep '^schema/'
```

## Review focus

- Does `schema/VERSION` match the filename and the actual `lagoonVersion` response?
- Descriptions present? This is the one thing that is expensive to discover late.
- Exactly **one** `schema/lagoon-*.graphql` file. Multiple vendored SDLs would make
  "which schema generated this module" ambiguous.
- SDL committed verbatim — no reformatting in the diff.

## Commit

```
feat(v3): vendor Lagoon GraphQL SDL for <VERSION>

Pins the schema the Phase 3 generator will read, records its provenance
in schema/VERSION, and adds a make fetch-schema target that refuses to
run without an explicit version or to overwrite an existing SDL.

Resolves open item 12.1 in docs/plans/v3-refactor.md
Refs docs/plans/v3-refactor.md Phase 1
```

---

# P1-S3 — `module_utils/errors.py` — exception hierarchy

## Goal

A single, dependency-free exception hierarchy that every v3 runtime component
raises, so `client.py`, `auth.py`, `lookup.py`, and `resource.py` never need to
know whether they are running inside a module, an action plugin, or the inventory
plugin.

## Context

v1 has two half-solutions and they are the reason error handling is inconsistent:

- `api/plugins/module_utils/gqlError.py` (12 LOC) defines `ResourceError(errors, message)`,
  used only by the hand-written `gqlResourceBase` classes.
- `api/plugins/module_utils/api_client.py::make_api_call` raises `AnsibleError`
  directly for every failure mode — HTTP, URL, SSL, connection, and GraphQL errors
  all collapse into one untyped string. `AnsibleError` is a **controller-side**
  exception; raising it from module code is wrong and produces poor failure output.

v3 must separate these concerns:

- `module_utils` raises **its own** exceptions. It never imports `ansible.errors`.
- The **module** catches them and calls `module.fail_json()`.
- The **action plugin / inventory plugin** catches them and raises `AnsibleError`.

This story is small but it is load-bearing: P1-S4 depends on the taxonomy, and
getting it wrong means reworking every `except` in phases 2–6.

## Files to create

```
plugins/module_utils/errors.py
tests/unit/plugins/module_utils/test_errors.py
```

## Implementation notes

### Required taxonomy

```python
class LagoonError(Exception):
    """Base for all Lagoon collection errors."""

class LagoonConfigError(LagoonError):
    """Caller supplied invalid/incomplete configuration. Never retryable."""

class LagoonAuthError(LagoonError):
    """Authentication or authorisation failed (401/403, token expired,
    SSH grant failed). Never retryable without new credentials."""

class LagoonTransportError(LagoonError):
    """Network, TLS, or 5xx failure. Retryable."""

class LagoonAPIError(LagoonError):
    """The API returned HTTP 200 with a GraphQL errors[] payload."""

class LagoonNotFoundError(LagoonError):
    """A read/lookup query resolved to no result."""

class LagoonAmbiguousResultError(LagoonError):
    """A lookup resolved to more than one result."""
```

### `LagoonAPIError` requirements

GraphQL returns `errors` as a list of objects with `message`, and optionally
`path`, `locations`, `extensions`. Capture the structure — do not stringify early.

```python
class LagoonAPIError(LagoonError):
    def __init__(self, errors, message=None, query=None, variables=None):
        self.errors = errors or []
        self.query = query
        self.variables = variables
        super().__init__(message or self._summarise())

    @property
    def messages(self):
        """List of human-readable messages from the GraphQL errors payload."""

    def _summarise(self):
        """'Lagoon API error: <msg>' / 'Lagoon API errors (N): <msg>; <msg>'"""
```

- `messages` must tolerate malformed entries: a plain string in the list, a dict
  with no `message` key, `None`. Never raise from the error class itself.
- **`variables` must never be included in `__str__`.** Variables carry user input
  and, for auth-adjacent mutations, potentially secrets. Keep them as an attribute
  for `-vvv` debugging at the caller's discretion, but keep them out of the
  message that lands in `fail_json` output and the audit trail
  (ISM-1402 — credential protection; parent plan §7.2).
- The same applies to `query`: safe to include (it is a static string with
  `$variables`), and useful for debugging. Include it in `__str__` only when short,
  or expose it as an attribute and let the caller decide. Prefer the attribute.

### `LagoonNotFoundError` / `LagoonAmbiguousResultError` requirements

Parent plan §7.3 requires lookup failures to name the attempted query and value.
Bake that into the signature so callers cannot forget:

```python
class LagoonNotFoundError(LagoonError):
    def __init__(self, resource, query=None, arg=None, value=None, message=None): ...
```

Message should read like:
`Lagoon project not found: query 'projectByName' with name='my-project' returned no result`

### Hard constraints

- **No imports from `ansible.*`.** Not `ansible.errors`, not `ansible.module_utils.*`.
  This file must be importable in a bare pytest process with only stdlib available.
  Add a unit test that asserts this.
- No `graphql-core`, no `gql`, no `requests`.
- Every class is picklable (relevant because `ansible-test units --forked` runs
  tests in subprocesses). Give every `__init__` a signature where all args after
  the first are keyword-defaulted, and set attributes before `super().__init__()`.

### Do not

- Do not port `gqlError.ResourceError`. It is v1-only and its `(errors, message)`
  positional signature is the wrong shape.
- Do not add a `to_ansible_error()` helper here. That coupling belongs in the
  action plugin (Phase 2), not in `module_utils`.

## Acceptance criteria

- [ ] All seven classes exist with the inheritance above; `LagoonError` is the
      single root.
- [ ] `errors.py` imports nothing outside the Python standard library.
- [ ] `LagoonAPIError.messages` handles a well-formed payload, a list of bare
      strings, dicts missing `message`, `None`, and `[]` — without raising.
- [ ] `str(LagoonAPIError(...))` does **not** contain any value passed in
      `variables`.
- [ ] `LagoonNotFoundError` and `LagoonAmbiguousResultError` messages include the
      query name and the attempted value.
- [ ] Every exception round-trips through `pickle.dumps`/`loads`.
- [ ] Unit tests cover all of the above.

## Verification commands

```sh
docker compose run --rm test-v3 ansible-test units -v --requirements \
  tests/unit/plugins/module_utils/test_errors.py

# Prove the no-ansible-imports constraint holds
python - <<'PY'
import ast, sys
tree = ast.parse(open('plugins/module_utils/errors.py').read())
bad = []
for n in ast.walk(tree):
    if isinstance(n, ast.Import):
        bad += [a.name for a in n.names if a.name.split('.')[0] in ('ansible','gql','graphql','requests')]
    if isinstance(n, ast.ImportFrom) and n.module:
        if n.module.split('.')[0] in ('ansible','gql','graphql','requests'):
            bad.append(n.module)
assert not bad, f"forbidden imports: {bad}"
print("OK: stdlib only")
PY
```

## Review focus

- Is the taxonomy right for what phases 2–6 need? In particular: is
  retryable-vs-not cleanly separable (`LagoonTransportError` alone), because
  P1-S4's retry logic will branch on exactly that.
- No secret leakage in `__str__`. Check `variables` specifically.
- No `ansible.errors` import. This is the single most likely thing to slip in.

## Commit

```
feat(v3): add LagoonError exception hierarchy

Replaces v1's untyped AnsibleError-everywhere approach in api_client.py
with a stdlib-only taxonomy that module_utils can raise regardless of
execution context. Retryable failures are separable from terminal ones,
and GraphQL error payloads are captured structurally rather than
stringified. Query variables are held as an attribute but kept out of
error messages so they cannot reach fail_json output or the audit trail.

Refs docs/plans/v3-refactor.md Phase 1, 7.1
```

---

# P1-S4 — `module_utils/client.py` — `LagoonClient`

## Goal

The one HTTP/GraphQL client for the whole collection: `ansible-core` only, flat
single-level queries, typed errors, retry on transport failures only.

## Context

This replaces three v1 components:

| v1 | LOC | Why it goes |
| -- | --- | ----------- |
| `module_utils/api_client.py` | 693 | Hand-written query strings embedded per method; `open_url` with `validate_certs=False` **default**; all errors → `AnsibleError`; string interpolation into queries. |
| `module_utils/gql.py` | 541 | Depends on `gql` + `graphql-core` at runtime and fetches the schema over the wire on every run (`fetch_schema_from_transport=True`) — a full introspection round-trip per task. |
| `module_utils/display.py` | 43 | `try: from ansible.utils.display import Display` shim, needed only because `gql.py` wanted controller-side logging from module context. |

Two v1 defects to explicitly not carry forward:

> **`api_client.py` line ~646:** `validate_certs=self.options.get('validate_certs', False)`
> — TLS verification is **off by default**. v3 must default to `True`
> (ISM-1552 — TLS for data in transit). Make it an explicit opt-out parameter with
> a documented warning.

> **`api_client.py` `__patch_dict_to_string` / `deploy_target_config_delete_mutation`:**
> user values are interpolated directly into query text with `%s` / `%d`. This is
> GraphQL injection. v3 must pass **all** user data via the `variables` map, never
> via string formatting into the document.

## Files to create

```
plugins/module_utils/client.py
tests/unit/plugins/module_utils/test_client.py
```

## Design

### Transport: `fetch_url` vs `open_url`

Parent plan D3/§7.1 says `fetch_url` from `ansible.module_utils.urls`. `fetch_url`
requires an `AnsibleModule` instance — but `LagoonClient` is also needed by the
inventory plugin (Phase 7) and the action shim (Phase 2), neither of which has one.

**Implement a dual path:**

```python
class LagoonClient:
    def __init__(self, endpoint, token, module=None, validate_certs=True,
                 timeout=30, retries=3, headers=None): ...
```

- `module` provided → `fetch_url(module, ...)`. Preferred inside modules: picks up
  `no_log` handling, proxy env, and the module's `validate_certs` conventions.
- `module` omitted → `open_url(...)`. Used by inventory/action-plugin contexts.

Both paths must funnel into a single private `_request()` so response handling,
error translation, and retry exist **once**. Raise `LagoonConfigError` if
`endpoint` or `token` is missing/empty.

> This is a deliberate, documented deviation from the letter of §7.1. Flag it in
> the commit body and let the reviewer confirm. The alternative — `open_url` only —
> is simpler but loses `fetch_url`'s module integration; the alternative of
> `fetch_url` only makes the client unusable in Phase 7.

### Public surface

```python
def execute(self, query: str, variables: dict = None) -> dict:
    """POST the document. Returns the `data` object. Raises on any failure."""

@staticmethod
def build_query(operation: str, *, fields: list, args: dict = None,
                operation_type: str = 'query', operation_name: str = None) -> str:
    """Build a FLAT single-level GraphQL document.

    args maps GraphQL variable name -> GraphQL type, e.g. {'name': 'String!'}.
    fields is a list of scalar field names. No nesting is permitted.
    """
```

`build_query('projectByName', fields=['id','name','gitUrl'], args={'name':'String!'})`
must produce, on one line:

```
query projectByName($name: String!) { projectByName(name: $name) { id name gitUrl } }
```

Requirements on `build_query`:

- Reject any entry in `fields` containing `{`, `}`, whitespace, or `(` →
  `LagoonConfigError`. This is the first line of defence for the REST-semantics
  rule; P1-S5 is the second.
- Reject `fields` being empty **only** when the operation returns a selectable
  type. The client cannot know the SDL, so accept `fields=[]` and emit no
  selection set — some mutations return a scalar (`deleteProject` returns `String`).
  Document this.
- Validate `operation` and every `args` key against `^[A-Za-z_][A-Za-z0-9_]*$` →
  `LagoonConfigError` otherwise. Never interpolate unvalidated identifiers.
- `operation_type` must be `query` or `mutation` — nothing else.
- Deterministic output. Same inputs → byte-identical string. Do not iterate over
  unordered sets. Phase 3 snapshot tests and the Phase 8 drift guard depend on this.

### Error translation

| Condition | Raise |
| --------- | ----- |
| missing endpoint/token, malformed args | `LagoonConfigError` |
| HTTP 401, 403 | `LagoonAuthError` |
| HTTP 400, 404, 409, 422 (other 4xx) | `LagoonAPIError` — terminal, no retry |
| HTTP 5xx | `LagoonTransportError` after retries exhausted |
| `URLError`, `ConnectionError`, socket timeout | `LagoonTransportError` after retries |
| `SSLValidationError` | `LagoonTransportError`, **no retry** — retrying a cert failure is pointless |
| HTTP 200, body not JSON | `LagoonAPIError` with a truncated body excerpt |
| HTTP 200, body has `errors` | `LagoonAPIError(errors=..., query=..., variables=...)` |
| HTTP 200, body has neither `data` nor `errors` | `LagoonAPIError` |

Note the important case: **HTTP 200 with `errors`**. GraphQL signals application
errors in a 200 response. v1's `make_api_call` handled this, but flattened it to a
string. Preserve the payload via `LagoonAPIError.errors`.

Partial success (`data` **and** `errors` both present) — raise. A module cannot
safely act on partial data, and silently returning it is how v1's inventory
produced hosts with missing fields.

### Retry

- Retry **only** `LagoonTransportError`-class conditions: 5xx, `URLError`,
  connection errors, timeouts. Never 4xx, never `LagoonAPIError`, never
  `SSLValidationError`.
- Exponential backoff with a small base (e.g. `0.5 * 2**attempt`), capped.
- `retries=0` must mean "one attempt, no retry".
- Backoff sleeps must be injectable/patchable so tests do not actually sleep.
  A `_sleep = staticmethod(time.sleep)` class attribute is sufficient.

### Headers and secrecy

- `Content-Type: application/json`, `Authorization: Bearer <token>`,
  and a `User-Agent` identifying the collection and version.
- Caller-supplied `headers` merge, but **must not** be able to override
  `Authorization`.
- The token must never appear in any exception message, `repr()`, or debug string.
  `__repr__` must redact it. Add a test that greps `repr(client)` and every raised
  exception's `str()` for the token value.

### Hard constraints

- Imports permitted: stdlib, `ansible.module_utils.urls`,
  `ansible.module_utils.six.moves.urllib.error`, `ansible.module_utils._text`,
  and `.errors`.
- **Forbidden:** `gql`, `graphql`, `requests`, `requests_toolbelt`, `urllib3`,
  `ansible.errors`, `ansible.utils.display`. Assert this with an AST test, same
  pattern as P1-S3.
- No schema introspection. Ever. The vendored SDL is the schema source
  (parent plan D2).
- No module-level mutable state, no caching. Token caching is Phase 2
  (`auth.py`); lookup caching is Phase 4 (`lookup.py`). Keep this class stateless
  beyond its constructor args.

## Testing requirements

`tests/unit/plugins/module_utils/test_client.py`. Mock at the
`fetch_url` / `open_url` boundary — do not hit a network, and do not depend on the
`graphql-mock` container (that is Phase 5 integration).

Cover:

1. `build_query` — exact expected string for query and mutation, with and without
   args, with `fields=[]`, with an explicit `operation_name`.
2. `build_query` rejects: field with `{`, field with a space, field with `(`,
   bad operation name, bad arg name, bad `operation_type`.
3. `build_query` determinism — call twice, assert identical.
4. `execute` happy path returns `data`.
5. Each row of the error-translation table above, one test each.
6. Retry: 5xx twice then 200 → succeeds, exactly 3 attempts. 5xx always →
   `LagoonTransportError`, exactly `retries+1` attempts. 4xx → exactly 1 attempt.
   `SSLValidationError` → exactly 1 attempt.
7. `retries=0` → exactly 1 attempt.
8. Token redaction: token string absent from `repr(client)` and from `str(exc)`
   for every exception type the client raises.
9. Caller headers cannot override `Authorization`.
10. `validate_certs` defaults to `True` and is passed through on both transports.
11. Both transports: `module` given → `fetch_url` called; `module` omitted →
    `open_url` called.
12. Variables are passed in the JSON body's `variables` key and never appear in
    the `query` string.

## Acceptance criteria

- [ ] All tests above pass.
- [ ] `validate_certs` defaults to `True`.
- [ ] AST check confirms no forbidden imports.
- [ ] No user data reaches the query document — only `variables`.
- [ ] `build_query` output is single-level and deterministic.
- [ ] Token never appears in `repr` or any error string.
- [ ] `client.py` raises only `errors.py` types — no `AnsibleError`, no bare
      `Exception`.

## Verification commands

```sh
docker compose run --rm test-v3 ansible-test units -v --requirements \
  tests/unit/plugins/module_utils/test_client.py

# Forbidden-import check
python - <<'PY'
import ast
FORBIDDEN = {'gql','graphql','requests','requests_toolbelt','urllib3'}
tree = ast.parse(open('plugins/module_utils/client.py').read())
bad=[]
for n in ast.walk(tree):
    if isinstance(n, ast.Import):
        bad += [a.name for a in n.names if a.name.split('.')[0] in FORBIDDEN]
    if isinstance(n, ast.ImportFrom) and n.module:
        root = n.module.split('.')[0]
        if root in FORBIDDEN: bad.append(n.module)
        if n.module in ('ansible.errors','ansible.utils.display'): bad.append(n.module)
assert not bad, f"forbidden imports: {bad}"
print("OK")
PY

grep -n "validate_certs" plugins/module_utils/client.py    # confirm True default
```

## Review focus

- **TLS default.** v1 defaulted to `validate_certs=False`. Confirm v3 is `True`.
- **Injection.** Search the file for `%` formatting and f-strings that touch user
  values inside a query document. There must be none.
- Is the retry predicate genuinely limited to transport failures? A retry on 4xx
  or on a GraphQL `errors[]` response would make non-idempotent mutations fire
  twice — that is a correctness bug, not just noise.
- Single `_request()` funnel, or duplicated logic across the two transports?
- Token redaction actually tested, not just asserted in a comment.
- Is the `fetch_url`/`open_url` dual path acceptable, or should it be `open_url`
  only? Confirm the deviation from §7.1.

## Commit

```
feat(v3): add LagoonClient with flat-query GraphQL transport

Replaces v1's api_client.py and gql.py with a single ansible-core-only
client. Drops the runtime gql/requests/urllib3 dependencies and the
per-task schema introspection round-trip.

Fixes two defects carried by v1: validate_certs now defaults to True
(v1 defaulted to False), and all user data is passed via the GraphQL
variables map rather than interpolated into the query document.

Retry is restricted to transport failures (5xx, connection, timeout) so
non-idempotent mutations cannot be replayed on an application error.

Deviation from plan 7.1: the client accepts an optional AnsibleModule
and uses fetch_url when present, open_url otherwise, so the same client
serves modules, the action shim (Phase 2) and the inventory plugin
(Phase 7).

Refs docs/plans/v3-refactor.md Phase 1, 7.1
```

---

# P1-S5 — Flat-query nesting-depth guardrail

## Goal

A mechanical, reusable check that fails the test suite if **any** GraphQL document
anywhere in the collection contains a nested selection set. This is what stops the
REST-semantics rule (parent plan D3 / §7.1) from eroding once Phase 3 starts
generating dozens of modules.

## Context

The parent plan §7.1 specifies "a unit test asserts no generated query string
contains a nested selection set (regex for `{` nesting depth > 2)". A regex cannot
do this — brace depth is not a regular language, and the check must ignore braces
inside string literals. Implement a small scanner instead.

This is the highest-leverage story in Phase 1 relative to its size. Without it,
nested selections creep back in via the allowlist in Phase 5 and nobody notices
until the request count explodes.

Why v1 needs this: `api_client.py::project()` selects
`projectByName { ... openshift { id name } environments { name openshift { id name } } deployTargetConfigs { ... deployTarget { name id } } }` — four levels
deep. That shape is exactly what v3 forbids.

## Files to create

```
tests/unit/plugins/module_utils/query_depth.py     # the checker (test-tree helper)
tests/unit/plugins/module_utils/test_query_depth.py
```

## Design

### Depth definition — be precise

For `query ($name: String!) { projectByName(name: $name) { id name } }`:

- depth 1 = the operation's selection set (`{ projectByName ... }`)
- depth 2 = a field's selection set (`{ id name }`)

**Maximum permitted depth is 2.** Any brace opening at depth 3 is a violation.
A document with no selection set at all (a mutation returning a scalar) has max
depth 1 and is valid.

### `max_selection_depth(document: str) -> int`

A character scanner, not a regex:

- Track depth on `{` / `}`.
- **Ignore braces inside string literals.** Handle `"..."` and GraphQL block
  strings `"""..."""`, including `\"` escapes. Query documents built by
  `LagoonClient.build_query` use variables and so should contain no literals at
  all — but the checker must be sound regardless, or it becomes a source of false
  passes.
- Ignore `#` comments to end of line.
- Raise `ValueError` on unbalanced braces — an unbalanced document is a bug worth
  surfacing, not something to silently score as depth 0.

### `assert_flat_query(document: str, source: str = None)`

Wraps the above; raises `AssertionError` with the offending document and the
computed depth. `source` lets the sweep name the file and symbol.

### The sweep

The point of this story is not the checker — it is the sweep that applies it to
the whole collection automatically, so Phase 3+ generated modules are covered with
no extra work.

`test_query_depth.py` must contain a test that:

1. Walks every `.py` file under `plugins/`.
2. Parses each with `ast` and collects every module-level or class-level string
   constant assigned to a name matching `(?i)(QUERY|MUTATION|_GQL|DOCUMENT)`,
   plus every string literal anywhere in the file that contains both `{` and one
   of `query ` / `mutation ` / `query(` / `mutation(`.
3. Asserts `assert_flat_query` on each.
4. **Fails if it finds zero candidates once `plugins/modules/` is non-empty.** A
   sweep that silently matches nothing is worse than no sweep. In Phase 1
   `plugins/modules/` is empty, so guard this with a count check that becomes
   meaningful automatically. Include an explanatory assertion message.

Use `ast`, not `import`. Importing `plugins/` modules pulls in `AnsibleModule` and
will not work under bare pytest.

## Testing requirements

`test_query_depth.py` must cover the checker itself, then the sweep:

**Checker — must pass (depth ≤ 2):**
- `query { me }` → 1
- `query ($name: String!) { projectByName(name: $name) { id name } }` → 2
- `mutation ($input: AddProjectInput!) { addProject(input: $input) { id name } }` → 2
- `mutation ($input: DeleteProjectInput!) { deleteProject(input: $input) }` → 1
- a document whose string literal contains braces:
  `query { search(q: "a { b }") { id } }` → 2
- a document with a `#` comment containing a brace → correct depth
- a block string `"""{ }"""` inside a document → correct depth

**Checker — must fail (depth ≥ 3):**
- `query { projectByName(name: $n) { id openshift { id name } } }` → 3
- the real four-level v1 `projectByName` document from `api_client.py::project()`
  — copy it into the test as a fixture. This proves the guardrail catches the
  actual historical pattern it exists to prevent.

**Checker — errors:**
- `query { a` → `ValueError`
- `query { a } }` → `ValueError`

**Integration with P1-S4:**
- Feed several `LagoonClient.build_query(...)` outputs through `assert_flat_query`
  and assert they pass. This ties the two stories together and means a regression
  in `build_query` fails here too.

**Sweep:**
- Runs clean against the current `plugins/` tree.
- Given a temporary fixture file containing a nested document, the sweep logic
  detects it. (Test the collection function against a temp dir rather than
  polluting `plugins/`.)

## Acceptance criteria

- [ ] `max_selection_depth` is a scanner, not a regex, and is string-literal- and
      comment-aware.
- [ ] All checker cases above pass, including the v1 four-level fixture failing.
- [ ] Unbalanced braces raise `ValueError`.
- [ ] The sweep walks `plugins/` via `ast` with no imports of collection code.
- [ ] The sweep's zero-candidate guard is in place with a clear message, so it
      cannot pass vacuously once modules exist.
- [ ] `assert_flat_query` failure output names the source and includes the document.
- [ ] `LagoonClient.build_query` outputs pass the guardrail.
- [ ] The helper lives under `tests/`, not `plugins/` — it is a test-time
      guardrail, not shipped runtime code.

## Verification commands

```sh
docker compose run --rm test-v3 ansible-test units -v --requirements \
  tests/unit/plugins/module_utils/test_query_depth.py

docker compose run --rm test-v3 ansible-test units -v --requirements

# Confirm the guardrail is not shipped
ansible-galaxy collection build --force --output-path /tmp/v3build
tar -tzf /tmp/v3build/salsadigitalauorg-lagoon-3.0.0.tar.gz | grep query_depth && \
  echo "FAIL: test helper shipped" || echo "OK"
```

## Review focus

- Does the scanner actually handle string literals and block strings, or does it
  only claim to? Check the tests exercise it.
- Is the max depth 2 (not 1, not 3)? Off-by-one here either blocks all valid
  queries or permits one level of nesting.
- **The vacuous-pass guard.** This is the thing most likely to be skipped and most
  costly later. Confirm the sweep cannot silently match zero documents once
  `plugins/modules/` is populated.
- Is the v1 four-level `projectByName` document present as a negative fixture?
  Without a real-world case the test only proves the checker against toy inputs.

## Commit

```
test(v3): add flat-query nesting-depth guardrail

Enforces the REST-semantics rule mechanically: a scanner computes GraphQL
selection-set depth (string-literal and comment aware) and a sweep applies
it to every query document under plugins/ via AST, so modules generated in
Phase 3 onward are covered automatically.

Implements plan 7.1 as a scanner rather than the suggested regex — brace
depth is not regular and the check must ignore braces inside literals.
The negative fixture is the real four-level projectByName document from
v1's api_client.py, the pattern this guardrail exists to prevent.

Refs docs/plans/v3-refactor.md Phase 1, 7.1
```

---

## Phase 1 exit criteria

Phase 1 is complete when all five commits are reviewed and merged, and:

- [ ] `ansible-galaxy collection build` produces a clean `salsadigitalauorg-lagoon-3.0.0`
      artifact containing `plugins/`, `meta/`, `schema/`, `README.md` and nothing
      from `api/`, `docs/`, `codegen/`, `.docker/`, `.github/`.
- [ ] `docker compose run --rm test-v3 ansible-test units -v --requirements`
      is green.
- [ ] Zero runtime dependencies beyond `ansible-core`. `grep -rn "import gql\|import requests\|from graphql" plugins/` returns nothing.
- [ ] `schema/VERSION` records a real, verified Lagoon version.
- [ ] The v1 collection is untouched and still builds from `api/`.
- [ ] `antsibull-changelog lint` and `antsibull-docs lint-collection-docs --plugin-docs .`
      both pass.

## Carried forward to later phases

Recorded here so they are not rediscovered:

| Item | Phase | Note |
| ---- | ----- | ---- |
| `ansible-test sanity` will scan `api/` while it remains inside the v3 collection root | 8 | Either `tests/sanity/ignore-*.txt` entries, or sequence the `api/` deletion before sanity lands. Prefer the latter. |
| `.docker/Dockerfile.graphql-mock` still copies `api/tests/common/schema.graphql` | 5 | Repoint at the vendored `schema/lagoon-<version>.graphql` when integration targets land. |
| `.docker/Dockerfile.docs` and the `docs`/`lint-docs` compose services still reference `lagoon/api` | 8 | Repoint with the docs workflow update. |
| Delete `api/`, the v1 compose services, and `api/tests/common/schema.graphql` | post-8 | Final cleanup story (P1-D2). |
| Galaxy namespace ownership for `salsadigitalauorg` | before 3.0.0 tag | Parent plan §12.2 — unblocked for Phase 1 but must be confirmed before publish. |
| Whether `*_info` modules need the action shim | 3 | Parent plan §12.3. |
