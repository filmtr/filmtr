"""Find titles by name in any language, using the IMDb staging db."""

import re
import sqlite3

from filmtr import paths
from filmtr.sources import imdb
from filmtr.text import norm_title


def _fts_query(q: str, prefix: bool = False) -> str:
    """All words of the query. With prefix=True, only word stems are required,
    to tolerate spelling variants: "Шоу Трумэна" finds "Шоу Трумана"."""
    tokens = re.findall(r"\w+", q.replace("ё", "е").replace("Ё", "Е"))
    if prefix:
        return " ".join(f'"{t[:max(3, len(t) - 3)]}"*' if len(t) > 3 else f'"{t}"' for t in tokens)
    return " ".join(f'"{t}"' for t in tokens)


def find(query: str, year: int | None = None, limit: int = 8) -> list[dict]:
    """Titles whose primary, original or alternative title contains all words
    of the query. Exact title matches first, then by number of votes."""
    staging = imdb.connect()
    if not re.search(r"\w", query):
        return []
    rows = _search(staging, _fts_query(query), year)
    if not rows:
        rows = _search(staging, _fts_query(query, prefix=True), year)

    target = norm_title(query)
    results = []
    for t, kind, primary, original, y, rating, votes, matched in rows:
        exact = any(norm_title(m) == target for m in matched.split(" | "))
        results.append({"id": t, "kind": kind, "title": primary, "original_title": original,
                        "year": y, "rating": rating, "votes": votes, "exact": exact})
    results.sort(key=lambda r: (r["exact"], r["votes"] or 0), reverse=True)
    results = results[:limit]

    for r in results:
        r["directors"] = ", ".join(n for (n,) in staging.execute(
            "SELECT n.name FROM crew c JOIN name n USING (nconst) "
            "WHERE c.tconst = ? AND c.role = 'director' ORDER BY c.ord", (r["id"],)))
        r["title_ru"] = _title_ru(staging, r["id"])
    return results


def _search(staging: sqlite3.Connection, fts: str, year: int | None) -> list[tuple]:
    params: list = [fts]
    year_filter = ""
    if year:
        year_filter = "AND t.year BETWEEN ? AND ?"
        params += [year - 1, year + 1]
    return staging.execute(f"""
        SELECT t.tconst, t.kind, t.primary_title, t.original_title, t.year, t.rating, t.votes,
               group_concat(s.text, ' | ')
        FROM title_search s JOIN title t USING (tconst)
        WHERE title_search MATCH ? {year_filter}
        GROUP BY t.tconst ORDER BY t.votes DESC LIMIT 300""", params).fetchall()


def _title_ru(staging: sqlite3.Connection, tconst: str) -> str | None:
    if paths.CATALOG_DB.exists():
        with sqlite3.connect(paths.CATALOG_DB) as db:
            row = db.execute("SELECT title_ru FROM film WHERE id = ?", (tconst,)).fetchone()
            if row and row[0]:
                return row[0]
    row = staging.execute("SELECT title FROM aka WHERE tconst = ? AND region IN ('RU', 'SUHH') "
                          "ORDER BY region = 'RU' DESC, rowid LIMIT 1", (tconst,)).fetchone()
    return row[0] if row else None


def describe(r: dict) -> str:
    ru = f"{r['title_ru']} / " if r.get("title_ru") and r["title_ru"] != r["title"] else ""
    kind = "" if r["kind"] == "movie" else f", {r['kind']}"
    votes = f", IMDb {r['rating']} ({r['votes']:,})" if r.get("rating") else ""
    by = f" — {r['directors']}" if r.get("directors") else ""
    return f"{r['id']}  {ru}{r['title']} ({r['year']}{kind}){by}{votes}"
