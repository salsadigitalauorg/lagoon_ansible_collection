# P2-S4 implementation plan — `module_utils/cache.py` opt-in cross-process file cache

**Date:** 2026-08-26
**Story:** [`docs/plans/v3-phase2-stories.md`](./v3-phase2-stories.md) § P2-S4
**Parent plan:** [`docs/plans/v3-refactor.md`](./v3-refactor.md) §7.2
**Branch:** `3.x`
**Depends on:** P2-S3b (`4e35c8b`) — landed
**Deliverable:** exactly one commit (story process item 2), then `review`

---

## Scope

Two new files, two modified:

```
plugins/module_utils/cache.py                        NEW
tests/unit/plugins/module_utils/test_cache.py        NEW
plugins/module_utils/auth.py                         MODIFIED (wire the flag in)
tests/unit/plugins/module_utils/test_auth.py         MODIFIED (disabled-path test)
```

No changelog fragment — consistent with P2-S1…P2-S3b, none of which added one
(`git log --stat` on `f992647`, `e809eaa`, `4e35c8b`). Phase 8 owns changelog
wiring.

`lagoon_token_cache=dict(type='bool', default=False)` **already exists** in
`auth_argument_spec()` (`auth.py:74`, landed with P2-S3) but is read nowhere.
This story makes it load-bearing.

---

## Decisions taken for this story

These were open in the story text and are resolved here. Both were confirmed
with the user before implementation.

