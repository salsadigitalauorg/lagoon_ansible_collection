from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import ast
import json
import os
import stat
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from .....plugins.module_utils.errors import LagoonAuthError
from .....plugins.module_utils.ssh import request_grant

_MODULE_PATH = (
    'ansible_collections.salsadigitalauorg.lagoon.plugins.module_utils.ssh')


def _grant_response(access_token='the-token', expires_in=3600):
    return MagicMock(
        returncode=0,
        stdout=json.dumps(
            {'access_token': access_token, 'expires_in': expires_in}
        ).encode('utf-8'),
        stderr=b'')


class TestArgvConstruction(unittest.TestCase):

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_representative_argv(self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 32222,
            private_key_file='/home/user/.ssh/id_rsa',
            timeout=15)

        argv = mock_run.call_args.args[0]
        self.assertEqual(argv[0], 'ssh')
        self.assertIn('-p', argv)
        self.assertEqual(argv[argv.index('-p') + 1], '32222')
        self.assertIn('StrictHostKeyChecking=accept-new', argv)
        self.assertIn('ConnectTimeout=15', argv)
        self.assertIn('-i', argv)
        self.assertEqual(
            argv[argv.index('-i') + 1], '/home/user/.ssh/id_rsa')
        self.assertIn('lagoon@lagoon.example.test', argv)
        self.assertEqual(argv[-1], 'grant')

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_custom_ssh_user(self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22,
            private_key_file='/key', ssh_user='custom')
        argv = mock_run.call_args.args[0]
        self.assertIn('custom@lagoon.example.test', argv)

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_shell_never_true(self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22, private_key_file='/key')
        self.assertNotIn('shell', mock_run.call_args.kwargs)
        self.assertFalse(mock_run.call_args.kwargs.get('shell', False))

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_argv_is_a_list_not_a_string(self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22, private_key_file='/key')
        argv = mock_run.call_args.args[0]
        self.assertIsInstance(argv, list)


