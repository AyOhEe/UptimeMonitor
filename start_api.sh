#!/bin/bash
LOGS_DIR="$HOME/uptime_logs"
yes | fastapi run api.py > api.log 2> api.log &
disown