| # | Item | Decision |
| - | ---- | -------- |
| **S4-1** | **P2-D11 for the file cache** (story: "must resolve", "do not inherit the in-memory cache's reasoning by default without saying so") | **Accept the collision, documented explicitly in `cache.py`'s module docstring** — not inherited silently. The docstring must state the cross-process lifetime *changes* the risk relative to P2-D11's in-memory finding (the "agent socket cannot change mid-process" justification does **not** transfer), name the residual risk, and record that disambiguation was considered and rejected. See "S4-1 in detail" below for the exact reasoning that must appear. |
| **S4-2** | `lagoon_token_cache_dir` (P2-S5 lists it "if exposed") | **Not exposed.** Directory resolution is `$XDG_CACHE_HOME/ansible-lagoon` → `~/.cache/ansible-lagoon`, controllable only by the operator/runner environment, never by a playbook author. A playbook-settable path could point at `/tmp`, reintroducing the predictable-path-in-a-world-writable-directory defect class P2-S2 exists to fix, and validating that away is fiddler than it is worth. **This resolves P2-S5's "if exposed" to "not exposed"** — the doc fragment must not declare it, or P2-S5's drift test will fail against the argspec. |
| **S4-3** | Path-traversal-shaped key: raise or miss? (story: "pick one, document it, test it") | **Raise `LagoonConfigError`**, from both `read_cached_token` and `write_cached_token`, before any filesystem call. Validated with a **positive allowlist** (`^[0-9a-f]{64}$`) rather than blocklisting `/`, `\`, `..`. Rationale below. |
| **S4-4** | Cache *write* failure (read-only HOME, disk full) | Swallowed. `write_cached_token` catches `OSError` and returns `False`; a successful grant must not be turned into a task failure because an opportunistic cache write failed. `LagoonConfigError` (S4-3) is **not** swallowed — that is an invariant violation, not an environmental one. |
| **S4-5** | Orphaned temp file when `os.replace` fails | Unlinked on the failure path (best-effort, `try`/`except OSError: pass`). This is a deliberate strengthening of the story's "the temp file may remain — that's acceptable"; leaving a mode-0600 file containing a live bearer token behind is exactly the credential-litter posture this module is trying to bound. It does **not** conflict with the story's "no `finally`-block deletion" rule, which is about the *final* cache entry, not an orphaned temp that never became one. Story test 4 asserts on the **final** path only, so it passes either way. |

### S4-1 in detail — what the docstring must say

The story's instruction is that the decision be made *deliberately*. The
reasoning that must be on the page in `cache.py`, not just here:

- Under agent auth (P2-D9) `auth.cache_key()`'s `key_material_hash` is `''`,
  so the key degenerates to `(endpoint, ssh_host, ssh_port, ssh_user)`.
- P2-D11 accepted that for the in-memory cache because the agent socket cannot
  change mid-process. **That justification does not transfer here** — this
  cache outlives the process and can be read by a later
  `ansible-playbook` run whose agent holds a *different* identity.
- Residual risk, stated plainly: within a single OS user account, a run may be
  served a token minted for a different Lagoon identity that the same OS user
  also controls. Consequences are mis-attribution in Lagoon's audit trail and,
  if the two identities differ in privilege, a run acting with the wrong one.
- Why accepted anyway: the trust boundary is the OS user account. Both agent
  identities are already reachable by that account (they are in its agent), so
  this is not a privilege *escalation* across a security boundary — it is
  wrong-identity selection within one. The cache is off by default, and an
  operator who opts in is choosing to persist a bearer token under their own
  `$HOME`.
- Why not disambiguated: the obvious discriminator is the agent's loaded-key
  fingerprint set (`ssh-add -l`), which would mean a new external binary
  dependency, output parsing, and new failure modes inside a security-sensitive
  key-derivation path. `SSH_AUTH_SOCK` itself is not usable — it is typically a
  random per-run temp path, so hashing it in would defeat cache reuse rather
  than protect it (same finding as P2-D11).
- Mitigation available to operators today, and it must be named in the
  docstring: supply `lagoon_ssh_private_key_file` so the key path participates
  in the hash, or grant once and `set_fact` the token (parent plan §4).

This creates a **P2-S5 documentation obligation**: `lagoon_token_cache`'s
description in the doc fragment must carry a short version of this caveat.
Flagged in "Downstream obligations" below.

### S4-3 in detail — allowlist, and raise rather than miss

`auth.cache_key()` can only ever return a 64-character lowercase hex sha256
digest. So a key that fails that shape means a caller bypassed `cache_key()` —
a programming defect. Degrading a defect into a silent cache miss produces a
cache that appears to work while caching nothing; raising makes it loud.

The allowlist is strictly stronger than the story's "reject `/`, `\`, `..`"
blocklist and satisfies the same acceptance criterion ("path-traversal-shaped
keys rejected"). It is not a deviation from the plan's intent, so no
stop-and-raise is needed — but note it in the commit body.

`read_cached_token`'s "never raises" contract is about **cache state** (absent,
unreadable, wrong-owned, wrong-moded, malformed, expired) — all of which are
misses. A malformed *argument* is a different category. Say so in the
docstring so a future contributor doesn't "fix" the raise into a miss.

---

## `plugins/module_utils/cache.py`

### Imports — and the circular-import trap

```python
import errno, json, os, re, stat, tempfile
from .errors import LagoonConfigError
from .token import token_is_valid
```

**`cache.py` must NOT import `auth.py`.** The story says the filename uses
"the same value `auth.cache_key()` produces (imported, not recomputed)" — that
means `auth.py` passes its own `cache_key()` result **in** as the `key`
argument. `auth.py` already imports `ssh` and `token`; adding
`auth → cache` is fine, `cache → auth` would be a cycle. The public functions
all take `key` as a parameter precisely so this stays acyclic.

`stat` and `errno` are only needed if the implementation uses them; drop
whichever is unused rather than carrying a dead import past the linter.

### Module docstring

Must cover, each as its own short paragraph:

1. **Off by default; this is the only place in the collection where a bearer
   token touches disk.**
2. **Why a stable path under `$HOME` is not the `/tmp` defect** (story
   explicitly asks for this, to stop a future reviewer pattern-matching on
   "predictable path"): the P2-S2 attack needs a *world-writable* parent
   directory so an attacker can pre-create the path as a symlink. `$HOME` and
   `$XDG_CACHE_HOME` are not world-writable, so predictability alone is not
   the vulnerability. The read path's ownership/mode checks are the backstop.
3. **No `finally`-block deletion, and why** — a cross-process cache the first
   worker deletes on exit never serves a second task, defeating the feature.
   Entries age out via the token's own `exp` claim on read. Phrase this as a
   standing instruction ("do not 'fix' this by adding cleanup") since parent
   plan §7.2's SSH-key requirements read as if they transfer, and §7.2 has
   already been amended to say they don't.
4. **S4-1's agent-auth collision** in full (above).

### `cache_dir()`

```python
def cache_dir():
    """$XDG_CACHE_HOME/ansible-lagoon, else ~/.cache/ansible-lagoon.
    Created at mode 0700 (parents too) if absent. Returns the path."""
