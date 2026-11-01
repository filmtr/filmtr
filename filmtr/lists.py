"""Registry of lists that define what is worth attention.

Three kinds:
- poll:     critics' and filmmakers' polls (TSPDT, Sight and Sound)
- award:    festival and academy awards, from Wikidata
- computed: selections computed from ratings (IMDb core)
"""

import math
from dataclasses import dataclass, field
from typing import Callable

from filmtr.sources import polls, wikidata


@dataclass
class ListSpec:
    id: str
    title: str
    title_ru: str
    kind: str
    entity: str
    source: str
    url: str | None
    edition: str | None
    load: Callable[[], list[dict]] = field(repr=False)
    description: str | None = None


def _tspdt_films(page):
    return lambda: polls.tspdt_films(page)


def _tspdt_directors(page):
    return lambda: polls.tspdt_directors(page)


def _bfi(page):
    return lambda: polls.bfi_poll(page)


def _award(qid: str):
    """Winners of an award, with the year it was given."""
    def load():
        rows = wikidata.sparql(f"""
            SELECT ?imdb ?label (MIN(YEAR(?when)) AS ?year) (MIN(YEAR(?pub)) AS ?pubyear) WHERE {{
              ?film p:P166 ?st . ?st ps:P166 wd:{qid} .
              ?film wdt:P345 ?imdb . FILTER(STRSTARTS(?imdb, "tt"))
              OPTIONAL {{ ?st pq:P585 ?when }}
              OPTIONAL {{ ?film wdt:P577 ?pub }}
              OPTIONAL {{ ?film rdfs:label ?label FILTER(LANG(?label) = "en") }}
            }} GROUP BY ?imdb ?label""")
        entries = []
        for r in rows:
            year = r.get("year") or r.get("pubyear")
            entries.append({"imdb": r["imdb"], "title": r.get("label"),
                            "year": int(year) if year else None})
        entries.sort(key=lambda e: (e["year"] or 0, e["imdb"]))
        return entries
    return load


def award(id, qid, title, title_ru):
    return ListSpec(id, title, title_ru, "award", "film", "wikidata",
                    f"https://www.wikidata.org/wiki/{qid}", None, _award(qid))


# IMDb core: Bayesian-damped rating weighted by the log of the vote count.
# Damping and the vote floor keep out vote-brigaded titles; obscure classics
# come in through the critics' polls instead.
CORE_SIZE = 5000
CORE_MIN_VOTES = 10_000
CORE_PRIOR_VOTES = 10_000
CORE_PRIOR_RATING = 6.5


def core_score(rating: float, votes: int) -> float:
    damped = (votes * rating + CORE_PRIOR_VOTES * CORE_PRIOR_RATING) / (votes + CORE_PRIOR_VOTES)
    return (damped - 5) * math.log10(votes)


def imdb_core(staging) -> list[dict]:
    rows = staging.execute(
        "SELECT tconst, primary_title, year, rating, votes FROM title "
        "WHERE kind = 'movie' AND is_adult = 0 AND votes >= ?", (CORE_MIN_VOTES,)).fetchall()
    rows.sort(key=lambda r: core_score(r[3], r[4]), reverse=True)
    return [{"pos": i + 1, "imdb": t, "title": title, "year": year, "rating": rating,
             "votes": votes, "score": round(core_score(rating, votes), 3)}
            for i, (t, title, year, rating, votes) in enumerate(rows[:CORE_SIZE])]


LISTS = [
    ListSpec("tspdt-1000", "They Shoot Pictures, Don't They: The 1,000 Greatest Films",
             "TSPDT: 1000 величайших фильмов", "poll", "film", "tspdt",
             polls.TSPDT + "gf1000_all1000films_table.php", "2026",
             _tspdt_films("gf1000_all1000films_table.php"),
             "Aggregate of ~17,000 critics' and filmmakers' lists and ballots."),
    ListSpec("tspdt-21c-1000", "They Shoot Pictures, Don't They: The 21st Century's Most Acclaimed Films",
             "TSPDT: 1000 лучших фильмов XXI века", "poll", "film", "tspdt",
             polls.TSPDT + "21stcentury_allfilms_table.php", "2026",
             _tspdt_films("21stcentury_allfilms_table.php")),
    ListSpec("tspdt-directors-250", "They Shoot Pictures, Don't They: Top 250 Directors",
             "TSPDT: 250 лучших режиссёров", "poll", "person", "tspdt",
             polls.TSPDT + "gf1000_top250directors.htm", "2026",
             _tspdt_directors("gf1000_top250directors.htm")),
    ListSpec("tspdt-21c-directors-100", "They Shoot Pictures, Don't They: Top 100 Directors of the 21st Century",
             "TSPDT: 100 лучших режиссёров XXI века", "poll", "person", "tspdt",
             polls.TSPDT + "21stcentury_top100directors.htm", "2026",
             _tspdt_directors("21stcentury_top100directors.htm")),
    ListSpec("sight-and-sound-2022-critics", "Sight and Sound Greatest Films of All Time (critics' poll)",
             "Sight and Sound 2022: опрос критиков", "poll", "film", "bfi",
             polls.BFI + "greatest-films-all-time", "2022", _bfi("greatest-films-all-time")),
    ListSpec("sight-and-sound-2022-directors", "Sight and Sound Directors' 100 Greatest Films of All Time",
             "Sight and Sound 2022: опрос режиссёров", "poll", "film", "bfi",
             polls.BFI + "directors-100-greatest-films-all-time", "2022",
             _bfi("directors-100-greatest-films-all-time")),
    award("palme-dor", "Q179808", "Palme d'Or", "Золотая пальмовая ветвь"),
    award("golden-lion", "Q209459", "Golden Lion", "Золотой лев"),
    award("golden-bear", "Q154590", "Golden Bear", "Золотой медведь"),
    award("oscar-best-picture", "Q102427", "Academy Award for Best Picture", "Оскар за лучший фильм"),
    award("oscar-international-feature", "Q105304", "Academy Award for Best International Feature Film",
          "Оскар за лучший фильм на иностранном языке"),
    ListSpec("imdb-core-5000", "IMDb core 5000", "Ядро IMDb: 5000 фильмов", "computed", "film", "imdb",
             None, None, lambda: [],  # computed from staging, see imdb_core()
             f"Top {CORE_SIZE} movies by (damped rating - 5) * log10(votes); damped = Bayesian "
             f"average with {CORE_PRIOR_VOTES} prior votes at {CORE_PRIOR_RATING}; "
             f"at least {CORE_MIN_VOTES} votes."),
]
