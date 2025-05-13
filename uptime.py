# Standard library
import argparse
import datetime
import json
import logging
import os
import platform
import re
import signal
import stat
import subprocess
import sys
import time

# Standard library "from" statements
from typing import Any, Dict, Generator, List, Never, Tuple

# 3rd party libraries
import pygal


# Directory containing logs/ and precomputes/
LOGS_DIR = "~/uptime_logs"

# Add another level to ensure startup messages are always included in logs
logging.addLevelName(100, "START")
LOGGER = logging.getLogger("uptime")
LOGGER.setLevel(logging.INFO)

# Log time as a unix timestamp. Not supported directly, so we monkeypatch a logging.Formatter instance
formatter = logging.Formatter("[%(asctime)s]\t[%(levelname)s]:\t %(message)s")
formatter.formatTime = lambda record, datefmt=None: str(int(time.time()))


# Calculates the uptime percentage for a section of log.
# Until encountering a startup message, assumes 2000ms per log entry.
def calculate_uptime(log: List[str]) -> float:
    # We keep track of the *accounted* time so that gaps don't skew the results
    accounted_uptime = 0
    accounted_downtime = 0

    # Default the period to 2000ms so there's something to work off of
    period = 2000

    # Iterate over every log entry (index isn't important so just iterate over the list)
    for line in log:
        # Split by and remove whitespace (spaces, newlines - default str.strip() behaviour) 
        # so .endswith behaves
        line = line.strip()

        if line.endswith("ms"):
            # Take the last segment split by spaces, remove the last two chars ("ms"), and cast to int
            period = int(line.split(" ")[-1][:-2])
            continue # We've processed this entry, don't bother checking the rest

        elif line.endswith("success"):
            # Account for another period of connection success
            accounted_uptime += period
            continue # We've processed this entry, don't bother checking the rest

        elif line.endswith("FAILED"):
            # Account for another period of connection failure
            accounted_downtime += period
            continue # We've processed this entry, don't bother checking the rest

    # Calculate and return the ratio between accounted uptime and total accounted time
    return accounted_uptime / (accounted_uptime + accounted_downtime)


# Extracts the timestamp from a single log entry
def get_log_entry_time(line: str) -> int:
    # Split by and remove whitespace (spaces, newlines - default str.strip() behaviour) so int behaves
    segments = line.split()

    # Take and return the first segment, removing the square brackets
    t = int(segments[0][1:-1])
    return t

# Extracts the most recent {period} seconds of the provided log 
def get_period_before(log: List[str], start_from: int, period: int) -> List[str]:
    # Work backwards from the marked start point
    end_at = start_from
    # Keep going backwards until we either run out of log, or the time gap is greater than the requested period
    while end_at > 0 and get_log_entry_time(log[start_from]) - get_log_entry_time(log[end_at]) < period:
        end_at -= 1

    # Return the log from end_at and start_from, inclusive of *both* (hence why we add 1)
    return log[end_at:start_from + 1]

def calculate_uptime_rolling(section: List[str], period=2000) -> Tuple[bool, float, float]:
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
        valid, minute_uptime, period = calculate_uptime_rolling(last_minute, period)

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
    global LOGS_DIR

    yesterday = time.localtime(time.time() - 24*60*60)
    yesterday_str = time.strftime('%Y-%m-%d', yesterday)
    yesterday_log = f"{LOGS_DIR}/{yesterday_str}-uptime.log"

    if not os.path.isdir(f"{LOGS_DIR}/precomputes"):
        os.mkdir(f"{LOGS_DIR}/precomputes", stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH | stat.S_IXGRP | stat.S_IXOTH)

    if not os.path.exists(yesterday_log):
        return
    

    with open(f"{LOGS_DIR}/logs/{yesterday_str}-uptime.log", "r") as f:
        log = f.readlines()
        precompute = {
            "daily-uptime": calculate_uptime(log),
            "disruptions": calculate_disruptions(log)
        }
    
    with open(f"{LOGS_DIR}/precomputes/{yesterday_str}-uptime.json", "w") as f:
        json.dump(precompute, f, indent=4)

