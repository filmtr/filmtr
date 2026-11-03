"""Command line: `uv run filmtr <command>`."""

import argparse
import re
import sqlite3
import sys


def _pick(results: list[dict]) -> dict | None:
    """The obvious match, or None if the choice is ambiguous.

    Obvious: the only exact title match, or one with 10x more votes than the
    next; without exact matches, the same rule over all results.
    """
    pool = [r for r in results if r["exact"]] or results
    if len(pool) == 1:
        return pool[0]
    if pool and (pool[0]["votes"] or 0) >= 10 * max(pool[1]["votes"] or 0, 1):
        return pool[0]
    return None


def _resolve(query: str, year: int | None) -> dict:
    from filmtr.search import describe, find
    if re.fullmatch(r"tt\d+", query):
        hit = _lookup(query)
        if hit is None:
            raise SystemExit(f"{query} is not in the IMDb data")
        return hit
    results = find(query, year)
    hit = _pick(results)
    if hit is None:
        print(f"'{query}' is ambiguous or not found. Candidates:", file=sys.stderr)
        for r in results:
            print("  " + describe(r), file=sys.stderr)
        print("Add --year, or pass the IMDb id instead of the title.", file=sys.stderr)
        raise SystemExit(1)
    return hit


def _lookup(tconst: str) -> dict | None:
    from filmtr.search import _title_ru
    from filmtr.sources import imdb
    staging = imdb.connect()
    row = staging.execute("SELECT tconst, kind, primary_title, original_title, year, rating, votes "
                          "FROM title WHERE tconst = ?", (tconst,)).fetchone()
    if row is None:
        return None
    keys = ["id", "kind", "title", "original_title", "year", "rating", "votes"]
    r = dict(zip(keys, row))
    r["directors"] = ", ".join(n for (n,) in staging.execute(
        "SELECT n.name FROM crew c JOIN name n USING (nconst) WHERE c.tconst = ? AND c.role = 'director' "
        "ORDER BY c.ord", (tconst,)))
    r["title_ru"] = _title_ru(staging, tconst)
    return r


def _sync() -> None:
    from filmtr import paths, personal
    if paths.CATALOG_DB.exists():
        with sqlite3.connect(paths.CATALOG_DB) as db:
            personal.sync(db)


def cmd_find(args) -> None:
    from filmtr.search import describe, find
    for r in find(" ".join(args.query), args.year, limit=args.limit):
        print(describe(r))


def cmd_add(args) -> None:
    from filmtr import personal
    from filmtr.search import describe
    pl = personal.load(args.list)
    hit = _resolve(" ".join(args.query), args.year)
    entry = pl.find(hit["id"])
    if entry:
        entry.tags += [t for t in args.tag if t not in entry.tags]
        entry.note = args.note if args.note is not None else entry.note
        action = "updated in"
    else:
        entry = personal.Entry(hit["id"], hit.get("title_ru") or hit["title"], str(hit["year"] or ""),
                               list(dict.fromkeys(args.tag)), args.note or "", personal.today())
        pl.entries.append(entry)
        action = "added to"
    pl.save()
    _sync()
    tags = f"  [{', '.join(entry.tags)}]" if entry.tags else ""
    print(f"{action} {pl.id}: {describe(hit)}{tags}")


def cmd_remove(args) -> None:
    from filmtr import personal
    pl = personal.load(args.list)
    query = " ".join(args.query)
    tconst = query if re.fullmatch(r"tt\d+", query) else _resolve(query, args.year)["id"]
    entry = pl.find(tconst)
    if entry is None:
        raise SystemExit(f"{tconst} is not in {pl.id}")
    if args.tag:
        entry.tags = [t for t in entry.tags if t not in args.tag]
        print(f"untagged {entry.title}: {', '.join(args.tag)}")
    else:
        pl.entries.remove(entry)
        print(f"removed from {pl.id}: {entry.title} ({entry.year})")
    pl.save()
    _sync()


