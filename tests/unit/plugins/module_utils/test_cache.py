from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import ast
import base64
import json
import os
import stat
import tempfile
import unittest
from unittest.mock import patch

from .....plugins.module_utils.cache import (
    cache_dir,
    read_cached_token,
    write_cached_token,
)
from .....plugins.module_utils.errors import LagoonConfigError

_MODULE_PATH = (
    'ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.cache')

# A valid-shaped key: 64 lowercase hex characters, as auth.cache_key()
# produces. Tests must not invent their own shapes except where they are
# deliberately exercising _validate_key().
_KEY = 'a' * 64
_OTHER_KEY = 'b' * 64


def _b64url(raw_bytes):
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b'=').decode('ascii')


def _make_jwt(payload):
    """Hand-build a JWT. Mirrors test_token.py's helper -- no signature is
    ever verified collection-side, so the third segment is arbitrary."""
    header_seg = _b64url(
        json.dumps({'alg': 'none', 'typ': 'JWT'}).encode('utf-8'))
    payload_seg = _b64url(json.dumps(payload).encode('utf-8'))
    return '%s.%s.%s' % (header_seg, payload_seg, 'signature')


def _fresh_token():
    """A well-formed JWT that token_is_valid() will accept. Needed by any
    test going through read_cached_token()'s real validity check."""
    return _make_jwt({'exp': 9999999999, 'sub': 'lagoon'})


