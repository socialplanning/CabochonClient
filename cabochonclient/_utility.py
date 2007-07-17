
def datetime_to_string(dt):
    return dt.strftime("@%s@")

def datetime_from_string(dt):
    assert dt.startswith("@")
    assert dt.endswith("@")
    return datetime.utcfromtimestamp(dt[1:-1])
