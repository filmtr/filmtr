"""IMDb non-commercial datasets: download and stage into data/imdb.db.

The staging database is a trimmed mirror of IMDb, used for selecting and
matching films. It keeps all non-episode titles, and for titles with enough
votes also their credits and alternative titles.

Terms: https://developer.imdb.com/non-commercial-datasets/ (personal,
non-commercial use).
"""

import datetime as dt
import gzip
import sqlite3
import urllib.request
from filmtr import paths
from filmtr.log import log

BASE_URL = "https://datasets.imdbws.com/"
FILES = [
    "title.basics",
    "title.ratings",
    "title.crew",
    "title.principals",
    "title.akas",
    "name.basics",
]

# Title types worth keeping. Episodes, games and pilots are skipped.
KINDS = {"movie", "tvMovie", "short", "tvMiniSeries", "tvSeries", "tvSpecial", "video"}
MIN_VOTES_AKAS = 50
MIN_VOTES_PRINCIPALS = 100

SCHEMA = """
CREATE TABLE title (
    tconst TEXT PRIMARY KEY, kind TEXT, primary_title TEXT, original_title TEXT,
    is_adult INTEGER, year INTEGER, end_year INTEGER, runtime INTEGER,
    genres TEXT, rating REAL, votes INTEGER
);
CREATE TABLE crew (tconst TEXT, nconst TEXT, role TEXT, ord INTEGER);
CREATE TABLE principal (
    tconst TEXT, ord INTEGER, nconst TEXT, category TEXT, job TEXT, characters TEXT
);
CREATE TABLE aka (
    tconst TEXT, title TEXT, region TEXT, language TEXT, is_original INTEGER
);
CREATE TABLE name (
    nconst TEXT PRIMARY KEY, name TEXT, birth_year INTEGER, death_year INTEGER,
    professions TEXT
);
"""

INDEXES = """
CREATE INDEX title_year ON title(year);
CREATE INDEX title_votes ON title(votes);
CREATE INDEX crew_tconst ON crew(tconst);
CREATE INDEX crew_nconst ON crew(nconst, role);
CREATE INDEX principal_tconst ON principal(tconst);
CREATE INDEX aka_tconst ON aka(tconst);
"""


def download(refresh: bool = False) -> None:
    paths.IMDB_RAW.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = paths.IMDB_RAW / f"{name}.tsv.gz"
        if target.exists() and not refresh:
            continue
        log(f"downloading {name}")
        part = target.with_suffix(".part")
        urllib.request.urlretrieve(BASE_URL + target.name, part)
        part.rename(target)


def _rows(name: str):
    """Yield split rows of an IMDb TSV file, skipping the header.

    IMDb files are not CSV-quoted, so a plain split on tabs is correct.
    """
    with gzip.open(paths.IMDB_RAW / f"{name}.tsv.gz", "rt", encoding="utf-8") as f:
        next(f)
        for line in f:
            yield line.rstrip("\n").split("\t")


def _null(v: str):
    return None if v == "\\N" else v


def _int(v: str):
    return None if v == "\\N" else int(v)


def stage() -> None:
    download()
    db_path = paths.IMDB_DB
    tmp = db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA)

    log("ratings")
    ratings = {r[0]: (float(r[1]), int(r[2])) for r in _rows("title.ratings")}

    log("titles")
    votes: dict[str, int] = {}

    def titles():
        for t, kind, primary, original, adult, start, end, runtime, genres in _rows("title.basics"):
            if kind not in KINDS:
                continue
            rating, n = ratings.get(t, (None, 0))
            votes[t] = n
            yield (t, kind, primary, original, int(adult), _int(start), _int(end),
                   _int(runtime), _null(genres), rating, n)

    db.executemany("INSERT INTO title VALUES (?,?,?,?,?,?,?,?,?,?,?)", titles())
    del ratings

    people: set[str] = set()

    log("crew")

    def crew():
        for t, directors, writers in _rows("title.crew"):
            if t not in votes:
                continue
            for role, field in (("director", directors), ("writer", writers)):
                if field == "\\N":
                    continue
                for i, n in enumerate(field.split(",")):
                    people.add(n)
                    yield t, n, role, i

    db.executemany("INSERT INTO crew VALUES (?,?,?,?)", crew())

    log("principals")

    def principals():
        for t, ordering, n, category, job, characters in _rows("title.principals"):
            if votes.get(t, 0) < MIN_VOTES_PRINCIPALS:
                continue
            people.add(n)
            yield t, int(ordering), n, category, _null(job), _null(characters)

    db.executemany("INSERT INTO principal VALUES (?,?,?,?,?,?)", principals())

    log("akas")

    def akas():
        for t, _ordering, title, region, language, _types, _attrs, is_original in _rows("title.akas"):
            if votes.get(t, 0) < MIN_VOTES_AKAS:
                continue
            yield t, title, _null(region), _null(language), is_original == "1"

    db.executemany("INSERT INTO aka VALUES (?,?,?,?,?)", akas())

    log("names")

    def names():
        for n, name, birth, death, professions, _known in _rows("name.basics"):
            if n in people:
                yield n, name, _int(birth), _int(death), _null(professions)

    db.executemany("INSERT INTO name VALUES (?,?,?,?,?)", names())

    log("indexes")
    db.executescript(INDEXES)
    build_search_index(db)
    db.commit()
    db.close()
    tmp.replace(db_path)
    log(f"staged into {db_path}")


# Full-text index over primary, original and alternative titles. unicode61
# folds case for all scripts and strips diacritics, so "амели" finds "Амели"
# and "amelie" finds "Amélie".
SEARCH_MIN_VOTES = 5
SEARCH_INDEX_VERSION = 2  # bump to rebuild the index on next use


def build_search_index(db: sqlite3.Connection) -> None:
    log("search index")
    db.executescript("""
        DROP TABLE IF EXISTS title_search;
        CREATE VIRTUAL TABLE title_search USING fts5(
            tconst UNINDEXED, text, tokenize = 'unicode61 remove_diacritics 2');
    """)
    # unicode61 does not fold Cyrillic ё to е; do it on both sides (see search.py).
    db.execute("""
        INSERT INTO title_search (tconst, text)
        SELECT tconst, replace(replace(text, 'ё', 'е'), 'Ё', 'Е') FROM (
            SELECT tconst, primary_title AS text FROM title WHERE votes >= ?
            UNION
            SELECT tconst, original_title FROM title WHERE votes >= ? AND original_title <> primary_title
            UNION
            SELECT tconst, title FROM aka)""", (SEARCH_MIN_VOTES, SEARCH_MIN_VOTES))
    db.execute(f"PRAGMA user_version = {SEARCH_INDEX_VERSION}")
    db.commit()


def connect() -> sqlite3.Connection:
    if not paths.IMDB_DB.exists():
        stage()
    db = sqlite3.connect(paths.IMDB_DB)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'title_search'").fetchone() \
            or db.execute("PRAGMA user_version").fetchone()[0] < SEARCH_INDEX_VERSION:
        build_search_index(db)
    return db


def snapshot_date() -> str:
    """Date of the downloaded IMDb snapshot."""
    mtime = (paths.IMDB_RAW / "title.basics.tsv.gz").stat().st_mtime
    return dt.date.fromtimestamp(mtime).isoformat()
