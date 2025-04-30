#!/bin/bash
source UptimeMonitor/bin/activate
python3 uptime.py --target 8.8.8.8 --period 2000 &
disown