def cmd_show(args) -> None:
    from filmtr import paths, personal
    lists = [personal.load(args.list)] if args.list else personal.load_all()
    db = sqlite3.connect(paths.CATALOG_DB) if paths.CATALOG_DB.exists() else None
    for pl in lists:
        entries = [e for e in pl.entries if not args.tag or args.tag in e.tags]
        print(f"## {pl.title} ({pl.id}, {len(entries)})")
        for e in entries:
            info = ""
            if db:
                row = db.execute("SELECT title, year, directors, imdb_rating FROM film_card WHERE id = ?",
                                 (e.imdb_id,)).fetchone()
                if row:
                    title, year, directors, rating = row
                    info = f"{title} ({year}) — {directors or '?'}, IMDb {rating}"
            info = info or f"{e.title} ({e.year})"
            tags = f"  [{', '.join(e.tags)}]" if e.tags else ""
            note = f"  — {e.note}" if e.note else ""
            print(f"  {e.imdb_id}  {info}{tags}{note}")
        print()


def cmd_tmdb(args) -> None:
    """Load TMDB data on demand: for given films, or for the whole catalog."""
    from filmtr import paths, tmdb
    with sqlite3.connect(paths.CATALOG_DB) as db:
        ids = set(args.ids) or {r[0] for r in db.execute("SELECT id FROM catalog")}
        tmdb.enrich(db, ids, refresh=args.refresh)


def cmd_web(args) -> None:
    from filmtr import web
    if args.action == "export":
        web.export()
    elif args.action == "seed":
        web.seed(remote=args.remote, force=args.force)
    elif args.action == "pull":
        web.pull(remote=args.remote)


def main() -> None:
    p = argparse.ArgumentParser(prog="filmtr")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download", help="download IMDb datasets")
    d.add_argument("--refresh", action="store_true", help="re-download even if present")
    sub.add_parser("stage", help="rebuild data/imdb.db from downloaded IMDb files")
    sub.add_parser("build", help="rebuild data/filmtr.db (stages IMDb first if needed)")
    sub.add_parser("stats", help="print catalog statistics")

    f = sub.add_parser("find", help="find a title in any language")
    f.add_argument("query", nargs="+")
    f.add_argument("--year", type=int)
    f.add_argument("--limit", type=int, default=8)
    f.set_defaults(func=cmd_find)

    a = sub.add_parser("add", help="add a film to a personal list (or update its tags/note)")
    a.add_argument("list", help="list id, e.g. favorites or watchlist")
    a.add_argument("query", nargs="+", help="title in any language, or an IMDb id (tt...)")
    a.add_argument("--year", type=int, help="disambiguate by year (±1)")
    a.add_argument("--tag", action="append", default=[], help="tag, repeatable")
    a.add_argument("--note")
    a.set_defaults(func=cmd_add)

    r = sub.add_parser("remove", help="remove a film from a personal list, or only some tags")
    r.add_argument("list")
    r.add_argument("query", nargs="+")
    r.add_argument("--year", type=int)
    r.add_argument("--tag", action="append", default=[], help="remove only this tag")
    r.set_defaults(func=cmd_remove)

    s = sub.add_parser("show", help="show personal lists")
    s.add_argument("list", nargs="?")
    s.add_argument("--tag", help="only entries with this tag")
    s.set_defaults(func=cmd_show)

    t = sub.add_parser("tmdb", help="load TMDB data (overview, poster, crew) for films; default: catalog")
    t.add_argument("ids", nargs="*", help="IMDb ids (tt...)")
    t.add_argument("--refresh", action="store_true", help="reload even if already loaded")
    t.set_defaults(func=cmd_tmdb)

    w = sub.add_parser("web", help="web app: export static data, sync personal lists with D1")
    w.add_argument("action", choices=["export", "seed", "pull"],
                   help="export: catalog JSON to web/public/data; seed: my/*.csv -> D1; pull: D1 -> my/*.csv")
    w.add_argument("--remote", action="store_true", help="use the deployed D1 instead of the local one")
    w.add_argument("--force", action="store_true", help="seed: overwrite non-empty D1 lists")
    w.set_defaults(func=cmd_web)

    args = p.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    elif args.cmd == "download":
        from filmtr.sources import imdb
        imdb.download(refresh=args.refresh)
    elif args.cmd == "stage":
        from filmtr.sources import imdb
        imdb.stage()
    elif args.cmd == "build":
        from filmtr import catalog
        catalog.build()
    elif args.cmd == "stats":
        from filmtr import stats
        stats.show()
