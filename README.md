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

`aw_report` - still not working.

In order to use it install https://activitywatch.net/.

> **Note:** YOU MUST SET A SCREEN SAVER, at least a Blank one. Otherwise lock events won't be logged!


You need to manually fix `WorkTimingVEnv\Lib\site-packages\aw_transform\union_no_overlap.py`:
```python
"""
Originally from aw-research
"""

from copy import deepcopy
from typing import List, Tuple, Optional
from datetime import datetime, timedelta, timezone

from timeslot import Timeslot

from aw_core import Event


def _split_event(e: Event, dt: datetime) -> Tuple[Event, Event]:
    """ Splits event on given datetime. Raises exception if split point is not within the event. """
    if e.timestamp <= dt <= e.timestamp + e.duration:
        e1 = deepcopy(e)
        e2 = deepcopy(e)
        e1.duration = dt - e.timestamp
        e2.timestamp = dt
        e2.duration = (e.timestamp + e.duration) - dt
        return (e1, e2)

    raise Exception(f'Split point {dt=} is not within event {e=}')


def test_split_event():
    now = datetime(2018, 1, 1, 0, 0).astimezone(timezone.utc)
    td1h = timedelta(hours=1)
    e = Event(timestamp=now, duration=2 * td1h, data={})
    e1, e2 = _split_event(e, now + td1h)
    assert e1.timestamp == now
    assert e1.duration == td1h
    assert e2
    assert e2.timestamp == now + td1h
    assert e2.duration == td1h


def union_no_overlap(events1: List[Event], events2: List[Event]) -> List[Event]:
    """Merges two eventlists and removes overlap, the first eventlist will have precedence

    Example:
      events1  | xxx    xx     xxx     |
      events1  |  ----     ------   -- |
      result   | xxx--  xx ----xxx  -- |
    """
    events1 = deepcopy(events1)
    events2 = deepcopy(events2)

    # I looked a lot at aw_transform.union when I wrote this
    events_union = []
    e1_i = 0
    e2_i = 0
    while e1_i < len(events1) and e2_i < len(events2):
        e1 = events1[e1_i]
        e2 = events2[e2_i]
        e1_p = Timeslot(e1.timestamp, e1.timestamp + e1.duration)
        e2_p = Timeslot(e2.timestamp, e2.timestamp + e2.duration)

        if e1_p.intersects(e2_p):
            if e1.timestamp <= e2.timestamp:
                events_union.append(e1)
                e1_i += 1

                # If e2 continues after e1, we need to split up the event so we only get the part that comes after
                e2_next, e2_next2 = _split_event(e2, e1.timestamp + e1.duration)
                if e2_next2.duration > timedelta(0):
                    events2[e2_i] = e2_next2
                else:
                    e2_i += 1
            else:
                e2_next, e2_next2 = _split_event(e2, e1.timestamp)
                events_union.append(e2_next)
                e2_i += 1
                if e2_next2.duration > timedelta(0):
                    events2.insert(e2_i, e2_next2)
        else:
            if e1.timestamp <= e2.timestamp:
                events_union.append(e1)
                e1_i += 1
            else:
                events_union.append(e2)
                e2_i += 1
    events_union += events1[e1_i:]
    events_union += events2[e2_i:]
    return events_union
```

