import { useSignal } from "@preact/signals";
import { useLocation } from "preact-iso";
import { useEffect } from "preact/hooks";
import { Loading, NoteEditor, Tag, TagEditor } from "../components";
import { addBook, books, removeBook, saveBook, toast, type Book } from "../data";
import { plural } from "../util";

const LISTS: Record<string, string> = { "to-read": "Прочитать", read: "Прочитано" };
const BOOK_TAGS = ["перечитать", "в отпуск", "короткая", "с детьми"];

const cover = (id: number | null | undefined, size: "S" | "M" | "L" = "M") =>
  id ? `https://covers.openlibrary.org/b/id/${id}-${size}.jpg` : null;

function Cover(props: { book: Pick<Book, "cover_id" | "title" | "author">; size?: "S" | "M" | "L" }) {
  const src = cover(props.book.cover_id, props.size);
  return src ? (
    <img class="poster" src={src} alt="" loading="lazy" decoding="async" />
  ) : (
    <div class="poster none book-none" aria-hidden="true">
      <span>
        {props.book.title}
        {props.book.author && <small>{props.book.author}</small>}
      </span>
    </div>
  );
}

export function BooksPage() {
  const { query, route } = useLocation();
  const open = useSignal<number | null>(null);
  const adding = useSignal(false);
  if (books.value === null) return <Loading text="Загружаю книги…" />;

  const listId = query.list && LISTS[query.list] ? query.list : "to-read";
  const tag = query.tag ?? null;
  const inList = books.value.filter((b) => b.list_id === listId).sort((a, b) => a.pos - b.pos);
  const tags = [...new Set(inList.flatMap((b) => b.tags))];
  const shown = tag ? inList.filter((b) => b.tags.includes(tag)) : inList;
  const tabs = Object.keys(LISTS).filter((id) => id === "to-read" || books.value!.some((b) => b.list_id === id));
  const allBookTags = [...new Set([...books.value.flatMap((b) => b.tags), ...BOOK_TAGS])];
  const current = open.value !== null ? books.value.find((b) => b.id === open.value) : undefined;

  return (
    <main class="books">
      <div class="list-switch" role="tablist">
        {tabs.map((id) => (
          <button
            type="button"
            role="tab"
            aria-selected={id === listId}
            class={id === listId ? "on" : ""}
            onClick={() => route(id === "to-read" ? "/books" : `/books?list=${id}`, true)}
          >
            {LISTS[id]}
            <span class="count">{books.value!.filter((b) => b.list_id === id).length}</span>
          </button>
        ))}
      </div>

      <div class="moods">
        {tags.length > 0 && (
          <div class="tag-row" aria-label="Теги">
            {tags.map((t) => (
              <Tag
                key={t}
                tag={t}
                on={t === tag}
                onClick={() => {
                  const qs = [listId !== "to-read" && `list=${listId}`, t !== tag && `tag=${encodeURIComponent(t)}`];
                  route(`/books${qs.some(Boolean) ? "?" + qs.filter(Boolean).join("&") : ""}`, true);
                }}
              />
            ))}
          </div>
        )}
        <div class="pick-bar">
          {listId === "to-read" && (
            <button type="button" class="pick" onClick={() => (adding.value = !adding.value)} aria-expanded={adding.value}>
              {adding.value ? "Закрыть поиск" : "Добавить книгу"}
            </button>
          )}
          <span class="muted">
            {shown.length} {plural(shown.length, "книга", "книги", "книг")}
          </span>
        </div>
        {adding.value && <AddBook />}
      </div>

      {shown.length === 0 ? (
        <p class="empty">
          {listId === "to-read"
            ? "Очередь чтения пуста. Добавьте книгу, которую давно собираетесь прочитать."
            : "Здесь будут прочитанные книги."}
        </p>
      ) : (
        <div class="grid">
          {shown.map((b) => (
            <button type="button" class="card book-card" key={b.id} onClick={() => (open.value = b.id)}>
              <Cover book={b} />
              <span class="card-title">{b.title}</span>
              <span class="card-sub">{[b.author, b.year].filter(Boolean).join(", ")}</span>
              {b.tags.length > 0 && (
                <span class="card-tags">
                  {b.tags.map((t) => (
                    <Tag key={t} tag={t} />
                  ))}
                </span>
              )}
              {b.note && <span class="card-note">{b.note}</span>}
            </button>
          ))}
        </div>
      )}

      {current && <BookDialog book={current} tags={allBookTags} onClose={() => (open.value = null)} />}
    </main>
  );
}

