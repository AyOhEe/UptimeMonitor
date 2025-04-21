import pygal
import time
import os
import re
import json
import uptime as ut

from enum import Enum
from typing import List, Tuple
from fastapi import FastAPI, Query, Response
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field


app = FastAPI()


#demo page which uses the endpoints
@app.get("/", response_class=HTMLResponse)
def index_html():
    content = "Failed to load web/index.html"
    with open("web/index.html", "r") as f:
        content = f.read()
    return Response(content, 200, {"Content-Type" : "text/html; charset=utf-8"})

@app.get("/styles.css", response_class=FileResponse)
def styles_css():
    content = "Failed to load web/styles.css"
    with open("web/styles.css", "r") as f:
        content = f.read()
    return Response(content, 200, {"Content-Type" : "text/css; charset=utf-8"})

@app.get("/script.js", response_class=FileResponse)
def script_js():
    content = "Failed to load web/script.js"
    with open("web/script.js", "r") as f:
        content = f.read()
    return Response(content, 200, {"Content-Type" : "text/javascript; charset=utf-8"})


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

def calculate_log_rolling_uptimes(log: List[str]) -> List[Tuple[float, float]]:
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
            uptimes.append((delta_hours, minute_uptime))

    return uptimes

def calculate_uptime_data() -> List[Tuple[float, float]]:
    yesterday = time.localtime(time.time() - 24*60*60)
    yesterday_str = time.strftime('%Y-%m-%d', yesterday)
    yesterday_log = f"logs/{yesterday_str}-uptime.log"
    try:
        with open(yesterday_log, "r") as f:
            log = f.readlines()
    except FileNotFoundError:
        log = []
    
    today = time.localtime()
    today_str = time.strftime('%Y-%m-%d', today)
    today_log = f"logs/{today_str}-uptime.log"
    try:
        with open(today_log, "r") as f:
            log += f.readlines()
    except FileNotFoundError:
        pass

    return calculate_log_rolling_uptimes(log)

#shows past 24hrs of uptime on a graph
@app.get("/uptime_graph.svg", response_class=FileResponse)
def uptime_graph() -> Response:
    graph = pygal.XY(
        x_label_rotation=30,
        x_value_formatter=lambda x: f"{x}hrs",
        y_value_formatter=lambda y: f"{y*100.0:2.1}%",
        show_dots=False,
        width=1500,
        legend_at_bottom=True,
        legend_at_bottom_columns=3
    )
    graph.x_labels = [0, -6, -12, -18, -24]
    graph.y_labels = [0.00, 20.0, 50.0, 70.0, 100.0]

    graph.add("Uptime", calculate_uptime_data())
    graph.add("Disruption end threshold", [
        (-24, 90.0),
        (0, 90.0)
    ])
    graph.add("Disruption start threshold", [
        (-24, 80.0),
        (0, 80.0)
    ])


    return Response(graph.render(), 200, {"Content-Type" : "image/svg+xml"})


class ConnectionResult(Enum):
    FAIL = "FAIL"
    SUCCESS = "SUCCESS"

class ConnectionTest(BaseModel):
    timestamp: int = Field(ge=0)
    result: ConnectionResult

class RawUptimeData(BaseModel):
    entries: List[ConnectionTest] = []

#raw data since provided date, up to 31 days in the past, between now and {period} seconds ago
@app.get("/raw")
def raw(period: int = Query(ge=0, le=31*24*60*60)) -> RawUptimeData:
    return RawUptimeData()


class UptimeReport(BaseModel):
    uptime: float = Field(1.0, ge=0, le=1)

#returns average uptime between now and {period} seconds ago
@app.get("/uptime")
def uptime(period: int = Query(ge=0)) -> UptimeReport:
    return UptimeReport()


class DisruptionInstance(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

class DisruptionHistory(BaseModel):
    disruptions: List[DisruptionInstance] = []

def get_disruptions_past() -> List[DisruptionInstance]:
    disruptions = []
    all_precomputes = [f for f in os.listdir("precomputes/") if re.match("[0-9]{4}-[01][0-9]-[0-3][0-9]-uptime.json", f)]
    for precompute in all_precomputes:
        with open(f"precomputes/{precompute}", "r") as f:
            contents = json.load(f)
            disruptions += contents["disruptions"]


    disruptions = [DisruptionInstance(start=d["start"], end=d["end"]) for d in disruptions]
    return disruptions

def get_disruptions_today() -> List[DisruptionInstance]:
    today = time.localtime()
    today_str = time.strftime('%Y-%m-%d', today)
    today_log = f"logs/{today_str}-uptime.log"
    try:
        with open(today_log, "r") as f:
            log = f.readlines()
    except FileNotFoundError:
        return []

    disruptions = ut.calculate_disruptions(log)
    disruptions = [DisruptionInstance(start=d["start"], end=d["end"]) for d in disruptions]

    return disruptions

#returns a list of all disruptions between now and {period} seconds ago
@app.get("/disruptions")
def disruptions(period: int = Query(ge=0)) -> DisruptionHistory:
    historic = get_disruptions_past()
    today = get_disruptions_today()

    disruptions = historic + today
    disruptions = [d for d in disruptions if time.time() - d.end < period]

    for disruption in disruptions:
        print (time.time() - disruption.end)

    return DisruptionHistory(disruptions=disruptions)