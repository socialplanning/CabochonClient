from cabochonclient import *
from simplejson import loads, dumps
import tempfile
import re
from sha import sha
from datetime import datetime, timedelta

message_dir = tempfile.mkdtemp()
client = CabochonClient(message_dir, 'http://www.example.com/')
sender = client.sender()

# def test_sender():
#     #no messages
#     url, message, init_pos = sender.read_message()
#     assert not url

#     #one message
#     client.send_message(dict(a=1, b=3,c="three"), url = "http://example.com/")
#     url, message, init_pos = sender.read_message()
#     assert url == "http://example.com/"
#     assert loads(message) == dict(a=1, b=3,c="three")
#     assert init_pos == 0
#     url, message, init_pos = sender.read_message()
#     assert not url

#     #two messages
#     client.send_message(dict(a=1, b=3,c="three"), url = "http://example.com/")
#     client.send_message(dict(new=1), url = "http://example.org/")
    
#     url, message, init_pos = sender.read_message()
#     assert url == "http://example.com/"
#     assert loads(message) == dict(a=1, b=3,c="three")
    
#     url, message, init_pos = sender.read_message()
#     assert url == "http://example.org/"
#     assert loads(message) == dict(new=1)

#     #two messages, with intervening failure
#     client.send_message(dict(a=1, b=3,c="three"), url = "http://example.com/")
#     client.send_message(dict(new=1), url = "http://example.org/")
#     url, message, init_pos = sender.read_message()
#     assert url == "http://example.com/"
#     assert loads(message) == dict(a=1, b=3,c="three")

#     #simulate a failure
#     sender.rollback_read(init_pos)
#     #and read it again
#     url, message, init_pos = sender.read_message()
#     assert url == "http://example.com/"
#     assert loads(message) == dict(a=1, b=3,c="three")
    
#     url, message, init_pos = sender.read_message()
#     assert url == "http://example.org/"
#     assert loads(message) == dict(new=1)
#     assert init_pos > 0    


def test_wsse():
    real_password = 'toppzecretpassvord'
    header = wsse_header('bob', real_password)
    wsse_re = re.compile('UsernameToken Username="([^"]+)", PasswordDigest="([^"]+)", Nonce="([^"]+)", Created="([^"]+)"')
    match = wsse_re.match(header)
    username, password_digest, nonce, created = match.groups()
    expected_password_digest = "%s%s%s" % (nonce, created, real_password)
    expected_password_digest = sha(expected_password_digest).digest().encode("base64").strip()
    assert expected_password_digest == password_digest


def test_datetime_to_string():
    date = datetime(2004, 5, 1)
    print datetime_from_string(datetime_to_string(date))
    assert datetime_from_string(datetime_to_string(date)) - date < timedelta(0, 1, 0)
