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


def print_datetime(datetime_with_tz, print_diff=False):
    system_time = datetime.now().astimezone()
    if print_diff:
        time_diff = system_time - datetime_with_tz
    print(f'\nUTC Time: {datetime_with_tz.astimezone(pytz.utc)}', flush=True)
    print(f'Encoded Time: {datetime_with_tz}', flush=True)
    print(f'Time in your timezone: {datetime_with_tz.astimezone(tzlocal())}', flush=True)
    print(f'System time: {system_time}', flush=True)
    if print_diff:
        print(f'Time difference: {time_diff}', flush=True)
