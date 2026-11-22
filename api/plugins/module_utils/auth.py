"""Lagoon API credentials, resolved lazily.

Callers supply whatever they have - a token, a key, a key file, or nothing -
and the first API call mints a bearer token from it. Nothing here does any I/O
until token() is called, so constructing a client stays free.

Supplying nothing is the useful default: ssh runs with no -i and no caller
options, so the machine's own ~/.ssh/config, IdentityFile, ssh-agent and
known_hosts all apply. Host key checking is therefore the user's to configure;
this module does not disable it.

The only options always present are token.HARDENED_SSH_OPTIONS, which turn off
agent, port and X11 forwarding and terminal allocation, and the ssh verbosity
flag matched to Ansible's own. None of those weaken authentication or host
identity checking.
"""

import os
import tempfile
from collections.abc import Sequence
from typing import Optional, Union

from . import token as LagoonToken
from . import token_cache
from .display import Display, register_secret

DEFAULT_SSH_HOST = "ssh.lagoon.amazeeio.cloud"
DEFAULT_SSH_PORT = "32222"

ENV_TOKEN = "LAGOON_API_TOKEN"

# Catches the two ssh options that run a command directly in an ssh_options
# value. Defence in depth, not a boundary: -F <file> loads an arbitrary ssh
# config that may itself set ProxyCommand, and that passes this check
# untouched. An allowlist would close that gap but is a larger change.
FORBIDDEN_SSH_OPTIONS = ("proxycommand", "localcommand")


class LagoonAuthError(Exception):
    """Raised when no usable API token could be obtained.

    Carries the ssh exit code and raw diagnostic so a caller reporting a
    task result can surface them without re-running the fetch.
    """

    def __init__(self, message, rc=None, diagnostic=None):
        self.rc = rc
        self.diagnostic = diagnostic
        super().__init__(message)


def normalise_ssh_options(
    ssh_options: Optional[Union[str, Sequence[str]]],
) -> list[str]:
    """ssh options as a list of argv elements, rejecting command execution.

    A string is accepted and split for backwards compatibility; a list is
    preferred, since splitting a string on whitespace cannot represent an
    option whose value contains a space.
    """

    if not ssh_options:
        return []

    if isinstance(ssh_options, str):
        options = ssh_options.split()
    else:
        options = [str(o) for o in ssh_options]

    # Matched on each element and on the whole set concatenated, both with all
    # whitespace removed, so "-o ProxyCommand=x", "-oProxyCommand=x",
    # "ProxyCommand=x" and a form split across elements are all caught.
    # PermitLocalCommand contains "localcommand" and so is covered.
    candidates = ["".join(o.split()).lower() for o in options]
    candidates.append("".join(candidates))

    for forbidden in FORBIDDEN_SSH_OPTIONS:
        if any(forbidden in candidate for candidate in candidates):
            raise LagoonAuthError(
                f"Refusing to pass ssh options {ssh_options!r}: options that make "
                "ssh execute a command are not permitted."
            )

    return options


