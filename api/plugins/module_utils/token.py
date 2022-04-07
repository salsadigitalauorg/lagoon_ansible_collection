import subprocess

from typing import List, Union

def write_ssh_key(key_content: str, key_path: str):
    """Helper function for writing a private key to a file."""
    with open(key_path, 'w') as fh:
        fh.write(key_content)

def fetch_token(ssh_host, ssh_port, ssh_options: Union[str, List[str]], key_path: str):
    """Fetch a token from Lagoon via SSH."""
    ssh_command = ['ssh', '-p', f'{ssh_port}']

    # Add options.
    if isinstance(ssh_options, str):
        options = ssh_options.split()
        ssh_command.extend(options)
    elif isinstance(ssh_options, list):
        ssh_command.extend(ssh_options)

    if key_path:
        ssh_command.extend(['-i', key_path])
    ssh_command.extend([f"lagoon@{ssh_host}", 'token'])

    ssh_res = subprocess.run(ssh_command, capture_output=True)
    return ssh_res.returncode, ssh_res.stdout, ssh_res.stderr
