# WorkTiming

## Main Directory - old version

`work_timing.py`
- Main script.
- Was evolving a bit:
  - Initially it extracted data from Event Viewer (system logs).
  - Then after Python package for extracting the data broke it extracted data from .tsv files exported from Event Viewer.
  - Then it was using a log file based on events/heartbeats that were logging every x minutes (run by Task Scheduler).
  - Finally now it is using a log file based on Connect, Disconnect, Lock, etc. events run by Task Scheduler.
    - `WorkTiming *.xml` files contain Task Scheduler tasks for that (they must be imported manually).
    - `login.bat` is being run and outputs to `login.txt`. 

Next iteration will be working based on ActivityWatch.

## ActivityWatch-based version

`aw_report` - currently broken

In order to use it install https://activitywatch.net/.

> **Note:** YOU MUST SET A SCREEN SAVER, at least a Blank one. Otherwise events won't be logged!

