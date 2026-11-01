# Filmtr

Личный локальный каталог фильмов, достойных внимания, с фокусом на их создателях.

## Быстрый старт

Нужен [uv](https://docs.astral.sh/uv/). Внешних зависимостей нет, только стандартная библиотека Python 3.12.

```sh
uv run filmtr build   # скачать IMDb (~1,9 ГБ), собрать data/imdb.db и data/filmtr.db
uv run filmtr stats   # размер каталога, покрытие и несопоставленные записи
sqlite3 data/filmtr.db "SELECT * FROM film_card WHERE lists LIKE '%tspdt-1000%' LIMIT 10"
```

Первая сборка занимает около 10 минут: скачивание, раскладка IMDb по таблицам и запросы к Wikidata. Ответы сайтов кэшируются в `data/raw/cache/`, поэтому повторные сборки быстрее. Чтобы обновить данные, удали кэш или нужные файлы в `data/raw/`.

## Как устроено

```
data/raw/imdb/*.tsv.gz  ─┐
TSPDT, Sight & Sound     ├─► data/imdb.db (зеркало IMDb) ─► data/filmtr.db (каталог)
Wikidata (премии, ID, ru)┘
```

- **`data/imdb.db`** — урезанное зеркало IMDb для отбора и сопоставления: все тайтлы, кроме эпизодов сериалов, а у тайтлов с достаточным числом голосов ещё съёмочные группы и альтернативные названия.
- **`data/filmtr.db`** — сам каталог. Он полностью пересобирается из источников, поэтому личные данные (отметки, очереди) будут храниться отдельно и ссылаться на ID IMDb.

Модель данных описана в [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md), схема — в [`filmtr/schema.sql`](filmtr/schema.sql). Исследование источников — в [`docs/RESEARCH.md`](docs/RESEARCH.md).

## Ручные исправления

Если запись списка не сопоставилась с IMDb или сопоставилась неверно, исправление добавляется в `data/overrides/list_matches.csv`. Название указывается как в источнике: у нескольких записей может быть одно место.

```csv
list_id,pos,source_title,imdb_id,comment
tspdt-1000,123,Some Title,tt0012345,альтернативное название
```

## Источники и лицензии

- [IMDb Non-Commercial Datasets](https://developer.imdb.com/non-commercial-datasets/) — только личное некоммерческое использование.
- [Wikidata](https://www.wikidata.org/) — CC0.
- [They Shoot Pictures, Don't They](https://theyshootpictures.com/) и [BFI Sight and Sound](https://www.bfi.org.uk/sight-and-sound/greatest-films-all-time) — списки для личного использования.
