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
from os import mkdir, listdir, remove as removefile, fstat, fsync
import struct
from restclient import rest_invoke

from decorator import decorator
from simplejson import loads, dumps
import traceback
import time
from random import random
from datetime import datetime
from sha import sha
from _utility import datetime_to_string

RECORD_SEPARATOR = '\x00""""""\x00' 

@decorator
def locked(proc, *args, **kwargs):
    try:
        args[0].lock.acquire()
        proc(*args, **kwargs)
    finally:
        args[0].lock.release()

def find_most_recent(message_dir, prefix, reverse=False):
    files = listdir(message_dir)
    most_recent = 1
    if reverse:
        most_recent = 100000
    for f in files:
        if not f.startswith(prefix): 
            continue
        dot = f.rfind(".")
        if dot == -1:
            continue
        number = int(f[dot + 1:])
        if reverse ^ (number > most_recent):
            most_recent = number    
    return most_recent

class CabochonSender:
    def __init__(self, message_dir, max_file_size = 1000000):
        self.max_file_size = max_file_size
        self.message_dir = message_dir
        self.file_index = find_most_recent(self.message_dir, "messages.", reverse=True)

        try:
            self.log_file = open(os.path.join(self.message_dir, "log.%d" % self.file_index), "r+")
        except IOError:
            self.log_file = open(os.path.join(self.message_dir, "log.%d" % self.file_index), "a+")
        self.message_file = open(os.path.join(self.message_dir, "messages.%d" % self.file_index), "r+")
        message_pos = self.clean_log_file()
        self.calculate_message_file_len()
        self.message_file.seek(message_pos)

    def stop(self):
        self.running = False
        
    def clean_log_file(self):
        log_file = self.log_file
        log_file.seek(0, 2)
        file_len = log_file.tell()
        if file_len % 8:
            log_file.seek (-(file_len % 8), 2)
            log_file.truncate()

        if not file_len:
            return 0
        log_file.seek(-8, 2)
        r_len, = struct.unpack("!q", log_file.read(8))
        return r_len

    def calculate_message_file_len(self):
        self.message_file_len = fstat(self.message_file.fileno())[6]

    def try_rollover(self):
        if not os.path.exists(os.path.join(self.message_dir, "messages.%d" % (self.file_index + 1))):
            return False
        self.log_file.close()
        self.message_file.close()
        removefile("messages.%d" % self.file_index)
        removefile("log.%d" % self.file_index)
        
        self.file_index += 1
        self.log_file = open(os.path.join(self.message_dir, "log.%d" % self.file_index), "r+")
        self.message_file = open(os.path.join(self.message_dir, "messages.%d" % self.file_index), "r")
        self.calculate_message_file_len()
        return True

    def read_message(self):
        message_file = self.message_file
        pos = message_file.tell()
        init_pos = pos

        if self.message_file_len < pos + 24:
            self.calculate_message_file_len()
            if self.message_file_len == pos:
                if not self.try_rollover():
                    return False, False, -1
                    
            if self.message_file_len < pos + 24:
                return False, False, -1 #not enough data for sure

        #try to read a record
        
        url_len, = struct.unpack("!q", message_file.read(8))
        pos += url_len + 8
        if self.message_file_len < pos + 16:
            #middle of a record; back up and fail
            self.message_file.seek(-8, 1)
            return False, False, init_pos
        assert url_len < 10000 
        url = message_file.read(url_len)
        message_len, = struct.unpack("!q", message_file.read(8))
        pos += message_len + 8
        if self.message_file_len < pos + 8:
            #middle of a record
            self.message_file.seek(-(url_len + 16), 1)
            return False, False, init_pos
        assert message_len < 100000000
        message = message_file.read(message_len)
        assert message_file.read(8) == RECORD_SEPARATOR
        return url, message, init_pos

    def rollback_read(self, init_pos):
        self.message_file.seek(init_pos)

    def wsse_header(self, username, password):
        hexdigits = "0123456789abcdef"
        nonce = "".join(hexdigits[int(random() * 16)] for x in range(32))
        created = datetime.utcnow().isoformat() + "Z"
        password_digest = "%s%s%s" % (nonce, created, password)
        password_digest = sha(password_digest).digest().encode("base64")
        
        header = 'UsernameToken Username="%s", PasswordDigest="%s", Nonce="%s", Created="%s"' % (username, password_digest, nonce, created)
        return header
    
    def send_one(self):
        url, message, init_pos = self.read_message()
        if not url:
            return url #failure

        params = loads(message)
        headers = {}
        if params.has_key("__extra"):
            extra = params['__extra']
            del params['__extra']
            username = extra['username']
            password = extra['password']
            headers['Authorization'] = 'WSSE profile="UsernameToken"'
            headers['X-WSSE'] = self.wsse_header(username, password)
        
        #try to send it to the server
        if rest_invoke(url, method="POST", params=loads(message), headers = headers) != '"accepted"':
            self.rollback_read(init_pos)
            return #failure

        self.log_file.write(struct.pack("!q", self.message_file.tell()))
        self.log_file.flush()
        return True

    def send_forever(self):
        self.running = True
        while self.running:
            try:
                if not self.send_one():
                    time.sleep(0.001)
            except Exception, e:
                traceback.print_exc()
                
