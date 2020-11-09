import csv
import datetime
from contextlib import contextmanager

import pytz
import itertools
from collections import namedtuple
from winevt import EventLog

# This program must be run as an Administrator.
# Tune this date:
global_date_start = '2020-10-20'


EventData = namedtuple('EventData', [
    'begin',                # True if this is a lock event, false if it is unlock event.
    'time',                 # datetime of the event.
])

# See Security ID and Logon ID here:
#   https://blog.netwrix.com/2016/01/15/how-to-get-user-logon-session-times-from-event-log/

#    4648: A logon was attempted using explicit credentials - maybe not...
#    Logon – 4624 (Security event log)
#    Logoff – 4647 (Security event log)
#    Startup – 6005 (System event log)
#    RDP Session Reconnect – 4778 (Security event log)
#    RDP Session Disconnect – 4779 (Security event log)

# 4802(S): The screen saver was invoked. (https://docs.microsoft.com/en-us/windows/security/threat-protection/auditing/event-4802)
# 4803(S): The screen saver was dismissed.

# "4801" - "The workstation was unlocked.",
# "4800" - "The workstation was locked.",
# "7002" - "User Logoff Notification for Customer Experience Improvement Program",
# "1074" - " Shutdown Type: power off".


def isStartEvent(event_id):
    return event_id in ['4801']
    #return event_id in ['4801', '4624', '6005', '4803']


def isEndEvent(event_id):
    return event_id in ['4800', '7002', '1074']
    #return event_id in ['4800', '7002', '1074', '4647', '4802']


def load_data_from_event_log(date_start):
    # We need this date format: '2019-06-01T09:03:26.000Z'
    date_start = datetime.datetime.fromisoformat(date_start).astimezone()
    date_end = datetime.datetime.now().astimezone()
    #date_start = date_start.astimezone(pytz.utc)
    #date_end = date_end.astimezone(pytz.utc)
    #date_start = date_start.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    #date_end = date_end.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    milliseconds = int((date_end - date_start).total_seconds() * 1000)

    # This query was constructed using Event Viewer.
    # See this tutorial: https://blogs.technet.microsoft.com/askds/2011/09/26/advanced-xml-filtering-in-the-windows-event-viewer/
    # Note: Simpler query syntax is also supported. See here: https://github.com/bannsec/winevt
    #eventsCondition = '((EventID &gt;= 4800 and EventID &lt;= 4810) or EventID=4648 or EventID=4647 or EventID=7002 or EventID=1074)'
    eventsCondition = '(EventID=4800 or EventID=4801 or EventID=7002 or EventID=1074)'
    #dateCondition = f"TimeCreated[@SystemTime&gt;='{date_start}' and @SystemTime&lt;='{date_end}']"
    #dateCondition = "TimeCreated[@SystemTime&gt;='2019-06-01T09:03:26.000Z' and @SystemTime&lt;='2019-06-04T09:10:15.999Z']"
    #dateCondition = "TimeCreated[timediff(@SystemTime) &lt;= 2592000000]"
    dateCondition = f"TimeCreated[timediff(@SystemTime) &lt;= {milliseconds}]"
    structuredQuery = f'''
    <QueryList>
      <Query Id="0" Path="Security">
        <Select Path="Security">*[System[{eventsCondition} and {dateCondition}]]</Select>
        <Select Path="System">*[System[{eventsCondition} and {dateCondition}]]</Select>
      </Query>
    </QueryList>
    '''

    query = EventLog.Query('', structuredQuery)
    events = list(query)

    event_datas = []
    for event in events:
        beginEvent = isStartEvent(str(event.EventID))
        endEvent = isEndEvent(str(event.EventID))
        if (not beginEvent) and (not endEvent):
            continue
        timestr = event.System.TimeCreated['SystemTime']
        (time, nSecs) = timestr.split('.')
        time = datetime.datetime.strptime(f'{time}.UTC', '%Y-%m-%dT%H:%M:%S.%Z')
        time = time.replace(tzinfo=pytz.utc)
        time = time.astimezone(date_start.tzinfo)
        data = EventData(begin=beginEvent, time=time)
        event_datas.append(data)

    return event_datas


def load_data_from_csv(file_name):
    """
    Returns list of lists of values from the CSV.
    Format as from Event Viewer:
        - no column headers,
        - Level	DateAndTime	Source	EventID	TaskCategory"
        - "Information	6/26/2019 6:57:11 PM	Microsoft Windows security auditing.	4800	Other Logon/Logoff Events"
    :param file_name:   TSV file.
    :return: List of EventData tuples.
    """
    with open(file_name, newline='') as csvfile:
        reader = csv.reader(csvfile, dialect='excel-tab')
        raw_event_data = list(reader)

    # Convert dates to datetime.
    filtered_raw_data = [event for event in raw_event_data if isStartEvent(event[3]) or isEndEvent(event[3])]
    event_data = [EventData(begin=isStartEvent(event[3]), time=datetime.datetime.strptime(event[1], '%m/%d/%Y %I:%M:%S %p')) for event in filtered_raw_data]

    return event_data


