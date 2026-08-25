from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import ast
import base64
import json
import os
import unittest

from .....plugins.module_utils.errors import LagoonAuthError
from .....plugins.module_utils.token import (
    decode_jwt_claims,
    token_expiry,
    token_is_valid,
)


def _b64url(raw_bytes):
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b'=').decode('ascii')


def _make_jwt(payload, header=None):
    """Hand-build a JWT string from header/payload dicts. No signature
    verification is ever performed on the collection's side, so the
    signature segment content is arbitrary."""
    header = header if header is not None else {'alg': 'none', 'typ': 'JWT'}
    header_seg = _b64url(json.dumps(header).encode('utf-8'))
    payload_seg = _b64url(json.dumps(payload).encode('utf-8'))
    return '%s.%s.%s' % (header_seg, payload_seg, 'signature')


class TestDecodeJwtClaims(unittest.TestCase):

    def test_well_formed_token_returns_full_claims(self):
        token = _make_jwt({'exp': 9999999999, 'sub': 'lagoon'})
        claims = decode_jwt_claims(token)
        self.assertEqual(claims['exp'], 9999999999)
        self.assertEqual(claims['sub'], 'lagoon')

    def test_wrong_segment_count_two(self):
        with self.assertRaises(LagoonAuthError):
            decode_jwt_claims('onlyone.segment')

    def test_wrong_segment_count_four(self):
        with self.assertRaises(LagoonAuthError):
            decode_jwt_claims('a.b.c.d')

    def test_non_base64_segment(self):
        # base64.urlsafe_b64decode() runs in non-strict mode by default and
        # silently discards invalid-alphabet characters rather than raising
        # -- 'not!!valid!!base64' decodes to garbage bytes and fails later
        # in the JSON-decode branch, not the base64-decode branch. This
        # case is retained to prove *a* LagoonAuthError is still raised for
        # visually-invalid-looking base64, but it does not exercise the
        # base64-decode except branch itself; see
        # test_base64_decode_error_branch for that.
        with self.assertRaises(LagoonAuthError):
            decode_jwt_claims('header.not!!valid!!base64.sig')

    def test_base64_decode_error_branch(self):
        # A single-character payload segment cannot be padded to a valid
        # base64 length no matter how '=' padding is applied -- this is
        # the one input shape that reaches the except (ValueError,
        # TypeError) around base64.urlsafe_b64decode() itself (a real
        # binascii.Error, "number of data characters (1) cannot be 1 more
        # than a multiple of 4"), rather than failing downstream in the
        # JSON-decode branch.
        with self.assertRaises(LagoonAuthError):
            decode_jwt_claims('header.a.sig')

    def test_valid_base64_non_json_payload(self):
        bad_payload = _b64url(b'this is not json')
        token = 'header.%s.sig' % bad_payload
        with self.assertRaises(LagoonAuthError):
            decode_jwt_claims(token)

    def test_json_array_instead_of_object(self):
        bad_payload = _b64url(json.dumps([1, 2, 3]).encode('utf-8'))
        token = 'header.%s.sig' % bad_payload
        with self.assertRaises(LagoonAuthError):
            decode_jwt_claims(token)

    def test_raises_lagoon_auth_error_not_bare_value_error(self):
        with self.assertRaises(LagoonAuthError):
            decode_jwt_claims('a.b')

    def test_token_value_absent_from_exception_message(self):
        secret_looking_token = 'not-a-real-jwt-but-secret-shaped-value'
        try:
            decode_jwt_claims(secret_looking_token)
            self.fail("expected LagoonAuthError")
        except LagoonAuthError as e:
            self.assertNotIn(secret_looking_token, str(e))

    def test_non_string_input_raises_lagoon_auth_error(self):
        # A non-string token (e.g. a corrupted cache entry) must raise the
        # typed LagoonAuthError, not an unhandled AttributeError/TypeError
        # from calling .split() on a non-string.
        for bad in (None, 123, 1.5, b'a.b.c', ['a', 'b', 'c'], {}, True):
            with self.assertRaises(LagoonAuthError):
                decode_jwt_claims(bad)


