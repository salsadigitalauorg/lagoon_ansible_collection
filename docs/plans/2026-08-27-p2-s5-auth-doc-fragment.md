# P2-S5 — `doc_fragments/auth.py` + argspec drift test

**Date:** 2026-08-27
**Story:** [`docs/plans/v3-phase2-stories.md`](./v3-phase2-stories.md) § P2-S5
**Parent plan:** [`docs/plans/v3-refactor.md`](./v3-refactor.md) §9 Phase 2, §7.2
**Branch:** `3.x`
**Depends on:** P2-S4 (`64cd23d`)
**Status:** Ready for implementation

---

## Scope

Two files, one commit:

```
plugins/doc_fragments/auth.py                        (new)
tests/unit/plugins/module_utils/test_auth_docs.py    (new)
```

No changes to `auth.py`, `ssh.py`, or `cache.py`. This is a documentation +
drift-test story; per P2-S3a/P2-S3b precedent, behaviour changes to
`module_utils` get their own story.

The real deliverable is the **drift test**, not the YAML. The fragment is a
second, independent declaration of the option set that `auth_argument_spec()`
already owns canonically (P2-D6); the test is what stops the two diverging
once Phase 3 generates modules against both.

---

## Stop-and-raise: AC #4 is unimplementable as written

Per process rule 5, recording this rather than silently deviating.

