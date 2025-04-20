from fastapi import FastAPI, Query, HTTPException


app = FastAPI()


#demo page which uses the endpoints
@app.get("/")
def index():
    return "Hello, world!"

#shows past 24hrs of uptime on a graph
@app.get("/uptime_graph")
def uptime_graph():
    return "TODO"

#raw data since provided date, up to 31 days in the past, between now and {period} seconds ago
@app.get("/raw")
def raw(period: int = Query(ge=0, le=31*24*60*60)):
    return "TODO"

#returns average uptime between now and {period} seconds ago
@app.get("/uptime")
def uptime(period: int = Query(ge=0)):
    return "TODO"

#returns a list of all disruptions between now and {period} seconds ago
@app.get("/disruptions")
def disruptions(period: int = Query(ge=0)):
    return "TODO"