class CabochonClient:
    def __init__(self, message_dir, server_url = None, max_file_size = 1000000, username = None, password = None):
        self.message_dir = message_dir
        self.server_url = server_url
        self.max_file_size = max_file_size

        self.username = username
        self.password = password
        
        self.queues = {}
        
        if not os.path.isdir(self.message_dir):
            mkdir(self.message_dir)

        #locate the most recent message and log files for the writer
        most_recent = find_most_recent(self.message_dir, "messages.")

        try:
            self.message_file = open(os.path.join(self.message_dir, "messages.%d" % most_recent), "r+")
        except IOError:
            self.message_file = open(os.path.join(self.message_dir, "messages.%d" % most_recent), "a+")
            
        self.clean_message_file()
        self.file_index = most_recent
        self.lock = RLock()
        self._sender = None
        
    def sender(self):
        if not self._sender:
            self._sender = CabochonSender(self.message_dir, max_file_size=self.max_file_size)
        return self._sender
    
    def clean_message_file(self):
        message_file = self.message_file
        #remove the last item in the message buffer if it's not complete
        message_file.seek(0, 2)
        if message_file.tell() < len(RECORD_SEPARATOR):
            message_file.truncate(0)
            return

        message_file.seek(-len(RECORD_SEPARATOR), 2)

        if message_file.read(len(RECORD_SEPARATOR)) == RECORD_SEPARATOR:
            return #the last record is complete

        #we must have a partially-completed record.
        pos = 0
        last_message = ""
        message_file.seek(0, 2)
        file_len = message_file.tell()
        while 1:
            pos -= 4096
            pos = max(pos, -file_len)
            message_file.seek(pos, 2)
            block = message_file.read(4096)
            window = block + last_message
            sep = window.rfind(RECORD_SEPARATOR)
            if sep:
                message_file.seek(pos + sep + len(RECORD_SEPARATOR), 2)
                message_file.truncate()
                break
            last_message = block
            if pos == -file_len:
                message_file.truncate(0)
                break #no messages
        message_file.seek(0, 2) #skip to end

    @locked
    def rollover(self):
        self.file_index += 1
        self.message_file = open(os.path.join(self.message_dir, "messages.%d" % self.file_index), "a")

        
    @locked
    def send_message(self, params, url = None, path=None):
        if not url:
            url = self.server_url
        if path:
            url += path
        if self.username:
            params['__extra'] = dict(username = self.username,
                                     password = self.password)
        json = dumps(params)
        self.message_file.write(struct.pack("!q",len(url)))
        self.message_file.write(url)
        self.message_file.write(struct.pack("!q",len(json)))
        self.message_file.write(json)
        self.message_file.write(RECORD_SEPARATOR)        
        self.message_file.flush()
        fsync(self.message_file.fileno())
        if self.message_file.tell() > self.max_file_size:
            self.rollover()

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
        
