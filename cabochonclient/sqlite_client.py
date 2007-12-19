# Copyright (C) 2007 The Open Planning Project

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor,
# Boston, MA  02110-1301
# USA

from threading import RLock
import os.path
from os import makedirs, listdir, remove as removefile, fstat, fsync
import struct
from restclient import rest_invoke

from decorator import decorator
from simplejson import loads, dumps
import traceback
import time

from datetime import datetime
from sha import sha
from _utility import *
from wsseauth import wsse_header
import logging

from sqlobject import *

log = logging.getLogger("CabochonClient")

@decorator
def locked(proc, *args, **kwargs):
    try:
        args[0].lock.acquire()
        proc(*args, **kwargs)
    finally:
        args[0].lock.release()


class Message(SQLObject):
    url = StringCol()
    message = StringCol()
    
class CabochonSender:
    def __init__(self, message_dir, lock):
        uri = 'sqlite:' + os.path.join(message_dir, 'messages.db')
        Message._connection = connectionForURI(uri)
        Message.createTable(ifNotExists=True)

        self.messages = list(Message.select())
        self.lock = lock
        
    def stop(self):
        self.running = False

    def send_one(self):
        if not len(self.messages):
            return

        try:
            self.lock.acquire()
            message = self.messages[0]
        finally:
            self.lock.release()        
        url, message, id = message.url, message.message, message.id
        
        if not url:
            return url #failure

        log.debug("sending a message")

        params = loads(message)
        headers = {}
        if params.has_key("__extra"):
            extra = params['__extra']
            del params['__extra']
            username = extra['username']
            password = extra['password']
            headers['Authorization'] = 'WSSE profile="UsernameToken"'
            headers['X-WSSE'] = wsse_header(username, password)

        params = dict((key, dumps(value)) for key, value in params.items())        
        
        #try to send it to the server
        result = rest_invoke(url, method="POST", params=params, headers = headers)
        try:
            result = loads(result)
        except ValueError:
            return False
        
        if result.get('status', None) != 'accepted':
            return #failure

        self.messages[0].destroySelf()            
        try:
            self.lock.acquire()
            self.messages = self.messages[1:]
        finally:
            self.lock.release()
        return True

    @locked
    def add_message(self, message):
        self.messages.append(message)

    def send_forever(self):
        self.running = True
        while self.running:
            try:
                if not self.send_one():
                    time.sleep(0.001)
            except Exception, e:
                traceback.print_exc()
                
class CabochonClient:
    def __init__(self, message_dir, server_url = None, username = None, password = None):
        self.message_dir = message_dir
        self.server_url = server_url

        self.username = username
        self.password = password
        
        self.queues = {}
        
        if not os.path.isdir(self.message_dir):
            makedirs(self.message_dir)

        self.lock = RLock()
        self._sender = None

    def test_login(self):
        """Tests whether the given username and password work with the
        given server.  If the server is down, returns False even
        though queued messages with this username/password might
        eventually be accepted."""

        headers = {}        
        if self.username:
            headers['Authorization'] = 'WSSE profile="UsernameToken"'
            headers['X-WSSE'] = wsse_header(self.username, self.password)        
        result, body = rest_invoke(self.server_url + "/event", method="GET", headers = headers, resp=True)
        return result['status'] == '200'
        
    def sender(self):
        if not self._sender:
            self._sender = CabochonSender(self.message_dir, self.lock)
        return self._sender
            
    @locked
    def send_message(self, params, url = None, path=None):
        if not url:
            url = self.server_url
        if path:
            url += path
            log.debug("enqueueing message to %s" % url)
            
        if self.username:
            params['__extra'] = dict(username = self.username,
                                     password = self.password)
        json = dumps(params)
        m = Message(url=url, message=json)
        self._sender.add_message(m)

    def queue(self, event):
        try:
            return self.queues[event]
        except KeyError:
            queue = CabochonMessageQueue(self, event)
            self.queues[event] = queue
            return queue


class CabochonMessageQueue:
    def __init__(self, client, event):
        self.client = client
        self.event = event        

        assert client.server_url

    def send_message(self, params):

        self.client.send_message(params, path="/event/fire_by_name/%s" % self.event)
        
