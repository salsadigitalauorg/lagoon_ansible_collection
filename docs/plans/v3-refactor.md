# Lagoon Ansible Collection v3 — Architecture & Implementation Plan

**Date:** 2026-07-27
**Last amended:** 2026-09-03 — Phase 2 confirmed complete (all nine commits
merged, exit criteria verified). §6/§6.1/§9 amended against the real vendored
SDL for Phase 3: the create/update mutation asymmetry, the gate resource
selection, the description-fallback chain, and the Phase 3/4 boundary move
(§9 Phase 3 now owns `resource.py`/`lookup.py`, old Phase 5 retired into it).
§11 gains three risk rows. See P3-D1..D9 in
`docs/plans/v3-phase3-stories.md`.
**Status:** Approved for implementation — Phases 1–2 complete; Phase 3 broken into stories
**Target:** `salsadigitalauorg.lagoon` v3.0.0 (replaces `lagoon.api` v1.3.0)
**Author:** plan agent (QuantCode Gov)

---

## 1. Objective

Rewrite the collection so that:

1. All API surface is exposed as **real Ansible modules**, not action plugins.
2. Modules are **generated at build time** from a vendored GraphQL SDL and committed to git.
3. Queries are **strictly single-level** — the API is treated as REST. No nested field selection.
4. Auth uses **short-lived SSH-grant tokens** validated/refreshed before each request, with a long-lived token escape hatch.
5. The inventory plugin is reduced to **running flat queries** and feeding standard inventory constructs.
6. Name→id resolution (project name → id, namespace → environment id) happens automatically via **declared intermediate lookups**.
7. Docs are published for every module.

---

## 2. Current state (baseline)

| Aspect           | Today                                                                                                                                                                                                            |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Collection       | `lagoon.api` v1.3.0                                                                                                                                                                                              |
| Action plugins   | 27 in `api/plugins/action/`                                                                                                                                                                                      |
| Modules          | 27 files in `api/plugins/modules/` that are **documentation stubs only** — no `main()`, no execution                                                                                                             |
| `module_utils`   | ~3,076 LOC, incl. hand-written resource classes (`gqlProject`, `gqlEnvironment`, `gqlVariable`, `gqlMetadata`, `gqlTaskDefinition`, `gqlDeployTargetConfig`, `gqlGroup`)                                         |
| Query building   | `gql` DSL (`DSLQuery`/`DSLMutation`), deeply nested selections                                                                                                                                                   |
| Existing codegen | `generate_argspec_from_mutation()` in `module_utils/argspec.py` + `MutationConfig`/`MutationActionConfig` + `ProxyLookup` — **runtime** introspection, used by only 2 of 27 actions (`group`, `task_definition`) |
| Inventory        | ~700 LOC, nested batched queries with `api_batch_project_environments_size` / `api_batch_project_groups_size` tuning knobs                                                                                       |
| Auth             | `fetch_token` action + `token` role → `lagoon_api_token` task var                                                                                                                                                |
| Schema           | `api/tests/common/schema.graphql`, 4,923 lines (`Query` ~178 lines, `Mutation` ~422 lines), includes SDL descriptions                                                                                            |
| Deps             | `gql<4,>=3.5.3`, `requests`, `requests-toolbelt==0.10.1`, `urllib3==1.26.19` (pinned to work around test breakage)                                                                                               |
| Docs             | `antsibull-docs` → QuantCDN on push to `master`                                                                                                                                                                  |

### 2.1 What carries forward

The v1 codebase already solved two of the hardest problems. **Do not rewrite these from scratch — port them.**

- `module_utils/argspec.py::generate_argspec_from_mutation()` — maps GraphQL input types to Ansible argspec, handling `GraphQLNonNull`, `GraphQLEnumType` (→ `choices`), `GraphQLInputObjectType` (→ `type: dict` + `options`), list types. This becomes the core of the build-time generator.
- `MutationConfig` / `MutationActionConfig` / `ProxyLookup` — already model "mutation + update mutation + extra argspec + name→id lookup". These become the **declarative allowlist schema**.

The shift is *when* they run: runtime → build time.

---

## 3. Confirmed decisions

| #   | Decision         | Choice                                                                                                                            |
| --- | ---------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| D1  | Codegen timing   | Build-time, committed to git                                                                                                      |
| D2  | Schema source    | Vendored SDL, committed, pinned per Lagoon version                                                                                |
| D3  | HTTP client      | Drop `gql` from runtime; `graphql-core` is a **generator-only dev dependency**. `fetch_url` when an `AnsibleModule` is available, `open_url` otherwise — see §7.1 |
| D4  | Generation scope | Curated allowlist, expanded incrementally                                                                                         |
| D5  | Module naming    | Resource-oriented, `state: present\|absent`; read-only → `*_info`                                                                 |
| D6  | Auth             | Controller-side cache + validation via thin action-plugin sidecar                                                                 |
| D7  | Inventory        | User-supplied flat queries + `compose`/`keyed_groups`/`groups`                                                                    |
| D8  | Back-compat      | Clean break. New major, migration guide, no shims                                                                                 |
| D9  | Lookups          | Explicit per-resource declaration in the allowlist                                                                                |
| D10 | Lookup caching   | Controller-side, cached alongside the token                                                                                       |
| D11 | Idempotency      | Generated read-before-write diff; real `check_mode` + `--diff`                                                                    |
| D12 | Collection name  | `salsadigitalauorg.lagoon` — matches the GitHub org, so Galaxy namespace ownership (§12.2) is straightforward to verify            |
| D13 | Docs             | Keep `antsibull-docs` → QuantCDN, **plus a CI drift guard**                                                                       |
| D14 | Long-lived token | Module param + `LAGOON_API_TOKEN` env fallback, `no_log: true`                                                                    |
| D15 | Seed scope       | Core set: project, environment, variables, deploy, task, group, user, notification                                                |
| D16 | Bespoke actions  | Hand-written modules alongside generated, sharing `module_utils`                                                                  |
| D17 | Repo layout      | Collection root **is** the repo root — `galaxy.yml`, `plugins/`, `schema/`, `codegen/` all top-level. Repo moves to `salsadigitalauorg/ansible-lagoon` |
| D18 | v1 coexistence   | `api/` retained untouched through phases 1–8, excluded via `build_ignore`; deleted in a post-Phase 8 cleanup story                 |
| D19 | Support matrix    | `requires_ansible: '>=2.16'`; tested Python 3.11 / 3.12 / 3.13. v1's 3.9 / 3.10 floor dropped (both EOL)                          |
| D20 | Phase 1 CI        | No CI in Phase 1 — verification is local via a containerised `test-v3` compose service. All CI wiring lands in Phase 8            |

