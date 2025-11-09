#!/usr/bin/env python3
"""
scale_infrastructure.py
Launches one extra EC2 instance in the existing subnet and appends instance id/ip to files.
"""

import boto3
from cloudwatch_utils import CloudWatchUtils
from create_infrastructure import read_config

cfg = read_config()
REGION = cfg['REGION']
ec2 = boto3.client('ec2', region_name=REGION)
cw = CloudWatchUtils(cfg)
cw.log("Scaling infrastructure: launching 1 extra instance")

# find AMI and subnet and sg
images = ec2.describe_images(Owners=[cfg['UBUNTU_OWNER']],
                             Filters=[{'Name':'name','Values':[cfg['UBUNTU_FILTER']]}])['Images']
images_sorted = sorted(images, key=lambda x: x['CreationDate'])
ami_id = images_sorted[-1]['ImageId']

# get subnet id by cidr
subnets = ec2.describe_subnets(Filters=[{'Name':'cidr-block','Values':[cfg['SUBNET_CIDR_1']]}])['Subnets']
if not subnets:
    raise SystemExit("Subnet for scaling not found.")
subnet_id = subnets[0]['SubnetId']

sgs = ec2.describe_security_groups(Filters=[{'Name':'group-name','Values':[cfg['SECURITY_GROUP_NAME']]}])['SecurityGroups']
if not sgs:
    raise SystemExit("Security group not found.")
sg_id = sgs[0]['GroupId']

inst = ec2.run_instances(ImageId=ami_id, MinCount=1, MaxCount=1,
                         InstanceType=cfg['INSTANCE_TYPE'], KeyName=cfg['KEY_NAME'],
                         SecurityGroupIds=[sg_id], SubnetId=subnet_id, AssociatePublicIpAddress=True)
instance_id = inst['Instances'][0]['InstanceId']
ec2.get_waiter('instance_running').wait(InstanceIds=[instance_id])
desc = ec2.describe_instances(InstanceIds=[instance_id])
pub_ip = desc['Reservations'][0]['Instances'][0].get('PublicIpAddress')

with open('instance_id.txt','a') as f:
    f.write(instance_id + '\n')
with open('instance_ip.txt','a') as f:
    f.write(pub_ip + '\n')

cw.log(f"Scaled: new instance {instance_id} ({pub_ip})")
cw.put_metric(1)
print("Scaling complete. New instance:", instance_id, pub_ip)
