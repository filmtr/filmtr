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

## Личные списки

Списки «Любимое» (`favorites`) и «Очередь» (`watchlist`) хранятся в CSV-файлах в `my/`. Их можно править руками или командами:

```sh
uv run filmtr find Дюна                                # поиск на любом языке
uv run filmtr add favorites "Шоу Трумана"
uv run filmtr add favorites Дюна --year 2021           # при неоднозначности уточнить годом
uv run filmtr add watchlist tt1504320 --tag "с детьми" # или по ID IMDb
uv run filmtr remove watchlist tt1504320 --tag "с детьми"  # снять только тег
uv run filmtr show watchlist --tag "с детьми"
```

Если фильма ещё нет в каталоге, `add` добавит его вместе со съёмочной группой, описанием и постером.

## Данные TMDB

Описания, постеры (`data/posters/w342/`), ключевые слова и полные съёмочные группы загружаются при сборке только для фильмов из списков: лучших и личных. Остальные фильмы базы, то есть фильмографии, подгружаются по требованию:

```sh
uv run filmtr tmdb tt0056592 tt0060107   # конкретные фильмы
```

## Как устроено

```
data/raw/imdb/*.tsv.gz  ─┐
TSPDT, Sight & Sound     ├─► data/imdb.db (зеркало IMDb) ─► data/filmtr.db (каталог)
Wikidata (премии, ID, ru)┘
```

- **`data/imdb.db`** — урезанное зеркало IMDb для отбора и сопоставления: все тайтлы, кроме эпизодов сериалов, а у тайтлов с достаточным числом голосов ещё съёмочные группы и альтернативные названия.
- **`data/filmtr.db`** — сам каталог. Он полностью пересобирается из источников, а личные списки при каждой сборке загружаются из `my/`.

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
- [TMDB](https://www.themoviedb.org/) — описания, постеры, полные съёмочные группы. *This product uses the TMDB API but is not endorsed or certified by TMDB.* Бесплатно для некоммерческого использования. Ключ API читается из `~/.tmdb-api-read-access-token` или `~/.tmdb-api-key` (либо `$TMDB_TOKEN`, `$TMDB_API_KEY`) и в репозиторий не попадает.
- [They Shoot Pictures, Don't They](https://theyshootpictures.com/) и [BFI Sight and Sound](https://www.bfi.org.uk/sight-and-sound/greatest-films-all-time) — списки для личного использования.