---

## 4. Architectural tension to resolve up front

**D6 (action-plugin sidecar) appears to contradict the "refactor all actions into modules" goal.** It does not, but the boundary must be strict and enforced in review:

- The **module** contains 100% of the business logic — argspec, read-before-write, mutation, diff, idempotency, check mode. A module invoked with an explicit `lagoon_api_token` is fully functional standalone.
- The **action-plugin sidecar** is generated boilerplate that does *only* two things on the controller: (a) resolve/validate/refresh the API token, (b) resolve declared name→id lookups from cache. It then injects those as module args and delegates via `self._execute_module()`.
- The sidecar contains **no resource-specific logic**. A single shared `LagoonActionShim` base class does the work; per-module sidecars are one-line subclasses (or a single sidecar registered for all modules via `action_groups`).

Rationale: modules are per-task processes with no shared state. Without a controller-side cache, a 50-task play triggers 50 SSH `grant` round-trips plus 50 redundant name→id lookups. The sidecar keeps modules pure and independently testable while giving the controller a place to cache.

**Correction (Phase 2 story breakdown, see `docs/plans/v3-phase2-stories.md` P2-D2):** the sidecar does **not** buy "one grant per play". Ansible forks a `WorkerProcess` per `(host, task)` pair, and action plugins execute only in the child, so a module-level/process-scoped cache is bounded by one *task*, not one play. It does cover every iteration of a `loop:` on that task — which is where Lagoon's N+1 pattern (e.g. looping over many projects) actually bites hardest in practice. Cross-task reuse within a play requires either the opt-in file-backed cache (§7.2) or an explicit `lagoon_api_token` set once via `set_fact`, per the documented fallback below.

Per-module sidecars are one-line subclasses of a single shared `LagoonActionShim` base class, one file per module under `plugins/action/`. **`action_groups` does not affect action-plugin dispatch** — Ansible dispatches to an action plugin only when a same-named file exists under `plugins/action/`; `action_groups` only groups modules for `module_defaults` sharing. The earlier suggestion that a single sidecar could be "registered for all modules via `action_groups`" was incorrect and is withdrawn.

**Fallback if the sidecar proves problematic:** modules already accept a token directly, so the v1 `token` role pattern remains viable as a documented alternative.

---

## 5. Target layout

```
<repo root>/                          # = ansible_collections/salsadigitalauorg/lagoon (D17)
├── galaxy.yml                        # namespace: salsadigitalauorg, name: lagoon, version: 3.0.0
├── meta/runtime.yml                  # requires_ansible, action_groups
├── README.md
├── CHANGELOG.rst                     # antsibull-changelog
├── changelogs/config.yaml
├── docs/
│   ├── adr/0001-graphql-codegen-rest-semantics.md
│   └── migration-v1-to-v3.md
├── schema/
│   ├── lagoon-<version>.graphql        # vendored SDL (pinned) — see §12.1
│   └── VERSION                        # Lagoon version this SDL came from
├── codegen/                          # NOT shipped in the built artifact
│   ├── allowlist.yml                 # ← the single source of truth
│   ├── generate.py                   # entrypoint
│   ├── argspec.py                    # ported from module_utils/argspec.py
│   ├── docgen.py                     # DOCUMENTATION/EXAMPLES/RETURN emission
│   ├── templates/
│   │   ├── module.py.j2
│   │   ├── info_module.py.j2
│   │   └── action_shim.py.j2
│   └── requirements.txt              # graphql-core, jinja2, PyYAML
├── plugins/
│   ├── module_utils/
│   │   ├── client.py                 # LagoonClient — fetch_url, flat queries only
│   │   ├── auth.py                   # token validation, SSH grant, cache
│   │   ├── lookup.py                 # name→id resolution + cache
│   │   ├── resource.py               # LagoonResourceModule base (read/diff/mutate)
│   │   └── errors.py
│   ├── action/
│   │   └── __init__.py               # LagoonActionShim (shared, generated subclasses)
│   ├── modules/
│   │   ├── project.py                # GENERATED
│   │   ├── project_info.py           # GENERATED
│   │   ├── environment.py            # GENERATED
│   │   ├── environment_info.py       # GENERATED
│   │   ├── env_variable.py           # GENERATED
│   │   ├── deployment.py             # GENERATED
│   │   ├── task.py                   # GENERATED
│   │   ├── group.py                  # GENERATED
│   │   ├── user.py                   # GENERATED
│   │   ├── notification.py           # GENERATED
│   │   ├── whoami_info.py            # HAND-WRITTEN
│   │   ├── deploy_bulk.py            # HAND-WRITTEN
│   │   ├── lagoon_log.py             # HAND-WRITTEN
│   │   └── cmdb_diff.py              # HAND-WRITTEN
│   ├── inventory/
│   │   └── lagoon.py                 # simplified
│   └── doc_fragments/
│       ├── auth.py                   # shared auth options
│       └── lookup.py                 # shared lookup options
├── tests/
│   ├── unit/plugins/{modules,module_utils}/
│   ├── integration/targets/
│   └── sanity/ignore-*.txt
├── api/                              # v1 lagoon.api — build_ignore'd, deleted post-Phase 8 (D18)
└── Makefile                          # fetch-schema / generate / verify-generated / test / docs
```

**Generated-file marker.** Every generated file starts with:

```python
#!/usr/bin/python
# -*- coding: utf-8 -*-
# GENERATED FILE — DO NOT EDIT.
# Source: schema/lagoon-<version>.graphql + codegen/allowlist.yml
# Regenerate: make generate
```

---

## 6. The allowlist — single source of truth

`codegen/allowlist.yml` drives everything: argspec, lookups, idempotency, docs.

**Amended (Phase 3 story planning, against the real vendored
`schema/lagoon-2.33.0.graphql`).** The example below replaces the original —
verification against the live SDL found four things wrong with it, each
recorded as a Phase 3 decision (`docs/plans/v3-phase3-stories.md` P3-D1..D3):

