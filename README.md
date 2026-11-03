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

## Веб-интерфейс

`web/` — лёгкое приложение для Cloudflare: Worker со статическими файлами и базой D1.

- **Каталог** — статические JSON-файлы, которые собирает `filmtr web export` в `web/public/data/` (в git не попадают: это производные данные IMDb).
- **Личные списки** — в D1, их правит Worker (`/api/my`). Постеры берутся с CDN TMDB.
- **Книги** — очередь чтения (`/books`, `/api/books`) тоже в D1. Каталога книг нет: название, автор и год хранятся в самой записи, а обложки и ссылки берутся из [Open Library](https://openlibrary.org/).
- **Доступ** — только через Cloudflare Access. Worker проверяет токен Access на каждом запросе, включая статические файлы. Пока Access не настроен, сайт отдаёт 403 на всё.

### Локально

```sh
uv run filmtr web export                    # каталог в web/public/data
cd web && npm install
npm run db:migrate:local                    # таблицы личных списков в локальной D1
cd .. && uv run filmtr web seed && cd web   # my/*.csv и my/books.csv -> локальная D1
printf 'DEV_NO_AUTH=1\nTMDB_TOKEN=%s\n' "$(cat ~/.tmdb-api-read-access-token)" > .dev.vars
npm run dev                                 # http://localhost:5173
```

### Первый деплой

```sh
cd web
npx wrangler login
npx wrangler d1 create filmtr               # id базы вписать в wrangler.jsonc, database_id
npm run db:migrate:remote
npx wrangler secret put TMDB_TOKEN          # вставить токен из ~/.tmdb-api-read-access-token
cd .. && uv run filmtr web seed --remote && cd web
npm run deploy                              # https://filmtr.<аккаунт>.workers.dev, пока всё отдаёт 403
```

Затем включить Cloudflare Access: в панели Cloudflare открыть Workers & Pages → filmtr → Settings → Domains & Routes и включить Cloudflare Access для workers.dev. В политике оставить только свой email. Из настроек приложения Access (Zero Trust → Access → Applications) взять team domain (`<team>.cloudflareaccess.com`) и Application Audience (AUD), вписать их в `vars` в `wrangler.jsonc` и снова выполнить `npm run deploy`.

### Обновление данных

Личные списки правятся в вебе, а в git сохраняются так:

```sh
uv run filmtr web pull --remote   # D1 -> my/*.csv и my/books.csv, затем закоммитить
uv run filmtr build               # фильмы, добавленные из веба, попадают в каталог с полными данными
uv run filmtr web export && (cd web && npm run deploy)
```

Пока работает веб, главная копия личных списков — в D1. Команды `filmtr add/remove` правят только `my/*.csv`. Чтобы перенести такие правки в веб, нужен `filmtr web seed --remote --force`, а он перезапишет то, что изменили в вебе.

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
