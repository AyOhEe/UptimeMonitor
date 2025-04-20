import pygal

from enum import Enum
from typing import List
from fastapi import FastAPI, Query, Response
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field


app = FastAPI()


#demo page which uses the endpoints
@app.get("/", response_class=HTMLResponse)
def index_html():
    return Response("<h1>Hello, world!</h1><img src='uptime_graph.svg'></img>", 200, {"Content-Type" : "text/html; charset=utf-8"})

@app.get("/styles.css", response_class=FileResponse)
def styles_css():
    return Response("", 200, {"Content-Type" : "text/css; charset=utf-8"})

@app.get("/script.js", response_class=FileResponse)
def script_js():
    return Response("", 200, {"Content-Type" : "text/javascript; charset=utf-8"})


#shows past 24hrs of uptime on a graph
@app.get("/uptime_graph.svg", response_class=FileResponse)
def uptime_graph() -> Response:
    bar_chart = pygal.Bar()
    bar_chart.add('Fibonacci', [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55])

    return Response(bar_chart.render(), 200, {"Content-Type" : "image/svg+xml"})


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
    return []

def get_disruptions_today() -> List[DisruptionInstance]:
    return []

#returns a list of all disruptions between now and {period} seconds ago
@app.get("/disruptions")
def disruptions(period: int = Query(ge=0)) -> DisruptionHistory:
    historic = get_disruptions_past()
    today = get_disruptions_today()

    return DisruptionHistory(disruptions=historic + today)