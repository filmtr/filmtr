import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import { Loading, Poster } from "../components";
import { entries, films, lists, meta, personDetail, type PersonDetail } from "../data";
import { KIND_RU, poster } from "../util";

export function PersonPage(props: { id: string }) {
  const detail = useSignal<PersonDetail | null | undefined>(undefined);
  const onlyCatalog = useSignal(false);
  useEffect(() => {
    detail.value = undefined;
    personDetail(props.id)
      .then((d) => (detail.value = d))
      .catch(() => (detail.value = null));
    scrollTo(0, 0);
  }, [props.id]);

  const d = detail.value;
  if (d === undefined) return <Loading />;
  if (d === null) return <p class="pad">Этого человека нет в каталоге.</p>;

  const name = d.name_ru ?? d.name;
  const roles = meta.value?.roles ?? {};
  const mine = new Set(entries.value.map((e) => e.film_id));
  const byRole = new Map<string, [string, string | null][]>();
  for (const [f, role, detail] of d.credits) byRole.set(role, [...(byRole.get(role) ?? []), [f, detail]]);
  // The role with the most catalog films comes first: Tarkovsky is a director first.
  const weight = (r: string) =>
    byRole.get(r)!.filter(([f]) => films.value?.get(f)?.c).length * 100 + byRole.get(r)!.length;
  const order = [...byRole.keys()].sort((a, b) => weight(b) - weight(a));
  const inCatalog = d.credits.filter(([f]) => films.value?.get(f)?.c).length;
  const years = [d.birth, d.death].filter(Boolean).join("–");
  const listTitle = (id: string) => lists.value?.find((l) => l.id === id)?.title_ru ?? id;

  return (
    <main class="person">
      <div class="person-head">
        {d.photo ? (
          <img class="photo" src={poster(d.photo, "w185")!} alt="" />
        ) : (
          <div class="photo none" aria-hidden="true" />
        )}
        <div>
          <h1 class="film-title">{name}</h1>
          {d.name_ru && d.name_ru !== d.name && <p class="original">{d.name}</p>}
          {years && <p class="facts">{years}</p>}
          {d.lists.length > 0 && (
            <ul class="honours">
              {d.lists.map(([id, pos]) => (
                <li key={id}>
                  {listTitle(id)}, место {pos}
                </li>
              ))}
            </ul>
          )}
          <label class="check">
            <input
              type="checkbox"
              checked={onlyCatalog.value}
              onChange={(e) => (onlyCatalog.value = e.currentTarget.checked)}
            />
            Только фильмы из каталога ({inCatalog})
          </label>
        </div>
      </div>

      {order.map((role) => {
        const items = byRole
          .get(role)!
          .filter(([f]) => !onlyCatalog.value || films.value?.get(f)?.c)
          .sort((a, b) => (films.value?.get(b[0])?.y ?? 0) - (films.value?.get(a[0])?.y ?? 0));
        if (!items.length) return null;
        return (
          <section class="filmography" key={role}>
            <h2>
              {roles[role]?.[0] ?? role} <span class="muted">{items.length}</span>
            </h2>
            <ul>
              {items.map(([f, detail]) => {
                const row = films.value?.get(f);
                return (
                  <li key={f} class={row?.c ? "in-catalog" : ""}>
                    <a href={`/film/${f}`}>
                      <Poster path={row?.p} title={row?.t ?? f} size="w92" />
                      <span class="fy">{row?.y ?? ""}</span>
                      <span class="ft">
                        {row?.t ?? f}
                        {row?.k && <span class="muted">, {KIND_RU[row.k]}</span>}
                        {detail && role === "actor" && <span class="muted"> {detail}</span>}
                      </span>
                      {mine.has(f) && <span class="mark" title="В моих списках" aria-label="В моих списках" />}
                    </a>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </main>
  );
}
