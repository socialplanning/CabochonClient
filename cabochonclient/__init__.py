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

from threading import Lock
import os.path
from os import mkdir, listdir, remove as removefile
import struct
from restclient import rest_invoke

from decorator import decorator
from simplejson import loads, dumps

RECORD_SEPARATOR = struct.pack("!q",0) #JSON contains no zero bytes.
        
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
    def __init__(self, message_dir):
        self.message_dir = message_dir
        self.file_index = find_most_recent(self.message_dir, "messages.", reverse=True)

        try:
            self.log_file = open(os.path.join(self.message_dir, "log.%d" % self.file_index), "r+")
        except IOError:
            self.log_file = open(os.path.join(self.message_dir, "log.%d" % self.file_index), "a")
        self.message_file = open(os.path.join(self.message_dir, "messages.%d" % self.file_index), "r")
        message_pos = self.clean_log_file()
        self.calculate_message_file_len()
        self.message_file.seek(message_pos)
        
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
        return struct.unpack("!q", log_file.read(8))

    def calculate_message_file_len(self):
        old_pos = self.message_file.tell()
        self.message_file.seek(0, 2)
        self.message_file_len = self.message_file.tell()
        self.message_file.seek(old_pos)

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

    def send_one(self):
        message_file = self.message_file
        pos = message_file.tell()
        if self.message_file_len < pos + 24:
            self.calculate_message_file_len()
            if self.message_file_len == pos:
                if not self.try_rollover():
                    return
                    
            if self.message_file_len < pos + 24:
                return False #not enough data for sure

        #try to read a record
        
        url_len, = struct.unpack("!q", message_file.read(8))
        pos += url_len + 8
        if self.message_file_len < pos + 16:
            #middle of a record; back up and fail
            self.message_file.seek(-8, 1)
            return False
        assert url_len < 10000 
        url = message_file.read(url_len)
        message_len, = struct.unpack("!q", message_file.read(8))
        pos += message_len + 8
        if self.message_file_len < pos + 8:
            #middle of a record
            self.message_file.seek(-(url_len + 16), 1)
            return False
        assert message_len < 100000000
        message = message_file.read(message_len)
        assert message_file.read(8) == RECORD_SEPARATOR

        print "trying to send"
        #try to send it to the server
        if rest_invoke(url, method="POST", params=loads(message)) != '"accepted"':
            self.message_file.seek(pos)
            return #failure

        self.log_file.write(struct.pack("!q", message_file.tell()))
        self.log_file.flush()
        return True

    def send_forever(self):
        while 1:
            self.send_one()

class CabochonClient:
    def __init__(self, message_dir):
        self.message_dir = message_dir
        if not os.path.isdir(self.message_dir):
            mkdir(self.message_dir)

        #locate the most recent message and log files for the writer
        most_recent = find_most_recent(self.message_dir, "messages.")

        try:
            self.message_file = open(os.path.join(self.message_dir, "messages.%d" % most_recent), "r+")
        except IOError:
            self.message_file = open(os.path.join(self.message_dir, "messages.%d" % most_recent), "a")
            
        self.clean_message_file()
        self.file_index = most_recent
        self.lock = Lock()
        self._sender = None
        
    def sender(self):
        if not self._sender:
            self._sender = CabochonSender(self.message_dir)
        return self._sender
    
    def clean_message_file(self):
        message_file = self.message_file
        #remove the last item in the message buffer if it's not complete
        message_file.seek(0, 2)
        if message_file.tell() < len(RECORD_SEPARATOR):
            message_file.truncate(0)
            return

        message_file.seek(-len(RECORD_SEPARATOR), 2)
        if message_file.read(RECORD_SEPARATOR) == RECORD_SEPARATOR:
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
                message_file.truncate(message_file.tell())
                break
            last_message = block
            if pos == -file_len:
                message_file.truncate(0)
                break #no messages
        message_file.seek(0, -2) #skip to end

    @locked
    def rollover(self):
        self.file_index += 1
        self.message_file = open(os.path.join(self.message_dir, "messages.%d" % self.file_index), "a")

        
    @locked
    def send_message(self, params, url):
        json = dumps(params)
        self.message_file.write(struct.pack("!q",len(url)))
        self.message_file.write(url)
        self.message_file.write(struct.pack("!q",len(json)))
        self.message_file.write(json)
        self.message_file.write(RECORD_SEPARATOR)        
        self.message_file.flush()
        if self.message_file.tell() > 1000000:
            self.rollover()