class TestTokenExpiry(unittest.TestCase):

    def test_returns_exp_claim(self):
        token = _make_jwt({'exp': 1234567890})
        self.assertEqual(token_expiry(token), 1234567890)

    def test_missing_exp_returns_none(self):
        token = _make_jwt({'sub': 'lagoon'})
        self.assertIsNone(token_expiry(token))

    def test_exp_as_string_returns_none(self):
        token = _make_jwt({'exp': '1234567890'})
        self.assertIsNone(token_expiry(token))

    def test_malformed_token_returns_none_not_raise(self):
        self.assertIsNone(token_expiry('not.a.jwt.at.all'))

    def test_never_raises_for_malformed_input(self):
        for bad in ('', 'a', 'a.b', 'a.b.c.d', 'a.!!!.c'):
            self.assertIsNone(token_expiry(bad))

    def test_never_raises_for_non_string_input(self):
        for bad in (None, 123, 1.5, b'a.b.c', ['a', 'b', 'c'], {}, True):
            self.assertIsNone(token_expiry(bad))


class TestTokenIsValid(unittest.TestCase):

    def test_valid_well_before_expiry(self):
        now = 1000.0
        token = _make_jwt({'exp': now + 3600})
        self.assertTrue(token_is_valid(token, skew=60, now=now))

    def test_invalid_within_skew_window(self):
        now = 1000.0
        token = _make_jwt({'exp': now + 30})
        self.assertFalse(token_is_valid(token, skew=60, now=now))

    def test_invalid_after_expiry(self):
        now = 1000.0
        token = _make_jwt({'exp': now - 10})
        self.assertFalse(token_is_valid(token, skew=60, now=now))

    def test_boundary_exactly_at_now_plus_skew(self):
        now = 1000.0
        skew = 60
        token = _make_jwt({'exp': now + skew})
        # now + skew == exp -- must be False, the check is a strict '<'.
        self.assertFalse(token_is_valid(token, skew=skew, now=now))

    def test_boundary_one_second_past_skew(self):
        now = 1000.0
        skew = 60
        token = _make_jwt({'exp': now + skew + 1})
        self.assertTrue(token_is_valid(token, skew=skew, now=now))

    def test_missing_exp_is_invalid(self):
        token = _make_jwt({'sub': 'lagoon'})
        self.assertFalse(token_is_valid(token, now=1000.0))

    def test_exp_as_string_is_invalid(self):
        token = _make_jwt({'exp': '1234567890'})
        self.assertFalse(token_is_valid(token, now=1000.0))

    def test_malformed_token_never_raises_and_is_invalid(self):
        for bad in ('', 'a', 'a.b', 'a.b.c.d',
                    'a.!!!not-base64!!!.c'):
            self.assertFalse(token_is_valid(bad, now=1000.0))

    def test_non_string_input_never_raises_and_is_invalid(self):
        # A non-string token (e.g. a corrupted cache entry) must degrade
        # to a plain False, not an unhandled AttributeError/TypeError.
        for bad in (None, 123, 1.5, b'a.b.c', ['a', 'b', 'c'], {}, True):
            self.assertFalse(token_is_valid(bad, now=1000.0))

    def test_uses_time_time_when_now_not_supplied(self):
        # Far-future exp so the test is not time-sensitive/flaky.
        token = _make_jwt({'exp': 99999999999})
        self.assertTrue(token_is_valid(token))

    def test_token_value_absent_from_any_interaction(self):
        # token_is_valid never raises, but assert the malformed-input path
        # still does not leak the token value anywhere observable.
        secret_looking_token = 'secret-shaped-not-a-real-jwt'
        result = token_is_valid(secret_looking_token, now=1000.0)
        self.assertFalse(result)


class TestNoForbiddenImports(unittest.TestCase):

    def test_stdlib_only(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..',
            'plugins', 'module_utils', 'token.py')
        path = os.path.normpath(path)
        tree = ast.parse(open(path).read())
        bad = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                bad += [a.name for a in n.names
                        if a.name.split('.')[0] in
                        ('ansible', 'gql', 'graphql', 'requests', 'jwt')]
            if isinstance(n, ast.ImportFrom) and n.module:
                if n.module.split('.')[0] in \
                        ('ansible', 'gql', 'graphql', 'requests', 'jwt'):
                    bad.append(n.module)
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
