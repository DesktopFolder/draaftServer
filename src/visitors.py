from fastapi import Request
import json
import xxhash
from threading import Lock

def load_visitors(data: dict) -> dict[str, set[int]]:
    return { k: set(v) for k, v in data.items() }

def dump_visitors(data: dict):
    import json
    return json.dumps({ k: list(v) for k, v in data.items() })

try:
    with open(".visitors.json") as file:
        VISITORS = load_visitors(json.load(file))
except FileNotFoundError:
    VISITORS: dict[str, set[int]] = dict()

_file_mutex = Lock()

def increment(request: Request, kind: str):
    user_ip = request.headers.get('cf-connecting-ip')
    if user_ip is None:
        return

    if kind not in VISITORS:
        VISITORS[kind] = set()
    kind_visitors: set[int] = VISITORS[kind]

    hsh = xxhash.xxh64_intdigest(user_ip)
    if hsh not in kind_visitors:
        kind_visitors.add(hsh)
        to_write = dump_visitors(VISITORS)
        with _file_mutex:
            with open(".visitors.json", "w") as file:
                file.write(to_write)