- **Create/update are structurally asymmetric, not siblings.**
  `addProject(input: AddProjectInput!)` is flat (36 fields).
  `updateProject(input: UpdateProjectInput!)` is `{id: Int!, patch:
  UpdateProjectPatchInput!}` — one level of nesting the generator must
  produce internally, never expose. The field sets also diverge: 3
  create-only (`id`, `organization`, `addOrgOwner`), 6 update-only
  (`restrictions`, `autogeneratedRoutes`, `autogeneratedRoutePrefixes`,
  `autogeneratedPathRoutes`, `autogeneratedRoutesPullrequests`,
  `disableRequestVerification`). Same shape on `environment`
  (`AddEnvironmentInput` vs. `UpdateEnvironmentPatchInput`). **P3-D1:**
  present one flat argspec to the user; the generator emits a per-mutation
  wire-shaping map that wraps the wire payload for whichever mutation is
  actually being called, and rejects a create-only/update-only field used on
  the wrong path with a named-option error, not a server-side one.
- **`project.fields` included `openshift`, an object-typed field
  (`Openshift`), not a scalar.** Invalid as a leaf under this file's own
  flat-query rule. Removed from the example below.
- **`env_variable.lookups: [project_id, environment_id]` was invented, not
  real.** `EnvVariableByNameInput`/`DeleteEnvVariableByNameInput` take
  `project`/`environment` as **name strings** already — no id lookup
  exists or is needed for this resource. Corrected below.
- **The read query in the original example was wrong for `env_variable`.**
  The real read is `getEnvVariablesByProjectEnvironmentName(input:
  EnvVariableByProjectEnvironmentNameInput!): [EnvKeyValue]` — a **list**,
  filtered client-side by `name`, not `projectByName`.

```yaml
lagoon_version: "2.33.0"
schema: schema/lagoon-2.33.0.graphql

# Reusable lookup definitions, referenced by modules below.
lookups:
  project_id:
    alias: project_name              # user-facing param name
    query: projectByName             # single-level query to resolve it
    arg: name                        # query argument that takes the alias value
    returns: id                      # scalar field to extract
    description: Name of the project. Mutually exclusive with C(project_id).

  environment_id:
    alias: namespace
    query: environmentByKubernetesNamespaceName
    arg: kubernetesNamespaceName
    returns: id
    description: Kubernetes namespace of the environment. Mutually exclusive with C(environment_id).

modules:
  project:
    description: Manage Lagoon projects.
    create: addProject                # AddProjectInput -- flat
    update: updateProject              # UpdateProjectInput{id, patch: UpdateProjectPatchInput} -- generator wraps
    delete: deleteProject
    # Read-before-write source for idempotency + check_mode + --diff.
    read:
      query: projectByName
      arg: name
      from: name
    # Scalar fields returned by the read query. NO nested fields — REST semantics.
    # openshift/kubernetes (object-typed on Project) deliberately excluded.
    fields: [id, name, gitUrl, branches, pullrequests, productionEnvironment,
             autoIdle, developmentEnvironmentsLimit, storageCalc]
    # Fields excluded from the diff (server-computed / write-only).
    diff_ignore: [id]
    delete_by: name
    # create-only / update-only input fields, enforced per P3-D1 (§6.1.9).
    create_only: [organization, addOrgOwner]
    update_only: [restrictions, autogeneratedRoutes, autogeneratedRoutePrefixes,
                   autogeneratedPathRoutes, autogeneratedRoutesPullrequests,
                   disableRequestVerification]
    # SDL carries zero input-type descriptions for AddProjectInput/
    # UpdateProjectPatchInput (§6.1.5) -- explicit overrides for the ~7
    # fields the output-type fallback can't cover either.
    descriptions:
      organization: ID of the organization that owns the project.
      addOrgOwner: Whether the creating user is added as an owner of C(organization).
      sharedBaasBucket: Whether this project shares a backup bucket with other projects.
      activeSystemsDeploy: No longer in use.
      activeSystemsPromote: No longer in use.
      activeSystemsRemove: No longer in use.
      activeSystemsTask: No longer in use.
      activeSystemsMisc: No longer in use.

  environment:
    description: Manage Lagoon environments.
    create: addOrUpdateEnvironment    # AddEnvironmentInput -- flat, takes project as an id
    update: updateEnvironment          # UpdateEnvironmentInput{id, patch: UpdateEnvironmentPatchInput}
    delete: deleteEnvironment
    lookups: [project_id]              # AddEnvironmentInput.project: Int! -- genuinely needs the id lookup
    read:
      query: environmentByKubernetesNamespaceName
      arg: kubernetesNamespaceName
      from: namespace
    fields: [id, name, deployType, deployBaseRef, environmentType,
             kubernetesNamespaceName, autoIdle, route, routes]
    diff_ignore: [id]
    delete_by: name

  env_variable:
    description: Manage environment variables on a project or environment.
    create: addOrUpdateEnvVariableByName   # EnvVariableByNameInput{name, value, scope, project, environment} -- flat, no id lookup
    delete: deleteEnvVariableByName
    # No `lookups:` -- project/environment are name strings on this
    # resource's own input types, unlike project/environment above.
    read:
      # Returns [EnvKeyValue], not a single record -- filtered client-side
      # by `name` in resource.py's read step (P3-D2/D9), the resource in
      # the gate set that proves the list-read + client-side-filter path.
      query: getEnvVariablesByProjectEnvironmentName
      arg: {project: project_name, environment: namespace}
      filter_by: name
    fields: [id, name, value, scope]
    diff_ignore: [id]
    # value is a secret. no_log throughout; diff reports changed/unchanged
    # only, never the value itself (P3-D7, option (a)).
    no_log: [value]
    # scope is `EnvVariableScope` (upper-case enum) on input but plain
    # `String` on output -- diff must upper-case the read side before
    # comparing or every run reports spuriously changed (P3-D9).
    enum_case_normalise: {scope: upper}
```

### 6.1 Generator rules