function BookDialog(props: { book: Book; tags: string[]; onClose: () => void }) {
  const b = props.book;
  const editing = useSignal(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && props.onClose();
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, []);
  const move = (listId: string, message: string) => {
    const from = b.list_id;
    saveBook(b.id, { list_id: listId, position: "top" });
    toast(message, () => saveBook(b.id, { list_id: from }));
    props.onClose();
  };

  return (
    <div class="picked-backdrop" onClick={props.onClose}>
      <div class="picked book-dialog" role="dialog" aria-modal="true" aria-label={b.title} onClick={(e) => e.stopPropagation()}>
        <Cover book={b} size="L" />
        <div class="picked-body">
          {editing.value ? (
            <BookForm
              initial={b}
              submit="Сохранить"
              onSubmit={(fields) => {
                saveBook(b.id, fields);
                editing.value = false;
              }}
              onCancel={() => (editing.value = false)}
            />
          ) : (
            <>
              <h2 class="film-title">{b.title}</h2>
              <p class="muted">
                {[b.author, b.year].filter(Boolean).join(", ")}
                {b.original_title && <span class="original-inline">, {b.original_title}</span>}
              </p>
            </>
          )}
          <TagEditor tags={b.tags} suggestions={props.tags} onChange={(tags) => saveBook(b.id, { tags })} />
          <NoteEditor
            note={b.note}
            placeholder="Заметка: кто посоветовал, почему хочется прочитать"
            onSave={(note) => saveBook(b.id, { note })}
          />
          <div class="picked-actions">
            {b.list_id === "to-read" ? (
              <>
                <button type="button" class="btn primary" onClick={() => move("read", `«${b.title}» прочитана`)}>
                  Прочитал
                </button>
                <button type="button" class="btn" onClick={() => saveBook(b.id, { position: "top" })}>
                  Поднять наверх
                </button>
              </>
            ) : (
              <button type="button" class="btn" onClick={() => move("to-read", `«${b.title}» снова в очереди`)}>
                Вернуть в очередь
              </button>
            )}
            {!editing.value && (
              <button type="button" class="link" onClick={() => (editing.value = true)}>
                Изменить
              </button>
            )}
            {b.ol_work && (
              <a class="link quiet" href={`https://openlibrary.org/works/${b.ol_work}`} target="_blank" rel="noreferrer">
                Open Library
              </a>
            )}
            <button
              type="button"
              class="link quiet"
              onClick={() => {
                const saved = b;
                removeBook(b.id);
                props.onClose();
                toast(`«${b.title}» удалена`, () => addBook({ ...saved, position: undefined }));
              }}
            >
              Удалить
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

type Fields = { title: string; author: string; year: string; original_title: string };

function BookForm(props: {
  initial?: Partial<Book>;
  submit: string;
  onSubmit: (f: { title: string; author: string | null; year: number | null; original_title: string | null }) => void;
  onCancel?: () => void;
}) {
  const f = useSignal<Fields>({
    title: props.initial?.title ?? "",
    author: props.initial?.author ?? "",
    year: props.initial?.year ? String(props.initial.year) : "",
    original_title: props.initial?.original_title ?? "",
  });
  const field = (key: keyof Fields, label: string, attrs: Record<string, unknown> = {}) => (
    <label class="field">
      <span>{label}</span>
      <input
        value={f.value[key]}
        onInput={(e) => (f.value = { ...f.value, [key]: e.currentTarget.value })}
        {...attrs}
      />
    </label>
  );
  return (
    <form
      class="book-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (!f.value.title.trim()) return;
        props.onSubmit({
          title: f.value.title.trim(),
          author: f.value.author.trim() || null,
          year: Number(f.value.year) || null,
          original_title: f.value.original_title.trim() || null,
        });
      }}
    >
      {field("title", "Название", { required: true })}
      {field("author", "Автор")}
      {field("year", "Год", { inputMode: "numeric", pattern: "\\d{1,4}" })}
      {field("original_title", "Название в оригинале")}
      <div class="picked-actions">
        <button type="submit" class="btn primary">
          {props.submit}
        </button>
        {props.onCancel && (
          <button type="button" class="link quiet" onClick={props.onCancel}>
            Отмена
          </button>
        )}
      </div>
    </form>
  );
}