WorkTime = namedtuple('WorkTime', [
    'date',                 # Date.
    'start_time',           # Earliest log in of the day, not earlier than 6:00.
    'end_time',             # Latest log off of the day.
    'duration',             # end_time - start_time
    'logged_in_duration',   # Time user was logged in during the day.
    'logged_out_duration',  # duration - logged_in_duration
    'warnings',             # List of warning strings.
    'events',               # List of events [EventData, ...]
    'paired_events',        # List of paired events [(EventData, EventData), ...]
])

def compute_times(event_data):
    """
    Computes work times for each day.
    Data exported from Event Viewer has the following columns:
        - Level ("Information")
        - Date and Time ("4/16/2019 3:41:53 PM")
        - Source ("Microsoft Windows security auditing.")
        - Event ID
            - "4801" - "The workstation was unlocked.",

            - "4800" - "The workstation was locked.",
            - "7002" - "User Logoff Notification for Customer Experience Improvement Program",
            - "1074" - " Shutdown Type: power off".
        - Task Category ("Other Logon/Logoff Events")
    :param event_data: List of EventData tuples.
    :return: global_warnings: string[], work_times: WorkTime[]
    """

    global_warnings = []   # List of top level string warnings.

    # Remove all events before 6:00, and warn about them.
    bad_time_data = [] #[event for event in event_data if event.time.time() < datetime.time(hour=6)]
    #event_data = [event for event in event_data if event.time.time() >= datetime.time(hour=6)]

    for event in bad_time_data:
        global_warnings.append(f'Ignoring too early event: {event}')

    # Sort by datetimes.
    event_data.sort(key=lambda event: event.time)

    # Group by days.
    day_events = []
    for date, events in itertools.groupby(event_data, lambda event: event.time.date()):
       day_events.append(list(events))    # Store group iterator as a list

    def process_day_events(events):
        """
        In each day's events:
           Find unpaired log-in and log-outs - add them to warnings.
            - warn if first event is log out, and remove that log out
            - warn if after log in the is log in, and remove that log in,
            - repeat
           Find min and max datetime: start_time, end_time.
           Compute logged_in_duration.
           Warn if logged_in_duration if more than 1 hour less than duration.

        :param events: Events for one day.
        :return: WorkTime or None if work time could not be computed.
        """
        paired_events = []
        day_warnings = []

        if len(events) > 0 and (not events[0].begin):
            event = events[0]
            syn_time = datetime.datetime(event.time.year, event.time.month, event.time.day, tzinfo=event.time.tzinfo)
            syn_event = EventData(begin=True, time=syn_time)
            day_warnings.append(f'Synthesized log in at midnight {syn_event} for: {event}')
            events.insert(0, syn_event)

        if len(events) > 0 and events[-1].begin:
            event = events[-1]
            syn_time = datetime.datetime(event.time.year, event.time.month, event.time.day, tzinfo=event.time.tzinfo) + datetime.timedelta(days=1)
            syn_event = EventData(begin=False, time=syn_time)
            day_warnings.append(f'Synthesized log out at midnight {syn_event} for: {event}')
            events.append(syn_event)

        startEvent = None
        for event in events:
            if startEvent is None:
                if event.begin:
                    startEvent = event
                else:
                    day_warnings.append(f'Ignoring log out without log in: {event}')
                continue

            if event.begin:
                day_warnings.append(f'Ignoring second log in without log out in between: {event}')
            else:
                paired_events.append((startEvent, event))
                startEvent = None

        if len(paired_events) == 0:
            day_warnings.append(f'No events left for day: {events[0].time.date()}')
            nonlocal global_warnings
            global_warnings += day_warnings
            return None

        start_date = paired_events[0][0].time
        end_date = paired_events[-1][1].time
        start_time = start_date.time()
        end_time = end_date.time()
        duration = end_date - start_date
        durations = [end_event.time - start_event.time for start_event, end_event in paired_events]
        logged_in_duration = sum(durations, datetime.timedelta(hours=0))
        logged_out_duration = duration - logged_in_duration

        if logged_in_duration < datetime.timedelta(hours=6):
            day_warnings.append(f'Logged in duration is small: {logged_in_duration}')
        if logged_out_duration > datetime.timedelta(hours=1):
            day_warnings.append(f'Logged out duration is large: {logged_out_duration}')

        return WorkTime(date=events[0].time.date(),
                        start_time=start_time,
                        end_time=end_time,
                        duration=duration,
                        logged_in_duration=logged_in_duration,
                        logged_out_duration=logged_out_duration,
                        warnings=day_warnings,
                        events=events,
                        paired_events=paired_events)

    work_times = []
    for events in day_events:
        work_time = process_day_events(events)
        if work_time is not None:
            work_times.append(work_time)

    return global_warnings, work_times


