"""Catalog statistics and data-quality report."""

import json
import sqlite3

from filmtr import paths


def show() -> None:
    if not paths.CATALOG_DB.exists():
        raise SystemExit("no catalog yet: run `filmtr build`")
    db = sqlite3.connect(paths.CATALOG_DB)
    q = lambda sql: db.execute(sql).fetchone()[0]

    print("Catalog")
    print(f"  films worth attention:     {q('SELECT count(*) FROM catalog')}")
    print(f"  films incl. filmographies: {q('SELECT count(*) FROM film')}")
    print(f"  people:                    {q('SELECT count(*) FROM person')}")
    print(f"  credits:                   {q('SELECT count(*) FROM credit')}")

    print("\nCoverage of catalog films")
    for label, cond in [("Russian title", "title_ru IS NOT NULL"), ("Wikidata", "wikidata_id IS NOT NULL"),
                        ("TMDB id", "tmdb_id IS NOT NULL"), ("Kinopoisk id", "kinopoisk_id IS NOT NULL"),
                        ("Letterboxd", "letterboxd_slug IS NOT NULL"),
                        ("country", "id IN (SELECT film_id FROM film_country)"),
                        ("TMDB data", "tmdb_status = 'ok'"), ("overview (ru)", "overview_ru IS NOT NULL"),
                        ("poster", "poster_path IS NOT NULL"),
                        ("keywords", "id IN (SELECT film_id FROM film_keyword)"),
                        ("composer", "id IN (SELECT film_id FROM credit WHERE role = 'composer')"),
                        ("prod. design", "id IN (SELECT film_id FROM credit WHERE role = 'production_designer')")]:
        n = q(f"SELECT count(*) FROM catalog WHERE {cond}")
        total = q("SELECT count(*) FROM catalog")
        print(f"  {label:<14} {n:>6} ({100 * n / total:.0f}%)")
    n = q("SELECT count(DISTINCT person_id) FROM credit WHERE role = 'director' AND person_id IN "
          "(SELECT id FROM person WHERE name_ru IS NOT NULL)")
    total = q("SELECT count(DISTINCT person_id) FROM credit WHERE role = 'director'")
    print(f"  directors with Russian name: {n}/{total}")

    print("\nLists (entries / matched / fuzzy / unmatched)")
    for lid, total, matched, fuzzy in db.execute(
            "SELECT list_id, count(*), count(match), count(*) FILTER (WHERE match = 'fuzzy') "
            "FROM list_entry GROUP BY list_id ORDER BY list_id"):
        print(f"  {lid:<32} {total:>5} {matched:>5} {fuzzy:>5} {total - matched:>5}")

    unmatched = db.execute("SELECT list_id, pos, raw FROM list_entry WHERE match IS NULL "
                           "ORDER BY list_id, pos").fetchall()
    if unmatched:
        print("\nUnmatched entries (fix in data/overrides/list_matches.csv)")
        for lid, pos, raw in unmatched:
            r = json.loads(raw)
            print(f"  {lid} #{pos}: {r.get('title') or r.get('name')} ({r.get('year', '')}) {r.get('director', '')}")
