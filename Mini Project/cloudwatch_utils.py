"""
cloudwatch_utils.py
Utility class to write CloudWatch Logs and metrics.
Handles creating log group/stream and sequenceToken management.
"""

import boto3
import time
import os
from botocore.exceptions import ClientError

class CloudWatchUtils:
    def __init__(self, cfg):
        """
        cfg: dict with REGION, CW_LOG_GROUP, CW_LOG_STREAM, CW_METRIC_NAMESPACE, CW_METRIC_NAME
        """
        self.cfg = cfg
        self.region = cfg.get('REGION')
        self.logs = boto3.client('logs', region_name=self.region)
        self.cw = boto3.client('cloudwatch', region_name=self.region)
        # local file to store nextSequenceToken for the stream to make repeated put_log_events work
        self.token_file = f".{self.cfg.get('CW_LOG_GROUP')}_{self.cfg.get('CW_LOG_STREAM')}.seq"

        # ensure log group/stream exist
        self._ensure_log_group_and_stream()

    def _ensure_log_group_and_stream(self):
        group = self.cfg.get('CW_LOG_GROUP')
        stream = self.cfg.get('CW_LOG_STREAM')
        try:
            self.logs.create_log_group(logGroupName=group)
        except ClientError as e:
            if 'ResourceAlreadyExistsException' not in str(e):
                raise
        try:
            self.logs.create_log_stream(logGroupName=group, logStreamName=stream)
        except ClientError as e:
            if 'ResourceAlreadyExistsException' not in str(e):
                raise

    def _read_token(self):
        try:
            with open(self.token_file, 'r') as f:
                return f.read().strip() or None
        except FileNotFoundError:
            return None

    def _write_token(self, token):
        with open(self.token_file, 'w') as f:
            if token is None:
                f.write('')
            else:
                f.write(token)

    def log(self, message):
        """
        Write a message to CloudWatch Logs (log group/stream from cfg).
        Handles sequence token by checking the streams API if necessary.
        """
        timestamp = int(time.time() * 1000)
        group = self.cfg.get('CW_LOG_GROUP')
        stream = self.cfg.get('CW_LOG_STREAM')

        event = {
            'timestamp': timestamp,
            'message': message
        }

        kwargs = {
            'logGroupName': group,
            'logStreamName': stream,
            'logEvents': [event]
        }

        token = self._read_token()
        if token:
            kwargs['sequenceToken'] = token

        try:
            resp = self.logs.put_log_events(**kwargs)
            next_token = resp.get('nextSequenceToken')
            self._write_token(next_token)
        except ClientError as e:
            # Common case: invalid sequence token; refresh and retry once
            err = e.response.get('Error', {})
            code = err.get('Code', '')
            msg = err.get('Message', '')
            if code in ('InvalidSequenceTokenException', 'DataAlreadyAcceptedException'):
                # fetch latest token from describe-log-streams
                streams = self.logs.describe_log_streams(
                    logGroupName=group,
                    logStreamNamePrefix=stream,
                    limit=1
                )
                items = streams.get('logStreams', [])
                token = items[0].get('uploadSequenceToken') if items else None
                if token:
                    kwargs['sequenceToken'] = token
                else:
                    kwargs.pop('sequenceToken', None)
                resp = self.logs.put_log_events(**kwargs)
                next_token = resp.get('nextSequenceToken')
                self._write_token(next_token)
            else:
                raise

    def put_metric(self, value):
        """
        Send a single metric datapoint to CloudWatch.
        """
        self.cw.put_metric_data(
            Namespace=self.cfg.get('CW_METRIC_NAMESPACE'),
            MetricData=[
                {
                    'MetricName': self.cfg.get('CW_METRIC_NAME'),
                    'Value': value,
                    'Unit': 'Count'
                }
            ]
        )
