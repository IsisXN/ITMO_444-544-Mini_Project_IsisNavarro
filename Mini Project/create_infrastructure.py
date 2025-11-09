#!/usr/bin/env python3
"""
create_infrastructure.py
Uses default VPC and existing subnets to create infrastructure:
- Internet Gateway, route table, security group, key pair
- Launches EC2 instance
- Writes resource IDs and public IPs to local files
"""

import boto3
import time
import os
import subprocess
from cloudwatch_utils import CloudWatchUtils

# -- Helpers to read config.txt --
def read_config(path='config.txt'):
    cfg = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip()
    return cfg

cfg = read_config()
REGION = cfg['REGION']

# -- boto3 clients --
ec2 = boto3.client('ec2', region_name=REGION)
cw = CloudWatchUtils(cfg)
cw.log("=== Creating Infrastructure (Python) ===")

# 1) Use default VPC
vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])['Vpcs']
if not vpcs:
    raise SystemExit("No default VPC found in this region.")
vpc_id = vpcs[0]['VpcId']
with open('vpc_id.txt', 'w') as f:
    f.write(vpc_id)
cw.log(f"Using default VPC: {vpc_id}")

# 2) Use existing subnets in the VPC
subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])['Subnets']
if len(subnets) < 2:
    raise SystemExit("Not enough subnets in the default VPC. At least 2 are required.")
subnet1_id = subnets[0]['SubnetId']
subnet2_id = subnets[1]['SubnetId']
cw.log(f"Using existing subnets: {subnet1_id}, {subnet2_id}")

# 3) Internet Gateway (check if already exists)
igws = ec2.describe_internet_gateways(
    Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}]
)['InternetGateways']

if igws:
    igw_id = igws[0]['InternetGatewayId']
    cw.log(f"Using existing Internet Gateway: {igw_id}")
else:
    igw = ec2.create_internet_gateway()
    igw_id = igw['InternetGateway']['InternetGatewayId']
    ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
    cw.log(f"Internet Gateway created and attached: {igw_id}")

# 4) Route table
rt = ec2.create_route_table(VpcId=vpc_id)
rt_id = rt['RouteTable']['RouteTableId']

# Create route for internet
ec2.create_route(RouteTableId=rt_id, DestinationCidrBlock='0.0.0.0/0', GatewayId=igw_id)

# Associate route table only if not already associated
for subnet_id in [subnet1_id, subnet2_id]:
    try:
        ec2.associate_route_table(RouteTableId=rt_id, SubnetId=subnet_id)
        cw.log(f"Route table {rt_id} associated with subnet {subnet_id}")
    except ec2.exceptions.ClientError as e:
        if "AlreadyAssociated" in str(e):
            cw.log(f"Subnet {subnet_id} already associated with a route table, skipping.")
        else:
            raise

# 5) Security Group (authorize SSH & HTTP)
try:
    my_ip = subprocess.check_output(['curl', '-s', 'ifconfig.me']).decode().strip() + '/32'
except Exception:
    my_ip = '0.0.0.0/0'

# check if SG exists
existing_sgs = ec2.describe_security_groups(Filters=[{'Name': 'group-name', 'Values':[cfg['SECURITY_GROUP_NAME']]}])['SecurityGroups']
if existing_sgs:
    sg_id = existing_sgs[0]['GroupId']
    cw.log(f"Security Group already exists: {sg_id}")
else:
    sg = ec2.create_security_group(
        GroupName=cfg['SECURITY_GROUP_NAME'],
        Description=cfg['SECURITY_GROUP_DESC'],
        VpcId=vpc_id
    )
    sg_id = sg['GroupId']
    cw.log(f"Security Group created: {sg_id}")

# allow SSH from your IP
try:
    ec2.authorize_security_group_ingress(GroupId=sg_id, IpProtocol='tcp', FromPort=22, ToPort=22, CidrIp=my_ip)
except ec2.exceptions.ClientError as e:
    if 'InvalidPermission.Duplicate' in str(e):
        cw.log("SSH rule already exists, skipping.")
    else:
        raise

# allow HTTP from anywhere
try:
    ec2.authorize_security_group_ingress(GroupId=sg_id, IpProtocol='tcp', FromPort=80, ToPort=80, CidrIp='0.0.0.0/0')
except ec2.exceptions.ClientError as e:
    if 'InvalidPermission.Duplicate' in str(e):
        cw.log("HTTP rule already exists, skipping.")
    else:
        raise

# 6) Key Pair
existing_keys = [kp['KeyName'] for kp in ec2.describe_key_pairs()['KeyPairs']]
if cfg['KEY_NAME'] in existing_keys:
    cw.log(f"Key pair already exists: {cfg['KEY_NAME']}")
else:
    kp = ec2.create_key_pair(KeyName=cfg['KEY_NAME'], KeyType=cfg.get('KEY_TYPE','ed25519'))
    with open(cfg['KEY_FILE'], 'w') as f:
        f.write(kp['KeyMaterial'])
    os.chmod(cfg['KEY_FILE'], 0o400)
    cw.log(f"Key pair created and saved to {cfg['KEY_FILE']}")

# 7) Find AMI
images = ec2.describe_images(Owners=[cfg['UBUNTU_OWNER']],
                             Filters=[{'Name':'name','Values':[cfg['UBUNTU_FILTER']]}])['Images']
if not images:
    raise SystemExit("No AMI matched the filter. Check UBUNTU_OWNER and UBUNTU_FILTER.")

images_sorted = sorted(images, key=lambda x: x['CreationDate'])
ami_id = images_sorted[-1]['ImageId']
cw.log(f"Using AMI {ami_id}")

# 8) Launch EC2 instance
inst = ec2.run_instances(
    ImageId=ami_id,
    MinCount=1,
    MaxCount=1,
    InstanceType=cfg['INSTANCE_TYPE'],  # t2.micro, Free Tier
    KeyName=cfg['KEY_NAME'],
    SecurityGroupIds=[sg_id],
    SubnetId=subnet1_id
)

instance_id = inst['Instances'][0]['InstanceId']

# wait until running
ec2.get_waiter('instance_running').wait(InstanceIds=[instance_id])

# get public IP
desc = ec2.describe_instances(InstanceIds=[instance_id])
pub_ip = desc['Reservations'][0]['Instances'][0].get('PublicIpAddress')

with open('instance_id.txt','w') as f:
    f.write(instance_id + '\n')
with open('instance_ip.txt','w') as f:
    f.write(pub_ip + '\n')

cw.log(f"EC2 instance created: {instance_id} ({pub_ip})")
cw.put_metric(1)
print("Create complete. Instance IP:", pub_ip)
