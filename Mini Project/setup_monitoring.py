#!/usr/bin/env python3
"""
setup_monitoring.py
Creates SNS topic, subscribes email, and creates CloudWatch alarm on StepsCompleted metric.
"""

import boto3
from cloudwatch_utils import CloudWatchUtils
from create_infrastructure import read_config

cfg = read_config()
REGION = cfg['REGION']
sns = boto3.client('sns', region_name=REGION)
cw_client = boto3.client('cloudwatch', region_name=REGION)
cw = CloudWatchUtils(cfg)

cw.log("Setting up SNS topic and CloudWatch Alarm")

# Create SNS topic
topic = sns.create_topic(Name=cfg['SNS_TOPIC_NAME'])
topic_arn = topic['TopicArn']
# Subscribe email
resp = sns.subscribe(TopicArn=topic_arn, Protocol='email', Endpoint=cfg['ALARM_EMAIL'])
cw.log(f"SNS Topic created: {topic_arn}. Subscription ARN pending confirmation (check your email).")

# Create CloudWatch alarm: if StepsCompleted Sum < 1 for 1 evaluation period (period 300s)
cw_client.put_metric_alarm(
    AlarmName=cfg['ALARM_NAME'],
    MetricName=cfg['CW_METRIC_NAME'],
    Namespace=cfg['CW_METRIC_NAMESPACE'],
    Statistic='Sum',
    Period=300,
    EvaluationPeriods=1,
    Threshold=0,
    ComparisonOperator='LessThanThreshold',
    AlarmActions=[topic_arn]
)
cw.log(f"CloudWatch Alarm created: {cfg['ALARM_NAME']}")
cw.put_metric(1)
print("Monitoring & alarm created. Check email to confirm SNS subscription.")

