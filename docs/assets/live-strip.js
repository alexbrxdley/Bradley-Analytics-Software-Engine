/* ============================================================
   Live strip: the auto-scrolling row of animated cards right above
   the dashboard. The visitor's own browser reads ESPN's public NBA
   feed (site.api.espn.com -- it allows websites to read it; the
   NBA's own feed does not), so there is nothing to run or set up:
   the strip is always current.
     * A game on right now: the live games (they refresh every minute)
       plus today's finished ones.
     * Otherwise: the most recent game day's finished games.
     * From the NBA Finals until the next regular season tips off
       (preseason never counts): every game of that Finals.
   If ESPN can't be reached, data/live/ (scripts/build_live_strip.py)
   is used if it exists. Every card has its own small dropdowns
   (game, and player or team). No data at all: the strip stays hidden.
   ============================================================ */
(function () {
  "use strict";
  var root = document.getElementById("live-strip");
  if (!root || !window.fetch || !window.requestAnimationFrame) return;
  var BASE = root.getAttribute("data-src") || "data/live/";
  var REDUCE = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var HEADSHOT = "https://cdn.nba.com/headshots/nba/latest/260x190/";
  var TOP = 330, BASE_Y = TOP + 47.5, Y89 = TOP - 89.5;
  var cache = {};
  var index = null;

  // ------------------------------------------------------------ helpers
  function getJSON(url) {
    return fetch(url, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }
  var source = "espn";
  function loadGame(id) {
    if (!cache[id]) {
      cache[id] = (source === "espn" ? getJSON(ESPN + "summary?event=" + id).then(function (s) { return fromSummary(s, id); })
        : getJSON(BASE + "games/" + id + ".json")).catch(function (e) { delete cache[id]; throw e; });
    }
    return cache[id];
  }

  // ------------------------------------------------------------ ESPN's feed -> the strip's game format
  var ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/";
  var ESPN_TRI = { GS: "GSW", NY: "NYK", SA: "SAS", NO: "NOP", UTAH: "UTA", WSH: "WAS", PHO: "PHX", BRK: "BKN", CHO: "CHA" };
  // team colours chosen to read on the page's near-black background (a team's darkest official colour often doesn't)
  var TEAM_COLORS = {
    ATL: "#E03A3E", BOS: "#18A659", BKN: "#C9C9C9", CHA: "#00A3B4", CHI: "#E0314B", CLE: "#FDBB30",
    DAL: "#1E7FD6", DEN: "#FEC524", DET: "#E0314B", GSW: "#FFC72C", HOU: "#E0314B", IND: "#FDBB30",
    LAC: "#3B82F6", LAL: "#FDB927", MEM: "#7D95C9", MIA: "#F25C54", MIL: "#EEE1C6", MIN: "#78BE20",
    NOP: "#C9A95E", NYK: "#F58426", OKC: "#2E9BE6", ORL: "#2F8FE0", PHI: "#3B82F6", PHX: "#F07A2E",
    POR: "#E03A3E", SAC: "#A57FDB", SAS: "#C4CED4", TOR: "#E0314B", UTA: "#F9C21B", WAS: "#E31837"
  };
  function triOf(team) {
    var a = String((team && team.abbreviation) || "").toUpperCase();
    return ESPN_TRI[a] || a;
  }
  function num(v) { var n = parseFloat(v); return isFinite(n) ? n : 0; }
  function etDay(iso) {
    try { return new Date(iso).toLocaleDateString("en-CA", { timeZone: "America/New_York" }); } catch (e) { return String(iso).slice(0, 10); }
  }
  function niceDay(iso) {
    try { return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" }); }
    catch (e) { return String(iso).slice(0, 10); }
  }
  function isNbaTeam(c) { var n = parseInt(c && c.team && c.team.id, 10); return n >= 1 && n <= 30; }
  function realEvent(e) {
    // regular season, play-in, playoffs -- never preseason, and never the All-Star game (not two real NBA teams)
    var t = e && e.season && e.season.type;
    var comp = e && e.competitions && e.competitions[0];
    return t !== 1 && t !== 4 && !!comp && (comp.competitors || []).length === 2 && comp.competitors.every(isNbaTeam);
  }
  function teamBrief(c) {
    var tri = triOf(c.team);
    return { tri: tri, name: c.team.name || c.team.shortDisplayName || tri, city: c.team.location || "",
      score: num(c.score), color: TEAM_COLORS[tri] || "#D4AF37" };
  }
  function brief(e) {
    var c = e.competitions[0], st = (e.status || c.status || {}).type || {}, home = null, away = null;
    c.competitors.forEach(function (t) { if (t.homeAway === "home") home = teamBrief(t); else away = teamBrief(t); });
    var note = (c.notes || []).map(function (n) { return n.headline || ""; }).join(" ");
    var game = /game\s*(\d+)/i.exec(note);
    return { id: String(e.id), label: game ? "Game " + game[1] : "", date: niceDay(e.date), day: etDay(e.date), when: e.date,
      status: st.shortDetail || st.detail || "", live: st.state === "in", final: st.state === "post", series: "",
      finals: /nba finals/i.test(note) || !!(c.type && c.type.abbreviation === "FINAL"), home: home, away: away };
  }
  function scoreboard(day) { return getJSON(ESPN + "scoreboard" + (day ? "?dates=" + day.replace(/-/g, "") : "")); }
  function calendarDays(sb) {
    var lg = (sb && sb.leagues || [])[0] || {};
    return (lg.calendar || []).map(function (d) { return String(typeof d === "string" ? d : (d.startDate || d.value || "")).slice(0, 10); })
      .filter(function (d) { return /^\d{4}-\d{2}-\d{2}$/.test(d); });
  }
  function seriesText(games) {
    var wins = {}, teams = {};
    games.forEach(function (g) {
      teams[g.home.tri] = 1; teams[g.away.tri] = 1;
      if (!g.final) return;
      var w = g.home.score > g.away.score ? g.home.tri : g.away.tri;
      wins[w] = (wins[w] || 0) + 1;
    });
    var ranked = Object.keys(teams).sort(function (a, b) { return (wins[b] || 0) - (wins[a] || 0); });
    if (!ranked.length || !wins[ranked[0]]) return "";
    var a = ranked[0], b = ranked[1] || "", wa = wins[a] || 0, wb = wins[b] || 0;
    if (wa === 4) return a + " wins " + wa + "-" + wb;
    if (wa === wb) return "Series tied " + wa + "-" + wb;
    return a + " leads " + wa + "-" + wb;
  }
  function finalsIndex(days, today, seasonText) {
    // the Finals are the season's last game days: read the last seven and keep the Finals games that have started
    var last = days.filter(function (d) { return d <= today; }).slice(-7);
    return Promise.all(last.map(function (d) { return scoreboard(d).catch(function () { return null; }); })).then(function (boards) {
      var games = [], seen = {};
      boards.forEach(function (b) {
        ((b && b.events) || []).forEach(function (e) {
          if (!realEvent(e)) return;
          var g = brief(e);
          if (g.finals && (g.final || g.live) && !seen[g.id]) { seen[g.id] = 1; games.push(g); }
        });
      });
      if (!games.length) return null;
      games.sort(function (a, b) { return String(a.when).localeCompare(String(b.when)); });
      var text = seriesText(games);
      games.forEach(function (g, i) { g.label = g.label || "Game " + (i + 1); g.series = text; });
      var live = games.filter(function (g) { return g.live; })[0];
      var year = String(games[0].when).slice(0, 4);
      return { mode: "finals", label: year + " NBA Finals", season: seasonText, games: games,
        "default": live ? live.id : games[games.length - 1].id };
    });
  }
  function espnIndex() {
    var today = etDay(new Date().toISOString());
    return scoreboard().then(function (sb) {
      var lg = (sb.leagues || [])[0] || {}, season = lg.season || {};
      var seasonText = season.displayName || "";
      var days = calendarDays(sb);
      var todays = (sb.events || []).filter(realEvent).map(brief);
      var live = todays.filter(function (g) { return g.live; });
      var done = todays.filter(function (g) { return g.final; });
      if (live.some(function (g) { return g.finals; })) return finalsIndex(days, today, seasonText);
      if (live.length) {
        return { mode: "live", label: "Live now", season: seasonText, games: live.concat(done).slice(0, 15), "default": live[0].id };
      }
      // the latest game days that had real games (checking back at most three game days: during the preseason
      // there are none, so the last Finals stay up until opening night)
      var past = days.filter(function (d) { return d < today; }).reverse().slice(0, 3);
      var look = done.length ? Promise.resolve([done]) : Promise.all(past.map(function (d) {
        return scoreboard(d).then(function (b) {
          return ((b && b.events) || []).filter(realEvent).map(brief).filter(function (g) { return g.final; });
        }).catch(function () { return []; });
      }));
      return look.then(function (lists) {
        var k = -1;
        for (var i = 0; i < lists.length; i++) { if (lists[i].length) { k = i; break; } }
        if (k >= 0) {
          var latest = lists[k];
          if (latest.some(function (g) { return g.finals; })) return finalsIndex(days, today, seasonText);
          var games = latest.concat(lists[k + 1] && latest.length < 6 ? lists[k + 1] : []).slice(0, 15);
          return { mode: "recent", label: "Latest games", season: seasonText, games: games, "default": games[0].id };
        }
        // nothing played yet this season: the last Finals (the previous season's final game days)
        var prevYear = (parseInt(season.year, 10) || new Date().getFullYear()) - 1;
        var prevSeason = (prevYear - 1) + "-" + String(prevYear).slice(2);
        return scoreboard(prevYear + "0615").then(function (old) {
          return finalsIndex(calendarDays(old), today, prevSeason);
        });
      });
    });
  }
  function clockLeft(v) {
    var s = String(v == null ? "" : v);
    if (s.indexOf(":") >= 0) { var p = s.split(":"); return num(p[0]) * 60 + num(p[1]); }
    return num(s);
  }
  function elapsed(period, clock) {
    var p = Math.max(1, parseInt(period, 10) || 1), len = p <= 4 ? 720 : 300;
    var before = 720 * Math.min(p - 1, 4) + 300 * Math.max(0, p - 5);
    return Math.round((before + len - Math.min(len, clockLeft(clock))) * 10) / 10;
  }
  function fromSummary(s, id) {
    var comp = ((s.header || {}).competitions || [])[0] || {};
    var status = (comp.status || {}).type || {};
    var sides = {}, home = null, away = null;
    (comp.competitors || []).forEach(function (c) {
      var t = teamBrief(c);
      t.id = String(c.id || (c.team && c.team.id));
      t.periods = (c.linescores || []).map(function (l) { return num(l.displayValue != null ? l.displayValue : l.value); });
      t.stats = {};
      if (c.homeAway === "home") home = t; else away = t;
      sides[t.id] = c.homeAway === "home" ? "home" : "away";
    });
    if (!home || !away) throw new Error("no teams");
    ((s.boxscore || {}).teams || []).forEach(function (bt) {
      var t = sides[String(bt.team && bt.team.id)] === "home" ? home : away, st = {};
      (bt.statistics || []).forEach(function (x) { st[x.name] = x.displayValue; });
      t.stats = {
        fg: st["fieldGoalsMade-fieldGoalsAttempted"], fgPct: st.fieldGoalPct != null ? num(st.fieldGoalPct) : null,
        tp: st["threePointFieldGoalsMade-threePointFieldGoalsAttempted"], tpPct: st.threePointFieldGoalPct != null ? num(st.threePointFieldGoalPct) : null,
        ft: st["freeThrowsMade-freeThrowsAttempted"], reb: num(st.totalRebounds), ast: num(st.assists),
        tov: num(st.totalTurnovers != null ? st.totalTurnovers : st.turnovers), stl: num(st.steals), blk: num(st.blocks),
        paint: st.pointsInPaint != null ? num(st.pointsInPaint) : null, fastBreak: st.fastBreakPoints != null ? num(st.fastBreakPoints) : null,
        tovPts: st.turnoverPoints != null ? num(st.turnoverPoints) : null, biggestLead: num(st.largestLead)
      };
    });
    var players = [];
    ((s.boxscore || {}).players || []).forEach(function (bp) {
      var side = sides[String(bp.team && bp.team.id)] || "away", bench = 0;
      var block = (bp.statistics || [])[0] || {}, keys = block.keys || [];
      (block.athletes || []).forEach(function (a) {
        if (a.didNotPlay || !a.stats || !a.stats.length) return;
        var v = {};
        keys.forEach(function (k, i) { v[k] = a.stats[i]; });
        var pair = function (k) { var p = String(v[k] || "0-0").split("-"); return [num(p[0]), num(p[1])]; };
        var fg = pair("fieldGoalsMade-fieldGoalsAttempted"), tp = pair("threePointFieldGoalsMade-threePointFieldGoalsAttempted"),
          ft = pair("freeThrowsMade-freeThrowsAttempted"), ath = a.athlete || {};
        var p = { id: String(ath.id), name: ath.displayName || "", short: ath.shortName || ath.displayName || "", team: side,
          starter: !!a.starter, pos: (ath.position || {}).abbreviation || "", min: String(v.minutes || "0"),
          pts: num(v.points), reb: num(v.rebounds), ast: num(v.assists), stl: num(v.steals), blk: num(v.blocks),
          tov: num(v.turnovers), fgm: fg[0], fga: fg[1], tpm: tp[0], tpa: tp[1], ftm: ft[0], fta: ft[1],
          pm: num(v.plusMinus), img: (ath.headshot || {}).href || "" };
        if (!p.starter) bench += p.pts;
        players.push(p);
      });
      (side === "home" ? home : away).stats.benchPts = bench;
    });
    var shots = [], flow = [[0, 0, 0]], assists = [], scoring = [], lastH = 0, lastA = 0;
    (s.plays || []).forEach(function (pl) {
      var t = elapsed(pl.period && pl.period.number, pl.clock && pl.clock.displayValue);
      var side = sides[String(pl.team && pl.team.id)] === "home" ? 0 : 1;
      var parts = pl.participants || [], pid = parts[0] && parts[0].athlete ? String(parts[0].athlete.id) : null;
      var c = pl.coordinate || {}, type = String((pl.type && pl.type.text) || "");
      var value = pl.pointsAttempted === 3 || pl.pointsAttempted === 2 ? pl.pointsAttempted : (pl.scoreValue === 3 ? 3 : 2);
      if (pl.shootingPlay && !/free throw/i.test(type) && pl.pointsAttempted !== 1 && Math.abs(c.x) < 100 && Math.abs(c.y) < 100) {
        var X = Math.round((c.x - 25) * 10), Y = Math.round(c.y * 10), made = pl.scoringPlay ? 1 : 0;
        shots.push([t, pid, side, X, Y, made, value, pl.period && pl.period.number]);
        if (made && parts[1] && parts[1].athlete && /assist/i.test(pl.text || "")) {
          assists.push([String(parts[1].athlete.id), pid, side, X, Y, value]);
        }
      }
      if (pl.homeScore != null && pl.awayScore != null) {
        var h = num(pl.homeScore), a = num(pl.awayScore);
        if (h !== lastH || a !== lastA) {
          flow.push([t, h, a]);
          var pts = h !== lastH ? h - lastH : a - lastA;
          if (pid && pts > 0 && pl.scoringPlay) scoring.push([t, pid, pts]);
          lastH = h; lastA = a;
        }
      }
    });
    var leadChanges = 0, timesTied = 0, leader = 0, wasTied = true;
    flow.forEach(function (f, i) {
      var now = (f[1] > f[2]) - (f[1] < f[2]);
      if (now && leader && now !== leader) leadChanges++;
      if (i && !now && !wasTied) timesTied++;
      wasTied = !now;
      leader = now || leader;
    });
    var live = status.state === "in";
    var brief0 = (index && index.games || []).filter(function (g) { return g.id === String(id); })[0] || {};
    return { id: String(id), label: brief0.label || "", series: brief0.series || "", date: niceDay(comp.date),
      status: status.shortDetail || status.detail || "", live: live, final: status.state === "post",
      clock: live ? (status.shortDetail || "") : "", home: home, away: away, players: players, shots: shots, flow: flow,
      assists: assists, scoring: scoring, leadChanges: leadChanges, timesTied: timesTied };
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function el(tag, cls, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }
  function lastName(p) {
    var parts = String((p && (p.short || p.name)) || "").split(" ");
    return parts[parts.length - 1] || "";
  }
  function hexRgb(h) {
    var m = /^#?([0-9a-f]{6})$/i.exec(h || "");
    if (!m) return [212, 175, 55];
    var n = parseInt(m[1], 16);
    return [n >> 16 & 255, n >> 8 & 255, n & 255];
  }
  function colors(g) {
    var a = g.home.color || "#D4AF37", b = g.away.color || "#e8e8e8";
    var x = hexRgb(a), y = hexRgb(b);
    var d = Math.sqrt(Math.pow(x[0] - y[0], 2) + Math.pow(x[1] - y[1], 2) + Math.pow(x[2] - y[2], 2));
    return { home: a, away: d < 110 ? "#e8e8e8" : b };
  }
  function teamOf(g, side) { return side === "home" || side === 0 ? g.home : g.away; }
  function gameEnd(g) {
    var last = g.flow && g.flow.length ? g.flow[g.flow.length - 1][0] : 2880;
    return Math.max(2880, last, g.shots && g.shots.length ? g.shots[g.shots.length - 1][0] : 0);
  }
  function clockAt(t) {
    var q, left;
    if (t < 2880) { q = Math.floor(t / 720) + 1; left = 720 - (t - (q - 1) * 720); return "Q" + Math.min(q, 4) + " " + mmss(left); }
    q = Math.floor((t - 2880) / 300) + 1; left = 300 - (t - 2880 - (q - 1) * 300);
    return "OT" + (q > 1 ? q : "") + " " + mmss(left);
  }
  function mmss(s) { s = Math.max(0, Math.round(s)); return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2); }
  function playerById(g) {
    var m = {};
    (g.players || []).forEach(function (p) { m[p.id] = p; });
    return m;
  }
  function countUp(node, to, ms, fmt) {
    fmt = fmt || function (v) { return String(Math.round(v)); };
    if (REDUCE) { node.textContent = fmt(to); return; }
    var t0 = performance.now();
    (function step(now) {
      var p = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - p, 3);
      node.textContent = fmt(to * e);
      if (p < 1) requestAnimationFrame(step);
    })(t0);
  }
  function drawIn(path) {
    if (REDUCE || !path.getTotalLength) return;
    var len = path.getTotalLength();
    path.style.setProperty("--len", len);
    path.classList.add("ls-draw");
  }
  function gameOptionLabel(g) {
    var score = g.away.tri + " " + g.away.score + "–" + g.home.score + " " + g.home.tri;
    return (index.mode === "finals" && g.label ? g.label + ": " : "") + score + (g.live ? " (live)" : "");
  }
  function courtLines(stroke) {
    return '<g fill="none" stroke="' + (stroke || "#4a463d") + '" stroke-width="2" stroke-linecap="round">' +
      '<line x1="-250" y1="' + BASE_Y + '" x2="250" y2="' + BASE_Y + '"/>' +
      '<rect x="-80" y="' + (TOP - 142.5) + '" width="160" height="190"/>' +
      '<circle cx="0" cy="' + (TOP - 142.5) + '" r="60"/>' +
      '<path d="M -40 ' + TOP + ' A 40 40 0 0 1 40 ' + TOP + '"/>' +
      '<line x1="-30" y1="' + (TOP + 7.5) + '" x2="30" y2="' + (TOP + 7.5) + '"/>' +
      '<circle cx="0" cy="' + TOP + '" r="7.5"/>' +
      '<path d="M -220 ' + BASE_Y + ' L -220 ' + Y89 + ' A 237.5 237.5 0 0 1 220 ' + Y89 + ' L 220 ' + BASE_Y + '"/>' +
      '</g>';
  }
  var SVGNS = "http://www.w3.org/2000/svg";

  // ------------------------------------------------------------ a card with its own dropdowns
  function makeCard(opts) {
    var card = el("div", "ls-card" + (opts.wide ? " wide" : ""));
    var top = el("div", "ls-card-top");
    top.appendChild(el("div", "ls-title", esc(opts.title)));
    var pickers = el("div", "ls-pickers");
    top.appendChild(pickers);
    card.appendChild(top);
    var body = el("div", "ls-body");
    card.appendChild(body);
    var state = { gameId: index["default"], sub: null, stop: null };

    var gameSel = el("select", "ls-select");
    gameSel.setAttribute("aria-label", opts.title + ": game");
    index.games.forEach(function (g) {
      var o = el("option", null, esc(gameOptionLabel(g)));
      o.value = g.id;
      if (g.id === state.gameId) o.selected = true;
      gameSel.appendChild(o);
    });
    if (index.games.length > 1) pickers.appendChild(gameSel);
    var subSel = null;
    if (opts.sub) {
      subSel = el("select", "ls-select");
      subSel.setAttribute("aria-label", opts.title + ": " + opts.sub);
      pickers.appendChild(subSel);
      subSel.addEventListener("change", function () { state.sub = subSel.value; draw(); });
    }
    gameSel.addEventListener("change", function () { state.gameId = gameSel.value; draw(); });

    function fillSub(g) {
      var items = opts.subItems(g);
      if (!items.some(function (it) { return it[0] === state.sub; })) state.sub = items.length ? items[0][0] : null;
      subSel.innerHTML = "";
      items.forEach(function (it) {
        var o = el("option", null, esc(it[1]));
        o.value = it[0];
        if (it[0] === state.sub) o.selected = true;
        subSel.appendChild(o);
      });
    }
    function draw() {
      if (state.stop) { state.stop(); state.stop = null; }
      loadGame(state.gameId).then(function (g) {
        if (subSel) fillSub(g);
        body.innerHTML = "";
        state.stop = opts.render(body, g, state.sub, card) || null;
      }).catch(function () {
        body.innerHTML = '<div class="ls-foot">This game couldn\'t be loaded right now.</div>';
      });
    }
    card._draw = draw;
    card._refresh = function (liveNow) {
      Array.prototype.forEach.call(gameSel.options, function (o) {
        var g = index.games.filter(function (x) { return x.id === o.value; })[0];
        if (g) o.textContent = gameOptionLabel(g);
      });
      if (liveNow[state.gameId]) draw();
    };
    draw();
    return card;
  }

  function playerItems(g, withAll) {
    var c = colors(g);
    var items = withAll ? [["all", "All shots"], ["team:home", g.home.tri + " shots"], ["team:away", g.away.tri + " shots"]] : [];
    (g.players || []).slice().sort(function (a, b) { return b.pts - a.pts; }).forEach(function (p) {
      if (withAll && !p.fga) return;
      items.push([String(p.id), (p.short || p.name) + " · " + teamOf(g, p.team).tri]);
    });
    return items;
  }

  // ------------------------------------------------------------ 1. scoreboard + game flow
  function renderScore(body, g) {
    var c = colors(g);
    var homeWin = g.home.score >= g.away.score;
    [["away", g.away, c.away, !homeWin], ["home", g.home, c.home, homeWin]].forEach(function (row) {
      var r = el("div", "ls-team" + (row[3] && g.final ? " win" : ""),
        '<span class="tri"><i style="background:' + row[2] + '"></i>' + esc(row[1].city ? row[1].name : row[1].tri) +
        ' <span style="color:#8c867b;font-weight:400;font-size:12px">' + esc(row[1].tri) + '</span></span><span class="sc">0</span>');
      body.appendChild(r);
      countUp(r.querySelector(".sc"), row[1].score, 1600);
    });
    var n = Math.max(g.home.periods.length, g.away.periods.length);
    var head = "<tr><th></th>", ra = "<tr><td>" + esc(g.away.tri) + "</td>", rh = "<tr><td>" + esc(g.home.tri) + "</td>";
    for (var i = 0; i < n; i++) {
      head += "<th>" + (i < 4 ? i + 1 : "OT" + (i > 4 ? i - 3 : "")) + "</th>";
      ra += "<td>" + (g.away.periods[i] == null ? "" : g.away.periods[i]) + "</td>";
      rh += "<td>" + (g.home.periods[i] == null ? "" : g.home.periods[i]) + "</td>";
    }
    body.appendChild(el("table", "ls-qtable", head + "<th>T</th></tr>" + ra + '<td class="t">' + g.away.score + "</td></tr>" +
      rh + '<td class="t">' + g.home.score + "</td></tr>"));
    // the game-flow line: home lead above the middle, away lead below
    var W = 330, H = 92, end = gameEnd(g), maxAbs = 5;
    g.flow.forEach(function (f) { maxAbs = Math.max(maxAbs, Math.abs(f[1] - f[2])); });
    var X = function (t) { return 4 + (W - 8) * t / end; }, Y = function (m) { return H / 2 - (H / 2 - 8) * m / maxAbs; };
    var d = "M " + X(0).toFixed(1) + " " + Y(0).toFixed(1), prevY = Y(0);
    g.flow.forEach(function (f) {
      var y = Y(f[1] - f[2]);
      d += " L " + X(f[0]).toFixed(1) + " " + prevY.toFixed(1) + " L " + X(f[0]).toFixed(1) + " " + y.toFixed(1);
      prevY = y;
    });
    d += " L " + X(end).toFixed(1) + " " + prevY.toFixed(1);
    var qlines = "";
    for (var q = 1; q < 4; q++) qlines += '<line x1="' + X(q * 720) + '" x2="' + X(q * 720) + '" y1="4" y2="' + (H - 4) + '" stroke="#2a2721"/>';
    var svg = el("div", null,
      '<svg class="ls-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Score margin through the game">' +
      '<rect x="0" y="0" width="' + W + '" height="' + H + '" fill="none"/>' + qlines +
      '<line x1="4" x2="' + (W - 4) + '" y1="' + H / 2 + '" y2="' + H / 2 + '" stroke="#3a362e" stroke-dasharray="3 3"/>' +
      '<text x="6" y="12" font-size="9" fill="' + c.home + '">' + esc(g.home.tri) + ' lead</text>' +
      '<text x="6" y="' + (H - 4) + '" font-size="9" fill="' + c.away + '">' + esc(g.away.tri) + ' lead</text>' +
      '<path d="' + d + '" fill="none" stroke="#F5D370" stroke-width="1.8" stroke-linejoin="round"/></svg>');
    body.appendChild(svg);
    drawIn(svg.querySelector("path"));
    var foot = [g.series, g.date, g.live ? "Live · " + g.clock : g.status].filter(Boolean).join(" · ");
    body.appendChild(el("div", "ls-foot", esc(foot)));
  }

  // ------------------------------------------------------------ 2. shot chart replay
  function renderShots(body, g, sub, card) {
    var c = colors(g), byId = playerById(g);
    var shots = g.shots.filter(function (s) {
      if (!sub || sub === "all") return true;
      if (sub === "team:home") return s[2] === 0;
      if (sub === "team:away") return s[2] === 1;
      return String(s[1]) === sub;
    });
    var wrap = el("div", null, '<svg class="ls-svg" viewBox="-252 -2 504 381.5" role="img" aria-label="Shots in game order">' +
      '<rect x="-252" y="-2" width="504" height="381.5" fill="#0e0d0b" rx="10"/>' + courtLines() + '<g></g></svg>');
    body.appendChild(wrap);
    var layer = wrap.querySelector("g:last-of-type");
    var stats = el("div", "ls-stats", '<div><span>Plotted</span><b class="n">0</b></div><div><span>FG%</span><b class="f">–</b></div>' +
      '<div><span>Threes</span><b class="t">0/0</b></div>');
    body.appendChild(stats);
    var label = sub && sub !== "all" ? (sub.indexOf("team:") === 0 ? teamOf(g, sub.slice(5)).name : (byId[sub] || {}).name || "") : "Both teams";
    var foot = el("div", "ls-foot", esc(label) + " · every shot in game order");
    body.appendChild(foot);
    var i = 0, made = 0, tpm = 0, tpa = 0, timer = null, alive = true;
    function add(s) {
      var col = s[2] === 0 ? c.home : c.away;
      var x = s[3], y = TOP - s[4];
      var node;
      if (s[5]) {
        node = document.createElementNS(SVGNS, "circle");
        node.setAttribute("cx", x); node.setAttribute("cy", y); node.setAttribute("r", 7);
        node.setAttribute("fill", col); node.setAttribute("stroke", "#0e0d0b"); node.setAttribute("stroke-width", 1.5);
      } else {
        node = document.createElementNS(SVGNS, "path");
        node.setAttribute("d", "M" + (x - 5) + " " + (y - 5) + " L" + (x + 5) + " " + (y + 5) + " M" + (x + 5) + " " + (y - 5) + " L" + (x - 5) + " " + (y + 5));
        node.setAttribute("stroke", "#8f887a"); node.setAttribute("stroke-width", 2.2); node.setAttribute("fill", "none");
      }
      node.style.transformBox = "fill-box"; node.style.transformOrigin = "center";
      layer.appendChild(node);
      if (!REDUCE && node.animate) node.animate([{ opacity: 0, transform: "scale(2.2)" }, { opacity: 1, transform: "scale(1)" }],
        { duration: 380, easing: "ease-out" });
      made += s[5]; if (s[6] === 3) { tpa++; tpm += s[5]; }
    }
    function update() {
      stats.querySelector(".n").textContent = i + "/" + shots.length;
      stats.querySelector(".f").textContent = i ? Math.round(100 * made / i) + "%" : "–";
      stats.querySelector(".t").textContent = tpm + "/" + tpa;
    }
    function restart() {
      layer.innerHTML = ""; i = made = tpm = tpa = 0; update();
      if (REDUCE) { shots.forEach(add); i = shots.length; update(); return; }
      var gap = Math.max(35, Math.min(160, 9000 / Math.max(1, shots.length)));
      timer = setInterval(function () {
        if (!alive) return;
        if (card && card._hidden) return;
        if (i >= shots.length) { clearInterval(timer); timer = setTimeout(restart, 3500); return; }
        add(shots[i]); i++; update();
      }, gap);
    }
    restart();
    return function () { alive = false; clearInterval(timer); clearTimeout(timer); };
  }

  // ------------------------------------------------------------ 3. player card
  function renderPlayer(body, g, sub) {
    var byId = playerById(g), p = byId[sub] || (g.players || [])[0];
    if (!p) { body.appendChild(el("div", "ls-foot", "No player stats for this game.")); return; }
    var team = teamOf(g, p.team), c = colors(g), col = p.team === "home" ? c.home : c.away;
    body.appendChild(el("div", "ls-player", '<img alt="" loading="lazy" src="' + esc(p.img || HEADSHOT + p.id + ".png") + '" onerror="this.style.visibility=\'hidden\'">' +
      '<div><div class="nm">' + esc(p.name) + '</div><div class="tm">' + esc(team.city + " " + team.name) + (p.min ? " · " + esc(p.min) + " min" : "") + '</div></div>'));
    var s1 = el("div", "ls-stats", '<div><span>Points</span><b>0</b></div><div><span>Rebounds</span><b>0</b></div><div><span>Assists</span><b>0</b></div>');
    body.appendChild(s1);
    var bs = s1.querySelectorAll("b");
    countUp(bs[0], p.pts, 1200); countUp(bs[1], p.reb, 1200); countUp(bs[2], p.ast, 1200);
    body.appendChild(el("div", "ls-stats", '<div><span>FG</span><b>' + p.fgm + "/" + p.fga + '</b></div><div><span>3PT</span><b>' +
      p.tpm + "/" + p.tpa + '</b></div><div><span>+/-</span><b>' + (p.pm > 0 ? "+" : "") + p.pm + "</b></div>"));
    // points through the game
    var W = 270, H = 58, end = gameEnd(g), pts = [[0, 0]], tot = 0;
    (g.scoring || []).forEach(function (s) { if (s[1] === p.id) { tot += s[2]; pts.push([s[0], tot]); } });
    pts.push([end, tot]);
    var X = function (t) { return 3 + (W - 6) * t / end; }, Y = function (v) { return H - 4 - (H - 10) * v / Math.max(10, tot); };
    var d = "M " + pts.map(function (q, k) {
      return X(q[0]).toFixed(1) + " " + Y(k ? pts[k - 1][1] : 0).toFixed(1) + " L " + X(q[0]).toFixed(1) + " " + Y(q[1]).toFixed(1);
    }).join(" L ");
    var svg = el("div", null, '<div class="ls-title" style="margin-bottom:4px">Points through the game</div>' +
      '<svg class="ls-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Points through the game">' +
      '<path d="' + d + ' L ' + X(end) + ' ' + (H - 4) + ' L ' + X(0) + ' ' + (H - 4) + ' Z" fill="' + col + '" fill-opacity=".12"/>' +
      '<path class="ln" d="' + d + '" fill="none" stroke="' + col + '" stroke-width="2"/></svg>');
    body.appendChild(svg);
    drawIn(svg.querySelector("path.ln"));
  }

  // ------------------------------------------------------------ 4. scoring race
  function renderRace(body, g, sub, card) {
    var c = colors(g), byId = playerById(g);
    var top = (g.players || []).slice().sort(function (a, b) { return b.pts - a.pts; }).slice(0, 8);
    var ids = top.map(function (p) { return p.id; });
    var box = el("div", "ls-race");
    box.style.height = (top.length * 26) + "px";
    body.appendChild(box);
    var rows = top.map(function (p) {
      var r = el("div", "ls-rrow", '<span class="n">' + esc(lastName(p)) + '</span><span class="b"><i style="background:' +
        (p.team === "home" ? c.home : c.away) + '"></i></span><span class="v">0</span>');
      box.appendChild(r);
      return r;
    });
    var clock = el("div", "ls-foot", "");
    body.appendChild(clock);
    var end = gameEnd(g), maxPts = Math.max.apply(null, top.map(function (p) { return p.pts; }).concat([1]));
    var events = (g.scoring || []).filter(function (s) { return ids.indexOf(s[1]) >= 0; });
    var t = 0, k = 0, pts = {}, timer = null, alive = true;
    function render() {
      var order = ids.slice().sort(function (a, b) { return (pts[b] || 0) - (pts[a] || 0) || ids.indexOf(a) - ids.indexOf(b); });
      ids.forEach(function (id, j) {
        var r = rows[j], v = pts[id] || 0, rank = order.indexOf(id);
        r.style.transform = "translateY(" + (rank * 26) + "px)";
        r.querySelector("i").style.width = (100 * v / maxPts) + "%";
        r.querySelector(".v").textContent = v;
      });
      clock.textContent = t >= end ? "Final · " + (byId[order[0]] ? byId[order[0]].name + " led the way" : "") : clockAt(t);
    }
    function restart() {
      t = 0; k = 0; pts = {}; render();
      if (REDUCE) { events.forEach(function (s) { pts[s[1]] = (pts[s[1]] || 0) + s[2]; }); t = end; render(); return; }
      timer = setInterval(function () {
        if (!alive || (card && card._hidden)) return;
        t = Math.min(end, t + end / 90);
        while (k < events.length && events[k][0] <= t) { pts[events[k][1]] = (pts[events[k][1]] || 0) + events[k][2]; k++; }
        render();
        if (t >= end) { clearInterval(timer); timer = setTimeout(restart, 4000); }
      }, 110);
    }
    restart();
    return function () { alive = false; clearInterval(timer); clearTimeout(timer); };
  }

  // ------------------------------------------------------------ 5. assist web
  function renderAssists(body, g, sub, card) {
    var side = sub === "away" ? 1 : 0, team = side ? g.away : g.home, c = colors(g), col = side ? c.away : c.home;
    var byId = playerById(g);
    var pairs = {};
    (g.assists || []).forEach(function (a) {
      if (a[2] !== side) return;
      var key = a[0] + ">" + a[1];
      pairs[key] = (pairs[key] || 0) + 1;
    });
    var involved = {};
    Object.keys(pairs).forEach(function (k) { var ab = k.split(">"); involved[ab[0]] = (involved[ab[0]] || 0) + pairs[k]; involved[ab[1]] = (involved[ab[1]] || 0) + pairs[k]; });
    var nodes = Object.keys(involved).sort(function (a, b) { return involved[b] - involved[a]; }).slice(0, 8);
    if (!nodes.length) { body.appendChild(el("div", "ls-foot", "No assists recorded for " + esc(team.name) + " in this game.")); return; }
    var W = 330, H = 250, cx = W / 2, cy = H / 2 + 4, R = 88, pos = {};
    nodes.forEach(function (id, i) {
      var a = -Math.PI / 2 + 2 * Math.PI * i / nodes.length;
      pos[id] = [cx + R * Math.cos(a), cy + R * Math.sin(a)];
    });
    var maxN = 1, list = [];
    Object.keys(pairs).forEach(function (k) {
      var ab = k.split(">");
      if (pos[ab[0]] && pos[ab[1]]) { list.push([ab[0], ab[1], pairs[k]]); maxN = Math.max(maxN, pairs[k]); }
    });
    list.sort(function (a, b) { return a[2] - b[2]; });
    var paths = "", labels = "";
    list.forEach(function (e, i) {
      var p1 = pos[e[0]], p2 = pos[e[1]];
      var mx = (p1[0] + p2[0]) / 2, my = (p1[1] + p2[1]) / 2;
      var qx = mx + (cx - mx) * 0.35, qy = my + (cy - my) * 0.35;
      paths += '<path class="arc" data-n="' + e[2] + '" d="M ' + p1[0].toFixed(1) + " " + p1[1].toFixed(1) + " Q " + qx.toFixed(1) + " " + qy.toFixed(1) +
        " " + p2[0].toFixed(1) + " " + p2[1].toFixed(1) + '" fill="none" stroke="' + col + '" stroke-opacity="' + (0.25 + 0.55 * e[2] / maxN).toFixed(2) +
        '" stroke-width="' + (1 + 5 * e[2] / maxN).toFixed(1) + '" stroke-linecap="round"/>';
    });
    nodes.forEach(function (id) {
      var p = pos[id], pl = byId[id] || {};
      var below = p[1] >= cy;
      labels += '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="' + (6 + 6 * involved[id] / involved[nodes[0]]).toFixed(1) +
        '" fill="#161513" stroke="' + col + '" stroke-width="2"/>' +
        '<text x="' + p[0].toFixed(1) + '" y="' + (p[1] + (below ? 24 : -16)).toFixed(1) + '" text-anchor="middle" font-size="11" font-weight="700" fill="#f0f0f0">' +
        esc(lastName(pl)) + "</text>";
    });
    var wrap = el("div", null, '<svg class="ls-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Who assisted whom">' +
      paths + '<g class="balls"></g>' + labels + "</svg>");
    body.appendChild(wrap);
    var best = list[list.length - 1];
    body.appendChild(el("div", "ls-foot", esc(team.name) + " · thicker line = more assists" +
      (best ? " · most: " + esc(lastName(byId[best[0]])) + " → " + esc(lastName(byId[best[1]])) + " (" + best[2] + ")" : "")));
    if (REDUCE) return;
    var arcs = wrap.querySelectorAll("path.arc"), balls = wrap.querySelector("g.balls"), dots = [], alive = true;
    Array.prototype.forEach.call(arcs, function (a, i) {
      var len = a.getTotalLength ? a.getTotalLength() : 0;
      var b = document.createElementNS(SVGNS, "circle");
      b.setAttribute("r", 3.4); b.setAttribute("fill", "#FFF0B8"); b.setAttribute("opacity", 0);
      balls.appendChild(b);
      dots.push({ a: a, b: b, len: len, period: 2600 - 1200 * (+a.getAttribute("data-n")) / maxN, off: (i * 0.37) % 1 });
    });
    var t0 = performance.now();
    (function frame(now) {
      if (!alive) return;
      if (!(card && card._hidden)) {
        dots.forEach(function (d) {
          if (!d.len) return;
          var p = ((now - t0) / d.period + d.off) % 1, pt = d.a.getPointAtLength(p * d.len);
          d.b.setAttribute("cx", pt.x.toFixed(1)); d.b.setAttribute("cy", pt.y.toFixed(1));
          d.b.setAttribute("opacity", Math.min(1, p * 6, (1 - p) * 6).toFixed(2));
        });
      }
      requestAnimationFrame(frame);
    })(t0);
    return function () { alive = false; };
  }

  // ------------------------------------------------------------ 6. team comparison
  function renderCompare(body, g) {
    var c = colors(g), h = g.home.stats || {}, a = g.away.stats || {};
    var rows = [["FG%", a.fgPct, h.fgPct, "%"], ["3PT%", a.tpPct, h.tpPct, "%"], ["Rebounds", a.reb, h.reb], ["Assists", a.ast, h.ast],
      ["Paint pts", a.paint, h.paint], ["Fast break", a.fastBreak, h.fastBreak], ["2nd chance", a.secondChance, h.secondChance],
      ["Turnovers", a.tov, h.tov], ["Pts off TOs", a.tovPts, h.tovPts], ["Bench pts", a.benchPts, h.benchPts]];
    var grid = el("div", "ls-cmp");
    grid.appendChild(el("div", "ls-cmp-row", '<span class="l" style="color:' + c.away + '">' + esc(g.away.tri) + '</span><span></span><span></span><span></span>' +
      '<span class="r" style="color:' + c.home + '">' + esc(g.home.tri) + "</span>"));
    rows.forEach(function (r) {
      if (r[1] == null && r[2] == null) return;
      var va = +r[1] || 0, vh = +r[2] || 0, max = Math.max(va, vh, 1);
      var row = el("div", "ls-cmp-row", '<span class="l">' + va + (r[3] || "") + '</span><span class="bar left"><i style="background:' + c.away +
        '"></i></span><span class="lbl">' + r[0] + '</span><span class="bar"><i style="background:' + c.home + '"></i></span><span class="r">' +
        vh + (r[3] || "") + "</span>");
      grid.appendChild(row);
      var bars = row.querySelectorAll("i");
      requestAnimationFrame(function () { requestAnimationFrame(function () {
        bars[0].style.width = (100 * va / max) + "%"; bars[1].style.width = (100 * vh / max) + "%";
      }); });
    });
    body.appendChild(grid);
  }

  // ------------------------------------------------------------ 7. count-up tiles
  function renderTiles(body, g) {
    var h = g.home.stats || {}, a = g.away.stats || {};
    var tpm = function (s) { return +(String(s.tp || "0-0").split("-")[0]) || 0; };
    var tiles = [[g.leadChanges || 0, "Lead changes"], [g.timesTied || 0, "Times tied"],
      [h.biggestLead || 0, "Biggest " + g.home.tri + " lead"], [a.biggestLead || 0, "Biggest " + g.away.tri + " lead"],
      [tpm(h) + tpm(a), "Threes made"], [(g.shots || []).length, "Shots charted"]];
    var box = el("div", "ls-tiles");
    tiles.forEach(function (t) {
      var d = el("div", "ls-tile", "<b>0</b><span>" + esc(t[1]) + "</span>");
      box.appendChild(d);
      countUp(d.querySelector("b"), t[0], 1400);
    });
    body.appendChild(box);
  }

  // ------------------------------------------------------------ ticker
  function ticker(g) {
    var items = [];
    if (index.label) items.push(["", index.label + (g.series ? " · " + g.series : "")]);
    index.games.forEach(function (x) {
      items.push([(index.mode === "finals" && x.label ? x.label : x.away.tri + " @ " + x.home.tri),
        x.away.tri + " " + x.away.score + ", " + x.home.tri + " " + x.home.score + (x.live ? " · LIVE" : x.final ? " · FINAL" : "")]);
    });
    (g.players || []).slice().sort(function (a, b) { return b.pts - a.pts; }).slice(0, 4).forEach(function (p) {
      items.push([p.name, p.pts + " PTS · " + p.reb + " REB · " + p.ast + " AST"]);
    });
    var one = items.map(function (it) {
      return "<span>" + esc(it[0]) + (it[0] ? " " : "") + "<b>" + esc(it[1]) + '</b></span><span class="sep">◆</span>';
    }).join("");
    var track = root.querySelector(".ls-ticker-track");
    if (track) track.innerHTML = one + one;
  }

  // ------------------------------------------------------------ auto-scroll
  function autoScroll(vp) {
    if (REDUCE) return;
    var pos = 0, paused = false, waitUntil = performance.now() + 2500, visible = true, holdEnd = 0;
    function later(ms) { waitUntil = Math.max(waitUntil, performance.now() + ms); pos = vp.scrollLeft; }
    vp.addEventListener("pointerenter", function () { paused = true; });
    vp.addEventListener("pointerleave", function () { paused = false; later(1200); });
    vp.addEventListener("focusin", function () { paused = true; });
    vp.addEventListener("focusout", function () { paused = false; later(2000); });
    vp.addEventListener("touchstart", function () { paused = true; }, { passive: true });
    vp.addEventListener("touchend", function () { paused = false; later(5000); }, { passive: true });
    vp.addEventListener("wheel", function () { later(4000); }, { passive: true });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) { visible = es[0].isIntersecting; }, { threshold: 0.2 }).observe(vp);
    }
    (function step(now) {
      var max = vp.scrollWidth - vp.clientWidth;
      if (!paused && visible && now >= waitUntil && max > 4) {
        if (holdEnd) {
          if (now >= holdEnd) {
            holdEnd = 0;
            vp.scrollTo({ left: 0, behavior: "smooth" });
            waitUntil = now + 2600;
            pos = 0;
          }
        } else {
          pos += 0.7;
          if (pos >= max) { pos = max; holdEnd = now + 2500; }
          vp.scrollLeft = Math.round(pos);
        }
      }
      requestAnimationFrame(step);
    })(performance.now());
  }

  // ------------------------------------------------------------ build
  function build() {
    var live = index.games.some(function (g) { return g.live; });
    var badge = root.querySelector(".ls-badge");
    badge.classList.toggle("live", live);
    badge.querySelector("span").textContent = live ? "Live now" : index.label || "Latest games";
    var sub = root.querySelector(".ls-sub");
    var first = index.games[0] || {};
    sub.textContent = index.mode === "finals"
      ? (first.series ? first.series + " · " : "") + "every game, replayed"
      : (live ? "Updating through the night" : "The latest games") + (index.season ? " · " + index.season : "");
    var track = root.querySelector(".ls-track");
    track.innerHTML = "";
    var cards = [
      makeCard({ title: "Final score · game flow", wide: true, render: renderScore }),
      makeCard({ title: "Shot chart replay", sub: "player", subItems: function (g) { return playerItems(g, true); }, render: renderShots }),
      makeCard({ title: "Player card", sub: "player", subItems: function (g) { return playerItems(g, false); }, render: renderPlayer }),
      makeCard({ title: "Scoring race", render: renderRace }),
      makeCard({ title: "Assist web", sub: "team", subItems: function (g) { return [["home", g.home.name], ["away", g.away.name]]; }, render: renderAssists }),
      makeCard({ title: "Team comparison", render: renderCompare }),
      makeCard({ title: "By the numbers", render: renderTiles }),
    ];
    cards.forEach(function (c) { track.appendChild(c); });
    if ("IntersectionObserver" in window) {
      var vp = root.querySelector(".ls-viewport");
      var io = new IntersectionObserver(function (es) {
        es.forEach(function (e) { e.target._hidden = !e.isIntersecting; });
      }, { root: vp, threshold: 0.05 });
      cards.forEach(function (c) { io.observe(c); });
    }
    loadGame(index["default"]).then(ticker).catch(function () {});
    autoScroll(root.querySelector(".ls-viewport"));
  }

  function start(data) {
    if (!data || !data.games || !data.games.length) return false;
    index = data;
    if (!index["default"]) index["default"] = index.games[0].id;
    root.hidden = false;
    build();
    return true;
  }
  function refreshLive() {
    // while games are live: every minute, fresh scores in the dropdowns and ticker, and cards showing a live game
    // redraw (unless the visitor is pointing at the strip)
    if (document.hidden || root.matches(":hover")) return;
    espnIndex().then(function (nx) {
      if (!nx || !nx.games || !nx.games.length) return;
      var liveNow = {};
      index.games.forEach(function (g) { if (g.live) liveNow[g.id] = 1; });
      nx.games.forEach(function (g) { if (g.live) liveNow[g.id] = 1; });
      Object.keys(liveNow).forEach(function (id) { delete cache[id]; });
      var known = {};
      index.games.forEach(function (g) { known[g.id] = g; });
      nx.games.forEach(function (g) { if (known[g.id]) { known[g.id].home.score = g.home.score; known[g.id].away.score = g.away.score;
        known[g.id].live = g.live; known[g.id].final = g.final; known[g.id].status = g.status; } });
      Array.prototype.forEach.call(root.querySelectorAll(".ls-card"), function (card) {
        if (card._refresh) card._refresh(liveNow);
      });
      loadGame(index["default"]).then(ticker).catch(function () {});
      var badge = root.querySelector(".ls-badge");
      var anyLive = index.games.some(function (g) { return g.live; });
      badge.classList.toggle("live", anyLive);
    }).catch(function () {});
  }
  espnIndex().then(function (data) {
    if (!start(data)) throw new Error("no ESPN games");
    if (index.games.some(function (g) { return g.live; })) setInterval(refreshLive, 60000);
  }).catch(function () {
    source = "static";
    getJSON(BASE + "index.json").then(start).catch(function () { /* no data anywhere: the strip stays hidden */ });
  });
})();
