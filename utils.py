import pytz
from datetime import datetime
from dateutil.tz import tzlocal

weights = [1, 2, 4, 8]


def from_bcd(bits):
    result = 0
    p = 1
    i = 0
    while i < len(bits):
        digit = 0
        j = 0
        while i + j < len(bits) and j < 4:
            if bits[i+j] == '1':
                digit += weights[j]
            j += 1
        result += p*digit
        p *= 10
        i += j
    return result


def print_date(date, print_diff=False):
    system_time = datetime.now().astimezone()
    if print_diff:
        time_diff = system_time-date
    if date is None:
        return
    print(f'\nUTC Time: {date.astimezone(pytz.utc)}')
    print(f'Encoded Time: {date}')
    print(f'Time in your timezone: {date.astimezone(tzlocal())}')
    print(f'System time: {system_time}')
    if print_diff:
        print(f'Time difference: {time_diff}')
