#! /usr/bin/env python
# -*- coding:utf-8 -*-
# Author: ljw
import json

import requests
from airtest.utils.logger import get_logger
import airtest.core.api as airtest


LOGGING = get_logger(__name__)


class TimeoutRequestsSession(requests.Session):
    def __init__(self):
        super(TimeoutRequestsSession, self).__init__()
        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        self.mount("http://", adapter)
        self.mount("https://", adapter)

    def request(self, method, url, **kwargs):
        if kwargs.get('timeout') is None:
            kwargs['timeout'] = 60
        try:
            resp = super(TimeoutRequestsSession, self).request(
                method, url, **kwargs)
        except requests.ConnectionError:
            error_info = str(kwargs.get('data'))
            LOGGING.error(error_info)
        else:
            return resp


class Coor(object):

    def __init__(self, ip=None):
        super(Coor, self).__init__()
        self.rq = TimeoutRequestsSession()
        self.ip = ip if ip is not None else airtest.device().get_ip_address()
        self.url = 'http://' + self.ip + ':9000/jsonrpc/0'

    def coor(self, data):
        self._post_req(data)

    def start_coor(self):
        LOGGING.info("start coor")
        data = {
            "action": "start_coor",
        }
        data = json.dumps(data).encode('utf-8')
        return self._post_req(data)

    def stop_coor(self):
        LOGGING.info("stop coor")
        data = {
            "action": "stop_coor",
        }
        data = json.dumps(data).encode('utf-8')
        return self._post_req(data)

    def _post_req(self, data):
        res = self.rq.post(
            self.url,
            headers={"Content-Type": "application/json"},
            timeout=60,
            data=data)
        return res and 'success' in res