def remove_old_logs() -> None:
    global LOGS_DIR
    
    all_logs = [f for f in os.listdir(f"{LOGS_DIR}/logs/") if re.match("[0-9]{4}-[01][0-9]-[0-3][0-9]-uptime.log", f)]
    for log_name in all_logs:
        log_path = f"{LOGS_DIR}/logs/{log_name}"
        log_last_modified = os.stat(log_path).st_mtime
        if time.time() - log_last_modified > 31*24*60*60 + 120:
            os.remove(log_path)

def perform_daily_tasks() -> None:
    generate_precompute()
    remove_old_logs()

# Returns true if today is the first of the month
def is_first_of_month() -> bool:
    return time.localtime(time.time()).tm_mday == 1

def calculate_last_month() -> int:
    return ((time.localtime().tm_mon - 2) % 12) + 1

def last_month_precomputes() -> Generator[str, None, None]:
    all_precomputes = [f for f in os.listdir(f"{LOGS_DIR}/precomputes") if re.match("[0-9]{4}-[01][0-9]-[0-3][0-9]-uptime.json", f)]
    last_month = calculate_last_month()
    for precompute in all_precomputes:
        date = time.strptime(precompute[:10], "%Y-%m-%d")
        if date.tm_mon == last_month:
            yield precompute

def generate_month_disruption_report() -> None:
    disruptions = []
    for precompute in last_month_precomputes():
        with open(f"{LOGS_DIR}/precomputes/{precompute}", "r") as f:
            contents = json.load(f)
            disruptions += contents["disruptions"]

    year = time.localtime().tm_year
    last_month = calculate_last_month()
    with open(f"{LOGS_DIR}/precomputes/{year}-{last_month:02}-disruption.json", "w") as f:
        json.dump({ "disruptions" : disruptions }, f, indent=4)

# Creates a graph showing the daily uptime percentage for the past month of available data
def generate_month_disruption_graph() -> None:
    # Filter the precomputed data json files so we've only got last month's data
    year = time.localtime().tm_year
    last_month = calculate_last_month()
    all_precomputes = [f for f in os.listdir(f"{LOGS_DIR}/precomputes") if re.match(f"{year}-{last_month:02}-[0-3][0-9]-uptime.json", f)]
    
    # Consolidate the data (parsing dates when necessary)
    uptimes = []
    dates = []
    for precompute in all_precomputes:
        with open(f"{LOGS_DIR}/precomputes/{precompute}", "r") as f:
            contents = json.load(f)
            # Multiply by 100 to convert from fraction to percent
            uptimes.append(contents["daily-uptime"] * 100) 
        dates.append(datetime.datetime.strptime(precompute[:10], "%Y-%m-%d"))


    # Create and render the graph using pygal, as it's already used by the API server and lets me save to svg
    graph = pygal.DateLine(
        x_label_rotation=30,
        show_dots=False,
        show_x_guides=True,
        width=1500,
        legend_at_bottom=True,
        legend_at_bottom_columns=3
    )
    # Percentage runs from 0% to 100%
    graph.y_labels = [0, 100]

    # Add the data and render. Zip the dates and uptimes to get (X, Y) coordinate pairs for the graph
    # We can't provide the generator directly as DateLine.add expects a collection, not an iterable
    graph.add("Daily uptime", [t for t in zip(dates, uptimes)])
    graph.render_to_file(f"{LOGS_DIR}/precomputes/{year}-{last_month:02}-uptime-graph.svg")

# Performs the tasks due monthly, but only on the first of the month
def perform_monthly_tasks():
    if is_first_of_month():
        generate_month_disruption_report()
        generate_month_disruption_graph()


# Returns True if the target IP address could be pinged once
def is_accessible(target: str) -> bool:
    # Ping takes -n to count the number of attempts on windows, and -c on linux-like/darwin
    command = ["ping", "-n", "1"] if platform.platform().startswith("Windows") else ["ping", "-c", "1"]
    # Feed stdout to the void so it doesn't clog stdout. Errors should still go to stdout
    return subprocess.call(command + [target], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) == 0

