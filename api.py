from typing import Union
from fastapi import FastAPI, HTTPException

app = FastAPI()

#used to display other pages
@app.get("/")
def index():
    return "Hello, world!"

#only ever shows past 24hrs
@app.get("/uptime_graph")
def uptime_graph():
    return "TODO"

#raw data since provided date, up to 31 days in the past
@app.get("/raw")
def raw(since: int):
    return "TODO"

#returns average uptime since provided date
@app.get("/uptime")
def uptime(since: int):
    return "TODO"

#returns a list of all disruptions since provided date
@app.get("/disruptions")
def disruptions(since: int):
    return "TODO"