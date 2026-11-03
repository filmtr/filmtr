import { useSignal } from "@preact/signals";
import { useLocation } from "preact-iso";
import { useEffect } from "preact/hooks";
import { FilmCard, Loading, Poster, Tag } from "../components";
import { entries, filmDetail, films, meta, myError, myLists, myStatus, type Entry, type FilmDetail } from "../data";
import { norm, plural, runtime } from "../util";

const LENGTHS: Record<string, [string, (m: number) => boolean]> = {
  short: ["До 1:45", (m) => m <= 105],
  mid: ["1:45–2:30", (m) => m > 105 && m <= 150],
  long: ["Длиннее 2:30", (m) => m > 150],
};

const SORTS: Record<string, string> = {
  list: "Как в списке",
  added: "Недавно добавленные",
  year: "Сначала новые",
  old: "Сначала старые",
  rating: "По рейтингу IMDb",
};

export function ListsPage() {
  const { query, route } = useLocation();
  const listId = query.list || myLists.value[0]?.id || "watchlist";
  const picked = useSignal<string | null>(null);

  if (myStatus.value === "loading") return <Loading text="Загружаю списки…" />;
  if (myStatus.value === "error")
    return (
      <p class="pad error">
        Списки не загрузились: {myError.value}. Проверьте вход через Cloudflare Access и обновите страницу.
      </p>
    );

  const set = (patch: Record<string, string | null>) => {
    const next = { ...query, ...patch };
    const qs = Object.entries(next)
      .filter(([, v]) => v)
      .map(([k, v]) => `${k}=${encodeURIComponent(v as string)}`)
      .join("&");
    route(qs ? `/?${qs}` : "/", true);
  };

  const inList = entries.value.filter((e) => e.list_id === listId);
  const row = (e: Entry) => films.value?.get(e.film_id);
  const selectedTags = query.tags ? query.tags.split(",") : [];

  // Facets come from what is in the current list, so every option finds something.
  const tagCounts = new Map<string, number>();
  for (const e of inList) for (const t of e.tags) tagCounts.set(t, (tagCounts.get(t) ?? 0) + 1);
  const genreCounts = new Map<string, number>();
  const decades = new Set<number>();
  for (const e of inList) {
    for (const g of row(e)?.g ?? []) genreCounts.set(g, (genreCounts.get(g) ?? 0) + 1);
    const y = row(e)?.y ?? e.year;
    if (y) decades.add(Math.floor(y / 10) * 10);
  }

  let shown = inList.filter((e) => {
    const f = row(e);
    if (selectedTags.length && !selectedTags.every((t) => e.tags.includes(t))) return false;
    if (query.genre && !f?.g?.includes(query.genre)) return false;
    if (query.len && !(f?.m && LENGTHS[query.len]?.[1](f.m))) return false;
    if (query.decade) {
      const y = f?.y ?? e.year;
      if (!y || Math.floor(y / 10) * 10 !== Number(query.decade)) return false;
    }
    if (query.q) {
      const hay = norm(`${f?.t ?? e.title ?? ""} ${f?.o ?? ""} ${(f?.d ?? []).join(" ")} ${e.note ?? ""}`);
      if (!norm(query.q).split(" ").every((w) => hay.includes(w))) return false;
    }
    return true;
  });
  const sort = query.sort || "list";
  const year = (e: Entry) => row(e)?.y ?? e.year ?? 0;
  shown = [...shown].sort(
    {
      list: (a: Entry, b: Entry) => a.pos - b.pos,
      added: (a: Entry, b: Entry) => b.added_at.localeCompare(a.added_at),
      year: (a: Entry, b: Entry) => year(b) - year(a),
      old: (a: Entry, b: Entry) => year(a) - year(b),
      rating: (a: Entry, b: Entry) => (row(b)?.r ?? 0) - (row(a)?.r ?? 0),
    }[sort] ?? ((a: Entry, b: Entry) => a.pos - b.pos),
  );
  const filtered = selectedTags.length || query.genre || query.len || query.decade || query.q;

  const pick = () => {
    const pool = shown.filter((e) => e.film_id !== picked.value);
    const from = pool.length ? pool : shown;
    picked.value = from[Math.floor(Math.random() * from.length)]?.film_id ?? null;
  };

  return (
    <main class="lists">
      <div class="list-switch" role="tablist">
        {myLists.value.map((l) => {
          const n = entries.value.filter((e) => e.list_id === l.id).length;
          return (
            <button
              type="button"
              role="tab"
              aria-selected={l.id === listId}
              class={l.id === listId ? "on" : ""}
              onClick={() => set({ list: l.id, tags: null, genre: null, len: null, decade: null, q: null })}
            >
              {l.title}
              <span class="count">{n}</span>
            </button>
          );
        })}
      </div>

      {inList.length === 0 ? (
        <p class="empty">
          Здесь пока пусто. Найдите фильм через поиск сверху и добавьте его на странице фильма.
        </p>
      ) : (
        <>
          <div class="moods">
            {tagCounts.size > 0 && (
              <div class="tag-row" aria-label="Теги">
                {[...tagCounts.entries()]
                  .sort((a, b) => b[1] - a[1])
                  .map(([t]) => (
                    <Tag
                      key={t}
                      tag={t}
                      on={selectedTags.includes(t)}
                      onClick={() => {
                        const next = selectedTags.includes(t)
                          ? selectedTags.filter((x) => x !== t)
                          : [...selectedTags, t];
                        set({ tags: next.join(",") || null });
                      }}
                    />
                  ))}
              </div>
            )}
            <div class="filters">
              <select
                aria-label="Жанр"
                value={query.genre ?? ""}
                onChange={(e) => set({ genre: e.currentTarget.value || null })}
              >
                <option value="">Любой жанр</option>
                {[...genreCounts.entries()]
                  .sort((a, b) => b[1] - a[1])
                  .map(([g]) => (
                    <option value={g}>{meta.value?.genres[g] ?? g}</option>
                  ))}
              </select>
              <select
                aria-label="Длительность"
                value={query.len ?? ""}
                onChange={(e) => set({ len: e.currentTarget.value || null })}
              >
                <option value="">Любая длина</option>
                {Object.entries(LENGTHS).map(([k, [label]]) => (
                  <option value={k}>{label}</option>
                ))}
              </select>
              <select
                aria-label="Десятилетие"
                value={query.decade ?? ""}
                onChange={(e) => set({ decade: e.currentTarget.value || null })}
              >
                <option value="">Любые годы</option>
                {[...decades]
                  .sort((a, b) => b - a)
                  .map((d) => (
                    <option value={d}>{d}-е</option>
                  ))}
              </select>
              <select aria-label="Порядок" value={sort} onChange={(e) => set({ sort: e.currentTarget.value })}>
                {Object.entries(SORTS).map(([k, label]) => (
                  <option value={k}>{label}</option>
                ))}
              </select>
              <input
                type="search"
                class="filter-q"
                placeholder="Название, режиссёр, заметка"
                aria-label="Фильтр по тексту"
                value={query.q ?? ""}
                onInput={(e) => set({ q: e.currentTarget.value || null })}
              />
            </div>
            <div class="pick-bar">
              <button type="button" class="pick" onClick={pick} disabled={!shown.length}>
                Выбрать за меня
              </button>
              <span class="muted">
                {shown.length} {plural(shown.length, "фильм", "фильма", "фильмов")}
                {filtered ? ` из ${inList.length}` : ""}
              </span>
              {filtered && (
                <button
                  type="button"
                  class="link"
                  onClick={() => set({ tags: null, genre: null, len: null, decade: null, q: null })}
                >
                  Сбросить фильтры
                </button>
              )}
            </div>
          </div>

          {shown.length === 0 ? (
            <p class="empty">Под эти фильтры ничего не подходит. Снимите какой-нибудь тег или фильтр.</p>
          ) : (
            <div class="grid">
              {shown.map((e) => (
                <FilmCard key={e.film_id} id={e.film_id} entry={e} showNote />
              ))}
            </div>
          )}
        </>
      )}

      {picked.value && (
        <Picked id={picked.value} listId={listId} onClose={() => (picked.value = null)} onAgain={pick} />
      )}
    </main>
  );
}

