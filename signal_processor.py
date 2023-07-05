import threading
import argparse
from pathlib import Path
from queue import Queue

from abc import ABC, abstractmethod

import sounddevice as sd
import numpy as np
import math
import matplotlib.pyplot as plt

from scipy import signal
from scipy.io import wavfile
from scipy.signal import lfilter

from dcf_77 import dcf_77_decode, Dcf77MessageParser

from utils import print_datetime


class SourceSignal(ABC):
    def __init__(self, sample_rate, sample_count=None):
        self.sample_rate = sample_rate
        self.stream = self.stream(sample_count)

    @abstractmethod
    def stream(self, sample_count):
        pass


class WavFileSignal(SourceSignal):
    def __init__(self, file_name, sample_count=None):
        self.block_size = 1000
        sample_rate, self.file_data = wavfile.read(file_name, mmap=True)
        super().__init__(sample_rate, sample_count)

    def stream(self, sample_count):

        if not sample_count:
            sample_count = len(self.file_data)
        file_data = self.file_data[0:sample_count]
        cnt = 0
        while True:
            data = file_data[cnt:cnt + self.block_size]
            cnt += self.block_size
            yield data
            if len(data) == 0:
                break


class AudioDeviceSignal(SourceSignal):

    def __init__(self, sample_count=None):
        self.processed_count = 0
        self.device_info = sd.query_devices(kind="input")
        sample_rate = self.device_info['default_samplerate']
        super().__init__(sample_rate, sample_count)

    def stream(self, sample_count):
        event = threading.Event()
        queue = Queue()
        self.processed_count = 0

        def audio_callback(indata, samples, time, status):
            if status:
                print(status)
                return
            data = indata[:, 0]
            self.processed_count += samples
            if not (sample_count is None) and self.processed_count > sample_count:
                rest = self.processed_count - sample_count
                data = data[0: -rest]
                stop = True
            else:
                stop = False
            queue.put(data)
            if stop:
                event.set()

        input_stream = sd.InputStream(callback=audio_callback)
        with input_stream:
            while True:
                yield queue.get()
                if event.is_set():
                    break


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
    @staticmethod
    def draw_plots(source_signal, threshold_value):
        source = np.array([])
        envelope = np.array([])
        pwm = np.array([])
        envelope_detector = EnvelopeDetector(source_signal.sample_rate)

        for data in source_signal.stream:
            envelope_signal = envelope_detector.get_envelope(data)
            pwm_signal = threshold(envelope_signal, threshold_value)
            source = np.concatenate([source, data])
            envelope = np.concatenate([envelope, envelope_signal])
            pwm = np.concatenate([pwm, pwm_signal])

        fig, (ax1, ax2) = plt.subplots(2, 1)
        fig.canvas.manager.set_window_title('Signals')
        fig.tight_layout(pad=3)
        ax1.plot(source, label='Source Signal')
        ax1.set_title('Source signal and Envelope')
        ax1.set_xlabel('Samples count')
        ax1.set_ylabel('Amplitude')
        ax1.yaxis.set_label_position("right")
        ax1.plot(envelope, label='Envelope')
        ax1.legend()
        ax2.plot(pwm, color='red')
        ax2.set_title('PWM Signal')
        ax2.set_xlabel('Samples count')
        ax2.set_ylabel('Amplitude')
        ax2.yaxis.set_label_position("right")
        plt.show()

    @staticmethod
    def process_date_time(source_signal, threshold_value):
        print_diff = isinstance(source_signal, AudioDeviceSignal)
        dcf_77_message = ''
        envelope_detector = EnvelopeDetector(source_signal.sample_rate)
        message_parser = Dcf77MessageParser(source_signal.sample_rate)

        for data in source_signal.stream:
            envelope_signal = envelope_detector.get_envelope(data)
            pwm_signal = threshold(envelope_signal, threshold_value)
            symbols = message_parser.parse(pwm_signal)
            print(symbols, end="", flush=True)
            for i in range(len(symbols)):
                if symbols[i] == 'M':
                    try:
                        date = dcf_77_decode(dcf_77_message)
                        print_datetime(date, print_diff=print_diff)
                    except Exception as e:
                        print('\nError parsing DCF77 message:' + str(e), flush=True)
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
        src = WavFileSignal(file_name, sample_count=sample_count)
    elif source == 'audio-device':
        src = AudioDeviceSignal(sample_count=sample_count)
        print("Device Info:")
        print(src.device_info)
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
    print("Command line arguments:")
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

