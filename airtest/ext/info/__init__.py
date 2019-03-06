import json
import os
import datetime
import atexit
import conf
from airtest.ext.info.log import Trace


class Info(object):
    def __init__(self, driver, package_name=None):
        self._driver = driver
        self.output_dir = 'report/'
        self.pkg_name = package_name
        self.test_info = {}
        atexit.register(self.write_info)

    def read_file(self, filename):
        try:
            with open(self.output_dir + filename, 'r') as f:
                return f.read()
        except IOError as e:
            print(os.strerror(e.errno), self.output_dir + filename)

    def get_basic_info(self):
        device_info = self._driver.device_info
        app_info = self._driver.app_info(self.pkg_name)
        # query for exact model info
        if device_info['model'] in conf.phones:
            device_info['model'] = conf.phones[device_info['model']]
        self.test_info['basic_info'] = {'device_info': device_info, 'app_info': app_info}

    def get_app_icon(self):
        icon = self._driver.app_icon(self.pkg_name)
        file_path = self.output_dir + 'icon.png'
        icon.save(file_path)

    def get_record_info(self):
        record = json.loads(self.read_file('record.json'))
        steps = len(record['steps'])
        start_time = datetime.datetime.strptime(record['steps'][0]['time'],
                                                '%H:%M:%S')
        end_time = datetime.datetime.strptime(
            record['steps'][steps - 1]['time'], '%H:%M:%S')
        total_time = end_time - start_time
        self.test_info['record_info'] = {
            'steps': steps,
            'start_time': record['steps'][0]['time'],
            'total_time': str(total_time)
        }

    def get_result_info(self):
        file_path = self.output_dir + 'log.txt'
        if os.path.exists(file_path):
            content = self.read_file('log.txt')
            param = 'default'
            if self.pkg_name:
                param = self.pkg_name.replace('.', '_')
            trace = Trace(content, param)
            traces = trace.analyse()
            self.test_info['trace_info'] = traces
        else:
            self.test_info['trace_info'] = {'trace_count': 0}

    def start(self):
        self.get_basic_info()
        self.get_app_icon()

    def write_info(self):
        # self.get_basic_info()
        self.get_record_info()
        self.get_result_info()
        file_path = self.output_dir + 'info.json'
        if not os.path.exists(self.output_dir):
            os.mkdir(self.output_dir)
        if not os.path.exists(file_path):
            os.mknod(file_path)
        with open(file_path, 'wb') as f:
            f.write(json.dumps(self.test_info))


if __name__ == '__main__':
    info = Info(None, 'com.netease.frxy')
    info.get_result_info()
    print(info.test_info)
