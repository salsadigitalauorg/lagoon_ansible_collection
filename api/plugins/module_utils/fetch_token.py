import subprocess

import json
import jwt
import time
from typing import List, Union

DEFAULT_TOKEN_PATH = '/tmp/lagoon_token'

def write_ssh_key(key_content: str, key_path: str):
    """Helper function for writing a private key to a file."""
    try:
        with open(key_path, 'w') as fh:
            fh.write(key_content)
    except IOError as e:
        print('unable to write ssh key to file')
        print(e)
        raise

def write_token_to_file(token: str, token_path: str):
    """Helper function for writing a token to a file."""
    try:
        with open(token_path, 'w') as fh:
            fh.write(token)
    except IOError as e:
        print('unable to write token to file')
        print(e)
        raise

def read_token_from_file(token_path: str):
    """Helper function for reading a token from a file."""
    try:
        with open(token_path, 'r') as fh:
            token = fh.read()
    except IOError as e:
        if not e.strerror == 'No such file or directory':
            print('unable to read token from file')
            print(e.strerror)
        raise

    return token

def token_is_valid(token: dict):
    """Check if a token is valid."""
    if 'access_token' not in token:
        return False

    decoded = jwt.decode(token["access_token"], options={"verify_signature": False})
    expiry = decoded['exp']
    current_time = int(time.time())
    return expiry > current_time

def fetch_token(ssh_host, ssh_port, ssh_options: Union[str, List[str]], key_path: str, token_path: str = DEFAULT_TOKEN_PATH):
    """Fetch a token from Lagoon via SSH."""

    # Check if token exists.
    try:
        tokenStr = read_token_from_file(token_path)
        token = json.loads(tokenStr)
        if token_is_valid(token):
            return 0, token, "using existing valid token"
    except IOError:
        pass

    ssh_command = ['ssh', '-p', f'{ssh_port}']

    # Add options.
    if isinstance(ssh_options, str):
        options = ssh_options.split()
        ssh_command.extend(options)
    elif isinstance(ssh_options, list):
        ssh_command.extend(ssh_options)

    if key_path:
        ssh_command.extend(['-i', key_path])
    ssh_command.extend([f"lagoon@{ssh_host}", 'grant'])

    try:
        ssh_res = subprocess.run(ssh_command, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        print(e.stderr)
        print(e.stdout)
        raise

    grant_token = json.loads(ssh_res.stdout.strip())
    write_token_to_file(json.dumps(grant_token), token_path)
    return ssh_res.returncode, grant_token, ssh_res.stderr
