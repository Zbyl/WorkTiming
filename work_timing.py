import csv
import datetime
import itertools
from collections import namedtuple


def load_data(file_name):
    """
    Returns list of lists of values from the CSV.
    :param file_name:   TSV file.
    :return: List of lists of strings.
    """
    with open(file_name, newline='') as csvfile:
        reader = csv.reader(csvfile, dialect='excel-tab')
        rows = list(reader)
        return rows


WorkTime = namedtuple('WorkTime', [
    'date',                 # Date.
    'start_time',           # Earliest log in of the day, not earlier than 6:00.
    'end_time',             # Latest log off of the day.
    'duration',             # end_time - start_time
    'logged_in_duration',   # Time user was logged in during the day.
    'logged_out_duration',  # duration - logged_in_duration
    'warnings',             # List of warning strings.
])


EventData = namedtuple('EventData', [
    'begin',                # True if this is a lock event, false if it is unlock event.
    'time',                 # datetime of the event.
])


def compute_times(raw_event_data):
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
    :param raw_event_data: List of lists of values.
    :return: global_warnings: string[], work_times: WorkTime[]
    """

    global_warnings = []   # List of top level string warnings.

    def isStartEvent(event_id):
        return event_id in ['4801']

    def isEndEvent(event_id):
        return event_id in ['4800', '7002', '1074']

    # Convert dates to datetime.
    filtered_raw_data = [event for event in raw_event_data if isStartEvent(event[3]) or isEndEvent(event[3])]
    event_data = [EventData(begin=isStartEvent(event[3]), time=datetime.datetime.strptime(event[1], '%m/%d/%Y %I:%M:%S %p')) for event in filtered_raw_data]

    # Remove all events before 6:00, and warn about them.
    bad_time_data = [event for event in event_data if event.time.time() < datetime.time(hour=6)]
    event_data = [event for event in event_data if event.time.time() >= datetime.time(hour=6)]

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

        return WorkTime(date=events[0].time.date(), start_time=start_time, end_time=end_time, duration=duration, logged_in_duration=logged_in_duration, logged_out_duration=logged_out_duration, warnings=day_warnings)

    work_times = []
    for events in day_events:
        work_time = process_day_events(events)
        if work_time is not None:
            work_times.append(work_time)

    return global_warnings, work_times


def output_report(global_warnings, work_times):
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
        print(f'{"WARN: " if len(work_time.warnings) > 0 else ""}Day: {date} Times: {start_time} {end_time} Duration: {duration} Logged in: logged-in={logged_in_duration} logged-out={logged_out_duration}')
        if len(work_time.warnings) > 0:
            print('  Warnings:')
            for warning in work_time.warnings:
                print(f'    - {warning}')


def main():
    events = load_data('SummaryAprMay.tsv')
    global_warnings, work_times = compute_times(events)
    output_report(global_warnings, work_times)


if __name__ == '__main__':
    main()
