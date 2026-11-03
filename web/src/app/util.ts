import type { FilmRow } from "./data";

export const poster = (path: string | null | undefined, size: "w92" | "w185" | "w342" | "w500" = "w342") =>
  path ? `https://image.tmdb.org/t/p/${size}${path}` : null;

/** Lowercase, ё→е, no diacritics or punctuation: for forgiving search. */
export function norm(s: string): string {
  return s
    .toLowerCase()
    .replace(/ё/g, "е")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

/** Films whose title, original title or director contains every word of the query. */
export function searchFilms(all: Iterable<FilmRow>, query: string, limit = 60): FilmRow[] {
  const words = norm(query).split(" ").filter(Boolean);
  if (!words.length) return [];
  const q = words.join(" ");
  const hits: [number, FilmRow][] = [];
  for (const f of all) {
    const titles = norm(`${f.t} ${f.o ?? ""}`);
    const hay = `${titles} ${norm((f.d ?? []).join(" "))}`;
    if (!words.every((w) => hay.includes(w))) continue;
    const exact = norm(f.t) === q || norm(f.o ?? "") === q;
    const score = (exact ? 1e9 : 0) + (titles.includes(q) ? 1e8 : 0) + (f.c ? 1e7 : 0) + (f.v ?? 0);
    hits.push([score, f]);
  }
  return hits
    .sort((a, b) => b[0] - a[0])
    .slice(0, limit)
    .map(([, f]) => f);
}

/** A stable, muted colour for a tag, so the same mood always looks the same. */
export function tagHue(tag: string): number {
  let h = 0;
  for (const ch of tag) h = (h * 31 + ch.codePointAt(0)!) % 360;
  return h;
}

export function runtime(min: number | null | undefined): string {
  if (!min) return "";
  const h = Math.floor(min / 60);
  const m = min % 60;
  return h ? `${h} ч ${m ? `${m} мин` : ""}`.trim() : `${m} мин`;
}

export function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

export const KIND_RU: Record<string, string> = {
  tvMovie: "телефильм",
  tvMiniSeries: "мини-сериал",
  tvSeries: "сериал",
  short: "короткий метр",
  video: "видео",
  tvSpecial: "телеспецвыпуск",
};
