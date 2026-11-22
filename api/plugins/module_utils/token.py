import json
import shlex
import subprocess
from typing import List, Union

from .display import Display

TIMEOUT_RC = 124
MAX_OUTPUT_CHARS = 2000

# Substrings of ssh/grant stderr mapped to a short cause. Checked in order;
# first match wins. Kept small deliberately - a wrong guess is worse than no
# guess, and the raw stderr is always included alongside it.
_FAILURE_HINTS = [
    ("Permission denied", "ssh key not authorised for this Lagoon, or wrong key file"),
    ("publickey", "ssh key not authorised for this Lagoon, or wrong key file"),
    ("Connection refused", "host/port unreachable - check ssh_host/ssh_port"),
    ("Connection timed out", "host/port unreachable - check ssh_host/ssh_port"),
    ("kex_exchange_identification", "host/port unreachable - check ssh_host/ssh_port"),
    ("Host key verification failed", "known_hosts mismatch for this host"),
    ("UNPROTECTED PRIVATE KEY FILE", "key file permissions must be 0600"),
]

# Forwarding and terminal allocation are disabled on every token fetch. A
# passwordless ssh login must not carry the agent, ports or X11 to the remote
# end, and `grant` is a single non-interactive command that needs none of them.
# ClearAllForwardings covers -L/-R/-D from a config file; agent forwarding is
# separate and needs its own option.
HARDENED_SSH_OPTIONS = [
    "-o",
    "ForwardAgent=no",
    "-o",
    "ClearAllForwardings=yes",
    "-o",
    "ForwardX11=no",
    "-o",
    "RequestTTY=no",
]


def _truncated(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... (truncated, {len(text)} chars total)"


def _hint(stderr: str) -> Union[str, None]:
    for needle, hint in _FAILURE_HINTS:
        if needle in stderr:
            return hint
    return None


def _diagnostic(
    command: List[str], rc, stderr: str = "", stdout: str = "", extra: str = ""
) -> str:
    """Build a multi-line, human-readable failure message.

    Includes the command actually run (no secret material - argv only ever
    carries a key path) so a failure is reproducible outside Ansible.
    """
    lines = [f"ssh command: {shlex.join(command)}", f"exit code: {rc}"]
    if extra:
        lines.append(extra)
    if stderr:
        lines.append(f"stderr: {_truncated(stderr.strip())}")
    if stdout:
        lines.append(f"stdout: {_truncated(stdout.strip())}")
    hint = _hint(stderr)
    if hint:
        lines.append(f"hint: {hint}")
    return "\n".join(lines)


def fetch_token(
    ssh_host,
    ssh_port,
    ssh_options: Union[str, List[str]],
    key_path: str,
    timeout: int = 60,
):
    """Fetch a token from Lagoon via SSH.

    Returns (rc, grant_token, error). On any failure rc is non-zero,
    grant_token is None, and error is a multi-line diagnostic string. Never
    raises for an ssh/parsing failure - only for programming errors.
    """
    ssh_command = ["ssh", "-p", f"{ssh_port}"]

    # Fetching a grant needs no forwarding, no X11 and no terminal. Passed
    # first because ssh takes the first value it is given for these keywords,
    # so a caller's ssh_options cannot relax them - deliberately unlike host
    # key checking, which is left to the machine's own ssh configuration.
    ssh_command.extend(HARDENED_SSH_OPTIONS)

    if key_path:
        # Use only the key supplied, not the first thing the agent offers.
        ssh_command.extend(["-o", "IdentitiesOnly=yes"])

    # Add options.
    if isinstance(ssh_options, str):
        options = ssh_options.split()
        ssh_command.extend(options)
    elif isinstance(ssh_options, list):
        ssh_command.extend(ssh_options)

    if key_path:
        ssh_command.extend(["-i", key_path])
    ssh_command.extend([f"lagoon@{ssh_host}", "grant"])

    Display().vvv(lambda: f"running: {shlex.join(ssh_command)}")

    try:
        ssh_res = subprocess.run(
            ssh_command, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return (
            TIMEOUT_RC,
            None,
            _diagnostic(ssh_command, TIMEOUT_RC, extra=f"timed out after {timeout}s"),
        )
    except FileNotFoundError as e:
        return 127, None, _diagnostic(ssh_command, 127, extra=str(e))

    if ssh_res.returncode != 0:
        return (
            ssh_res.returncode,
            None,
            _diagnostic(
                ssh_command, ssh_res.returncode, ssh_res.stderr, ssh_res.stdout
            ),
        )

    try:
        grant_token = json.loads(ssh_res.stdout.strip())
    except json.JSONDecodeError:
        return (
            1,
            None,
            _diagnostic(
                ssh_command,
                1,
                ssh_res.stderr,
                ssh_res.stdout,
                extra="ssh succeeded but output was not valid JSON",
            ),
        )

    if not isinstance(grant_token, dict) or not grant_token.get("access_token"):
        keys = (
            list(grant_token.keys())
            if isinstance(grant_token, dict)
            else type(grant_token).__name__
        )
        return (
            1,
            None,
            _diagnostic(
                ssh_command,
                1,
                ssh_res.stderr,
                extra=f"grant response missing access_token (keys: {keys})",
            ),
        )

    return ssh_res.returncode, grant_token, ssh_res.stderr
