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

formatter = logging.Formatter("[%(asctime)s]\t[%(levelname)s]:\t %(message)s", datefmt="%H:%M:%S")

stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(formatter)


TODAY = time.strftime('%Y-%m-%d')
if not os.path.isdir("logs"):
    os.mkdir("logs", 777)
file_handler = logging.FileHandler(f"logs/{TODAY}-uptime.log")
file_handler.setFormatter(formatter)

LOGGER.addHandler(stdout_handler)
LOGGER.addHandler(file_handler)


def is_accessible(target):
    command = ["ping", "-n", "1"] if platform.platform().startswith("Windows") else ["ping", "-c", "1"]
    return subprocess.call(command + [target], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT) == 0

def start_monitor(target, delay):
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
        help="How often, in milliseconds, to ping the target"
    )
    args = parser.parse_args()


    LOGGER.log(100, f"Beginning to monitor {args.target} every {args.period}ms")
    start_monitor(args.target, args.period)