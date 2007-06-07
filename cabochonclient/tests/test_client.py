import os
from restclient import rest_invoke
from wsgiutils import wsgiServer
import paste.wsgiwrappers
from threading import Thread
from cabochonclient import CabochonClient
import time
import tempfile

class CabochonTestServer(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.setDaemon(True)
        
    def run(self):
        self.server_fixture = CabochonServerFixture()
        server = wsgiServer.WSGIServer (('localhost', 10424), {'/': self.server_fixture})
        server.serve_forever()

class CabochonServerFixture:
    def __init__(self):
        self.requests_received = []

    def clear(self):
        self.requests_received = []

    def __call__(self, environ, start_response):
        path_info = environ.get('PATH_INFO', '')
        req = paste.wsgiwrappers.WSGIRequest(environ)
            
        self.requests_received.append({'path' :  environ['PATH_INFO'], 'method' : environ['REQUEST_METHOD'], 'params' : req.params})
            
        if path_info == '/error':
            status = '500 Server Error'
            start_response(status, [('Content-type', 'text/plain')])
            return ['you lose']            
        else:
            status = '200 OK'
            start_response(status, [('Content-type', 'text/plain')])
            return ['"accepted"']

message_dir = tempfile.mkdtemp()
        
test_server = CabochonTestServer()
test_server.start()

cabochon_url = "http://localhost:10424/"

good_event_url = cabochon_url + "event/handle/1"
bad_event_url = cabochon_url + "error/fleem"

client = CabochonClient(message_dir)
sender = client.sender()
t = Thread(target=sender.send_forever)
t.setDaemon(True)
t.start()

def test_message():
    client.send_message({'morx' : 'fleem'}, good_event_url)
    time.sleep(0.01)
    assert test_server.server_fixture.requests_received