# Logs if the target IP address is accessible every delay milliseconds. Returns on the start of a new day.
def start_monitor(target: str, delay: float) -> None:
    # Keep track of the day we started on so we can switch log files when it changes
    start_day = time.localtime().tm_yday

    # Log the startup message (important as it has the target and delay period) on high priority
    LOGGER.log(100, f"Beginning to monitor {target} every {delay}ms")
    while True:
        # Return and start again after moving to a new log file if the day has changed 
        if time.localtime().tm_yday != start_day:
            return

        # Log the result of pinging the target
        start_time = time.time_ns()
        if is_accessible(target):
            LOGGER.info(f"success")
        else:
            LOGGER.warning(f"FAILED")

        # Wait until delay milliseconds after we started pinging the target
        delta_time = time.time_ns() - start_time # Nanoseconds
        sleep_time = (delay / 1000) - (delta_time / 1_000_000_000) # Seconds
        time.sleep(max(sleep_time, 0)) # Ensure we don't pass time.sleep a negative value


# Creates or replaces the .pid file with our PID
def create_pid_file() -> None:
    global LOGS_DIR

    with open(f"{LOGS_DIR}/.pid", "w") as f:
        f.write(str(os.getpid()))

# Removes the .pid file if it exists, and closes the uptime monitor
def remove_pid_file(sig, frame) -> Never:
    global LOGS_DIR

    if os.path.exists(f"{LOGS_DIR}/.pid"):
        os.remove(f"{LOGS_DIR}/.pid")

    exit(0)


# We keep track of FileHandlers so they can be cycled to new files when the day changes.
LAST_HANDLER = None
# Creates and registers a new logging.FileHandler with today's date in the logs directory
def create_logging_handler() -> None:
    global LOGS_DIR
    global LAST_HANDLER

    # Only remove the handler if it exists - this won't be the case on startup
    if not LAST_HANDLER is None:
        LOGGER.removeHandler(LAST_HANDLER)

    # If we don't create the folder with the correct permissions, the GH actions runner environment
    # defaults to creating it with 000 permissions
    TODAY = time.strftime('%Y-%m-%d')
    if not os.path.isdir(f"{LOGS_DIR}/logs"):
        os.mkdir(f"{LOGS_DIR}/logs", stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH | stat.S_IXGRP | stat.S_IXOTH)

    # Point the new FileHandler at today's log file and replace the formatter so logs are consistent
    file_handler = logging.FileHandler(f"{LOGS_DIR}/logs/{TODAY}-uptime.log")
    file_handler.setFormatter(formatter)

    # Make sure we keep track of the handler after it gets assigned
    LOGGER.addHandler(file_handler)
    LAST_HANDLER = file_handler

if __name__ == "__main__":
    # Standard argparse setup
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
        "--logs",
        default="~/uptime_logs",
        type=str,
        help="Directory where logs are stored"
    )
    parser.add_argument(
        "--stdout",
        default=False,
        action="store_true",
        help="Enables output to stdout"
    )
    args = parser.parse_args()


    # It's preferable to not clog stdout unless we're explicitly asked
    if args.stdout:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)
        LOGGER.addHandler(stdout_handler)


    # If we don't create the folder with the correct permissions, the GH actions runner environment
    # defaults to creating it with 000 permissions
    LOGS_DIR = args.logs
    if not os.path.isdir(LOGS_DIR):
        os.mkdir(LOGS_DIR, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH | stat.S_IXGRP | stat.S_IXOTH)

    # Keep a .pid file on hand so GH actions workflows updates can kill the active uptime monitor
    create_pid_file()
    # Remove the .pid file when we're (politely) asked to close. Will not remove if asked less nicely.
    signal.signal(signal.SIGINT, remove_pid_file)
    signal.signal(signal.SIGTERM, remove_pid_file)

    # This is in a loop as it restarts daily at midnight to change over log files, 
    # as well as to perform periodic tasks
    while True:
        create_logging_handler()
        perform_daily_tasks()
        perform_monthly_tasks()

        start_monitor(args.target, args.period)