1. Parse SDL with `graphql-core`. Resolve the `create`/`update`/`delete` mutation fields.
2. Build argspec from mutation input via the ported `generate_argspec_from_mutation()`,
   **fixing three defects found porting it against the real SDL** (not a
   straight copy — see `docs/plans/v3-phase3-stories.md` P3-S5):
   - `GraphQLNonNull` → `required: true`
   - `GraphQLEnumType` → `choices: [...]` (v1's list-type branch drops
     `choices` for `[EnumType]`; the port must preserve them)
   - `GraphQLInputObjectType` → `type: dict` + nested `options`
   - list types → `type: list` + `elements` from the **actual** wrapped
     type (`elements='str'` for `[String]`, `elements='dict'` only for
     `[SomeInputObjectType]`) — v1's `generate_argspec_for_input_type`
     hard-codes `elements='dict'` unconditionally, which is wrong for
     every scalar/enum list in this SDL (`[String]`, `[Restriction]`, etc.)
   - any field allowlisted under `no_log` (§6, `env_variable.no_log`) → `no_log: true` — v1's port has **no** `no_log` emission at all, so a
     naive port would log `privateKey`/`value` in plaintext
   - `snake_case` ↔ `camelCase` mapping table emitted per module
3. Reshape the flat argspec per-mutation using the module's `create_only`/
   `update_only` declarations (P3-D1): the `update` mutation's payload is
   built as `{id: <resolved id>, patch: {<update-eligible fields>}}`; a
   `create_only` field supplied with `state: present` on an existing
   resource is a named `LagoonConfigError`, never silently dropped or
   forwarded to the server.
