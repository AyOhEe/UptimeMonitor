# Standard library
import json
import os
import pygal
import re
import time
import uptime as ut

# Standard library "from" statements
from datetime import datetime
from enum import Enum
from typing import List, Tuple

# 3rd party library "from" statements
from fastapi import FastAPI, Query, Response
from fastapi.exceptions import HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field


# Directory containing logs/ and precomputes/
LOGS_DIR = os.getenv("LOGS_DIR", "~/uptime_logs")

# The FastAPI app used to serve this API
app = FastAPI()


# Calculates rolling uptimes over the past two days of log data
# We use two days so we always have at least 24 hours of data for the graph
def calculate_uptime_data() -> List[Tuple[float, float]]:
    # Read the log from yesterday (subtract 24 hours = 24*60*60 seconds),
    # but silently ignore it if it doesn't exist (may not exist on first day of running)
    yesterday = time.localtime(time.time() - 24*60*60)
    yesterday_str = time.strftime('%Y-%m-%d', yesterday)
    yesterday_log = f"{LOGS_DIR}/logs/{yesterday_str}-uptime.log"
    try:
        with open(yesterday_log, "r") as f:
            log = f.readlines()
    except FileNotFoundError:
        log = []
    
    # Read the log from today, and complain if it doesn't exist (we should always have a log today)
    today = time.localtime()
    today_str = time.strftime('%Y-%m-%d', today)
    today_log = f"{LOGS_DIR}/logs/{today_str}-uptime.log"
    try:
        with open(today_log, "r") as f:
            log += f.readlines()
    except FileNotFoundError:
        print(f"Failed to open {today_log}")

    # Process the assembled log
    return ut.calculate_log_rolling_uptimes(log, True)

# Inserts gaps of None in the provided uptime graph data, 
# to separate lines in the event of large time gaps 
def insert_none_at_gaps(data: List[Tuple[float, float]], gap: float) -> List[Tuple[float, float]]:
    # Start at i = 1 so i - 1 == 0 and thus isn't out of bounds
    i = 1 
    while i < len(data):
        # Calculate the difference in timestamps between the two adjacent points
        left = data[i - 1]
        right = data[i]

        # If it's more than the given threshold, add a gap in the graph
        if right[0] - left[0] > gap:
            data.insert(i, (left[0] + gap/3, None))
            data.insert(i + 1, (right[0] - gap/3, None))

            # Skip the two values that we added - they don't need to be processed
            i += 2 
        
        # Move to the next value
        i += 1

    return data

# Shows past 24hrs of uptime on a graph
@app.get("/uptime_graph.svg", response_class=FileResponse)
def uptime_graph() -> Response:
    # Create and render the graph using pygal, as it's threadsafe and lets me save to svg
    graph = pygal.XY(
        x_label_rotation=30,
        x_value_formatter=lambda x: f"{x}hrs",
        show_dots=False,
        show_x_guides=True,
        width=1500,
        legend_at_bottom=True,
        legend_at_bottom_columns=3
    )
    graph.x_labels = [0, -6, -12, -18, -24] # Up to 24 hours in the past, hence negative numbers
    graph.y_labels = [0.00, 20.0, 50.0, 70.0, 100.0] # 0% - 100%

    # Get the data and break lines with gaps of more than a minute
    data = calculate_uptime_data()
    data = insert_none_at_gaps(data, 1/60)

    # Insert it into the graph and explicitly turn on interruptions so we *do* get line breaking
    graph.add("Uptime", data, allow_interruptions=True)

    # Add markers for disruption start and end thresholds
    graph.add("Disruption end threshold", [
        (-24, 90.0),
        (0, 90.0)
    ])
    graph.add("Disruption start threshold", [
        (-24, 80.0),
        (0, 80.0)
    ])

    # Hand the image back to the requester (with the *correct* MIME type)
    return Response(graph.render(), 200, {"Content-Type" : "image/svg+xml"})


# The result of a single attempt to ping a given address
class ConnectionResult(Enum):
    FAIL = False
    SUCCESS = True

# An attempt to ping a given address at a given time
class ConnectionTest(BaseModel):
    timestamp: int = Field(ge=0)
    result: ConnectionResult

# Several attempts to ping a given address over a period of time
class RawUptimeData(BaseModel):
    entries: List[ConnectionTest] = []

# Converts a raw log file into a series of ConnectionTests, with time and result
def process_log_file(log_path: str) -> List[ConnectionTest]:
    tests = []
    # Load the file and iterate through each line (each entry takes up exactly one line)
    with open(log_path, "r") as f:
        for line in f.readlines():
            # Split the entry into segments by whitespace (also removes whitespace at the start and end)
            segments = line.split()
            time = int(segments[0][1:-1]) # The first segment is a timestamp in square brackets

            # Record success and failure entries
            if segments[-1].endswith("FAILED"):
                tests.append(ConnectionTest(timestamp=time, result=ConnectionResult.FAIL))
                
            if segments[-1].endswith("success"):
                tests.append(ConnectionTest(timestamp=time, result=ConnectionResult.SUCCESS))

    return tests

