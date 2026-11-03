"""TMDB API client. Free for non-commercial use with attribution:
"This product uses the TMDB API but is not endorsed or certified by TMDB."

Credentials, in order of preference (never stored in the repository):
- read access token: $TMDB_TOKEN or ~/.tmdb-api-read-access-token (sent in a header)
- API key (v3):      $TMDB_API_KEY or ~/.tmdb-api-key (sent in the URL)
"""

import http.client
import json
import os
import threading
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from filmtr import paths
from filmtr.http import USER_AGENT, fetch

API = "https://api.themoviedb.org/3"
IMAGES = "https://image.tmdb.org/t/p"
POSTER_SIZE = "w342"
WORKERS = 8  # TMDB allows roughly 50 requests per second


def _secret(env: str, file: str) -> str | None:
    if os.environ.get(env):
        return os.environ[env].strip()
    p = Path.home() / file
    return p.read_text().strip() if p.exists() else None


def _auth() -> tuple[dict, dict] | None:
    """(headers, query params) for authentication, or None without credentials."""
    token = _secret("TMDB_TOKEN", ".tmdb-api-read-access-token")
    if token and len(token) > 40:  # a real token is a long JWT, not the 32-char key
        return {"Authorization": f"Bearer {token}"}, {}
    key = _secret("TMDB_API_KEY", ".tmdb-api-key")
    if key:
        return {}, {"api_key": key}
    return None


def available() -> bool:
    return _auth() is not None


def get(path: str, **params) -> dict | None:
    """GET an API path; None if TMDB has no such object (404)."""
    auth = _auth()
    if auth is None:
        raise RuntimeError("no TMDB credentials, see filmtr/sources/tmdb.py")
    headers, auth_params = auth
    query = urllib.parse.urlencode({**params, **auth_params})
    url = f"{API}{path}" + (f"?{query}" if query else "")
    try:
        return json.loads(fetch(url, headers=headers, ext="json", compress=True))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def parallel(fn, items):
    """Map fn over items with a small thread pool, preserving order."""
    with ThreadPoolExecutor(WORKERS) as pool:
        return list(pool.map(fn, items))


def poster_file(poster_path: str, size: str = POSTER_SIZE) -> Path:
    return paths.POSTERS / size / poster_path.lstrip("/")


_local = threading.local()


def _image_conn() -> http.client.HTTPSConnection:
    """One keep-alive connection to the image CDN per thread: a new connection
    (DNS lookup + TLS) per poster is slow and can stall on DNS."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _local.conn = http.client.HTTPSConnection(urllib.parse.urlsplit(IMAGES).netloc, timeout=30)
    return conn


def download_poster(poster_path: str, size: str = POSTER_SIZE) -> Path | None:
    """Download a poster once; images need no authentication.

    Returns None on failure: a missing poster must not break a build, it is
    retried on the next run."""
    target = poster_file(poster_path, size)
    if target.exists():
        return target
    path = f"{urllib.parse.urlsplit(IMAGES).path}/{size}{poster_path}"
    for _ in range(3):
        conn = _image_conn()
        try:
            conn.request("GET", path, headers={"User-Agent": USER_AGENT})
            resp = conn.getresponse()
            data = resp.read()
        except (OSError, http.client.HTTPException):
            conn.close()
            _local.conn = None
            continue
        if resp.status == 404:
            return None
        if resp.status != 200:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + f".{threading.get_ident()}.tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
        return target
    return None
