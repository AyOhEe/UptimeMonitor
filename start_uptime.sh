#!/bin/bash
python3 uptime.py --target 8.8.8.8 --period 2000 --logs $HOME/uptime_logs &
disown