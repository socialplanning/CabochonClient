from cabochonclient import CabochonClient
from simplejson import loads, dumps
import tempfile


def test_sender():
    message_dir = tempfile.mkdtemp()
    client = CabochonClient(message_dir, 'http://www.example.com/')
    sender = client.sender()

    #no messages
    url, message, init_pos = sender.read_message()
    assert not url

    #one message
    client.send_message(dict(a=1, b=3,c="three"), url = "http://example.com/")
    url, message, init_pos = sender.read_message()
    assert url == "http://example.com/"
    assert loads(message) == dict(a=1, b=3,c="three")
    assert init_pos == 0
    url, message, init_pos = sender.read_message()
    assert not url

    #two messages
    client.send_message(dict(a=1, b=3,c="three"), url = "http://example.com/")
    client.send_message(dict(new=1), url = "http://example.org/")
    
    url, message, init_pos = sender.read_message()
    assert url == "http://example.com/"
    assert loads(message) == dict(a=1, b=3,c="three")
    
    url, message, init_pos = sender.read_message()
    assert url == "http://example.org/"
    assert loads(message) == dict(new=1)

    #two messages, with intervening failure
    client.send_message(dict(a=1, b=3,c="three"), url = "http://example.com/")
    client.send_message(dict(new=1), url = "http://example.org/")
    url, message, init_pos = sender.read_message()
    assert url == "http://example.com/"
    assert loads(message) == dict(a=1, b=3,c="three")

    #simulate a failure
    sender.rollback_read(init_pos)
    #and read it again
    url, message, init_pos = sender.read_message()
    assert url == "http://example.com/"
    assert loads(message) == dict(a=1, b=3,c="three")
    
    url, message, init_pos = sender.read_message()
    assert url == "http://example.org/"
    assert loads(message) == dict(new=1)
    assert init_pos > 0    

