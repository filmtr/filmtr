-- Books: a personal reading queue. There is no book catalog, so an entry
-- keeps everything itself; Open Library only provides the cover and a link.
CREATE TABLE my_book (
    id             INTEGER PRIMARY KEY,
    list_id        TEXT NOT NULL DEFAULT 'to-read',  -- to-read (later: read, favorites)
    title          TEXT NOT NULL,
    author         TEXT,
    year           INTEGER,                          -- when written or first published
    original_title TEXT,
    ol_work        TEXT,                             -- Open Library work id, e.g. OL498463W
    cover_id       INTEGER,                          -- Open Library cover id
    pos            REAL NOT NULL,
    tags           TEXT NOT NULL DEFAULT '[]',       -- JSON array of strings
    note           TEXT,
    added_at       TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX my_book_list ON my_book(list_id, pos);