```

- `XDG_CACHE_HOME` is honoured **only when set and non-empty**. A set-but-empty
  value must fall back to `~/.cache`, not resolve to `ansible-lagoon` relative
  to CWD. Test this — it is the easy bug here.
- `os.makedirs(path, mode=0o700, exist_ok=True)` **plus an explicit
  `os.chmod(path, 0o700)`** afterwards. `makedirs`'s `mode` is umask-affected,
  and it is a no-op entirely when the directory already exists at a wider
  mode. The story calls for both; do not drop the `chmod`.
- Use `os.path.expanduser('~')` for the fallback.
- This function **creates**. It must therefore only ever be called from the
  enabled path — see "zero filesystem activity" below.

### `read_cached_token(key)`

```python
def read_cached_token(key):
    """Return the cached token string, or None on any miss.

    A miss is: file absent, unreadable, not owned by the current euid,
    group/other-permissioned, malformed JSON, missing the token field, or
    expired per token.token_is_valid(). Never raises for cache state --
    a miss is not an error. Does raise LagoonConfigError for a malformed
    `key`, which is a caller defect, not a cache state (see S4-3)."""
```

Order of operations, and each step matters:

1. `_validate_key(key)` → `LagoonConfigError` on failure. **Before** any path
   construction or filesystem call (this is the acceptance criterion's
   "rejected before any filesystem operation").
2. Build `path = os.path.join(cache_dir(), 'token-%s.json' % key)`.
   - Note: this calls `cache_dir()`, which *creates* the directory. That is
     acceptable because reads only happen on the enabled path. Do not add a
     "probe without creating" variant — it doubles the surface for no gain.
3. `os.stat(path)`; `except OSError: return None` (covers `ENOENT` and
   `EACCES` alike, both genuine misses).
4. **Refuse, don't repair:**
   - `st.st_uid != os.geteuid()` → `None`
   - `stat.S_IMODE(st.st_mode) & 0o077` → `None`

   No `chmod`, no unlink. A wrongly-permissioned credential file is evidence
   that something else touched it; silently normalising it erases the signal.
   Put that sentence in the code as a comment — it is the single most
   likely thing for a later contributor to "tidy up".
   - **Portability:** `os.geteuid` does not exist on Windows. Guard with
     `hasattr(os, 'geteuid')` and skip only the ownership check when absent
     (the mode check still applies). The collection is controller-side and
     Ansible controllers are not supported on Windows, so this is a
     defensive nicety, not a supported configuration — say so in a comment
     so nobody expands it into a Windows support claim.
5. Read + `json.loads`; `except (OSError, ValueError): return None`.
6. `if not isinstance(payload, dict): return None`; pull `payload.get('token')`;
   `if not isinstance(token, str) or not token: return None`.
7. `if not token_is_valid(token): return None` — this is what ages entries out.
8. Return `token`.

### `write_cached_token(key, token)`

```python
def write_cached_token(key, token):
    """Atomically write token-<key>.json at mode 0600. Returns True on
    success, False if the write failed for an environmental reason (a
    read-only HOME, a full disk) -- a failed opportunistic cache write
    must never fail a task whose grant actually succeeded. Raises
    LagoonConfigError for a malformed `key`."""
