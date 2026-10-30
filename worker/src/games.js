// Scores (and drawn plays, moves and teams) for the website's games: Today's Play, GM Daily Challenge, Fantasy Draft and
// Guess the Analytics.
//
//   POST /games/score   { game, day, name, score, extra, detail }   save a result (one per name per game per day: the best)
//   GET  /games/board?game=&day=[&period=day|week|month|all]        a leaderboard (no details): that day's (top 100), or
//                                                                   the week's, the month's or all time's (top 300)
//   GET  /games/entry?game=&day=&id=                                one result with its details (a drawn play, a move...)
//
// Stored in the ALERTS KV namespace, kept forever: "gs:<game>:<day>:<id>" per result, "gb:<game>:<day>" the day's board
// (kept sorted, so a leaderboard view is one read), and "gb:<game>:w:<YYYY-Www>", "gb:<game>:m:<YYYY-MM>" and
// "gb:<game>:all" the weekly, monthly and all-time boards, updated with every result. For the daily games (Today's
// Play, GM Daily Challenge, Guess the Analytics) a longer board adds up each player's best score of every day in it
// (so playing every day counts); for 82-0 Fantasy Draft it keeps each player's best record. Like the dashboard's Community Uploads, every result can also be saved to
// the GitHub repo (branch GITHUB_BRANCH, default "community-data") when GITHUB_TOKEN and GITHUB_REPO are set as
// secrets: games/<game>/<day>/<id>.json.
const GAMES = { "todays-play": 100, "gm-challenge": 100, "fantasy-draft": 82, "guess-the-analytics": 100 };
const SUMS = { "todays-play": true, "gm-challenge": true, "guess-the-analytics": true };   // the rest keep the best
// Today's Play also has a board for each matchup: "todays-play~<ESPN game id>" (that day only)
function maxOf(g) { return GAMES[g] || (/^todays-play~\d{1,12}$/.test(g) ? 100 : 0); }

// the ISO week ("2026-W44") and month ("2026-10") of a day
function weekOf(day) {
  const d = new Date(day + "T12:00:00Z"), wd = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - wd + 3);
  const y = d.getUTCFullYear(), first = new Date(Date.UTC(y, 0, 4));
  const w = 1 + Math.round(((d - first) / 864e5 - 3 + ((first.getUTCDay() + 6) % 7)) / 7);
  return y + "-W" + String(w).padStart(2, "0");
}
function periodKey(game, day, period) {
  if (period === "week") return "gb:" + game + ":w:" + weekOf(day);
  if (period === "month") return "gb:" + game + ":m:" + day.slice(0, 7);
  if (period === "all") return "gb:" + game + ":all";
  return "gb:" + game + ":" + day;
}
// a result into a longer board: the day's score replaces that day's earlier one, the total (or the best) is the score
function addTo(board, game, day, r) {
  const old = board.find((x) => x.id === r.id) || { id: r.id, name: r.name, days: {}, score: 0, at: r.at };
  const days = Object.assign({}, old.days || {});
  if (days[day] != null && days[day] >= r.score) return null;
  days[day] = r.score;
  const vals = Object.values(days);
  const score = SUMS[game] ? Math.round(vals.reduce((a, b) => a + b, 0) * 10) / 10 : Math.max.apply(null, vals);
  const extra = Object.assign({}, SUMS[game] ? {} : r.extra, { days: vals.length });
  const row = { id: r.id, name: r.name, score, extra, days, at: r.at };
  return board.filter((x) => x.id !== r.id).concat([row]).sort((a, c) => c.score - a.score || a.at - c.at).slice(0, 300);
}

