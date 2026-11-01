-- Filmtr catalog schema (data/filmtr.db).
--
-- The catalog is fully rebuildable from public sources: `filmtr build` drops
-- and recreates it. Personal data (marks, queues, notes) must therefore live
-- elsewhere and refer to films and people by their stable IMDb ids, which are
-- the primary keys here.
--
-- Everything "curated" is a list: critics' polls, festival awards and the
-- computed IMDb core are all rows in `list`. A film is part of the catalog
-- ("worth attention") when it appears in at least one list. Other films are
-- kept only so that a person's filmography is complete.

PRAGMA foreign_keys = ON;

-- Films -----------------------------------------------------------------

CREATE TABLE film (
    id              TEXT PRIMARY KEY,   -- IMDb tconst, e.g. tt0069293
    kind            TEXT NOT NULL,      -- IMDb titleType: movie, tvMovie, short, tvMiniSeries, ...
    title           TEXT NOT NULL,      -- IMDb primary title
    original_title  TEXT,
    title_ru        TEXT,
    year            INTEGER,
    end_year        INTEGER,            -- series only
    runtime_min     INTEGER,
    wikidata_id     TEXT,
    tmdb_id         INTEGER,
    kinopoisk_id    INTEGER,
    letterboxd_slug TEXT
);
CREATE INDEX film_year ON film(year);

CREATE TABLE genre (
    id      TEXT PRIMARY KEY,           -- IMDb genre name, e.g. Drama
    name_ru TEXT
);

CREATE TABLE film_genre (
    film_id TEXT NOT NULL REFERENCES film(id) ON DELETE CASCADE,
    genre   TEXT NOT NULL REFERENCES genre(id),
    PRIMARY KEY (film_id, genre)
) WITHOUT ROWID;
CREATE INDEX film_genre_genre ON film_genre(genre);

CREATE TABLE country (
    id      TEXT PRIMARY KEY,           -- ISO 3166-1 alpha-2 when known, else Wikidata QID
    name_en TEXT,
    name_ru TEXT
);

CREATE TABLE film_country (
    film_id TEXT NOT NULL REFERENCES film(id) ON DELETE CASCADE,
    country TEXT NOT NULL REFERENCES country(id),
    PRIMARY KEY (film_id, country)
) WITHOUT ROWID;
CREATE INDEX film_country_country ON film_country(country);

-- Ratings from external sources; one row per film and source.
CREATE TABLE rating (
    film_id TEXT NOT NULL REFERENCES film(id) ON DELETE CASCADE,
    source  TEXT NOT NULL,              -- imdb, (later: tmdb, kinopoisk, letterboxd)
    value   REAL NOT NULL,              -- on the source's own scale
    scale   REAL NOT NULL,              -- maximum of that scale, e.g. 10
    votes   INTEGER,
    PRIMARY KEY (film_id, source)
) WITHOUT ROWID;

-- People ----------------------------------------------------------------

CREATE TABLE person (
    id          TEXT PRIMARY KEY,       -- IMDb nconst, e.g. nm0853567
    name        TEXT NOT NULL,
    name_ru     TEXT,
    birth_year  INTEGER,
    death_year  INTEGER,
    wikidata_id TEXT,
    tmdb_id     INTEGER
);

CREATE TABLE role (
    id      TEXT PRIMARY KEY,           -- director, writer, cinematographer, ...
    name_ru TEXT NOT NULL,
    sort    INTEGER NOT NULL            -- display order on a film page
);

CREATE TABLE credit (
    film_id    TEXT NOT NULL REFERENCES film(id) ON DELETE CASCADE,
    person_id  TEXT NOT NULL REFERENCES person(id),
    role       TEXT NOT NULL REFERENCES role(id),
    billing    INTEGER,                 -- order in the credits, lower is more prominent
    job        TEXT,                    -- free-form detail, e.g. "novel", "co-director"
    characters TEXT,                    -- actors only, "; "-separated
    PRIMARY KEY (film_id, person_id, role)
) WITHOUT ROWID;
CREATE INDEX credit_person ON credit(person_id, role);

-- Lists: critics' polls, awards, computed selections, personal lists ---

CREATE TABLE list (
    id          TEXT PRIMARY KEY,       -- slug, e.g. tspdt-1000
    title       TEXT NOT NULL,
    title_ru    TEXT,
    kind        TEXT NOT NULL,          -- poll | award | computed | personal
    entity      TEXT NOT NULL,          -- film | person
    source      TEXT NOT NULL,          -- tspdt, bfi, wikidata, imdb; me for personal lists
    url         TEXT,
    edition     TEXT,                   -- e.g. "2026" for a yearly poll
    description TEXT,
    fetched_at  TEXT NOT NULL
);