type OlDoc = {
  key: string;
  title: string;
  author_name?: string[];
  first_publish_year?: number;
  cover_i?: number;
  edition_count?: number;
};

/** Search Open Library, or enter a book by hand. */
function AddBook() {
  const q = useSignal("");
  const results = useSignal<OlDoc[] | "loading" | null>(null);
  const manual = useSignal(false);

  const search = async () => {
    if (!q.value.trim()) return;
    results.value = "loading";
    try {
      const url =
        "https://openlibrary.org/search.json?limit=12&fields=key,title,author_name,first_publish_year,cover_i,edition_count&q=" +
        encodeURIComponent(q.value.trim());
      const r = await fetch(url);
      if (!r.ok) throw new Error(`Open Library: ${r.status}`);
      results.value = ((await r.json()) as { docs: OlDoc[] }).docs;
    } catch (e) {
      results.value = null;
      toast(`Поиск не удался: ${e instanceof Error ? e.message : e}`);
    }
  };

  const add = async (fields: Parameters<typeof addBook>[0]) => {
    const book = await addBook({ ...fields, list_id: "to-read" });
    if (book) toast(`«${book.title}» добавлена в очередь чтения`);
  };

  return (
    <section class="add-book" aria-label="Добавить книгу">
      <form
        class="filters"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          search();
        }}
      >
        <input
          type="search"
          class="filter-q"
          placeholder="Название или автор, например «Пикник на обочине»"
          aria-label="Найти книгу в Open Library"
          value={q.value}
          onInput={(e) => (q.value = e.currentTarget.value)}
        />
        <button type="submit" class="btn">
          Найти
        </button>
        <button type="button" class="link" onClick={() => (manual.value = !manual.value)}>
          Ввести вручную
        </button>
      </form>
      {manual.value && (
        <BookForm
          initial={{ title: q.value }}
          submit="Добавить в очередь"
          onSubmit={(fields) => {
            add(fields);
            manual.value = false;
          }}
          onCancel={() => (manual.value = false)}
        />
      )}
      {results.value === "loading" && <Loading text="Ищу в Open Library…" />}
      {Array.isArray(results.value) && (
        <ul class="tmdb-hits">
          {results.value.length === 0 && (
            <li class="muted">Ничего не нашлось. Попробуйте другое написание или введите книгу вручную.</li>
          )}
          {results.value.map((d) => (
            <li class="tmdb-hit" key={d.key}>
              <Cover book={{ cover_id: d.cover_i ?? null, title: d.title, author: d.author_name?.[0] ?? null }} size="S" />
              <div>
                <p class="ft">
                  {d.title}
                  {d.first_publish_year && <span class="muted">, {d.first_publish_year}</span>}
                </p>
                {d.author_name && <p class="muted">{d.author_name.slice(0, 2).join(", ")}</p>}
                <p class="tmdb-actions">
                  <button
                    type="button"
                    class="link"
                    onClick={() =>
                      add({
                        title: d.title,
                        author: d.author_name?.[0] ?? null,
                        year: d.first_publish_year ?? null,
                        ol_work: d.key.replace("/works/", ""),
                        cover_id: d.cover_i ?? null,
                      })
                    }
                  >
                    В очередь чтения
                  </button>
                  {d.edition_count && <span class="muted">{d.edition_count} изд.</span>}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
