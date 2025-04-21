import pygal
import time
import os
import re
import json
import uptime as ut

from enum import Enum
from typing import List, Callable
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

    graph.add("Uptime", [
        (-24, 100.0),
        (-17, 90.0),
        (-15, 85.0),
        (-5, 82.5),
        (0, 81.25)
    ])
    graph.add("Disruption end threshold", [
        (-24, 70.0),
        (0, 70.0)
    ])
    graph.add("Disruption start threshold", [
        (-24, 20.0),
        (0, 20.0)
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