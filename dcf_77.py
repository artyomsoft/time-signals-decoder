from datetime import datetime, timedelta, timezone
from utils import from_bcd


def dcf_77_validate(bits):
    if len(bits) != 58:
        raise Exception("DCF77 message must contain 58 bits")
        return


def dcf_77_decode(bits):
    dcf_77_validate(bits)
    dcf_date_time = {
        'summer_time_announce': bits[16],
        'cest': bits[17] == '1',
        'cet': bits[18] == '1',
        'leap_sec_announce': bits[19],
        'minute': from_bcd(bits[21:28]),
        'hour': from_bcd((bits[29:35])),
        'day_of_month': from_bcd((bits[36:42])),
        'day_of_week': from_bcd((bits[42:45])),
        'month': from_bcd((bits[45:50])),
        'year': from_bcd((bits[50:58])),
    }
    offset = 2 if dcf_date_time['cest'] else 1

    date = datetime(year=dcf_date_time['year']+2000,
                    month=dcf_date_time['month'],
                    day=dcf_date_time['day_of_month'],
                    hour=dcf_date_time['hour'],
                    minute=dcf_date_time['minute'],
                    tzinfo=timezone(timedelta(hours=offset))
                    )
    return date

class Dcf77MessageParser:
    def __init__(self, sample_rate):
        self.sample_rate = sample_rate
        self.one_length = sample_rate*0.8
        self.zero_length = sample_rate*0.9
        self.end_of_minute_length = sample_rate*2

        self.cnt = 0
        self.prev = 0

    def parse(self, data):
        i = 0
        buff = ''
        while i < len(data):
            if self.prev == 0 and data[i] == 1:
                self.cnt = 1
            elif self.prev == 1 and data[i] == 0:
                if 0.95*self.one_length < self.cnt < 1.05 * self.one_length:
                    buff += '1'
                    self.cnt = 0
                elif 0.95*self.zero_length < self.cnt < 1.05 * self.zero_length:
                    buff += '0'
                    self.cnt = 0
                elif 0.9 * self.end_of_minute_length < self.cnt < 1.1 * self.end_of_minute_length:
                    buff += 'M'
                    self.cnt = 0
                else:
                    buff += 'E'
                    print(self.cnt, end="")
                    self.cnt = 0
            elif self.prev == 1 and data[i] == 1:
                self.cnt += 1
            self.prev = data[i]
            i += 1
        return buff
