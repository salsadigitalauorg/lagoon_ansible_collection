from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json
import re
import socket
import ssl
import time

from ansible.module_utils.six.moves.urllib.error import HTTPError, URLError
from ansible.module_utils._text import to_bytes, to_native, to_text
from ansible.module_utils.urls import (
    ConnectionError as AnsibleURLConnectionError,
    SSLValidationError,
    fetch_url,
    open_url,
)

from .errors import (
    LagoonAPIError,
    LagoonAuthError,
    LagoonConfigError,
    LagoonTransportError,
)

_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_FIELD_FORBIDDEN_RE = re.compile(r'[{}\s(]')

_USER_AGENT = 'ansible-collection-salsadigitalauorg.lagoon'


class _TransportFailure(Exception):
    """Internal signal: a connection-level failure occurred with no HTTP
    response at all. Retryable. Never escapes LagoonClient.execute()."""


class _SSLFailure(Exception):
    """Internal signal: TLS/certificate validation failed. Never retryable.
    Never escapes LagoonClient.execute()."""


class LagoonClient:
    """A single HTTP/GraphQL client for the Lagoon API.

    Uses only ``ansible-core``'s own URL helpers -- no ``gql``, no
    ``graphql-core``, no ``requests``. Builds and sends flat, single-level
    GraphQL documents and translates every failure mode into one of the
    typed exceptions in :mod:`.errors`.

    Stateless beyond its constructor arguments: no caching, no schema
    introspection. Token caching (``auth.py``) and lookup caching are
    layered on top of this class, not inside it.
    """

    _sleep = staticmethod(time.sleep)

    def __init__(self, endpoint, token, module=None, validate_certs=True,
                 timeout=30, retries=3, headers=None):
        if not endpoint:
            raise LagoonConfigError("endpoint is required")
        if not token:
            raise LagoonConfigError("token is required")
        if headers is not None and not isinstance(headers, dict):
            raise LagoonConfigError("headers must be a dict")

        self.endpoint = endpoint
        self.token = token
        self.module = module
        self.validate_certs = validate_certs
        self.timeout = timeout
        self.retries = retries
        self.headers = dict(headers) if headers else {}

    def __repr__(self):
        return "LagoonClient(endpoint=%r, token='***redacted***', validate_certs=%r)" % (
            self.endpoint, self.validate_certs)

    # -- Public surface -----------------------------------------------

    def execute(self, query, variables=None):
        """POST the document. Returns the ``data`` object. Raises on any
        failure."""
        if not self.endpoint or not self.token:
            raise LagoonConfigError("endpoint and token are required")

        payload = {'query': query, 'variables': variables or {}}
        data_bytes = to_bytes(json.dumps(payload))

        attempt = 0
        while True:
            try:
                status, body_bytes = self._transport_call(data_bytes)
            except _SSLFailure as e:
                raise LagoonTransportError(
                    "Lagoon API TLS validation failed: %s" % to_native(e))
            except _TransportFailure as e:
                if attempt < self.retries:
                    self._sleep(self._backoff(attempt))
                    attempt += 1
                    continue
                raise LagoonTransportError(
                    "Lagoon API request failed: %s" % to_native(e))
            else:
                if status >= 500:
                    if attempt < self.retries:
                        self._sleep(self._backoff(attempt))
                        attempt += 1
                        continue
                    raise LagoonTransportError(
                        "Lagoon API returned HTTP %d" % status)
                return self._handle_response(
                    status, body_bytes, query, variables)

    @staticmethod
    def build_query(operation, *, fields, args=None, operation_type='query',
                     operation_name=None):
        """Build a FLAT single-level GraphQL document.

        ``args`` maps GraphQL variable name -> GraphQL type, e.g.
        ``{'name': 'String!'}``. ``fields`` is a list of scalar field names.
        No nesting is permitted.

        ``fields=[]`` is accepted and emits no selection set at all -- some
        mutations return a scalar (e.g. ``deleteProject`` returns
        ``String``), and this client has no access to the SDL to know
        whether a selection set is required.
        """
        if operation_type not in ('query', 'mutation'):
            raise LagoonConfigError(
                "operation_type must be 'query' or 'mutation', got %r" %
                (operation_type,))

        if not operation or not _IDENTIFIER_RE.match(operation):
            raise LagoonConfigError("invalid operation name %r" % (operation,))

        op_name = operation_name if operation_name is not None else operation
        if not _IDENTIFIER_RE.match(op_name):
            raise LagoonConfigError(
                "invalid operation_name %r" % (op_name,))

        args = args or {}
        arg_names = sorted(args.keys())
        for name in arg_names:
            if not _IDENTIFIER_RE.match(name):
                raise LagoonConfigError("invalid argument name %r" % (name,))

        if fields is None:
            fields = []
        for field in fields:
            if not isinstance(field, str) or not field or \
                    _FIELD_FORBIDDEN_RE.search(field):
                raise LagoonConfigError(
                    "invalid field %r: fields must be plain scalar names, "
                    "no braces, parentheses or whitespace" % (field,))

        if arg_names:
            var_decls = ', '.join(
                '$%s: %s' % (name, args[name]) for name in arg_names)
            field_args = ', '.join(
                '%s: $%s' % (name, name) for name in arg_names)
            header = '%s %s(%s)' % (operation_type, op_name, var_decls)
            call = '%s(%s)' % (operation, field_args)
        else:
            header = '%s %s' % (operation_type, op_name)
            call = operation

        if fields:
            selection = ' { %s }' % ' '.join(fields)
        else:
            selection = ''

        return '%s { %s%s }' % (header, call, selection)

    # -- Internal: retry/backoff ---------------------------------------

    def _backoff(self, attempt):
        return min(0.5 * (2 ** attempt), 8)

    # -- Internal: response handling ------------------------------------

    def _handle_response(self, status, body_bytes, query, variables):
        if status in (401, 403):
            raise LagoonAuthError(
                "Lagoon API authentication failed (HTTP %d)" % status)

        text = to_text(body_bytes or b'')
        try:
            parsed = json.loads(text) if text else None
        except ValueError:
            excerpt = text[:200]
            raise LagoonAPIError(
                [], query=query, variables=variables,
                message="Lagoon API returned non-JSON response "
                        "(HTTP %d): %s" % (status, excerpt))

        if status >= 400:
            errors = parsed.get('errors') if isinstance(parsed, dict) else None
            raise LagoonAPIError(
                errors or [], query=query, variables=variables,
                message=None if errors else
                "Lagoon API returned HTTP %d" % status)

        if not isinstance(parsed, dict):
            raise LagoonAPIError(
                [], query=query, variables=variables,
                message="Lagoon API returned an unexpected response shape "
                        "(HTTP %d)" % status)

        has_data = 'data' in parsed
        errors = parsed.get('errors')

        if errors:
            # Covers both "errors only" and partial success (data AND
            # errors both present) -- a module cannot safely act on
            # partial data, so both cases raise.
            raise LagoonAPIError(errors, query=query, variables=variables)

        if not has_data:
            raise LagoonAPIError(
                [], query=query, variables=variables,
                message="Lagoon API response has neither 'data' nor "
                        "'errors'")

        return parsed['data']

    # -- Internal: transport dispatch -----------------------------------

    def _transport_call(self, data_bytes):
        headers = self._request_headers()
        if self.module is not None:
            return self._fetch_url_call(data_bytes, headers)
        return self._open_url_call(data_bytes, headers)

    def _request_headers(self):
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': _USER_AGENT,
        }
        if self.headers:
            headers.update(self.headers)
        # Caller-supplied headers must never be able to override the
        # collection-managed Authorization header.
        headers['Authorization'] = 'Bearer %s' % self.token
        return headers

    def _open_url_call(self, data_bytes, headers):
        try:
            response = open_url(
                self.endpoint,
                data=data_bytes,
                headers=headers,
                method='POST',
                timeout=self.timeout,
                validate_certs=self.validate_certs,
            )
        except HTTPError as e:
            try:
                body = e.read()
            except Exception:
                body = b''
            return e.code, body
        except SSLValidationError as e:
            raise _SSLFailure(to_native(e))
        except AnsibleURLConnectionError as e:
            raise _TransportFailure(to_native(e))
        except URLError as e:
            reason = getattr(e, 'reason', None)
            if isinstance(reason, ssl.SSLError):
                raise _SSLFailure(to_native(e))
            raise _TransportFailure(to_native(e))
        except socket.timeout as e:
            raise _TransportFailure(to_native(e))
        except OSError as e:
            raise _TransportFailure(to_native(e))
        else:
            return response.getcode(), response.read()

    def _fetch_url_call(self, data_bytes, headers):
        # fetch_url() has no validate_certs parameter of its own -- it
        # reads module.params['validate_certs'] internally. Force it so the
        # client's own validate_certs setting (default True) is honoured
        # rather than silently deferring to whatever the calling module's
        # argument_spec did or didn't set.
        self.module.params['validate_certs'] = self.validate_certs

        response, info = fetch_url(
            self.module,
            self.endpoint,
            data=data_bytes,
            headers=headers,
            method='POST',
            timeout=self.timeout,
        )
        status = info.get('status')
        if status is None or status < 0:
            msg = info.get('msg', 'Lagoon API transport error')
            # fetch_url() never raises for connection-level failures --
            # it catches them internally and returns status=-1 with a
            # message, so there is no exception type to branch on here
            # (contrast _open_url_call, which gets a real SSLValidationError
            # or ssl.SSLError instance). Every CPython ssl.SSLError
            # subclass -- including SSLCertVerificationError -- renders
            # via a stable "[SSL: <REASON_CODE>] ..." prefix
            # (Modules/_ssl.c), so this string match is the only available
            # signal on this transport. It intentionally treats *all*
            # SSL/TLS-layer failures (cert verification, protocol/version
            # mismatches, EOF-in-handshake, etc.) as non-retryable, not
            # only certificate failures: retrying a broken TLS handshake
            # is as pointless as retrying a bad cert, and the fail-safe
            # direction is fine -- worst case is one extra failed run
            # instead of a wasted retry, not a correctness bug. Do not
            # narrow this to a "CERTIFICATE_VERIFY_FAILED"-only match.
            if '[SSL:' in msg:
                raise _SSLFailure(msg)
            raise _TransportFailure(msg)

        if response is not None:
            try:
                body = response.read()
            except Exception:
                body = info.get('body', b'')
        else:
            body = info.get('body', b'')
        return status, body