class CacheTestCase(unittest.TestCase):
    """Points XDG_CACHE_HOME at a per-test temporary directory.

    This isolation is a hard requirement, not a convenience: cache_dir()
    creates directories and write_cached_token() writes credential files,
    so a test without this seam would litter the developer's real
    ~/.cache/ansible-lagoon. A test that does so is a defect even if it
    passes.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._prev_xdg = os.environ.get('XDG_CACHE_HOME')
        os.environ['XDG_CACHE_HOME'] = self._tmp.name

    def tearDown(self):
        if self._prev_xdg is None:
            os.environ.pop('XDG_CACHE_HOME', None)
        else:
            os.environ['XDG_CACHE_HOME'] = self._prev_xdg
        self._tmp.cleanup()

    def cache_path(self, key=_KEY):
        return os.path.join(
            self._tmp.name, 'ansible-lagoon', 'token-%s.json' % key)


class TestCacheDir(CacheTestCase):

    def test_created_with_mode_0700(self):
        path = cache_dir()
        self.assertTrue(os.path.isdir(path))
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o700)

    def test_uses_xdg_cache_home_when_set(self):
        self.assertEqual(
            cache_dir(),
            os.path.join(self._tmp.name, 'ansible-lagoon'))

    def test_pre_existing_wide_mode_is_narrowed_to_0700(self):
        # makedirs(exist_ok=True) ignores its mode argument entirely for an
        # existing directory, so without the explicit chmod this stays
        # 0755. This test is the only thing proving that chmod is there.
        path = os.path.join(self._tmp.name, 'ansible-lagoon')
        os.makedirs(path, mode=0o755)
        os.chmod(path, 0o755)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o755)

        cache_dir()

        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o700)

    def test_falls_back_to_home_cache_when_xdg_unset(self):
        # Assert on the resolved path string only -- expanduser is patched
        # so nothing is created in the real HOME.
        os.environ.pop('XDG_CACHE_HOME', None)
        fake_home = os.path.join(self._tmp.name, 'fake-home')
        with patch('%s.os.path.expanduser' % _MODULE_PATH,
                   return_value=fake_home):
            path = cache_dir()
        self.assertEqual(
            path, os.path.join(fake_home, '.cache', 'ansible-lagoon'))

    def test_falls_back_to_home_cache_when_xdg_set_but_empty(self):
        # A set-but-empty XDG_CACHE_HOME must not resolve to a CWD-relative
        # 'ansible-lagoon' -- that would scatter credential files wherever
        # ansible-playbook happened to be invoked from.
        os.environ['XDG_CACHE_HOME'] = ''
        fake_home = os.path.join(self._tmp.name, 'fake-home')
        with patch('%s.os.path.expanduser' % _MODULE_PATH,
                   return_value=fake_home):
            path = cache_dir()
        self.assertEqual(
            path, os.path.join(fake_home, '.cache', 'ansible-lagoon'))
        self.assertTrue(os.path.isabs(path))

    def test_resolved_path_is_always_under_the_configured_base(self):
        # The directory is only ever the XDG base or ~/.cache -- never the
        # system temporary directory. Asserted structurally rather than by
        # string-matching the resolved path, because the test harness
        # legitimately points XDG_CACHE_HOME *at* a temp directory.
        self.assertEqual(
            cache_dir(), os.path.join(self._tmp.name, 'ansible-lagoon'))


class TestWritePermissions(CacheTestCase):

    def test_written_file_has_mode_0600(self):
        self.assertTrue(write_cached_token(_KEY, _fresh_token()))
        mode = stat.S_IMODE(os.stat(self.cache_path()).st_mode)
        self.assertEqual(mode, 0o600)

    def test_written_file_lands_at_expected_path(self):
        write_cached_token(_KEY, _fresh_token())
        self.assertTrue(os.path.isfile(self.cache_path()))

    def test_no_temp_orphan_left_after_success(self):
        write_cached_token(_KEY, _fresh_token())
        leftovers = [
            n for n in os.listdir(os.path.join(
                self._tmp.name, 'ansible-lagoon'))
            if n.endswith('.tmp')]
        self.assertEqual(leftovers, [])


class TestRoundTrip(CacheTestCase):
    """Nothing mocked but XDG_CACHE_HOME -- proves the atomic-write/read
    pair works end to end, including the real token_is_valid() check."""

    def test_write_then_read_returns_same_token(self):
        token = _fresh_token()
        self.assertTrue(write_cached_token(_KEY, token))
        self.assertEqual(read_cached_token(_KEY), token)

    def test_independent_keys_do_not_collide(self):
        token_a = _make_jwt({'exp': 9999999999, 'sub': 'a'})
        token_b = _make_jwt({'exp': 9999999999, 'sub': 'b'})
        write_cached_token(_KEY, token_a)
        write_cached_token(_OTHER_KEY, token_b)
        self.assertEqual(read_cached_token(_KEY), token_a)
        self.assertEqual(read_cached_token(_OTHER_KEY), token_b)

    def test_overwrite_replaces_previous_entry(self):
        first = _make_jwt({'exp': 9999999999, 'sub': 'first'})
        second = _make_jwt({'exp': 9999999999, 'sub': 'second'})
        write_cached_token(_KEY, first)
        write_cached_token(_KEY, second)
        self.assertEqual(read_cached_token(_KEY), second)


class TestAtomicity(CacheTestCase):

    def test_replace_failure_leaves_no_file_at_final_path(self):
        with patch('%s.os.replace' % _MODULE_PATH,
                   side_effect=OSError('boom')):
            result = write_cached_token(_KEY, _fresh_token())

        self.assertFalse(result)
        self.assertFalse(os.path.exists(self.cache_path()))

    def test_replace_failure_cleans_up_the_temp_file(self):
        # S4-5: not required by the story (which permits an orphan), but a
        # mode-0600 file holding a live bearer token that nothing will ever
        # read is exactly the credential litter this module bounds.
        with patch('%s.os.replace' % _MODULE_PATH,
                   side_effect=OSError('boom')):
            write_cached_token(_KEY, _fresh_token())

        leftovers = [
            n for n in os.listdir(os.path.join(
                self._tmp.name, 'ansible-lagoon'))
            if n.endswith('.tmp')]
        self.assertEqual(leftovers, [])


class TestReadRefusesUnsafeFiles(CacheTestCase):
    """Ownership/permission checks: refuse as a cache miss, never raise,
    never repair.

    These use **real files with real permission bits** rather than a
    patched ``os.stat``. Patching ``cache.os.stat`` is not a viable seam:
    ``cache.os`` is the ``os`` module itself, so the patch is global and
    breaks ``os.makedirs()``'s own internal ``path.isdir()`` call inside
    ``cache_dir()``. Real bits also test what the story actually asks for
    -- the check, not the mock's shape.
    """

    def _write_valid_entry(self):
        self.assertTrue(write_cached_token(_KEY, _fresh_token()))

    def test_foreign_uid_is_a_miss(self):
        # Patching geteuid rather than stat: a test cannot chown a file to
        # another user without privileges, and geteuid is not used by
        # anything else on this code path.
        self._write_valid_entry()
        with patch('%s.os.geteuid' % _MODULE_PATH,
                   return_value=os.geteuid() + 1):
            self.assertIsNone(read_cached_token(_KEY))

    def test_group_readable_file_is_a_miss(self):
        self._write_valid_entry()
        os.chmod(self.cache_path(), 0o640)
        self.assertIsNone(read_cached_token(_KEY))

    def test_group_writable_file_is_a_miss(self):
        self._write_valid_entry()
        os.chmod(self.cache_path(), 0o620)
        self.assertIsNone(read_cached_token(_KEY))

    def test_other_readable_file_is_a_miss(self):
        self._write_valid_entry()
        os.chmod(self.cache_path(), 0o604)
        self.assertIsNone(read_cached_token(_KEY))

    def test_world_writable_file_is_a_miss(self):
        self._write_valid_entry()
        os.chmod(self.cache_path(), 0o666)
        self.assertIsNone(read_cached_token(_KEY))

    def test_refuses_without_repairing_the_mode(self):
        # The regression this guards: a future contributor "helpfully"
        # normalising the mode. Asserted on observable file state rather
        # than on mock call counts -- os.chmod cannot be patched here
        # (cache_dir() legitimately calls it on the directory), and the
        # state assertion is the stronger claim anyway.
        self._write_valid_entry()
        os.chmod(self.cache_path(), 0o640)

        self.assertIsNone(read_cached_token(_KEY))

        self.assertEqual(
            stat.S_IMODE(os.stat(self.cache_path()).st_mode), 0o640,
            "read path must not silently chmod a credential file -- the "
            "wrong mode is the operator's only signal that something "
            "else touched it")

    def test_refuses_without_deleting_the_file(self):
        self._write_valid_entry()
        os.chmod(self.cache_path(), 0o640)

        self.assertIsNone(read_cached_token(_KEY))

        self.assertTrue(
            os.path.isfile(self.cache_path()),
            "read path must not unlink a refused credential file")

    def test_refused_file_contents_are_left_intact(self):
        self._write_valid_entry()
        before = open(self.cache_path()).read()
        os.chmod(self.cache_path(), 0o640)

        self.assertIsNone(read_cached_token(_KEY))

        self.assertEqual(open(self.cache_path()).read(), before)

    def test_mode_0600_is_accepted(self):
        # Control for the tests above: prove they are rejecting on the
        # permission bits specifically, not failing for some other reason.
        token = _fresh_token()
        write_cached_token(_KEY, token)
        self.assertEqual(
            stat.S_IMODE(os.stat(self.cache_path()).st_mode), 0o600)
        self.assertEqual(read_cached_token(_KEY), token)

    def test_mode_0400_read_only_is_accepted(self):
        # Narrower than 0600 is still safe -- the check is for group/other
        # bits, not an exact-match on 0600.
        token = _fresh_token()
        write_cached_token(_KEY, token)
        os.chmod(self.cache_path(), 0o400)
        self.assertEqual(read_cached_token(_KEY), token)


class TestReadMisses(CacheTestCase):

    def test_absent_file_is_a_miss(self):
        self.assertIsNone(read_cached_token(_KEY))

    def test_expired_token_is_a_miss(self):
        write_cached_token(_KEY, _fresh_token())
        with patch('%s.token_is_valid' % _MODULE_PATH, return_value=False):
            self.assertIsNone(read_cached_token(_KEY))

    def test_genuinely_expired_token_is_a_miss(self):
        # Unmocked: a real JWT with an exp in the past, so the ageing-out
        # mechanism is proven rather than asserted via a patched predicate.
        write_cached_token(_KEY, _make_jwt({'exp': 1, 'sub': 'lagoon'}))
        self.assertIsNone(read_cached_token(_KEY))

    def test_malformed_json_is_a_miss(self):
        cache_dir()
        with open(self.cache_path(), 'w') as f:
            f.write('not json at all')
        os.chmod(self.cache_path(), 0o600)
        self.assertIsNone(read_cached_token(_KEY))

    def test_json_array_instead_of_object_is_a_miss(self):
        cache_dir()
        with open(self.cache_path(), 'w') as f:
            f.write('[]')
        os.chmod(self.cache_path(), 0o600)
        self.assertIsNone(read_cached_token(_KEY))

    def test_object_without_token_field_is_a_miss(self):
        cache_dir()
        with open(self.cache_path(), 'w') as f:
            f.write('{}')
        os.chmod(self.cache_path(), 0o600)
        self.assertIsNone(read_cached_token(_KEY))

    def test_non_string_token_field_is_a_miss(self):
        cache_dir()
        with open(self.cache_path(), 'w') as f:
            f.write(json.dumps({'token': 12345}))
        os.chmod(self.cache_path(), 0o600)
        self.assertIsNone(read_cached_token(_KEY))

    def test_empty_token_field_is_a_miss(self):
        cache_dir()
        with open(self.cache_path(), 'w') as f:
            f.write(json.dumps({'token': ''}))
        os.chmod(self.cache_path(), 0o600)
        self.assertIsNone(read_cached_token(_KEY))

    def test_unresolvable_cache_dir_is_a_miss_not_an_exception(self):
        # A read-only filesystem or an unset/unwritable $HOME (both common
        # in minimal containers) must degrade to a cache miss, not raise a
        # bare OSError out through resolve_token() and past the
        # collection's error taxonomy.
        with patch('%s.cache_dir' % _MODULE_PATH,
                   side_effect=OSError('read-only file system')):
            self.assertIsNone(read_cached_token(_KEY))

    def test_unwritable_cache_base_is_a_miss_not_an_exception(self):
        # Same property via the environment rather than a patch: point the
        # XDG base at a path that cannot be created.
        os.environ['XDG_CACHE_HOME'] = os.path.join(
            self._tmp.name, 'not-a-dir', 'nested')
        with open(os.path.join(self._tmp.name, 'not-a-dir'), 'w') as f:
            f.write('this is a file, not a directory')
        self.assertIsNone(read_cached_token(_KEY))

    def test_unreadable_file_is_a_miss_not_an_exception(self):
        # A file that passes the ownership/mode gate but cannot be opened
        # (mode 0000 -- owner-only bits are all clear, so no group/other
        # bit trips the earlier check). Skipped for root, which bypasses
        # permission checks entirely.
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            self.skipTest('root bypasses file permission checks')
        write_cached_token(_KEY, _fresh_token())
        os.chmod(self.cache_path(), 0o000)
        self.assertIsNone(read_cached_token(_KEY))


class TestWriteFailureIsNotFatal(CacheTestCase):
    """A failed opportunistic cache write must never fail a task whose
    grant already succeeded (S4-4)."""

    def test_mkstemp_failure_returns_false(self):
        with patch('%s.tempfile.mkstemp' % _MODULE_PATH,
                   side_effect=OSError('read-only file system')):
            self.assertFalse(write_cached_token(_KEY, _fresh_token()))

    def test_cache_dir_failure_returns_false(self):
        with patch('%s.cache_dir' % _MODULE_PATH,
                   side_effect=OSError('read-only file system')):
            self.assertFalse(write_cached_token(_KEY, _fresh_token()))

    def test_unwritable_cache_base_returns_false(self):
        # Same property via the environment rather than a patch.
        os.environ['XDG_CACHE_HOME'] = os.path.join(
            self._tmp.name, 'not-a-dir', 'nested')
        with open(os.path.join(self._tmp.name, 'not-a-dir'), 'w') as f:
            f.write('this is a file, not a directory')
        self.assertFalse(write_cached_token(_KEY, _fresh_token()))

    def test_fchmod_failure_returns_false(self):
        with patch('%s.os.fchmod' % _MODULE_PATH,
                   side_effect=OSError('not supported')):
            self.assertFalse(write_cached_token(_KEY, _fresh_token()))

    def test_write_failure_returns_false(self):
        with patch('%s.os.write' % _MODULE_PATH,
                   side_effect=OSError('no space left on device')):
            self.assertFalse(write_cached_token(_KEY, _fresh_token()))


class TestKeyValidation(CacheTestCase):
    """Traversal-shaped and otherwise malformed keys raise
    LagoonConfigError before any filesystem call (S4-3)."""

    def test_read_rejects_traversal_key(self):
        with self.assertRaises(LagoonConfigError):
            read_cached_token('../../etc/passwd')

    def test_write_rejects_traversal_key(self):
        with self.assertRaises(LagoonConfigError):
            write_cached_token('../../etc/passwd', _fresh_token())

    def test_read_rejects_before_any_filesystem_call(self):
        # cache_dir() is the gateway to every filesystem operation on the
        # read path (it resolves *and creates* the directory), so proving
        # it is never reached proves nothing was touched.
        with patch('%s.cache_dir' % _MODULE_PATH) as mock_dir:
            with self.assertRaises(LagoonConfigError):
                read_cached_token('../../etc/passwd')
        mock_dir.assert_not_called()

    def test_read_creates_no_cache_directory_for_a_bad_key(self):
        # Belt and braces on the above, asserted on observable state: a
        # rejected key must not even leave the cache directory behind.
        with self.assertRaises(LagoonConfigError):
            read_cached_token('../../etc/passwd')
        self.assertFalse(
            os.path.exists(os.path.join(self._tmp.name, 'ansible-lagoon')))

    def test_write_rejects_before_any_filesystem_call(self):
        with patch('%s.cache_dir' % _MODULE_PATH) as mock_dir, \
                patch('%s.tempfile.mkstemp' % _MODULE_PATH) as mock_mkstemp:
            with self.assertRaises(LagoonConfigError):
                write_cached_token('../../etc/passwd', _fresh_token())
        mock_dir.assert_not_called()
        mock_mkstemp.assert_not_called()

    def test_rejects_separator_shaped_keys(self):
        for bad in ('a/b', 'a\\b', '..', 'a' * 63 + '/'):
            with self.subTest(key=bad):
                with self.assertRaises(LagoonConfigError):
                    read_cached_token(bad)

    def test_rejects_uppercase_hex(self):
        with self.assertRaises(LagoonConfigError):
            read_cached_token('A' * 64)

    def test_rejects_too_short(self):
        with self.assertRaises(LagoonConfigError):
            read_cached_token('a' * 63)

    def test_rejects_too_long(self):
        with self.assertRaises(LagoonConfigError):
            read_cached_token('a' * 65)

    def test_rejects_empty_string(self):
        with self.assertRaises(LagoonConfigError):
            read_cached_token('')

    def test_rejects_non_hex_characters(self):
        with self.assertRaises(LagoonConfigError):
            read_cached_token('g' * 64)

    def test_rejects_trailing_newline(self):
        # Regression: '^...$' matches immediately before a trailing '\n'
        # as well as at the true end of string, so a naive regex would
        # accept 64 hex chars + '\n' as a valid key. \A/\Z do not have
        # that behaviour. cache_key() itself can never produce this
        # shape, but _validate_key() exists to catch a caller that
        # bypassed cache_key() in the first place.
        with self.assertRaises(LagoonConfigError):
            read_cached_token('a' * 64 + '\n')

    def test_rejects_leading_newline(self):
        with self.assertRaises(LagoonConfigError):
            read_cached_token('\n' + 'a' * 64)

    def test_rejects_embedded_newline(self):
        with self.assertRaises(LagoonConfigError):
            read_cached_token('a' * 32 + '\n' + 'a' * 32)

    def test_rejects_non_string(self):
        for bad in (None, 12345, b'a' * 64, ['a' * 64]):
            with self.subTest(key=bad):
                with self.assertRaises(LagoonConfigError):
                    read_cached_token(bad)

    def test_key_absent_from_error_message(self):
        offending = '../../etc/passwd'
        try:
            read_cached_token(offending)
            self.fail("expected LagoonConfigError")
        except LagoonConfigError as e:
            self.assertNotIn(offending, str(e))

    def test_accepts_a_real_digest_shape(self):
        # Control: prove the allowlist is not rejecting everything. Uses a
        # digest-shaped key that is valid but absent from the cache.
        self.assertIsNone(read_cached_token('0123456789abcdef' * 4))


class TestNoTokenLeakInErrors(CacheTestCase):

    def test_token_absent_from_write_key_error(self):
        secret = 'secret-shaped-token-value'
        try:
            write_cached_token('bad-key', secret)
            self.fail("expected LagoonConfigError")
        except LagoonConfigError as e:
            self.assertNotIn(secret, str(e))


class TestSourceGuardrails(unittest.TestCase):

    @staticmethod
    def _source_path():
        return os.path.normpath(os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..',
            'plugins', 'module_utils', 'cache.py'))

    def test_no_forbidden_imports(self):
        tree = ast.parse(open(self._source_path()).read())
        bad = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                bad += [a.name for a in n.names
                        if a.name.split('.')[0] in
                        ('ansible', 'gql', 'graphql', 'requests')]
            if isinstance(n, ast.ImportFrom) and n.module:
                if n.module.split('.')[0] in \
                        ('ansible', 'gql', 'graphql', 'requests'):
                    bad.append(n.module)
        self.assertEqual(bad, [])

    def test_does_not_import_auth(self):
        # auth.py imports this module; the reverse would be a cycle. The
        # public functions take `key` as a parameter precisely so the
        # value auth.cache_key() produces can be passed in rather than
        # recomputed here.
        tree = ast.parse(open(self._source_path()).read())
        imported = []
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module:
                imported.append(n.module)
            if isinstance(n, ast.Import):
                imported += [a.name for a in n.names]
        self.assertNotIn('auth', imported)
        self.assertNotIn('.auth', imported)

    def test_no_tmp_literal_in_source(self):
        # Enforced by the suite rather than only by a shell grep a
        # reviewer might skip.
        self.assertNotIn('/tmp', open(self._source_path()).read())

    def test_module_has_a_docstring(self):
        # The P2-D11 decision and the no-finally-cleanup rationale live in
        # it; a stray statement-position string would not be reachable as
        # cache.__doc__ and would not survive a docs build.
        tree = ast.parse(open(self._source_path()).read())
        self.assertIsNotNone(ast.get_docstring(tree))


if __name__ == '__main__':
    unittest.main()