import os
import stat
import unittest

from .....plugins.module_utils import token as LagoonToken
from .....plugins.module_utils.auth import LagoonAuthError
from .test_auth_resolution import AuthTestCase, completed

KEY_CONTENT = "-----BEGIN OPENSSH PRIVATE KEY-----\nkey-material\n"

FIXED_PATH = "/tmp/lagoon_ssh_private_key"


class KeyFileTester(AuthTestCase):
    """Key content goes to a private temporary file, used, then removed.

    The previous implementation wrote it to a fixed /tmp path with
    umask-derived permissions - world-readable on a default umask - in a
    world-writable directory where another user can pre-create or symlink it,
    and never deleted it.
    """

    def observe(self):
        """Record the identity file's path, mode and content during the call."""
        observed = {}

        def run(argv, **kwargs):
            path = argv[argv.index("-i") + 1]
            observed["path"] = path
            observed["mode"] = stat.S_IMODE(os.stat(path).st_mode)
            with open(path) as fh:
                observed["content"] = fh.read()
            return completed()

        self.ssh.side_effect = run
        return observed

    def test_key_content_is_written_to_a_temporary_file(self):
        observed = self.observe()

        self.credentials(ssh_private_key=KEY_CONTENT).token()

        assert observed["content"] == KEY_CONTENT

    def test_the_path_is_not_the_old_fixed_one(self):
        observed = self.observe()

        self.credentials(ssh_private_key=KEY_CONTENT).token()

        assert observed["path"] != FIXED_PATH

    def test_the_path_is_unpredictable(self):
        """A fixed path in a world-writable directory is pre-creatable and
        symlinkable by another user on a shared host."""

        observed_paths = set()
        for _ in range(3):
            observed = self.observe()
            credentials = self.credentials(ssh_private_key=KEY_CONTENT)
            credentials.token()
            observed_paths.add(observed["path"])
            # The cache would otherwise satisfy the next mint, so ssh - and
            # the key file - would never be reached again.
            credentials.invalidate()

        assert len(observed_paths) == 3, observed_paths

    def test_the_mode_is_0600_while_in_use(self):
        observed = self.observe()

        self.credentials(ssh_private_key=KEY_CONTENT).token()

        assert observed["mode"] == 0o600, oct(observed["mode"])

    def test_the_mode_is_0600_under_a_permissive_umask(self):
        """mkstemp creates at 0600 regardless, which is the point of using it
        rather than open-then-chmod."""

        observed = self.observe()
        original = os.umask(0o000)
        try:
            self.credentials(ssh_private_key=KEY_CONTENT).token()
        finally:
            os.umask(original)

        assert observed["mode"] == 0o600, oct(observed["mode"])

    def test_the_file_is_removed_afterwards(self):
        observed = self.observe()

        self.credentials(ssh_private_key=KEY_CONTENT).token()

        assert not os.path.exists(observed["path"])

    def test_the_file_is_removed_even_when_ssh_fails(self):
        observed = {}

        def run(argv, **kwargs):
            observed["path"] = argv[argv.index("-i") + 1]
            # fetch_token drops check=True, so a failed ssh run comes back as
            # a non-zero rc rather than a CalledProcessError.
            return completed(returncode=255, stderr="denied")

        self.ssh.side_effect = run

        with self.assertRaises(LagoonAuthError):
            self.credentials(ssh_private_key=KEY_CONTENT).token()

        assert observed["path"]
        assert not os.path.exists(observed["path"])

    def test_the_file_is_removed_even_when_the_grant_is_unparseable(self):
        observed = {}

        def run(argv, **kwargs):
            observed["path"] = argv[argv.index("-i") + 1]
            return completed(grant={"nothing": "useful"})

        self.ssh.side_effect = run

        with self.assertRaises(LagoonAuthError):
            self.credentials(ssh_private_key=KEY_CONTENT).token()

        assert not os.path.exists(observed["path"])

    def test_no_caller_supplied_path_is_used_for_key_content(self):
        """ssh_private_key_file stays a separate parameter, for keys that
        already exist on disk and are the user's to manage."""

        observed = self.observe()

        self.credentials(
            ssh_private_key=KEY_CONTENT, ssh_private_key_file=FIXED_PATH
        ).token()

        assert observed["path"] != FIXED_PATH
        assert not os.path.exists(FIXED_PATH)

    def test_the_old_helper_is_gone(self):
        """write_ssh_key open()s before it chmod()s, leaving the key
        world-readable in the window between. Its only caller was
        fetch_token, which now goes through LagoonCredentials.grant()."""

        assert not hasattr(LagoonToken, "write_ssh_key")


if __name__ == "__main__":
    unittest.main()
