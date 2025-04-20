import subprocess
import sys
import os
import platform
import time
import logging
import argparse


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



def generate_precompute():
    pass

def remove_old_logs():
    pass

def perform_daily_tasks():
    generate_precompute()
    remove_old_logs()


def is_first_of_month():
    pass

def generate_month_disruption_report():
    pass

def generate_month_disruption_graph():
    pass

def perform_monthly_tasks():
    if is_first_of_month():
        generate_month_disruption_report()
        generate_month_disruption_graph()



def is_accessible(target: str):
    command = ["ping", "-n", "1"] if platform.platform().startswith("Windows") else ["ping", "-c", "1"]
    return subprocess.call(command + [target], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) == 0

def start_monitor(target: str, delay: float, use_stdout: bool = False):
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