```

1. `_validate_key(key)` first, same as read.
2. `directory = cache_dir()`.
3. `fd, tmp_path = tempfile.mkstemp(dir=directory, prefix='.token-', suffix='.tmp')`
   - `dir=` is what keeps the temp file on the same filesystem, so
     `os.replace` is atomic.
   - The dotted prefix + `.tmp` suffix keeps an orphan from ever matching the
     `token-<64hex>.json` read pattern.
4. `os.fchmod(fd, 0o600)` **explicitly**, before writing. Do not rely on
   `mkstemp`'s documented 0600 — the story asks for it set, not assumed.
5. `os.write(fd, json.dumps({'token': token}).encode('utf-8'))`, then
   `os.close(fd)`.
6. `os.replace(tmp_path, final_path)`; return `True`.
7. On `OSError` anywhere in 3–6: best-effort `os.close(fd)` if still open,
   best-effort `os.unlink(tmp_path)` (S4-5), return `False`.

The JSON payload is `{"token": "..."}` — a dict, not a bare string, so a future
field (e.g. a cached `expires_in`) is additive. Do **not** store `expires_in`
now; `token_is_valid` reads `exp` from the token itself and a second, redundant
expiry source is a divergence waiting to happen.

### `_validate_key(key)`

```python
_KEY_RE = re.compile(r'^[0-9a-f]{64}$')
```

Raise `LagoonConfigError` with a message that describes the *shape* problem and
**does not echo the key back** — keep the same discipline as `token.py` and
`ssh.py` even though a cache key is not itself secret. Reject non-`str` inputs
too.

---

## `plugins/module_utils/auth.py` — wiring

### Resolution order

The file cache slots in as a sub-step of plan §7.2 step 3, between the
in-memory cache and the grant. The §7.2 numbering is unchanged.

```
1.  config['token']            -> as-is
2.  LAGOON_API_TOKEN           -> as-is
3.  in-memory _cache           -> if token_is_valid
3b. file cache                 -> ONLY if config['token_cache'] is true;
                                  validity checked inside read_cached_token;
                                  on hit, populate _cache too, so a loop:
                                  over one task reads the file once, not N times
4.  ssh.request_grant          -> populate _cache; and the file cache if enabled
```

Concretely, after the existing in-memory lookup and before the `ssh_host`
guard:

```python
if config.get('token_cache'):
    cached_token = read_cached_token(key)
    if cached_token is not None:
        _cache[key] = cached_token
        return cached_token
```

and after the grant, alongside `_cache[key] = access_token`:

```python
if config.get('token_cache'):
    write_cached_token(key, access_token)
