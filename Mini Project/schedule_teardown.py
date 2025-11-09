#!/usr/bin/env python3
"""
schedule_teardown.py
Schedules a local cron job to run destroy_infrastructure.py after AUTO_TEARDOWN_HOURS.
"""

import subprocess
from create_infrastructure import read_config
import datetime

cfg = read_config()
hours = int(cfg.get('AUTO_TEARDOWN_HOURS', '2'))
# calculate time
run_time = (datetime.datetime.now() + datetime.timedelta(hours=hours))
min_str = run_time.strftime('%M')
hour_str = run_time.strftime('%H')
# full path to destroy script
import os
cwd = os.getcwd()
destroy_cmd = f'cd {cwd} && source venv/bin/activate && python3 {cwd}/destroy_infrastructure.py >> {cwd}/teardown.log 2>&1'
cron_line = f'{min_str} {hour_str} * * * {destroy_cmd}'

# add to crontab
p = subprocess.Popen(['crontab','-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
out,err = p.communicate()
existing = out if p.returncode == 0 else ''
new_cron = existing + '\n' + cron_line + '\n'
p2 = subprocess.Popen(['crontab','-'], stdin=subprocess.PIPE, text=True)
p2.communicate(new_cron)
print("Auto teardown scheduled at", run_time)
