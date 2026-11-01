"""Personal lists: favorites, watch queue, and any others.

The source of truth is plain CSV in my/ (committed to the repository):

    my/lists.csv        id, title, description — one row per list
    my/<list id>.csv    imdb_id, title, year, tags, note, added — one row per film

Row order is the order of the list. `title` and `year` are only for
readability; the film is identified by imdb_id. Tags are separated by "; ".

The catalog mirrors these files as lists of kind "personal" (see sync()), so
personal lists survive any rebuild and can be edited by hand.
"""

import csv
import datetime as dt
import json
import sqlite3
from dataclasses import dataclass, field

from filmtr import paths
from filmtr.log import log

MY = paths.ROOT / "my"
LISTS_FILE = MY / "lists.csv"
FIELDS = ["imdb_id", "title", "year", "tags", "note", "added"]
TAG_SEP = "; "


@dataclass
class Entry:
    imdb_id: str
    title: str = ""
    year: str = ""
    tags: list[str] = field(default_factory=list)
    note: str = ""
    added: str = ""


@dataclass
class PersonalList:
    id: str
    title: str
    description: str = ""
    entries: list[Entry] = field(default_factory=list)

    @property
    def path(self):
        return MY / f"{self.id}.csv"

    def find(self, imdb_id: str) -> Entry | None:
        return next((e for e in self.entries if e.imdb_id == imdb_id), None)

    def save(self) -> None:
        MY.mkdir(exist_ok=True)
        with self.path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(FIELDS)
            for e in self.entries:
                w.writerow([e.imdb_id, e.title, e.year, TAG_SEP.join(e.tags), e.note, e.added])


def load_all() -> list[PersonalList]:
    if not LISTS_FILE.exists():
        return []
    with LISTS_FILE.open(encoding="utf-8") as f:
        lists = [PersonalList(r["id"], r["title"], r.get("description") or "") for r in csv.DictReader(f)]
    for pl in lists:
        if pl.path.exists():
            with pl.path.open(encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    tags = [t.strip() for t in (r.get("tags") or "").split(";") if t.strip()]
                    pl.entries.append(Entry(r["imdb_id"].strip(), r.get("title") or "", r.get("year") or "",
                                            tags, r.get("note") or "", r.get("added") or ""))
    return lists


def load(list_id: str) -> PersonalList:
    for pl in load_all():
        if pl.id == list_id:
            return pl
    known = ", ".join(pl.id for pl in load_all()) or "none"
    raise SystemExit(f"no personal list '{list_id}' (known: {known}); add it to {LISTS_FILE}")


def today() -> str:
    return dt.date.today().isoformat()


def sync(db: sqlite3.Connection) -> None:
    """Mirror my/*.csv into the catalog, adding films that are not there yet."""
    from filmtr import catalog, enrich  # catalog imports this module

    lists = load_all()
    film_ids = {e.imdb_id for pl in lists for e in pl.entries}
    catalog.ensure_films(db, film_ids)

    # Russian names for the cast and crew of personal films.
    if film_ids:
        marks = ",".join("?" * len(film_ids))
        missing = [r[0] for r in db.execute(
            f"SELECT DISTINCT c.person_id FROM credit c JOIN person p ON p.id = c.person_id "
            f"WHERE c.film_id IN ({marks}) AND (c.role <> 'actor' OR c.billing <= 6) "
            f"AND p.wikidata_id IS NULL", sorted(film_ids))]
        if missing:
            enrich._people(db, missing)

    old = [r[0] for r in db.execute("SELECT id FROM list WHERE kind = 'personal'")]
    for list_id in old:
        db.execute("DELETE FROM entry_tag WHERE entry_id IN (SELECT id FROM list_entry WHERE list_id = ?)",
                   (list_id,))
        db.execute("DELETE FROM list_entry WHERE list_id = ?", (list_id,))
        db.execute("DELETE FROM list WHERE id = ?", (list_id,))

    known = {r[0] for r in db.execute("SELECT id FROM film")}
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for pl in lists:
        db.execute("INSERT INTO list (id, title, title_ru, kind, entity, source, url, edition, description, "
                   "fetched_at) VALUES (?, ?, ?, 'personal', 'film', 'me', NULL, NULL, ?, ?)",
                   (pl.id, pl.title, pl.title, pl.description or None, now))
        for pos, e in enumerate(pl.entries, 1):
            if e.imdb_id not in known:
                log(f"  {pl.id}: {e.imdb_id} ({e.title}) is not in IMDb data, skipped")
                continue
            raw = {"imdb": e.imdb_id, "title": e.title, "year": e.year}
            cur = db.execute(
                "INSERT INTO list_entry (list_id, pos, film_id, match, note, added_at, raw) "
                "VALUES (?, ?, ?, 'id', ?, ?, ?)",
                (pl.id, pos, e.imdb_id, e.note or None, e.added or None, json.dumps(raw, ensure_ascii=False)))
            db.executemany("INSERT OR IGNORE INTO entry_tag VALUES (?, ?)",
                           ((cur.lastrowid, t) for t in e.tags))
    db.commit()
