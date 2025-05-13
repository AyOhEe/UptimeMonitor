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


# Creates the directory at path if it does not already exist
def create_directory_if_missing(path: str) -> None:
    # If we don't create the folder with the correct permissions, the GH actions runner environment
    # defaults to creating it with 000 permissions
    if not os.path.isdir(path):
        os.mkdir(path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH | stat.S_IXGRP | stat.S_IXOTH)

# Returns all files in path with filenames matching the provided regular expression
def files_matching_in(regex: str, path: str) -> List[str]:
    return [f for f in os.listdir(path) if re.match(regex, f)]

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

# Calculates the rolling uptime for a section of logs, and returns the updated period between entries
def calculate_uptime_rolling(section: List[str], period=2000) -> Tuple[bool, float, float]:
    # We're really returning the ratio between recorded uptime and downtime. We don't know what
    # happens in gaps, so we don't assume.
    accounted_uptime = 0
    accounted_downtime = 0

    for i in range(len(section)):
        # Removing whitespace (like \n) makes .endswith behave
        line = section[i].strip()
        # When we run into a starting message, update our period for accurate weighting
        if line.endswith("ms"):
            period = int(line.split(" ")[-1][:-2])
            continue

        # Otherwise just record success and failure entries
        elif line.endswith("success"):
            accounted_uptime += period
            continue

        elif line.endswith("FAILED"):
            accounted_downtime += period
            continue

    # If we didn't successfully record any data, inform the caller that this is a bad entry
    if (accounted_uptime + accounted_downtime) == 0:
        return False, None, None

    # Return the uptime percentage [0,100] and the new period
    section_uptime = 100 * accounted_uptime / (accounted_uptime + accounted_downtime)
    return True, section_uptime, period

# Calculates 60-second rolling uptimes for the entire log segment provided
def calculate_log_rolling_uptimes(log: List[str], give_24hr_delta: bool = True) -> List[Tuple[float, float]]:
    # Iterate through each log entry and assume a starting period of 2000ms (overriden on starting entries)
    uptimes = []
    period = 2000
    for i, line in enumerate(log):
        # Only consider the last 24 hours of data
        delta_t = get_log_entry_time(line) - time.time()
        delta_hours = delta_t / (60 * 60)

        if delta_hours < -24:
            continue

        # Separate the last minute of data before this log and calculate a rolling uptime
        # We update and keep track of the period each time as it may change, and those
        # Datapoints have a different weighting on the overall uptime
        last_minute = get_period_before(log, i, 60)
        valid, minute_uptime, period = calculate_uptime_rolling(last_minute, period)

        # If the segment has little-to-no data it may be rejected, so only store it if it's good
        if valid:
            # In the case of storing data we want timestamps, but when displaying data we want a delta
            if give_24hr_delta:
                uptimes.append((delta_hours, minute_uptime))
            else:
                uptimes.append((get_log_entry_time(line), minute_uptime))

    return uptimes

# Calculates the moments in the log file where uptime was below acceptable thresholds for a sustained period
def calculate_disruptions(log: List[str]) -> List[Dict[str, int]]:
    disruptions = []
    uptimes = calculate_log_rolling_uptimes(log, False) # The rolling uptimes to calculate with

    # We keep track of whether or not we're in a disruption period, and store it when we leave one
    start_time = 0
    in_disruption = False
    for uptime in uptimes:
        # Only enter a disruption when uptime goes below 80%, and only recover when uptime is above 90%
        if not in_disruption and uptime[1] < 80:
            start_time = uptime[0]
            in_disruption = True
        elif in_disruption and uptime[1] > 90:
            disruptions.append({ "start" : start_time, "end" : uptime[0]})
            in_disruption = False


    return disruptions