/** The chosen film, large: the one place where the page raises its voice. */
function Picked(props: { id: string; listId: string; onClose: () => void; onAgain: () => void }) {
  const detail = useSignal<FilmDetail | null>(null);
  useEffect(() => {
    detail.value = null;
    filmDetail(props.id).then((d) => (detail.value = d));
  }, [props.id]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && props.onClose();
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, []);
  const f = films.value?.get(props.id);
  const e = entries.value.find((x) => x.film_id === props.id && x.list_id === props.listId);
  const d = detail.value;
  const title = f?.t ?? e?.title ?? props.id;
  return (
    <div class="picked-backdrop" onClick={props.onClose}>
      <div class="picked" role="dialog" aria-modal="true" aria-label={`Выбор: ${title}`} onClick={(ev) => ev.stopPropagation()}>
        <Poster path={f?.p ?? e?.poster_path} title={title} size="w500" />
        <div class="picked-body">
          <h2 class="film-title">{title}</h2>
          <p class="muted">
            {[f?.y ?? e?.year, f?.d?.join(", "), runtime(f?.m ?? d?.runtime)].filter(Boolean).join(", ")}
          </p>
          {e && e.tags.length > 0 && (
            <div class="tag-row">
              {e.tags.map((t) => (
                <Tag key={t} tag={t} />
              ))}
            </div>
          )}
          {e?.note && <p class="picked-note">{e.note}</p>}
          {d?.overview && <p class="overview">{d.overview}</p>}
          <div class="picked-actions">
            <a class="btn primary" href={`/film/${props.id}`}>
              Открыть фильм
            </a>
            <button type="button" class="btn" onClick={props.onAgain}>
              Другой
            </button>
            <button type="button" class="link quiet" onClick={props.onClose}>
              Закрыть
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

