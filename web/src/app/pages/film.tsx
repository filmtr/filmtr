import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import { Loading, MyControls, Poster } from "../components";
import { entries, filmDetail, films, lists, meta, type Credit, type FilmDetail } from "../data";
import { KIND_RU, runtime } from "../util";

const CAST_SHOWN = 12;

export function FilmPage(props: { id: string }) {
  const detail = useSignal<FilmDetail | null | undefined>(undefined);
  const allCast = useSignal(false);
  useEffect(() => {
    detail.value = undefined;
    allCast.value = false;
    filmDetail(props.id)
      .then((d) => (detail.value = d))
      .catch(() => (detail.value = null));
    scrollTo(0, 0);
  }, [props.id]);

  const d = detail.value;
  const row = films.value?.get(props.id);
  const mine = entries.value.find((e) => e.film_id === props.id);
  if (d === undefined) return <Loading />;

  if (d === null) {
    // Added from TMDB, not yet in the static catalog.
    const title = row?.t ?? mine?.title ?? props.id;
    return (
      <main class="film">
        <div class="film-head">
          <Poster path={row?.p ?? mine?.poster_path} title={title} size="w500" />
          <div>
            <h1 class="film-title">{title}</h1>
            <p class="muted">{row?.y ?? mine?.year}</p>
            <MyControls
              filmId={props.id}
              snapshot={{ title, year: row?.y ?? mine?.year ?? null, poster_path: row?.p ?? mine?.poster_path ?? null }}
            />
            <p class="muted">
              Подробностей об этом фильме пока нет в каталоге. Они появятся после следующего обновления данных.
            </p>
            <ExternalLinks id={props.id} />
          </div>
        </div>
      </main>
    );
  }

  const title = d.title_ru ?? d.title;
  const originals = [d.title, d.original_title].filter((t, i, a) => t && t !== title && a.indexOf(t) === i);
  const facts = [
    d.kind !== "movie" ? KIND_RU[d.kind] : null,
    d.end_year && d.end_year !== d.year ? `${d.year}–${d.end_year}` : d.year,
    runtime(d.runtime),
    d.countries.map((c) => meta.value?.countries[c] ?? c).join(", "),
  ].filter(Boolean);

  const roles = meta.value?.roles ?? {};
  const byRole = new Map<string, Credit[]>();
  for (const c of d.credits) byRole.set(c[2], [...(byRole.get(c[2]) ?? []), c]);
  const crewRoles = [...byRole.keys()].filter((r) => r !== "actor" && r !== "self").sort((a, b) => (roles[a]?.[1] ?? 99) - (roles[b]?.[1] ?? 99));
  const cast = [...(byRole.get("actor") ?? []), ...(byRole.get("self") ?? [])];
  const listTitle = (id: string) => lists.value?.find((l) => l.id === id)?.title_ru ?? id;
  // Critics' polls first, then awards, the computed IMDb core last.
  const kindOrder = { poll: 0, award: 1, computed: 2 } as Record<string, number>;
  const kindOf = (id: string) => kindOrder[lists.value?.find((l) => l.id === id)?.kind ?? "computed"];
  const honours = [...d.lists].sort((a, b) => kindOf(a[0]) - kindOf(b[0]));

  return (
    <main class="film">
      <div class="film-head">
        <Poster path={d.poster} title={title} size="w500" />
        <div class="film-info">
          <h1 class="film-title">{title}</h1>
          {originals.length > 0 && <p class="original">{originals.join(" / ")}</p>}
          <p class="facts">{facts.join(", ")}</p>
          {d.genres.length > 0 && (
            <p class="genres">{d.genres.map((g) => meta.value?.genres[g] ?? g).join(", ")}</p>
          )}
          <p class="ratings">
            {d.ratings.imdb && (
              <span>
                IMDb <b>{d.ratings.imdb[0].toFixed(1)}</b>
              </span>
            )}
            {d.ratings.tmdb && (
              <span>
                TMDB <b>{d.ratings.tmdb[0].toFixed(1)}</b>
              </span>
            )}
          </p>
          {honours.length > 0 && (
            <ul class="honours">
              {honours.map(([id, pos, year]) => (
                <li key={id}>
                  {listTitle(id)}
                  {year ? `, ${year}` : pos ? `, место ${pos}` : ""}
                </li>
              ))}
            </ul>
          )}
          {d.tagline && <p class="tagline">{d.tagline}</p>}
          {d.overview && <p class="overview">{d.overview}</p>}
          <MyControls filmId={props.id} snapshot={{ title, year: d.year, poster_path: d.poster }} />
        </div>
      </div>

      {crewRoles.length > 0 && (
        <section class="crew">
          <h2>Создатели</h2>
          <dl>
            {crewRoles.map((r) => (
              <div class="crew-row" key={r}>
                <dt>{roles[r]?.[0] ?? r}</dt>
                <dd>
                  {byRole.get(r)!.map(([pid, name, , detail], i) => (
                    <span key={pid}>
                      {i > 0 && ", "}
                      <a href={`/person/${pid}`}>{name}</a>
                      {detail && r === "writer" && <span class="muted"> ({writerJob(detail)})</span>}
                    </span>
                  ))}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {cast.length > 0 && (
        <section class="cast">
          <h2>В ролях</h2>
          <ul>
            {(allCast.value ? cast : cast.slice(0, CAST_SHOWN)).map(([pid, name, role, detail]) => (
              <li key={pid + role}>
                <a href={`/person/${pid}`}>{name}</a>
                {detail && <span class="muted">{role === "self" ? " (в роли себя)" : ` ${detail}`}</span>}
              </li>
            ))}
          </ul>
          {cast.length > CAST_SHOWN && !allCast.value && (
            <button type="button" class="link" onClick={() => (allCast.value = true)}>
              Показать всех ({cast.length})
            </button>
          )}
        </section>
      )}

      <ExternalLinks id={props.id} ids={d.ids} />
    </main>
  );
}

const WRITER_JOBS: Record<string, string> = {
  screenplay: "сценарий",
  novel: "роман",
  story: "сюжет",
  author: "автор",
  teleplay: "телесценарий",
};

function writerJob(detail: string): string {
  const key = detail.split(" ")[0].toLowerCase();
  return WRITER_JOBS[key] ?? detail;
}

function ExternalLinks(props: { id: string; ids?: FilmDetail["ids"] }) {
  const ids = props.ids;
  return (
    <p class="external">
      <a href={`https://www.imdb.com/title/${props.id}/`} target="_blank" rel="noreferrer">
        IMDb
      </a>
      {ids?.kinopoisk && (
        <a href={`https://www.kinopoisk.ru/film/${ids.kinopoisk}/`} target="_blank" rel="noreferrer">
          Кинопоиск
        </a>
      )}
      {ids?.letterboxd && (
        <a href={`https://letterboxd.com/film/${ids.letterboxd}/`} target="_blank" rel="noreferrer">
          Letterboxd
        </a>
      )}
      {ids?.tmdb && (
        <a href={`https://www.themoviedb.org/${ids.tmdb_type ?? "movie"}/${ids.tmdb}`} target="_blank" rel="noreferrer">
          TMDB
        </a>
      )}
      {ids?.wikidata && (
        <a href={`https://www.wikidata.org/wiki/${ids.wikidata}`} target="_blank" rel="noreferrer">
          Wikidata
        </a>
      )}
    </p>
  );
}
