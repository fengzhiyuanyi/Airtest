# coding: utf-8
#

from __future__ import absolute_import, print_function

import threading
import re
import time
import datetime
import csv
import sys
import os
import atexit
from collections import namedtuple

_MEM_PATTERN = re.compile(r'TOTAL[:\s]+(\d+)')
# acct_tag_hex is a socket tag
# cnt_set==0 are for background data
# cnt_set==1 are for foreground data
_NetStats = namedtuple(
    "NetStats",
    """idx iface acct_tag_hex uid_tag_int cnt_set rx_bytes rx_packets
    tx_bytes tx_packets rx_tcp_bytes rx_tcp_packets rx_udp_bytes rx_udp_packets rx_other_bytes rx_other_packets
    tx_tcp_bytes tx_tcp_packets tx_udp_bytes tx_udp_packets tx_other_bytes tx_other_packets"""
    .split())


class Perf(object):
    def __init__(self, d, package_name=None):
        self.d = d
        self.package_name = package_name
        self.csv_output = "perf.csv"
        self.debug = False
        self.interval = 1.0
        self._th = None
        self._event = threading.Event()
        self._condition = threading.Condition()
        self._data = {}

    def shell(self, *args, **kwargs):
        # print("Shell:", args)
        return self.d.shell(*args, **kwargs)

    def memory(self):
        """ PSS(KB) """
        output = self.shell(['dumpsys', 'meminfo', self.package_name])
        m = _MEM_PATTERN.search(output)
        if m:
            return int(m.group(1))
        return 0

    def _cpu_rawdata_collect(self, pid):
        """
        pjiff maybe 0 if /proc/<pid>stat not exists
        """
        first_line = self.shell(['cat', '/proc/stat']).splitlines()[0]
        assert first_line.startswith('cpu ')
        # ds: user, nice, system, idle, iowait, irq, softirq, stealstolen, guest, guest_nice
        ds = list(map(int, first_line.split()[1:]))
        total_cpu = sum(ds)
        idle = ds[3]

        proc_stat = self.shell(['cat',
                                '/proc/%d/stat' % pid]).split(') ')
        pjiff = 0
        if len(proc_stat) > 1:
            proc_values = proc_stat[1].split()
            utime = int(proc_values[11])
            stime = int(proc_values[12])
            pjiff = utime + stime
        return (total_cpu, idle, pjiff)

    def cpu(self, pid):
        """ CPU

        Refs:
        - http://man7.org/linux/man-pages/man5/proc.5.html
        - [安卓性能测试之cpu占用率统计方法总结](https://www.jianshu.com/p/6bf564f7cdf0)
        """
        store_key = 'cpu-%d' % pid
        # first time jiffies, t: total, p: process
        if store_key in self._data:
            tjiff1, idle1, pjiff1 = self._data[store_key]
        else:
            tjiff1, idle1, pjiff1 = self._cpu_rawdata_collect(pid)
            time.sleep(.3)

        # second time jiffies
        self._data[
            store_key] = tjiff2, idle2, pjiff2 = self._cpu_rawdata_collect(pid)

        # calculate
        pcpu = 0.0
        if pjiff1 > 0 and pjiff2 > 0:
            pcpu = 100.0 * (pjiff2 - pjiff1) / (tjiff2 - tjiff1)  # process cpu
        scpu = 100.0 * ((tjiff2 - idle2) -
                        (tjiff1 - idle1)) / (tjiff2 - tjiff1)  # system cpu
        assert scpu > -1  # maybe -0.5, sometimes happens
        scpu = max(0, scpu)
        return round(pcpu, 1), round(scpu, 1)

    def netstat(self, pid):
        """
        Returns:
            (rall, tall, rtcp, ttcp, rudp, tudp)
        """
        m = re.search(r'^Uid:\s+(\d+)',
                      self.shell(['cat', '/proc/%d/status' % pid]),
                      re.M)
        if not m:
            return (0, 0, 0, 0, 0, 0)
        uid = m.group(1)
        lines = self.shell(['cat',
                            '/proc/net/xt_qtaguid/stats']).splitlines()

        traffic = [0] * 6

        def plus_array(arr, *args):
            for i, v in enumerate(args):
                arr[i] = arr[i] + int(v)

        for line in lines:
            vs = line.split()
            if len(vs) != 21:
                continue
            v = _NetStats(*vs)
            if v.uid_tag_int != uid:
                continue
            if v.iface != 'wlan0':
                continue
            # all, tcp, udp
            plus_array(traffic, v.rx_bytes, v.tx_bytes, v.rx_tcp_bytes,
                       v.tx_tcp_bytes, v.rx_udp_bytes, v.tx_udp_bytes)

        store_key = 'netstat-%s' % uid
        result = []
        if store_key in self._data:
            last_traffic = self._data[store_key]
            for i in range(len(traffic)):
                result.append(traffic[i] - last_traffic[i])
        self._data[store_key] = traffic
        return result or [0] * 6

    def _current_view(self, app=None):
        d = self.d
        views = self.shell(['dumpsys', 'SurfaceFlinger',
                            '--list']).splitlines()
        if not app:
            app = d.get_top_activity()
        current = app[0] + "/" + app[1]
        surface_curr = 'SurfaceView - ' + current
        if surface_curr in views:
            return surface_curr
        return current

    def _dump_surfaceflinger(self, view):
        valid_lines = []
        MAX_N = 9223372036854775807
        for line in self.shell(
            ['dumpsys', 'SurfaceFlinger', '--latency',
             view]).splitlines():
            fields = line.split()
            if len(fields) != 3:
                continue
            a, b, c = map(int, fields)
            if a == 0:
                continue
            if MAX_N in (a, b, c):
                continue
            valid_lines.append((a, b, c))
        return valid_lines

    def _fps_init(self):
        view = self._current_view()
        self.shell(["dumpsys", "SurfaceFlinger", "--latency-clear", view])
        self._data['fps-start-time'] = time.time()
        self._data['fps-last-vsync'] = None
        self._data['fps-inited'] = True

    def fps(self, app=None):
        """
        Return float
        """
        if 'fps-inited' not in self._data:
            self._fps_init()
            time.sleep(.2)
        view = self._current_view(app)
        values = self._dump_surfaceflinger(view)
        last_vsync = self._data.get('fps-last-vsync')
        last_start = self._data.get('fps-start-time')
        try:
            idx = values.index(last_vsync)
            values = values[idx + 1:]
        except ValueError:
            pass
        duration = time.time() - last_start
        if len(values):
            self._data['fps-last-vsync'] = values[-1]
        self._data['fps-start-time'] = time.time()
        return round(len(values) / duration, 1)

    def collect(self):
        pid = (int)(self.d.get_top_pid())
        if pid is None:
            return
        app = self.d.get_top_activity()
        pss = self.memory()
        cpu, scpu = self.cpu(pid)
        rbytes, tbytes, rtcp, ttcp = self.netstat(pid)[:4]
        fps = self.fps(app)
        timestr = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        data =  {
            'time': timestr,
            'package': app[0],
            'pss': round(pss / 1024.0, 2),  # MB
            'cpu': cpu,
            'systemCpu': scpu,
            'rxBytes': rbytes,
            'txBytes': tbytes,
            'rxTcpBytes': rtcp,
            'txTcpBytes': ttcp,
            'fps': fps,
        }
        return data

    def continue_collect(self, f):
        try:
            headers = [
                'time', 'package', 'pss', 'cpu', 'systemCpu', 'rxBytes',
                'txBytes', 'rxTcpBytes', 'txTcpBytes', 'fps'
            ]
            fcsv = csv.writer(f)
            fcsv.writerow(headers)
            update_time = time.time()
            while not self._event.isSet():
                perfdata = self.collect()
                if self.debug:
                    print("DEBUG:", perfdata)
                if not perfdata:
                    print("perf package is not alive:", self.package_name)
                    time.sleep(1)
                    continue
                fcsv.writerow([perfdata[k] for k in headers])
                wait_seconds = max(0, self.interval - (time.time() - update_time))
                time.sleep(wait_seconds)
                update_time = time.time()
            f.close()
        finally:
            self._condition.acquire()
            self._th = None
            self._condition.notify()
            self._condition.release()

    def start(self):
        csv_dir = os.path.dirname(self.csv_output)
        if not os.path.isdir(csv_dir):
            os.makedirs(csv_dir)
        if sys.version_info.major < 3:
            f = open(self.csv_output, "wb")
        else:
            f = open(self.csv_output, "w", newline='\n')

        def defer_close():
            if not f.closed:
                f.close()

        atexit.register(defer_close)

        if self._th:
            raise RuntimeError("perf is already running")
        if not self.package_name:
            raise EnvironmentError("package_name need to be set")
        self._data.clear()
        self._event = threading.Event()
        self._condition = threading.Condition()
        self._th = threading.Thread(target=self.continue_collect, args=(f, ))
        self._th.daemon = True
        self._th.start()

    def stop(self):
        self._event.set()
        self._condition.acquire()
        self._condition.wait(timeout=2)
        self._condition.release()
        if self.debug:
            print("DEBUG: perf collect stopped")


if __name__ == '__main__':
    print("threading stopped")