```

`config.get('token_cache')` — the `config` dict keys are the unprefixed forms
(`token`, `ssh_host`, `private_key`…), matching how `resolve_token` already
reads `config`. The `lagoon_`-prefixed names are the *argspec* surface; P2-S6's
shim does the mapping. Do not read `config['lagoon_token_cache']` here.

Note the asymmetry, and comment it: a file-cache **hit** back-fills the
in-memory cache, but the in-memory cache is never written *through* to disk
except on a fresh grant. A token that arrived via steps 1–2 must never be
written to disk — the operator supplied it directly and did not ask us to
persist it. This is the same "don't second-guess an explicit token" principle
as P2-S1's validation boundary.

### `resolve_token` docstring

Add the 3b step to the numbered list, and one paragraph: the file cache is
opt-in via `lagoon_token_cache`, off by default, and is the only path in the
collection that persists a bearer token to disk. Cross-reference `cache.py`
rather than restating its reasoning.

### Not changed

- `cache_key()` — unchanged, including its existing P2-D11 paragraph. That
  paragraph currently says P2-S4 "must make this call explicitly rather than
  inheriting this reasoning by default". Update its final sentence to point at
  the decision now that it exists (`cache.py`'s docstring records the
  cross-process decision), so the forward reference doesn't dangle.
- `auth_argument_spec()` — `lagoon_token_cache` is already present and already
  defaults `False`. No new options (S4-2).
- `clear_cache()` — in-memory only. Do **not** make it delete cache files; a
  test seam that reaches into the operator's `$HOME` is a footgun. If
  `test_auth.py` needs isolation from a real cache file, it patches
  `read_cached_token`/`write_cached_token` — which is what the disabled-path
  test does anyway.

---

## Tests — `tests/unit/plugins/module_utils/test_cache.py`

Conventions to match (from `test_ssh.py` / `test_auth.py`): `unittest.TestCase`
classes, `from __future__` + `__metaclass__` header, five-dot relative imports
(`from .....plugins.module_utils import cache`), and a `_MODULE_PATH` constant
`'ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.cache'`
for `patch()` targets.

Prefer **real temp directories** over mocked filesystems wherever the assertion
is about permission bits — `test_ssh.py`'s `TestTempKeyFilePermissions` sets
this precedent, and the story is explicit ("assert via `os.stat`, not by
trusting the code path"). A helper that patches `XDG_CACHE_HOME` to a
`tempfile.TemporaryDirectory()` for the duration of a test is the cleanest
seam and avoids touching the developer's real `~/.cache`.

> **Isolation is a hard requirement of this test file.** Every test that can
> reach `cache_dir()` must have `XDG_CACHE_HOME` pointed at a temp directory.
> A test that writes into the real `~/.cache/ansible-lagoon` is a defect even
> if it passes.

| # | Test | Asserts |
| - | ---- | ------- |
| 1 | `cache_dir()` mode | Real temp `XDG_CACHE_HOME`; `stat.S_IMODE(os.stat(d).st_mode) == 0o700` |
| 2 | `cache_dir()` pre-existing wide mode | Pre-create the directory `0755`; `cache_dir()` narrows it to `0700` (proves the explicit `chmod`, which `makedirs(exist_ok=True)` alone would skip) |
| 3 | XDG unset | `XDG_CACHE_HOME` removed from `os.environ` → path is under `expanduser('~')/.cache/ansible-lagoon`. Assert the **resolved path string** with `expanduser` patched; do not create anything in the real HOME |
| 4 | XDG set-but-empty | Falls back to `~/.cache`, not a CWD-relative path |
| 5 | Written file mode | Real dir; `write_cached_token` then `os.stat` → `0o600` |
| 6 | Round-trip | Real dir, nothing mocked except `XDG_CACHE_HOME`: write then read returns the same token. Needs a **real, well-formed, unexpired JWT** — build one the way `test_token.py` does (base64url header/payload with a far-future `exp`), since `read_cached_token` runs it through `token_is_valid` |
| 7 | Atomicity | Patch `%s.os.replace` to raise `OSError` → `write_cached_token` returns `False`, and the **final** `token-<key>.json` path does not exist. (Per S4-5 the temp is also cleaned; assert the final path per the story, and optionally that no `.tmp` orphan remains) |
| 8 | Foreign uid | Patch `%s.os.stat` to return a stat result with a foreign `st_uid` → `None`, no exception |
| 9 | Over-permissive mode | Patch `st_mode` to `0o100640` → `None`, no exception |
| 10 | Refuse, don't repair | On the 8/9 paths, assert `os.chmod` and `os.unlink` are **not** called. This is the test that stops the "helpfully fix the mode" regression |
| 11 | Expired entry | Real file, correct owner/mode, `token_is_valid` patched `False` → `None` |
| 12 | Malformed JSON | File containing `not json` → `None` |
| 13 | JSON but not an object / missing `token` | `[]` and `{}` → `None` |
| 14 | Absent file | → `None`, no exception |
| 15 | Traversal key — read | `read_cached_token('../../etc/passwd')` → `LagoonConfigError`, **and** assert no filesystem call happened (patch `%s.os.stat` / `%s.cache_dir`, assert not called) |
| 16 | Traversal key — write | Same for `write_cached_token`; assert `tempfile.mkstemp` not called |
| 17 | Key allowlist edges | Uppercase hex, 63 chars, 65 chars, empty string, non-`str` → all `LagoonConfigError` |
| 18 | Key absent from the error message | `str(e)` does not contain the offending key |
| 19 | Write failure is not fatal | Patch `%s.tempfile.mkstemp` to raise `OSError` → returns `False`, does not raise |
| 20 | No forbidden imports | AST walk over `cache.py`, mirroring `test_auth.py::TestNoForbiddenImports`. Extend the blocklist to include **`ansible`** (not just `ansible.errors`) and check `ast.Import` as well as `ast.ImportFrom` — `test_ssh.py`'s variant is the better template here |
| 21 | No `/tmp` literal | Assert the string `/tmp` is absent from the source, so the acceptance criterion is enforced by the suite rather than only by a shell grep a reviewer might skip |

## Tests — `tests/unit/plugins/module_utils/test_auth.py` (additions)

Story test 1 is really an `auth.py`-side test. Add a `TestFileCacheDisabled` /
`TestFileCacheEnabled` pair:

| # | Test | Asserts |
| - | ---- | ------- |
| A | **Disabled → zero filesystem activity.** `_config()` without `token_cache` (or explicitly `False`); patch `%s.read_cached_token` and `%s.write_cached_token` in `auth`'s namespace → both `assert_not_called()` after a grant. This is the acceptance criterion's teeth | |
| B | Enabled, file-cache hit → `request_grant` **not** called; returned token is the cached one | |
| C | Enabled, file-cache hit → the in-memory `_cache` is back-filled (`auth._cache[cache_key(config)]`) | |
| D | Enabled, file-cache miss (`read_cached_token` → `None`) → grant runs once, `write_cached_token` called once with `(cache_key(config), granted_token)` | |
| E | In-memory hit short-circuits the file cache → `read_cached_token` not called at all | |
| F | Explicit `token` and `LAGOON_API_TOKEN` are **never** written to disk, even with the flag on → `write_cached_token.assert_not_called()`. Two tests; this is a security property, not a nicety | |

`_config()` in `test_auth.py` gains `'token_cache': False` so the default in
every existing test is explicit rather than incidental.

---

## Verification

Story commands, plus the ones the additions warrant:

```sh
docker compose run --rm test-v3 units -v --requirements \
  tests/unit/plugins/module_utils/test_cache.py \
  tests/unit/plugins/module_utils/test_auth.py

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

