from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


class LagoonError(Exception):
    """Base for all Lagoon collection errors."""


class LagoonConfigError(LagoonError):
    """Caller supplied invalid/incomplete configuration. Never retryable."""


class LagoonAuthError(LagoonError):
    """Authentication or authorisation failed (401/403, token expired,
    SSH grant failed). Never retryable without new credentials."""


class LagoonTransportError(LagoonError):
    """Network, TLS, or 5xx failure. Retryable."""


class LagoonAPIError(LagoonError):
    """The API returned HTTP 200 with a GraphQL errors[] payload."""

    def __init__(self, errors, message=None, query=None, variables=None):
        self.errors = errors or []
        self.query = query
        self.variables = variables
        super(LagoonAPIError, self).__init__(message or self._summarise())

    @property
    def messages(self):
        """List of human-readable messages from the GraphQL errors payload.

        Tolerates malformed entries -- a plain string, a dict with no
        ``message`` key, or ``None`` -- without raising.
        """
        result = []
        for entry in self.errors:
            if isinstance(entry, dict):
                msg = entry.get('message')
                if msg is not None:
                    result.append(str(msg))
            elif entry is not None:
                result.append(str(entry))
        return result

    def _summarise(self):
        msgs = self.messages
        if not msgs:
            return "Lagoon API error: unknown error"
        if len(msgs) == 1:
            return "Lagoon API error: %s" % msgs[0]
        return "Lagoon API errors (%d): %s" % (len(msgs), "; ".join(msgs))

    def __reduce__(self):
        # Exception's default __reduce_ex__ reconstructs via cls(*self.args),
        # which would re-run __init__ with the rendered message string as the
        # ``errors`` positional argument. Pass the already-computed message
        # through explicitly so round-tripping is exact.
        message = self.args[0] if self.args else None
        return (self.__class__,
                (self.errors, message, self.query, self.variables))


class LagoonNotFoundError(LagoonError):
    """A read/lookup query resolved to no result."""

    def __init__(self, resource, query=None, arg=None, value=None, message=None):
        self.resource = resource
        self.query = query
        self.arg = arg
        self.value = value
        super(LagoonNotFoundError, self).__init__(
            message or self._summarise())

    def _summarise(self):
        detail = ""
        if self.query:
            detail = " query '%s'" % self.query
            if self.arg is not None:
                detail += " with %s=%r" % (self.arg, self.value)
        return "Lagoon %s not found:%s returned no result" % (
            self.resource, detail)

    def __reduce__(self):
        message = self.args[0] if self.args else None
        return (self.__class__,
                (self.resource, self.query, self.arg, self.value, message))


class LagoonAmbiguousResultError(LagoonError):
    """A lookup resolved to more than one result."""

    def __init__(self, resource, query=None, arg=None, value=None,
                 count=None, message=None):
        self.resource = resource
        self.query = query
        self.arg = arg
        self.value = value
        self.count = count
        super(LagoonAmbiguousResultError, self).__init__(
            message or self._summarise())

    def _summarise(self):
        detail = ""
        if self.query:
            detail = " query '%s'" % self.query
            if self.arg is not None:
                detail += " with %s=%r" % (self.arg, self.value)
        count_detail = " (%d results)" % self.count if self.count is not None else ""
        return "Lagoon %s ambiguous:%s returned more than one result%s" % (
            self.resource, detail, count_detail)

    def __reduce__(self):
        message = self.args[0] if self.args else None
        return (self.__class__,
                (self.resource, self.query, self.arg, self.value,
                 self.count, message))