"""Build data/filmtr.db from the IMDb staging db, lists and Wikidata."""

import csv
import datetime as dt
import json
import sqlite3

from filmtr import enrich, paths, personal
from filmtr.lists import LISTS, imdb_core
from filmtr.log import log
from filmtr.match import FilmMatcher, match_people
from filmtr.sources import imdb

# Kinds of titles shown in a person's filmography, and the vote floor for
# films that enter the catalog only through a filmography.
FILMOGRAPHY_KINDS = ("movie", "tvMovie", "tvMiniSeries", "short", "video", "tvSpecial")
FILMOGRAPHY_MIN_VOTES = 100

ROLE_BY_CATEGORY = {
    "actor": "actor", "actress": "actor", "self": "self", "director": "director",
    "writer": "writer", "producer": "producer", "composer": "composer",
    "cinematographer": "cinematographer", "editor": "editor",
    "production_designer": "production_designer", "casting_director": "casting_director",
}


def _load_overrides() -> list[dict]:
    """data/overrides/list_matches.csv: manual fixes for list entries.

    Columns: list_id, pos, source_title (title or name as in the source, to
    tell apart entries sharing a position), imdb_id (tt... or nm...), comment.
    """
    path = paths.OVERRIDES / "list_matches.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def collect_lists(staging: sqlite3.Connection) -> dict[str, list[dict]]:
    """Load every list and resolve its entries to IMDb ids."""
    entries: dict[str, list[dict]] = {}
    for spec in LISTS:
        log(f"list {spec.id}")
        entries[spec.id] = imdb_core(staging) if spec.id == "imdb-core-5000" else spec.load()

    known = lambda t: staging.execute("SELECT 1 FROM title WHERE tconst = ?", (t,)).fetchone()
    to_match = []
    for spec in LISTS:
        for e in entries[spec.id]:
            if spec.entity == "person":
                continue
            if "imdb" in e:
                ok = known(e["imdb"])
                e["film_id"], e["match"] = (e["imdb"], "id") if ok else (None, None)
            else:
                to_match.append(e)

    log(f"matching {len(to_match)} poll entries")
    FilmMatcher(staging).match(to_match)
    people = [e for s in LISTS if s.entity == "person" for e in entries[s.id]]
    listed = {e["film_id"] for es in entries.values() for e in es if e.get("film_id")}
    match_people(staging, people, listed)

    for o in _load_overrides():
        hits = [e for e in entries.get(o["list_id"], [])
                if e.get("pos") == int(o["pos"]) and (e.get("title") or e.get("name")) == o["source_title"]]
        if not hits:
            log(f"  override does not match any entry: {o}")
        for e in hits:
            key = "person_id" if o["imdb_id"].startswith("nm") else "film_id"
            e[key], e["match"] = o["imdb_id"], "override"
    return entries


def copy_films(db: sqlite3.Connection, film_ids: set[str], extra_people: set[str] = frozenset()) -> set[str]:
    """Copy films with their genres, ratings, credits and people from the
    staging db into the catalog; films already present are skipped.

    Returns the ids of the films actually added.
    """
    db.commit()  # ATTACH is not allowed inside a transaction
    db.execute(f"ATTACH DATABASE '{paths.IMDB_DB}' AS s")
    present = {r[0] for r in db.execute("SELECT id FROM film")}
    db.execute("DROP TABLE IF EXISTS temp.films")
    db.execute("CREATE TEMP TABLE films (id TEXT PRIMARY KEY)")
    db.executemany("INSERT OR IGNORE INTO films VALUES (?)", ((t,) for t in film_ids - present))
    added = {r[0] for r in db.execute("SELECT id FROM films WHERE id IN (SELECT tconst FROM s.title)")}

    db.execute("""
        INSERT INTO film (id, kind, title, original_title, year, end_year, runtime_min, title_ru)
        SELECT t.tconst, t.kind, t.primary_title, nullif(t.original_title, t.primary_title),
               t.year, t.end_year, t.runtime,
               -- Russian title from IMDb; Wikidata labels override it later.
               (SELECT a.title FROM s.aka a WHERE a.tconst = t.tconst AND a.region IN ('RU', 'SUHH')
                ORDER BY a.region = 'RU' DESC, a.rowid LIMIT 1)
        FROM s.title t WHERE t.tconst IN (SELECT id FROM films)""")
    db.execute("""
        INSERT INTO rating (film_id, source, value, scale, votes)
        SELECT tconst, 'imdb', rating, 10, votes FROM s.title
        WHERE tconst IN (SELECT id FROM films) AND rating IS NOT NULL""")
    genres = []
    for t, g in db.execute("SELECT tconst, genres FROM s.title WHERE tconst IN (SELECT id FROM films) "
                           "AND genres IS NOT NULL"):
        genres += [(t, x) for x in g.split(",")]
    db.executemany("INSERT INTO film_genre VALUES (?, ?)", genres)

    credits: dict[tuple[str, str, str], list] = {}
    for t, n, role, ord_ in db.execute(
            "SELECT tconst, nconst, role, ord FROM s.crew WHERE tconst IN (SELECT id FROM films)"):
        credits[(t, n, role)] = [100 + ord_, None, None]
    for t, ord_, n, category, job, characters in db.execute(
            "SELECT tconst, ord, nconst, category, job, characters FROM s.principal "
            "WHERE tconst IN (SELECT id FROM films)"):
        role = ROLE_BY_CATEGORY.get(category)
        if role is None:
            continue
        if characters:
            try:
                characters = "; ".join(json.loads(characters))
            except ValueError:
                pass
        c = credits.setdefault((t, n, role), [ord_, None, None])
        c[0] = min(c[0], ord_)
        c[1] = c[1] or job
        c[2] = c[2] or characters
    people = {n for _, n, _ in credits} | set(extra_people)
    db.execute("DROP TABLE IF EXISTS temp.people")
    db.execute("CREATE TEMP TABLE people (id TEXT PRIMARY KEY)")
    db.executemany("INSERT OR IGNORE INTO people VALUES (?)", ((p,) for p in people))
    db.execute("""
        INSERT OR IGNORE INTO person (id, name, birth_year, death_year)
        SELECT nconst, name, birth_year, death_year FROM s.name WHERE nconst IN (SELECT id FROM people)""")
    # IMDb credits occasionally point to people missing from name.basics.
    known = {r[0] for r in db.execute("SELECT id FROM person WHERE id IN (SELECT id FROM people)")}
    db.executemany(
        "INSERT INTO credit VALUES (?, ?, ?, ?, ?, ?)",
        ((t, n, role, *v) for (t, n, role), v in credits.items() if n in known))
    db.commit()
    db.execute("DETACH DATABASE s")
    return added