Then re-run the full v3 module_utils suite, since `auth.py` changed:

```sh
docker compose run --rm test-v3 units -v --requirements \
  tests/unit/plugins/module_utils/
```

Confirm no `~/.cache/ansible-lagoon` was created by the run — if it exists
after a green suite, an isolation seam is missing:

```sh
test -e "${XDG_CACHE_HOME:-$HOME/.cache}/ansible-lagoon" \
  && echo "FAIL: test suite touched the real cache dir" || echo "OK"
```

---

## Acceptance criteria (from the story, mapped)

- [ ] Disabled by default; zero filesystem writes when not opted in → test A
- [ ] Directory `0700`, file `0600`, verified by `os.stat` → tests 1, 2, 5
- [ ] Atomic write via `mkstemp` + `os.replace` → tests 6, 7
- [ ] Read refuses foreign-owned / over-permissive as a miss, never an
      exception, never a silent `chmod` → tests 8, 9, 10
- [ ] No `finally`-block deletion; deviation documented in the module
      docstring **and** the commit body → docstring item 3
- [ ] `/tmp` absent from the file → test 21 + grep
- [ ] Path-traversal-shaped keys rejected → tests 15, 16, 17
- [ ] **P2-D11 resolved explicitly for this cache** (story's "must also
      resolve") → S4-1, in `cache.py`'s docstring

## Review focus (story's list, plus)

- Is "disabled by default, zero filesystem activity" actually true — does
  `cache_dir()` get called (and therefore create) regardless of the flag?
- Is the permission check enforced against a real mode mismatch?
- Is the "no `finally` cleanup" deviation justified **on the page**, not just
  in the story doc?
- XDG resolution correct with `XDG_CACHE_HOME` unset *and* set-but-empty.
- **Added:** is the S4-1 agent-auth decision argued, or does it read as
  inherited from P2-D11 by default (which the story forbids)?
- **Added:** can a token from resolution steps 1–2 ever reach disk?

---

## Downstream obligations created

Record these in the commit body so they are not lost between stories.

1. **P2-S5** must document `lagoon_token_cache` including: off by default;
   the credential-at-rest tradeoff; the `$XDG_CACHE_HOME` location and `0700`/
   `0600` posture; and a short form of the S4-1 agent-identity caveat with the
   `lagoon_ssh_private_key_file` mitigation.
2. **P2-S5** must **not** declare `lagoon_token_cache_dir` (S4-2) — the drift
   test compares the fragment against `auth_argument_spec()` in both
   directions, so declaring an option the argspec lacks fails the test.
3. **P2-S6** (`LagoonActionShim`) is where a warn channel first exists. Two
   things worth surfacing there, neither blocking this story:
   `write_cached_token` returning `False` (opt-in cache silently not working),
   and `strict_host_key_checking='no'` (the warning P2-S2 deliberately left to
   a policy layer). Note as a follow-up, do not build a warn shim here.
4. **Phase 8 migration table** already owes the P2-D10 `ssh_options` no-op
   entry; add that v1 had no equivalent file cache, so `lagoon_token_cache` is
   new-and-opt-in rather than a behaviour change.

---

## Commit

Story's message, extended with the two decisions it required be made
explicitly. Keep the story's first three paragraphs verbatim.

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
disk; it is off by default for that reason. Tokens supplied explicitly
via lagoon_api_token or LAGOON_API_TOKEN are never written here --
the operator supplied them directly and did not ask us to persist
them.

Resolves P2-D11 for this cache explicitly rather than inheriting the
in-memory cache's reasoning: under agent auth the cache key has no
key-material component, and unlike the in-memory cache this one
outlives the process, so a later run whose agent holds a different
identity can be served the earlier identity's token. Accepted, because
the trust boundary is the OS user account and both identities are
already reachable by it -- this is wrong-identity selection within a
boundary, not escalation across one. Not disambiguated via ssh-add -l
fingerprints, which would put an external binary and its parsing
inside a security-sensitive key-derivation path. Operators who need
the distinction should supply lagoon_ssh_private_key_file, which
participates in the hash. Reasoning is in cache.py's docstring, not
only in the story doc.

The cache directory is intentionally not exposed as a module option;
it is resolved from the environment only, so a playbook author cannot
redirect a bearer token to a world-writable path. P2-S5's
"lagoon_token_cache_dir if exposed" therefore resolves to not exposed.

Cache keys are validated against a positive ^[0-9a-f]{64}$ allowlist
rather than a traversal blocklist, and a malformed key raises
LagoonConfigError rather than degrading to a cache miss -- cache_key()
cannot produce one, so a bad key is a caller defect and should be
loud.

Refs docs/plans/v3-refactor.md Phase 2, 7.2
Refs docs/plans/v3-phase2-stories.md P2-S4 (P2-D1, P2-D11)
```

---

## Sequencing note

Per story process items 2–3: one commit, then hand the SHA to `review` and
iterate on that commit until the reviewer is satisfied before starting P2-S5.
This story is not in the security-critical class that item 6 flags (that was
P2-S2), but it does put a credential on disk and makes a security decision
under S4-1 — a `security` pass is discretionary and worth considering.
