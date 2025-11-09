#!/usr/bin/env python3
"""
destroy_infrastructure.py
Terminates instances listed in instance_id.txt and deletes key pair, security group, and VPC.
"""

import boto3
from cloudwatch_utils import CloudWatchUtils
from create_infrastructure import read_config
import os, time

cfg = read_config()
REGION = cfg['REGION']
ec2 = boto3.client('ec2', region_name=REGION)
cw = CloudWatchUtils(cfg)
cw.log("Destroying infrastructure...")

# Terminate instances
if os.path.exists('instance_id.txt'):
    with open('instance_id.txt') as f:
        ids = [l.strip() for l in f if l.strip()]
    if ids:
        ec2.terminate_instances(InstanceIds=ids)
        ec2.get_waiter('instance_terminated').wait(InstanceIds=ids)
        cw.log(f"Terminated instances: {ids}")

# Delete key pair
try:
    ec2.delete_key_pair(KeyName=cfg['KEY_NAME'])
    if os.path.exists(cfg['KEY_FILE']):
        os.remove(cfg['KEY_FILE'])
    cw.log(f"Deleted key pair: {cfg['KEY_NAME']}")
except Exception as e:
    cw.log(f"Key pair deletion error: {e}")

# Delete security group
try:
    sgs = ec2.describe_security_groups(Filters=[{'Name':'group-name','Values':[cfg['SECURITY_GROUP_NAME']]}])['SecurityGroups']
    if sgs:
        sg_id = sgs[0]['GroupId']
        ec2.delete_security_group(GroupId=sg_id)
        cw.log(f"Deleted security group: {sg_id}")
except Exception as e:
    cw.log(f"Security group deletion error: {e}")

# Delete VPC
if os.path.exists('vpc_id.txt'):
    with open('vpc_id.txt') as f:
        vpc_id = f.read().strip()
    try:
        ec2.delete_vpc(VpcId=vpc_id)
        cw.log(f"Deleted VPC: {vpc_id}")
    except Exception as e:
        cw.log(f"VPC deletion error: {e}")

# Cleanup local files
for fname in ('instance_id.txt','instance_ip.txt','vpc_id.txt'):
    if os.path.exists(fname):
        os.remove(fname)

cw.log("Infrastructure destroyed successfully")
cw.put_metric(1)
print("Destroy complete.")
