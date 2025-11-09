from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum

import aw_transform
import tzlocal
from aw_client import ActivityWatchClient
import datetime

from aw_core import Event
from aw_transform import union_no_overlap


# ActivityWatch is on: http://localhost:5600/
# YOU MUST SET A SCREEN SAVER, at least a Blank one. Otherwise events won't be logged!


local_tz = tzlocal.get_localzone()


eternity = Event(id=None, timestamp=datetime.datetime(year=2000, month=1, day=1, tzinfo=local_tz),
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


class EventType(Enum):
    UNLOCKED_INACTIVE = 0
    UNLOCKED_ACTIVE = 1
    LOCKED_INACTIVE = 2
    LOCKED_ACTIVE = 3
    FILL = 4


@dataclass
class TypedEvent:
    kind: EventType
    event: Event

    @property
    def start(self) -> datetime.datetime:
        return self.event.timestamp.astimezone(local_tz)

    @property
    def end(self) -> datetime.datetime:
        return self.start + self.duration

    @property
    def duration(self) -> datetime.timedelta:
        return self.event.duration


class HtmlReport:
    #         .span { box-sizing: border-box; border: 1px solid gray; }
    css = """
        .span { box-sizing: border-box; border: 0px solid gray; }
        .span:hover { border: 2px solid red; }
        .unlocked-inactive { background-color: yellow; }
        .unlocked-active { background-color: lightgreen; }
        .locked-inactive { background-color: lightgray; }
        .locked-active { background-color: darkgray; }
        .interrupted { background-color: violet; }
        .fill { background-color: lightcyan; }
    """

    def __init__(self):
        self.indent = 0
        self.result_lines = []

    def _raw_out(self, txt, same_line):
        if same_line:
            self.result_lines.append(txt)
        else:
            self.result_lines.append(f'{"  " * self.indent}{txt}\n')

    @contextmanager
    def _out_cm(self, end, same_line):
        self.indent += 1
        try:
            yield
        finally:
            self.indent -= 1
            if end is not None:
                self._raw_out(end, same_line)

    def out(self, txt, end=None, same_line=False):
        self._raw_out(txt, same_line=same_line)
        return self._out_cm(end, same_line=same_line)

    def tag(self, name, same_line=False, **attributes):
        atts = ''
        if len(attributes) > 0:
            atts = ' ' + ' '.join([f'{key}="{value}"' for key, value in attributes.items()])
        start = f'<{name}{atts}>'
        end = f'</{name}>'
        return self.out(start, end, same_line=same_line)

    @staticmethod
    def style(**styles):
        return '; '.join([f'{key.replace("_", "-")}: {value}' for key, value in styles.items()])


def generate_html_report(report: HtmlReport, all_typed_events: list[TypedEvent]):
    """
    Generates an HTML report.
    :param all_typed_events:          List of events. Should be sorted by start time and have no spaces.
    :return: List of HTML lines.
    """
    all_typed_events.sort(key=lambda e: (e.start, e.end))
    previous_monday = datetime.date(year=2000, month=1, day=1) # Not exactly Monday, but good enough.

    with report.tag('div'):
        #with report.tag('h1'):
        #    report.out('REPORT')

        for typed_events_for_day in [all_typed_events]:
            work_events = [typed_event for typed_event in typed_events_for_day if typed_event.kind != EventType.LOCKED_INACTIVE]
            nafk_events = [typed_event for typed_event in typed_events_for_day if typed_event.kind in [EventType.UNLOCKED_ACTIVE, EventType.LOCKED_ACTIVE]]
            unlocked_events = [typed_event for typed_event in typed_events_for_day if typed_event.kind in [EventType.UNLOCKED_ACTIVE, EventType.UNLOCKED_INACTIVE]]
            nafk_unlocked_events = [typed_event for typed_event in typed_events_for_day if typed_event.kind == EventType.UNLOCKED_ACTIVE]
            if len(work_events) == 0:
                continue

            first_event = work_events[0]
            last_event = work_events[-1]

            current_day = first_event.start.date()
            if  current_day >= previous_monday + datetime.timedelta(days=7):
                previous_monday = current_day - datetime.timedelta(days=current_day.weekday())
                #with report.tag('h1'):
                #    report.out('NEW WEEK')

            date = current_day.strftime('%Y-%m-%d (%a)')
            start_time = first_event.start.strftime('%H:%M')
            end_time = last_event.end.strftime('%H:%M')
            duration = str(last_event.end - first_event.start)

            nafk_duration = sum((e.duration for e in nafk_events), datetime.timedelta())
            unlocked_duration = sum((e.duration for e in unlocked_events), datetime.timedelta())
            nafk_unlocked_duration = sum((e.duration for e in nafk_unlocked_events), datetime.timedelta())

            start_of_day = datetime.datetime.combine(current_day, datetime.time()).astimezone(local_tz)
            end_of_day = start_of_day + + datetime.timedelta(days=1)
            scale = 4.0 / 60.0

            def time_to_pos(time: datetime.datetime) -> int:
                return int(scale * (time - start_of_day).total_seconds())

            end_of_day_pos = time_to_pos(end_of_day)
            with report.tag('div', style=report.style(width=f'{end_of_day_pos + 10}px', margin='0', padding='0')):
                report.out(f'Day: {date} Times: {start_time} {end_time} Duration: {duration} Logged in: active={nafk_duration} (green+dark-gray) unlocked={unlocked_duration} (green+yellow) active-unlocked={nafk_unlocked_duration} (green)')

                cur_pos = 0

                with report.tag('div'):
                    for event_index, typed_event in enumerate(typed_events_for_day):
                        start_pos = time_to_pos(typed_event.start)
                        end_pos = time_to_pos(typed_event.end)

                        if start_pos > end_pos:
                            raise Exception(f'{start_pos=} > {end_pos=}')
                        if start_pos < cur_pos:
                            raise Exception(f'{start_pos=} < {cur_pos=}')
                        if start_pos > cur_pos:
                            #raise Exception(f'{start_pos=} > {cur_pos=}')
                            cls = 'interrupted'
                            title = f'End time: {typed_event.start}\n{cls}'
                            with report.tag('div', same_line=True, **{ 'class': f'span {cls}' }, style=report.style(height='20px', width=f'{start_pos - cur_pos}px', display='inline-block', margin='0', padding='0'), title=title):
                                pass
                        cur_pos = start_pos

                        cls = {
                            EventType.UNLOCKED_ACTIVE: 'unlocked-active',
                            EventType.UNLOCKED_INACTIVE: 'unlocked-inactive',
                            EventType.LOCKED_ACTIVE: 'locked-active',
                            EventType.LOCKED_INACTIVE: 'locked-inactive',
                            EventType.FILL: 'fill',
                        }[typed_event.kind]

                        title = f'Duration: {typed_event.duration}\nStart time: {typed_event.start}\nEnd time: {typed_event.end}\n{cls}'
                        with report.tag('div', same_line=True, **{ 'class': f'span {cls}' }, style=report.style(height='20px', width=f'{end_pos - start_pos}px', display='inline-block', margin='0', padding='0'), title=title):
                            pass
                        cur_pos = end_pos

                    if cur_pos < end_of_day_pos:
                        cls = 'interrupted'
                        title = f'End time: {end_of_day}\n{cls}'
                        with report.tag('div', same_line=True, **{ 'class': f'span {cls}' }, style=report.style(height='20px', width=f'{end_of_day_pos - cur_pos}px', display='inline-block', margin='0', padding='0'), title=title):
                            pass
                        cur_pos = end_of_day_pos


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

    #daystart = datetime.datetime.combine(datetime.datetime.now().date(), datetime.time()).astimezone(local_tz)
    daystart = datetime.datetime.combine(datetime.date(year=2025, month=11, day=8), datetime.time()).astimezone(local_tz)
    dayend = daystart + datetime.timedelta(days=1)


    whole_day = Event(id=None, timestamp=daystart, duration=dayend - daystart, data={'whole-day': True})

    all_afk_events = client.get_events(afk_bucket_id, start=daystart, end=dayend)
    not_afk_events = [event for event in all_afk_events if event.data['status'] == 'not-afk']
    afk_events = [event for event in all_afk_events if event.data['status'] == 'afk']
    not_afk_events = aw_transform.filter_period_intersect(not_afk_events, [whole_day])  # I think not necessary, but let's be safe.

    # In window bucket lock screen:
    # Win 11:
    # app:   LockApp.exe
    # title: Windows Default Lock Screen
    # Win 10:
    # app:   unknown
    # title:
    all_window_events = client.get_events(window_bucket_id, start=daystart, end=dayend)
    locked_events = [event for event in all_window_events if event.data['app'] in ['LockApp.exe', 'unknown']]
    locked_events = aw_transform.filter_period_intersect(locked_events, [whole_day])  # I think not necessary, but let's be safe.

    evs = aw_transform.period_union(not_afk_events, locked_events)

    union_events = aw_transform.period_union(not_afk_events, locked_events)
    any_events = aw_transform.period_union(all_afk_events, locked_events)
    both_events = aw_transform.filter_period_intersect(not_afk_events, locked_events)
    only_nafk = subtract(not_afk_events, locked_events)
    only_lock = subtract(locked_events, not_afk_events)
    afky_events = subtract(any_events, union_events)
    fill_events = subtract([whole_day], any_events)

    typed_events: list[TypedEvent] = []
    for event in both_events:
        typed_events.append(TypedEvent(kind=EventType.LOCKED_ACTIVE, event=event))
    for event in only_nafk:
        typed_events.append(TypedEvent(kind=EventType.UNLOCKED_ACTIVE, event=event))
    for event in only_lock:
        typed_events.append(TypedEvent(kind=EventType.LOCKED_INACTIVE, event=event))
    for event in afky_events:
        typed_events.append(TypedEvent(kind=EventType.UNLOCKED_INACTIVE, event=event))
    for event in fill_events:
        typed_events.append(TypedEvent(kind=EventType.FILL, event=event))

    def typeze(events: list[Event], kind: EventType = EventType.UNLOCKED_ACTIVE) -> list[TypedEvent]:
        return [TypedEvent(kind=kind, event=event) for event in events]

    html_report = HtmlReport()
    with html_report.tag('html'):
        with html_report.tag('head'):
            with html_report.tag('style'):
                html_report.result_lines.extend(html_report.css.split('\n'))

        with html_report.tag('body'):

            html_report.out('')
            generate_html_report(html_report, all_typed_events=typeze(not_afk_events, kind=EventType.UNLOCKED_ACTIVE))
            generate_html_report(html_report, all_typed_events=typeze(only_nafk, kind=EventType.UNLOCKED_ACTIVE))
            generate_html_report(html_report, all_typed_events=typeze(locked_events, kind=EventType.UNLOCKED_ACTIVE))
            generate_html_report(html_report, all_typed_events=typeze(only_lock, kind=EventType.UNLOCKED_ACTIVE))
            generate_html_report(html_report, all_typed_events=typeze(union_events, kind=EventType.UNLOCKED_ACTIVE))
            generate_html_report(html_report, all_typed_events=typeze(afky_events, kind=EventType.UNLOCKED_INACTIVE))
            generate_html_report(html_report, all_typed_events=typeze(fill_events, kind=EventType.FILL))
            generate_html_report(html_report, all_typed_events=typed_events)


    with open('aw-report.html', 'wt') as f:
        f.writelines(html_report.result_lines)


if __name__ == '__main__':
    main()