**The story's AC #4** — "Every option with `no_log=True` in the argspec is
marked `no_log: true` in the fragment (add this to the fragment's schema even
though `antsibull-docs` doesn't strictly require it — belt and suspenders)" —
**directly contradicts** the story's own AC "`docker compose run --rm
lint-docs-v3` passes". `no_log` is not merely unrequired by `antsibull-docs`;
it is **rejected**.

### Evidence

`antsibull_docs.schemas.docs.base.BaseModel` sets:

```python
model_config = p.ConfigDict(extra="forbid", coerce_numbers_to_str=True)
```

`OptionsSchema` declares `description, aliases, choices, default, elements,
required, type, version_added, version_added_collection` — no `no_log`.

Direct schema probe:

```
OptionsSchema(description=['x'], type='str', no_log=True)
  -> 1 validation error for OptionsSchema
     no_log  Extra inputs are not permitted [type=extra_forbidden, input_value=True]
OptionsSchema(description=['x'], type='str')
  -> OK
```

End-to-end, via a throwaway `acme.demo` collection whose module does
`extends_documentation_fragment: [acme.demo.auth]`:

```
plugins/modules/demo_info.py:0:0: 1 validation error for ModuleDocSchema
                                  doc -> options -> lagoon_api_token -> no_log
                                    Extra inputs are not permitted (type=extra_forbidden)
plugins/modules/demo_info.py:0:0: Did not return correct DOCUMENTATION
```

The same scratch collection with `no_log` removed, and otherwise covering
`str`/`int`/`raw`/`path`/`bool` options plus defaults, exits `0`.

### Why the story got this wrong

`no_log` is valid in an **argspec** — `validate-modules`'
`argument_spec_schema()` lists `'no_log': bool` — but not in a
**DOCUMENTATION** block. The story conflated the two schemas. `no_log`'s
redaction behaviour comes entirely from the argspec, which
`auth_argument_spec()` already sets correctly; putting it in the fragment
would add no runtime protection even if the schema allowed it.

### Why this story would nonetheless have passed CI

`doc_fragments` is **not** a documentable plugin type:

```
antsibull_docs.constants.DOCUMENTABLE_PLUGINS ==
  frozenset({'module', 'lookup', 'filter', 'test', 'callback', 'connection',
             'inventory', 'become', 'cache', 'cliconf', 'netconf', 'httpapi',
             'shell', 'strategy', 'vars', 'role'})
```

A fragment is only ever validated *through a module that extends it*. With
`plugins/modules/` empty, `lint-docs-v3` exits `0` today regardless of what
the fragment contains — verified against the real repo. So a `no_log`-bearing
fragment would land green here and detonate in **P2-S7**, the first story to
add a module extending it. Fixing it here is the cheap end.

### Resolution (decided with the user)

Drop `no_log` from the fragment, and **keep the intent** via two substitute
assertions in the drift test (replacing requirement 4 rather than deleting
it):

- **4a.** Assert **no** fragment option carries a `no_log` key at all — a
  regression guard, with the antsibull constraint recorded in a comment so a
  future contributor doesn't "helpfully" add it back and break P2-S7.
- **4b.** Assert every argspec option with `no_log=True`
  (`lagoon_api_token`, `lagoon_ssh_private_key`) has prose in its fragment
  `description` marking it as sensitive. This is the belt-and-suspenders
  value AC #4 was reaching for, expressed in the one place antsibull
  actually renders to operators.

Record the deviation in the commit body.

---

## `plugins/doc_fragments/auth.py`

Standard `ModuleDocFragment` shape, modelled on
`api/plugins/doc_fragments/auth_options.py` but covering the full v3 option
set. No `__init__.py` is needed in `plugins/doc_fragments/` — verified that
the namespace-package import works without one, matching
`plugins/module_utils/`'s existing layout.

### Option set — exactly these 13, no more, no fewer

Mirrors `auth_argument_spec()` as it stands after P2-S3b (`64cd23d`).
Dumped from the live argspec, not transcribed from the story text:

| Option | `type` | `default` | argspec `no_log` |
| ------ | ------ | --------- | ---------------- |
| `lagoon_api_endpoint` | `str` | — | |
| `lagoon_api_token` | `str` | — | ✅ |
| `validate_certs` | `bool` | `true` | |
| `lagoon_ssh_host` | `str` | — | |
| `lagoon_ssh_port` | `int` | `22` | |
| `lagoon_ssh_user` | `str` | `lagoon` | |
| `lagoon_ssh_private_key` | `str` | — | ✅ |
| `lagoon_ssh_private_key_file` | `path` | — | |
| `lagoon_ssh_known_hosts_file` | `path` | — | |
| `lagoon_ssh_options` | `raw` | — | |
| `lagoon_ssh_strict_host_key_checking` | `str` | `accept-new` | |
| `lagoon_ssh_batch_mode` | `bool` | `true` | |
| `lagoon_token_cache` | `bool` | `false` | |

Options whose argspec default is `None` **omit** `default:` from the fragment
(don't write `default: null`) — `yaml.safe_load` then yields no key and
`.get('default')` returns `None` on both sides, so parity holds. Verified.

The story's speculative `lagoon_token_cache_dir` (“if exposed”) is **not
exposed** — `cache.cache_dir()` resolves `$XDG_CACHE_HOME`/`~/.cache`
internally with no config seam. Correctly absent; the drift test would reject
it.

### Required prose

Each of these is an AC, not a nicety:

1. **`lagoon_api_token`** — the `LAGOON_API_TOKEN` environment-variable
   fallback; and that a long-lived token is the **exceptional** path
   (short-lived SSH-grant tokens strongly preferred), stored in Ansible Vault
   and rotated on a 12-month cycle (§7.2). Doubles as the 4b sensitivity
   marker.
2. **`lagoon_ssh_strict_host_key_checking`** — that `no` disables host key
   verification and permits a MITM on the grant channel to supply an
   attacker-controlled bearer token for the whole play (P2-D4).
3. **`lagoon_ssh_private_key` / `lagoon_ssh_private_key_file`** — mutually
   exclusive; supplying **neither** authenticates via the SSH agent over the
   inherited `SSH_AUTH_SOCK` and **is not an error** (P2-D9).
   `lagoon_ssh_private_key` also needs the 4b sensitivity marker.
4. **`lagoon_ssh_options`** — that collection-managed `-o` options
   (`StrictHostKeyChecking`, `ConnectTimeout`, `UserKnownHostsFile`,
   `BatchMode`) are emitted **before** this value and OpenSSH is first-wins,
   so this option **cannot** override any of them (P2-D10); use the dedicated
   option instead. Worth naming that v1's
   `"-q -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"` idiom
   is now a silent no-op.
5. **`lagoon_token_cache`** — off by default; the only path in the collection
   that persists a bearer token to disk; `$XDG_CACHE_HOME/ansible-lagoon`
   (else `~/.cache/ansible-lagoon`), dir `0700`, file `0600`; and the P2-D11
   agent-auth caveat (two agent identities sharing
   `(endpoint, host, port, user)` share one entry).
6. **`lagoon_ssh_batch_mode`** — why it defaults `true` (a grant that cannot
   authenticate fails fast instead of stalling on an unanswerable prompt).

Keep `description` entries as YAML lists of short strings, matching v1's
style. Use `O(...)`/`V(...)` antsibull markup only if it lints clean — plain
prose is acceptable and lower-risk.

---

## `tests/unit/plugins/module_utils/test_auth_docs.py`

Location follows the story text. Note it tests a `doc_fragments` plugin from
a `module_utils` test directory — deliberate, since the subject under test is
the *parity relationship* with `auth_argument_spec()`, and the existing
`__init__.py` scaffolding is already there.

Imports mirror the established relative-import style
(`from .....plugins.module_utils.auth import auth_argument_spec`,
`from .....plugins.doc_fragments.auth import ModuleDocFragment`), matching
`test_auth.py` / `test_cache.py`.

Parse once with `yaml.safe_load(ModuleDocFragment.DOCUMENTATION)['options']`
and compare **structurally**. The comparison logic below was prototyped
against the real argspec and reports full parity, so the test should pass on
a correctly-written fragment first time — if it doesn't, the fragment is
wrong, not the test.

### Assertions

1. **Names, both directions.** `set(fragment) == set(argspec)`. On failure,
   report the two set differences separately (`only in argspec` / `only in
   fragment`) — a bare `assertEqual` on sets is unreadable when it fires,
   and this is the assertion most likely to fire in Phase 3.
2. **`type` agrees** for every shared option. Default both sides to `'str'`
   when absent (argspec and antsibull both treat `str` as the implicit type)
   so an omitted `type:` can't read as a mismatch.
3. **`default` agrees** where the argspec declares one, via plain
   `.get('default')` on both sides. YAML `true`/`false`/`22`/`accept-new`
   normalise onto `True`/`False`/`22`/`'accept-new'` — verified, no coercion
   helper needed. Do **not** add a `str()` normalisation: it would mask a
   real `'22'` vs `22` divergence.
4. **4a — no `no_log` key anywhere in the fragment.** Comment must state
   *why* (antsibull `extra="forbid"`; see the stop-and-raise above) and that
   redaction is the argspec's job.
5. **4b — sensitivity prose.** For each argspec option with `no_log=True`,
   assert its joined fragment `description` matches a sensitivity signal
   (case-insensitive, e.g. `vault|secret|sensitive`). Assert **per option**,
   not over the whole document, so a marker on the wrong option can't
   satisfy it.
6. **Non-empty `description`** for every documented option — reject `None`,
   `''`, `[]`, and `['']`.
7. **Required prose markers**, each a small focused test asserting on the
   *specific option's* description (never a whole-document substring
   search — that's the vacuous-pass shape the story's review focus calls
   out): `LAGOON_API_TOKEN` + Vault/rotation on `lagoon_api_token`; MITM
   warning on `lagoon_ssh_strict_host_key_checking`; `SSH_AUTH_SOCK`/agent on
   both key options; the cannot-override rule on `lagoon_ssh_options`.
8. **The fragment YAML parses at all**, and `options` is a non-empty dict —
   cheap guard so a YAML syntax error surfaces as one clear failure rather
   than 12 confusing `KeyError`s.

### Proving the test bites

Per the story's AC ("prove this by temporarily breaking parity locally").
Do it **without** committing a broken fragment: in-test, deep-copy the
parsed fragment dict, mutate the copy (delete an option; flip a `type`;
inject a `no_log`), and assert the comparison helper reports a failure. This
makes "the test bites" a committed, permanent property rather than a claim in
a commit message.

Structure the comparison as a helper returning a list of problem strings,
with the `unittest` cases asserting on it. That is what makes the
self-check above expressible.

---

## Acceptance criteria

- [ ] Fragment covers every `auth_argument_spec()` key — all 13, no extras.
- [ ] Drift test compares **structurally** (parsed YAML vs argspec), not by
      substring presence.
- [ ] Drift test fails if a key is added to one side only — proven by
      committed self-check tests (mutated deep copies), not a manual
      experiment.
- [ ] Long-lived-token warning (Vault + 12-month rotation) present.
- [ ] Host-key-checking MITM warning present.
- [ ] Agent-auth (`SSH_AUTH_SOCK`, "not an error") documented on the key
      options.
- [ ] P2-D10 non-overridability documented on `lagoon_ssh_options`.
- [ ] **No `no_log` key in the fragment** (deviation from AC #4, with the
      antsibull `extra="forbid"` reason recorded in code comment + commit
      body), and 4a/4b substitutes both present.
- [ ] `docker compose run --rm lint-docs-v3` passes.
- [ ] No changes to `auth.py` / `ssh.py` / `cache.py` in this commit.

## Verification commands

```sh
docker compose run --rm test-v3 units -v --requirements \
  tests/unit/plugins/module_utils/test_auth_docs.py

docker compose run --rm lint-docs-v3

# The fragment must not reintroduce no_log (would break P2-S7's module).
# Matches the YAML key form only: a bare `grep -n no_log` also hits the
# header comment that explains why the key is absent, which this story
# deliberately requires -- so the naive form is a false positive.
grep -nE '^\s+no_log\s*:' plugins/doc_fragments/auth.py \
  && echo "FAIL: no_log in fragment -- antsibull forbids it" || echo "OK"

# Full suite, to confirm no collateral damage.
docker compose run --rm test-v3 units -v --requirements
```

`lint-docs-v3` is currently vacuous for fragments (no modules yet, so nothing
extends this one). It is still worth running — it catches YAML syntax errors
and proves no regression — but **it does not prove the fragment is valid**.
The scratch-collection method described in the stop-and-raise section is how
that was actually established, and P2-S7 is where it gets enforced for real.

## Review focus

- Does the drift test parse YAML and compare structurally, or is any check
  secretly a whole-document substring search that would pass vacuously?
- Do the self-check tests genuinely fail the helper, or are they asserting on
  something trivially true?
- Are both required warnings prominent in the rendered description, not
  buried mid-list?
- Is the `no_log` deviation clearly justified in-code, so a reviewer
  pattern-matching on AC #4 doesn't "fix" it back into a P2-S7 breakage?
- Is `default` comparison free of over-normalisation that would hide a real
  `'22'`-vs-`22` type drift?

## Commit

```
feat(v3): add shared auth doc fragment with an argspec drift test

extends_documentation_fragment target for the auth options resolved
by module_utils/auth.py. A test parses the fragment's DOCUMENTATION
against auth_argument_spec() so the two declarations of the same
option set cannot silently diverge once Phase 3 generates modules
against both.

Deviates from P2-S5's AC 4, which asked for no_log: true in the
fragment as belt-and-suspenders. antsibull-docs' OptionsSchema sets
extra="forbid" and has no no_log field, so a module extending a
no_log-bearing fragment fails lint with "Did not return correct
DOCUMENTATION". no_log is valid in an argspec (validate-modules
allows it) but not in a DOCUMENTATION block -- the AC conflated the
two schemas. It would not have failed here, because doc_fragments is
not in antsibull's DOCUMENTABLE_PLUGINS and is only validated through
a module that extends it; it would have failed in P2-S7 instead.

