"""Enrich the catalog from Wikidata: ids of other services, Russian names, countries."""

import sqlite3

from filmtr.log import log
from filmtr.text import clean_ru_name, clean_ru_title
from filmtr.sources.wikidata import chunks, sparql, values

FILM_CHUNK = 250
PERSON_CHUNK = 400

# People whose Russian names are worth fetching: makers of any film, and the
# leading cast of catalog films.
PEOPLE_QUERY = """
SELECT DISTINCT person_id FROM credit
WHERE role IN ('director', 'writer', 'cinematographer', 'composer', 'editor', 'production_designer')
UNION
SELECT person_id FROM credit
WHERE role = 'actor' AND billing <= 6 AND film_id IN (SELECT film_id FROM list_entry)
UNION
SELECT person_id FROM list_entry WHERE person_id IS NOT NULL
"""


def _films(db: sqlite3.Connection, ids: list[str]) -> None:
    log(f"wikidata: {len(ids)} films")
    for n, chunk in enumerate(chunks(ids, FILM_CHUNK)):
        if n % 20 == 0:
            log(f"  films {n * FILM_CHUNK}/{len(ids)}")
        rows = sparql(f"""
            SELECT ?imdb ?item ?tmdb ?kp ?lb ?ru ?country ?iso ?cru ?cen WHERE {{
              VALUES ?imdb {{ {values(chunk)} }}
              ?item wdt:P345 ?imdb .
              OPTIONAL {{ ?item wdt:P4947 ?tmdb }}
              OPTIONAL {{ ?item wdt:P2603 ?kp }}
              OPTIONAL {{ ?item wdt:P6127 ?lb }}
              OPTIONAL {{ ?item rdfs:label ?ru FILTER(LANG(?ru) = "ru") }}
              OPTIONAL {{
                ?item wdt:P495 ?country .
                OPTIONAL {{ ?country wdt:P297 ?iso }}
                OPTIONAL {{ ?country rdfs:label ?cru FILTER(LANG(?cru) = "ru") }}
                OPTIONAL {{ ?country rdfs:label ?cen FILTER(LANG(?cen) = "en") }}
              }}
            }}""")
        seen = set()
        for r in rows:
            film = r["imdb"]
            if film not in seen:
                seen.add(film)
                db.execute(
                    "UPDATE film SET wikidata_id = ?, tmdb_id = ?, kinopoisk_id = ?, letterboxd_slug = ?, "
                    "title_ru = coalesce(?, title_ru) WHERE id = ?",
                    (r["item"], _int(r.get("tmdb")), _int(r.get("kp")), r.get("lb"), _clean(clean_ru_title, r.get("ru")), film))
            if "country" in r:
                cid = r.get("iso") or r["country"]
                db.execute("INSERT OR IGNORE INTO country VALUES (?, ?, ?)", (cid, r.get("cen"), r.get("cru")))
                db.execute("INSERT OR IGNORE INTO film_country VALUES (?, ?)", (film, cid))
        db.commit()


def _people(db: sqlite3.Connection, ids: list[str]) -> None:
    log(f"wikidata: {len(ids)} people")
    for n, chunk in enumerate(chunks(sorted(ids), PERSON_CHUNK)):
        if n % 20 == 0:
            log(f"  people {n * PERSON_CHUNK}/{len(ids)}")
        rows = sparql(f"""
            SELECT ?imdb ?item ?tmdb ?ru WHERE {{
              VALUES ?imdb {{ {values(chunk)} }}
              ?item wdt:P345 ?imdb .
              OPTIONAL {{ ?item wdt:P4985 ?tmdb }}
              OPTIONAL {{ ?item rdfs:label ?ru FILTER(LANG(?ru) = "ru") }}
            }}""")
        db.executemany(
            "UPDATE person SET wikidata_id = ?, tmdb_id = ?, name_ru = ? WHERE id = ?",
            ((r["item"], _int(r.get("tmdb")), _clean(clean_ru_name, r.get("ru")), r["imdb"]) for r in rows))
        db.commit()


def _clean(fn, v):
    return fn(v) if v else None


def _int(v):
    try:
        return int(v) if v else None
    except ValueError:
        return None


def wikidata(db: sqlite3.Connection, film_ids: set[str] | None = None) -> None:
    """Enrich all films (and notable people), or only the given films and their people."""
    if film_ids is None:
        _films(db, [r[0] for r in db.execute("SELECT id FROM film ORDER BY id")])
        _people(db, [r[0] for r in db.execute(PEOPLE_QUERY)])
    else:
        _films(db, sorted(film_ids))
        marks = ",".join("?" * len(film_ids))
        people = [r[0] for r in db.execute(
            f"SELECT DISTINCT person_id FROM credit WHERE film_id IN ({marks}) "
            f"AND (role <> 'actor' OR billing <= 6)", sorted(film_ids))]
        _people(db, people)
