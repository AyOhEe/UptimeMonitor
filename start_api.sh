#!/bin/bash
LOGS_DIR="$HOME/uptime_logs"
yes | fastapi run api.py > $LOGS_DIR/api.log 2> $LOGS_DIR/api.log &
disown