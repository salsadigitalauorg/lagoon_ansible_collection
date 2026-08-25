from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import base64
import json
import time

from .errors import LagoonAuthError

_NUMERIC_TYPES = (int, float)


def decode_jwt_claims(token):
    """Decode and return the JWT payload (2nd segment) as a dict.

    No signature verification -- the collection is the bearer, not the
    verifier; the Lagoon API validates the signature server-side.

    Raises :class:`LagoonAuthError` if the token is not a well-formed JWT:
    wrong segment count, unpadded/invalid base64url, or a payload that is
    not a JSON object. The raw token value never appears in the exception
    message -- only the shape of the problem is described.

    This applies only to tokens the collection itself cached after an SSH
    grant (resolution order step 3, plan 7.2). An explicit
    ``lagoon_api_token`` module parameter or ``LAGOON_API_TOKEN`` env var
    (steps 1-2) is used as-is and must never be passed through this
    function -- there is no sensible recovery if it looked invalid, since
    re-granting would silently discard the operator's explicit token.
    """
    if not isinstance(token, str):
        raise LagoonAuthError(
            "malformed JWT: expected a string, got %s" %
            type(token).__name__)

    segments = token.split('.')
    if len(segments) != 3:
        raise LagoonAuthError(
            "malformed JWT: expected 3 dot-separated segments, got %d" %
            len(segments))

    payload_segment = segments[1]
    padded = payload_segment + '=' * (-len(payload_segment) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded)
    except (ValueError, TypeError):
        raise LagoonAuthError(
            "malformed JWT: payload segment is not valid base64url")

    try:
        claims = json.loads(decoded)
    except ValueError:
        raise LagoonAuthError(
            "malformed JWT: payload segment is not valid JSON")

    if not isinstance(claims, dict):
        raise LagoonAuthError(
            "malformed JWT: payload is not a JSON object")

    return claims


def token_expiry(token):
    """Return the JWT's ``exp`` claim as an int/float, or ``None`` if the
    token is malformed or the claim is absent/non-numeric.

    Never raises -- this is a best-effort freshness lookup, not a source
    of truth.
    """
    try:
        claims = decode_jwt_claims(token)
    except LagoonAuthError:
        return None

    exp = claims.get('exp')
    if not isinstance(exp, _NUMERIC_TYPES) or isinstance(exp, bool):
        return None

    return exp


def token_is_valid(token, skew=60, now=None):
    """True if ``token`` decodes, has a numeric ``exp`` claim, and
    ``now + skew < exp``.

    False for anything that cannot be proven fresh: a malformed token, a
    missing/non-numeric ``exp``, or an ``exp`` within the skew window
    (deliberately more conservative than a bare ``exp`` comparison -- a
    token expiring in 30s with a 60s skew must not be treated as usable
    for the remainder of a task).

    ``now`` is injectable (defaults to :func:`time.time`) so tests never
    depend on wall-clock time.

    Never raises -- this is a predicate. Every :class:`LagoonAuthError`
    that :func:`decode_jwt_claims`/:func:`token_expiry` would raise is
    swallowed here and reported as ``False``.
    """
    exp = token_expiry(token)
    if exp is None:
        return False

    if now is None:
        now = time.time()

    return now + skew < exp
