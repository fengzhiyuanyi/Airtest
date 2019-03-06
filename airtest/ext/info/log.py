#! /usr/bin/env python
# -*- coding:utf-8 -*-
# Author: ljw
import re


class Trace(object):

    def __init__(self, log, package_name=None):
        self.log = log
        self.package_name = package_name

    def analyse(self):
        func = 'analyse_' + self.package_name
        method = getattr(self, func, 'analyse_default')
        return method()

    def analyse_default(self):
        traces = []
        traces_count = []
        traces_type = []
        trace_count = 0
        if self.log:
            lines = self.log.splitlines()
            for i in range(len(lines)):
                if 'Traceback' in lines[i]:
                    new_trace = lines[i]
                    i += 1
                    while 'File' in lines[i]:
                        new_trace += '\n' + lines[i]
                        i += 1
                    new_trace += '\n' + lines[i]
                    trace_count += 1
                    if new_trace in traces:
                        traces_count[traces.index(new_trace)] += 1
                    else:
                        traces.append(new_trace)
                        traces_type.append('TRACEBACK')
                        traces_count.append(1)
        else:
            pass
        return {
            'trace_count': trace_count,
            'traces_type': traces_type,
            'traces_time': "",
            'traces': traces,
            'traces_count': traces_count}

    def analyse_com_netease_wyclx(self):
        self.analyse_default()

    def analyse_com_netease_frxy(self):
        compares = []
        traces = []
        traces_count = []
        traces_type = []
        traces_time = []
        trace_count = 0
        if self.log:
            lines = self.log.splitlines()
            for i in range(len(lines)):
                if '<SCRIPT> ============= TRACEBACK =============' in lines[i]:
                    i, new_trace = pick_by_end(lines, i, '============= END =============')
                    trace_time = re.findall("\[(.*?)\.", lines[i])[0]
                elif '<SCRIPT> Traceback' in lines[i]:
                    i, new_trace = pick_by_contain(lines, i, 'File "')
                    trace_time = re.findall("\[(.*?)\.", lines[i])[0]
                else:
                    continue
                trace_count += 1
                compare = re.sub("\d", "", new_trace)
                if compare in compares:
                    traces_count[compares.index(compare)] += 1
                else:
                    compares.append(compare)
                    traces_type.append('TRACEBACK')
                    traces.append(new_trace)
                    traces_time.append(trace_time)
                    traces_count.append(1)

        else:
            pass
        return {
            'trace_count': trace_count,
            'traces_type': traces_type,
            'traces_time': traces_time,
            'traces': traces,
            'traces_count': traces_count}


def pick_by_end(lines, start_index, end_sign):
    line_count = 1
    new_trace = lines[start_index]
    start_index += 1
    if end_sign in new_trace:
        return start_index, new_trace
    while start_index < len(lines) and end_sign not in lines[start_index] and line_count < 60:
        line_count += 1
        new_trace += '\n' + lines[start_index]
        start_index += 1
    new_trace += '\n' + lines[start_index]
    start_index += 1
    return start_index, new_trace


def pick_by_contain(lines, start_index, continue_sign):
    line_count = 1
    new_trace = lines[start_index]
    start_index += 1
    while start_index < len(lines) and continue_sign in lines[start_index] and line_count < 60:
        line_count += 1
        new_trace += '\n' + lines[start_index]
        start_index += 1
    new_trace += '\n' + lines[start_index]
    start_index += 1
    return start_index, new_trace


def re_filter(content, match):
    res = re.findall(match, content)
    if len(res) > 0:
        return res[0]
    else:
        return ''

