import { computed, signal } from "@preact/signals";

// --- Static catalog (built by `filmtr web export`) -------------------------

/** Compact film row from /data/films.json. */
export type FilmRow = {
  i: string; // IMDb id
  t: string; // title (Russian when known)
  o?: string; // IMDb primary title, when different
  y: number | null;
  k?: string; // kind, when not "movie"
  p?: string; // TMDB poster path
  d?: string[]; // directors
  c?: 1; // in the catalog (some best-of list)
  g?: string[]; // genres
  n?: string[]; // countries
  m?: number; // runtime, minutes
  r?: number; // IMDb rating
  v?: number; // IMDb votes
  l?: string[]; // lists
};

export type Meta = {
  genres: Record<string, string>;
  countries: Record<string, string>;
  roles: Record<string, [string, number]>;
};

export type ListMeta = {
  id: string;
  title: string;
  title_ru: string;
  kind: "poll" | "award" | "computed";
  entity: "film" | "person";
  url: string | null;
  edition: string | null;
  description: string | null;
  people?: [number, string, string][];
};

export type Credit = [personId: string, name: string, role: string, detail: string | null];

export type FilmDetail = {
  title: string;
  title_ru: string | null;
  original_title: string | null;
  kind: string;
  year: number | null;
  end_year: number | null;
  runtime: number | null;
  overview: string | null;
  tagline: string | null;
  language: string | null;
  poster: string | null;
  backdrop: string | null;
  genres: string[];
  countries: string[];
  ratings: { imdb?: [number, number]; tmdb?: [number, number] };
  ids: { wikidata: string | null; tmdb: number | null; tmdb_type: string | null; kinopoisk: number | null; letterboxd: string | null };
  lists: [listId: string, pos: number | null, year: number | null][];
  credits: Credit[];
};

export type PersonDetail = {
  name: string;
  name_ru: string | null;
  birth: number | null;
  death: number | null;
  photo: string | null;
  lists: [listId: string, pos: number][];
  credits: [filmId: string, role: string, detail: string | null][];
};

const cache = new Map<string, Promise<any>>();

function load<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(
      path,
      fetch(path).then((r) => {
        if (!r.ok) throw new Error(`${path}: ${r.status}`);
        return r.json();
      }),
    );
  }
  return cache.get(path)!;
}

export const films = signal<Map<string, FilmRow> | null>(null);
export const meta = signal<Meta | null>(null);
export const lists = signal<ListMeta[] | null>(null);

export function loadCatalog(): void {
  load<FilmRow[]>("/data/films.json").then((rows) => (films.value = new Map(rows.map((r) => [r.i, r]))));
  load<Meta>("/data/meta.json").then((m) => (meta.value = m));
  load<ListMeta[]>("/data/lists.json").then((l) => (lists.value = l));
}

const shard = (id: string) => id.slice(-2);

export async function filmDetail(id: string): Promise<FilmDetail | null> {
  const s = await load<Record<string, FilmDetail>>(`/data/film/${shard(id)}.json`);
  return s[id] ?? null;
}

export async function personDetail(id: string): Promise<PersonDetail | null> {
  const s = await load<Record<string, PersonDetail>>(`/data/person/${shard(id)}.json`);
  return s[id] ?? null;
}

// --- Personal lists (D1 via /api/my) ---------------------------------------

export type MyList = { id: string; title: string; description: string | null };

export type Entry = {
  list_id: string;
  film_id: string;
  pos: number;
  tags: string[];
  note: string | null;
  added_at: string;
  updated_at: string;
  title: string | null;
  year: number | null;
  poster_path: string | null;
};

export const myLists = signal<MyList[]>([]);
export const entries = signal<Entry[]>([]);
export const myStatus = signal<"loading" | "ready" | "error">("loading");
export const myError = signal<string | null>(null);

export const allTags = computed(() => {
  const counts = new Map<string, number>();
  for (const e of entries.value) for (const t of e.tags) counts.set(t, (counts.get(t) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "ru")).map(([t]) => t);
});

export const SUGGESTED_TAGS = ["пересмотреть", "с детьми", "лёгкое", "на вечер вдвоём", "под настроение"];

export async function loadMy(): Promise<void> {
  try {
    const r = await fetch("/api/my");
    if (!r.ok) throw new Error(await errorText(r));
    const data = (await r.json()) as { lists: MyList[]; entries: Entry[] };
    myLists.value = data.lists;
    entries.value = data.entries;
    myStatus.value = "ready";
  } catch (e) {
    myError.value = e instanceof Error ? e.message : String(e);
    myStatus.value = "error";
  }
}

export function entryOf(listId: string, filmId: string): Entry | undefined {
  return entries.value.find((e) => e.list_id === listId && e.film_id === filmId);
}

type Patch = Partial<Pick<Entry, "tags" | "note" | "title" | "year" | "poster_path">> & {
  position?: "top" | "bottom";
};

/** Add a film to a list or update its entry; the change shows at once. */
export async function saveEntry(listId: string, filmId: string, patch: Patch): Promise<void> {
  const before = entries.value;
  const current = entryOf(listId, filmId);
  const now = new Date().toISOString();
  const optimistic: Entry = {
    list_id: listId,
    film_id: filmId,
    pos: current?.pos ?? Number.MAX_SAFE_INTEGER,
    tags: current?.tags ?? [],
    note: current?.note ?? null,
    added_at: current?.added_at ?? now,
    updated_at: now,
    title: current?.title ?? null,
    year: current?.year ?? null,
    poster_path: current?.poster_path ?? null,
    ...stripUndefined(patch),
  };
  if (patch.position === "top") optimistic.pos = Number.MIN_SAFE_INTEGER;
  entries.value = [...before.filter((e) => e !== current), optimistic];
  try {
    const r = await fetch(`/api/my/${listId}/${filmId}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!r.ok) throw new Error(await errorText(r));
    const saved = (await r.json()) as Entry;
    entries.value = [...entries.value.filter((e) => !(e.list_id === listId && e.film_id === filmId)), saved];
  } catch (e) {
    entries.value = before;
    toast(`Не сохранилось: ${e instanceof Error ? e.message : e}`);
  }
}

export async function removeEntry(listId: string, filmId: string): Promise<void> {
  const before = entries.value;
  entries.value = before.filter((e) => !(e.list_id === listId && e.film_id === filmId));
  try {
    const r = await fetch(`/api/my/${listId}/${filmId}`, { method: "DELETE" });
    if (!r.ok) throw new Error(`Ошибка ${r.status}`);
  } catch (e) {
    entries.value = before;
    toast(`Не удалилось: ${e instanceof Error ? e.message : e}`);
  }
}

/** The API's error message, or the HTTP status. */
export async function errorText(r: Response): Promise<string> {
  const body = (await r.json().catch(() => null)) as { error?: string } | null;
  return body?.error ?? `Ошибка ${r.status}`;
}

function stripUndefined<T extends object>(o: T): Partial<T> {
  return Object.fromEntries(Object.entries(o).filter(([k, v]) => v !== undefined && k !== "position")) as Partial<T>;
}

// --- Toasts ---------------------------------------------------------------

export const toasts = signal<{ id: number; text: string; undo?: () => void }[]>([]);
let toastId = 0;

export function toast(text: string, undo?: () => void): void {
  const id = ++toastId;
  toasts.value = [...toasts.value, { id, text, undo }];
  setTimeout(() => (toasts.value = toasts.value.filter((t) => t.id !== id)), 6000);
}
