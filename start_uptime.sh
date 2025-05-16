#!/bin/bash
export LOGS_DIR="$HOME/uptime_logs"
python3 uptime.py --target 8.8.8.8 --period 2000 --logs $LOGS_DIR &
disown