The intent is preserved by two substitute assertions: the fragment is
asserted to carry no no_log key at all (a regression guard against
reintroducing the P2-S7 break), and every no_log=True argspec option
is asserted to carry explicit sensitivity prose in its description.
Redaction itself remains the argspec's job, where it already works.

Refs docs/plans/v3-refactor.md Phase 2, 7.2
Refs docs/plans/2026-08-27-p2-s5-auth-doc-fragment.md
```

---

## Follow-ups raised, deliberately not in this story

- **`lagoon_ssh_timeout` is missing from `auth_argument_spec()`.**
  `auth.resolve_token()` reads `config.get('timeout') or
  _DEFAULT_SSH_TIMEOUT` (`auth.py:224`) and threads it to
  `request_grant(timeout=...)`, but no argspec option exposes it — so no
  module can set the SSH grant timeout. Same defect class as P2-S3a
  (resolver-consumed, module-unsettable). Per the user's decision this is
  **out of scope for P2-S5 and not documented in the fragment**: the
  fragment mirrors the 13 options that exist, and the drift test would
  reject a 14th. Noted here only so the gap is on the record; treat
  `timeout` as internal-only unless a later story chooses to expose it, at
  which point both the argspec and this fragment must change together —
  which the drift test will enforce.
- **P2-S7 will be the first real validation of this fragment.** Expect the
  `validate_certs` note in `auth_argument_spec()`'s docstring
  (`client.py::_fetch_url_call` reads `module.params['validate_certs']`) to
  matter there.
