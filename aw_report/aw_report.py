from contextlib import contextmanager
from enum import Enum

import aw_transform
from aw_client import ActivityWatchClient
import datetime

from aw_core import Event
from aw_transform import union_no_overlap


# ActivityWatch is on: http://localhost:5600/
# YOU MUST SET A SCREEN SAVER, at least a Blank one. Otherwise events won't be logged!

eternity = Event(id=None, timestamp=datetime.datetime(year=2000, month=1, day=1),
                 duration=datetime.timedelta(days=365 * 50), data={'eternity': True})


def complement(events: list[Event]) -> list[Event]:
    """ Returns complement of events. """
    carved_events = aw_transform.union_no_overlap(events, [eternity])
    complement_events = [event for event in carved_events if event.data == eternity.data]
    return complement_events


def subtract(events: list[Event], mask_events: list[Event]) -> list[Event]:
    """ Returns events with parts overlapping mask_events deleted. """
    complement_events = complement(mask_events)
    difference = aw_transform.filter_period_intersect(events, complement_events)
    return difference


class EventKind(Enum):
    UNLOCKED_INACTIVE = 0
    UNLOCKED_ACTIVE = 1
    LOCKED_INACTIVE = 2
    LOCKED_ACTIVE = 3


def generate_html_report(eventesties: list[tuple[EventKind, Event]]):
    """
    Generates an HTML report.
    :param event:          List of events.
    :return: List of HTML lines.
    """
    indent = 0
    result_lines = []

    def _raw_out(txt, same_line):
        if same_line:
            result_lines.append(txt)
        else:
            result_lines.append(f'{"  " * indent}{txt}\n')

    @contextmanager
    def _out_cm(end, same_line):
        nonlocal indent
        indent += 1
        try:
            yield
        finally:
            indent -= 1
            if end is not None:
                _raw_out(end, same_line)

    def out(txt, end=None, same_line=False):
        _raw_out(txt, same_line=same_line)
        return _out_cm(end, same_line=same_line)

    def tag(name, same_line=False, **attributes):
        atts = ''
        if len(attributes) > 0:
            atts = ' ' + ' '.join([f'{key}="{value}"' for key, value in attributes.items()])
        start = f'<{name}{atts}>'
        end = f'</{name}>'
        return out(start, end, same_line=same_line)

    def style(**styles):
        return '; '.join([f'{key.replace("_", "-")}: {value}' for key, value in styles.items()])

    css = """
        .span { box-sizing: border-box; border: 1px solid gray; }
        .span:hover { border: 2px solid red; }
        .unlocked-inactive { background-color: yellow; }
        .unlocked-active { background-color: lightgreen; }
        .locked-inactive { background-color: lightgray; }
        .locked-active { background-color: lightpink; } 
    """

    previous_monday = datetime.date(year=2000, month=1, day=1) # Not exactly Monday, but good enough.
    with tag('html'):
        with tag('head'):
            with tag('style'):
                result_lines.extend(css.split('\n'))

        with tag('body'):

            out('')

            with tag('div'):
                with tag('h1'):
                    out('REPORT')
                for eventes_for_day in [eventesties]:
                    work_events = [event for event_kind, event in eventes_for_day if event_kind != EventKind.LOCKED_INACTIVE]
                    nafk_events = [event for event_kind, event in eventes_for_day if event_kind in [EventKind.UNLOCKED_ACTIVE, EventKind.LOCKED_ACTIVE]]
                    unlocked_events = [event for event_kind, event in eventes_for_day if event_kind in [EventKind.UNLOCKED_ACTIVE, EventKind.UNLOCKED_INACTIVE]]
                    nafk_unlocked_events = [event for event_kind, event in eventes_for_day if event_kind == EventKind.UNLOCKED_ACTIVE]
                    if len(work_events) == 0:
                        continue

                    first_event = work_events[0]
                    last_event = work_events[-1]

                    current_day = first_event.timestamp.date()
                    if  current_day >= previous_monday + datetime.timedelta(days=7):
                        previous_monday = current_day - datetime.timedelta(days=current_day.weekday())
                        with tag('h1'):
                            out('NEW WEEK')

                    date = current_day.strftime('%Y-%m-%d (%a)')
                    start_time = first_event.timestamp.strftime('%H:%M')
                    end_time = (last_event.timestamp + last_event.duration).strftime('%H:%M')
                    duration = str(last_event.timestamp + last_event.duration - first_event.timestamp)

                    nafk_duration = sum((e.duration for e in nafk_events), datetime.timedelta())
                    unlocked_duration = sum((e.duration for e in unlocked_events), datetime.timedelta())
                    nafk_unlocked_duration = sum((e.duration for e in nafk_unlocked_events), datetime.timedelta())
                    with tag('div'):
                        out(f'Day: {date} Times: {start_time} {end_time} Duration: {duration} Logged in: active={nafk_duration} unlocked={unlocked_duration} active-unlocked={nafk_unlocked_duration}')
                        with tag('div'):
                            def time_to_pos(time: datetime.datetime):
                                return 60 * time.hour + time.minute
                            for event_kind, event in eventes_for_day:
                                start_pos = time_to_pos(event.timestamp)
                                end_pos = time_to_pos(event.timestamp + event.duration)

                                cls = {
                                    EventKind.UNLOCKED_ACTIVE: 'unlocked-active',
                                    EventKind.UNLOCKED_INACTIVE: 'unlocked-inactive',
                                    EventKind.LOCKED_ACTIVE: 'locked-active',
                                    EventKind.LOCKED_INACTIVE: 'locked-inactive',
                                }[event_kind]

                                title = f'Duration: {event.duration}\nStart time: {event.timestamp}\nEnd time: {event.timestamp + event.duration}\n{cls}'

                                with tag('div', same_line=True, **{ 'class': f'span {cls}' }, style=style(height='20px', width=f'{end_pos - start_pos}px', display='inline-block', margin='0', padding='0'), title=title):
                                    pass

    return result_lines