def ensure_films(db: sqlite3.Connection, film_ids: set[str]) -> set[str]:
    """Add films missing from the catalog, enriched from Wikidata."""
    added = copy_films(db, film_ids)
    if added:
        log(f"adding {len(added)} films to the catalog")
        enrich.wikidata(db, film_ids=added)
    return added


def build() -> None:
    staging = imdb.connect()
    entries = collect_lists(staging)

    tmp = paths.CATALOG_DB.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(paths.SCHEMA.read_text())

    # Films: everything listed, plus filmographies of their directors and of
    # listed people.
    listed = {e["film_id"] for es in entries.values() for e in es if e.get("film_id")}
    listed_people = {e["person_id"] for es in entries.values() for e in es if e.get("person_id")}
    makers = set(listed_people)
    kinds = ",".join(f"'{k}'" for k in FILMOGRAPHY_KINDS)
    staging.execute("CREATE TEMP TABLE listed (id TEXT PRIMARY KEY)")
    staging.executemany("INSERT OR IGNORE INTO listed VALUES (?)", ((t,) for t in listed))
    makers |= {r[0] for r in staging.execute(
        "SELECT nconst FROM crew WHERE role = 'director' AND tconst IN (SELECT id FROM listed)")}
    staging.execute("CREATE TEMP TABLE makers (id TEXT PRIMARY KEY)")
    staging.executemany("INSERT OR IGNORE INTO makers VALUES (?)", ((p,) for p in makers))
    filmography = {r[0] for r in staging.execute(f"""
        SELECT c.tconst FROM crew c JOIN title t USING (tconst)
        WHERE c.role = 'director' AND c.nconst IN (SELECT id FROM makers)
          AND t.kind IN ({kinds}) AND t.votes >= {FILMOGRAPHY_MIN_VOTES} AND t.is_adult = 0""")}
    films = listed | filmography
    log(f"films: {len(listed)} listed, {len(films)} with filmographies")
    log("copying films and credits")
    copy_films(db, films, listed_people)

    log("lists")
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for spec in LISTS:
        db.execute("INSERT INTO list (id, title, title_ru, kind, entity, source, url, edition, "
                   "description, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (spec.id, spec.title, spec.title_ru, spec.kind, spec.entity, spec.source,
                    spec.url, spec.edition or (imdb.snapshot_date() if spec.kind == "computed" else None),
                    spec.description, now))
        for e in entries[spec.id]:
            raw = {k: v for k, v in e.items() if k not in ("film_id", "person_id", "match")}
            db.execute(
                "INSERT INTO list_entry (list_id, pos, year, film_id, person_id, match, raw) "
                "VALUES (?,?,?,?,?,?,?)",
                (spec.id, e.get("pos"), e["year"] if spec.kind == "award" else None,
                 e.get("film_id"), e.get("person_id"), e.get("match"),
                 json.dumps(raw, ensure_ascii=False)))
    db.commit()

    enrich.wikidata(db)
    personal.sync(db)
    db.execute("ANALYZE")
    db.commit()
    db.close()
    tmp.replace(paths.CATALOG_DB)
    log(f"catalog written to {paths.CATALOG_DB}")
