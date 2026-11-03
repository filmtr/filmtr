"""Enrich films from TMDB: overviews, posters, keywords, full cast and crew.

Called for listed films at build time and for any other film on demand
(enrich(db, ids)). API responses are cached on disk, so rebuilding the
catalog does not hit TMDB again.
"""

import sqlite3

from filmtr import enrich as wikidata
from filmtr.log import log
from filmtr.sources import tmdb

CAST_LIMIT = 20

# TMDB crew job -> (our role, job detail kept in credit.job)
JOB_ROLE = {
    "Director": ("director", None),
    "Co-Director": ("director", "co-director"),
    "Screenplay": ("writer", "screenplay"),
    "Writer": ("writer", None),
    "Story": ("writer", "story"),
    "Novel": ("writer", "novel"),
    "Author": ("writer", "author"),
    "Teleplay": ("writer", "teleplay"),
    "Original Story": ("writer", "story"),
    "Director of Photography": ("cinematographer", None),
    "Original Music Composer": ("composer", None),
    "Music": ("composer", None),
    "Editor": ("editor", None),
    "Production Design": ("production_designer", None),
    "Costume Design": ("costume_designer", None),
    "Producer": ("producer", None),
    "Casting": ("casting_director", None),
}


def _resolve(film_id: str, kind: str, tmdb_id: int | None) -> tuple[str, int] | None:
    """(tmdb type, tmdb id) for an IMDb title."""
    series = kind in ("tvSeries", "tvMiniSeries")
    if tmdb_id and not series:
        return "movie", tmdb_id
    found = tmdb.get(f"/find/{film_id}", external_source="imdb_id") or {}
    movies, tv = found.get("movie_results") or [], found.get("tv_results") or []
    order = [("tv", tv), ("movie", movies)] if series else [("movie", movies), ("tv", tv)]
    for t, results in order:
        if results:
            return t, results[0]["id"]
    return None


def _details(t: str, tid: int) -> dict | None:
    extra = "credits,keywords,translations" if t == "movie" else "aggregate_credits,keywords,translations"
    return tmdb.get(f"/{t}/{tid}", append_to_response=extra)


def _fetch(item: tuple[str, str, int | None]) -> dict | None:
    film_id, kind, tmdb_id = item
    target = _resolve(film_id, kind, tmdb_id)
    data = _details(*target) if target else None
    if data is None and tmdb_id:  # stale id from Wikidata: look up by IMDb id
        target = _resolve(film_id, kind, None)
        data = _details(*target) if target else None
    return _parse(film_id, target[0], data) if data else None


def _parse(film_id: str, t: str, d: dict) -> dict:
    ru = next((x["data"] for x in d.get("translations", {}).get("translations", [])
               if x["iso_639_1"] == "ru"), {})
    kw = d.get("keywords", {})
    out = {
        "film_id": film_id, "type": t, "tmdb_id": d["id"],
        "overview_en": d.get("overview") or None, "overview_ru": ru.get("overview") or None,
        "tagline_en": d.get("tagline") or None, "tagline_ru": ru.get("tagline") or None,
        "title_ru": ru.get("title") or ru.get("name") or None,
        "original_language": d.get("original_language"),
        "poster_path": d.get("poster_path"), "backdrop_path": d.get("backdrop_path"),
        "vote_average": d.get("vote_average"), "vote_count": d.get("vote_count"),
        "keywords": [(k["id"], k["name"]) for k in kw.get("keywords", kw.get("results", []))],
        "people": {},   # tmdb person id -> (name, profile_path)
        "credits": [],  # (tmdb person id, role, billing, job, characters)
    }
    if t == "movie":
        credits = d.get("credits", {})
        cast = [(c["id"], c.get("character"), c["order"]) for c in credits.get("cast", [])]
        crew = [(c["id"], c["job"]) for c in credits.get("crew", [])]
    else:
        credits = d.get("aggregate_credits", {})
        cast = [(c["id"], "; ".join(r["character"] for r in c.get("roles", []) if r.get("character")),
                 c["order"]) for c in credits.get("cast", [])]
        crew = [(c["id"], j["job"]) for c in credits.get("crew", []) for j in c.get("jobs", [])]
        for c in d.get("created_by", []):
            crew.append((c["id"], "Writer"))
            out["people"][c["id"]] = (c["name"], c.get("profile_path"))
    for c in credits.get("cast", []) + credits.get("crew", []):
        out["people"][c["id"]] = (c["name"], c.get("profile_path"))
    for pid, character, order in sorted(cast, key=lambda c: c[2])[:CAST_LIMIT]:
        out["credits"].append((pid, "actor", order + 1, None, character or None))
    for pid, job in crew:
        if job in JOB_ROLE:
            role, detail = JOB_ROLE[job]
            out["credits"].append((pid, role, None, detail, None))
    return out


def _imdb_person(tmdb_person: int) -> str | None:
    ids = tmdb.get(f"/person/{tmdb_person}/external_ids") or {}
    imdb_id = ids.get("imdb_id")
    return imdb_id if imdb_id and imdb_id.startswith("nm") else None


