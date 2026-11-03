"""Export the catalog as static JSON for the web UI (web/), and sync personal
lists between my/*.csv and the web app's D1 database.

Static data (written to web/public/data/, not committed: it is derived from
IMDb data, licensed for personal use only):

    films.json        every film in the catalog db, compact, for lists and search
    lists.json        lists (polls, awards, computed) and person-list entries
    meta.json         genres, countries, roles: id -> Russian name
    film/NN.json      film details, sharded by the last two digits of the IMDb id
    person/NN.json    people with their credits, sharded the same way

Personal lists live in D1 while the web app is in use; `pull` writes them back
to my/*.csv so that git keeps their history.
"""

import csv
import json
import shutil
import sqlite3
import subprocess
from collections import defaultdict

from filmtr import paths, personal
from filmtr.log import log

WEB = paths.ROOT / "web"
OUT = WEB / "public" / "data"
D1_NAME = "filmtr"


def _shard(id_: str) -> str:
    return id_[-2:]


def _dump(path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    return len(text.encode())


def export() -> None:
    db = sqlite3.connect(paths.CATALOG_DB)
    db.row_factory = sqlite3.Row
    if OUT.exists():
        shutil.rmtree(OUT)

    # Personal lists are served from D1, not from the static catalog.
    catalog = {r[0] for r in db.execute(
        "SELECT DISTINCT e.film_id FROM list_entry e JOIN list l ON l.id = e.list_id "
        "WHERE l.kind <> 'personal' AND e.film_id IS NOT NULL")}

    genres = defaultdict(list)
    for f, g in db.execute("SELECT film_id, genre FROM film_genre"):
        genres[f].append(g)
    countries = defaultdict(list)
    for f, c in db.execute("SELECT film_id, country FROM film_country"):
        countries[f].append(c)
    directors = defaultdict(list)
    for f, n in db.execute(
            "SELECT c.film_id, coalesce(p.name_ru, p.name) FROM credit c JOIN person p ON p.id = c.person_id "
            "WHERE c.role = 'director' ORDER BY c.film_id, c.billing"):
        directors[f].append(n)
    ratings = {(f, s): (v, n) for f, s, v, n in db.execute("SELECT film_id, source, value, votes FROM rating")}
    entries = defaultdict(list)
    for lid, pos, year, f in db.execute(
            "SELECT e.list_id, e.pos, e.year, e.film_id FROM list_entry e JOIN list l ON l.id = e.list_id "
            "WHERE l.kind <> 'personal' AND e.film_id IS NOT NULL ORDER BY e.list_id, e.pos"):
        entries[f].append([lid, pos, year])

    # films.json: compact rows; keys are short to keep the file small.
    films = []
    for r in db.execute("SELECT * FROM film ORDER BY id"):
        f = r["id"]
        row = {"i": f, "t": r["title_ru"] or r["title"], "y": r["year"]}
        if (r["title_ru"] or r["title"]) != r["title"]:
            row["o"] = r["title"]
        if r["kind"] != "movie":
            row["k"] = r["kind"]
        if r["poster_path"]:
            row["p"] = r["poster_path"]
        if directors[f]:
            row["d"] = directors[f]
        if f in catalog:
            row["c"] = 1
            row["g"] = genres[f]
            row["n"] = countries[f]
            if r["runtime_min"]:
                row["m"] = r["runtime_min"]
            if (f, "imdb") in ratings:
                row["r"], row["v"] = ratings[(f, "imdb")]
            row["l"] = [e[0] for e in entries[f]]
        films.append(row)
    size = _dump(OUT / "films.json", films)
    log(f"films.json: {len(films)} films, {size / 1e6:.1f} MB")

    # lists.json
    lists = []
    for r in db.execute("SELECT * FROM list WHERE kind <> 'personal' ORDER BY kind, id"):
        item = {k: r[k] for k in ("id", "title", "title_ru", "kind", "entity", "url", "edition", "description")}
        if r["entity"] == "person":
            item["people"] = [[pos, p, n] for pos, p, n in db.execute(
                "SELECT e.pos, e.person_id, coalesce(p.name_ru, p.name) FROM list_entry e "
                "JOIN person p ON p.id = e.person_id WHERE e.list_id = ? ORDER BY e.pos", (r["id"],))]
        lists.append(item)
    _dump(OUT / "lists.json", lists)

    meta = {
        "genres": dict(db.execute("SELECT id, name_ru FROM genre")),
        "countries": {i: ru or en for i, en, ru in db.execute("SELECT id, name_en, name_ru FROM country")},
        "roles": {i: [ru, s] for i, ru, s in db.execute("SELECT id, name_ru, sort FROM role")},
    }
    _dump(OUT / "meta.json", meta)

    # film/NN.json
    credits_by_film = defaultdict(list)
    credits_by_person = defaultdict(list)
    for f, p, role, billing, job, chars, name in db.execute(
            "SELECT c.film_id, c.person_id, c.role, c.billing, c.job, c.characters, coalesce(p.name_ru, p.name) "
            "FROM credit c JOIN person p ON p.id = c.person_id ORDER BY c.film_id, c.role, c.billing"):
        credits_by_film[f].append([p, name, role, job or chars])
        credits_by_person[p].append([f, role, job or chars])
    shards = defaultdict(dict)
    for r in db.execute("SELECT * FROM film"):
        f = r["id"]
        shards[_shard(f)][f] = {
            "title": r["title"], "title_ru": r["title_ru"], "original_title": r["original_title"],
            "kind": r["kind"], "year": r["year"], "end_year": r["end_year"], "runtime": r["runtime_min"],
            "overview": r["overview_ru"] or r["overview_en"], "tagline": r["tagline_ru"] or r["tagline_en"],
            "language": r["original_language"], "poster": r["poster_path"], "backdrop": r["backdrop_path"],
            "genres": genres[f], "countries": countries[f],
            "ratings": {s: list(ratings[(f, s)]) for s in ("imdb", "tmdb") if (f, s) in ratings},
            "ids": {"wikidata": r["wikidata_id"], "tmdb": r["tmdb_id"], "tmdb_type": r["tmdb_type"],
                    "kinopoisk": r["kinopoisk_id"], "letterboxd": r["letterboxd_slug"]},
            "lists": entries[f],
            "credits": credits_by_film[f],
        }
    total = sum(_dump(OUT / "film" / f"{k}.json", v) for k, v in shards.items())
    log(f"film/: {len(shards)} shards, {total / 1e6:.1f} MB")

    # person/NN.json
    shards = defaultdict(dict)
    person_lists = defaultdict(list)
    for lid, pos, p in db.execute("SELECT list_id, pos, person_id FROM list_entry WHERE person_id IS NOT NULL"):
        person_lists[p].append([lid, pos])
    for r in db.execute("SELECT * FROM person"):
        p = r["id"]
        if p not in credits_by_person and p not in person_lists:
            continue
        shards[_shard(p)][p] = {
            "name": r["name"], "name_ru": r["name_ru"], "birth": r["birth_year"], "death": r["death_year"],
            "photo": r["photo_path"], "lists": person_lists[p], "credits": credits_by_person[p],
        }
    total = sum(_dump(OUT / "person" / f"{k}.json", v) for k, v in shards.items())
    log(f"person/: {len(shards)} shards, {total / 1e6:.1f} MB")


# --- Personal lists <-> D1 ---------------------------------------------------

def _wrangler(args: list[str], remote: bool) -> str:
    cmd = ["npx", "wrangler", "d1", "execute", D1_NAME, "--remote" if remote else "--local", *args]
    return subprocess.run(cmd, cwd=WEB, check=True, capture_output=True, text=True).stdout


def _sql_str(v) -> str:
    return "NULL" if v is None or v == "" else "'" + str(v).replace("'", "''") + "'"


def seed(remote: bool, force: bool = False) -> None:
    """Upload my/*.csv to D1. Refuses to overwrite non-empty D1 lists unless forced."""
    out = json.loads(_wrangler(["--json", "--command", "SELECT count(*) AS n FROM my_entry"], remote))
    if out[0]["results"][0]["n"] and not force:
        raise SystemExit("D1 already has personal entries; run `filmtr web pull` first, or pass --force")
    db = sqlite3.connect(paths.CATALOG_DB)
    sql = ["DELETE FROM my_entry;", "DELETE FROM my_list;"]
    for n, pl in enumerate(personal.load_all()):
        sql.append(f"INSERT INTO my_list (id, title, description, pos) VALUES "
                   f"({_sql_str(pl.id)}, {_sql_str(pl.title)}, {_sql_str(pl.description)}, {n});")
        for pos, e in enumerate(pl.entries):
            row = db.execute("SELECT coalesce(title_ru, title), year, poster_path FROM film WHERE id = ?",
                             (e.imdb_id,)).fetchone() or (e.title, e.year, None)
            sql.append(
                "INSERT INTO my_entry (list_id, film_id, pos, tags, note, added_at, updated_at, title, year, "
                f"poster_path) VALUES ({_sql_str(pl.id)}, {_sql_str(e.imdb_id)}, {pos}, "
                f"{_sql_str(json.dumps(e.tags, ensure_ascii=False))}, {_sql_str(e.note)}, "
                f"{_sql_str(e.added)}, {_sql_str(e.added)}, {_sql_str(row[0])}, {row[1] or 'NULL'}, "
                f"{_sql_str(row[2])});")
    path = paths.DATA / "seed-personal.sql"
    path.write_text("\n".join(sql), encoding="utf-8")
    _wrangler(["--file", str(path)], remote)
    path.unlink()
    log(f"seeded {'remote' if remote else 'local'} D1 from my/")


def pull(remote: bool) -> None:
    """Write personal lists from D1 to my/*.csv (to commit them to git)."""
    lists = json.loads(_wrangler(["--json", "--command",
                                  "SELECT id, title, description FROM my_list ORDER BY pos"], remote))[0]["results"]
    rows = json.loads(_wrangler(["--json", "--command",
                                 "SELECT list_id, film_id, title, year, tags, note, added_at FROM my_entry "
                                 "ORDER BY list_id, pos"], remote))[0]["results"]
    personal.MY.mkdir(exist_ok=True)
    with personal.LISTS_FILE.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "title", "description"])
        for l in lists:
            w.writerow([l["id"], l["title"], l["description"] or ""])
    for l in lists:
        pl = personal.PersonalList(l["id"], l["title"], l["description"] or "")
        for r in rows:
            if r["list_id"] == l["id"]:
                pl.entries.append(personal.Entry(r["film_id"], r["title"] or "", str(r["year"] or ""),
                                                 json.loads(r["tags"] or "[]"), r["note"] or "",
                                                 (r["added_at"] or "")[:10]))
        pl.save()
    log(f"pulled {len(rows)} entries in {len(lists)} lists into my/")
