import { useSignal } from "@preact/signals";
import { useLocation } from "preact-iso";
import { useEffect } from "preact/hooks";
import { FilmCard, Loading, Poster } from "../components";
import { entryOf, errorText, films, myLists, saveEntry, toast } from "../data";
import { searchFilms } from "../util";

type TmdbHit = {
  tmdb_type: "movie" | "tv";
  tmdb_id: number;
  title: string;
  original_title: string;
  year: number | null;
  poster_path: string | null;
  overview: string;
};

export function SearchPage() {
  const { query } = useLocation();
  const q = query.q ?? "";
  const tmdb = useSignal<TmdbHit[] | "loading" | null>(null);
  useEffect(() => {
    tmdb.value = null;
  }, [q]);
  if (!films.value) return <Loading text="Загружаю каталог…" />;

  const hits = searchFilms(films.value.values(), q);
  const searchTmdb = async () => {
    tmdb.value = "loading";
    try {
      const r = await fetch(`/api/tmdb/search?q=${encodeURIComponent(q)}`);
      if (!r.ok) throw new Error(await errorText(r));
      tmdb.value = ((await r.json()) as { results: TmdbHit[] }).results;
    } catch (e) {
      tmdb.value = null;
      toast(`Поиск в TMDB не удался: ${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <main class="search-page">
      <h1 class="page-title">Поиск: {q}</h1>
      {hits.length === 0 ? (
        <p class="muted">В базе ничего не нашлось. Попробуйте другое написание или поищите в TMDB.</p>
      ) : (
        <div class="grid">
          {hits.map((f) => (
            <FilmCard key={f.i} id={f.i} />
          ))}
        </div>
      )}

      <section class="tmdb">
        {tmdb.value === null && (
          <button type="button" class="btn" onClick={searchTmdb}>
            Нет нужного? Искать в TMDB
          </button>
        )}
        {tmdb.value === "loading" && <Loading text="Ищу в TMDB…" />}
        {Array.isArray(tmdb.value) && (
          <>
            <h2>В TMDB</h2>
            {tmdb.value.length === 0 && <p class="muted">И в TMDB ничего не нашлось.</p>}
            <ul class="tmdb-hits">
              {tmdb.value.map((h) => (
                <TmdbRow key={`${h.tmdb_type}${h.tmdb_id}`} hit={h} />
              ))}
            </ul>
          </>
        )}
      </section>
    </main>
  );
}

function TmdbRow(props: { hit: TmdbHit }) {
  const h = props.hit;
  const imdb = useSignal<string | null>(null);
  const resolve = async (): Promise<string | null> => {
    if (imdb.value) return imdb.value;
    const r = await fetch(`/api/tmdb/imdb/${h.tmdb_type}/${h.tmdb_id}`);
    const id = r.ok ? ((await r.json()) as { imdb_id: string | null }).imdb_id : null;
    if (!id) toast("У этого фильма в TMDB нет ID IMDb, добавить его нельзя.");
    imdb.value = id;
    return id;
  };
  const add = async (listId: string, title: string) => {
    const id = await resolve();
    if (!id) return;
    await saveEntry(listId, id, { title: h.title, year: h.year, poster_path: h.poster_path });
    toast(`«${h.title}» добавлен в «${title}»`);
  };
  const known = imdb.value && films.value?.get(imdb.value);
  return (
    <li class="tmdb-hit">
      <Poster path={h.poster_path} title={h.title} size="w92" />
      <div>
        <p class="ft">
          {known ? <a href={`/film/${imdb.value}`}>{h.title}</a> : h.title}
          {h.year && <span class="muted">, {h.year}</span>}
          {h.tmdb_type === "tv" && <span class="muted">, сериал</span>}
        </p>
        {h.original_title !== h.title && <p class="muted">{h.original_title}</p>}
        <p class="tmdb-actions">
          {myLists.value.map((l) =>
            imdb.value && entryOf(l.id, imdb.value) ? (
              <span class="muted" key={l.id}>
                Уже в «{l.title}»
              </span>
            ) : (
              <button type="button" class="link" key={l.id} onClick={() => add(l.id, l.title)}>
                В «{l.title}»
              </button>
            ),
          )}
        </p>
      </div>
    </li>
  );
}
