# -*- coding: utf-8 -*-

# Documentation for the auth options resolved by
# plugins/module_utils/auth.py::resolve_token().
#
# This is a SECOND, INDEPENDENT declaration of the option set that
# auth_argument_spec() owns canonically. antsibull-docs cannot read a
# Python argspec, so the two must be maintained side by side --
# tests/unit/plugins/module_utils/test_auth_docs.py binds them
# mechanically (names both directions, type, and default) so they cannot
# silently diverge. Add an option here and to auth_argument_spec() in the
# same change, or that test fails.
#
# DELIBERATELY NO `no_log:` KEYS BELOW. no_log is an *argspec* key, not a
# DOCUMENTATION key: antsibull-docs' OptionsSchema sets
# model_config = ConfigDict(extra="forbid") and declares no no_log field,
# so any module doing extends_documentation_fragment against a
# no_log-bearing fragment fails `antsibull-docs lint-collection-docs
# --plugin-docs` with "Did not return correct DOCUMENTATION". Redaction is
# already handled where it actually takes effect -- no_log=True on
# lagoon_api_token and lagoon_ssh_private_key in auth_argument_spec().
# Adding no_log here would buy no extra protection and would break the
# first module that extends this fragment.

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


class ModuleDocFragment(object):

    DOCUMENTATION = r'''
options:
  lagoon_api_endpoint:
    description:
    - URL of the Lagoon GraphQL API, including the path.
    - For example V(https://api.lagoon.example.com/graphql).
    type: str
  lagoon_api_token:
    description:
    - Bearer token used to authenticate with the Lagoon API. Sensitive.
    - If omitted, the C(LAGOON_API_TOKEN) environment variable is used
      when set.
    - A long-lived token is the exceptional path, not the norm. Prefer
      the short-lived tokens obtained automatically over SSH by setting
      O(lagoon_ssh_host) and leaving this option unset.
    - If a long-lived token cannot be avoided, store it as an encrypted
      Ansible Vault secret rather than in plain text, and rotate it at
      least every 12 months.
    - A token supplied here, or via the environment variable, is used
      exactly as given. It is never validated for expiry and is never
      written to the on-disk cache described in O(lagoon_token_cache).
    type: str
  validate_certs:
    description:
    - Whether to verify the TLS certificate of the Lagoon API endpoint.
    - Leave enabled. Disabling it permits an active network attacker to
      intercept API traffic, including the bearer token used to
      authenticate it.
    type: bool
    default: true
  lagoon_ssh_host:
    description:
    - Hostname of the Lagoon SSH service used to obtain a short-lived
      API token.
    - Required unless O(lagoon_api_token) or the C(LAGOON_API_TOKEN)
      environment variable is set.
    type: str
  lagoon_ssh_port:
    description:
    - Port of the Lagoon SSH service.
    type: int
    default: 22
  lagoon_ssh_user:
    description:
    - Username used when connecting to the Lagoon SSH service.
    type: str
    default: lagoon
  lagoon_ssh_private_key:
    description:
    - Contents of the SSH private key used to obtain a token. Sensitive.
    - Mutually exclusive with O(lagoon_ssh_private_key_file).
    - Supplying neither this option nor O(lagoon_ssh_private_key_file) is
      valid and is not an error. It authenticates using the identities
      offered by an already-running SSH agent over the inherited
      C(SSH_AUTH_SOCK), which is how AWX and ansible-runner supply the
      key.
    - The key is written to a private temporary file for the lifetime of
      the SSH call only, at mode C(0600) from the instant it exists, and
      removed afterwards. Prefer O(lagoon_ssh_private_key_file) or an SSH
      agent where possible, so the key need not pass through Ansible
      variables at all.
    type: str
  lagoon_ssh_private_key_file:
    description:
    - Path to an SSH private key file used to obtain a token.
    - Mutually exclusive with O(lagoon_ssh_private_key). Unlike that
      option, the file is used in place and is never copied.
    - Supplying neither option authenticates via an SSH agent over the
      inherited C(SSH_AUTH_SOCK). See O(lagoon_ssh_private_key).
    type: path
  lagoon_ssh_known_hosts_file:
    description:
    - Path to a C(known_hosts) file used to verify the Lagoon SSH host
      key, passed to C(ssh) as C(UserKnownHostsFile).
    - When unset, C(ssh) uses its own default, normally
      C(~/.ssh/known_hosts) for the user running Ansible.
    type: path
  lagoon_ssh_options:
    description:
    - Additional options passed to the C(ssh) command used to obtain a
      token, either as a single string (parsed with shell-style quoting)
      or as a list of arguments.
    - This option cannot override the options the collection sets itself
      (C(StrictHostKeyChecking), C(ConnectTimeout),
      C(UserKnownHostsFile) and C(BatchMode)). Those are placed ahead of
      this value on the command line and OpenSSH honours the first
      setting it sees for a given option, so the collection's values win.
      This is deliberate; it is what stops the secure default for
      O(lagoon_ssh_strict_host_key_checking) being weakened here.
    - As a result, the idiom used by the older C(lagoon.api) collection,
      V(-q -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no),
      is silently ignored. Use
      O(lagoon_ssh_strict_host_key_checking) and
      O(lagoon_ssh_known_hosts_file) instead.
    type: raw
  lagoon_ssh_strict_host_key_checking:
    description:
    - Value passed to the C(ssh) C(StrictHostKeyChecking) option when
      obtaining a token.
    - The default V(accept-new) trusts a host the first time it is seen
      and refuses it thereafter if its key changes.
    - Setting this to V(no) disables host key verification entirely. An
      attacker able to intercept the SSH connection can then impersonate
      the Lagoon SSH service and return an API token of their choosing,
      which every subsequent task in the play will use. Do not set V(no)
      outside a disposable test environment.
    type: str
    default: accept-new
  lagoon_ssh_batch_mode:
    description:
    - Whether to pass C(BatchMode=yes) to C(ssh) when obtaining a token.
    - Enabled by default so a connection that cannot authenticate fails
      immediately, instead of blocking on a passphrase or host key
      prompt that Ansible has no way to answer. Such a prompt is not
      covered by the connection timeout and would otherwise surface as an
      unexplained stall.
    - Disable only when an C(ssh_config) or O(lagoon_ssh_options) setting
      needs to govern this instead.
    type: bool
    default: true
  lagoon_token_cache:
    description:
    - Whether to cache the short-lived API token on disk so it can be
      reused by later tasks and later C(ansible-playbook) runs.
    - Disabled by default. This is the only feature in the collection
      that writes a bearer token to disk. Tokens are always cached in
      memory regardless, but that cache only lasts for the current task,
      because Ansible runs each task in a separate worker process.
    - When enabled, tokens are written under
      C($XDG_CACHE_HOME/ansible-lagoon), or C(~/.cache/ansible-lagoon)
      when that variable is unset, with the directory at mode C(0700)
      and each file at mode C(0600). A cached file whose ownership or
      permissions are unexpected is ignored rather than repaired.
      Entries are never deleted explicitly; they are ignored once the
      token they hold has expired.
    - Note when authenticating via an SSH agent, that is, with neither
      O(lagoon_ssh_private_key) nor O(lagoon_ssh_private_key_file) set.
      Cache entries are then keyed only by endpoint, SSH host, port and
      user, so two runs using different agent identities that share those
      values will share a cached token. The consequence is
      misattribution in Lagoon's audit log, and acting with the wrong
      identity's privileges until the token expires. Set
      O(lagoon_ssh_private_key_file) to keep such identities apart.
    type: bool
    default: false
'''
