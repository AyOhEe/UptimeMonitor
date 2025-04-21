import subprocess
import sys
import os
import platform
import time
import logging
import argparse
import json
import re

from typing import List, Dict, Never, Any


logging.addLevelName(100, "START")
LOGGER = logging.getLogger("uptime")
LOGGER.setLevel(logging.INFO)

formatter = logging.Formatter("[%(asctime)s]\t[%(levelname)s]:\t %(message)s")
formatter.formatTime = lambda record, datefmt=None: str(int(time.time()))

TODAY = time.strftime('%Y-%m-%d')
if not os.path.isdir("logs"):
    os.mkdir("logs", 777)
file_handler = logging.FileHandler(f"logs/{TODAY}-uptime.log")
file_handler.setFormatter(formatter)

LOGGER.addHandler(file_handler)


def calculate_uptime(log: List[str]) -> float:
    accounted_uptime = 0
    accounted_downtime = 0

    period = 2000

    for i in range(len(log)):
        line = log[i].strip()
        line = line.strip()
        if line.endswith("ms"):
            period = int(line.split(" ")[-1][:-2])
            continue

        elif line.endswith("success"):
            accounted_uptime += period
            continue

        elif line.endswith("FAILED"):
            accounted_downtime += period
            continue

    return accounted_uptime / (accounted_uptime + accounted_downtime)

def calculate_disruptions(log: List[str]) -> List[Dict[str, int]]:
    disruptions = []
    rolling_window = []
    in_disruption = False
    for line in log:
        line_sections = line.split()
        t = int(line_sections[0][1:-1])
        result = line_sections[-1]

        if result[-2:] == "ms":
            continue

        rolling_window.append((t, result))
        while len(rolling_window) > 1:
            if rolling_window[-1][0] - rolling_window[0][0] > 60:
                rolling_window.pop(0)
            else:
                break

        if len(rolling_window) < 2:
            continue
        
        total_t = 0
        success_t = 0
        for i in range(1, len(rolling_window)):
            delta_t = rolling_window[i][0] - rolling_window[i - 1][0]
            total_t += delta_t
            if rolling_window[i][1] == "success":
                success_t += delta_t

        uptime = (success_t / total_t)
        if not in_disruption and total_t > 50 and uptime < 0.80:
            disruptions.append({ "start" : rolling_window[0][0], "end" : -1})
            in_disruption = True
        elif in_disruption and total_t > 50 and uptime > 0.90:
            disruptions[-1]["end"] = rolling_window[-1][0]
            in_disruption = False


    return disruptions

def generate_precompute() -> Dict[str, Any]:
    yesterday = time.localtime(time.time() - 24*60*60)
    yesterday_str = time.strftime('%Y-%m-%d', yesterday)
    yesterday_log = f"logs/{yesterday_str}-uptime.log"

    if not os.path.exists(yesterday_log):
        return
    

    with open(f"logs/{yesterday_str}-uptime.log", "r") as f:
        log = f.readlines()
        precompute = {
            "daily-uptime": calculate_uptime(log),
            "disruptions": calculate_disruptions(log)
        }
    
    if not os.path.isdir("precomputes"):
        os.mkdir("precomputes", 777)
    
    with open(f"precomputes/{yesterday_str}-uptime.json", "w") as f:
        json.dump(precompute, f, indent=4)

def remove_old_logs() -> None:
    all_logs = [f for f in os.listdir("logs/") if re.match("[0-9]{4}-[01][0-9]-[0-3][0-9]-uptime.log", f)]
    for log_name in all_logs:
        log_path = "logs/" + log_name
        log_last_modified = os.stat(log_path).st_mtime
        if time.time() - log_last_modified > 31*24*60*60 + 120:
            os.remove(log_path)

def perform_daily_tasks() -> None:
    generate_precompute()
    remove_old_logs()


def is_first_of_month() -> bool:
    return time.localtime(time.time()).tm_mday == 1

def generate_month_disruption_report() -> None:
    pass

def generate_month_disruption_graph() -> None:
    pass

def perform_monthly_tasks():
    if is_first_of_month():
        generate_month_disruption_report()
        generate_month_disruption_graph()



def is_accessible(target: str) -> bool:
    command = ["ping", "-n", "1"] if platform.platform().startswith("Windows") else ["ping", "-c", "1"]
    return subprocess.call(command + [target], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) == 0

def start_monitor(target: str, delay: float, use_stdout: bool = False) -> Never:
    if use_stdout:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)
        LOGGER.addHandler(stdout_handler)

    LOGGER.log(100, f"Beginning to monitor {target} every {delay}ms")
    while True:
        start_time = time.time_ns()
        if is_accessible(target):
            LOGGER.info(f"success")
        else:
            LOGGER.warning(f"FAILED")

        delta_time = time.time_ns() - start_time
        sleep_time = (delay / 1000) - (delta_time / 1_000_000_000)
        time.sleep(max(sleep_time, 0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target", 
        default="8.8.8.8", 
        help="The IP(v4/v6) address to ping when checking WAN accessibility"
    )
    parser.add_argument(
        "--period",
        default=2000,
        type=int,
        help="How often, in milliseconds, to ping the target"
    )
    parser.add_argument(
        "--stdout",
        default=False,
        action="store_true",
        help="Disables output to stdout"
    )
    args = parser.parse_args()

    perform_daily_tasks()
    perform_monthly_tasks()
    start_monitor(args.target, args.period, use_stdout=args.stdout)