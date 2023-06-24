import threading
import argparse
from pathlib import Path
from queue import Queue

from abc import ABC

import sounddevice as sd
import numpy as np
import math
import matplotlib.pyplot as plt

from scipy import signal
from scipy.io import wavfile
from scipy.signal import lfilter

from dcf_77 import dcf_77_decode, Dcf77MessageParser

from utils import print_date


class SignalSource(ABC):
    def __init__(self, stream, sample_rate):
        self.sample_rate = sample_rate
        self.stream = stream


class WavFile(SignalSource):
    def __init__(self, file_name, sample_count=None):
        self.sample_rate, self.file_data = wavfile.read(file_name, mmap=True)
        self.stream = self.wav_file_stream(sample_count)

    def wav_file_stream(self, sample_count, block_size=1000):

        if not sample_count:
            sample_count = len(self.file_data)
        file_data = self.file_data[0:sample_count-1]
        cnt = 0
        while True:
            data = file_data[cnt:cnt + block_size]
            cnt += block_size
            yield data
            if len(data) == 0:
                yield None
                break


class AudioDevice(SignalSource):

    def __init__(self, sample_count=None):
        self.cnt = 0
        a = sd.query_devices(kind="input")
        print(a)
        self.sample_rate = a['default_samplerate']
        self.sample_cnt = sample_count
        self.stream = self.audio_device_stream(sample_count)

    def audio_device_stream(self, sample_cnt):
        event = threading.Event()
        queue = Queue()
        self.cnt = 0

        def audio_callback(indata, samples, time, status):
            if status:
                print(status)
                return
            data = indata[:, 0]
            self.cnt += samples
            queue.put(data)
            if not (self.sample_cnt is None) and self.cnt > sample_cnt:
                event.set()

        input_stream = sd.InputStream(callback=audio_callback)
        with input_stream:
            while True:
                yield queue.get()
                if event.is_set():
                    break
        yield None


class EnvelopeDetector:
    def __init__(self, sample_rate, cut_off_frequency=10):
        self.sample_rate = sample_rate
        self.filter = LowPassFilter(sample_rate, cut_off_frequency)

    def get_envelope(self, data):
        arr = np.array([math.fabs(el) for el in data])
        result = self.filter.apply(arr)
        return result


def threshold(data, threshold_value):
    result = np.array([0 if el < threshold_value else 1 for el in data])
    return result


class LowPassFilter:
    def __init__(self, sample_rate, frequency, order=2):
        self.b, self.a = signal.butter(order, frequency, btype='low', fs=sample_rate)
        self.zi = signal.lfilter_zi(self.b, self.a)
        self.first_run = True

    def apply(self, data):
        if self.first_run:
            result, self.zi = lfilter(self.b, self.a, data, zi=data[0] * self.zi)
            self.first_run = False
        else:
            result, self.zi = lfilter(self.b, self.a, data, zi=self.zi)
        return result


class SignalProcessor:

    def draw_plots(signal_source, threshold_value):
        source = np.array([])
        envelope = np.array([])
        pwm = np.array([])
        envelope_detector = EnvelopeDetector(signal_source.sample_rate)

        while True:
            data = next(signal_source.stream)
            if data is None:
                break
            envelope_signal = envelope_detector.get_envelope(data)
            pwm_signal = threshold(envelope_signal, threshold_value)
            source = np.concatenate([source, data])
            envelope = np.concatenate([envelope, envelope_signal])
            pwm = np.concatenate([pwm, pwm_signal])

        fig, (ax1, ax2) = plt.subplots(2, 1)
        ax1.plot(source)
        ax1.plot(envelope)
        ax2.plot(pwm)
        plt.show()

    def process_date_time(signal_source, threshold_value):
        print_diff = isinstance(signal_source, AudioDevice)
        dcf_77_message = ''
        envelope_detector = EnvelopeDetector(signal_source.sample_rate)
        data_detector = Dcf77MessageParser(signal_source.sample_rate)

        while True:
            data = next(signal_source.stream)
            if data is None:
                break
            envelope_signal = envelope_detector.get_envelope(data)
            pwm_signal = threshold(envelope_signal, threshold_value)
            symbols = data_detector.process(pwm_signal)
            print(symbols, end="")
            for i in range(len(symbols)):
                if symbols[i] == 'M':
                    try:
                        date = dcf_77_decode(dcf_77_message)
                        print_date(date, print_diff=print_diff)
                    except Exception as e:
                        print('\nError parsing DCF77 message:' + str(e))
                    dcf_77_message = ''
                else:
                    dcf_77_message += symbols[i]

def validate_file(arg):
    if (file := Path(arg)).is_file():
        return file
    else:
        raise FileNotFoundError(arg)


def process(command, source, sample_count, threshold_value, file_name):
    if source == 'file':
        src = WavFile(file_name, sample_count=sample_count)
    elif source == 'audio-device':
        src = AudioDevice(sample_count=sample_count)
    if command == 'plot':
        SignalProcessor.draw_plots(src, threshold_value=threshold_value)
    elif command == 'decode-dcf77':
        SignalProcessor.process_date_time(src, threshold_value=threshold_value)


def get_command():
    parser = argparse.ArgumentParser(description="Argument parser",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    subparsers = parser.add_subparsers()
    plot_parser = subparsers.add_parser('plot')
    plot_parser.add_argument('-s', '--source', required=True,
                             type=str, choices=['file', 'audio-device'], help='source of signal')
    plot_parser.add_argument('--sample-count', required=True,
                             type=int, help='number of samples to plot')
    plot_parser.add_argument('--threshold', type=float, required=True, help='threshold value')
    plot_parser.add_argument('file-name', nargs='?', default=None,
                             type=validate_file, help='file name of wav file')
    plot_parser.set_defaults(command='plot')

    decode_dcf_77_parser = subparsers.add_parser('decode-dcf77')
    decode_dcf_77_parser.add_argument('-s', '--source', required=True,
                                      type=str, choices=['file', 'audio-device'], help='source of signal')
    decode_dcf_77_parser.add_argument('--threshold', required=True, type=float, help='threshold value')
    decode_dcf_77_parser.add_argument('file-name', nargs='?', default=None, help='file name of wav file')
    decode_dcf_77_parser.set_defaults(command='decode-dcf77')

    args = parser.parse_args()
    config = vars(args)
    print(config)
    if config['source'] == 'file':
        validate_file(config['file-name'])
    if config['command'] == 'decode-dcf77':
        sample_count = None
    else:
        sample_count = config['sample_count']
    return lambda: process(command=config['command'],
                           source=config['source'],
                           sample_count=sample_count,
                           threshold_value=config['threshold'],
                           file_name=config['file-name'])


cmd = get_command()
cmd()

