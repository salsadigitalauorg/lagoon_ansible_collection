# v3 Phase 2 — Auth: Implementation Stories

**Date:** 2026-08-26
**Parent plan:** [`docs/plans/v3-refactor.md`](./v3-refactor.md) §9 Phase 2
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
   commit body. (Phase 2's own breakdown already did this three times — see
   the decisions table below.)
6. **P2-S2 is the security-critical story in this phase** — it fixes the Critical
   SSH-key-handling defect carried over from v1. Consider routing that commit
   through the `security` agent in addition to `review`.
7. **P2-S7 is the only story carrying an unverified assumption** (the vendored
   SDL loads cleanly under the mock server's `graphql-import` loader — this
   could not be verified in the story-breakdown session because Docker Desktop
   does not share `/tmp` with containers on this machine). It is sequenced last
   so a failure there blocks nothing upstream. If it fails, stop and raise it —
   do not weaken the AC to work around a loader incompatibility.

---

## Phase 2 decisions (resolved during story breakdown)

These resolve open items and **correct** parts of `v3-refactor.md` §4 and §7.2.
They apply to every story below and are also being applied as amendments to the
parent plan itself (see the amendment list at the end of this document).

| # | Item | Decision |
| - | ---- | -------- |
| **P2-D1** | **Token cache** | In-memory module-level cache **always on** (scoped to one worker process — see P2-D2 for why this is less than a whole play). Optional cross-process **file** cache, **opt-in** via `lagoon_token_cache: true`, stored under `$XDG_CACHE_HOME/ansible-lagoon/` (or `~/.cache/ansible-lagoon/`), directory mode `0700`, file mode `0600` — **never `/tmp`**. This supersedes the file-cache-first design in parent plan §7.2. |
| **P2-D2** | **Fork model correction** | Parent plan §4 claims the sidecar "buys one grant per play". This is incorrect: Ansible forks a `WorkerProcess` per `(host, task)` pair, and action plugins run only in the child, so a module-level cache is scoped to **one task**, not one play. It *is* shared across all iterations of a `loop:` on that task, which is where Lagoon's N+1 pattern (e.g. looping over many projects) actually bites hardest. Cross-*task* reuse within a play requires either the opt-in file cache (P2-D1) or an explicit `lagoon_api_token` set once via `set_fact`, matching the documented v1 fallback in parent plan §4. |
| **P2-D3** | **Shim dispatch mechanism** | Parent plan §4 states per-module sidecars could be "a single sidecar registered for all modules via `action_groups`". This is incorrect: `action_groups` only groups modules for `module_defaults` sharing; it does not affect action-plugin dispatch. Ansible dispatches to an action plugin only when a file of the same name exists under `plugins/action/`. **Per-module `plugins/action/<name>.py` files, each a one-line `LagoonActionShim` subclass, are mandatory.** The Phase 3 generator must emit one per generated module. `action_groups` is still added, but for `module_defaults` convenience only. |
| **P2-D4** | **SSH host key verification** | On by default, `StrictHostKeyChecking=accept-new`. Explicit opt-out (`no`) requires an explicit option and emits a documented warning. This reverses v1's `token` role, which hard-codes `-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null` — a MITM on the grant channel yields an attacker-controlled bearer token for the whole play. |
| **P2-D5** | **Walking skeleton** | `whoami_info` is pulled forward from Phase 6 into Phase 2 (P2-S7). It proves endpoint → auth → shim → module → client end to end before the Phase 3 generator exists, and resolves parent plan open item §12.3 ("whether `*_info` modules need the action shim"). |
| **P2-D6** | **Argspec home** | `auth_argument_spec()` is the canonical definition, in `plugins/module_utils/auth.py`. `plugins/doc_fragments/auth.py` is a second, independent declaration of the same options for `antsibull-docs`. A drift test (P2-S5) binds the two mechanically so they cannot silently diverge once Phase 3 starts generating modules against both. |
| **P2-D7** | **CI** | Still out of scope, per P1-D5. Local verification only, via `test-v3` and the new `graphql-mock-v3` service (P2-S7). |
| **P2-D8** | **Mock service is a hard AC** | `graphql-mock-v3`, serving the vendored `schema/lagoon-2.33.0.graphql`, is a **hard acceptance criterion** of P2-S7, not an optional nice-to-have. This retires the Phase 5 carry-forward item "`.docker/Dockerfile.graphql-mock` still copies `api/tests/common/schema.graphql`" for the v3 path early. A `package-lock.json` must be committed alongside it, because the existing mock's dependencies (`graphql-import`, `graphql-tools`) are unpinned (`^`) with no lockfile, and an unpinned hard AC is a standing invitation for Phase 2 to break on an unrelated `npm install`. |

---

## Story index

| ID | Story | Depends on | Est. |
| -- | ----- | ---------- | ---- |
| P2-S1 | `module_utils/token.py` — JWT expiry inspection | P1-S3 | S |
| P2-S2 | `module_utils/ssh.py` — SSH grant + secure key handling | P2-S1 | L |
| P2-S3 | `module_utils/auth.py` — resolver + in-memory cache | P2-S2 | M |
| P2-S4 | `module_utils/cache.py` — opt-in cross-process file cache | P2-S3 | M |
| P2-S5 | `doc_fragments/auth.py` + argspec drift test | P2-S3 | S |
| P2-S6 | `LagoonActionShim` in `plugins/action/__init__.py` | P2-S5 | M |
| P2-S7 | `whoami_info` walking skeleton + sweep extension + `graphql-mock-v3` | P2-S6 | L |

---

# P2-S1 — `module_utils/token.py` — JWT expiry inspection

## Goal

Decide whether a cached token is still safely usable for the remainder of a
task, without a network round-trip and without pretending to be the token's
verifier.

## Context

Parent plan §7.2 step 3: "Cached token → **validate** (decode JWT `exp` with a
60s skew margin; no signature verification, we're not the verifier). If valid,
use it." This story implements exactly that primitive; P2-S3 consumes it.

v1 has no equivalent — it never inspects a token's freshness, it just re-grants
every task.

## Files to create

```
plugins/module_utils/token.py
tests/unit/plugins/module_utils/test_token.py
```

## Design

```python
def decode_jwt_claims(token):
    """Decode and return the JWT payload (2nd segment) as a dict.

    No signature verification -- the collection is the bearer, not the
    verifier; the Lagoon API validates the signature server-side. Raises
    LagoonAuthError if the token is not a well-formed JWT (wrong segment
    count, unpadded/invalid base64url, payload is not a JSON object).
    """

def token_expiry(token):
    """Return the 'exp' claim as an int, or None if absent/non-numeric.

    Never raises for a malformed token -- callers use this for a
    best-effort freshness check, not as a source of truth.
    """

def token_is_valid(token, skew=60, now=None):
    """True if the token decodes, has an 'exp' claim, and
    now + skew < exp. False for anything that cannot be proven fresh:
    missing 'exp', malformed token, or an exp within the skew window.

    now is injectable (defaults to time.time()) so tests never depend
    on wall-clock time.
    """
```

### Implementation notes

- Base64url-decode segment 1 only (`token.split('.')[1]`). Pad with
  `'=' * (-len(seg) % 4)` before calling `base64.urlsafe_b64decode`.
- `skew=60` means a token expiring in 30 seconds is **invalid** — it must not
  expire mid-task. This is deliberately more conservative than a bare `exp`
  comparison.
- Any of the following causes `token_is_valid` to return `False` (cannot
  prove freshness → the caller re-grants) and causes `decode_jwt_claims` to
  raise `LagoonAuthError`:
  - wrong number of `.`-separated segments (not exactly 3);
  - segment 1 is not valid base64url;
  - decoded segment 1 is not valid JSON;
  - decoded JSON is not an object;
  - `exp` claim missing, or present but not an `int`/`float`.
- `token_is_valid` must **swallow** every `LagoonAuthError` from
  `decode_jwt_claims` internally — it is a predicate, not a raiser.
