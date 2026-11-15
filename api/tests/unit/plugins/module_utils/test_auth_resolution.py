import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from .....plugins.module_utils import token as LagoonToken
from .....plugins.module_utils import token_cache
from .....plugins.module_utils.auth import (
    DEFAULT_SSH_HOST,
    DEFAULT_SSH_PORT,
    LagoonAuthError,
    LagoonCredentials,
)

GRANT = {"access_token": "minted-token", "expires_in": 3600}


def completed(grant=None, returncode=0, stderr=""):
    """A finished ssh run.

    stdout and stderr are str, not bytes: fetch_token calls subprocess.run
    with text=True, and its failure diagnostics substring-match on stderr,
    which raises TypeError when handed bytes.
    """
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = returncode
    result.stdout = json.dumps(grant if grant is not None else GRANT)
    result.stderr = stderr
    return result


class AuthTestCase(unittest.TestCase):
    """Isolated from the developer's own environment and token cache.

    LAGOON_API_TOKEN in particular would otherwise satisfy precedence 1 and
    quietly make every other case untested.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {"LAGOON_TOKEN_CACHE_DIR": os.path.join(self.tmp.name, "cache")},
            clear=True,
        )
        self.env.start()
        token_cache._memory.clear()
        self.addCleanup(token_cache._memory.clear)
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)

        self.run = patch.object(LagoonToken.subprocess, "run", return_value=completed())
        self.ssh = self.run.start()
        self.addCleanup(self.run.stop)

    def argv(self):
        return self.ssh.call_args.args[0]

    def credentials(self, **kwargs):
        kwargs.setdefault("endpoint", "https://api.example.com/graphql")
        return LagoonCredentials(**kwargs)


class PrecedenceTester(AuthTestCase):
    def test_1_an_explicit_token_is_used_verbatim(self):
        """No ssh at all: we did not mint it, and cannot refresh it."""

        credentials = self.credentials(token="supplied-token")

        assert credentials.token() == "supplied-token"
        self.ssh.assert_not_called()

    def test_1_the_environment_variable_is_also_precedence_1(self):
        with patch.dict(os.environ, {"LAGOON_API_TOKEN": "env-token"}):
            credentials = self.credentials()

            assert credentials.token() == "env-token"
            self.ssh.assert_not_called()

    def test_1_an_explicit_token_beats_a_supplied_key(self):
        credentials = self.credentials(
            token="supplied-token", ssh_private_key="key-content"
        )

        assert credentials.token() == "supplied-token"
        self.ssh.assert_not_called()

    def test_2_key_content_is_passed_as_a_temporary_identity_file(self):
        credentials = self.credentials(ssh_private_key="key-content")

        assert credentials.token() == "minted-token"

        argv = self.argv()
        assert "-i" in argv
        identity = argv[argv.index("-i") + 1]
        assert identity != "/tmp/lagoon_ssh_private_key"
        assert "key-content" not in argv

    def test_2_key_content_beats_a_key_file(self):
        credentials = self.credentials(
            ssh_private_key="key-content", ssh_private_key_file="/keys/id_rsa"
        )
        credentials.token()

        argv = self.argv()
        assert argv[argv.index("-i") + 1] != "/keys/id_rsa"

    def test_3_a_key_file_path_is_passed_to_ssh_i(self):
        credentials = self.credentials(ssh_private_key_file="/keys/id_rsa")

        assert credentials.token() == "minted-token"
        argv = self.argv()
        assert argv[argv.index("-i") + 1] == "/keys/id_rsa"

    def test_4_nothing_supplied_runs_ssh_with_no_identity(self):
        """The new default, and the reason the collection works with no
        credential configuration: ssh falls back to the machine's own
        ~/.ssh/config, IdentityFile and agent."""

        credentials = self.credentials()

        assert credentials.token() == "minted-token"
        assert "-i" not in self.argv()


class SshInvocationTester(AuthTestCase):
    def test_host_and_port_reach_the_command(self):
        self.credentials(ssh_host="ssh.example.com", ssh_port="2222").token()

        argv = self.argv()
        assert argv[:3] == ["ssh", "-p", "2222"]
        assert argv[-2:] == ["lagoon@ssh.example.com", "grant"]

    def test_defaults_are_the_public_lagoon(self):
        credentials = self.credentials()
        assert credentials.ssh_host == DEFAULT_SSH_HOST
        assert credentials.ssh_port == DEFAULT_SSH_PORT

        credentials.token()
        assert f"lagoon@{DEFAULT_SSH_HOST}" in self.argv()

    def test_host_key_checking_is_not_disabled_by_default(self):
        """Previously every caller passed StrictHostKeyChecking=no, so the
        connection minting the API token did not verify it was talking to
        Lagoon. Passing no options leaves the user's known_hosts in force."""

        self.credentials().token()

        joined = " ".join(self.argv())
        assert "StrictHostKeyChecking" not in joined
        assert "UserKnownHostsFile" not in joined

    def test_only_the_forwarding_hardening_is_injected_by_default(self):
        """Nothing is added to the user's own ssh configuration except the
        forwarding and terminal options, which are not the caller's to relax.

        Anything else appearing here would be a decision taken away from the
        machine's ~/.ssh/config, which the no-options default exists to honour.
        """

        self.credentials().token()

        argv = self.argv()
        injected = {argv[i + 1] for i, a in enumerate(argv) if a == "-o"}
        assert injected == {
            "ForwardAgent=no",
            "ClearAllForwardings=yes",
            "ForwardX11=no",
            "RequestTTY=no",
        }


