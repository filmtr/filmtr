import sys
import time

_start = time.monotonic()


def log(msg: str) -> None:
    print(f"[{time.monotonic() - _start:7.1f}s] {msg}", file=sys.stderr, flush=True)
