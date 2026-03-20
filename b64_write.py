import base64
def write_file(path, b64_str):
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64_str.encode('utf-8')))