function clean(s, n) { return String(s == null ? "" : s).replace(/[\u0000-\u001f<>]/g, "").trim().slice(0, n); }
async function idOf(s) {
  const h = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)));
  return Array.from(h.slice(0, 8), (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function handleGames(req, env, url, ctx) {
  const game = clean(url.searchParams.get("game"), 40), day = clean(url.searchParams.get("day"), 10);
  if (req.method === "GET" && url.pathname === "/games/board") {
    const period = clean(url.searchParams.get("period"), 6) || (day === "all" ? "all" : "day");
    if (!maxOf(game) || !/^(\d{4}-\d{2}-\d{2}|all)$/.test(day) || !/^(day|week|month|all)$/.test(period) || (day === "all" && period !== "all")) return [400, { error: "bad game, day or period" }];
    const board = ((await env.ALERTS.get(periodKey(game, day, period), "json")) || []).map((r) => ({ id: r.id, name: r.name, score: r.score, extra: r.extra, at: r.at }));
    return [200, { game, day, period, board }];
  }
  if (req.method === "GET" && url.pathname === "/games/entry") {
    const id = clean(url.searchParams.get("id"), 20);
    const e = await env.ALERTS.get("gs:" + game + ":" + day + ":" + id, "json");
    return e ? [200, e] : [404, { error: "not found" }];
  }
  if (req.method === "POST" && url.pathname === "/games/score") {
    let b;
    try { b = await req.json(); } catch { return [400, { error: "bad json" }]; }
    const g = clean(b.game, 40), d = clean(b.day, 10), name = clean(b.name, 24) || "Anonymous";
    const max = maxOf(g), score = Number(b.score);
    if (!max || !/^(\d{4}-\d{2}-\d{2}|all)$/.test(d) || !isFinite(score) || score < 0 || score > max) return [400, { error: "bad result" }];
    const detail = JSON.stringify(b.detail || {});
    if (detail.length > 40000) return [413, { error: "too big" }];
    const extra = {};
    Object.keys(b.extra || {}).slice(0, 8).forEach((k) => { const v = b.extra[k]; extra[clean(k, 16)] = typeof v === "number" ? v : clean(v, 40); });
    const id = await idOf(g + d + name.toLowerCase());
    const entry = { id, name, score: Math.round(score * 10) / 10, extra, at: Date.now(), detail: JSON.parse(detail) };
    const bkey = "gb:" + g + ":" + d;
    const board = (await env.ALERTS.get(bkey, "json")) || [];
    const old = board.find((r) => r.id === id);
    if (old && old.score >= entry.score) return [200, { ok: true, kept: true, rank: board.indexOf(old) + 1, board }];
    const next = board.filter((r) => r.id !== id).concat([{ id, name, score: entry.score, extra, at: entry.at }])
      .sort((a, c) => c.score - a.score || a.at - c.at).slice(0, 100);
    await env.ALERTS.put("gs:" + g + ":" + d + ":" + id, JSON.stringify(entry));          // (kept forever)
    await env.ALERTS.put(bkey, JSON.stringify(next));
    if (d !== "all" && GAMES[g]) {                         // the week's, the month's and all time's boards
      const pid = await idOf(g + "*" + name.toLowerCase());
      for (const period of ["week", "month", "all"]) {
        const key = periodKey(g, d, period), b2 = (await env.ALERTS.get(key, "json")) || [];
        const n2 = addTo(b2, g, d, { id: pid, name, score: entry.score, extra, at: entry.at });
        if (n2) await env.ALERTS.put(key, JSON.stringify(n2));
      }
    }
    if (env.GITHUB_TOKEN && env.GITHUB_REPO && ctx) ctx.waitUntil(toGitHub(env, "games/" + g + "/" + d + "/" + id + ".json", entry).catch(() => {}));
    return [200, { ok: true, rank: next.findIndex((r) => r.id === id) + 1, board: next }];
  }
  return [404, { error: "not found" }];
}

// the same backup the dashboard's Community Uploads use: a file committed to the repo's data branch
async function toGitHub(env, path, data) {
  const api = "https://api.github.com/repos/" + env.GITHUB_REPO + "/contents/" + path, branch = env.GITHUB_BRANCH || "community-data";
  const head = { Authorization: "Bearer " + env.GITHUB_TOKEN, "User-Agent": "bradley-analytics-games", Accept: "application/vnd.github+json" };
  let sha;
  const cur = await fetch(api + "?ref=" + encodeURIComponent(branch), { headers: head });
  if (cur.ok) sha = (await cur.json()).sha;
  const content = btoa(unescape(encodeURIComponent(JSON.stringify(data, null, 1))));
  await fetch(api, { method: "PUT", headers: head, body: JSON.stringify({ message: "Game result: " + path, content, branch, sha }) });
}
