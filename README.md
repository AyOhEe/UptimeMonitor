# UptimeMonitor
 An internet uptime monitor, with API endpoints to access data and visualisations.

## Description

This repository consists of two programs:
* uptime.py - Regularly pings a configurable target address, on a configurable period.
* api.py - Provides API endpoints for accessing data from uptime.py using FastAPI. 

View the API docs on a running instance under `{SERVER ADDRESS}/docs#/`.

This was an experiment in long-term code running, CI/CD pipelines, data aggregation, and API serving, intended to give me experience in these areas. 

I noticed repeated drops in internet quality, so I wanted concrete empirical evidence of my internet quality to decide whether the problem was as bad as I thought it was, or not that big of a deal.

## Getting Started

### Dependencies

* Python 3.13
* FastAPI >= 0.112.0
* Pygal >= 3.0.5

### Installing

#### Non-CI/CD

* Clone git repo.
```
git clone https://github.com/AyOhEe/UptimeMonitor.git
```
* Create virtual environment and install dependencies.
```
python3 -m venv UptimeMonitor
cd UptimeMonitor
source bin/activate
python3 -m pip install -r requirements.txt
```
* (OPTIONAL) Create logs directory.
```
mkdir /path/to/logs 
chmod 755 /path/to/logs # Ensure the directory contents are usable
```

#### CI/CD
* Fork git repo using GitHub.
* Register an [actions runner](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners) in Settings -> Actions -> Runners -> New self-hosted runner.
* Create a logs directory on the machine hosting your actions runner.
```
mkdir /path/to/logs 
chmod 755 /path/to/logs # Ensure the directory contents are usable
```
* Modify line 2 in both `start_api.py` and `start_uptime.py`, setting `$LOGS_DIR` to the *absolute path* of the logs directory you just created.
* Add a crontab entry to start your actions runner on system start.
```
crontab -e
[...OPENS A TEXT EDITOR...]

# Append at the end of the file
@reboot /path/to/actions-runner/run.sh >> /path/to/actions-runner/runner.log
```
* Restart your machine.

### Executing program

#### Non-CI/CD

* Start the uptime monitor.
```
cd /path/to/UptimeMonitor # Directory that you cloned the repository to
source bin/activate

# Start the uptime monitor and direct all logs to the created directory
python3 uptime.py --target 8.8.8.8 --period 2000 --logs /path/to/logs &
```
* Start the API server.
```
cd /path/to/UptimeMonitor # Directory that you cloned the repository to
source bin/activate

# Start the API server and direct all output (stdout, stderr) to api.log
yes | fastapi run api.py > /path/to/logs/api.log 2> /path/to/logs/api.log &
```
* The API server will be accessible on the same network as the machine it was installed on, on port 8000. E.g. `127.0.0.1:8000`

#### CI/CD

* Navigate to Actions -> "Deploy to Self-hosted runner" on YOUR fork of the repository.
* Click "Run workflow" -> "Run workflow".
* The uptime monitor and API server should spin up within a few minutes.
* When the workflow completes, the API server will be accessible on the same network as the machine hosting the actions runner, on port 8000. E.g. `192.168.0.78:8000`

## Help

Please create an issue on the original GitHub repository (NOT your fork) with as much information as possible, and reproduction conditions if possible.

## Authors

AyOhEe 

## Version History

* 1.0.0
    * Initial Release

## License

This project is licensed under the MIT License - see the LICENSE file for details
