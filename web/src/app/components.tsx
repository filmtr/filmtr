import { useSignal } from "@preact/signals";
import { useLocation } from "preact-iso";
import { useEffect, useRef } from "preact/hooks";
import {
  SUGGESTED_TAGS,
  allTags,
  entries,
  entryOf,
  films,
  myLists,
  removeEntry,
  saveEntry,
  toast,
  toasts,
  type Entry,
} from "./data";
import { KIND_RU, poster, tagHue } from "./util";

export function Header() {
  const { path, query, route } = useLocation();
  const q = useSignal(path === "/search" ? (query.q ?? "") : "");
  return (
    <header class="top">
      <a class="brand" href="/">
        filmtr
      </a>
      <nav>
        <a href="/" class={path === "/" ? "on" : ""}>
          Мои списки
        </a>
        <a href="/catalog" class={path === "/catalog" ? "on" : ""}>
          Каталог
        </a>
      </nav>
      <form
        class="search"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.value.trim()) route(`/search?q=${encodeURIComponent(q.value.trim())}`);
        }}
      >
        <input
          type="search"
          placeholder="Найти фильм или режиссёра"
          aria-label="Найти фильм или режиссёра"
          value={q.value}
          onInput={(e) => (q.value = e.currentTarget.value)}
        />
      </form>
    </header>
  );
}

export function Poster(props: { path?: string | null; title: string; size?: "w92" | "w185" | "w342" | "w500" }) {
  const src = poster(props.path, props.size);
  return src ? (
    <img class="poster" src={src} alt="" loading="lazy" decoding="async" />
  ) : (
    <div class="poster none" aria-hidden="true">
      <span>{props.title}</span>
    </div>
  );
}

export function Tag(props: { tag: string; on?: boolean; onClick?: () => void; title?: string }) {
  const style = { "--h": tagHue(props.tag) } as Record<string, number>;
  const cls = `tag${props.on ? " on" : ""}`;
  return props.onClick ? (
    <button type="button" class={cls} style={style} onClick={props.onClick} aria-pressed={props.on} title={props.title}>
      {props.tag}
    </button>
  ) : (
    <span class={cls} style={style}>
      {props.tag}
    </span>
  );
}

/** A poster card linking to the film page; personal tags and note when given. */
export function FilmCard(props: { id: string; entry?: Entry; showNote?: boolean }) {
  const f = films.value?.get(props.id);
  const title = f?.t ?? props.entry?.title ?? props.id;
  const year = f?.y ?? props.entry?.year;
  return (
    <a class="card" href={`/film/${props.id}`}>
      <Poster path={f?.p ?? props.entry?.poster_path} title={title} />
      <span class="card-title">{title}</span>
      <span class="card-sub">
        {[year, f?.d?.[0], f?.k ? KIND_RU[f.k] : null].filter(Boolean).join(", ")}
      </span>
      {props.entry && props.entry.tags.length > 0 && (
        <span class="card-tags">
          {props.entry.tags.map((t) => (
            <Tag tag={t} key={t} />
          ))}
        </span>
      )}
      {props.showNote && props.entry?.note && <span class="card-note">{props.entry.note}</span>}
    </a>
  );
}

type Snapshot = { title: string; year: number | null; poster_path: string | null };

/** Add to / remove from personal lists, edit tags and note. */
export function MyControls(props: { filmId: string; snapshot: Snapshot }) {
  entries.value; // re-render on changes
  return (
    <section class="mine" aria-label="Мои списки">
      {myLists.value.map((l) => (
        <MyListControl key={l.id} listId={l.id} title={l.title} {...props} />
      ))}
    </section>
  );
}

