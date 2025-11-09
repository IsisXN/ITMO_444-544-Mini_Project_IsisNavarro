#!/usr/bin/env python3
"""
deploy_infrastructure.py
Reads the first public IP in instance_ip.txt and deploys nginx via SSH.
"""

import os
import time
import paramiko
from cloudwatch_utils import CloudWatchUtils
from create_infrastructure import read_config  # reuse config reader

cfg = read_config()
cw = CloudWatchUtils(cfg)
cw.log("Deploying NGINX")

# read public ip
with open('instance_ip.txt') as f:
    ip = f.readline().strip()

keyfile = cfg['KEY_FILE']
username = 'ubuntu'  # Ubuntu AMIs use ubuntu user

# Wait a little for SSH to become available
def wait_for_ssh(host, port=22, timeout=300):
    import socket
    start = time.time()
    while time.time() - start < timeout:
        try:
            s = socket.create_connection((host, port), timeout=10)
            s.close()
            return True
        except Exception:
            time.sleep(5)
    return False

print("Waiting for SSH on", ip)
if not wait_for_ssh(ip):
    raise SystemExit("SSH did not become available in time")

# SSH and run commands
k = paramiko.RSAKey.from_private_key_file(keyfile) if cfg.get('KEY_TYPE', 'rsa') != 'ed25519' else None
# Paramiko doesn't parse ed25519 private key easily prior to certain versions.
# We'll let paramiko use the key file directly.

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
# try connecting; paramiko will auto-read keyfile
ssh.connect(hostname=ip, username=username, key_filename=keyfile, timeout=30)

commands = [
    'sudo apt update -y',
    'sudo apt install -y nginx',
    'sudo systemctl enable nginx',
    'sudo systemctl start nginx'
]

for cmd in commands:
    print("Running:", cmd)
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out:
        print(out)
    if err:
        print("ERR:", err)
    time.sleep(1)

ssh.close()
cw.log(f"NGINX deployed and running on {ip}")
cw.put_metric(1)
print("Deploy complete.")
