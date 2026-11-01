"""Match list entries (title, year, director) to IMDb ids in the staging db."""

import difflib
import re
import sqlite3
from collections import defaultdict

from filmtr.log import log
from filmtr.text import fold, name_tokens, norm_title

MIN_VOTES = 20  # ignore obscure duplicates when matching
MAX_YEAR_GAP = 10


def _director_names(field: str) -> list[str]:
    return [n.strip() for n in re.split(r" & | / | and |; ", field or "") if n.strip()]


def director_score(listed: str, imdb_names: list[str]) -> int:
    """2 = every token of a listed director found in an IMDb director's name,
    1 = a distinctive token (surname-like) found, 0 = no evidence."""
    imdb_tokens = [name_tokens(n) for n in imdb_names]
    best = 0
    for name in _director_names(listed):
        tokens = name_tokens(name)
        if not tokens:
            continue
        for s in imdb_tokens:
            if tokens <= s:
                return 2
            if any(len(t) >= 4 and t in s for t in tokens):
                best = 1
    return best


class FilmMatcher:
    def __init__(self, staging: sqlite3.Connection):
        self.db = staging
        self._dir_index: dict[str, set[str]] | None = None

    def _directors(self, tconst: str) -> list[str]:
        return [r[0] for r in self.db.execute(
            "SELECT n.name FROM crew c JOIN name n USING (nconst) "
            "WHERE c.tconst = ? AND c.role = 'director'", (tconst,))]

    def _title_hits(self, wanted: set[str]) -> dict[str, set[str]]:
        """Map normalized title -> tconsts having it as primary, original or alternative title."""
        hits: dict[str, set[str]] = defaultdict(set)
        q = ("SELECT tconst, primary_title, original_title FROM title "
             "WHERE votes >= ? AND year IS NOT NULL")
        for t, primary, original in self.db.execute(q, (MIN_VOTES,)):
            for s in {primary, original}:
                n = norm_title(s)
                if n in wanted:
                    hits[n].add(t)
        for t, s in self.db.execute("SELECT tconst, title FROM aka"):
            n = norm_title(s)
            if n in wanted:
                hits[n].add(t)
        return hits

    def _candidate_info(self, tconsts) -> dict[str, tuple]:
        if not tconsts:
            return {}
        marks = ",".join("?" * len(tconsts))
        return {r[0]: r[1:] for r in self.db.execute(
            f"SELECT tconst, year, votes, kind FROM title WHERE tconst IN ({marks})", list(tconsts))}

    def _director_index(self) -> dict[str, set[str]]:
        """Token -> nconsts of people who directed something."""
        if self._dir_index is None:
            log("  indexing directors")
            idx: dict[str, set[str]] = defaultdict(set)
            for n, name in self.db.execute(
                    "SELECT nconst, name FROM name WHERE nconst IN "
                    "(SELECT nconst FROM crew WHERE role = 'director')"):
                for tok in name_tokens(name):
                    idx[tok].add(n)
            self._dir_index = idx
        return self._dir_index

    def _fuzzy(self, e: dict) -> str | None:
        """Fallback: films by the listed director around that year, closest title."""
        idx = self._director_index()
        people: set[str] = set()
        for name in _director_names(e.get("director", "")):
            sets = [idx.get(t, set()) for t in name_tokens(name)]
            if sets:
                people |= set.intersection(*sets)
        if not people or len(people) > 50:
            return None
        marks = ",".join("?" * len(people))
        rows = self.db.execute(
            f"SELECT DISTINCT t.tconst, t.primary_title, t.original_title, t.votes FROM crew c "
            f"JOIN title t USING (tconst) WHERE c.role = 'director' AND c.nconst IN ({marks}) "
            f"AND t.year BETWEEN ? AND ?", [*people, e["year"] - 1, e["year"] + 1]).fetchall()
        target = norm_title(e["title"])
        best, best_ratio = None, 0.0
        for t, primary, original, votes in rows:
            titles = {primary, original} | {r[0] for r in self.db.execute(
                "SELECT title FROM aka WHERE tconst = ?", (t,))}
            ratio = max(difflib.SequenceMatcher(None, target, norm_title(s)).ratio() for s in titles)
            if ratio > best_ratio or (ratio == best_ratio and best and votes > best[1]):
                best, best_ratio = (t, votes), ratio
        if best and best_ratio >= 0.6:
            return best[0]
        if len(rows) == 1 and best_ratio >= 0.4:
            return rows[0][0]
        return None

    def match(self, entries: list[dict]) -> None:
        """Set `film_id` and `match` on each entry in place."""
        wanted = {norm_title(e["title"]) for e in entries}
        hits = self._title_hits(wanted)
        info = self._candidate_info({t for ts in hits.values() for t in ts})
        for e in entries:
            various = "various" in (e.get("director") or "").lower()
            cands = []
            for t in hits.get(norm_title(e["title"]), ()):
                year, votes, kind = info[t]
                if year is None:
                    continue
                gap = abs(year - e["year"])
                dscore = director_score(e.get("director", ""), self._directors(t))
                # Release years differ between sources (festival vs. release,
                # production delays); a confirmed director allows a wider gap.
                if gap > 1 and not (dscore == 2 and gap <= MAX_YEAR_GAP):
                    continue
                cands.append((dscore, -gap, kind in ("movie", "tvMovie"), votes, t))
            cands.sort(reverse=True)
            if cands and (cands[0][0] > 0 or not e.get("director")):
                e["film_id"], e["match"] = cands[0][-1], "exact"
            elif (t := self._fuzzy(e)) is not None:
                e["film_id"], e["match"] = t, "fuzzy"
            elif (t := _dominant(cands, various)) is not None:
                e["film_id"], e["match"] = t, "fuzzy"
            else:
                e["film_id"], e["match"] = None, None


