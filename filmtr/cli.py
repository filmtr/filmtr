"""Command line: `uv run filmtr <command>`."""

import argparse


def main() -> None:
    p = argparse.ArgumentParser(prog="filmtr")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download", help="download IMDb datasets")
    d.add_argument("--refresh", action="store_true", help="re-download even if present")
    sub.add_parser("stage", help="rebuild data/imdb.db from downloaded IMDb files")
    sub.add_parser("build", help="rebuild data/filmtr.db (stages IMDb first if needed)")
    sub.add_parser("stats", help="print catalog statistics")
    args = p.parse_args()

    if args.cmd == "download":
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