# Precomputes uptime metrics from the raw uptime log recorded yesterday
def generate_precompute() -> Dict[str, Any]:
    global LOGS_DIR

    # Find the name of yesterday's log
    yesterday = time.localtime(time.time() - 24*60*60)
    yesterday_str = time.strftime('%Y-%m-%d', yesterday)
    yesterday_log = f"{LOGS_DIR}/{yesterday_str}-uptime.log"

    # Ensure the precomputes directory actually exists
    create_directory_if_missing(f"{LOGS_DIR}/precomputes")

    # Ensure we don't work on a log that doesn't exist (this will be the case for fresh installs)
    if not os.path.exists(yesterday_log):
        return
    

    # Open yesterday's log, create the data, and store it to a json file
    with open(f"{LOGS_DIR}/logs/{yesterday_str}-uptime.log", "r") as f:
        log = f.readlines()
        precompute = {
            "daily-uptime": calculate_uptime_rolling(log)[1] or 0.0, # If the data is bad, default to 0%
            "disruptions": calculate_disruptions(log)
        }
    
    with open(f"{LOGS_DIR}/precomputes/{yesterday_str}-uptime.json", "w") as f:
        json.dump(precompute, f, indent=4)

# Removes logs older than 31 days from the logs directory, as precomputes store the necessary data
def remove_old_logs() -> None:
    global LOGS_DIR
    
    # Find and iterate over each log
    for log_name in files_matching_in("[0-9]{4}-[01][0-9]-[0-3][0-9]-uptime.log", f"{LOGS_DIR}/logs/"):
        log_path = f"{LOGS_DIR}/logs/{log_name}"
        log_last_modified = os.stat(log_path).st_mtime

        # Compare the last modification with the current time in seconds, with a two minute buffer
        # to account for potential restart delays
        if time.time() - log_last_modified > 31*24*60*60 + 120:
            os.remove(log_path)

# Performs the tasks due daily, at the start of the day
def perform_daily_tasks() -> None:
    generate_precompute()
    remove_old_logs()


# Returns true if today is the first of the month
def is_first_of_month() -> bool:
    return time.localtime(time.time()).tm_mday == 1

# Returns the number [1,12] == [Jan, Dec] representing the month of the year
def calculate_last_month() -> int:
    return time.localtime().tm_mon

# Yields each precomputed data json file found from last month
def last_month_precomputes() -> Generator[str, None, None]:
    # Filter the precomputed data json files so we've only got last month's data
    last_month = calculate_last_month()
    for precompute in files_matching_in("[0-9]{4}-[01][0-9]-[0-3][0-9]-uptime.json", f"{LOGS_DIR}/precomputes"):
        # Double check that we're only providing data from last month
        date = time.strptime(precompute[:10], "%Y-%m-%d")
        if date.tm_mon == last_month:
            yield precompute

# Precomputes a disruption report for the month, consolidating all of last month's data
def generate_month_disruption_report() -> None:
    # Iterate through each precompute we find, and store each disruption logged in them
    disruptions = []
    for precompute in last_month_precomputes():
        with open(f"{LOGS_DIR}/precomputes/{precompute}", "r") as f:
            contents = json.load(f)
            disruptions += contents["disruptions"]

    # Store each of them under a disruption report json file for last month
    year = time.localtime().tm_year
    last_month = calculate_last_month()
    with open(f"{LOGS_DIR}/precomputes/{year}-{last_month:02}-disruption.json", "w") as f:
        json.dump({ "disruptions" : disruptions }, f, indent=4)

# Creates a graph showing the daily uptime percentage for the past month of available data
def generate_month_disruption_graph() -> None:
    # Filter the precomputed data json files so we've only got last month's data
    year = time.localtime().tm_year
    last_month = calculate_last_month()
    
    # Consolidate the data (parsing dates when necessary)
    uptimes = []
    dates = []
    for precompute in files_matching_in(f"{year}-{last_month:02}-[0-3][0-9]-uptime.json", f"{LOGS_DIR}/precomputes"):
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

    # Ensure the logs directory actually exists
    create_directory_if_missing(f"{LOGS_DIR}/logs")

    # Point the new FileHandler at today's log file and replace the formatter so logs are consistent
    TODAY = time.strftime('%Y-%m-%d')
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

    # Ensure the logs directory actually exists
    LOGS_DIR = args.logs
    create_directory_if_missing(LOGS_DIR)

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