- **The raw token must never appear in any exception message.** Same
  constraint as P1-S4's client and P1-S3's error taxonomy. If a malformed
  token needs describing in an error, describe the *shape* of the problem
  (segment count, decode failure), never the token bytes.
- This validation applies **only to tokens the collection itself cached**
  after an SSH grant. Steps 1–2 of the resolution order (explicit
  `lagoon_api_token` param, `LAGOON_API_TOKEN` env) use the supplied token
  as-is and never call this module — the plan does not ask the collection to
  second-guess a token the operator supplied directly, and there'd be no
  sensible recovery action if it looked invalid (re-granting would silently
  discard the operator's explicit token). Document this clearly in the
  module docstring so it isn't "fixed" into validating explicit tokens too.

### Hard constraints

- stdlib only (`base64`, `json`, `time`). No `jwt`/`PyJWT`, no `ansible.*`.
- Add the same AST-based forbidden-import test used in P1-S3/P1-S4.

## Testing requirements

1. A hand-built well-formed JWT (base64url-encode a header and a payload with
   a known `exp`, no real signature needed since it's never checked) —
   `token_is_valid` true well before expiry, false within skew, false after
   expiry.
2. `now` injection — pass a fixed `now` and assert the boundary at exactly
   `now + skew == exp`.
3. Malformed inputs, each asserted to return `False` / raise `LagoonAuthError`
   as appropriate: two segments, four segments, non-base64 segment, valid
   base64 but non-JSON payload, JSON array instead of object, missing `exp`,
   `exp` as a string.
4. `decode_jwt_claims` on a well-formed token returns the full claims dict
   (assert at least `exp` and one other claim survive).
5. Token value absent from every raised exception's `str()`.
6. Pickling round-trip is inherited from `LagoonAuthError` — no new test
   needed, but do not construct a token-module-specific exception subclass
   that breaks it.

## Acceptance criteria

- [ ] All three functions exist with the signatures above.
- [ ] No signature verification is performed anywhere in this file.
- [ ] `token_is_valid` never raises — every malformed-input case returns
      `False`.
- [ ] `decode_jwt_claims` raises `LagoonAuthError` (not a bare `ValueError`)
      for every malformed-input case.
- [ ] `skew` behaviour is exact at the boundary (test 2 above).
- [ ] No token value in any exception string.
- [ ] `token.py` imports nothing outside stdlib + `.errors`.

## Verification commands

```sh
docker compose run --rm test-v3 units -v --requirements \
  tests/unit/plugins/module_utils/test_token.py

python - <<'PY'
import ast
tree = ast.parse(open('plugins/module_utils/token.py').read())
bad = []
for n in ast.walk(tree):
    if isinstance(n, ast.Import):
        bad += [a.name for a in n.names if a.name.split('.')[0] in ('ansible', 'gql', 'graphql', 'requests', 'jwt')]
    if isinstance(n, ast.ImportFrom) and n.module:
        if n.module.split('.')[0] in ('ansible', 'gql', 'graphql', 'requests', 'jwt'):
            bad.append(n.module)
assert not bad, f"forbidden imports: {bad}"
print("OK: stdlib only")
PY
```

## Review focus

- Is the skew boundary correct and tested exactly at the edge, not just
  "well before" / "well after"?
- Does `token_is_valid` genuinely never raise, for every malformed case in
  the test list?
- No token value leaks into any exception message.
- No accidental signature verification creeping in (e.g. via a stray `jwt`
  import that happens to be available in the test venv).

## Commit

```
feat(v3): add JWT expiry inspection for cached tokens

Decodes the JWT payload segment to read the exp claim with a 60s skew
margin, deliberately without signature verification -- the collection
is the bearer, not the verifier; the API validates server-side.

Applies only to tokens the collection itself cached after an SSH
grant. Explicit lagoon_api_token / LAGOON_API_TOKEN values are used
as supplied and never pass through this validation, per plan 7.2
step 1-2 vs step 3.

Refs docs/plans/v3-refactor.md Phase 2, 7.2
```

---

# P2-S2 — `module_utils/ssh.py` — SSH grant + secure key handling

## Goal

Fetch a short-lived Lagoon API token via SSH `grant`, fixing the **Critical**
key-handling defect inherited from v1 and turning on host key verification by
default.

## Context

This story replaces `api/plugins/module_utils/token.py` (42 LOC) and the
SSH-invocation half of `api/plugins/action/fetch_token.py`. Two v1 defects,
already flagged in parent plan §7.2 and §11, are fixed here:

> **v1 finding — Critical.** `write_ssh_key()` writes the private key to the
> predictable path `/tmp/lagoon_ssh_private_key`, then `chmod`s it *after*
> writing. On a shared host this is exploitable via symlink pre-creation, or
> by reading the key in the brief window before `chmod` (mode depends on
> process umask until then).

> **v1 finding.** `api/roles/token/tasks/main.yml` passes
> `-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null` unconditionally.
> A MITM on the grant channel can hand back an attacker-controlled bearer
> token, silently, for the whole play.

This is the security-critical story of Phase 2 (see the note at the top of
this document about routing it through the `security` agent as well as
`review`).

## Files to create

```
plugins/module_utils/ssh.py
tests/unit/plugins/module_utils/test_ssh.py
```

## Design

```python
def request_grant(ssh_host, ssh_port, *, private_key=None,
                   private_key_file=None, ssh_options=None,
                   strict_host_key_checking='accept-new',
                   known_hosts_file=None, timeout=30, ssh_user='lagoon'):
    """Run `ssh ... lagoon@<host> grant` and return (access_token,
    expires_in). Raises LagoonAuthError on any failure.

    Exactly one of private_key / private_key_file should be supplied by
    the caller (auth.py enforces this); private_key content is written
    to a securely-created temporary file for the duration of the call
    and removed afterwards. private_key_file, if given directly, is
    used in place and is never copied.
    """
```

### Security requirements — each one is a review checkpoint

| # | Requirement | Fixes |
| - | ----------- | ---- |
| 1 | Temp dir via `tempfile.mkdtemp()` (mode `0700`), never a fixed/predictable path | v1's `/tmp/lagoon_ssh_private_key` |
| 2 | Key file created with `os.open(path, os.O_WRONLY \| os.O_CREAT \| os.O_EXCL, 0o600)`, written, then closed — mode is correct from the instant the file exists; `O_EXCL` makes the call fail outright if the path already exists (it shouldn't, given `mkdtemp`, but the atomicity is the point) | v1's write-then-`chmod` race |
| 3 | `try`/`finally`: `shutil.rmtree(tmp_dir, ignore_errors=True)` runs on **every** exit path, including exceptions | v1 never cleaned up |
| 4 | When the caller passes `private_key_file` directly (no `private_key` content), that path is used as-is and never copied into a temp file | avoids gratuitously duplicating a credential on disk |
| 5 | `subprocess.run(argv_list, ...)` — a list, never `shell=True`, never a shell string | command injection via `ssh_options` |
| 6 | String `ssh_options` parsed with `shlex.split()`; list `ssh_options` passed through unchanged | v1's naive `.split()` mishandles quoting |
| 7 | `strict_host_key_checking` defaults to `'accept-new'`; `'no'` is accepted but only with an explicit, documented opt-in, and callers passing it get a warning surfaced (return it as part of the raised context so `auth.py`/module code can log it, or accept a `warn` callback — implementer's choice, document whichever) | P2-D4 / the MITM-on-every-run defect |
| 8 | `-o ConnectTimeout=<n>` passed to `ssh` **and** `subprocess.run(timeout=...)` set — both belt and suspenders, since a hung TCP handshake and a hung SSH negotiation fail differently | ssh can hang indefinitely otherwise |
| 9 | Key content never appears in any exception, log line, or `repr()` | ISM-1402 |
| 10 | stderr captured and truncated (e.g. 500 chars) into the `LagoonAuthError` message; never `print()`ed — v1 does `print(e.stderr)` | keeps failure detail out of stdout / audit-adjacent streams and bounds message size |

### Error handling

All failure modes raise `LagoonAuthError` with a distinguishing message:

- `ssh` binary not found (`FileNotFoundError`) → "ssh executable not found".
- Non-zero exit code → include truncated stderr.
- `subprocess.TimeoutExpired` → "SSH grant timed out after Ns".
- Grant succeeded (rc 0) but stdout is not valid JSON → "unexpected grant response".
- Grant JSON is valid but missing `access_token` or `expires_in` → "malformed grant response".

### `known_hosts_file`

When supplied, pass `-o UserKnownHostsFile=<path>`. When `None`, let `ssh` use
its default (the user's own `~/.ssh/known_hosts`) — do **not** default to
`/dev/null` as v1 did; that is precisely the behaviour being reversed.

## Testing requirements

Mock `subprocess.run` throughout — no real `ssh` invocation, no network.

1. Assert the exact `argv` list passed to `subprocess.run` for a representative
   call, including `-p <port>`, `-o StrictHostKeyChecking=accept-new`,
   `-o ConnectTimeout=<timeout>`, `-i <key_path>`, `lagoon@<host>`, `grant`.
2. Assert `shell` is never passed / is falsy.
3. Assert the temp directory created has mode `0700` (`stat.S_IMODE`).
4. Assert the key file has mode `0600` immediately (mock `os.open`/`os.write`
   or use a real `tempfile.mkdtemp()` + real file and `os.stat` it — prefer
   the latter, it tests the real permission bits rather than asserting on a
   mocked call).
5. Assert `O_EXCL` semantics: pre-create the target path and confirm a
   `FileExistsError`-derived failure surfaces as `LagoonAuthError`, not an
   unhandled traceback.
6. Assert `shutil.rmtree` (or direct filesystem check) confirms the temp dir
   is gone after both a successful call and one that raises partway through.
7. String `ssh_options` with a quoted argument (`'-o "Foo Bar=baz"'`) parses
   via `shlex.split` correctly; list `ssh_options` passed through unchanged.
8. `strict_host_key_checking='no'` still functions, but assert it appears in
   the argv only when explicitly requested — never as an implicit default.
9. Timeout: mock `subprocess.run` to raise `subprocess.TimeoutExpired` →
   `LagoonAuthError` mentioning the timeout value.
10. Non-zero rc → `LagoonAuthError` containing (truncated) stderr, not the
    full private key content if it were ever (hypothetically) echoed by a
    misbehaving `ssh` — assert the key content string is absent from the
    raised message regardless.
11. Malformed / missing-field JSON stdout → distinct `LagoonAuthError`
    messages per case.
12. `private_key_file` passed directly → no temp file created at all (assert
    `tempfile.mkdtemp` not called, or that no new file appears).

## Acceptance criteria

- [ ] All ten security requirements in the table verified by a specific test,
      not just implemented.
- [ ] `grep -n "/tmp" plugins/module_utils/ssh.py` — no match.
- [ ] `grep -n "shell=True" plugins/module_utils/ssh.py` — no match.
- [ ] `grep -n "print(" plugins/module_utils/ssh.py` — no match.
- [ ] Default `strict_host_key_checking` is `'accept-new'`, not `'no'`.
- [ ] Key content absent from every raised exception's `str()`.
- [ ] `ssh.py` raises only `LagoonAuthError` — no bare `Exception`, no
      `AnsibleError`.

## Verification commands

```sh
docker compose run --rm test-v3 units -v --requirements \
  tests/unit/plugins/module_utils/test_ssh.py

grep -n "/tmp\b" plugins/module_utils/ssh.py && echo "FAIL: hardcoded /tmp" || echo "OK"
grep -n "shell=True" plugins/module_utils/ssh.py && echo "FAIL: shell=True" || echo "OK"
grep -n "StrictHostKeyChecking=no" plugins/module_utils/ssh.py | grep -v "accept-new" \
  && echo "review: confirm this path requires explicit opt-in" || echo "OK"

python - <<'PY'
import ast
tree = ast.parse(open('plugins/module_utils/ssh.py').read())
bad = []
for n in ast.walk(tree):
    if isinstance(n, ast.Import):
        bad += [a.name for a in n.names if a.name.split('.')[0] in ('ansible', 'gql', 'graphql', 'requests')]
    if isinstance(n, ast.ImportFrom) and n.module:
        if n.module.split('.')[0] in ('ansible', 'gql', 'graphql', 'requests'):
            bad.append(n.module)
        if n.module == 'ansible.errors':
            bad.append(n.module)
assert not bad, f"forbidden imports: {bad}"
print("OK")
PY
```

## Review focus

- **This is the story fixing a Critical finding. Verify by reading the code,
  not by trusting the test names.** Specifically: is the key file mode
  `0600` from the instant it exists (no window), and is `O_EXCL` actually
  used (not just documented as intended)?
- Does cleanup run on *every* exit path, including an exception raised by
  `subprocess.run` itself, not just the success path?
- Is `shell=True` genuinely absent, and is `ssh_options` parsing injection-safe
  even with adversarial input (e.g. `ssh_options="; rm -rf /"` as a string)?
- Is the host-key-checking default genuinely `accept-new`, and does choosing
  `no` require an explicit, deliberate action by the caller?
- Does any error path (stderr capture, JSON parse failure) risk echoing key
  material back into a message?

## Commit

```
fix(v3): add secure SSH grant with host key verification on by default

Replaces v1's fetch_token/token.py, which wrote the private key to the
predictable path /tmp/lagoon_ssh_private_key and chmod'd it after
writing -- leaving it briefly world-readable per the process umask and
exploitable via symlink pre-creation on a shared host. v3 uses
mkdtemp(0700) plus O_EXCL|0600 at creation time, and removes the key
in a finally block on every exit path.

Also reverses v1's token role default of
StrictHostKeyChecking=no + UserKnownHostsFile=/dev/null, which allowed
a MITM on the grant channel to supply an attacker-controlled bearer
token for the whole play. v3 defaults to StrictHostKeyChecking=
accept-new; disabling verification now requires an explicit opt-in.

Refs docs/plans/v3-refactor.md Phase 2, 7.2, 11 (Critical finding)
```

---

# P2-S3 — `module_utils/auth.py` — resolver + in-memory cache

## Goal

The single token-resolution entrypoint every module and the action shim call:
param → env → validated in-memory cache → SSH grant, per parent plan §7.2's
resolution order.

## Context

This is where P2-S1 (validity) and P2-S2 (grant) compose. It also defines
`auth_argument_spec()` — the canonical argspec for auth-related module
options (P2-D6) — which P2-S5's doc fragment is checked against.

## Files to create

```
plugins/module_utils/auth.py
tests/unit/plugins/module_utils/test_auth.py
```

## Design

```python
def auth_argument_spec(spec=None):
    """Canonical argspec fragment for auth options, merged with an
    optional caller-supplied spec dict (caller keys win on conflict)."""

def resolve_token(config):
    """config is a plain dict with (at least): endpoint, token (explicit,
    may be None), ssh_host, ssh_port, ssh_user, private_key,
    private_key_file, ssh_options, strict_host_key_checking,
    known_hosts_file. Returns a bearer token string. Raises
    LagoonConfigError if nothing usable is configured, LagoonAuthError
    if the SSH grant itself fails.

    Resolution order (plan 7.2):
      1. config['token'] (explicit lagoon_api_token) -> used as-is.
      2. LAGOON_API_TOKEN env var -> used as-is.
      3. In-memory cache entry for this config's cache_key(), if
         token_is_valid() -> used.
      4. ssh.request_grant(...) -> cache the result -> use it.
    """

def cache_key(config):
    """sha256 hex digest over (endpoint, ssh_host, ssh_port, ssh_user,
    sha256(key_material)) so two distinct identities never collide and
    raw key material never appears in the key itself. key_material is
    the private key content if given, else the private_key_file path
    (not its content -- the file is not read here)."""

def clear_cache():
    """Test seam: empties the module-level cache dict."""
```

### Implementation notes

- The in-memory cache is a plain module-level `dict`, `{cache_key: (token,
  expires_hint)}` or simply `{cache_key: token}` if `token_is_valid` alone is
  sufficient (prefer the simpler shape unless a test proves it insufficient).
- **Document the process-boundary limitation explicitly** (P2-D2): this cache
  is only useful in a context that survives across multiple `execute()`
  calls within the same process — i.e. inside the action shim, across
  `loop:` iterations of one task. A module executing on a managed node via
  AnsiballZ is a fresh interpreter every invocation, so `resolve_token`
  called from *inside* a module (the no-shim fallback path) will never get a
  cache hit across tasks. This asymmetry is why the shim (P2-S6) exists at
  all — say so in the module docstring, not just in this story doc.
- `auth_argument_spec()` must mark `lagoon_api_token` and
  `lagoon_ssh_private_key` with `no_log=True`, and give `validate_certs` a
  default of `True`.
- **Note for the P2-S6/S7 implementer:** `client.py::_fetch_url_call`
  reaches into `module.params['validate_certs']`. Any module using
  `LagoonClient` with a module instance must declare `validate_certs` in its
  own argspec (via this fragment) or the client synthesises the key at
  runtime and it never appears in `ansible-doc` output. Flag this loudly in
  the module template when Phase 3 arrives; for now just make sure
  `auth_argument_spec()` includes it.
- Raise `LagoonConfigError` (not `LagoonAuthError`) when the config has
  neither an explicit token, nor `LAGOON_API_TOKEN`, nor enough to attempt an
  SSH grant (missing `ssh_host` and no cached entry) — this is a caller
  configuration problem, not an auth failure.

## Testing requirements

1. Each resolution step in isolation: explicit token short-circuits
   everything (assert `ssh.request_grant` never called); env var same;
   valid cache entry same; all three absent → grant called exactly once and
   result cached.
2. Cache hit avoids a second grant on a second `resolve_token()` call with
   the same config.
3. An **expired** cache entry (mock `token_is_valid` → `False`) triggers a
   fresh grant, and the new token replaces the stale entry.
4. Two configs differing only in `endpoint` produce two independent cache
   entries (assert both are retrievable and don't clobber each other).
5. `clear_cache()` actually empties state between tests — add a test that
   would fail without it (grant-call-count assertion across two "isolated"
   calls) to prove the seam works, not just that it exists.
6. `cache_key()` never contains the raw key material as a substring of its
   own output.
7. Missing everything → `LagoonConfigError`, not `LagoonAuthError`.
8. Token value absent from every raised exception's `str()`.

## Acceptance criteria

- [ ] Resolution order matches plan §7.2 exactly: param → env → cache →
      grant.
- [ ] `auth_argument_spec()` sets `no_log=True` on both secret-bearing
      options and `validate_certs` default `True`.
- [ ] In-memory cache is module-level state, explicitly documented as
      process-scoped (not play-scoped) with the reasoning in P2-D2.
- [ ] `clear_cache()` exists and is proven to work by a test.
- [ ] No `ansible.errors` import (this file, like all `module_utils`, never
      imports it).

## Verification commands

```sh
docker compose run --rm test-v3 units -v --requirements \
  tests/unit/plugins/module_utils/test_auth.py

python - <<'PY'
import ast
tree = ast.parse(open('plugins/module_utils/auth.py').read())
bad = [n.module for n in ast.walk(tree)
       if isinstance(n, ast.ImportFrom) and n.module and
       (n.module.split('.')[0] in ('gql', 'graphql', 'requests') or n.module == 'ansible.errors')]
assert not bad, f"forbidden imports: {bad}"
print("OK")
PY
```

## Review focus

- Is the process-scope limitation of the in-memory cache documented clearly
  enough that a Phase 6/7 implementer won't assume play-wide reuse?
- Does an expired cache entry actually trigger re-grant, or does a bug let a
  stale token slip through?
- `validate_certs` default really `True` here too (it must agree with
  `client.py`'s default — check they don't silently diverge).

## Commit

```
feat(v3): add token resolution with process-scoped in-memory caching

Implements the param -> env -> cache -> SSH-grant resolution order
from plan 7.2, composing the JWT validity check (P2-S1) and secure
SSH grant (P2-S2).

The in-memory cache is scoped to one worker process, i.e. one task --
not one play, correcting plan 4's "one grant per play" claim (see
Phase 2 decisions P2-D2 in docs/plans/v3-phase2-stories.md). It still
collapses N SSH grants into one for loop: iterations over a single
task, which is where Lagoon's N+1 pattern bites hardest in practice.

Refs docs/plans/v3-refactor.md Phase 2, 7.2
```

---

# P2-S4 — `module_utils/cache.py` — opt-in cross-process file cache

## Goal

An optional, off-by-default file-backed token cache for operators who need
grant reuse across tasks within a play (or across separate `ansible-playbook`
runs), without the credential-at-rest posture the parent plan's §7.2 design
would have had by default.

## Context

The in-memory cache in P2-S3 cannot survive across the process fork boundary
between tasks (P2-D2). Some users genuinely need cross-task reuse — a 50-task
play with one Lagoon token is the common case in practice. This story gives
them that, deliberately opt-in, with a materially different security posture
to the always-on in-memory cache: this is the one place in the whole
collection where a bearer token touches disk.

## Files to create

```
plugins/module_utils/cache.py
tests/unit/plugins/module_utils/test_cache.py
```

## Design

```python
def cache_dir():
    """$XDG_CACHE_HOME/ansible-lagoon or ~/.cache/ansible-lagoon.
    Created with mode 0700 if absent (parents too)."""

def read_cached_token(key):
    """Returns the cached token string, or None if absent, unreadable,
    wrong-owned, wrong-moded, malformed, or expired (via token.py's
    token_is_valid). Never raises for a missing/bad cache file --
    a cache miss is not an error."""

def write_cached_token(key, token):
    """Atomically writes {key}.json to cache_dir() at mode 0600."""
```

### Implementation notes

- **Off by default, no exceptions.** `auth.py`'s resolver only calls into
  this module when the caller's config sets `lagoon_token_cache: true`. When
  disabled, **zero filesystem activity** — no directory created, nothing
  probed. Test this directly (mock the filesystem calls and assert zero
  invocations when disabled).
- Directory: `$XDG_CACHE_HOME/ansible-lagoon/` if `XDG_CACHE_HOME` is set,
  else `~/.cache/ansible-lagoon/`. **Never `/tmp`** — a stable, predictable
  path under the home directory is not equivalent to a predictable path
  under a world-writable directory (the home dir isn't world-writable, so
  the symlink pre-creation attack this collection exists to avoid doesn't
  apply the same way), but state the reasoning in the module docstring so a
  future reviewer doesn't flag it as the same defect by pattern-matching on
  "predictable path".
- Directory mode `0700` (`os.makedirs(path, mode=0o700, exist_ok=True)` plus
  an explicit `os.chmod` afterward, since `makedirs`'s `mode` is
  umask-affected on some platforms — don't rely on it alone).
- File name: `token-<cache_key>.json` where `cache_key` is the same value
  `auth.cache_key()` produces (imported, not recomputed).
- **Atomic write:** `tempfile.mkstemp(dir=cache_dir())` (inherits the
  directory's restrictive default), `os.fchmod(fd, 0o600)` explicitly before
  writing (don't assume `mkstemp`'s default mode is 0600 on every platform —
  verify and set it), write, `os.close`, then `os.replace(tmp_path,
  final_path)`. No partial-write window, no TOCTOU gap.
- **Paranoid read path.** Before trusting file contents: `os.stat()` the
  path and refuse (treat as cache miss, do **not** attempt to "fix" the
  file) if:
  - `st_uid != os.geteuid()` (not owned by the current user), or
  - `st_mode & 0o077` (group or other has any permission bit set).

  This is a deliberate "refuse, don't repair" policy — a wrongly-permissioned
  credential file is a signal that something else has touched it, and
  silently `chmod`-ing it away would erase that signal.
- **No `finally`-block deletion.** This is a considered deviation from a
  literal reading of parent plan §7.2's "remove key and token files in a
  finally block" — that requirement makes sense for the *SSH key* (P2-S2,
  which does delete in `finally`) but not for this *cross-process* cache: if
  the worker that wrote it deletes it on exit, no later task/process ever
  benefits, defeating the feature's purpose. Instead, entries age out
  naturally via `token_is_valid()`'s `exp` check on read. Document this
  explicitly — don't let a future contributor "fix" it by adding cleanup
  that reintroduces the single-use bug.
- Reject any `key` containing `/`, `\`, or `..` before building a path from
  it (defence in depth even though `cache_key()` only ever produces a hex
  digest).

## Testing requirements

1. Disabled path: with the feature flag off, no call into this module
   happens at all — this is really an `auth.py`-side test, but add a
   same-module test asserting `read_cached_token`/`write_cached_token` are
   simply not exercised in that configuration (can be a light integration
   test against `auth.resolve_token` with mocked `cache` functions asserting
   zero calls).
2. `cache_dir()` created at `0700`; assert via `os.stat`.
3. Written file has mode `0600`; assert via `os.stat`, not by trusting the
   code path.
4. Atomicity: patch `os.replace` to raise partway and assert no partial file
   is left behind under the final name (the temp file may remain — that's
   acceptable and expected; assert the *final* path is untouched).
5. Read refuses a file owned by a different uid (mock `os.stat` to report a
   foreign `st_uid`) — assert cache-miss behaviour (`None`), not an
   exception.
6. Read refuses a group/other-readable file (mock `st_mode` with `0o640`) —
   same, cache-miss.
7. Expired entry (valid ownership/mode, but `token_is_valid` → `False`) is
   treated as a miss.
8. Path traversal: `cache_key` containing `../../etc/passwd`-shaped input is
   rejected before any filesystem operation (raise `LagoonConfigError` or
   treat as a miss — pick one, document it, test it).
9. Round-trip: write then read on a real `tempfile.TemporaryDirectory()`
   (not mocked) returns the same token, proving the atomic-write/read pair
   actually works end to end, not just per-mock.

## Acceptance criteria

- [ ] Disabled by default; zero filesystem writes when not opted in.
- [ ] Directory `0700`, file `0600`, verified by `os.stat` in tests, not by
      code inspection alone.
- [ ] Atomic write via `mkstemp` + `os.replace`.
- [ ] Read path refuses foreign-owned or over-permissive files as a cache
      miss, never an exception, never a silent `chmod`.
- [ ] No `finally`-block deletion of the cross-process cache file; the
      deviation from a literal §7.2 reading is documented in the module
      docstring and the commit body.
- [ ] `/tmp` does not appear anywhere in the file.
- [ ] Path-traversal-shaped keys rejected.

## Verification commands

```sh
docker compose run --rm test-v3 units -v --requirements \
  tests/unit/plugins/module_utils/test_cache.py

grep -n "/tmp\b" plugins/module_utils/cache.py && echo "FAIL" || echo "OK"

python - <<'PY'
import ast
tree = ast.parse(open('plugins/module_utils/cache.py').read())
bad = [n.module for n in ast.walk(tree)
       if isinstance(n, ast.ImportFrom) and n.module and
       (n.module.split('.')[0] in ('gql', 'graphql', 'requests') or n.module == 'ansible.errors')]
assert not bad, f"forbidden imports: {bad}"
print("OK")
PY
```

## Review focus

- Is "disabled by default, zero filesystem activity" actually true, or does
  `cache_dir()` get created eagerly regardless of the flag?
- Is the permission check on read genuinely enforced (test with a real mode
  mismatch, not just asserted)?
- Is the "no finally cleanup" deviation clearly justified and documented, or
  does it read like an oversight? This is the one place a reviewer might
  reasonably push back — make sure the reasoning is on the page, not just in
  this story doc.
- XDG path resolution correct on a box with `XDG_CACHE_HOME` unset.

## Commit

```
feat(v3): add opt-in cross-process token cache

Off by default. When enabled via lagoon_token_cache: true, tokens
persist under $XDG_CACHE_HOME/ansible-lagoon (falling back to
~/.cache/ansible-lagoon), directory 0700, file 0600, written
atomically via mkstemp + os.replace. Reads refuse foreign-owned or
over-permissive files as a cache miss rather than repairing them.

Deliberately does not delete the cache file in a finally block, unlike
the SSH key handling in P2-S2 -- a cross-process cache that the first
worker deletes on exit never serves a second task, which defeats the
purpose. Entries age out via the token's own exp claim instead.

This is the only place in the collection where a bearer token touches
disk; it is off by default for that reason.

Refs docs/plans/v3-refactor.md Phase 2, 7.2
```

---

# P2-S5 — `doc_fragments/auth.py` + argspec drift test

## Goal

A documented, shared auth options fragment for `extends_documentation_fragment`,
mechanically bound to `auth_argument_spec()` so the two cannot silently
diverge once Phase 3 starts generating modules against both.

## Context

The real content of this story is the drift test, not the YAML — Phase 1's
retrospective note on P1-S3/S4 established that load-bearing but easy-to-get-
wrong pieces get their own story; this is the doc-parity equivalent.

## Files to create

```
plugins/doc_fragments/auth.py
tests/unit/plugins/module_utils/test_auth_docs.py
```

## Implementation notes

### `plugins/doc_fragments/auth.py`

Model on v1's `api/plugins/doc_fragments/auth_options.py` but cover the full
v3 option set: `lagoon_api_endpoint`, `lagoon_api_token`, `validate_certs`,
plus the SSH-grant-path options (`lagoon_ssh_host`, `lagoon_ssh_port`,
`lagoon_ssh_user`, `lagoon_ssh_private_key`, `lagoon_ssh_options`,
`lagoon_ssh_strict_host_key_checking`) and the two cache flags
(`lagoon_token_cache`, `lagoon_token_cache_dir` if exposed).

Must include, as prose in the relevant option descriptions:

- the `LAGOON_API_TOKEN` environment variable fallback;
- an explicit warning that a long-lived token is the exceptional path —
  short-lived SSH-grant tokens are strongly preferred; if a long-lived token
  must be used, store it in Ansible Vault and rotate on a 12-month cycle
  (parent plan §7.2);
- an explicit warning on `lagoon_ssh_strict_host_key_checking: no` that
  disabling host key verification permits a MITM to supply an
  attacker-controlled token.

### The drift test

`test_auth_docs.py` parses the fragment's `DOCUMENTATION` block with
`yaml.safe_load` and compares it against `auth_argument_spec()`:

1. Same set of option names in both directions (fragment has none the
   argspec doesn't, and vice versa).
2. `type` agrees for every shared option.
3. `default` agrees where the argspec declares one.
4. Every option with `no_log=True` in the argspec is marked
   `no_log: true` in the fragment (add this to the fragment's schema even
   though `antsibull-docs` doesn't strictly require it — belt and suspenders
   given what these options carry).
5. Every documented option has a non-empty `description`.

## Acceptance criteria

- [ ] Fragment covers every `auth_argument_spec()` key.
- [ ] Drift test fails if a key is added to one side and not the other —
      prove this by temporarily breaking parity locally while writing the
      test (not committed, just to convince yourself the test bites).
- [ ] Long-lived-token warning and host-key-checking warning both present in
      the fragment text.
- [ ] `docker compose run --rm lint-docs-v3` passes.

## Verification commands

```sh
docker compose run --rm test-v3 units -v --requirements \
  tests/unit/plugins/module_utils/test_auth_docs.py
docker compose run --rm lint-docs-v3
```

## Review focus

- Does the drift test actually parse the fragment's YAML and compare
  structurally, or does it just check for substring presence (which would
  pass vacuously)?
- Are both required warnings present and clearly worded, not buried?

## Commit

```
feat(v3): add shared auth doc fragment with an argspec drift test

extends_documentation_fragment target for the auth options resolved
by module_utils/auth.py. A test parses the fragment's DOCUMENTATION
against auth_argument_spec() so the two declarations of the same
option set cannot silently diverge once Phase 3 generates modules
against both.

Refs docs/plans/v3-refactor.md Phase 2, 7.2
```

---

# P2-S6 — `LagoonActionShim` in `plugins/action/__init__.py`

## Goal

The shared controller-side base class that resolves/injects a token before
delegating to the real module — and nothing else. Name→id lookup injection is
explicitly **not** part of this story (that's Phase 4).

## Context

Parent plan §4 draws the boundary precisely: the module holds 100% of the
business logic; the shim does only token handling (this story) and, later,
lookup resolution (Phase 4). Corrected per P2-D3, the shim is **not** a single
plugin registered collection-wide — it is a base class, and every generated
module gets its own one-line subclass file under `plugins/action/`.

## Files to create

```
plugins/action/__init__.py
tests/unit/plugins/action/__init__.py
tests/unit/plugins/action/test_shim.py
```

## Design

```python
class LagoonActionShim(ActionBase):

    def run(self, tmp=None, task_vars=None):
        task_vars = task_vars or {}
        result = super().run(tmp, task_vars)
        del tmp

        try:
            config = self._build_auth_config(task_vars)
            token = auth.resolve_token(config)
        except LagoonError as e:
            raise AnsibleError(str(e))

        module_args = dict(self._task.args)
        module_args['lagoon_api_token'] = token
        module_args.setdefault(
            'lagoon_api_endpoint', config['endpoint'])

        result.update(self._execute_module(
            module_name=self._task.action,
            module_args=module_args,
            task_vars=task_vars))
        return result
```

(Illustrative — implementer should match the codebase's actual `ActionBase`
conventions, e.g. v1's `createClient` precedence pattern in
`api/plugins/action/__init__.py`, but rebuilt on `module_utils.auth` instead
of the `gql`-based client.)

### Requirements

- **Zero resource-specific logic.** No knowledge of any module's argspec
  beyond the auth-related keys it injects. If a reviewer can point at a
  line that only makes sense for one particular module, that line doesn't
  belong here.
- **Config precedence:** explicit task args (`lagoon_api_token:` set directly
  on the task) → `task_vars` (`lagoon_api_endpoint`, `lagoon_ssh_host`, etc. —
  the v1-compatible `set_fact`/`vars:` pattern) → environment (handled inside
  `auth.resolve_token` itself, not here) → module defaults. Task args arrive
  already templated by Ansible; values pulled from `task_vars` must go
  through `self._templar.template(...)` before use, matching v1's
  `createClient` convention.
- **This file is the only place in the collection permitted to import
  `ansible.errors`.** `module_utils` never does (enforced by the same
  AST-import tests as every other story). The shim's entire purpose is to be
  the seam where `LagoonError` becomes `AnsibleError`.
- The token must not appear in the `AnsibleError` message the shim raises —
  `LagoonError.__str__` already guarantees this for the exceptions it wraps;
  don't undo that guarantee by building a new message that includes
  `config['token']` or similar.
- Delegate via `self._execute_module(...)`, defaulting `module_name` to
  `self._task.action` so subclasses genuinely need only one line (see
  P2-S7's `whoami_info` shim for the reference example).
- Inject **only** the auth-related keys (`lagoon_api_token`,
  `lagoon_api_endpoint`, and `validate_certs` if resolved centrally). Never
  touch any other key in `self._task.args` — copy, don't mutate in place, so
  a mistake here can't leak into the caller's original dict.
- Do not interfere with check mode. `self._task.check_mode` flows through to
  `_execute_module` as normal Ansible behaviour; the shim has no check-mode
  logic of its own.

### The §4 boundary, made testable

A module invoked directly with an explicit `lagoon_api_token` module
parameter, and *no* shim involved, must be fully functional. P2-S7's
`whoami_info` unit tests must pass with the shim entirely absent from the
test — that's how this story's boundary claim gets proven, not asserted.

## Testing requirements

Construct `LagoonActionShim` with mocked `task`, `connection`, `play_context`,
`loader`, `templar`, and `shared_loader_obj` (standard `ActionBase` test
scaffolding — check whether `ansible-core`'s own test suite or `amazon.aws`
has a reusable fixture pattern worth borrowing). Mock `_execute_module`.

1. Token resolved and injected as `lagoon_api_token` in the args passed to
   `_execute_module`.
2. All other task args pass through to `_execute_module` byte-identical to
   what was on the task (assert dict equality apart from the injected keys).
3. `task_vars`-sourced config values (e.g. `lagoon_ssh_host`) are templated
   via `self._templar.template()` before being used — assert the mock
   templar was called, not that the raw `{{ }}` string leaked through.
4. Task-arg-level `lagoon_api_token` takes precedence over anything in
   `task_vars`.
5. A `LagoonError` raised by `auth.resolve_token` is caught and re-raised as
   `AnsibleError`; `_execute_module` is **not called** in that case (assert
   call count zero).
6. The `AnsibleError` message does not contain any token value used in the
   test setup.
7. `_task.action` is used as the default `module_name` when the subclass
   doesn't override it.

## Acceptance criteria

- [ ] `ansible.errors` imported here and nowhere else in `plugins/` outside
      `plugins/action/` — grep-checked.
- [ ] No resource-specific logic (reviewer's judgement call, but the story
      exists precisely so this gets checked).
- [ ] Auth failure never reaches `_execute_module`.
- [ ] Only auth-related keys injected; everything else passed through
      unmodified.
- [ ] Token absent from any `AnsibleError` raised.

## Verification commands

```sh
docker compose run --rm test-v3 units -v --requirements \
  tests/unit/plugins/action/test_shim.py

grep -rln "ansible.errors" plugins/ | grep -v '^plugins/action/' \
  && echo "FAIL: ansible.errors imported outside plugins/action" || echo "OK"
```

## Review focus

- Is the boundary from §4 actually held, or has resource-specific logic
  crept in because it was "just easier here"?
- Precedence order — does an explicit task arg really win over `task_vars`?
- Does a resolution failure genuinely short-circuit before
  `_execute_module`, or could a partially-built `module_args` dict leak
  through on an error path?

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
```

---

# P2-S7 — `whoami_info` walking skeleton + sweep extension + `graphql-mock-v3`

## Goal

Prove endpoint → auth → shim → module → client end to end against a real
GraphQL server serving the actual vendored schema, before the Phase 3
generator is built — and fix the P1-S5 guardrail regression that a correctly
written module triggers.

## Context

Two things collide in this story and both must be resolved, not worked
around:

1. **§12.3** ("do `*_info` modules need the action shim?") is answered here:
   yes — an `_info` module needs a token exactly like any other module, and
   without the shim every `_info` task would trigger its own SSH grant.
2. **P1-S5's vacuous-pass guard fires on this module by design**, and that is
   the point of building it now rather than waiting for Phase 3. A module
   built the *right* way — via `LagoonClient.build_query(...)` — contains no
   GraphQL string literal for the AST sweep to find. The guard must be taught
   to reconstruct documents from `build_query()` call sites, not relaxed.

## Files to create

```
plugins/modules/whoami_info.py
plugins/action/whoami_info.py
tests/unit/plugins/modules/__init__.py
tests/unit/plugins/modules/test_whoami_info.py
.docker/Dockerfile.graphql-mock-v3
.docker/graphql-mock/package-lock.json
```

## Files to modify

```
tests/unit/plugins/module_utils/query_depth.py
tests/unit/plugins/module_utils/test_query_depth.py
meta/runtime.yml
docker-compose.yml
Makefile
```

## Part 1 — the module

### `plugins/modules/whoami_info.py`

- Query: `LagoonClient.build_query('me', fields=['id', 'email', 'firstName',
  'lastName', 'created', 'lastAccessed', 'has2faEnabled'])`.
  **Deliberately drops `groups`** from v1's equivalent — a nested `groups {
  name type }` selection is forbidden under the REST-semantics rule
  (parent plan D3/§7.1). Record this as a breaking change for Phase 8's
  migration table (parent plan §10).
- `supports_check_mode = True`; always `changed=False` (read-only info
  module, matching parent plan D5's `*_info` naming convention).
- If the API returns `me: null` (e.g. an invalid/expired token that somehow
  passed the shim, or a token with insufficient scope), raise
  `LagoonNotFoundError('user', query='me')` and let the module's own
  exception handling convert it to `fail_json`.
- Returns a single `user` key with the flat field dict.
- Full `DOCUMENTATION`, `EXAMPLES`, `RETURN`;
  `extends_documentation_fragment: salsadigitalauorg.lagoon.auth`.
- **Use fully-qualified absolute imports**, e.g.:
  ```python
  from ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.client import LagoonClient
  ```
  Relative imports (the `.....plugins.module_utils` style used in this
  repo's *test* files) work under bare pytest but **not** under AnsiballZ,
  which only resolves the fully-qualified collection path. This is worth
  getting right the first time — it is exactly the kind of thing that looks
  fine in unit tests and then fails only when actually run as a module.

### `plugins/action/whoami_info.py`

One-line subclass, the reference template for what the Phase 3 generator
will emit per P2-D3:

```python
from ansible.plugins.action import LagoonActionShim


class ActionModule(LagoonActionShim):
    pass
```

(Adjust the import path to match wherever `__init__.py` actually lives —
`ansible_collections.salsadigitalauorg.lagoon.plugins.action`.)

### `meta/runtime.yml`

Add `action_groups: {all: [whoami_info]}` — for `module_defaults` grouping
convenience only, per P2-D3. State explicitly in the commit that this is
**not** what causes the shim to be invoked; the file
`plugins/action/whoami_info.py` existing is what does that.

### Unit tests — the §4 boundary proof

`test_whoami_info.py` must run the module's logic **directly, with no shim
involved** — construct/mock an `AnsibleModule`-equivalent with an explicit
`lagoon_api_token` already set, call into the module's main logic, and assert
correct behaviour purely from that. This is the concrete proof that "a module
invoked with an explicit token is fully functional standalone" (§4) holds,
not just an assertion in a docstring.

Cover: happy path returns the expected `user` dict with `changed=False`;
`me: null` → `fail_json` (or the equivalent exception path) via
`LagoonNotFoundError`; `check_mode=True` still executes the read (it's
read-only, there's nothing to skip) and returns the same shape.

## Part 2 — the sweep extension

### The collision, precisely

`whoami_info.py` contains the Python source text
`LagoonClient.build_query('me', fields=[...])` — a function *call*, not a
string literal containing `query me { ... }`. P1-S5's
`collect_candidate_documents()` walks `ast.Constant` string nodes and named
string assignments; it has nothing to match here. The moment this file lands
in `plugins/modules/`, P1-S5's own vacuous-pass guard
(`test_vacuous_pass_guard` in `test_query_depth.py`) fails — correctly,
because the sweep truly is finding zero candidates in a now-non-empty
`plugins/modules/`. This is the guard doing its job; the fix belongs in the
sweep, not in loosening the guard.

### Required change to `query_depth.py`

Extend `collect_candidate_documents()` to also recognise
`LagoonClient.build_query(...)` (and bare `build_query(...)`, in case of a
`from ... import build_query`-style call — check what Phase 3's templates
will actually emit and match that convention) call sites via `ast.Call`
matching:

1. Walk `ast.Call` nodes where the function name resolves to `build_query`
   (match on `.attr == 'build_query'` for the attribute form, and on
   `.id == 'build_query'` for the bare form).
2. Extract `operation` (first positional arg or `operation=` keyword),
   `fields`, `args`, `operation_type`, `operation_name` from keyword
   arguments **only when every one is an `ast.Constant` or a literal
   `list`/`dict` of `ast.Constant`s** — i.e. fully statically resolvable.
3. Where fully resolvable, call the real
   `LagoonClient.build_query(**resolved_kwargs)` to reconstruct the actual
   document string, and feed that through `assert_flat_query` exactly like
   any other candidate. This exercises the real implementation, not a
   reimplementation of its string-building logic.
4. Where **not** fully resolvable (e.g. `fields` built dynamically), still
   record it as a candidate — using a placeholder marker rather than a
   document — so it counts toward the non-vacuous-pass guard, but skip the
   depth assertion for that entry and instead assert-log (or otherwise
   surface) that it was skipped, so an unresolvable `build_query` call
   doesn't silently stop being checked at all. Add a code comment
   explaining why full static resolution isn't always possible.
5. Must **not** `import` `plugins.modules.whoami_info` or any other
   collection module — stay within the existing `ast`-only constraint from
   P1-S5. Reconstructing via `LagoonClient.build_query` directly (importing
   only `module_utils.client`, which has no `AnsibleModule` dependency) is
   fine; importing a *module* file is not.

### Required change to `test_query_depth.py`

- A new unit test constructing a small fixture file containing a
  `LagoonClient.build_query('x', fields=['a','b'])` call and asserting the
  extended `collect_candidate_documents` finds it and it passes
  `assert_flat_query`.
- A fixture with a `build_query` call whose `fields` argument is a nested
  list containing a value that would make the reconstructed document exceed
  depth 2 — this can't happen through `build_query`'s own field-name
  validation (it rejects `{` in field names), so instead prove the negative
  path a different way: a fixture with a call to something that *looks like*
  `build_query` but is actually a decoy (e.g. a local function of the same
  name that returns a deliberately nested string) — and confirm the checker
  still catches it once reconstructed. If this proves impractical, document
  precisely why and instead strengthen the assertion that unresolvable calls
  are surfaced rather than silently skipped.
- `test_vacuous_pass_guard` (already exists from P1-S5) must now **pass**
  against the real `plugins/` tree, because `whoami_info.py` makes
  `plugins/modules/` non-empty and the extended sweep genuinely finds a
  candidate in it. Confirm by running it, not by inspection.

## Part 3 — `graphql-mock-v3` (hard AC, per P2-D8)

### `.docker/Dockerfile.graphql-mock-v3`

```dockerfile
FROM node:lts

COPY .docker/graphql-mock/ /app/
COPY schema/lagoon-2.33.0.graphql /app/schema.graphql

WORKDIR /app

RUN npm ci

EXPOSE 4000

CMD ["npm", "start"]
```

(`npm ci` rather than `npm install`, since a lockfile now exists — deterministic
builds instead of drifting `^` resolution.)

### `.docker/graphql-mock/package-lock.json`

Generate with `npm install --package-lock-only` against the existing
`.docker/graphql-mock/package.json` (do not change the package.json itself —
both the v1 and v3 mock Dockerfiles share it). Commit the resulting lockfile.
This directly addresses the dependency-drift risk noted in P2-D8: the mock's
declared dependencies (`graphql-import@^1.0.2`, `graphql-tools@^9.0.1`, etc.)
are unpinned, and a hard AC that can silently break on an unrelated
`npm install` some weeks from now is not a hard AC worth having.

### `docker-compose.yml` addition

```yaml
  graphql-mock-v3:
    build:
      context: .
      dockerfile: .docker/Dockerfile.graphql-mock-v3
    command: ["npm", "start"]
    ports:
      - "4200:4000"
```

(Distinct host port from the v1 `graphql-mock` service so both can run
simultaneously during the migration period, per parent plan D18's
coexistence stance.)

### `Makefile` additions

```make
.PHONY: mock-up mock-down verify-mock

mock-up:
	docker compose up -d graphql-mock-v3

mock-down:
	docker compose down graphql-mock-v3

verify-mock:            ## Confirm the vendored SDL loads under the mock's graphql-import
	curl -sS -X POST http://localhost:4200/graphql \
	  -H 'Content-Type: application/json' \
	  -d '{"query":"{ lagoonVersion }"}' | tee /tmp/verify-mock.out
	grep -q '"lagoonVersion"' /tmp/verify-mock.out
```

### End-to-end proof

Either an `ansible-playbook` run against `graphql-mock-v3` (preferred — add
under `tests/integration/` even though Phase 5 is the formal home for
integration targets; a single ad hoc playbook here is acceptable scope
creep given this story's purpose) or a documented manual command sequence in
the commit body if a full integration target is too heavy for this story.
Either way, the run must exercise the **real** `whoami_info` module
end-to-end, i.e. through the actual action shim and SSH-less token path
(pass `lagoon_api_token` directly for this test — no real SSH host exists
in the mock setup), against the mock server, and show a `changed: false`
result with a mocked `user` object.

## Acceptance criteria

- [ ] `whoami_info` module and doc lint pass.
- [ ] Module's own unit tests pass **with the shim entirely absent from the
      test**, proving the §4 boundary.
- [ ] `LagoonClient.build_query(...)` output for the `me` query passes
      `assert_flat_query` directly (unit test, independent of the sweep).
- [ ] `collect_candidate_documents` finds the `whoami_info.py` `build_query`
      call site and it passes the depth check.
- [ ] `test_vacuous_pass_guard` passes against the real tree (not skipped,
      not weakened) — verify by actually running it after `whoami_info.py`
      is added, not by code review alone.
- [ ] **Hard AC:** `docker compose up -d graphql-mock-v3` starts cleanly and
      `make verify-mock` succeeds — proves the vendored `schema/lagoon-2.33.0.graphql`
      loads correctly under `graphql-import`/`graphql-tools`. **If this
      fails, stop and raise it as a blocking finding — do not relax this AC
      to work around a loader incompatibility; the SDL-vs-mock-loader
      compatibility was flagged as unverified during story planning and this
      is where it gets settled.**
- [ ] `.docker/graphql-mock/package-lock.json` committed; a from-scratch
      `docker compose build graphql-mock-v3` still serves the schema
      afterward (i.e. the lockfile is not stale on commit).
- [ ] `whoami_info` runs end to end against `graphql-mock-v3` and returns a
      `user` dict with `changed: false`.
- [ ] `ansible-test units` green for the whole suite (not just the new
      files) — this story touches the most shared surface of the phase.

## Verification commands

```sh
docker compose run --rm test-v3 units -v --requirements

docker compose build graphql-mock-v3
docker compose up -d graphql-mock-v3
sleep 3
make verify-mock
docker compose down graphql-mock-v3

docker compose run --rm lint-docs-v3

grep -rn "^from \.\." plugins/modules/whoami_info.py \
  && echo "FAIL: relative import in a module file" || echo "OK"
```

## Review focus

- Is the sweep extension reconstructing the *real* `build_query()` output
  (calling the actual function), or has a parallel string-building
  reimplementation crept in that could drift from the real one?
- Does `test_vacuous_pass_guard` genuinely pass because the sweep found a
  real candidate, not because the guard was loosened?
- Absolute imports used throughout the module file — this is easy to get
  wrong and easy to miss in review because it "just works" under pytest.
- Is `graphql-mock-v3` actually a *different* schema from the v1
  `graphql-mock` (confirm it's built from `schema/lagoon-2.33.0.graphql`,
  not accidentally still pointing at `api/tests/common/schema.graphql`)?
- Is the `package-lock.json` real (generated, matching the `package.json`),
  not a hand-written stub?
- Does the dropped `groups` field get called out as a breaking change
  somewhere durable (this story's commit body at minimum; Phase 8's
  migration table eventually)?

## Commit

```
feat(v3): add whoami_info module as the auth walking skeleton

Pulled forward from Phase 6 (P2-D5) to prove endpoint -> auth -> shim
-> module -> client end to end before the Phase 3 generator exists.
Resolves open item 12.3: *_info modules do need the action shim, since
they require a token exactly like any other module.

Drops v1 whoami's nested `groups { name type }` selection -- a nested
selection set is forbidden under the REST-semantics rule (plan D3/7.1).
Breaking change, to be recorded in Phase 8's migration table (plan
10).

Extends the P1-S5 sweep to reconstruct documents from
LagoonClient.build_query() call sites by calling the real
implementation with statically-resolved arguments. Without this, the
vacuous-pass guard fails on the first correctly-written module, which
contains no query string literal for the original sweep to match.

Adds graphql-mock-v3, serving the vendored schema/lagoon-2.33.0.graphql
via a pinned package-lock.json (the existing mock's dependencies were
unpinned with no lockfile). Confirms the vendored SDL loads cleanly
under graphql-import/graphql-tools, and retires the Phase 5
carry-forward item covering this Dockerfile for the v3 path.

Refs docs/plans/v3-refactor.md Phase 2, 12.3
```

---

## Phase 2 exit criteria

Phase 2 is complete when all seven commits are reviewed and merged, and:

- [ ] `docker compose run --rm test-v3 units -v --requirements` is green.
- [ ] `grep -rn "import gql\|import requests\|from graphql" plugins/` returns
      nothing.
- [ ] `grep -rln "ansible.errors" plugins/` returns only files under
      `plugins/action/`.
- [ ] No `/tmp` path, no `shell=True`, no write-then-`chmod` pattern anywhere
      in `plugins/module_utils/ssh.py` or `cache.py`.
- [ ] `StrictHostKeyChecking` defaults to `accept-new` wherever the
      collection invokes `ssh`.
- [ ] `antsibull-changelog lint` and
      `antsibull-docs lint-collection-docs --plugin-docs .` both pass.
- [ ] `graphql-mock-v3` builds and serves the vendored SDL; `whoami_info`
      runs against it end to end.
- [ ] `whoami_info`'s own unit tests pass with no action shim involved,
      demonstrating the §4 module/shim boundary holds.

## Carried forward to later phases

| Item | Phase | Note |
| ---- | ----- | ---- |
| Lookup resolution injection in `LagoonActionShim` | 4 | Explicitly out of scope for P2-S6; the shim only handles auth in Phase 2. |
| Extend the auth doc fragment / argspec as new auth-adjacent options appear | 3+ | Keep the P2-S5 drift test passing as the generator starts emitting modules against `doc_fragments/auth.py`. |
| **SDL input-type description coverage is sparse** | 3 | Only 14 of 193 `input` types in `schema/lagoon-2.33.0.graphql` carry any field-level `"""` description (47 total, vs. 213 on output `type` fields and ~60 on `Query`/`Mutation` fields). Parent plan §6.1.5 sources generated option help text from exactly the input-type descriptions that are mostly absent -- e.g. `AddProjectInput` has zero. `antsibull-docs` fails on undocumented options, so the Phase 3 gate module will fail docs lint unless the generator has a fallback (an `allowlist.yml` per-option `descriptions:` override block, at minimum for the gate resources). Discovered during Phase 2 story planning; not a Phase 2 blocker, but will block Phase 3's gate if not designed for up front. |
| `.docker/Dockerfile.graphql-mock` (v1) still copies `api/tests/common/schema.graphql` | — | Retired for the **v3** path by P2-S7's `graphql-mock-v3`. The v1 service and Dockerfile stay as-is; only deleted in the post-Phase-8 cleanup story per P1-D2. |
| Galaxy namespace ownership for `salsadigitalauorg` | before 3.0.0 tag | Unchanged from Phase 1's carry-forward. |
