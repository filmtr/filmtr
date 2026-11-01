from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
IMDB_RAW = RAW / "imdb"
CACHE = RAW / "cache"          # cached HTTP responses (HTML pages, SPARQL results)
IMDB_DB = DATA / "imdb.db"     # staging mirror of IMDb, rebuildable
CATALOG_DB = DATA / "filmtr.db"
OVERRIDES = DATA / "overrides"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"
