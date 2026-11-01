"""HTTP with an on-disk cache, so that rebuilding is fast and polite."""

import hashlib
import time
import urllib.error
import urllib.parse
import urllib.request

from filmtr import paths
from filmtr.log import log

USER_AGENT = "filmtr/0.1 (personal non-commercial film catalog)"


def fetch(url: str, *, data: dict | None = None, headers: dict | None = None,
          cache: bool = True, ext: str = "html") -> str:
    body = urllib.parse.urlencode(data).encode() if data else None
    key = hashlib.sha1(url.encode() + (body or b"")).hexdigest()
    path = paths.CACHE / f"{key}.{ext}"
    if cache and path.exists():
        return path.read_text(encoding="utf-8")

    req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT, **(headers or {})})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                text = resp.read().decode("utf-8")
            break
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            code = getattr(e, "code", None)
            if code is not None and code not in (429, 500, 502, 503, 504):
                raise
            wait = 2 ** (attempt + 1)
            log(f"  {url[:60]}: {e}; retrying in {wait}s")
            time.sleep(wait)
    else:
        raise RuntimeError(f"giving up on {url}")

    if cache:
        paths.CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return text
