import json
import os
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from .....plugins.module_utils import token_cache

TOKEN = "a-minted-token"


class TokenCacheTestCase(unittest.TestCase):
    """Always against a temporary directory, never the real cache.

    LAGOON_TOKEN_CACHE_DIR is set for every test, and the process-level memory
    tier cleared, so no test can read or write a developer's own token cache.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "cache")
        self.env = patch.dict(
            os.environ,
            {"LAGOON_TOKEN_CACHE_DIR": self.dir, "LAGOON_TOKEN_CACHE": "1"},
        )
        self.env.start()
        token_cache._memory.clear()
        self.addCleanup(token_cache._memory.clear)
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)

    def entry_path(self, key):
        return os.path.join(self.dir, f"token-{key}.json")


class RoundTripTester(TokenCacheTestCase):
    def test_put_then_get(self):
        token_cache.put("k", TOKEN, 3600)
        assert token_cache.get("k") == TOKEN

    def test_a_miss_is_none(self):
        assert token_cache.get("never-written") is None

    def test_the_entry_survives_a_cleared_memory_tier(self):
        """The point of the on-disk tier: Ansible forks a worker per host per
        task, and module-level state does not survive the fork."""

        token_cache.put("k", TOKEN, 3600)
        token_cache._memory.clear()

        assert token_cache.get("k") == TOKEN


class PermissionsTester(TokenCacheTestCase):
    def test_file_mode_is_0600(self):
        token_cache.put("k", TOKEN, 3600)
        mode = stat.S_IMODE(os.stat(self.entry_path("k")).st_mode)
        assert mode == 0o600, oct(mode)

    def test_directory_mode_is_0700(self):
        token_cache.put("k", TOKEN, 3600)
        mode = stat.S_IMODE(os.stat(self.dir).st_mode)
        assert mode == 0o700, oct(mode)

    def test_mode_is_not_left_to_the_umask(self):
        """The mode argument to makedirs is masked by umask, so it is set with
        an explicit chmod. A permissive umask must not widen either."""

        original = os.umask(0o000)
        try:
            token_cache.put("k", TOKEN, 3600)
        finally:
            os.umask(original)

        assert stat.S_IMODE(os.stat(self.entry_path("k")).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(self.dir).st_mode) == 0o700

    def test_no_credential_material_in_the_filename(self):
        key = token_cache.make_key(
            "https://api.example.com",
            "ssh.example.com",
            "32222",
            token_cache.fingerprint("-----BEGIN OPENSSH PRIVATE KEY-----\nabc"),
        )
        token_cache.put(key, TOKEN, 3600)

        names = os.listdir(self.dir)
        assert names
        for name in names:
            assert TOKEN not in name
            assert "BEGIN" not in name
            assert "api.example.com" not in name


class ExpiryTester(TokenCacheTestCase):
    def test_an_expired_entry_is_a_miss(self):
        token_cache.put("k", TOKEN, -1)
        token_cache._memory.clear()

        assert token_cache.get("k") is None

    def test_an_entry_inside_the_skew_window_is_a_miss(self):
        """Treated as spent before its stated expiry, so a token is never
        handed out with less life left than the request might take."""

        token_cache.put("k", TOKEN, token_cache.EXPIRY_SKEW - 1)
        token_cache._memory.clear()

        assert token_cache.get("k") is None

    def test_an_entry_outside_the_skew_window_is_a_hit(self):
        token_cache.put("k", TOKEN, token_cache.EXPIRY_SKEW + 60)
        token_cache._memory.clear()

        assert token_cache.get("k") == TOKEN

    def test_expires_at_is_absolute_in_the_stored_entry(self):
        token_cache.put("k", TOKEN, 3600)
        with open(self.entry_path("k")) as fh:
            entry = json.load(fh)

        assert entry["expires_at"] > time.time()
        assert entry["expires_at"] <= time.time() + 3600

    def test_an_unusable_expires_in_is_not_cached(self):
        token_cache.put("k", TOKEN, None)
        assert token_cache.get("k") is None
        assert not os.path.exists(self.entry_path("k"))


class CorruptEntryTester(TokenCacheTestCase):
    def write_raw(self, key, content):
        os.makedirs(self.dir, exist_ok=True)
        with open(self.entry_path(key), "w") as fh:
            fh.write(content)

    def test_a_truncated_entry_is_a_miss(self):
        self.write_raw("k", '{"access_token": "abc", "expires_at":')
        assert token_cache.get("k") is None

    def test_an_entry_missing_its_keys_is_a_miss(self):
        self.write_raw("k", '{"something_else": 1}')
        assert token_cache.get("k") is None

    def test_a_non_numeric_expiry_is_a_miss(self):
        self.write_raw("k", '{"access_token": "abc", "expires_at": "soon"}')
        assert token_cache.get("k") is None

    def test_an_empty_token_is_a_miss(self):
        self.write_raw("k", json.dumps({"access_token": "", "expires_at": 1 << 40}))
        assert token_cache.get("k") is None


class KeyTester(TokenCacheTestCase):
    def test_different_endpoints_get_different_keys(self):
        a = token_cache.make_key("https://a.example.com", "h", "22", "fp")
        b = token_cache.make_key("https://b.example.com", "h", "22", "fp")
        assert a != b

    def test_different_identities_get_different_keys(self):
        a = token_cache.make_key("https://a.example.com", "h", "22", "fp-one")
        b = token_cache.make_key("https://a.example.com", "h", "22", "fp-two")
        assert a != b

    def test_different_ssh_hosts_and_ports_get_different_keys(self):
        base = token_cache.make_key("e", "h", "22", "fp")
        assert base != token_cache.make_key("e", "other", "22", "fp")
        assert base != token_cache.make_key("e", "h", "2222", "fp")

    def test_the_same_inputs_get_the_same_key(self):
        assert token_cache.make_key("e", "h", "22", "fp") == token_cache.make_key(
            "e", "h", "22", "fp"
        )

    def test_fingerprint_does_not_reveal_the_credential(self):
        key_content = "-----BEGIN OPENSSH PRIVATE KEY-----\nsecret-material"
        fp = token_cache.fingerprint(key_content)

        assert "secret-material" not in fp
        assert "BEGIN" not in fp
        assert fp != key_content
        assert fp == token_cache.fingerprint(key_content)
        assert fp != token_cache.fingerprint(key_content + "x")

    def test_absent_credentials_fingerprint_consistently(self):
        assert token_cache.fingerprint(None) == token_cache.fingerprint("")


class DegradationTester(TokenCacheTestCase):
    """A cache miss must never fail a playbook run.

    Containers routinely run as an arbitrary UID with no writable HOME -
    OpenShift's random UID being the common case - so an unusable cache
    directory is an ordinary condition, not an error.
    """

    def test_an_unwritable_directory_degrades_to_memory(self):
        blocked = os.path.join(self.tmp.name, "blocked")
        os.makedirs(blocked, mode=0o500)
        self.addCleanup(os.chmod, blocked, 0o700)

        with patch.dict(
            os.environ,
            {"LAGOON_TOKEN_CACHE_DIR": os.path.join(blocked, "cache")},
        ):
            token_cache.put("k", TOKEN, 3600)
            assert token_cache.get("k") == TOKEN

            token_cache._memory.clear()
            assert token_cache.get("k") is None

    def test_an_unwritable_directory_does_not_raise(self):
        blocked = os.path.join(self.tmp.name, "blocked2")
        os.makedirs(blocked, mode=0o500)
        self.addCleanup(os.chmod, blocked, 0o700)

        with patch.dict(
            os.environ,
            {"LAGOON_TOKEN_CACHE_DIR": os.path.join(blocked, "cache")},
        ):
            assert token_cache.resolve("k", lambda: (TOKEN, 3600)) == TOKEN

    def test_no_home_and_no_override_is_not_fatal(self):
        with patch.dict(os.environ, clear=True):
            with patch("os.path.expanduser", side_effect=OSError("no home")):
                assert token_cache.cache_dir() is None
                token_cache.put("k", TOKEN, 3600)
                assert token_cache.get("k") == TOKEN


class OptOutTester(TokenCacheTestCase):
    def test_disabled_writes_nothing_to_disk(self):
        with patch.dict(os.environ, {"LAGOON_TOKEN_CACHE": "0"}):
            token_cache.put("k", TOKEN, 3600)
            assert not os.path.exists(self.entry_path("k"))
            # Still cached for this process, which puts no credential at rest.
            assert token_cache.get("k") == TOKEN

    def test_disabled_reads_nothing_from_disk(self):
        token_cache.put("k", TOKEN, 3600)
        token_cache._memory.clear()

        with patch.dict(os.environ, {"LAGOON_TOKEN_CACHE": "0"}):
            assert token_cache.get("k") is None

    def test_the_documented_and_obvious_false_values_all_disable(self):
        for value in ["0", "false", "False", "no", "off", "OFF"]:
            with patch.dict(os.environ, {"LAGOON_TOKEN_CACHE": value}):
                assert not token_cache.enabled(), value

    def test_absent_means_enabled(self):
        with patch.dict(os.environ, {"LAGOON_TOKEN_CACHE_DIR": self.dir}, clear=True):
            assert token_cache.enabled()


class CacheDirTester(TokenCacheTestCase):
    def test_the_override_wins(self):
        assert token_cache.cache_dir() == self.dir

    def test_xdg_cache_home_is_next(self):
        with patch.dict(os.environ, {"XDG_CACHE_HOME": "/xdg"}, clear=True):
            assert token_cache.cache_dir() == os.path.join("/xdg", "lagoon")

    def test_otherwise_the_user_cache_directory(self):
        with patch.dict(os.environ, clear=True):
            with patch("os.path.expanduser", return_value="/home/someone"):
                assert token_cache.cache_dir() == os.path.join(
                    "/home/someone", ".cache", "lagoon"
                )

    def test_never_inside_the_project_directory(self):
        """So it cannot be committed, or picked up by a collection build."""
        with patch.dict(os.environ, clear=True):
            with patch("os.path.expanduser", return_value="/home/someone"):
                assert not token_cache.cache_dir().startswith(os.getcwd())


class DiscardTester(TokenCacheTestCase):
    def test_discard_removes_both_tiers(self):
        token_cache.put("k", TOKEN, 3600)
        token_cache.discard("k")

        assert token_cache.get("k") is None
        assert not os.path.exists(self.entry_path("k"))

    def test_discarding_an_absent_entry_is_not_an_error(self):
        token_cache.discard("never-written")


class ResolveTester(TokenCacheTestCase):
    def test_fetch_runs_once_for_many_resolves(self):
        calls = []

        def fetch():
            calls.append(1)
            return TOKEN, 3600

        for _ in range(5):
            assert token_cache.resolve("k", fetch) == TOKEN

        assert len(calls) == 1

    def test_fetch_runs_again_once_the_entry_expires(self):
        calls = []

        def fetch():
            calls.append(1)
            return TOKEN, token_cache.EXPIRY_SKEW - 1

        token_cache.resolve("k", fetch)
        token_cache.resolve("k", fetch)

        assert len(calls) == 2

    def test_a_fetched_token_is_written_through(self):
        token_cache.resolve("k", lambda: (TOKEN, 3600))
        token_cache._memory.clear()

        assert token_cache.get("k") == TOKEN


@unittest.skipUnless(hasattr(os, "fork"), "requires fork")
@unittest.skipUnless(token_cache.HAS_FCNTL, "requires fcntl")
class ConcurrencyTester(TokenCacheTestCase):
    """The flock serialisation is the entire justification for the on-disk
    cache, and it is easy to break silently.

    Without it, N forks starting together all miss and all fetch, which
    defeats the purpose on exactly the task that matters most: the first task
    of a play across many hosts.
    """

    def test_concurrent_resolves_against_a_cold_cache_fetch_once(self):
        counter = os.path.join(self.tmp.name, "fetches")
        os.makedirs(self.dir, mode=0o700, exist_ok=True)

        def fetch():
            # Appended from several processes, so each fetch is one line.
            with open(counter, "a") as fh:
                fh.write("1\n")
            time.sleep(0.2)
            return TOKEN, 3600

        children = []
        for _ in range(6):
            pid = os.fork()
            if pid == 0:
                status = 0
                try:
                    token_cache._memory.clear()
                    if token_cache.resolve("cold", fetch) != TOKEN:
                        status = 1
                except Exception:
                    status = 2
                finally:
                    os._exit(status)
            children.append(pid)

        failures = []
        for pid in children:
            _, status = os.waitpid(pid, 0)
            failures.append(os.waitstatus_to_exitcode(status))

        assert failures == [0] * 6, failures

        with open(counter) as fh:
            fetches = len([line for line in fh if line.strip()])

        assert fetches == 1, f"expected 1 fetch across 6 forks, got {fetches}"


if __name__ == "__main__":
    sys.exit(unittest.main())