class TestTempKeyFilePermissions(unittest.TestCase):
    """Uses a real tempfile.mkdtemp() + real file, and os.stat()s it, to
    prove the actual permission bits rather than asserting on a mocked
    call."""

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_temp_dir_created_with_mode_0700(self, mock_run):
        captured = {}
        real_mkdtemp = __import__('tempfile').mkdtemp

        def _spy_mkdtemp(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            # Stat immediately, while the directory still exists -- this
            # is the actual mode-0700 assertion the test name promises,
            # not just a post-hoc "it got cleaned up" check (that is
            # TestCleanup's job).
            captured['dir'] = path
            captured['mode'] = stat.S_IMODE(os.stat(path).st_mode)
            return path

        mock_run.return_value = _grant_response()
        with patch('%s.tempfile.mkdtemp' % _MODULE_PATH,
                   side_effect=_spy_mkdtemp):
            request_grant(
                'lagoon.example.test', 22, private_key='key-material')

        self.assertIn('dir', captured)
        self.assertEqual(captured['mode'], 0o700)

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_key_file_mode_0600_and_dir_mode_0700(self, mock_run):
        seen = {}

        def _capture_argv(argv, **kwargs):
            key_path = argv[argv.index('-i') + 1]
            dir_path = os.path.dirname(key_path)
            seen['dir_mode'] = stat.S_IMODE(os.stat(dir_path).st_mode)
            seen['file_mode'] = stat.S_IMODE(os.stat(key_path).st_mode)
            return _grant_response()

        mock_run.side_effect = _capture_argv
        request_grant(
            'lagoon.example.test', 22, private_key='key-material')

        self.assertEqual(seen['dir_mode'], 0o700)
        self.assertEqual(seen['file_mode'], 0o600)


class TestCleanup(unittest.TestCase):

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_temp_dir_removed_after_success(self, mock_run):
        captured = {}

        def _capture(argv, **kwargs):
            key_path = argv[argv.index('-i') + 1]
            captured['dir'] = os.path.dirname(key_path)
            return _grant_response()

        mock_run.side_effect = _capture
        request_grant(
            'lagoon.example.test', 22, private_key='key-material')

        self.assertFalse(os.path.exists(captured['dir']))

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_temp_dir_removed_after_failure(self, mock_run):
        captured = {}

        def _capture(argv, **kwargs):
            key_path = argv[argv.index('-i') + 1]
            captured['dir'] = os.path.dirname(key_path)
            raise RuntimeError("boom")

        mock_run.side_effect = _capture
        with self.assertRaises(RuntimeError):
            request_grant(
                'lagoon.example.test', 22, private_key='key-material')

        self.assertFalse(os.path.exists(captured['dir']))

    def test_o_excl_failure_surfaces_as_lagoon_auth_error(self):
        import tempfile
        real_mkdtemp = tempfile.mkdtemp

        def _pre_populated_mkdtemp(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            key_path = os.path.join(path, 'lagoon_ssh_key')
            with open(key_path, 'w') as fh:
                fh.write('pre-existing')
            return path

        with patch('%s.tempfile.mkdtemp' % _MODULE_PATH,
                   side_effect=_pre_populated_mkdtemp):
            with self.assertRaises(LagoonAuthError):
                request_grant(
                    'lagoon.example.test', 22,
                    private_key='key-material')

    @patch('%s.os.write' % _MODULE_PATH)
    def test_write_failure_raises_lagoon_auth_error_not_bare_oserror(
            self, mock_write):
        # os.write() failing (e.g. ENOSPC, a full temp filesystem) must
        # surface as the typed LagoonAuthError like the adjacent os.open()
        # failure path above -- not a bare OSError escaping request_grant.
        mock_write.side_effect = OSError(28, 'No space left on device')
        with self.assertRaises(LagoonAuthError) as ctx:
            request_grant(
                'lagoon.example.test', 22, private_key='key-material')
        self.assertNotIsInstance(ctx.exception, OSError)

    def test_write_failure_still_closes_fd_and_removes_temp_dir(self):
        import tempfile
        captured = {}
        real_mkdtemp = tempfile.mkdtemp
        real_open = os.open
        real_close = os.close
        closed_fds = []

        def _spy_mkdtemp(*args, **kwargs):
            path = real_mkdtemp(*args, **kwargs)
            captured['dir'] = path
            return path

        def _spy_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            captured['fd'] = fd
            return fd

        def _spy_close(fd):
            # Delegate to the real os.close() so this test doesn't leak
            # the fd or interfere with fds opened elsewhere in the
            # process (e.g. by pytest-xdist) -- only record the call for
            # our own assertion below.
            closed_fds.append(fd)
            return real_close(fd)

        with patch('%s.tempfile.mkdtemp' % _MODULE_PATH,
                   side_effect=_spy_mkdtemp), \
                patch('%s.os.open' % _MODULE_PATH, side_effect=_spy_open), \
                patch('%s.os.write' % _MODULE_PATH,
                      side_effect=OSError(28, 'No space left on device')), \
                patch('%s.os.close' % _MODULE_PATH,
                      side_effect=_spy_close):
            with self.assertRaises(LagoonAuthError):
                request_grant(
                    'lagoon.example.test', 22, private_key='key-material')

        # fd cleanup (os.close) still ran on the exact fd opened for the
        # key file, despite the write failure, and the temp directory
        # itself was removed by the outer finally.
        self.assertIn(captured['fd'], closed_fds)
        self.assertFalse(os.path.exists(captured['dir']))


class TestSshOptionsParsing(unittest.TestCase):

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_string_ssh_options_parsed_with_shlex(self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22, private_key_file='/key',
            ssh_options='-o "Foo Bar=baz" -4')
        argv = mock_run.call_args.args[0]
        self.assertIn('Foo Bar=baz', argv)
        self.assertIn('-4', argv)

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_list_ssh_options_passed_through_unchanged(self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22, private_key_file='/key',
            ssh_options=['-4', '-o', 'BatchMode=yes'])
        argv = mock_run.call_args.args[0]
        self.assertIn('-4', argv)
        self.assertIn('BatchMode=yes', argv)

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_adversarial_string_ssh_options_does_not_inject_shell(
            self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22, private_key_file='/key',
            ssh_options='; rm -rf /')
        argv = mock_run.call_args.args[0]
        self.assertIsInstance(argv, list)
        self.assertFalse(mock_run.call_args.kwargs.get('shell', False))
        # shlex.split('; rm -rf /') yields literal tokens appended to argv,
        # never executed as shell syntax -- ';' is just a string in the list.
        self.assertIn(';', argv)


class TestStrictHostKeyChecking(unittest.TestCase):

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_default_is_accept_new(self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22, private_key_file='/key')
        argv = mock_run.call_args.args[0]
        self.assertIn('StrictHostKeyChecking=accept-new', argv)

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_no_requires_explicit_opt_in(self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22, private_key_file='/key',
            strict_host_key_checking='no')
        argv = mock_run.call_args.args[0]
        self.assertIn('StrictHostKeyChecking=no', argv)

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_no_never_appears_without_explicit_request(self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22, private_key_file='/key')
        argv = mock_run.call_args.args[0]
        self.assertNotIn('StrictHostKeyChecking=no', argv)


class TestKnownHostsFile(unittest.TestCase):

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_known_hosts_file_passed_when_supplied(self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22, private_key_file='/key',
            known_hosts_file='/home/user/.ssh/known_hosts')
        argv = mock_run.call_args.args[0]
        self.assertIn(
            'UserKnownHostsFile=/home/user/.ssh/known_hosts', argv)

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_no_dev_null_default(self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22, private_key_file='/key')
        argv = mock_run.call_args.args[0]
        joined = ' '.join(argv)
        self.assertNotIn('/dev/null', joined)


class TestTimeout(unittest.TestCase):

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_connect_timeout_and_subprocess_timeout_both_set(
            self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22, private_key_file='/key',
            timeout=42)
        argv = mock_run.call_args.args[0]
        self.assertIn('ConnectTimeout=42', argv)
        self.assertEqual(mock_run.call_args.kwargs.get('timeout'), 42)

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_timeout_expired_raises_lagoon_auth_error_with_value(
            self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=['ssh'], timeout=30)
        with self.assertRaises(LagoonAuthError) as ctx:
            request_grant(
                'lagoon.example.test', 22, private_key_file='/key',
                timeout=30)
        self.assertIn('30', str(ctx.exception))

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_ssh_binary_not_found_raises_lagoon_auth_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        with self.assertRaises(LagoonAuthError):
            request_grant(
                'lagoon.example.test', 22, private_key_file='/key')


class TestNonZeroExitCode(unittest.TestCase):

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_stderr_included_truncated(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout=b'', stderr=b'permission denied' * 50)
        with self.assertRaises(LagoonAuthError) as ctx:
            request_grant(
                'lagoon.example.test', 22, private_key_file='/key')
        message = str(ctx.exception)
        self.assertIn('permission denied', message)
        self.assertLessEqual(len(message), 600)

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_key_content_absent_from_error_message_even_if_echoed(
            self, mock_run):
        secret_key = 'MIIsecretkeymateriallooksliketh1s'
        mock_run.return_value = MagicMock(
            returncode=1, stdout=b'',
            stderr=('some unrelated error, not %s' % secret_key).encode())
        with self.assertRaises(LagoonAuthError) as ctx:
            request_grant(
                'lagoon.example.test', 22, private_key=secret_key)
        # We assert the *key material passed to request_grant* never
        # appears verbatim -- the stderr text above intentionally does
        # not include it either, proving the collection doesn't
        # reintroduce it via some other path (e.g. re-reading the temp
        # file into an error message).
        self.assertNotIn(secret_key, str(ctx.exception))


class TestMalformedGrantResponse(unittest.TestCase):

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_non_json_stdout_raises_distinct_message(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=b'not json at all', stderr=b'')
        with self.assertRaises(LagoonAuthError) as ctx:
            request_grant(
                'lagoon.example.test', 22, private_key_file='/key')
        self.assertIn('unexpected grant response', str(ctx.exception))

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_missing_access_token_raises_distinct_message(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({'expires_in': 3600}).encode(), stderr=b'')
        with self.assertRaises(LagoonAuthError) as ctx:
            request_grant(
                'lagoon.example.test', 22, private_key_file='/key')
        self.assertIn('malformed grant response', str(ctx.exception))

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_missing_expires_in_raises_distinct_message(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({'access_token': 'tok'}).encode(), stderr=b'')
        with self.assertRaises(LagoonAuthError) as ctx:
            request_grant(
                'lagoon.example.test', 22, private_key_file='/key')
        self.assertIn('malformed grant response', str(ctx.exception))

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_json_array_instead_of_object_is_malformed(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout=b'[1, 2, 3]', stderr=b'')
        with self.assertRaises(LagoonAuthError):
            request_grant(
                'lagoon.example.test', 22, private_key_file='/key')

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_well_formed_response_returns_token_and_expiry(self, mock_run):
        mock_run.return_value = _grant_response(
            access_token='abc123', expires_in=7200)
        token, expires_in = request_grant(
            'lagoon.example.test', 22, private_key_file='/key')
        self.assertEqual(token, 'abc123')
        self.assertEqual(expires_in, 7200)


class TestPrivateKeyFileDirectNoCopy(unittest.TestCase):

    @patch('%s.subprocess.run' % _MODULE_PATH)
    @patch('%s.tempfile.mkdtemp' % _MODULE_PATH)
    def test_no_temp_file_created_when_private_key_file_given(
            self, mock_mkdtemp, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22, private_key_file='/home/user/key')
        mock_mkdtemp.assert_not_called()

    @patch('%s.subprocess.run' % _MODULE_PATH)
    def test_private_key_file_path_used_as_is(self, mock_run):
        mock_run.return_value = _grant_response()
        request_grant(
            'lagoon.example.test', 22,
            private_key_file='/home/user/my-key')
        argv = mock_run.call_args.args[0]
        self.assertEqual(argv[argv.index('-i') + 1], '/home/user/my-key')


class TestNoForbiddenImports(unittest.TestCase):

    def test_forbidden_imports_absent(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..',
            'plugins', 'module_utils', 'ssh.py')
        path = os.path.normpath(path)
        tree = ast.parse(open(path).read())
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
                if n.module == 'ansible.errors':
                    bad.append(n.module)
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
