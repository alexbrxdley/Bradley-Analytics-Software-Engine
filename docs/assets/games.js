/* What the four daily games share (Today's Play, GM Daily Challenge, Fantasy Draft, Guess the Analytics): the day, the
   NBA data (ESPN's public feeds, the site's ratings and salaries), a seeded random for the day's puzzle, and the
   leaderboards.

   Leaderboards are shared through the site's server (worker/, the same one as the live game alerts: push_worker_url in
   _config.yml). Until it's set up, or if it can't be reached, results are kept on this device only, and the board says so. */
(function () {
  "use strict";
  var CFG = window.BA_PUSH || {}, API = (CFG.worker || "").replace(/\/+$/, "");
  var ESPN_ATH = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/statistics/byathlete?region=us&lang=en&contentorigin=espn&isqualified=false&page=1&limit=1000&sort=offensive.avgPoints:desc";
  var ESPN_TEAM = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/statistics/byteam?region=us&lang=en&contentorigin=espn&sort=team.offensive.avgPoints:desc";
  var SB = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?limit=200&dates=";
  var CELTICS = "https://www.2kratings.com/wp-content/uploads/Boston-Celtics-Current-Logo.svg";
  var COLORS = { ATL: "#E03A3E", BOS: "#18A659", BKN: "#C9C9C9", CHA: "#00778B", CHI: "#E0314B", CLE: "#FDBB30", DAL: "#1E7FD6", DEN: "#FEC524",
    DET: "#E0314B", GS: "#FFC72C", HOU: "#E0314B", IND: "#FDBB30", LAC: "#3B82F6", LAL: "#FDB927", MEM: "#7D95C9", MIA: "#F25C54", MIL: "#EEE1C6",
    MIN: "#1F4399", NO: "#B6995A", NY: "#F58426", OKC: "#2E9BE6", ORL: "#2F8FE0", PHI: "#3B82F6", PHX: "#E56020", POR: "#E03A3E", SAC: "#A57FDB",
    SA: "#C4CED4", TOR: "#E0314B", UTAH: "#8D5BD6", WSH: "#E31837" };
  var NAMES = { ATL: "Atlanta Hawks", BOS: "Boston Celtics", BKN: "Brooklyn Nets", CHA: "Charlotte Hornets", CHI: "Chicago Bulls", CLE: "Cleveland Cavaliers",
    DAL: "Dallas Mavericks", DEN: "Denver Nuggets", DET: "Detroit Pistons", GS: "Golden State Warriors", HOU: "Houston Rockets", IND: "Indiana Pacers",
    LAC: "LA Clippers", LAL: "Los Angeles Lakers", MEM: "Memphis Grizzlies", MIA: "Miami Heat", MIL: "Milwaukee Bucks", MIN: "Minnesota Timberwolves",
    NO: "New Orleans Pelicans", NY: "New York Knicks", OKC: "Oklahoma City Thunder", ORL: "Orlando Magic", PHI: "Philadelphia 76ers", PHX: "Phoenix Suns",
    POR: "Portland Trail Blazers", SAC: "Sacramento Kings", SA: "San Antonio Spurs", TOR: "Toronto Raptors", UTAH: "Utah Jazz", WSH: "Washington Wizards" };

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function getJSON(u, opts) { return fetch(u, opts || { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }); }
  function day(offset) {                                   // the NBA's day, in New York, rolling over at 6 a.m.
    var d = new Date(Date.now() - 6 * 3600e3 + (offset || 0) * 864e5);
    try { return d.toLocaleDateString("en-CA", { timeZone: "America/New_York" }); } catch (e) { return d.toISOString().slice(0, 10); }
  }
  function niceDay(d) { try { return new Date(d + "T12:00:00Z").toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", timeZone: "UTC" }); } catch (e) { return d; } }
  function seeded(seed) {                                  // the day's puzzle is the same for everyone
    var h = 2166136261;
    for (var i = 0; i < seed.length; i++) { h ^= seed.charCodeAt(i); h = Math.imul(h, 16777619); }
    return function () { h += 0x6D2B79F5; var t = h; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  function logo(tri) { return tri === "BOS" ? CELTICS : "https://a.espncdn.com/i/teamlogos/nba/500/" + String(tri).toLowerCase() + ".png"; }
  function store(k, v) { try { if (v === undefined) return JSON.parse(localStorage.getItem(k) || "null"); localStorage.setItem(k, JSON.stringify(v)); } catch (e) { return null; } }

  // ------------------------------------------------------------ data
  var cache = {};
  function once(k, f) { return cache[k] || (cache[k] = f().catch(function (e) { delete cache[k]; throw e; })); }
  // a player's picture, small and fast: ESPN's image server crops and shrinks it (w = width in px)
  function face(id, w) { w = w || 120; return "https://a.espncdn.com/combiner/i?img=/i/headshots/nba/players/full/" + id + ".png&w=" + w + "&h=" + Math.round(w * 0.727) + "&scale=crop&cquality=70"; }
  function nbaFace(id) { return "https://cdn.nba.com/headshots/nba/latest/260x190/" + id + ".png"; }
  var preloaded = {};
  function preload(urls) { (urls || []).forEach(function (u) { if (u && !preloaded[u]) { var im = new Image(); im.decoding = "async"; im.src = u; preloaded[u] = im; } }); }
  // every player's per-game numbers for a season (season = the year it ends, e.g. 1997 for 1996-97; none = this season)
  function players(season) {
    return once("players" + (season || ""), function () {
      return getJSON(ESPN_ATH + (season ? "&season=" + season + "&seasontype=2" : "")).then(function (d) {
        var at = {}; (d.categories || []).forEach(function (c) { if (c.names) at[c.name] = c.names; });
        function v(a, cat, n) { var c = (a.categories || []).filter(function (x) { return x.name === cat; })[0], i = (at[cat] || []).indexOf(n); if (!c || i < 0) return 0; return parseFloat((c.values || c.totals || [])[i]) || 0; }
        return (d.athletes || []).map(function (a) {
          var p = a.athlete || {};
          return { id: p.id, name: p.displayName, short: p.shortName || p.displayName, team: p.teamShortName || "", pos: (p.position && p.position.abbreviation) || "",
            head: face(p.id, 120), teams: (p.teams || []).map(function (t) { return { tri: t.abbreviation, name: t.displayName, logo: ((t.logos || [])[0] || {}).href || "" }; }), gp: v(a, "general", "gamesPlayed"), min: v(a, "general", "avgMinutes"),
            pts: v(a, "offensive", "avgPoints"), reb: v(a, "general", "avgRebounds"), ast: v(a, "offensive", "avgAssists"), stl: v(a, "defensive", "avgSteals"),
            blk: v(a, "defensive", "avgBlocks"), tov: v(a, "offensive", "avgTurnovers"), fgp: v(a, "offensive", "fieldGoalPct"), fga: v(a, "offensive", "avgFieldGoalsAttempted"),
            tpm: v(a, "offensive", "avgThreePointFieldGoalsMade"), tpa: v(a, "offensive", "avgThreePointFieldGoalsAttempted"), tpp: v(a, "offensive", "threePointFieldGoalPct"),
            ftp: v(a, "offensive", "freeThrowPct"), fta: v(a, "offensive", "avgFreeThrowsAttempted") };
        }).filter(function (p) { return p.gp > 0; });
      });
    });
  }
  function teams(season) {
    return once("teams" + (season || ""), function () {
      return getJSON(ESPN_TEAM + (season ? "&season=" + season + "&seasontype=2" : "")).then(function (d) {
        var names = {}; (d.categories || []).forEach(function (c) { if (c.names && !names[c.name]) names[c.name] = c.names; });
        return (d.teams || []).map(function (t) {
          function v(cat, n, opp) {
            var c = (t.categories || []).filter(function (x) { return x.name === cat && (!!opp === (String(x.splitId) === "900" || /^opponent/i.test(x.displayName || ""))); })[0];
            var i = (names[cat] || []).indexOf(n); return c && i >= 0 ? parseFloat((c.values || [])[i]) || 0 : 0;
          }
          var tm = t.team || {};
          return { tri: tm.abbreviation, name: tm.displayName, logo: ((tm.logos || [])[0] || {}).href || "", short: tm.shortDisplayName, gp: v("general", "gamesPlayed"), pts: v("offensive", "avgPoints"),
            opp: v("offensive", "avgPoints", true), reb: v("general", "avgRebounds"), ast: v("offensive", "avgAssists"), stl: v("defensive", "avgSteals"),
            blk: v("defensive", "avgBlocks"), tov: v("offensive", "avgTurnovers"), fgp: v("offensive", "fieldGoalPct"), tpp: v("offensive", "threePointFieldGoalPct"),
            tpm: v("offensive", "avgThreePointFieldGoalsMade"), oppfgp: v("offensive", "fieldGoalPct", true), opptpp: v("offensive", "threePointFieldGoalPct", true) };
        });
      });
    });
  }
  function scoreboard(d) { return getJSON(SB + d.replace(/-/g, "")); }
  function ratings() {
    return once("ratings", function () {
      return getJSON("data/ratings.json", {}).then(function (d) {
        return d.players.map(function (r) { var o = {}; d.fields.forEach(function (f, i) { o[f] = r[i]; }); return o; });
      });
    });
  }
  function contracts() { return once("contracts", function () { return getJSON("data/contracts.json", {}); }); }
  function analytics() { return once("analytics", function () { return getJSON("data/analytics.json", {}); }); }
  function lineups() { return once("lineups", function () { return getJSON("data/lineups.json", {}).then(function (d) { return d.lineups || []; }); }); }
  function salaries() { return once("salaries", function () { return getJSON("data/salaries.json", {}).then(function (d) { return d.salaries || {}; }); }); }
  // a ratings card for an ESPN player (the ratings use "T. Maxey" and the full team name)
  function fold(s) { return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z ]/g, ""); }
  function ratingFor(list, p) {
    var parts = fold(p.name).split(" "), first = parts[0] || "", last = parts.slice(1).join(" "), team = fold(NAMES[p.team] || "");
    var best = null;
    list.forEach(function (r) {
      var n = fold(r.name), rl = n.replace(/^[a-z]+ /, "");
      if (rl === last && n.charAt(0) === first.charAt(0)) { if (!best || fold(r.team) === team) best = r; }
    });
    return best;
  }

  // ------------------------------------------------------------ leaderboards
  function localKey(g, d) { return "bag:" + g + ":" + d; }
  function localBoard(g, d) { return store(localKey(g, d)) || []; }
  function submit(game, d, r) {
    var entry = { game: game, day: d, name: r.name, score: r.score, extra: r.extra || {}, detail: r.detail || {} };
    var local = function () {
      var b = localBoard(game, d), id = "me-" + (r.name || "").toLowerCase();
      var old = b.filter(function (x) { return x.id === id; })[0];
      if (!old || old.score < r.score) {
        b = b.filter(function (x) { return x.id !== id; }).concat([{ id: id, name: r.name, score: r.score, extra: r.extra || {}, at: Date.now(), detail: r.detail || {} }]);
        b.sort(function (a, c) { return c.score - a.score; });
        store(localKey(game, d), b.slice(0, 50));
      }
      return { board: b, shared: false };
    };
    if (!API) return Promise.resolve(local());
    return fetch(API + "/games/score", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(entry) })
      .then(function (res) { if (!res.ok) throw new Error(); return res.json(); })
      .then(function (j) { local(); return { board: j.board || [], shared: true, rank: j.rank }; })
      .catch(function () { return local(); });
  }
  // the week ("2026-W44") and month of a day, and the days of this device's own results in it
  function weekOf(day) {
    var d = new Date(day + "T12:00:00Z"), wd = (d.getUTCDay() + 6) % 7; d.setUTCDate(d.getUTCDate() - wd + 3);
    var y = d.getUTCFullYear(), first = new Date(Date.UTC(y, 0, 4));
    var w = 1 + Math.round(((d - first) / 864e5 - 3 + ((first.getUTCDay() + 6) % 7)) / 7);
    return y + "-W" + (w < 10 ? "0" : "") + w;
  }
  var SUMS = { "todays-play": true, "gm-challenge": true, "guess-the-analytics": true };
  function localPeriod(game, d, period) {               // this device's results, added up the way the server does
    var rows = {};
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i), m = k && k.match(/^bag:([a-z0-9~-]+):(\d{4}-\d{2}-\d{2})$/);
        if (!m || m[1] !== game) continue;
        var day2 = m[2];
        if (period === "week" && weekOf(day2) !== weekOf(d)) continue;
        if (period === "month" && day2.slice(0, 7) !== d.slice(0, 7)) continue;
        (store(k) || []).forEach(function (r) {
          var row = rows[r.name.toLowerCase()] || (rows[r.name.toLowerCase()] = { id: r.id, name: r.name, score: 0, extra: { days: 0 }, at: r.at });
          row.extra.days++;
          row.score = SUMS[game] ? Math.round((row.score + r.score) * 10) / 10 : Math.max(row.score, r.score);
          if (!SUMS[game] && row.score === r.score) row.extra = Object.assign({}, r.extra, { days: row.extra.days });
        });
      }
    } catch (e) {}
    return Object.keys(rows).map(function (k) { return rows[k]; }).sort(function (a, b) { return b.score - a.score; });
  }
  function board(game, d, period) {
    period = period || "day";
    var local = function () { return period === "day" ? localBoard(game, d) : localPeriod(game, d, period); };
    if (!API) return Promise.resolve({ board: local(), shared: false, period: period });
    return getJSON(API + "/games/board?game=" + encodeURIComponent(game) + "&day=" + encodeURIComponent(d) + "&period=" + period)
      .then(function (j) { return { board: j.board || [], shared: true, period: period }; })
      .catch(function () { return { board: local(), shared: false, period: period }; });
  }
  function entry(game, d, id) {
    var mine = localBoard(game, d).filter(function (x) { return x.id === id; })[0];
    if (mine || !API) return Promise.resolve(mine || null);
    return getJSON(API + "/games/entry?game=" + encodeURIComponent(game) + "&day=" + encodeURIComponent(d) + "&id=" + encodeURIComponent(id)).catch(function () { return null; });
  }
  // the board: rank, name, score (and any extra columns); a row with details opens them
  var PERIODS = [["day", "Today"], ["week", "This week"], ["month", "This month"], ["all", "All time"]];
  function renderBoard(el, game, d, opts) {
    opts = opts || {};
    var period = el._period || "day";
    if (opts.dayOnly && !el._tabs) { el._tabs = true; el.innerHTML = '<div class="gm-board-in"></div>'; }
    if (!el._tabs) {                                    // the tabs: today, this week, this month, all time
      el._tabs = true;
      el.innerHTML = '<div class="gm-tabs" role="tablist">' + PERIODS.map(function (p) { return '<button type="button" role="tab" data-p="' + p[0] + '"' + (p[0] === period ? ' class="on" aria-selected="true"' : ' aria-selected="false"') + ">" + p[1] + "</button>"; }).join("") + '</div><div class="gm-board-in"></div>';
      el.querySelectorAll(".gm-tabs button").forEach(function (b) {
        b.addEventListener("click", function () {
          el._period = b.getAttribute("data-p");
          el.querySelectorAll(".gm-tabs button").forEach(function (x) { var on = x === b; x.classList.toggle("on", on); x.setAttribute("aria-selected", on); });
          renderBoard(el, game, d, opts);
        });
      });
    }
    var box = el.querySelector(".gm-board-in");
    box.innerHTML = '<p class="gm-empty">Loading the leaderboard…</p>';
    return board(game, d, period).then(function (b) { drawBoard(box, game, d, b, opts); return b; });
  }
  function drawBoard(el, game, d, b, opts) {
    var period = b.period || "day", long = period !== "day", sums = SUMS[game] && long;
    var cols = long ? (sums ? [["days", "Days"]] : (opts.cols || []).concat([["days", "Days"]])) : (opts.cols || []);
    var fmt = sums ? function (s) { return (+s).toFixed(1).replace(/\.0$/, ""); } : (opts.format || function (s) { return s.toFixed(1) + "%"; });
    var me = (store("bag:name") || "").toLowerCase();
    var when = { day: "Today", week: "This week", month: "This month", all: "All time" }[period];
    el.innerHTML = (b.board.length ? '<table class="gm-board"><thead><tr><th>#</th><th class="l">Name</th>' + cols.map(function (c) { return "<th>" + esc(c[1]) + "</th>"; }).join("") +
      "<th>" + esc(sums ? "Total" : (opts.scoreLabel || "Score")) + "</th>" + (opts.onView && !long ? "<th></th>" : "") + "</tr></thead><tbody>" +
      b.board.slice(0, opts.limit || 25).map(function (r, i) {
        return '<tr class="' + (String(r.name).toLowerCase() === me ? "me" : "") + '"><td>' + (i + 1) + '</td><td class="l">' + esc(r.name) + "</td>" +
          cols.map(function (c) { var v = (r.extra || {})[c[0]]; return "<td>" + esc(v == null ? "–" : (c[2] ? c[2](v) : v)) + "</td>"; }).join("") +
          '<td class="s">' + esc(fmt(+r.score)) + "</td>" + (opts.onView && !long ? '<td><button type="button" class="gm-view" data-id="' + esc(r.id) + '">' + esc(opts.viewLabel || "View") + "</button></td>" : "") + "</tr>";
      }).join("") + "</tbody></table>" : '<p class="gm-empty">No results ' + (period === "day" ? "yet today" : when.toLowerCase().replace("all time", "yet")) + ". Be the first.</p>") +
      '<p class="gm-board-note">' + (b.shared ? when + (period === "day" ? ", " + esc(niceDay(d)) : "") + (sums ? ": every day's best score added up." : period === "all" || long ? ": each player's best." : ".")
        : "Saved on this device. The shared leaderboard turns on once the site's server is connected.") + "</p>";
    if (opts.onView && !long) el.querySelectorAll(".gm-view").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-id"), local = b.board.filter(function (r) { return r.id === id; })[0];
        (local && local.detail ? Promise.resolve(local) : entry(game, d, id)).then(function (e) { if (e) opts.onView(e); });
      });
    });
  }
  function askName() {
    var n = store("bag:name");
    if (n) return Promise.resolve(n);
    return new Promise(function (resolve) {
      var shade = document.createElement("div");
      shade.className = "gm-shade";
      shade.innerHTML = '<form class="gm-namebox"><h3>Your name for the leaderboard</h3><input maxlength="24" required placeholder="e.g. Alex B." autocomplete="nickname"><div class="gm-row"><button type="submit" class="gm-btn">Save</button></div></form>';
      document.body.appendChild(shade);
      var f = shade.querySelector("form"), inp = f.querySelector("input"); inp.focus();
      f.addEventListener("submit", function (e) { e.preventDefault(); var v = inp.value.trim().slice(0, 24); if (!v) return; store("bag:name", v); shade.remove(); resolve(v); });
    });
  }

  window.BAG = { esc: esc, getJSON: getJSON, day: day, niceDay: niceDay, seeded: seeded, logo: logo, colors: COLORS, names: NAMES, store: store,
    players: players, teams: teams, face: face, nbaFace: nbaFace, preload: preload, contracts: contracts, analytics: analytics, lineups: lineups, scoreboard: scoreboard, ratings: ratings, salaries: salaries, ratingFor: ratingFor, fold: fold,
    submit: submit, board: board, entry: entry, renderBoard: renderBoard, drawBoard: drawBoard, askName: askName, shared: !!API };
})();
