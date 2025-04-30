#!/bin/bash
source UptimeMonitor/bin/activate
yes | fastapi run api.py > api.log 2> api.log &
disown