-- An entry keeps the raw source row so that unmatched entries can be fixed
-- later (see data/overrides/list_matches.csv).
CREATE TABLE list_entry (
    id        INTEGER PRIMARY KEY,
    list_id   TEXT NOT NULL REFERENCES list(id) ON DELETE CASCADE,
    pos       INTEGER,                  -- rank in a poll, order in a personal list; NULL for awards
    year      INTEGER,                  -- award year, if any
    film_id   TEXT REFERENCES film(id),
    person_id TEXT REFERENCES person(id),
    match     TEXT,                     -- id | exact | fuzzy | override; NULL = unmatched
    note      TEXT,                     -- personal lists: free-form note
    added_at  TEXT,                     -- personal lists: date added
    raw       TEXT NOT NULL             -- JSON of the source row
);
CREATE INDEX list_entry_list ON list_entry(list_id, pos);
CREATE INDEX list_entry_film ON list_entry(film_id);
CREATE INDEX list_entry_person ON list_entry(person_id);

-- Tags on list entries, e.g. "с детьми", "пересмотреть" in a personal queue.
CREATE TABLE entry_tag (
    entry_id INTEGER NOT NULL REFERENCES list_entry(id) ON DELETE CASCADE,
    tag      TEXT NOT NULL,
    PRIMARY KEY (entry_id, tag)
) WITHOUT ROWID;
CREATE INDEX entry_tag_tag ON entry_tag(tag);

-- Views -----------------------------------------------------------------

-- Films worth attention: present in at least one list.
CREATE VIEW catalog AS
SELECT f.*,
       group_concat(DISTINCT e.list_id) AS lists
FROM film f
JOIN list_entry e ON e.film_id = f.id
GROUP BY f.id;

-- Convenient flat view for browsing.
CREATE VIEW film_card AS
SELECT f.id,
       coalesce(f.title_ru, f.title) AS title,
       f.original_title,
       f.year,
       f.runtime_min,
       r.value AS imdb_rating,
       r.votes AS imdb_votes,
       (SELECT group_concat(g.genre, ', ') FROM film_genre g WHERE g.film_id = f.id) AS genres,
       (SELECT group_concat(coalesce(c.name_ru, c.name_en), ', ')
          FROM film_country fc JOIN country c ON c.id = fc.country
         WHERE fc.film_id = f.id) AS countries,
       (SELECT group_concat(coalesce(p.name_ru, p.name), ', ')
          FROM credit cr JOIN person p ON p.id = cr.person_id
         WHERE cr.film_id = f.id AND cr.role = 'director') AS directors,
       (SELECT group_concat(DISTINCT e.list_id) FROM list_entry e WHERE e.film_id = f.id) AS lists
FROM film f
LEFT JOIN rating r ON r.film_id = f.id AND r.source = 'imdb';

-- Reference data --------------------------------------------------------

INSERT INTO role (id, name_ru, sort) VALUES
    ('director',            'Режиссёр',            1),
    ('writer',              'Сценарист',           2),
    ('cinematographer',     'Оператор',            3),
    ('composer',            'Композитор',          4),
    ('editor',              'Монтажёр',            5),
    ('production_designer', 'Художник-постановщик', 6),
    ('producer',            'Продюсер',            7),
    ('actor',               'Актёр',               8),
    ('self',                'В роли себя',         9),
    ('casting_director',    'Кастинг-директор',    10);

INSERT INTO genre (id, name_ru) VALUES
    ('Action', 'Боевик'), ('Adult', 'Для взрослых'), ('Adventure', 'Приключения'),
    ('Animation', 'Анимация'), ('Biography', 'Биография'), ('Comedy', 'Комедия'),
    ('Crime', 'Криминал'), ('Documentary', 'Документальный'), ('Drama', 'Драма'),
    ('Family', 'Семейный'), ('Fantasy', 'Фэнтези'), ('Film-Noir', 'Нуар'),
    ('Game-Show', 'Игровое шоу'), ('History', 'История'), ('Horror', 'Ужасы'),
    ('Music', 'Музыка'), ('Musical', 'Мюзикл'), ('Mystery', 'Детектив'),
    ('News', 'Новости'), ('Reality-TV', 'Реалити-шоу'), ('Romance', 'Мелодрама'),
    ('Sci-Fi', 'Фантастика'), ('Short', 'Короткометражный'), ('Sport', 'Спорт'),
    ('Talk-Show', 'Ток-шоу'), ('Thriller', 'Триллер'), ('War', 'Военный'),
    ('Western', 'Вестерн');