def _dominant(cands: list[tuple], various: bool) -> str | None:
    """Same title within a year and no director evidence (names spelled too
    differently, "Various Directors"): accept the candidate only if it clearly
    dominates by votes."""
    near = sorted((c for c in cands if c[1] >= -1), key=lambda c: c[3], reverse=True)
    if not near:
        return None
    if various or len(near) == 1 or near[0][3] >= 10 * max(near[1][3], 1):
        return near[0][-1]
    return None


def match_people(staging: sqlite3.Connection, entries: list[dict], listed_films: set[str]) -> None:
    """Match person-list entries (directors) to IMDb people.

    1. exact: the IMDb name has all tokens of the listed name, in any order
       ("Bong Joon-ho" = "Bong Joon Ho"); the most-voted filmography wins.
    2. fuzzy: the surname (last word) matches a director of a listed film
       ("Alexander Dovzhenko" = "Aleksandr Dovzhenko"); the one with the most
       listed films wins.
    """
    directors: dict[str, tuple[set[str], int, int]] = {}
    rows = staging.execute(
        "SELECT n.nconst, n.name, sum(t.votes), group_concat(t.tconst) FROM name n "
        "JOIN crew c ON c.nconst = n.nconst AND c.role = 'director' "
        "JOIN title t ON t.tconst = c.tconst WHERE t.votes >= 100 GROUP BY n.nconst")
    for n, name, votes, films in rows:
        in_lists = sum(1 for t in films.split(",") if t in listed_films)
        directors[n] = (name_tokens(name), votes or 0, in_lists)
    by_token: dict[str, set[str]] = defaultdict(set)
    for n, (tokens, _, _) in directors.items():
        for t in tokens:
            by_token[t].add(n)

    for e in entries:
        tokens = name_tokens(e["name"])
        sets = [by_token.get(t, set()) for t in tokens]
        exact = set.intersection(*sets) if sets else set()
        if exact:
            best = max(exact, key=lambda n: (directors[n][2], directors[n][1]))
            e["person_id"], e["match"] = best, "exact"
            continue
        words = fold(e["name"]).replace("-", " ").split()
        surname = words[-1] if words else ""
        loose = {n for n in by_token.get(surname, ()) if directors[n][2] > 0} if len(surname) >= 4 else set()
        if loose:
            best = max(loose, key=lambda n: (directors[n][2], directors[n][1]))
            e["person_id"], e["match"] = best, "fuzzy"
        else:
            e["person_id"], e["match"] = None, None
