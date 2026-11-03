/**
 * filmtr Worker: static app and catalog data come from assets; this handles
 * /api/* — personal lists in D1 and a small TMDB proxy for adding films that
 * are not in the static catalog.
 */

interface Env {
  DB: D1Database;
  ASSETS: Fetcher;
  TMDB_TOKEN?: string;
  ACCESS_TEAM_DOMAIN?: string;
  ACCESS_AUD?: string;
  DEV_NO_AUTH?: string;
}

type Entry = {
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

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });

const error = (status: number, message: string) => json({ error: message }, status);

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (!(await accessAllowed(req, env))) {
      return url.pathname.startsWith("/api/")
        ? error(403, "Нужен вход через Cloudflare Access")
        : new Response("filmtr: нужен вход через Cloudflare Access.", {
            status: 403,
            headers: { "content-type": "text/plain; charset=utf-8" },
          });
    }
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(req);
    try {
      return await api(req, env, url);
    } catch (e) {
      return error(500, e instanceof Error ? e.message : String(e));
    }
  },
} satisfies ExportedHandler<Env>;

async function api(req: Request, env: Env, url: URL): Promise<Response> {
  const parts = url.pathname.split("/").filter(Boolean).slice(1); // drop "api"

  // GET /api/my — all personal lists with entries
  if (parts[0] === "my" && parts.length === 1 && req.method === "GET") {
    const lists = await env.DB.prepare("SELECT id, title, description FROM my_list ORDER BY pos").all();
    const rows = await env.DB.prepare("SELECT * FROM my_entry ORDER BY list_id, pos").all<Record<string, unknown>>();
    const entries = rows.results.map((r) => ({ ...r, tags: JSON.parse((r.tags as string) || "[]") }));
    return json({ lists: lists.results, entries });
  }

  // PUT /api/my/:list/:film — add or update an entry
  // DELETE /api/my/:list/:film — remove it
  if (parts[0] === "my" && parts.length === 3) {
    const [, listId, filmId] = parts;
    if (!/^tt\d+$/.test(filmId)) return error(400, "Неверный ID фильма");
    const list = await env.DB.prepare("SELECT id FROM my_list WHERE id = ?").bind(listId).first();
    if (!list) return error(404, "Нет такого списка");

    if (req.method === "DELETE") {
      await env.DB.prepare("DELETE FROM my_entry WHERE list_id = ? AND film_id = ?").bind(listId, filmId).run();
      return json({ ok: true });
    }
    if (req.method === "PUT") {
      const body = (await req.json()) as Partial<Entry> & { position?: "top" | "bottom" };
      return json(await upsert(env.DB, listId, filmId, body));
    }
  }

  // GET /api/tmdb/search?q= — films and series outside the catalog
  if (parts[0] === "tmdb" && parts[1] === "search" && req.method === "GET") {
    const q = url.searchParams.get("q")?.trim();
    if (!q) return json({ results: [] });
    const data = await tmdb(env, `/search/multi?query=${encodeURIComponent(q)}&language=ru-RU`);
    const results = (data.results as Record<string, any>[])
      .filter((r) => r.media_type === "movie" || r.media_type === "tv")
      .slice(0, 12)
      .map((r) => ({
        tmdb_type: r.media_type,
        tmdb_id: r.id,
        title: r.title ?? r.name,
        original_title: r.original_title ?? r.original_name,
        year: Number((r.release_date ?? r.first_air_date ?? "").slice(0, 4)) || null,
        poster_path: r.poster_path,
        overview: r.overview,
      }));
    return json({ results });
  }

  // GET /api/tmdb/imdb/:type/:id — IMDb id of a TMDB movie or series
  if (parts[0] === "tmdb" && parts[1] === "imdb" && parts.length === 4) {
    const [, , type, id] = parts;
    if (type !== "movie" && type !== "tv") return error(400, "Неверный тип");
    const ids = await tmdb(env, `/${type}/${Number(id)}/external_ids`);
    return json({ imdb_id: ids.imdb_id ?? null });
  }

  return error(404, "Нет такого метода");
}

