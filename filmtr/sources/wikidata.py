"""Wikidata: identifiers, Russian labels, countries and awards. CC0."""

import json

from filmtr.http import fetch

ENDPOINT = "https://query.wikidata.org/sparql"


def sparql(query: str) -> list[dict[str, str]]:
    """Run a SPARQL query and return rows as {variable: plain value}."""
    text = fetch(ENDPOINT, data={"query": query},
                 headers={"Accept": "application/sparql-results+json"}, ext="json")
    rows = []
    for b in json.loads(text)["results"]["bindings"]:
        row = {}
        for k, v in b.items():
            value = v["value"]
            if v["type"] == "uri" and value.startswith("http://www.wikidata.org/entity/"):
                value = value.rsplit("/", 1)[1]
            row[k] = value
        rows.append(row)
    return rows


def chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def values(ids: list[str]) -> str:
    return " ".join(f'"{i}"' for i in ids)