def main():
    # Connect to ActivityWatch (use testing=True for safety during development)
    client = ActivityWatchClient('aw-report', testing=False)

    buckets = client.get_buckets()

    def find_bucket(bucket_name: str) -> str:
        """ Returns bucket id. """
        candidate_buckets = [bucket for name, bucket in buckets.items() if bucket['client'] == bucket_name]
        if len(candidate_buckets) != 1:
            raise Exception(f'Expected one {bucket_name=}, but got: {candidate_buckets}')
        return candidate_buckets[0]['id']

    afk_bucket_id = find_bucket('aw-watcher-afk')
    window_bucket_id = find_bucket('aw-watcher-window')

    daystart = datetime.datetime.combine(datetime.datetime.now().date(), datetime.time()).astimezone(datetime.timezone.utc)
    dayend = daystart + datetime.timedelta(days=1)


    whole_day = Event(id=None, timestamp=daystart, duration=dayend - daystart, data={'whole-day': True})

    all_afk_events = client.get_events(afk_bucket_id, start=daystart, end=dayend)
    not_afk_events = [event for event in all_afk_events if event.data['status'] == 'not-afk']
    not_afk_events = aw_transform.filter_period_intersect(not_afk_events, [whole_day])  # I think not necessary, but let's be safe.

    # In window bucket:
    # app:   LockApp.exe
    # title: Windows Default Lock Screen
    all_window_events = client.get_events(window_bucket_id, start=daystart, end=dayend)
    locked_events = [event for event in all_window_events if event.data['app'] == 'LockApp.exe']
    locked_events = aw_transform.filter_period_intersect(locked_events, [whole_day])  # I think not necessary, but let's be safe.

    evs = aw_transform.period_union(not_afk_events, locked_events)

    union_events = aw_transform.period_union(not_afk_events, locked_events)
    both_events = aw_transform.filter_period_intersect(not_afk_events, locked_events)
    only_nafk = subtract(not_afk_events, locked_events)
    only_lock = subtract(locked_events, not_afk_events)
    fill_events = subtract([whole_day], union_events)

    eventesties: list[tuple[EventKind, Event]] = []
    for event in both_events:
        eventesties.append((EventKind.UNLOCKED_ACTIVE, event))
    for event in only_nafk:
        eventesties.append((EventKind.LOCKED_ACTIVE, event))
    for event in only_lock:
        eventesties.append((EventKind.UNLOCKED_INACTIVE, event))
    for event in fill_events:
        eventesties.append((EventKind.LOCKED_INACTIVE, event))

    eventesties.sort(key=lambda v: v[1].timestamp)

    html_report = generate_html_report(eventesties=eventesties)
    with open('aw-report.html', 'wt') as f:
        f.writelines(html_report)


if __name__ == '__main__':
    main()
