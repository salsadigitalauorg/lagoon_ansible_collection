import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from .....plugins.module_utils import token as LagoonToken


def _completed(rc=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=["ssh"], returncode=rc, stdout=stdout, stderr=stderr
    )


class FetchTokenTester(unittest.TestCase):
    def test_nonzero_exit_reports_command_rc_and_stderr(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=255, stderr="Permission denied (publickey)."),
        ):
            rc, token, error = LagoonToken.fetch_token(
                "ssh.lagoon.example", "32222", "", None
            )

        assert rc == 255
        assert token is None
        assert "ssh command:" in error
        assert "exit code: 255" in error
        assert "Permission denied (publickey)" in error

    def test_permission_denied_includes_hint(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=255, stderr="Permission denied (publickey)."),
        ):
            rc, token, error = LagoonToken.fetch_token(
                "ssh.lagoon.example", "32222", "", None
            )

        assert rc != 0
        assert "hint:" in error
        assert "not authorised" in error

    def test_timeout_reports_non_zero_rc_and_duration(self):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=5),
        ):
            rc, token, error = LagoonToken.fetch_token(
                "ssh.lagoon.example", "32222", "", None, timeout=5
            )

        assert rc != 0
        assert token is None
        assert "5s" in error

    def test_missing_ssh_binary_does_not_raise(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("no such file")):
            rc, token, error = LagoonToken.fetch_token(
                "ssh.lagoon.example", "32222", "", None
            )

        assert rc != 0
        assert token is None
        assert error

    def test_non_json_stdout_reports_raw_output(self):
        with patch(
            "subprocess.run",
            return_value=_completed(rc=0, stdout="Welcome to Lagoon\n"),
        ):
            rc, token, error = LagoonToken.fetch_token(
                "ssh.lagoon.example", "32222", "", None
            )

        assert rc != 0
        assert token is None
        assert "Welcome to Lagoon" in error

    def test_missing_access_token_reports_keys_not_values(self):
        payload = json.dumps({"refresh_token": "should-not-appear"})
        with patch(
            "subprocess.run",
            return_value=_completed(rc=0, stdout=payload),
        ):
            rc, token, error = LagoonToken.fetch_token(
                "ssh.lagoon.example", "32222", "", None
            )

        assert rc != 0
        assert token is None
        assert "should-not-appear" not in error
        assert "refresh_token" in error

    def test_successful_grant_returns_token(self):
        payload = json.dumps({"access_token": "abc123", "expires_in": 3600})
        with patch(
            "subprocess.run",
            return_value=_completed(rc=0, stdout=payload),
        ) as run:
            rc, token, error = LagoonToken.fetch_token(
                "ssh.lagoon.example", "32222", "", None
            )

        assert rc == 0
        assert token["access_token"] == "abc123"
        assert error == ""
        assert run.call_args.kwargs["text"] is True

    def test_ssh_options_as_string_and_list_produce_same_argv(self):
        payload = json.dumps({"access_token": "abc123", "expires_in": 3600})
        captured = []

        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            return _completed(rc=0, stdout=payload)

        with patch("subprocess.run", side_effect=fake_run):
            LagoonToken.fetch_token(
                "ssh.lagoon.example", "32222", "-o Foo=bar -o Baz=qux", None
            )
            LagoonToken.fetch_token(
                "ssh.lagoon.example", "32222", ["-o", "Foo=bar", "-o", "Baz=qux"], None
            )

        assert captured[0] == captured[1]

    def test_key_path_added_to_argv(self):
        payload = json.dumps({"access_token": "abc123", "expires_in": 3600})
        with patch("subprocess.run", return_value=_completed(rc=0, stdout=payload)) as run:
            LagoonToken.fetch_token(
                "ssh.lagoon.example", "32222", "", "/tmp/key"
            )

        argv = run.call_args.args[0]
        assert "-i" in argv
        assert "/tmp/key" in argv
