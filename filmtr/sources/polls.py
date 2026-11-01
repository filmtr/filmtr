"""Parsers for critics' polls published as web pages.

Each parser returns raw entries as dicts. Film entries have
`pos, title, year, director` (and optionally `country`, `runtime`);
person entries have `pos, name`.
"""

import html
import re

from filmtr.http import fetch

TSPDT = "https://theyshootpictures.com/"
BFI = "https://www.bfi.org.uk/sight-and-sound/"


def _cells(row: str) -> list[str]:
    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
    return [html.unescape(re.sub(r"<[^>]+>", "", c)).strip().lstrip("﻿") for c in cells]


def tspdt_films(page: str) -> list[dict]:
    """TSPDT table pages: Pos | previous Pos | Title | Director | Year | Country | Mins."""
    text = fetch(TSPDT + page)
    rows = [_cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S)]
    header, body = rows[0], rows[1:]
    assert header[0] == "Pos" and header[2] == "Title", header
    entries = []
    for pos, prev, title, director, year, country, mins in (r[:7] for r in body):
        entries.append({
            "pos": int(pos), "prev_pos": int(prev) if prev.isdigit() and prev != "0" else None,
            # Titles may carry a disambiguation suffix: "M [1931]", "Wire, The [TV]".
            "title": re.sub(r"(?<=\S)\s*\[[^\]]*\]$", "", title), "director": director, "year": int(year[:4]),
            "country": country, "runtime": int(mins) if mins.isdigit() else None,
        })
    return entries


def tspdt_directors(page: str) -> list[dict]:
    """TSPDT director rankings: '13. Andrei Tarkovsky (13) 7 films in ...'."""
    text = fetch(TSPDT + page)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text)
    entries = []
    for pos, names in re.findall(r"(?<![\d,])(\d{1,3})\. ([^()0-9]+?) \((?:\d+|NE|new|re)\)", text):
        for name in names.split(" & "):
            entries.append({"pos": int(pos), "name": name.strip()})
    return entries


def bfi_poll(page: str) -> list[dict]:
    """BFI Sight and Sound 2022 poll page (critics: top 250, directors: top 100).

    The page renders each film as: title, rank, blurb, year, countries,
    'Directed by', director.
    """
    text = fetch(BFI + page)
    text = re.sub(r"<(script|style).*?</\1>", "", text, flags=re.S)
    lines = [l.strip() for l in html.unescape(re.sub(r"<[^>]+>", "\n", text)).split("\n")]
    lines = [l for l in lines if l]
    entries = []
    for k, line in enumerate(lines):
        if line != "Directed by":
            continue
        year = lines[k - 2]
        if not re.fullmatch(r"\d{4}", year):
            continue
        j = k - 3
        while j > k - 8 and not lines[j].isdigit():
            j -= 1
        title = lines[j - 2] if lines[j - 1] == "=" else lines[j - 1]  # "=" marks a tie
        entries.append({
            "pos": int(lines[j]), "title": title, "year": int(year),
            "country": lines[k - 1], "director": lines[k + 1],
        })
    entries.sort(key=lambda e: e["pos"])
    return entries
