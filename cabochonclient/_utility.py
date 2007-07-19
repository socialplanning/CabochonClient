from datetime import datetime

def datetime_to_string(dt):
    #convert to utc
    dt += datetime.now() - datetime.utcnow()
    return dt.strftime("@%s@")

def datetime_from_string(dt):
    assert dt.startswith("@")
    assert dt.endswith("@")
    return datetime.utcfromtimestamp(int(dt[1:-1]))
