// The Bradley Analytics notification server: a Cloudflare Worker that sends the site's live game alerts to every
// browser that turned them on, even when the site is closed.
//
//   POST /subscribe    { subscription, prefs }   a browser turns alerts on (or changes them)
//   POST /unsubscribe  { endpoint }               a browser turns them off
//   every minute (cron): read ESPN's scoreboard, work out the alerts (src/alerts.js) and push each subscriber the ones
//                        they asked for.
//
// Storage (one KV namespace, bound as ALERTS): "sub:<id>" per subscriber, and "seen" (what's already been alerted
// tonight). Writes only happen when something changes, which keeps it inside Cloudflare's free plan.
import { KINDS as KIND_LIST, TEAMS, detect, detectNews, detectHighlights, due, recapFor, reminder, allowed, gameDay, pictureFor } from "./alerts.js";
import { sendPush } from "./webpush.js";
import { handleGames } from "./games.js";

const SB = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=";
const KINDS = KIND_LIST.map((k) => k[0]);

async function idOf(endpoint) {
  const h = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(endpoint)));
  return Array.from(h.slice(0, 16), (b) => b.toString(16).padStart(2, "0")).join("");
}
function cors(req, env) {
  const origin = req.headers.get("Origin") || "";
  const ok = (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).includes(origin) ||
    /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
  return ok ? { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "86400", Vary: "Origin" } : { Vary: "Origin" };
}
function json(body, status, headers) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}
function cleanPrefs(p) {
  p = p || {};
  const types = {};
  for (const k of KINDS) types[k] = p.types && k in p.types ? !!p.types[k] : true;     // (a type they haven't seen yet starts on)
  const teams = (Array.isArray(p.teams) ? p.teams : []).filter((t) => TEAMS.includes(t));
  const players = (Array.isArray(p.players) ? p.players : []).filter((s) => typeof s === "string" && s.trim())
    .slice(0, 25).map((s) => s.trim().slice(0, 40));
  return { types, teams, players };
}
function validSub(s) {
  return s && typeof s.endpoint === "string" && /^https:\/\//.test(s.endpoint) && s.endpoint.length < 1000 &&
    s.keys && typeof s.keys.p256dh === "string" && typeof s.keys.auth === "string";
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url), h = cors(req, env);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: h });
    if (req.method === "GET" && url.pathname === "/") return json({ ok: true, service: "Bradley Analytics alerts and games" }, 200, h);
    if (url.pathname.startsWith("/games/")) {
      if (req.method === "POST" && !h["Access-Control-Allow-Origin"]) return json({ error: "origin not allowed" }, 403, h);
      const [status, body] = await handleGames(req, env, url, ctx);
      return json(body, status, h);
    }
    if (req.method !== "POST") return json({ error: "not found" }, 404, h);
    if (!h["Access-Control-Allow-Origin"]) return json({ error: "origin not allowed" }, 403, h);
    let body;
    try { body = await req.json(); } catch { return json({ error: "bad json" }, 400, h); }
    if (url.pathname === "/subscribe") {
      if (!validSub(body.subscription)) return json({ error: "bad subscription" }, 400, h);
      const sub = { endpoint: body.subscription.endpoint, keys: { p256dh: body.subscription.keys.p256dh, auth: body.subscription.keys.auth } };
      await env.ALERTS.put("sub:" + await idOf(sub.endpoint), JSON.stringify({ subscription: sub, prefs: cleanPrefs(body.prefs), t: Date.now() }));
      return json({ ok: true }, 200, h);
    }
    if (url.pathname === "/unsubscribe") {
      if (typeof body.endpoint !== "string") return json({ error: "bad endpoint" }, 400, h);
      await env.ALERTS.delete("sub:" + await idOf(body.endpoint));
      return json({ ok: true }, 200, h);
    }
    return json({ error: "not found" }, 404, h);
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(run(env));
  }
};

export async function run(env, fetchImpl = fetch, now = Date.now()) {
  const day = gameDay(now), site = (env.SITE_URL || "https://bradley-analytics.com").replace(/\/+$/, "");
  const get = async (u) => { const r = await fetchImpl(u, { headers: { "User-Agent": "bradley-analytics-alerts" } }); if (!r.ok) throw new Error(r.status); return r.json(); };
  let sb;
  try { sb = await get(SB + day); } catch { return { sent: 0 }; }
  const before = (await env.ALERTS.get("seen")) || "{}";
  let seen = JSON.parse(before);
  if (seen._day !== day) seen = { _day: day, inj: seen.inj, injx: seen.injx, tx: seen.tx, hl: seen.hl, recap: seen.recap, remind: seen.remind, nt: seen.nt };
  const events = detect(sb, seen);
  // every 10 minutes: the injury report and transactions, and new highlights (small files the site's GitHub Action keeps)
  if (now - (seen.nt || 0) >= 10 * 60e3) {
    seen.nt = now;
    try { events.push(...detectNews(await get(site + "/data/news.json?t=" + Math.floor(now / 60e3)), seen)); } catch {}
    try { events.push(...detectHighlights(await get(site + "/data/highlights-recent.json?t=" + Math.floor(now / 60e3)), seen)); } catch {}
  }
  // once a day: the morning recap (made for each subscriber) and the evening reminder
  let yesterday = null;
  for (const k of due(seen, now)) {
    if (k === "games") { const m = reminder(sb); if (m) events.push(m); }
    if (k === "recap") { try { yesterday = await get(SB + gameDay(now - 864e5)); } catch {} }
  }
  const after = JSON.stringify(seen);
  if (after !== before) await env.ALERTS.put("seen", after);
  if (!events.length && !yesterday) return { sent: 0 };

  const opts = { publicKey: env.VAPID_PUBLIC_KEY, privateJwk: env.VAPID_PRIVATE_JWK, subject: env.VAPID_SUBJECT || "mailto:alexbrxdley@gmail.com", fetchImpl };
  let cursor, sent = 0;
  do {
    const page = await env.ALERTS.list({ prefix: "sub:", cursor });
    cursor = page.list_complete ? undefined : page.cursor;
    await Promise.all(page.keys.map(async (k) => {
      const rec = await env.ALERTS.get(k.name, "json");
      if (!rec) return;
      const list = events.slice();
      if (yesterday) { const r = recapFor(yesterday, rec.prefs); if (r) list.push(r); }
      const mine = list.filter((m) => allowed(m, rec.prefs)).slice(0, 6);
      for (const m of mine) {
        const pic = pictureFor(m, rec.prefs);
        const status = await sendPush(rec.subscription, { title: m.title, body: m.body, tag: m.tag, url: m.url, img: pic.img, imgs: pic.imgs, round: !!m.round, ring: m.ring || "" }, opts).catch(() => 0);
        if (status === 404 || status === 410) { await env.ALERTS.delete(k.name); return; }   // the browser dropped it
        if (status >= 200 && status < 300) sent++;
      }
    }));
  } while (cursor);
  return { sent, events: events.length };
}