4. For each declared lookup, add the alias param, mark `mutually_exclusive` with the id param, and add `required_one_of`.
5. Merge `doc_fragments` for auth + lookup options.
6. Emit `DOCUMENTATION` option help via the fallback chain (P3-D3), in order,
   each step trying only what the previous step left undescribed:
   1. the input type's own SDL description, if present;
   2. the same-named field's description on the mutation's output type
      (e.g. `AddProjectInput.gitUrl` ← `Project.gitUrl`) — covers 29/36
      fields on `project`, 10/14 on `environment`, but **0/6** on
      `env_variable` (`EnvKeyValue`'s fields are undescribed too);
   3. the allowlist's per-module `descriptions:` override block (§6, the
      `project.descriptions` block above is the worked example);
   4. **fail the build** — a module with any option still undescribed after
      all three steps must not generate. Docs lint must never be the first
      place this is discovered (this is what actually happened in Phase 2
      story planning, retroactively — see §11's new SDL-coverage risk row).
7. Emit `EXAMPLES` from optional per-module `examples:` in the allowlist; fall back to a generated minimal example.
8. Emit `RETURN` from the declared `fields`.
9. **Fail the build** if a declared mutation/query/field does not exist in the SDL. Schema drift must break CI, never generate silently-wrong modules.

---

## 7. Runtime design

### 7.1 `module_utils/client.py`

- `ansible-core` only. No `gql`, no `requests`, no `urllib3`, no schema introspection.
- **Dual transport (D3):** `LagoonClient(endpoint, token, module=None, ...)`. With a
  module → `fetch_url`; without → `open_url`. Both funnel through one private
  `_request()` so response handling, error translation and retry exist once.
  Required because the inventory plugin and action shim have no `AnsibleModule`.
- `validate_certs` defaults to **`True`**. v1's `api_client.py` defaults it to
  `False` — that is a defect, not a convention to carry forward (ISM-1552).
- All user data passes via the GraphQL `variables` map. **Never** interpolated into
  the document. v1's `__patch_dict_to_string()` and
  `deploy_target_config_delete_mutation()` do the latter — that is GraphQL injection.
- Queries built by a `build_query()` helper producing flat, deterministic documents:
  ```python
  "query projectByName($name: String!) { projectByName(name: $name) { id name gitUrl } }"
  ```
  Determinism matters: Phase 3 snapshot tests and the Phase 8 drift guard depend on
  byte-identical output for identical inputs.
- **Guardrail:** a character scanner computes selection-set depth (max permitted 2)
  and an AST sweep applies it to every query document under `plugins/`, so modules
  generated from Phase 3 onward are covered automatically. Implemented as a scanner,
  **not** the regex originally specified here — brace depth is not a regular
  language and the check must ignore braces inside string literals and comments.
- Errors raise the `errors.py` taxonomy; the *module* converts to `fail_json()`,
  the *action/inventory plugin* converts to `AnsibleError`. `module_utils` never
  imports `ansible.errors`.
- HTTP 200 carrying `errors[]` is an application error → `LagoonAPIError` with the
  payload preserved structurally. Partial success (`data` **and** `errors`) raises.
- Retry **only** transport failures: 5xx, `URLError`, connection, timeout. Never
  4xx, never a GraphQL `errors[]` response, never `SSLValidationError`. Retrying
  either of the first two replays non-idempotent mutations — a correctness bug.

### 7.2 `module_utils/auth.py`

Resolution order:

1. `lagoon_api_token` param → use as-is, skip all grant logic.
2. `LAGOON_API_TOKEN` env var → same.
3. Cached token → **validate** (decode JWT `exp` with a 60s skew margin; no signature verification, we're not the verifier). If valid, use it.
4. Otherwise SSH `grant` → cache → use. Grant options are `lagoon_ssh_private_key` **or** `lagoon_ssh_private_key_file` **or neither** — supplying neither authenticates via the SSH agent over the inherited `SSH_AUTH_SOCK` (**amended, P2-D9**: the original design required exactly one of the two, which made agent authentication unreachable — a regression against v1, caught in review of P2-S3 and fixed in P2-S3a). `lagoon_ssh_known_hosts_file` and `lagoon_ssh_batch_mode` (default `true`) are also part of this step's option set.

**`ssh` option precedence — added post-P2-S3 (P2-D10).** Collection-managed `-o` options (`StrictHostKeyChecking`, `ConnectTimeout`, `UserKnownHostsFile`, `BatchMode`) are emitted before any caller-supplied `lagoon_ssh_options`, and OpenSSH resolves repeated `-o` settings first-wins — so these defaults are authoritative and cannot be weakened via `lagoon_ssh_options`. This is what keeps `StrictHostKeyChecking=accept-new` (below) from being silently overridden, but it means v1's `token` role idiom of passing `StrictHostKeyChecking`/`UserKnownHostsFile` via `ssh_options` has no effect in v3 — use the dedicated options instead. Record for Phase 8's migration table.

**Cache design — amended by the Phase 2 story breakdown (`docs/plans/v3-phase2-stories.md` P2-D1).** A single file-backed cache as originally specified below writes a bearer token to disk on every resolution, which is a credential-at-rest posture (ISM-1402) the "one grant per play" rationale in §4 doesn't actually justify — see the §4 correction above. v3 instead layers two caches:

- **In-memory, always on, process-scoped.** No disk activity. Covers every iteration of a `loop:` within one task.
- **File-backed, opt-in (`lagoon_token_cache: true`), off by default.** For operators who need reuse across tasks or across separate `ansible-playbook` runs. Stored under `$XDG_CACHE_HOME/ansible-lagoon/` (or `~/.cache/ansible-lagoon/`) — never `/tmp` — directory `0700`, file `0600`, written atomically (`mkstemp` + `os.replace`). Entries age out via the token's own `exp` claim; **no `finally`-block deletion**, since a cache that the first worker deletes on exit never serves a second task or process — that would defeat the feature.

The security requirements below (`O_EXCL`/`0600`, `mkdtemp`, `finally` cleanup) still apply in full to the **SSH private key**, which is genuinely single-use per grant call. They do not transfer unmodified to the cross-process *token* cache, which has a different lifetime and a different threat model — see P2-D1/P2-S4 for the reasoning.

**Security requirements for the SSH key handling** (v1 has real problems here):

> **v1 finding — Critical.** `plugins/action/fetch_token.py` writes the SSH private key to the predictable path `/tmp/lagoon_ssh_private_key`. On a multi-user or shared CI host this is exploitable: an attacker pre-creates the path as a symlink, or reads it in the window before `chmod`. `write_ssh_key()` opens the file *then* chmods, leaving a race where the key is briefly world-readable per the process umask.

Requirements for v3 (ISM-1402 — credential protection; ISM-1590 — rotation on compromise):

- Create the key file with `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)` — atomic, mode set at creation, fails if the path exists.
- Use `tempfile.mkdtemp()` (mode `0700`) rather than a predictable `/tmp` path.
- Remove key and token files in a `finally` block.
- Token cache file mode `0600`, keyed by a hash of endpoint + SSH host + user so caches can't cross-contaminate between targets. **Note (P2-D11):** under SSH agent auth (no private key/private key file supplied), this hash has no key-material component to disambiguate on, so two distinct agent identities sharing the same endpoint/host/user collide. Accepted for the in-memory cache (the agent socket cannot change mid-process); P2-S4 must decide this deliberately for the cross-process file cache, which has a different lifetime.
- `no_log: true` on `lagoon_api_token` and `lagoon_ssh_private_key`; ensure tokens never reach `-vvv` output or the audit trail.
- Short-lived tokens are strongly preferred; document the long-lived path as exceptional and recommend vault storage + 12-month rotation.

### 7.3 `module_utils/lookup.py`

- One flat query per lookup, result cached controller-side alongside the token for the run.
- Cache key: `(query, arg, value)`.
- **Invalidation:** bypass cache when `state: absent` (the resource may have just been deleted) and after any successful create/delete affecting that resource type.
- `lagoon_lookup_cache: false` opt-out on the shared doc fragment for correctness-critical plays.
- Ambiguous or empty lookup result → `fail_json` with the attempted query and value. Never fall through to a null id.

### 7.4 `module_utils/resource.py` — `LagoonResourceModule`

Generated modules subclass this. Execution flow:

```
1. Resolve auth (injected by shim, or resolved in-module).
2. Resolve lookups → concrete ids.
3. READ current state via declared read query (flat, declared fields only).
4. Compute desired state from params (drop None; apply snake→camel mapping).
5. Diff current vs desired, excluding diff_ignore.
   - state=present, absent remotely      → create
   - state=present, present + no diff    → changed=False, exit
   - state=present, present + diff       → update
   - state=absent,  present              → delete
   - state=absent,  absent               → changed=False, exit
6. check_mode → return computed changed + diff WITHOUT mutating.
7. Execute mutation, re-read, return {changed, diff: {before, after}, <resource>}.
```

This is where the real engineering effort sits. `check_mode` and `--diff` correctness are the acceptance criteria for "idiomatic Ansible", and they are what v1 lacks entirely.

---

## 8. Inventory plugin (simplified)

Target `< 200` LOC, down from ~700.

```yaml
plugin: salsadigitalauorg.lagoon.lagoon
endpoint: https://api.lagoon.example.com/graphql

queries:
  - query: allProjects
    fields: [id, name, gitUrl, productionEnvironment, autoIdle]
    hostname: name

compose:
  ansible_host: name ~ '.example.com'
keyed_groups:
  - key: autoIdle
    prefix: autoidle
groups:
  production: productionEnvironment is defined
cache: true
```

- **Removed:** `api_batch_project_environments_size`, `api_batch_project_groups_size`, all nesting, `withGroups`/`withVariables` style expansion.
- Multiple entries in `queries` run as **separate flat calls**; users opt into the cost explicitly.
- Standard `Cacheable` / `Constructable` behaviour retained.
- Environments, if needed, are a second flat query keyed off project ids.

---

## 9. Phased implementation

Each phase should be a reviewable PR. Phases 1–3 are the risk; land them first.

### Phase 1 — Foundations — ✅ Complete

Broken into five discrete, independently reviewable stories — one commit each,
reviewed and iterated before the next begins. Full context, acceptance criteria
and verification commands: **[`docs/plans/v3-phase1-stories.md`](./v3-phase1-stories.md)**.

- [x] **P1-S1** Scaffold the collection at repo root — `galaxy.yml`, `meta/runtime.yml`,
      changelog config, `build_ignore` excluding `api/`, `test-v3` compose service, Makefile.
- [x] **P1-S2** Vendor the SDL to `schema/lagoon-2.33.0.graphql` + `VERSION`, plus
      `make fetch-schema`.
- [x] **P1-S3** `module_utils/errors.py` — stdlib-only `LagoonError` taxonomy.
- [x] **P1-S4** `module_utils/client.py` — `LagoonClient` per §7.1.
- [x] **P1-S5** Flat-query nesting-depth guardrail (scanner + AST sweep).

All five commits merged and reviewed; Phase 1 exit criteria (build artifact,
`test-v3 units`, zero non-`ansible-core` runtime deps, verified `schema/VERSION`,
docs/changelog lint) verified green.

### Phase 2 — Auth — ✅ Complete

Broken into nine discrete, independently reviewable stories — one commit each,
reviewed and iterated before the next begins. Full context, acceptance criteria
and verification commands: **[`docs/plans/v3-phase2-stories.md`](./v3-phase2-stories.md)**.

- [x] **P2-S1** `module_utils/token.py` — JWT expiry inspection (decode-only, no signature verification).
- [x] **P2-S2** `module_utils/ssh.py` — SSH grant with secure key handling (`O_EXCL` + `0600`, `mkdtemp`, `finally` cleanup) and host key verification on by default (`accept-new`), fixing the Critical v1 defects in §11.
- [x] **P2-S3** `module_utils/auth.py` — param → env → validated in-memory cache → SSH grant resolver.
- [x] **P2-S3a** SSH agent auth fix + missing argspec options (P2-D9) — found and fixed in review of P2-S3, before merge.
- [x] **P2-S3b** `BatchMode` default + `ssh` option-precedence documentation (P2-D10).
- [x] **P2-S4** `module_utils/cache.py` — opt-in cross-process file token cache (off by default; see the §7.2 amendment above).
- [x] **P2-S5** `doc_fragments/auth.py` + a drift test binding it to `auth_argument_spec()`.
- [x] **P2-S6** `LagoonActionShim` in `plugins/action/__init__.py` — token injection only; lookup injection is Phase 4.
- [x] **P2-S7** `whoami_info` pulled forward from Phase 6 as a walking skeleton (resolves §12.3), plus a `graphql-mock-v3` service proving the vendored SDL loads correctly.

Nine commits merged. Verified locally (2026-09-03): `docker compose run --rm
test-v3 units --requirements` — 331 passed, 1 skipped (module_utils) + 27
passed (controller); `docker compose run --rm lint-docs-v3` — clean;
`grep -rn "import gql\|import requests\|from graphql" plugins/` — empty;
`grep -rln "ansible.errors" plugins/` — `plugins/action/__init__.py` only;
no `/tmp` path or `shell=True` in `ssh.py`/`cache.py`; `StrictHostKeyChecking`
defaults to `accept-new`; story/decision-ID references confined to test
docstrings (`AGENTS.md`'s comment rule applies to shipped code, not test
narration, though P2-S7's own review flagged and removed them from shipped
files).

**Two process findings worth carrying into every later phase, not just
recording for Phase 2:**

- A green suite hid a cross-story regression: P2-S6's action shim silently
  dropped P2-S3b's `BatchMode=yes` default (inserting a config key with value
  `None` instead of omitting it, which defeated `resolve_token`'s
  `.get(key, default)` fallback) while `TestBatchMode` stayed green, because
  it exercised `request_grant` directly and never went through the shim.
  Caught only because `review` traced the option end-to-end through the real
  call path rather than trusting a passing assertion on an intermediate
  dict. **Any option with a default that must survive a hand-off between two
  layers needs a test asserting the value at the far end, not at the
  boundary.**
- A guard test can pass for the wrong reason: P2-S7's vacuous-pass guard for
  the flat-query sweep was satisfied by `DOCUMENTATION`/`RETURN` prose
  matching the sweep's own detection regexes, not by the `build_query()`
  extension it was written to prove. The fix
  (`test_vacuous_pass_guard_depends_on_the_build_query_extension`, which
  disables the extension and asserts the guard then fails) is a **guard on
  the guard** — worth the pattern name, since Phase 3's generator produces
  code at a much larger scale and the same failure mode (a passing test that
  isn't testing what it claims) is more expensive to catch late.

### Phase 3 — Generator + runtime engine (highest risk — validate before breadth)

**Amended (2026-09-03).** The original split — generator-only in Phase 3,
`resource.py`/`lookup.py` deferred to Phase 4 — could not close its own gate:
the Phase 3 gate requires "`check_mode`/`--diff` are correct", but that
correctness lives entirely in the read-diff-mutate engine Phase 4 was meant
to own. Phase 3 now owns both the generator *and* the runtime engine it
generates against, proven together on three resources — the same
walking-skeleton shape that worked for Phase 2's `whoami_info`. Old Phase 5
("generate the core set") folds into this phase's breadth stories; **Phase 5
is retired** and Phases 6/7/8 keep their existing numbers unchanged (every
cross-reference to "Phase 8" elsewhere in this document and in
`v3-phase1-stories.md`/`v3-phase2-stories.md` still resolves correctly).

Twelve discrete, independently reviewable stories — one commit each, reviewed
and iterated before the next begins. Full context, acceptance criteria and
verification commands: **[`docs/plans/v3-phase3-stories.md`](./v3-phase3-stories.md)**.

- [ ] **P3-S1** `codegen/` scaffold — SDL loader, `codegen-v3` compose service, `pytest` harness. `graphql-core` never enters the `ansible-test` environment (D3).
- [ ] **P3-S2** `module_utils/lookup.py` — name→id resolution + controller-side cache + invalidation, per §7.3.
- [ ] **P3-S3** `module_utils/resource.py` — `LagoonResourceModule`, the full read/diff/mutate/check_mode flow from §7.4.
- [ ] **P3-S4** Hand-write `project` against `resource.py`/`lookup.py` directly (no generator yet) — the golden target the generator must reproduce byte-identically.
- [ ] **P3-S5** Port `argspec.py` to `codegen/`, fixing the three defects found against the real SDL (missing `no_log`, wrong list `elements`, dropped enum `choices` on list types) — see §6.1.
- [ ] **P3-S6** `codegen/wire.py` — per-mutation wire-shaping (flat argspec ↔ nested `{id, patch}`; create-only/update-only enforcement, P3-D1).
- [ ] **P3-S7** `codegen/docgen.py` — `DOCUMENTATION`/`EXAMPLES`/`RETURN` emission via the description fallback chain (P3-D3).
- [ ] **P3-S8** `codegen/allowlist.py` + `codegen/allowlist.yml` — schema per §6, hard failure on schema drift.
- [ ] **P3-S9** Jinja templates (`module.py.j2`, `info_module.py.j2`, `action_shim.py.j2`) + `generate.py` + `make generate`/`make verify-generated` — **gate:** regenerating `project` reproduces P3-S4's hand-written file byte-for-byte.
- [ ] **P3-S10** Generate `environment` — proves the `project_id` lookup end to end.
- [ ] **P3-S11** Generate `env_variable` — proves the list-read/client-side-filter path (no id lookups; `getEnvVariablesByProjectEnvironmentName` returns `[EnvKeyValue]`) and enum-case diff normalisation (P3-D9).
- [ ] **P3-S12** Gate closure — `verify-generated` clean; `project`/`environment`/`env_variable` integration-tested end to end against `graphql-mock-v3`; `check_mode`/`--diff` correctness demonstrated for all three.

Order is strictly sequential, S1 → S2 → S3 → S4 → S5 → S6 → S7 → S8 → S9 → S10 → S11 → S12.
S4 (hand-written `project`) must land and be reviewed *before* S9's templates
exist — the golden-target technique only works if the target predates the
thing that must reproduce it.

Phase 5 ("generate the core set") is retired into Phase 3 above — its two
line items (extend the allowlist; integration-test each generated module)
are exactly P3-S10/S11 and P3-S12. Phase numbering below is otherwise
unchanged, so every existing "Phase 8" cross-reference in this document and
in `v3-phase1-stories.md`/`v3-phase2-stories.md` still resolves correctly;
there is deliberately no "Phase 5" section below.

### Phase 6 — Bespoke modules
- [x] `whoami_info` — shipped early in Phase 2 (P2-S7) as the auth walking skeleton, not deferred to this phase per the original plan. Remaining scope below is unaffected.
- [ ] Hand-write `deploy_bulk`, `lagoon_log`, `cmdb_diff` on the shared `module_utils`.
- [ ] Triage remaining v1 actions: port, defer, or drop — record the decision per action in the migration guide.

### Phase 7 — Inventory
- [ ] Rewrite per §8; delete batching knobs.
- [ ] Unit tests with mocked responses; document the v1 → v3 config migration.

### Phase 8 — Docs, CI, release
- [ ] Extend `build-docs.yml` for the new collection name; keep QuantCDN publishing.
- [ ] Add `verify-generated` to CI — fail if committed modules differ from a fresh generation.
- [ ] `ansible-test sanity` (all Python versions in support matrix) + `units` + `integration`.
- [ ] `docs/migration-v1-to-v3.md` with the mapping table (§10).
- [ ] `docs/adr/0001-graphql-codegen-rest-semantics.md`.
- [ ] Drop `gql` / `requests-toolbelt` / `urllib3` pins from runtime requirements.
- [ ] Tag and publish `3.0.0`; document that `lagoon.api` users pin `<3.0.0` until migrated.

---

## 10. Migration mapping (to complete in Phase 8)

| v1 `lagoon.api` action                                    | v3 `salsadigitalauorg.lagoon` module | Notes                                |
| --------------------------------------------------------- | ------------------------------- | ------------------------------------ |
| `project`, `project_update`                               | `project`                       | Collapsed under `state`              |
| `environment`, `environment_update`, `environment_delete` | `environment`                   | Collapsed under `state`              |
| `env_variable`, `variables`                               | `env_variable`                  | `project_name` / `namespace` lookups |
| `deploy`                                                  | `deployment`                    |                                      |
| `deploy_bulk`                                             | `deploy_bulk`                   | Hand-written                         |
| `task`, `task_definition`                                 | `task`                          |                                      |
| `group`, `user_group`, `project_group`                    | `group`                         |                                      |
| `project_notification`                                    | `notification`                  |                                      |
| `info`, `list`, `query`, `whoami`                         | `*_info` modules                | Flat fields only                     |
| `fact`, `problem`, `metadata`, `last_deploy`              | TBD Phase 6                     | Triage                               |
| `cmdb_diff`, `lagoon_log`                                 | `cmdb_diff`, `lagoon_log`       | Hand-written                         |
| `fetch_token` + `token` role                              | *removed*                       | Automatic in every module            |
| `mutation` (generic)                                      | *removed*                       | Use typed modules                    |

**Breaking changes to call out prominently:** FQCN change (`lagoon.api.*` → `salsadigitalauorg.lagoon.*`); nested field selection no longer supported; inventory batching options removed; `token` role removed. Also (P2-D10, discovered post-P2-S3): v1's `token` role passed `ssh_options: "-q -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"` — in v3 both `StrictHostKeyChecking` and `UserKnownHostsFile` set via `lagoon_ssh_options` are silently ignored, since collection-managed `-o` options are emitted first and OpenSSH is first-wins. Operators relying on that idiom must switch to `lagoon_ssh_strict_host_key_checking` / `lagoon_ssh_known_hosts_file`. This is not a functional regression — v3's defaults (`accept-new`, unset) are the secure replacement for what that idiom disabled — but the option string silently doing nothing is a genuine behavioural change worth flagging explicitly in release notes. SSH agent authentication itself (P2-D9) is **not** a breaking change: v3 restores v1 parity there after a regression was caught and fixed pre-merge (P2-S3a).

---

## 11. Risks

| Risk                                                                           | Severity     | Mitigation                                                                                                                                                     |
| ------------------------------------------------------------------------------ | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lagoon SDL lacks a natural read query for some resources, blocking idempotency | **Warning**  | Phase 3 gate exposes this early on 3 resources. Where no read exists, document the module as non-idempotent and set `changed=True` — do not fake a diff.       |
| Generated argspec wrong for deeply nested input objects                        | **Warning**  | v1's `argspec.py` is already battle-tested on `addAdvancedTaskDefinition`; reuse rather than rewrite. Snapshot-test generated argspecs. **Amended:** it is a *port*, not a reuse — verified against the real SDL it has three concrete defects (no `no_log` emission at all; `elements='dict'` hard-coded for every list type, wrong for `[String]`/`[Restriction]`; `choices` dropped on enum list types). See §6.1 and P3-S5. |
| Dropping nested queries increases request count (N+1)                          | **Info**     | Accepted tradeoff — this is the explicit goal. Lookup caching and per-run token reuse blunt the cost. Measure once the core set is generated (old Phase 5, folded into Phase 3's breadth stories).                                      |
| `addProject`/`updateProject` (and `environment`'s equivalents) are structurally asymmetric | **Warning** | Discovered verifying §6's allowlist example against the real SDL: create is flat, update is `{id, patch: {...}}, with divergent create-only/update-only field sets. §6 and P3-D1 fix the allowlist example and generator design; not merely a docs error — the original example would have generated a broken `update` mutation call. |
| `LagoonClient.build_query()`'s `args` parameter interpolates GraphQL *type* strings unvalidated | **Warning** | Found in P2-S7 review (only field *names* are validated by `_FIELD_FORBIDDEN_RE`); reproduced: `args={'name': 'String!) { evil { deeply { nested } } } #'}` produces a depth-3 document that the flat-query sweep still catches, but a crafted field name containing `"` crashes the depth scanner with `QueryDepthError` instead of failing cleanly. Deliberately deferred past Phase 3 — `args` values are generator-controlled from Phase 3 onward, not user-controlled, so the risk is latent rather than exploitable in the collection's own code paths. **Must be fixed in Phase 8** alongside the other security items in §9; do not let "generator-controlled today" become "forgotten by 3.0.0". |
| Action-plugin sidecar reintroduces controller-side complexity                  | **Warning**  | Strict boundary in §4, enforced in review. Modules must pass their unit tests with no sidecar involved.                                                        |
| Clean break strands GovCMS                                                     | **Warning**  | Side-by-side install is possible (new namespace), so v1 and v3 can coexist during migration. Coordinate the cutover with the GovCMS team before tagging 3.0.0. |
| SSH key written to predictable `/tmp` path (inherited from v1)                 | **Critical** | Fixed in Phase 2 (P2-S2) — `mkdtemp` + `O_EXCL`/`0600` + `finally` cleanup. Must not be carried forward.                                                       |
| `validate_certs` defaults to `False` in v1 `api_client.py` — TLS verification off | **Critical** | Fixed in P1-S4: defaults to `True`, opt-out explicit and documented (ISM-1552). Explicit review-focus item on that story.                                       |
| GraphQL injection via `%s`/`%d` interpolation into query text (v1)              | **Critical** | Fixed in P1-S4: all user data via the `variables` map; `build_query` rejects field names containing braces, whitespace or parens.                               |
| Guardrail sweep passes vacuously if it matches zero documents                   | **Warning**  | P1-S5 acceptance criterion: the sweep must fail on zero candidates once `plugins/modules/` is populated. Highest-leverage check in Phase 1. Confirmed to fire, as designed, the moment P2-S7 adds the first real module — see the sweep-extension work in that story. |
| `ansible-test sanity` at the repo root will also scan `api/` (D17 + D18)        | **Info**     | Units are unaffected. Sequence the `api/` deletion before sanity lands in Phase 8, in preference to `ignore-*.txt` entries.                                     |
| v1 `token` role disables SSH host key verification unconditionally             | **Critical** | Fixed in Phase 2 (P2-S2/P2-D4) — `StrictHostKeyChecking=accept-new` by default. A MITM on the grant channel previously yielded an attacker-controlled bearer token for the whole play.                                                                        |
| SDL carries field descriptions on only 14/193 `input` types                    | **Warning**  | Discovered during Phase 2 story planning; **quantified during Phase 3 story planning** against the three gate resources specifically: `AddProjectInput` 0/36 described, `UpdateProjectPatchInput` 0/39, `EnvVariableByNameInput` 0/6. §6.1's fallback chain (input desc → same-named output-type field desc → `allowlist.yml` override → fail build) is now specified, not just flagged as needed. Output-type fallback alone covers 29/36 on `project`, 10/14 on `environment`, but **0/6** on `env_variable` — every gate module needs at least some allowlist override text, `env_variable` needs it for all six options. See P3-D3. |
| v3's `auth.py` guard made SSH agent auth unreachable — a regression against v1 | **Warning**  | Caught in `review` of P2-S3, before merge. v1's `fetch_token` supported agent auth (it only wrote a key file when a key was actually given); v3's original "exactly one of private_key/private_key_file" guard rejected the neither-supplied case. Fixed in P2-S3a (P2-D9); the agent path now has explicit tests (`no env= kwarg reaches subprocess.run`) — it previously worked by accident and was entirely untested. |

---

## 12. Open items for the implementer

1. **In progress (P1-S2).** Confirm the exact Lagoon version to pin the SDL against.
   The `2.33.1` assumption is unverified. Procedure — query `lagoonVersion` for the
   real value, then `gql-cli --print-schema` — is in P1-S2; maintainer runs it
   against the GovCMS target. The fetched value supersedes every `2.33.1` reference
   in this document.
2. **Still open.** Confirm Galaxy namespace ownership for `salsadigitalauorg`.
   Rescoped: not a Phase 1 blocker (nothing publishes until Phase 8), but must be
   settled before tagging `3.0.0`.
3. ~~Still open — Phase 3.~~ — **Resolved (P2-D5/P2-S7):** yes, `*_info` modules
   need the action shim — they require a token exactly like any other module.
   Settled by pulling `whoami_info` forward into Phase 2 as a walking skeleton.
   See `docs/plans/v3-phase2-stories.md`.
4. ~~Support matrix~~ — **Resolved (D19):** `requires_ansible: '>=2.16'`, tested
   Python 3.11 / 3.12 / 3.13.
5. **New, post-Phase 8.** Cleanup story: delete `api/`, the v1 compose services and
   `api/tests/common/schema.graphql`; repoint `.docker/Dockerfile.graphql-mock`
   (previously "Phase 5", now folded into Phase 3 — see the Phase 3 heading's
   note) and `.docker/Dockerfile.docs` (Phase 8) away from `lagoon/api`.
6. **New, Phase 3 story planning.** `env_variable`'s `value` option carries
   `no_log: true` (it is a secret on the wire per the real
   `EnvVariableByNameInput`/`EnvKeyValue` types). `--diff` must report
   changed/unchanged for that field without ever rendering the value itself,
   in either the before or after side of the diff — resolved by explicit
   decision, not Ansible's default `no_log` diff suppression, since a bare
   `VALUE_SPECIFIED_IN_NO_LOG_PARAMETER` for the whole diff would defeat the
   Phase 3 gate's own "`--diff` is correct" acceptance criterion. See P3-S11.
7. **New, Phase 3 story planning.** `codegen/`'s dependency on `graphql-core`
   (a generator-only dev dependency per D3) needs its own test container
   (`codegen-v3`, plain `pytest`) rather than running inside `test-v3`'s
   `ansible-test` environment, so `graphql-core` never has a path into the
   environment that also runs the shipped collection's unit tests — keeping
   D3's "generator-only" property structurally enforced, not just documented.
   See P3-S1.
