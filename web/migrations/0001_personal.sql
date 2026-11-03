-- Personal lists, edited from the web app. The static catalog is not in D1;
-- entries keep a small snapshot (title, year, poster) so that a list renders
-- even for films outside the static catalog.
CREATE TABLE my_list (
    id          TEXT PRIMARY KEY,      -- favorites, watchlist, ...
    title       TEXT NOT NULL,
    description TEXT,
    pos         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE my_entry (
    list_id     TEXT NOT NULL REFERENCES my_list(id) ON DELETE CASCADE,
    film_id     TEXT NOT NULL,         -- IMDb id
    pos         REAL NOT NULL,         -- order in the list; fractional for cheap moves
    tags        TEXT NOT NULL DEFAULT '[]',  -- JSON array of strings
    note        TEXT,
    added_at    TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    title       TEXT,
    year        INTEGER,
    poster_path TEXT,
    PRIMARY KEY (list_id, film_id)
);

INSERT INTO my_list (id, title, description, pos) VALUES
    ('watchlist', 'Очередь', 'Что хочу посмотреть или пересмотреть', 0),
    ('favorites', 'Любимое', 'Самые важные и любимые фильмы', 1);
