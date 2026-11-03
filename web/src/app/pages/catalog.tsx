import { useSignal } from "@preact/signals";
import { useLocation } from "preact-iso";
import { FilmCard, Loading } from "../components";
import { films, lists, meta, type FilmRow } from "../data";
import { plural } from "../util";

const PAGE = 60;

const SORTS: Record<string, [string, (a: FilmRow, b: FilmRow) => number]> = {
  rating: ["По рейтингу IMDb", (a, b) => (b.r ?? 0) - (a.r ?? 0)],
  votes: ["По известности", (a, b) => (b.v ?? 0) - (a.v ?? 0)],
  new: ["Сначала новые", (a, b) => (b.y ?? 0) - (a.y ?? 0)],
  old: ["Сначала старые", (a, b) => (a.y ?? 0) - (b.y ?? 0)],
};

export function CatalogPage() {
  const { query, route } = useLocation();
  const limit = useSignal(PAGE);
  if (!films.value || !meta.value || !lists.value) return <Loading text="Загружаю каталог…" />;

  const set = (patch: Record<string, string | null>) => {
    limit.value = PAGE;
    const next = { ...query, ...patch };
    const qs = Object.entries(next)
      .filter(([, v]) => v)
      .map(([k, v]) => `${k}=${encodeURIComponent(v as string)}`)
      .join("&");
    route(qs ? `/catalog?${qs}` : "/catalog", true);
  };

  const catalog = [...films.value.values()].filter((f) => f.c);
  const countryCounts = new Map<string, number>();
  for (const f of catalog) for (const c of f.n ?? []) countryCounts.set(c, (countryCounts.get(c) ?? 0) + 1);
  const filmLists = lists.value.filter((l) => l.entity === "film");

  const shown = catalog
    .filter(
      (f) =>
        (!query.list || f.l?.includes(query.list)) &&
        (!query.genre || f.g?.includes(query.genre)) &&
        (!query.country || f.n?.includes(query.country)) &&
        (!query.decade || (f.y && Math.floor(f.y / 10) * 10 === Number(query.decade))),
    )
    .sort(SORTS[query.sort ?? "rating"]?.[1] ?? SORTS.rating[1]);

  const decades = [...new Set(catalog.map((f) => (f.y ? Math.floor(f.y / 10) * 10 : 0)).filter(Boolean))].sort(
    (a, b) => b - a,
  );

  return (
    <main class="catalog">
      <h1 class="page-title">Каталог</h1>
      <p class="muted lede">
        Фильмы из опросов критиков, фестивальных наград и самых значимых по IMDb. Фильмографии их создателей
        открываются на страницах людей.
      </p>
      <div class="filters">
        <select aria-label="Список" value={query.list ?? ""} onChange={(e) => set({ list: e.currentTarget.value || null })}>
          <option value="">Все списки</option>
          {filmLists.map((l) => (
            <option value={l.id}>{l.title_ru}</option>
          ))}
        </select>
        <select aria-label="Жанр" value={query.genre ?? ""} onChange={(e) => set({ genre: e.currentTarget.value || null })}>
          <option value="">Любой жанр</option>
          {Object.entries(meta.value.genres)
            .sort((a, b) => a[1].localeCompare(b[1], "ru"))
            .map(([g, ru]) => (
              <option value={g}>{ru}</option>
            ))}
        </select>
        <select
          aria-label="Страна"
          value={query.country ?? ""}
          onChange={(e) => set({ country: e.currentTarget.value || null })}
        >
          <option value="">Любая страна</option>
          {[...countryCounts.entries()]
            .sort((a, b) => b[1] - a[1])
            .slice(0, 40)
            .map(([c]) => (
              <option value={c}>{meta.value!.countries[c] ?? c}</option>
            ))}
        </select>
        <select
          aria-label="Десятилетие"
          value={query.decade ?? ""}
          onChange={(e) => set({ decade: e.currentTarget.value || null })}
        >
          <option value="">Любые годы</option>
          {decades.map((d) => (
            <option value={d}>{d}-е</option>
          ))}
        </select>
        <select aria-label="Порядок" value={query.sort ?? "rating"} onChange={(e) => set({ sort: e.currentTarget.value })}>
          {Object.entries(SORTS).map(([k, [label]]) => (
            <option value={k}>{label}</option>
          ))}
        </select>
      </div>
      <p class="muted">
        {shown.length} {plural(shown.length, "фильм", "фильма", "фильмов")}
      </p>
      <div class="grid">
        {shown.slice(0, limit.value).map((f) => (
          <FilmCard key={f.i} id={f.i} />
        ))}
      </div>
      {shown.length > limit.value && (
        <button type="button" class="btn more" onClick={() => (limit.value += PAGE)}>
          Показать ещё
        </button>
      )}
    </main>
  );
}
