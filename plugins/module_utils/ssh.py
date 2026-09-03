from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json
import os
import shlex
import shutil
import subprocess
import tempfile

from .errors import LagoonAuthError

_STDERR_TRUNCATE = 500
_KEY_FILE_NAME = 'lagoon_ssh_key'


def request_grant(ssh_host, ssh_port, *, private_key=None,
                   private_key_file=None, ssh_options=None,
                   strict_host_key_checking='accept-new',
                   known_hosts_file=None, timeout=30, ssh_user='lagoon',
                   batch_mode=True):
    """Run ``ssh ... <ssh_user>@<ssh_host> grant`` and return
    ``(access_token, expires_in)``. Raises :class:`LagoonAuthError` on any
    failure -- a missing ``ssh`` binary, a non-zero exit code, a timeout, or
    a response that is not well-formed JSON with the expected fields.

    At most one of ``private_key`` / ``private_key_file`` should be
    supplied by the caller (:mod:`.auth` enforces mutual exclusion, not
    this function). When ``private_key`` content is given, it is written
    to a securely-created temporary file for the duration of the call and
    removed afterwards -- never to a fixed or predictable path (this
    replaces v1's fixed, world-writable-directory path, which was
    exploitable via symlink pre-creation on a shared host, and which was
    ``chmod``'d *after* writing, leaving it briefly readable per the
    process umask). When ``private_key_file`` is given directly (no
    ``private_key`` content), that path is used in place and is never
    copied -- avoids gratuitously duplicating a credential on disk. When
    **neither** is given, no ``-i`` flag is emitted at all and ``ssh``
    authenticates via agent identities offered over ``SSH_AUTH_SOCK``,
    which this function inherits unmodified because it passes no ``env=``
    to :func:`subprocess.run` -- this is the path AWX/ansible-runner and a
    locally mounted agent socket rely on. Do not add an ``env=`` kwarg to
    the :func:`subprocess.run` call below without preserving
    ``SSH_AUTH_SOCK``, or agent auth breaks silently.

    ``strict_host_key_checking`` defaults to ``'accept-new'``. Passing
    ``'no'`` disables host key verification entirely and permits a MITM on
    the grant channel to hand back an attacker-controlled bearer token,
    silently, for the whole play (this reverses v1's unconditional
    ``StrictHostKeyChecking=no`` default). There is no implicit path to
    ``'no'``: a caller must pass it explicitly. This function does not itself
    emit a warning when ``'no'`` is passed -- it is a transport primitive,
    not a policy layer -- callers (``auth.py``, module documentation) are
    responsible for surfacing that warning to the operator.

    ``known_hosts_file``, when supplied, is passed as
    ``UserKnownHostsFile``. When ``None``, ``ssh`` uses its own default
    (the invoking user's ``~/.ssh/known_hosts``) -- this function never
    defaults it to ``/dev/null``, which is precisely the v1 behaviour being
    reversed.

    ``batch_mode`` defaults to ``True``, emitting ``-o BatchMode=yes`` so
    a grant that cannot authenticate (e.g. an agent holding no usable
    key) fails immediately instead of falling through to an interactive
    passphrase/host-key prompt that Ansible has no way to answer.
    ``ConnectTimeout``/``timeout`` do not cover this case -- both are
    about the network handshake, not an already-connected session
    blocked on terminal input -- so without ``BatchMode`` the only
    backstop is ``subprocess.run(timeout=...)`` itself, which turns a
    prompt into an opaque multi-second stall rather than a clean auth
    failure. Pass ``batch_mode=False`` to omit the flag entirely (not
    ``BatchMode=no``) and defer to ``ssh_config``/``ssh_options``.

    **Collection-managed options are emitted before caller-supplied**
    ``ssh_options`` **in argv** (see :func:`_build_argv`), and OpenSSH
    resolves repeated ``-o`` settings first-wins -- so every option this
    function sets itself (``StrictHostKeyChecking``, ``ConnectTimeout``,
    ``UserKnownHostsFile``, ``BatchMode``) is authoritative and cannot be
    weakened by a caller's ``ssh_options``. This is deliberate -- it is
    what keeps ``StrictHostKeyChecking=accept-new`` from being silently
    overridden -- but it means v1-style ``ssh_options`` values such as
    ``"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"`` are
    now no-ops; the equivalent behaviour must be requested via this
    function's own ``strict_host_key_checking``/``known_hosts_file``
    parameters instead.

    Key content never appears in any exception, log line, or ``repr()``
    (ISM-1402). Failure messages include truncated stderr, never the raw
    private key.
    """
    tmp_dir = None
    key_path = private_key_file

    try:
        if private_key is not None:
            tmp_dir = tempfile.mkdtemp()
            key_path = os.path.join(tmp_dir, _KEY_FILE_NAME)
            try:
                fd = os.open(
                    key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except OSError as e:
                raise LagoonAuthError(
                    "unable to create temporary SSH key file: %s" %
                    (e.strerror or e.__class__.__name__))
            try:
                try:
                    data = private_key.encode('utf-8') if \
                        isinstance(private_key, str) else private_key
                    os.write(fd, data)
                except OSError as e:
                    raise LagoonAuthError(
                        "unable to write temporary SSH key file: %s" %
                        (e.strerror or e.__class__.__name__))
            finally:
                os.close(fd)

        argv = _build_argv(
            ssh_host, ssh_port, key_path, ssh_options,
            strict_host_key_checking, known_hosts_file, timeout, ssh_user,
            batch_mode)

        try:
            result = subprocess.run(
                argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=timeout)
        except FileNotFoundError:
            raise LagoonAuthError("ssh executable not found")
        except subprocess.TimeoutExpired:
            raise LagoonAuthError(
                "SSH grant timed out after %ss" % timeout)

        if result.returncode != 0:
            raise LagoonAuthError(
                "SSH grant failed (rc=%d): %s" %
                (result.returncode,
                 _truncate_stderr(result.stderr, private_key)))

        try:
            payload = json.loads(result.stdout)
        except ValueError:
            raise LagoonAuthError(
                "unexpected grant response: stdout was not valid JSON")

        if not isinstance(payload, dict) or \
                'access_token' not in payload or 'expires_in' not in payload:
            raise LagoonAuthError(
                "malformed grant response: missing access_token/expires_in")

        return payload['access_token'], payload['expires_in']
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _build_argv(ssh_host, ssh_port, key_path, ssh_options,
                 strict_host_key_checking, known_hosts_file, timeout,
                 ssh_user, batch_mode=True):
    # Every collection-managed -o option is appended here, BEFORE
    # caller-supplied ssh_options below. OpenSSH resolves repeated -o
    # settings first-wins, so this ordering is what makes these defaults
    # authoritative rather than overridable -- do not reorder this
    # without re-reading request_grant()'s docstring.
    argv = [
        'ssh',
        '-p', str(ssh_port),
        '-o', 'StrictHostKeyChecking=%s' % strict_host_key_checking,
        '-o', 'ConnectTimeout=%d' % timeout,
    ]

    if known_hosts_file:
        argv += ['-o', 'UserKnownHostsFile=%s' % known_hosts_file]

    if batch_mode:
        argv += ['-o', 'BatchMode=yes']

    argv += _parse_ssh_options(ssh_options)

    if key_path:
        argv += ['-i', key_path]

    argv += ['%s@%s' % (ssh_user, ssh_host), 'grant']
    return argv


def _parse_ssh_options(ssh_options):
    if ssh_options is None:
        return []
    if isinstance(ssh_options, str):
        return shlex.split(ssh_options)
    return list(ssh_options)


def _truncate_stderr(stderr_bytes, private_key=None):
    if not stderr_bytes:
        return ''
    text = stderr_bytes.decode('utf-8', errors='replace')
    if private_key:
        # Defence in depth: a misbehaving `ssh` invocation is not expected
        # to echo the key it was given back on stderr, but if it ever did,
        # the raised message must not repeat it (ISM-1402). This only
        # catches an exact-substring echo, not a re-encoded/re-wrapped
        # copy -- it is a backstop, not a guarantee.
        text = text.replace(private_key, '***redacted***')
    return text[:_STDERR_TRUNCATE]