# Raw data since provided date, up to 30 days in the past, between now and {period} seconds ago
@app.get("/raw")
def raw(period: int = Query(ge=0, le=30*24*60*60)) -> RawUptimeData:
    # Load each log from the last 31 days (we only keep 31 days of raw history)
    full_log = []
    for log_path in ut.files_matching_in("[0-9]{4}-[01][0-9]-[0-3][0-9]-uptime.log", f"{LOGS_DIR}/logs/"):
        full_log += process_log_file(f"{LOGS_DIR}/logs/{log_path}")

    # Concatenate the raw uptime log entries that are within the time period
    start_t = time.time()
    for i, entry in enumerate(full_log):
        if entry.timestamp > start_t - period:
            return RawUptimeData(entries=full_log[i:])
    
    # Default to an empty list if no acceptable log entries exist
    return RawUptimeData(entries=[])


# A record of overall uptime for a given time period, [0,100]
class UptimeReport(BaseModel):
    uptime: float = Field(100, ge=0, le=100)

# Returns the average uptime since the provided date
@app.get("/uptime")
def uptime(since: str = Query(regex="[0-9]{4}-[01][0-9]-[0-3][0-9]")) -> UptimeReport:
    # Reject dates in the future, as we won't exactly have logs yet
    start_date = datetime.strptime(since, "%Y-%m-%d")
    if (start_date - datetime.now()).days >= 0:
        raise HTTPException(status_code=424, detail=f"Date ?{since=} is in the future")

    # Iterate through each precompute and store the uptime value if it's in the date range
    historical_uptime = []
    for precompute in ut.files_matching_in("[0-9]{4}-[01][0-9]-[0-3][0-9]-uptime.json", f"{LOGS_DIR}/precomputes/"):
        # Filter logs that are before the cutoff date
        precompute_date = datetime.strptime(precompute[:10], "%Y-%m-%d")
        if (start_date - precompute_date).days > 0:
            continue

        # Store the uptime value
        with open(f"{LOGS_DIR}/precomputes/{precompute}", "r") as f:
            contents = json.load(f)
            historical_uptime.append(contents["daily-uptime"])

    # Read the log from today, and complain if it doesn't exist (we should always have a log today)
    today = time.localtime()
    today_str = time.strftime('%Y-%m-%d', today)
    today_log = f"{LOGS_DIR}/logs/{today_str}-uptime.log"
    today_uptime = 1 # Default to 100% uptime in case the log doesn't exist
    try:
        with open(today_log, "r") as f:
            today_uptime = ut.calculate_uptime_rolling(f.readlines())[1] / 100
    except FileNotFoundError:
        print(f"Failed to open {today_log}")
    
    # Calculate the mean average for our overall uptime value
    overall_uptime = historical_uptime + [today_uptime]
    average_uptime = sum(overall_uptime) / len(overall_uptime)
    
    return UptimeReport(uptime=average_uptime)


# A single instance of disrupted connection, lasting (end - start) seconds
class DisruptionInstance(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

# A full history of disruptions over a given time period
class DisruptionHistory(BaseModel):
    disruptions: List[DisruptionInstance] = []

# Returns disruptions detected in precomputes from past days.
def get_disruptions_past() -> List[DisruptionInstance]:
    # Read and store prior precomputed disruption reports
    disruptions = []
    for precompute in ut.files_matching_in("[0-9]{4}-[01][0-9]-[0-3][0-9]-uptime.json", "{LOGS_DIR}/precomputes/"):
        with open(f"{LOGS_DIR}/precomputes/{precompute}", "r") as f:
            contents = json.load(f)
            disruptions += contents["disruptions"]

    # Convert the dictionaries to DisruptionInstance objects for serialization
    disruptions = [DisruptionInstance(start=d["start"], end=d["end"]) for d in disruptions]
    return disruptions

# Returns disruptions detected in today's log file
def get_disruptions_today() -> List[DisruptionInstance]:
    # Read the log from today, and complain if it doesn't exist (we should always have a log today)
    today = time.localtime()
    today_str = time.strftime('%Y-%m-%d', today)
    today_log = f"{LOGS_DIR}/logs/{today_str}-uptime.log"
    try:
        with open(today_log, "r") as f:
            log = f.readlines()
    except FileNotFoundError:
        print(f"Failed to open {today_log}")
        return [] # Return an empty list - an empty log can't have disruptions

    # Process the log and convert the dictionaries to DisruptionInstance objects for serialization
    disruptions = ut.calculate_disruptions(log)
    disruptions = [DisruptionInstance(start=d["start"], end=d["end"]) for d in disruptions]

    return disruptions

# Returns a list of all disruptions between now and {period} seconds ago
@app.get("/disruptions")
def disruptions(period: int = Query(ge=0)) -> DisruptionHistory:
    # Combine historic disruptions with today's disruptions
    historic = get_disruptions_past()
    today = get_disruptions_today()
    disruptions = historic + today

    # Filter disruptions to only be within the given timespan
    disruptions = [d for d in disruptions if time.time() - d.end < period]

    # Return a serializable object with the disruptions
    return DisruptionHistory(disruptions=disruptions)