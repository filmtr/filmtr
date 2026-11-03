"""HTTP with an on-disk cache, so that rebuilding is fast and polite."""

import gzip
import hashlib
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from filmtr import paths
from filmtr.log import log

USER_AGENT = "filmtr/0.1 (personal non-commercial film catalog)"


def fetch(url: str, *, data: dict | None = None, headers: dict | None = None,
          cache: bool = True, ext: str = "html", compress: bool = False) -> str:
    """GET (or POST with `data`) a URL as text, cached on disk by URL and body.

    Raises urllib.error.HTTPError for non-retriable errors such as 404.
    """
    body = urllib.parse.urlencode(data).encode() if data else None
    key = hashlib.sha1(url.encode() + (body or b"")).hexdigest()
    path = paths.CACHE / f"{key}.{ext}" if not compress else paths.CACHE / f"{key}.{ext}.gz"
    if cache and path.exists():
        if compress:
            return gzip.decompress(path.read_bytes()).decode("utf-8")
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
            log(f"  {url.split('?')[0][:80]}: {e}; retrying in {wait}s")  # no query: may hold keys
            time.sleep(wait)
    else:
        raise RuntimeError(f"giving up on {url}")

    if cache:
        paths.CACHE.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".{threading.get_ident()}.tmp")
        if compress:
            tmp.write_bytes(gzip.compress(text.encode("utf-8")))
        else:
            tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)  # atomic: safe with concurrent fetches
    return text