class FailureTester(AuthTestCase):
    def test_a_failing_ssh_call_raises(self):
        """fetch_token reports a failed ssh run, it does not raise.

        It drops check=True, so a non-zero exit comes back as an rc plus a
        diagnostic string rather than a CalledProcessError.
        """
        self.ssh.return_value = completed(
            returncode=255, stderr="Permission denied (publickey)."
        )

        with self.assertRaises(LagoonAuthError) as caught:
            self.credentials().token()

        message = str(caught.exception)
        assert "Permission denied" in message
        # fetch_token's hint lookup should also have fired for this stderr.
        assert "not authorised" in message

    def test_a_non_zero_return_code_raises(self):
        self.ssh.return_value = completed(returncode=3)

        with self.assertRaises(LagoonAuthError):
            self.credentials().token()

    def test_an_unparseable_grant_raises(self):
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = 0
        result.stdout = "not json at all"
        result.stderr = ""
        self.ssh.return_value = result

        with self.assertRaises(LagoonAuthError):
            self.credentials().token()

    def test_a_grant_with_no_access_token_raises(self):
        self.ssh.return_value = completed(grant={"expires_in": 3600})

        with self.assertRaises(LagoonAuthError) as caught:
            self.credentials().token()

        assert "access_token" in str(caught.exception)

    def test_ssh_not_being_installed_raises_cleanly(self):
        self.ssh.side_effect = FileNotFoundError("no ssh")

        with self.assertRaises(LagoonAuthError):
            self.credentials().token()

    def test_the_error_does_not_carry_the_token(self):
        self.ssh.return_value = completed(returncode=255, stderr="denied")

        with self.assertRaises(LagoonAuthError) as caught:
            self.credentials(ssh_private_key="key-content").token()

        assert "key-content" not in str(caught.exception)


class SecretRegistrationTester(AuthTestCase):
    def test_a_minted_token_is_registered_as_a_secret(self):
        """Registered the moment it exists, so it stays masked even if a
        later request or traceback is dumped."""

        with patch(
            "ansible_collections.lagoon.api.plugins.module_utils.auth.register_secret"
        ) as register:
            self.credentials().token()

        assert "minted-token" in [c.args[0] for c in register.call_args_list]

    def test_an_explicit_token_is_registered_too(self):
        with patch(
            "ansible_collections.lagoon.api.plugins.module_utils.auth.register_secret"
        ) as register:
            self.credentials(token="supplied-token")

        register.assert_called_once_with("supplied-token")
