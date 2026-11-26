"""Write complete JSON snapshots atomically, preserving the previous file on failure."""

import json
import os
import tempfile
from pathlib import Path


def write_json(path, data, *, if_changed=False):
    path = Path(path)
    body = (json.dumps(data, separators=(",", ":"), allow_nan=False) + "\n").encode()
    if if_changed:
        try:
            if path.read_bytes() == body:
                return body
        except FileNotFoundError:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(body)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return body