function MyListControl(props: { listId: string; title: string; filmId: string; snapshot: Snapshot }) {
  const e = entryOf(props.listId, props.filmId);
  const { listId, filmId } = props;
  if (!e) {
    return (
      <div class="mine-row">
        <button type="button" class="btn" onClick={() => saveEntry(listId, filmId, { ...props.snapshot })}>
          Добавить в «{props.title}»
        </button>
      </div>
    );
  }
  return (
    <div class="mine-row in">
      <div class="mine-head">
        <span class="mine-list">В списке «{props.title}»</span>
        {listId === "watchlist" && (
          <>
            <button type="button" class="link" onClick={() => saveEntry(listId, filmId, { position: "top" })}>
              Поднять наверх
            </button>
            <button
              type="button"
              class="link"
              onClick={() => {
                const saved = e;
                removeEntry(listId, filmId);
                toast(`«${props.snapshot.title}» убран из очереди`, () =>
                  saveEntry(listId, filmId, { ...props.snapshot, tags: saved.tags, note: saved.note ?? undefined }),
                );
              }}
            >
              Посмотрел
            </button>
          </>
        )}
        <button
          type="button"
          class="link quiet"
          onClick={() => {
            const saved = e;
            removeEntry(listId, filmId);
            toast(`Убрано из «${props.title}»`, () =>
              saveEntry(listId, filmId, { ...props.snapshot, tags: saved.tags, note: saved.note ?? undefined }),
            );
          }}
        >
          Убрать
        </button>
      </div>
      <TagEditor tags={e.tags} onChange={(tags) => saveEntry(listId, filmId, { tags })} />
      <NoteEditor note={e.note} onSave={(note) => saveEntry(listId, filmId, { note })} />
    </div>
  );
}

function TagEditor(props: { tags: string[]; onChange: (tags: string[]) => void }) {
  const draft = useSignal("");
  const add = (t: string) => {
    const tag = t.trim().toLowerCase();
    if (tag && !props.tags.includes(tag)) props.onChange([...props.tags, tag]);
    draft.value = "";
  };
  const suggestions = [...new Set([...allTags.value, ...SUGGESTED_TAGS])].filter((t) => !props.tags.includes(t));
  return (
    <div class="tag-editor">
      <div class="tag-row">
        {props.tags.map((t) => (
          <Tag key={t} tag={t} on onClick={() => props.onChange(props.tags.filter((x) => x !== t))} title="Снять тег" />
        ))}
        <input
          class="tag-input"
          placeholder={props.tags.length ? "ещё тег" : "добавить тег"}
          aria-label="Новый тег"
          value={draft.value}
          onInput={(ev) => (draft.value = ev.currentTarget.value)}
          onKeyDown={(ev) => {
            if (ev.key === "Enter" || ev.key === ",") {
              ev.preventDefault();
              add(draft.value);
            }
          }}
          onBlur={() => draft.value && add(draft.value)}
        />
      </div>
      {suggestions.length > 0 && (
        <div class="tag-row suggest">
          {suggestions.slice(0, 8).map((t) => (
            <Tag key={t} tag={t} onClick={() => add(t)} title="Добавить тег" />
          ))}
        </div>
      )}
    </div>
  );
}

function NoteEditor(props: { note: string | null; onSave: (note: string) => void }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (ref.current && document.activeElement !== ref.current) ref.current.value = props.note ?? "";
  }, [props.note]);
  return (
    <textarea
      ref={ref}
      class="note"
      rows={2}
      placeholder="Заметка: с кем смотреть, почему хочется, что запомнилось"
      aria-label="Заметка"
      onBlur={(ev) => {
        const v = ev.currentTarget.value.trim();
        if (v !== (props.note ?? "")) props.onSave(v);
      }}
    />
  );
}

export function Toasts() {
  return (
    <div class="toasts" role="status" aria-live="polite">
      {toasts.value.map((t) => (
        <div class="toast" key={t.id}>
          <span>{t.text}</span>
          {t.undo && (
            <button
              type="button"
              class="link"
              onClick={() => {
                t.undo!();
                toasts.value = toasts.value.filter((x) => x.id !== t.id);
              }}
            >
              Вернуть
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

export function Loading(props: { text?: string }) {
  return <p class="muted pad">{props.text ?? "Загружаю…"}</p>;
}