def output_report(global_warnings, work_times):
    """
    Outputs a report to console.
    :param global_warnings:     List of strings.
    :param work_times:          List of WorkTimes.
    """
    print('Global warnings:')
    for warning in global_warnings:
        print(f'  - {warning}')
    print('')

    for work_time in work_times:
        is_monday = work_time.date.weekday()
        if is_monday == 0:
            print('------- NEW WEEK -------')

        date = work_time.date.strftime('%Y-%m-%d (%a)')
        start_time = work_time.start_time.strftime('%H:%M')
        end_time = work_time.end_time.strftime('%H:%M')
        duration = str(work_time.duration)
        logged_in_duration = str(work_time.logged_in_duration)
        logged_out_duration = str(work_time.logged_out_duration)
        print(f'Day: {date} Times: {start_time} {end_time} Duration: {duration} logged-in={logged_in_duration} logged-out={logged_out_duration}')
        if len(work_time.warnings) > 0:
            print('  Warnings:')
            for warning in work_time.warnings:
                print(f'    - {warning}')


def generate_html_report(global_warnings, work_times):
    """
    Generates an HTML report.
    :param global_warnings:     List of strings.
    :param work_times:          List of WorkTimes.
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

    warning_style = style(color='red')

    css = """
        .span { box-sizing: border-box; border: 1px solid gray; }
        .span:hover { border: 2px solid red; }
        .logged-in-out { background-color: lightgreen; }
        .logged-out-in { background-color: lightgray; }
        .logged-in-in { background-color: yellow; }
        .logged-out-out { background-color: lightpink; }
    """
    with tag('html'):
        with tag('head'):
            with tag('style'):
                result_lines.extend(css.split('\n'))

        with tag('body'):

            out('')

            with tag('div'):
                with tag('h1'):
                    out('Global warnings')
                with tag('ul'):
                    for warning in global_warnings:
                        with tag('li', style=warning_style):
                            out(warning)

            out('')

            with tag('div'):
                with tag('h1'):
                    out('REPORT')
                for work_time in work_times:
                    is_monday = work_time.date.weekday()
                    if is_monday == 0:
                        with tag('h1'):
                            out('NEW WEEK')

                    date = work_time.date.strftime('%Y-%m-%d (%a)')
                    start_time = work_time.start_time.strftime('%H:%M')
                    end_time = work_time.end_time.strftime('%H:%M')
                    duration = str(work_time.duration)
                    logged_in_duration = str(work_time.logged_in_duration)
                    logged_out_duration = str(work_time.logged_out_duration)
                    with tag('div'):
                        out(f'Day: {date} Times: {start_time} {end_time} Duration: {duration} Logged in: logged-in={logged_in_duration} logged-out={logged_out_duration}')
                        if len(work_time.events) > 0:
                            with tag('div'):
                                def time_to_pos(time):
                                    return 60 * time.hour + time.minute
                                event = work_time.events[0]
                                day_start = datetime.datetime(event.time.year, event.time.month, event.time.day, tzinfo=event.time.tzinfo)
                                day_end = day_start + datetime.timedelta(hours=23, minutes=59, seconds=59)
                                last_time = day_start
                                events = [EventData(begin=False, time=day_start)] + [event for evs in work_time.paired_events for event in evs] + [EventData(begin=False, time=day_end)]
                                events = [EventData(begin=event.begin, time=min(event.time, day_end)) for event in events]
                                cur_begin = events[0].begin
                                for event in events:
                                    prev_begin = cur_begin
                                    cur_begin = event.begin
                                    start_pos = time_to_pos(last_time)
                                    end_pos = time_to_pos(event.time)
                                    if prev_begin and not cur_begin:
                                        cls = 'logged-in-out'
                                    elif (not prev_begin) and cur_begin:
                                        cls = 'logged-out-in'
                                    elif prev_begin and cur_begin:
                                        cls = 'logged-in-in'
                                    else:
                                        cls = 'logged-out-out'

                                    title = f'Duration: {event.time - last_time}\nStart time: {last_time}\nEnd time: {event.time}\n{cls}'

                                    with tag('div', same_line=True, **{ 'class': f'span {cls}' }, style=style(height='20px', width=f'{end_pos - start_pos}px', display='inline-block', margin='0', padding='0'), title=title):
                                        pass

                                    last_time = event.time

                        if len(work_time.warnings) > 0:
                            with tag('ul'):
                                for warning in work_time.warnings:
                                    with tag('li', style=warning_style):
                                        out(warning)

    return result_lines


def main():
    events = load_data_from_event_log(global_date_start)
    #events = load_data_from_csv('recov-sec.csv')

    global_warnings, work_times = compute_times(events)
    output_report(global_warnings, work_times)

    html_report = generate_html_report(global_warnings, work_times)
    with open('report.html', 'wt') as f:
        f.writelines(html_report)


if __name__ == '__main__':
    main()