def enrich(db: sqlite3.Connection, film_ids, refresh: bool = False) -> None:
    """Load TMDB data for these films (skipping ones already loaded)."""
    if not tmdb.available():
        log("tmdb: no credentials, skipped (see filmtr/sources/tmdb.py)")
        return
    film_ids = sorted(film_ids)
    if not film_ids:
        return
    marks = ",".join("?" * len(film_ids))
    done = "" if refresh else "AND tmdb_status IS NULL"
    todo = db.execute(f"SELECT id, kind, tmdb_id FROM film WHERE id IN ({marks}) {done}", film_ids).fetchall()
    if todo:
        _load(db, todo)

    posters = [p for (p,) in db.execute(
        f"SELECT poster_path FROM film WHERE id IN ({marks}) AND poster_path IS NOT NULL", film_ids)]
    missing = [p for p in posters if not tmdb.poster_file(p).exists()]
    if missing:
        log(f"tmdb: downloading {len(missing)} posters")
        failed = sum(1 for r in tmdb.parallel(tmdb.download_poster, missing) if r is None)
        if failed:
            log(f"tmdb: {failed} posters failed to download, will retry on the next run")


def _load(db: sqlite3.Connection, todo: list[tuple]) -> None:
    log(f"tmdb: {len(todo)} films")
    results = tmdb.parallel(_fetch, todo)

    # Map TMDB people to IMDb ids: Wikidata first, then TMDB external ids.
    by_tmdb = {t: p for p, t in db.execute("SELECT id, tmdb_id FROM person WHERE tmdb_id IS NOT NULL")}
    wanted = {pid for r in results if r for pid, *_ in r["credits"]} - by_tmdb.keys()
    log(f"tmdb: resolving {len(wanted)} people")
    for pid, imdb_id in zip(wanted, tmdb.parallel(_imdb_person, list(wanted))):
        if imdb_id:
            by_tmdb[pid] = imdb_id

    known = {r[0] for r in db.execute("SELECT id FROM person")}
    new_people = set()
    for (film_id, _, _), r in zip(todo, results):
        if r is None:
            db.execute("UPDATE film SET tmdb_status = 'missing' WHERE id = ?", (film_id,))
            continue
        db.execute("""
            UPDATE film SET tmdb_type = ?, tmdb_id = ?, tmdb_status = 'ok',
                   overview_ru = ?, overview_en = ?, tagline_ru = ?, tagline_en = ?,
                   original_language = ?, poster_path = ?, backdrop_path = ?,
                   title_ru = coalesce(title_ru, ?)
            WHERE id = ?""",
            (r["type"], r["tmdb_id"], r["overview_ru"], r["overview_en"], r["tagline_ru"], r["tagline_en"],
             r["original_language"], r["poster_path"], r["backdrop_path"], r["title_ru"], film_id))
        if r["vote_count"]:
            db.execute("INSERT OR REPLACE INTO rating (film_id, source, value, scale, votes) "
                       "VALUES (?, 'tmdb', ?, 10, ?)", (film_id, r["vote_average"], r["vote_count"]))
        db.executemany("INSERT OR IGNORE INTO keyword VALUES (?, ?)", r["keywords"])
        db.executemany("INSERT OR IGNORE INTO film_keyword VALUES (?, ?)",
                       ((film_id, k) for k, _ in r["keywords"]))

        as_self = {p for (p,) in db.execute(
            "SELECT person_id FROM credit WHERE film_id = ? AND role = 'self'", (film_id,))}
        for pid, role, billing, job, characters in r["credits"]:
            person = by_tmdb.get(pid)
            if person is None:
                continue  # no IMDb id: rare, skipped
            if role == "actor" and person in as_self:
                continue  # documentaries: IMDb already has them as themselves
            name, photo = r["people"][pid]
            if person not in known:
                db.execute("INSERT INTO person (id, name, tmdb_id, photo_path) VALUES (?, ?, ?, ?)",
                           (person, name, pid, photo))
                known.add(person)
                new_people.add(person)
            else:
                db.execute("UPDATE person SET tmdb_id = coalesce(tmdb_id, ?), "
                           "photo_path = coalesce(photo_path, ?) WHERE id = ?", (pid, photo, person))
            db.execute("INSERT OR IGNORE INTO credit VALUES (?, ?, ?, ?, ?, ?)",
                       (film_id, person, role, billing, job, characters))
            # TMDB cast order is the billing order; keep IMDb details where present.
            db.execute("UPDATE credit SET billing = coalesce(?, billing), job = coalesce(job, ?), "
                       "characters = coalesce(characters, ?) "
                       "WHERE film_id = ? AND person_id = ? AND role = ?",
                       (billing, job, characters, film_id, person, role))
    db.commit()

    if new_people:
        wikidata.people(db, sorted(new_people))  # Russian names from Wikidata
