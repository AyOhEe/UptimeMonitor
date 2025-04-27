import subprocess
import sys
import os
import platform
import time
import logging
import argparse
import json
import re
import signal

from typing import List, Dict, Tuple, Never, Any, Generator


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


def get_log_entry_time(line: str) -> int:
    segments = line.split()
    t = int(segments[0][1:-1])
    return t

def get_period_before(log: List[str], i: int, period: int) -> List[str]:
    j = i
    while j > 0 and get_log_entry_time(log[i]) - get_log_entry_time(log[j]) < period:
        j -= 1

    return log[j:i + 1]

def calculate_section_uptime(section: List[str], period=2000) -> Tuple[bool, float, float]:
    accounted_uptime = 0
    accounted_downtime = 0

    if section[0].strip().endswith("ms"):
        period = int(section[0].strip().split()[-1][:-2])

    current_period = period
    for i in range(len(section)):
        line = section[i].strip()
        if line.endswith("ms"):
            current_period = int(line.split(" ")[-1][:-2])
            continue

        elif line.endswith("success"):
            accounted_uptime += current_period
            continue

        elif line.endswith("FAILED"):
            accounted_downtime += current_period
            continue

    if (accounted_uptime + accounted_downtime) == 0:
        return False, None, None

    section_uptime = 100 * accounted_uptime / (accounted_uptime + accounted_downtime)
    return True, section_uptime, period

def calculate_log_rolling_uptimes(log: List[str], give_24hr_delta: bool = True) -> List[Tuple[float, float]]:
    uptimes = []
    period = 2000
    for i, line in enumerate(log):
        delta_t = get_log_entry_time(line) - time.time()
        delta_hours = delta_t / (60 * 60)

        if delta_hours < -24:
            continue

        last_minute = get_period_before(log, i, 60)
        valid, minute_uptime, period = calculate_section_uptime(last_minute, period)

        if valid:
            if give_24hr_delta:
                uptimes.append((delta_hours, minute_uptime))
            else:
                uptimes.append((get_log_entry_time(line), minute_uptime))

    return uptimes

def calculate_disruptions(log: List[str]) -> List[Dict[str, int]]:
    disruptions = []
    start_time = 0
    in_disruption = False
    uptimes = calculate_log_rolling_uptimes(log, False)
    for uptime in uptimes:
        if not in_disruption and uptime[1] < 80:
            start_time = uptime[0]
            in_disruption = True
        elif in_disruption and uptime[1] > 90:
            disruptions.append({ "start" : start_time, "end" : uptime[0]})
            in_disruption = False


    return disruptions

def generate_precompute() -> Dict[str, Any]:
    yesterday = time.localtime(time.time() - 24*60*60)
    yesterday_str = time.strftime('%Y-%m-%d', yesterday)
    yesterday_log = f"logs/{yesterday_str}-uptime.log"

    if not os.path.isdir("precomputes"):
        os.mkdir("precomputes", 777)

    if not os.path.exists(yesterday_log):
        return
    

    with open(f"logs/{yesterday_str}-uptime.log", "r") as f:
        log = f.readlines()
        precompute = {
            "daily-uptime": calculate_uptime(log),
            "disruptions": calculate_disruptions(log)
        }
    
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

def calculate_last_month() -> int:
    return ((time.localtime().tm_mon - 2) % 12) + 1

def last_month_precomputes() -> Generator[str, None, None]:
    all_precomputes = [f for f in os.listdir("precomputes/") if re.match("[0-9]{4}-[01][0-9]-[0-3][0-9]-uptime.json", f)]
    last_month = calculate_last_month()
    print(last_month)
    for precompute in all_precomputes:
        date = time.strptime(precompute[:10], "%Y-%m-%d")
        print(date)
        if date.tm_mon == last_month:
            yield precompute

def generate_month_disruption_report() -> None:
    disruptions = []
    for precompute in last_month_precomputes():
        with open(f"precomputes/{precompute}", "r") as f:
            contents = json.load(f)
            disruptions += contents["disruptions"]

    year = time.localtime().tm_year
    last_month = calculate_last_month()
    with open(f"precomputes/{year}-{last_month:02}-disruption.json", "w") as f:
        json.dump({ "disruptions" : disruptions }, f, indent=4)

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
    start_day = time.localtime().tm_yday
    if use_stdout:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)
        LOGGER.addHandler(stdout_handler)

    LOGGER.log(100, f"Beginning to monitor {target} every {delay}ms")
    while True:
        if time.localtime().tm_yday != start_day:
            return

        start_time = time.time_ns()
        if is_accessible(target):
            LOGGER.info(f"success")
        else:
            LOGGER.warning(f"FAILED")

        delta_time = time.time_ns() - start_time
        sleep_time = (delay / 1000) - (delta_time / 1_000_000_000)
        time.sleep(max(sleep_time, 0))


def create_pid_file():
    with open(".pid", "w") as f:
        f.write(str(os.getpid()))

def remove_pid_file(sig, frame):
    if os.path.exists(".pid"):
        os.remove(".pid")

    exit(0)

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
        help="Enables output to stdout"
    )
    args = parser.parse_args()

    perform_daily_tasks()
    perform_monthly_tasks()

    create_pid_file()

    signal.signal(signal.SIGINT, remove_pid_file)
    signal.signal(signal.SIGTERM, remove_pid_file)

    while True:
        start_monitor(args.target, args.period, use_stdout=args.stdout)