class LagoonCredentials(Display):
    """Whatever the caller has to authenticate with, and a token minted from it.

    Resolution order, first match wins:

    1. An explicit token, or LAGOON_API_TOKEN. Used verbatim - we did not mint
       it, cannot refresh it, and never cache it.
    2. ssh_private_key, the key content. Written to a private temporary file
       for the duration of the call and removed afterwards.
    3. ssh_private_key_file, a path, passed to ssh -i.
    4. Nothing, so ssh uses the machine's own configuration and agent.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        ssh_private_key: Optional[str] = None,
        ssh_private_key_file: Optional[str] = None,
        ssh_host: Optional[str] = None,
        ssh_port: Optional[Union[str, int]] = None,
        ssh_options: Optional[Union[str, Sequence[str]]] = None,
        endpoint: Optional[str] = None,
    ) -> None:
        super().__init__()

        self.explicit_token = token or os.environ.get(ENV_TOKEN) or None
        self.ssh_private_key = ssh_private_key
        self.ssh_private_key_file = ssh_private_key_file
        self.ssh_host = ssh_host or DEFAULT_SSH_HOST
        self.ssh_port = ssh_port or DEFAULT_SSH_PORT
        self.ssh_options = normalise_ssh_options(ssh_options)
        self.endpoint = endpoint

        if self.explicit_token:
            register_secret(self.explicit_token)

    def bind_endpoint(self, endpoint: str) -> None:
        """Record which API these credentials are for.

        Part of the cache key, so that two Lagoons never share an entry. Called
        by the client, which knows the endpoint when the credentials may not.
        """
        self.endpoint = endpoint

    def cache_key(self) -> str:
        return token_cache.make_key(
            self.endpoint,
            self.ssh_host,
            self.ssh_port,
            # Distinguishes identities without recording one.
            token_cache.fingerprint(self.ssh_private_key or self.ssh_private_key_file),
        )

    def token(self) -> str:
        """The bearer token, minted on first use and cached until it expires."""

        if self.explicit_token:
            return self.explicit_token

        token = token_cache.resolve(self.cache_key(), self.mint, self)
        if not token:
            raise LagoonAuthError("Failed to obtain a Lagoon API token.")

        register_secret(token)
        return token

    def invalidate(self) -> None:
        """Forget any minted token, so the next token() call mints another.

        A no-op for an explicitly supplied token: it is not ours to replace.
        """
        if self.explicit_token:
            return

        token_cache.discard(self.cache_key(), self)

    def mint(self) -> tuple[str, int]:
        """Obtain a fresh token over ssh, as (token, expires_in).

        The two-tuple shape token_cache.resolve expects; grant() carries
        everything else a caller such as fetch_token's "grant: true" mode
        needs (refresh_token, and so on).
        """
        grant = self.grant()
        return grant["access_token"], grant.get("expires_in", 0)

    def grant(self) -> dict:
        """Obtain a fresh grant dict over ssh: access_token, expires_in,
        refresh_token and whatever else the grant command returns.

        Handles the private key file dance itself, so a caller never
        touches key material directly.
        """

        if self.ssh_private_key:
            # mkstemp, never a caller-supplied path: 0600 at creation, in the
            # user's own temp directory, with an unpredictable name, and gone
            # before this returns. A fixed path in a world-writable directory
            # is pre-creatable and symlinkable by another user.
            fd, key_file = tempfile.mkstemp(prefix="lagoon-ssh-key-")
            try:
                with os.fdopen(fd, "w") as fh:
                    fh.write(self.ssh_private_key)
                return self._request_grant(key_file)
            finally:
                try:
                    os.unlink(key_file)
                except OSError:
                    pass

        return self._request_grant(self.ssh_private_key_file)

    def ssh_argv_options(self) -> list[str]:
        """Caller-supplied ssh options, plus ssh verbosity matched to Ansible's.

        No -q is ever added: it suppresses exactly the auth, connection and
        host key diagnostics needed to explain a failure. Running with -vvv or
        -vvvv therefore also surfaces ssh's own -v/-vv output, which
        fetch_token folds into its diagnostic.
        """
        options = list(self.ssh_options)

        verbosity = getattr(self.display, "verbosity", 0)
        if verbosity >= 4:
            options.append("-vv")
        elif verbosity >= 3:
            options.append("-v")

        return options

    def _request_grant(self, key_file: Optional[str]) -> dict:
        self.vvv(
            f"Fetching a Lagoon API token from {self.ssh_host}:{self.ssh_port}"
            f"{' with a supplied key' if key_file else ' using the local ssh configuration'}"
        )

        # fetch_token never raises for an ssh or parsing failure: it returns a
        # non-zero rc with a multi-line diagnostic. Only a genuine OS-level
        # failure to spawn ssh still comes back as an exception.
        try:
            rc, grant, diagnostic = LagoonToken.fetch_token(
                self.ssh_host,
                self.ssh_port,
                self.ssh_argv_options(),
                key_file,
            )
        except OSError as e:
            raise LagoonAuthError(f"Could not run ssh to fetch a Lagoon token: {e}")

        if rc > 0:
            where = self.endpoint or f"{self.ssh_host}:{self.ssh_port}"
            raise LagoonAuthError(
                f"Failed to fetch a Lagoon API token for {where} (error code: {rc}):\n"
                f"{_text(diagnostic)}",
                rc=rc,
                diagnostic=_text(diagnostic),
            )

        try:
            grant["access_token"] = grant["access_token"].strip()
        except (KeyError, TypeError, AttributeError) as e:
            raise LagoonAuthError(
                "Lagoon grant response carried no access_token."
            ) from e

        # Registered the moment it exists, so it stays masked even if a later
        # request or traceback is dumped.
        register_secret(grant["access_token"])

        try:
            grant["expires_in"] = int(grant.get("expires_in", 0))
        except (TypeError, ValueError):
            grant["expires_in"] = 0

        return grant


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace").strip()
    return str(value or "").strip()
