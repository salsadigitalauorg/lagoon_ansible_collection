import os
import unittest
from unittest.mock import patch

from .....plugins.module_utils import token_cache
from .test_auth_resolution import AuthTestCase, completed


class TokenCachingTester(AuthTestCase):
    """Ansible forks a worker per host per task, so an uncached mint would be
    one `ssh ... grant` per host per task."""

    def test_one_grant_for_many_token_calls(self):
        credentials = self.credentials()

        for _ in range(5):
            assert credentials.token() == "minted-token"

        assert self.ssh.call_count == 1

    def test_one_grant_across_separate_credentials_objects(self):
        """Each fork builds its own client, so sharing has to survive that."""

        for _ in range(3):
            assert self.credentials().token() == "minted-token"

        assert self.ssh.call_count == 1

    def test_a_refetch_once_past_the_expiry_window(self):
        self.ssh.return_value = completed(
            grant={
                "access_token": "short-lived",
                "expires_in": token_cache.EXPIRY_SKEW - 1,
            }
        )
        credentials = self.credentials()

        credentials.token()
        credentials.token()

        assert self.ssh.call_count == 2

    def test_no_refetch_while_the_token_is_good(self):
        self.ssh.return_value = completed(
            grant={"access_token": "long-lived", "expires_in": 3600}
        )
        credentials = self.credentials()

        credentials.token()
        credentials.token()

        assert self.ssh.call_count == 1

    def test_invalidate_forces_the_next_call_to_refetch(self):
        credentials = self.credentials()

        credentials.token()
        credentials.invalidate()
        credentials.token()

        assert self.ssh.call_count == 2

    def test_an_explicit_token_is_never_cached(self):
        """We do not know its expiry and are not responsible for its
        lifecycle, so it is neither read through nor written through."""

        credentials = self.credentials(token="supplied-token")
        credentials.token()

        assert token_cache._memory == {}
        cache_dir = token_cache.cache_dir()
        assert not os.path.isdir(cache_dir) or os.listdir(cache_dir) == []

    def test_invalidate_is_a_no_op_for_an_explicit_token(self):
        credentials = self.credentials(token="supplied-token")

        credentials.invalidate()

        assert credentials.token() == "supplied-token"
        self.ssh.assert_not_called()

    def test_two_endpoints_do_not_share_a_token(self):
        self.ssh.side_effect = [
            completed(grant={"access_token": "token-a", "expires_in": 3600}),
            completed(grant={"access_token": "token-b", "expires_in": 3600}),
        ]

        a = self.credentials(endpoint="https://a.example.com/graphql")
        b = self.credentials(endpoint="https://b.example.com/graphql")

        assert a.token() == "token-a"
        assert b.token() == "token-b"
        assert self.ssh.call_count == 2

    def test_two_identities_do_not_share_a_token(self):
        self.ssh.side_effect = [
            completed(grant={"access_token": "token-a", "expires_in": 3600}),
            completed(grant={"access_token": "token-b", "expires_in": 3600}),
        ]

        a = self.credentials(ssh_private_key_file="/keys/a")
        b = self.credentials(ssh_private_key_file="/keys/b")

        assert a.token() == "token-a"
        assert b.token() == "token-b"

    def test_the_cache_key_carries_no_credential_material(self):
        key_content = "-----BEGIN OPENSSH PRIVATE KEY-----\nsecret-material"
        key = self.credentials(ssh_private_key=key_content).cache_key()

        assert "secret-material" not in key
        assert "BEGIN" not in key

    def test_the_opt_out_keeps_the_token_off_disk(self):
        with patch.dict(os.environ, {"LAGOON_TOKEN_CACHE": "0"}):
            credentials = self.credentials()
            credentials.token()

            cache_dir = token_cache.cache_dir()
            assert not os.path.isdir(cache_dir) or os.listdir(cache_dir) == []

    def test_a_grant_without_expires_in_is_not_cached(self):
        self.ssh.return_value = completed(grant={"access_token": "no-expiry"})
        credentials = self.credentials()

        credentials.token()
        credentials.token()

        assert self.ssh.call_count == 2


if __name__ == "__main__":
    unittest.main()