async function upsert(
  db: D1Database,
  listId: string,
  filmId: string,
  body: Partial<Entry> & { position?: "top" | "bottom" },
): Promise<Entry> {
  const now = new Date().toISOString();
  const current = await db
    .prepare("SELECT * FROM my_entry WHERE list_id = ? AND film_id = ?")
    .bind(listId, filmId)
    .first<Record<string, unknown>>();

  let pos = current ? (current.pos as number) : undefined;
  if (body.position || pos === undefined) {
    const edge = await db
      .prepare("SELECT min(pos) AS lo, max(pos) AS hi FROM my_entry WHERE list_id = ?")
      .bind(listId)
      .first<{ lo: number | null; hi: number | null }>();
    pos = body.position === "top" ? (edge?.lo ?? 1) - 1 : (edge?.hi ?? -1) + 1;
  }
  if (typeof body.pos === "number") pos = body.pos;

  const tags = body.tags ?? (current ? JSON.parse(current.tags as string) : []);
  const cleanTags = [...new Set(tags.map((t: string) => t.trim()).filter(Boolean))] as string[];
  const entry: Entry = {
    list_id: listId,
    film_id: filmId,
    pos: pos!,
    tags: cleanTags,
    note: body.note !== undefined ? body.note?.trim() || null : ((current?.note as string) ?? null),
    added_at: (current?.added_at as string) ?? now,
    updated_at: now,
    title: body.title ?? (current?.title as string) ?? null,
    year: body.year ?? (current?.year as number) ?? null,
    poster_path: body.poster_path ?? (current?.poster_path as string) ?? null,
  };
  await db
    .prepare(
      `INSERT INTO my_entry (list_id, film_id, pos, tags, note, added_at, updated_at, title, year, poster_path)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT (list_id, film_id) DO UPDATE SET pos = excluded.pos, tags = excluded.tags,
         note = excluded.note, updated_at = excluded.updated_at, title = excluded.title,
         year = excluded.year, poster_path = excluded.poster_path`,
    )
    .bind(entry.list_id, entry.film_id, entry.pos, JSON.stringify(entry.tags), entry.note, entry.added_at,
      entry.updated_at, entry.title, entry.year, entry.poster_path)
    .run();
  return entry;
}

async function tmdb(env: Env, path: string): Promise<Record<string, any>> {
  if (!env.TMDB_TOKEN) throw new Error("TMDB_TOKEN не задан");
  const resp = await fetch(`https://api.themoviedb.org/3${path}`, {
    headers: { Authorization: `Bearer ${env.TMDB_TOKEN}`, accept: "application/json" },
  });
  if (!resp.ok) throw new Error(`TMDB: ${resp.status}`);
  return resp.json();
}

// --- Cloudflare Access ---------------------------------------------------
// The whole site sits behind Cloudflare Access, and the Worker verifies the
// Access token on every request too, so nothing leaks through a route that
// Access does not cover (such as a preview URL). Fails closed.

let certs: { keys: JsonWebKey[]; fetched: number } | null = null;

async function accessAllowed(req: Request, env: Env): Promise<boolean> {
  if (env.DEV_NO_AUTH === "1") return true; // local development only, from .dev.vars
  if (!env.ACCESS_TEAM_DOMAIN || !env.ACCESS_AUD) return false;
  const token = req.headers.get("cf-access-jwt-assertion");
  if (!token) return false;
  const [h, p, s] = token.split(".");
  if (!h || !p || !s) return false;
  const header = JSON.parse(b64urlText(h));
  const payload = JSON.parse(b64urlText(p));
  const auds = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
  if (!auds.includes(env.ACCESS_AUD)) return false;
  if (payload.iss !== `https://${env.ACCESS_TEAM_DOMAIN}`) return false;
  if (typeof payload.exp !== "number" || payload.exp * 1000 < Date.now()) return false;

  if (!certs || Date.now() - certs.fetched > 3600_000) {
    const resp = await fetch(`https://${env.ACCESS_TEAM_DOMAIN}/cdn-cgi/access/certs`);
    certs = { keys: ((await resp.json()) as { keys: JsonWebKey[] }).keys, fetched: Date.now() };
  }
  const jwk = certs.keys.find((k) => (k as { kid?: string }).kid === header.kid);
  if (!jwk) return false;
  const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, [
    "verify",
  ]);
  return crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64urlBytes(s), new TextEncoder().encode(`${h}.${p}`));
}

function b64urlBytes(s: string): Uint8Array<ArrayBuffer> {
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(s.length / 4) * 4, "="));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function b64urlText(s: string): string {
  return new TextDecoder().decode(b64urlBytes(s));
}
