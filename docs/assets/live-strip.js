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
   is used if it exists. The skinny ticker lists every one of those
   games (logo, score, logo, and a breathing dot + the clock while it's
   live); clicking a game there switches every card below to it. Every
   card also has its own small dropdowns (game, and player or team).
   Team logos go before team abbreviations everywhere; a team's own
   numbers are drawn in its colour, whole-game numbers in gold.
   No data at all: the strip stays hidden.
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
    ATL: "#E03A3E", BOS: "#18A659", BKN: "#C9C9C9", CHA: "#00778B", CHI: "#E0314B", CLE: "#FDBB30",
    DAL: "#1E7FD6", DEN: "#FEC524", DET: "#E0314B", GSW: "#FFC72C", HOU: "#E0314B", IND: "#FDBB30",
    LAC: "#3B82F6", LAL: "#FDB927", MEM: "#7D95C9", MIA: "#F25C54", MIL: "#EEE1C6", MIN: "#1F4399",
    NOP: "#B6995A", NYK: "#F58426", OKC: "#2E9BE6", ORL: "#2F8FE0", PHI: "#3B82F6", PHX: "#E56020",
    POR: "#E03A3E", SAC: "#A57FDB", SAS: "#C4CED4", TOR: "#E0314B", UTA: "#4F008F", WAS: "#E31837"
  };
  // a second colour for each team, used when both teams' main colours are too alike to tell apart
  var TEAM_ALT = {
    ATL: "#C1D32F", BOS: "#BA9653", BKN: "#FFFFFF", CHA: "#8C7FD6", CHI: "#FFFFFF", CLE: "#E07C95",
    DAL: "#B8C4CA", DEN: "#6F93D6", DET: "#3E8EDE", GSW: "#6F9BE8", HOU: "#C4CED4", IND: "#6F93D6",
    LAC: "#E0314B", LAL: "#9B6FD6", MEM: "#F5B112", MIA: "#F9A01B", MIL: "#2FA36B", MIN: "#78BE20",
    NOP: "#6F93D6", NYK: "#3E8EDE", OKC: "#F05133", ORL: "#C4CED4", PHI: "#ED174C", PHX: "#9B7FD6",
    POR: "#FFFFFF", SAC: "#C4CED4", SAS: "#FFFFFF", TOR: "#C4CED4", UTA: "#FFFFFF", WAS: "#6F93D6"
  };
  // ESPN's own abbreviation for each team (its logo files are named by it)
  var ESPN_ABBR = { GSW: "gs", NYK: "ny", SAS: "sa", NOP: "no", UTA: "utah", WAS: "wsh" };
  function logoFor(tri) {
    var t = String(tri || "").toUpperCase();
    return t ? "https://a.espncdn.com/i/teamlogos/nba/500/" + (ESPN_ABBR[t] || t.toLowerCase()) + ".png" : "";
  }
  function logoImg(team, size) {
    var src = (team && team.logo) || logoFor(team && team.tri);
    if (!src) return "";
    size = size || 16;
    return '<img class="ls-logo" alt="" loading="lazy" width="' + size + '" height="' + size + '" style="width:' + size + "px;height:" + size +
      'px" src="' + esc(src) + '" onerror="this.style.visibility=\'hidden\'">';
  }
  // "4th 10:10" -> "Q4 10:10", "End 3rd" -> "End Q3", "Final/5th" -> "Final/OT", "6th 2:00" -> "2OT 2:00"
  function qTick(t) {
    return String(t || "").replace(/\b(\d+)(?:st|nd|rd|th)\b/g, function (m, n) { n = +n; return n <= 4 ? "Q" + n : (n === 5 ? "" : n - 4) + "OT"; });
  }
  function triTag(team, size) { return logoImg(team, size) + esc(team.tri); }
  function svgLogo(team, x, y, size) {
    var src = (team && team.logo) || logoFor(team && team.tri);
    return src ? '<image href="' + esc(src) + '" x="' + x + '" y="' + y + '" width="' + size + '" height="' + size + '" preserveAspectRatio="xMidYMid meet"/>' : "";
  }
  function ordinal(p) {
    p = parseInt(p, 10) || 0;
    if (p > 4) return (p > 5 ? (p - 4) : "") + "OT";
    return p + (p === 1 ? "st" : p === 2 ? "nd" : p === 3 ? "rd" : "th");
  }
  // "3rd 7:37", "Half", "End 3rd", "Final", "Final/OT" -- or the tip-off time before a game
  function clockText(status) {
    var st = (status && status.type) || {}, p = status && status.period, name = String(st.name || "");
    if (st.state === "in") {
      if (/HALFTIME/i.test(name)) return "Half";
      if (/END_PERIOD/i.test(name)) return "End " + ordinal(p);
      return ordinal(p) + " " + (status.displayClock || "");
    }
    if (st.state === "post") return (parseInt(p, 10) || 0) > 4 ? "Final/" + ordinal(p) : "Final";
    return st.shortDetail || st.detail || "";
  }
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
    var t = c.team || {};
    var logo = t.logo || (t.logos && t.logos[0] && t.logos[0].href) || logoFor(tri);
    return { tri: tri, name: t.name || t.shortDisplayName || tri, city: t.location || "", logo: logo,
      score: num(c.score), color: TEAM_COLORS[tri] || "#D4AF37", alt: TEAM_ALT[tri] || "#e8e8e8" };
  }
  function brief(e) {
    var c = e.competitions[0], st = (e.status || c.status || {}).type || {}, home = null, away = null;
    c.competitors.forEach(function (t) { if (t.homeAway === "home") home = teamBrief(t); else away = teamBrief(t); });
    var note = (c.notes || []).map(function (n) { return n.headline || ""; }).join(" ");
    var game = /game\s*(\d+)/i.exec(note);
    return { id: String(e.id), label: game ? "Game " + game[1] : "", date: niceDay(e.date), day: etDay(e.date), when: e.date,
      status: st.shortDetail || st.detail || "", tick: clockText(e.status || c.status), live: st.state === "in",
      final: st.state === "post", series: "",
      finals: /nba finals/i.test(note) || !!(c.type && c.type.abbreviation === "FINAL"), home: home, away: away };
  }
  var boards = {};                                   // a past day's scoreboard, once fetched (today's is always fetched fresh)
  var knownDays = {};                                // every date in the season calendars seen so far
  function scoreboard(day) {
    var today = etDay(new Date().toISOString());
    if (day && day !== today && boards[day]) return boards[day];
    var p = getJSON(ESPN + "scoreboard" + (day ? "?dates=" + day.replace(/-/g, "") : "")).then(function (sb) {
      calendarDays(sb).forEach(function (d) { knownDays[d] = 1; });
      return sb;
    });
    if (day && day !== today) { boards[day] = p; p.catch(function () { delete boards[day]; }); }
    return p;
  }
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
      var fdays = [];
      games.forEach(function (g) { if (fdays.indexOf(g.day) < 0) fdays.push(g.day); });
      return { mode: "finals", label: year + " NBA Finals", season: seasonText, games: games, cardGames: games,
        days: fdays.reverse(), "default": live ? live.id : games[games.length - 1].id };
    });
  }
  // The last `n` days (newest first) that had at least one real game, with each day's games. `todays` is today's
  // list, already fetched.
  function findGameDays(cand, n, today, todays) {
    var found = [];
    function batch(i) {
      if (found.length >= n || i >= Math.min(cand.length, 45)) return Promise.resolve(found);
      var chunk = cand.slice(i, i + 7);
      return Promise.all(chunk.map(function (d) {
        if (d === today) return Promise.resolve(todays);
        return scoreboard(d).then(function (b) { return ((b && b.events) || []).filter(realEvent).map(brief); })
          .catch(function () { return []; });
      })).then(function (lists) {
        lists.forEach(function (games, k) { if (games.length && found.length < n) found.push({ day: chunk[k], games: games }); });
        return batch(i + 7);
      });
    }
    return batch(0);
  }
  // the first day after today (within a week) that has games: { day, games } or null
  function nextGameDay(days, today) {
    var limit = etDay(new Date(Date.now() + 7.5 * 864e5).toISOString());
    var cand = days.filter(function (d) { return d > today && d <= limit; });
    return Promise.all(cand.map(function (d) {
      return scoreboard(d).then(function (b) { return ((b && b.events) || []).filter(realEvent).map(brief); }).catch(function () { return []; });
    })).then(function (lists) {
      for (var i = 0; i < lists.length; i++) if (lists[i].length) return { day: cand[i], games: lists[i] };
      return null;
    });
  }
  function espnIndex() {
    var today = etDay(new Date().toISOString());
    return scoreboard().then(function (sb) {
      var lg = (sb.leagues || [])[0] || {}, season = lg.season || {};
      var seasonText = season.displayName || "";
      var days = calendarDays(sb);
      var todays = (sb.events || []).filter(realEvent).map(brief);
      if (todays.some(function (g) { return g.finals; })) return finalsIndex(days, today, seasonText);
      // during the season: the last 7 days that had games (today first when there are games today, even before tip-off);
      // with no games today, the next day with games in the coming week goes first ("UPCOMING GAMES")
      var cand = [today].concat(days.filter(function (d) { return d < today; }).reverse());
      var ahead = todays.length ? Promise.resolve(null) : nextGameDay(days, today);
      return Promise.all([findGameDays(cand, 7, today, todays), ahead]).then(function (res) {
        var found = res[0], next = res[1];
        if (found.length) {
          if (found[0].games.some(function (g) { return g.finals; })) return finalsIndex(days, today, seasonText);
          if (next) found.unshift(next);
          var idx = { mode: "season", label: "", season: seasonText, days: found.map(function (x) { return x.day; }), dayGames: {} };
          found.forEach(function (x) { idx.dayGames[x.day] = x.games; });
          applyDay(idx, found[0].day);
          return idx;
        }
        // nothing played yet this season (the offseason and preseason): the last Finals
        var prevYear = (parseInt(season.year, 10) || new Date().getFullYear()) - 1;
        var prevSeason = (prevYear - 1) + "-" + String(prevYear).slice(2);
        return scoreboard(prevYear + "0615").then(function (old) {
          return finalsIndex(calendarDays(old), today, prevSeason);
        });
      });
    });
  }
  // One day of the season on the tape: that day's games on the ticker, and the windows on them -- except that
  // before the first of today's games tips off the windows keep the last game day's games.
  function started(g) { return g.live || g.final; }
  function applyDay(idx, day) {
    var today = etDay(new Date().toISOString());
    var games = (idx.dayGames[day] || []).slice();
    idx.day = day;
    idx.games = games;
    var cards = games;
    if (day >= today && !games.some(started)) {
      var k = idx.days.indexOf(day), prev = idx.days[k + 1];
      if (prev && (idx.dayGames[prev] || []).length) cards = idx.dayGames[prev];
    }
    idx.cardGames = cards;
    var live = cards.filter(function (g) { return g.live; })[0], done = cards.filter(started)[0];
    idx["default"] = (live || done || cards[0] || {}).id;
    idx.selected = idx["default"];
  }
  // the header: "LIVE GAMES" while any game on the tape is live; otherwise during the Finals (and the offseason)
  // "2027 NBA Finals" and the series; during the season "TODAY'S GAMES" on a day with games still to come, "FINAL
  // SCORES" once they're all over, "UPCOMING GAMES" when there are none today but some in the next 7 days, and a
  // past day's date
  function headerText() {
    if (!index) return { badge: "", sub: "", live: false };
    var live = index.games.some(function (g) { return g.live; });
    var first = index.games[0] || {};
    if (index.mode !== "season") {
      return { badge: live ? "Live games" : (index.label || "Latest games"), sub: index.mode === "finals" ? (first.series || "") : "", live: live };
    }
    if (live) return { badge: "Live games", sub: "", live: true };
    var today = etDay(new Date().toISOString());
    if (index.day === today) {
      if (index.games.length && index.games.every(function (g) { return g.final; })) return { badge: "Final scores", sub: "", live: false };
      return { badge: "Today's games", sub: "", live: false };
    }
    if (index.day > today) return { badge: "Upcoming games", sub: "", live: false };
    return { badge: longDay(index.day + "T12:00:00-05:00"), sub: "", live: false, date: true };
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
    var lu = buildStints(s.plays || [], players, sides, live);
    var sit = live ? gameSituation(s, comp, players, sides, home, away) : null;
    return { id: String(id), label: brief0.label || "", series: brief0.series || "", date: niceDay(comp.date), when: comp.date,
      status: status.shortDetail || status.detail || "", tick: clockText(comp.status), live: live, final: status.state === "post",
      pre: status.state === "pre",
      clock: live ? (status.shortDetail || "") : "", home: home, away: away, players: players, shots: shots, flow: flow,
      assists: assists, scoring: scoring, leadChanges: leadChanges, timesTied: timesTied,
      stints: lu.stints, onNow: lu.onNow, starters: lu.starters, now: lu.now, situation: sit };
  }

  // ------------------------------------------------------------ timeouts left and the bonus (live games only)
  // Timeouts: ESPN's own count when the feed has one, otherwise counted from the play-by-play with the NBA's rules --
  // 7 a game, no more than 4 of them left for the 4th quarter and no more than 2 after its 3:00 mark, 2 per overtime.
  // Bonus: a team is in the bonus once the other team has 5 team fouls in the quarter (4 in overtime), or 2 in the
  // last 2:00 of it. Team fouls leave out offensive fouls and technicals.
  function gameSituation(s, comp, players, sides, home, away) {
    var sideOf = {}, out = { home: { timeouts: null, bonus: false }, away: { timeouts: null, bonus: false } };
    players.forEach(function (p) { sideOf[p.id] = p.team; });
    var st = comp.status || {}, per = parseInt(st.period, 10) || 1;
    var left = clockLeft(st.displayClock);
    var used = { home: { all: 0, q4: 0, q4late: 0, ot: 0 }, away: { all: 0, q4: 0, q4late: 0, ot: 0 } };
    var fouls = { home: { per: 0, late: 0 }, away: { per: 0, late: 0 } };
    var names = { home: normName(home.name), away: normName(away.name) };
    (s.plays || []).forEach(function (pl) {
      var p = (pl.period && pl.period.number) || 1, type = String((pl.type && pl.type.text) || ""), text = String(pl.text || "");
      var clk = clockLeft(pl.clock && pl.clock.displayValue);
      var parts = (pl.participants || []).map(function (x) { return x && x.athlete ? String(x.athlete.id) : null; }).filter(Boolean);
      var side = sides[String(pl.team && pl.team.id)] || null;
      if (/timeout/i.test(type + " " + text) && !/official|tv timeout/i.test(type + " " + text)) {
        if (!side) { var t = normName(text); side = t.indexOf(names.home) >= 0 ? "home" : t.indexOf(names.away) >= 0 ? "away" : null; }
        if (!side) return;
        var u = used[side];
        if (p <= 4) { u.all++; if (p === 4) { u.q4++; if (clk <= 180) u.q4late++; } } else if (p === per) u.ot++;
        return;
      }
      if (p === per && /foul/i.test(type) && !/offensive|technical|charge/i.test(type)) {
        var who = sideOf[parts[0]] || side;
        if (!who) return;
        fouls[who].per++;
        if (clk <= 120) fouls[who].late++;
      }
    });
    var sit = s.situation || comp.situation || {};
    ["home", "away"].forEach(function (k) {
      var u = used[k], rem;
      if (per <= 3) rem = 7 - u.all;
      else if (per === 4) { rem = Math.min(7 - u.all, 4 - u.q4); if (left <= 180) rem = Math.min(rem, 2 - u.q4late); }
      else rem = 2 - u.ot;
      var espn = sit[k + "Timeouts"];
      out[k].timeouts = typeof espn === "number" ? espn : Math.max(0, rem);
      var other = fouls[k === "home" ? "away" : "home"];
      out[k].bonus = other.per >= (per <= 4 ? 5 : 4) || other.late >= 2;
    });
    return out;
  }

  // ------------------------------------------------------------ who was on the floor, and how each lineup did
  // Every stretch of the game with the same ten players on the floor (a "stint"), from the play-by-play: each team
  // starts with its five starters, each "X enters the game for Y" swaps one player, and at the start of every later
  // quarter the five on the floor are worked out from who plays or gets subbed out before being subbed in (lineups
  // can change between quarters without a substitution being logged). For each stint and each team: points, field
  // goal and free throw attempts, offensive rebounds and turnovers -- enough to estimate possessions, and so a
  // lineup's net rating (points scored minus allowed per 100 possessions).
  function periodEnd(p) { return p <= 4 ? 720 * p : 2880 + 300 * (p - 4); }
  function normName(x) {
    var s = String(x || "");
    try { s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, ""); } catch (e) {}
    return s.toLowerCase().replace(/\b(jr|sr|ii|iii|iv)\b\.?/g, "").replace(/[^a-z]/g, "");
  }
  function buildStints(rawPlays, players, sides, live) {
    var sideOf = {}, byName = {}, starters = { home: [], away: [] };
    players.forEach(function (p) {
      sideOf[p.id] = p.team; byName[normName(p.name)] = p.id;
      if (p.starter && starters[p.team].length < 5) starters[p.team].push(p.id);
    });
    var plays = [], lastH = 0, lastA = 0;
    rawPlays.forEach(function (pl) {
      var per = (pl.period && pl.period.number) || 1, t = elapsed(per, pl.clock && pl.clock.displayValue);
      var type = String((pl.type && pl.type.text) || ""), text = String(pl.text || "");
      var parts = (pl.participants || []).map(function (x) { return x && x.athlete ? String(x.athlete.id) : null; }).filter(Boolean);
      var e = { t: t, per: per, type: type, side: sides[String(pl.team && pl.team.id)] || null, parts: parts, dh: 0, da: 0 };
      var m = /^(.+?) enters the game for (.+?)\.?$/i.exec(text);
      if (/substitution/i.test(type) || m) {
        var inId = (m && byName[normName(m[1])]) || parts[0], outId = (m && byName[normName(m[2])]) || parts[1];
        if (inId && outId) { e.sub = { inId: inId, outId: outId }; e.side = sideOf[inId] || sideOf[outId] || e.side; }
      }
      if (pl.homeScore != null && pl.awayScore != null) {
        var h = num(pl.homeScore), a = num(pl.awayScore);
        if (h >= lastH && a >= lastA) { e.dh = h - lastH; e.da = a - lastA; lastH = h; lastA = a; }
      }
      e.fga = !!pl.shootingPlay && !/free throw/i.test(type) && pl.pointsAttempted !== 1;
      e.fta = /free throw/i.test(type);
      e.oreb = /offensive (team )?rebound/i.test(type);
      e.tov = /turnover|traveling|double dribble|3-second|palming|offensive goaltending|backcourt/i.test(type) || /turnover/i.test(text);
      plays.push(e);
    });
    plays.sort(function (a, b) { return a.t - b.t; });                  // game order (ties keep the feed's order)
    var now = plays.length ? plays[plays.length - 1].t : 0;
    var maxPer = plays.reduce(function (m, e) { return Math.max(m, e.per); }, 1);
    var stints = [], on = { home: starters.home.slice(), away: starters.away.slice() };
    function blank() { return { pts: 0, fga: 0, fta: 0, oreb: 0, tov: 0 }; }
    var cur = null;
    function open(t) { cur = { t0: t, t1: t, home: on.home.slice(), away: on.away.slice(), h: blank(), a: blank() }; }
    function close(t) { if (cur) { cur.t1 = Math.max(cur.t0, t); if (cur.t1 > cur.t0 || cur.h.pts || cur.a.pts) stints.push(cur); cur = null; } }
    for (var per = 1; per <= maxPer; per++) {
      var inPer = plays.filter(function (e) { return e.per === per; });
      ["home", "away"].forEach(function (side) {
        if (per === 1 && starters[side].length === 5) { on[side] = starters[side].slice(); return; }
        var seen = {}, order = [];
        inPer.forEach(function (e) {
          if (e.sub && e.side === side) {
            if (!seen[e.sub.inId]) { seen[e.sub.inId] = "in"; order.push(e.sub.inId); }
            if (!seen[e.sub.outId]) { seen[e.sub.outId] = "out"; order.push(e.sub.outId); }
          } else if (!e.sub) {
            e.parts.forEach(function (id) { if (sideOf[id] === side && !seen[id]) { seen[id] = "play"; order.push(id); } });
          }
        });
        var five = order.filter(function (id) { return seen[id] !== "in"; });
        (on[side] || []).forEach(function (id) { if (five.length < 5 && five.indexOf(id) < 0 && seen[id] !== "in") five.push(id); });
        on[side] = five.slice(0, 5);
      });
      open(inPer.length ? Math.min(inPer[0].t, periodEnd(per) - (per <= 4 ? 720 : 300)) : periodEnd(per) - (per <= 4 ? 720 : 300));
      inPer.forEach(function (e) {
        if (e.sub) {
          var side = e.side, list = on[side];
          if (!list) return;
          var k = list.indexOf(e.sub.outId);
          if (list.indexOf(e.sub.inId) >= 0) return;                              // already on the floor: nothing changes
          close(e.t);
          if (k >= 0) list[k] = e.sub.inId; else if (list.length < 5) list.push(e.sub.inId); else list[list.length - 1] = e.sub.inId;
          open(e.t);
          return;
        }
        cur.h.pts += e.dh; cur.a.pts += e.da;
        var st = e.side === "home" ? cur.h : e.side === "away" ? cur.a : null;
        if (st) { if (e.fga) st.fga++; if (e.fta) st.fta++; if (e.oreb) st.oreb++; if (e.tov) st.tov++; }
      });
      close(live && per === maxPer ? now : periodEnd(per));
    }
    return { stints: stints, onNow: { home: on.home.slice(), away: on.away.slice() }, starters: starters, now: now };
  }
  function possOf(x) { return Math.max(0, x.fga + 0.44 * x.fta - x.oreb + x.tov); }
  // points for / against, possessions and seconds for `ids` (all of them on the floor together) -- for one team
  function lineupTotals(g, side, ids, upTo) {
    var r = { pf: 0, pa: 0, poss: 0, sec: 0 };
    (g.stints || []).forEach(function (st) {
      if (upTo != null && st.t1 > upTo) return;
      var five = st[side];
      for (var i = 0; i < ids.length; i++) if (five.indexOf(ids[i]) < 0) return;
      var mine = side === "home" ? st.h : st.a, theirs = side === "home" ? st.a : st.h;
      r.pf += mine.pts; r.pa += theirs.pts; r.poss += (possOf(mine) + possOf(theirs)) / 2; r.sec += st.t1 - st.t0;
    });
    r.net = r.poss >= 2 ? 100 * (r.pf - r.pa) / r.poss : null;
    return r;
  }
  function combos(list, k) {
    var out = [];
    (function rec(start, acc) {
      if (acc.length === k) { out.push(acc.slice()); return; }
      for (var i = start; i < list.length; i++) { acc.push(list[i]); rec(i + 1, acc); acc.pop(); }
    })(0, []);
    return out;
  }
  // every 2-, 3-, 4- and 5-man group inside one five, with its net rating so far
  function fiveBreakdown(g, side, five, upTo) {
    var out = {};
    [2, 3, 4, 5].forEach(function (k) {
      out[k] = combos(five, k).map(function (ids) { var r = lineupTotals(g, side, ids, upTo); r.ids = ids; return r; });
    });
    return out;
  }
  // one number for how good these five have been together: every group's net rating weighted by its possessions,
  // pulled toward 0 while there are only a few possessions to go on
  function fiveStrength(g, side, five, upTo) {
    if (!five || five.length < 2) return 0;
    var b = fiveBreakdown(g, side, five, upTo), sum = 0, w = 0, n = 0;
    [2, 3, 4, 5].forEach(function (k) { b[k].forEach(function (r) { n++; if (r.net != null && r.poss >= 2) { sum += r.net * r.poss; w += r.poss; } }); });
    if (!w) return 0;
    var per = w / n;                                       // possessions per group: about how long they've played together
    var v = (sum / w) * (per / (per + 60));                // half-trusted after ~60 possessions (about a half) together
    return Math.max(-15, Math.min(15, v));                 // never more than 15 points per 100 either way
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
  function colorGap(a, b) {
    var x = hexRgb(a), y = hexRgb(b);
    return Math.sqrt(Math.pow(x[0] - y[0], 2) + Math.pow(x[1] - y[1], 2) + Math.pow(x[2] - y[2], 2));
  }
  function colors(g) {
    // each team in its own colour; if the two are too alike, the away team switches to its second colour
    var a = g.home.color || TEAM_COLORS[g.home.tri] || "#D4AF37", b = g.away.color || TEAM_COLORS[g.away.tri] || "#e8e8e8";
    if (colorGap(a, b) < 110) {
      var alt = g.away.alt || TEAM_ALT[g.away.tri] || "#e8e8e8";
      b = colorGap(a, alt) >= 110 ? alt : "#e8e8e8";
    }
    return { home: a, away: b };
  }
  function sideColor(g, side) { var c = colors(g); return side === "home" || side === 0 ? c.home : c.away; }
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
  // the same, with each team's logo before its abbreviation (for the card dropdowns)
  function gameOptionHtml(g) {
    return (index.mode === "finals" && g.label ? esc(g.label) + ": " : "") + triTag(g.away, 14) + " " + g.away.score + "–" +
      g.home.score + " " + triTag(g.home, 14) + (g.live ? ' <span class="ls-live-word">live</span>' : "");
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

  // ------------------------------------------------------------ a small dropdown that can show logos
  // (a native <select> can only show plain text). items: [[value, html], ...]
  var openPicker = null;
  function closePicker() { if (openPicker) { openPicker.classList.remove("open"); openPicker.querySelector(".ls-pick-btn").setAttribute("aria-expanded", "false"); openPicker = null; } }
  document.addEventListener("click", function (e) { if (openPicker && !openPicker.contains(e.target)) closePicker(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closePicker(); });
  function makePicker(label, onPick) {
    var box = el("div", "ls-pick");
    var btn = el("button", "ls-pick-btn");
    btn.type = "button";
    btn.setAttribute("aria-label", label);
    btn.setAttribute("aria-haspopup", "listbox");
    btn.setAttribute("aria-expanded", "false");
    var list = el("div", "ls-pick-list");
    list.setAttribute("role", "listbox");
    box.appendChild(btn);
    box.appendChild(list);
    var value = null, items = [];
    function paint() {
      var cur = items.filter(function (it) { return it[0] === value; })[0] || items[0];
      btn.innerHTML = '<span class="v">' + (cur ? cur[1] : "") + "</span>";
      list.innerHTML = "";
      items.forEach(function (it) {
        var o = el("button", "ls-pick-opt" + (it[0] === value ? " on" : ""), it[1]);
        o.type = "button";
        o.setAttribute("role", "option");
        o.setAttribute("aria-selected", it[0] === value ? "true" : "false");
        o.addEventListener("click", function (e) {
          e.stopPropagation();
          closePicker();
          if (it[0] !== value) { value = it[0]; paint(); onPick(value); }
        });
        list.appendChild(o);
      });
    }
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var wasOpen = box.classList.contains("open");
      closePicker();
      if (!wasOpen) {
        box.classList.add("open");
        btn.setAttribute("aria-expanded", "true");
        openPicker = box;
        var on = list.querySelector(".on");
        if (on) list.scrollTop = on.offsetTop - 30;
      }
    });
    box._set = function (newItems, newValue) { items = newItems; value = newValue; paint(); };
    box._value = function () { return value; };
    return box;
  }

  // ------------------------------------------------------------ a card with its own dropdowns
  function makeCard(opts) {
    var card = el("div", "ls-card" + (opts.wide ? " wide" : "") + (opts.cls ? " " + opts.cls : ""));
    var top = el("div", "ls-card-top");
    var name = typeof opts.title === "function" ? (opts.name || "") : opts.title;
    var titleEl = el("div", "ls-title", esc(name));
    top.appendChild(titleEl);
    var pickers = el("div", "ls-pickers");
    top.appendChild(pickers);
    card.appendChild(top);
    var body = el("div", "ls-body");
    card.appendChild(body);
    var state = { gameId: index.selected || index["default"], sub: null, stop: null, mode: opts.mode ? opts.mode.def : null };

    function cardGames() { return index.cardGames || index.games; }
    function gameItems() { return cardGames().map(function (g) { return [g.id, gameOptionHtml(g)]; }); }
    var gamePick = makePicker(name + ": game", function (v) { state.gameId = v; draw(); });
    gamePick._set(gameItems(), state.gameId);
    pickers.appendChild(gamePick);
    gamePick.style.display = cardGames().length > 1 ? "" : "none";
    var subPick = null;
    if (opts.sub) {
      subPick = makePicker(name + ": " + opts.sub, function (v) { state.sub = v; draw(); });   // (a title can follow what's picked)
      pickers.appendChild(subPick);
    }
    if (opts.mode) {                                       // a third menu (Lineup network: season / live game numbers)
      var modePick = makePicker(name + ": " + opts.mode.label, function (v) { state.mode = v; draw(); });
      modePick._set(opts.mode.items, state.mode);
      pickers.appendChild(modePick);
    }

    function fillSub(g) {
      var items = opts.subItems(g);
      if (!items.some(function (it) { return it[0] === state.sub; })) state.sub = items.length ? items[0][0] : null;
      subPick._set(items, state.sub);
      subPick.style.display = items.length ? "" : "none";
    }
    function draw() {
      if (state.stop) { state.stop(); state.stop = null; }
      var want = state.gameId;
      loadGame(want).then(function (g) {
        return Promise.resolve(opts.prepare ? opts.prepare(g) : null).then(function () { return g; });
      }).then(function (g) {
        if (want !== state.gameId) return;            // another game was picked while this one loaded
        if (subPick) fillSub(g);
        if (typeof opts.title === "function") titleEl.innerHTML = opts.title(g, state.sub);
        body.innerHTML = "";
        if (g.pre) renderPregame(body, g);                  // not tipped off yet: nothing to draw
        else state.stop = opts.render(body, g, state.sub, card, state.mode) || null;
        if (opts.onDrawn) opts.onDrawn();
      }).catch(function () {
        body.innerHTML = '<div class="ls-foot">This game couldn\'t be loaded right now.</div>';
      });
    }
    card._draw = draw;
    // the ticker picked a game: this card shows it too
    card._showGame = function (id) {
      if (id === state.gameId) return;
      state.gameId = id;
      gamePick._set(gameItems(), id);
      draw();
    };
    card._refresh = function (liveNow) {
      gamePick._set(gameItems(), state.gameId);
      if (liveNow[state.gameId]) draw();
    };
    // a new day (or a new list of games) for the windows
    card._setGames = function () {
      state.gameId = index.selected || index["default"];
      gamePick._set(gameItems(), state.gameId);
      gamePick.style.display = cardGames().length > 1 ? "" : "none";
      draw();
    };
    draw();
    return card;
  }
  function renderPregame(body, g) {
    var tip = "";
    try { tip = new Date(g.when).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) + " ET"; } catch (e) {}
    body.appendChild(el("div", "ls-pre", '<div class="m">' + logoImg(g.away, 34) + '<span class="at">@</span>' + logoImg(g.home, 34) + "</div>" +
      '<div class="t">' + esc(g.away.city + " " + g.away.name) + " at " + esc(g.home.city + " " + g.home.name) + "</div>" +
      '<div class="w">Tips off ' + esc(tip || g.status || "later today") + "</div>"));
  }

  function playerItems(g, withAll) {
    var items = withAll ? [["all", "All shots"], ["team:home", triTag(g.home, 14) + " shots"], ["team:away", triTag(g.away, 14) + " shots"]] : [];
    (g.players || []).slice().sort(function (a, b) { return b.pts - a.pts; }).forEach(function (p) {
      if (withAll && !p.fga) return;
      items.push([String(p.id), esc(p.short || p.name) + " · " + triTag(teamOf(g, p.team), 14)]);
    });
    return items;
  }

  // ------------------------------------------------------------ 1. scoreboard + game flow
  function renderScore(body, g) {
    var c = colors(g);
    var homeWin = g.home.score >= g.away.score;
    [["away", g.away, c.away, !homeWin], ["home", g.home, c.home, homeWin]].forEach(function (row) {
      // the team's logo first, its name and abbreviation, and its score in its own colour
      var extra = "";
      var sit = g.live && g.situation ? g.situation[row[0]] : null;
      if (sit) {
        if (sit.timeouts != null) extra += '<span class="ls-to">' + sit.timeouts + " Timeout" + (sit.timeouts === 1 ? "" : "s") + "</span>";
        if (sit.bonus) extra += '<span class="ls-bonus">BONUS</span>';
      }
      var r = el("div", "ls-team" + (row[3] && g.final ? " win" : ""),
        '<span class="tri">' + logoImg(row[1], 24) + '<span style="color:' + row[2] + '">' + esc(row[1].city ? row[1].name : row[1].tri) +
        '</span> <span style="color:#8c867b;font-weight:400;font-size:12px">' + esc(row[1].tri) + "</span>" + extra + '</span><span class="sc" style="color:' +
        row[2] + '">0</span>');
      body.appendChild(r);
      countUp(r.querySelector(".sc"), row[1].score, 1600);
    });
    var n = Math.max(g.home.periods.length, g.away.periods.length);
    var head = "<tr><th></th>", ra = '<tr><td style="color:' + c.away + '">' + triTag(g.away, 13) + "</td>",
      rh = '<tr><td style="color:' + c.home + '">' + triTag(g.home, 13) + "</td>";
    for (var i = 0; i < n; i++) {
      head += "<th>" + (i < 4 ? i + 1 : "OT" + (i > 4 ? i - 3 : "")) + "</th>";
      ra += "<td>" + (g.away.periods[i] == null ? "" : g.away.periods[i]) + "</td>";
      rh += "<td>" + (g.home.periods[i] == null ? "" : g.home.periods[i]) + "</td>";
    }
    body.appendChild(el("table", "ls-qtable", head + "<th>T</th></tr>" + ra + '<td class="t" style="color:' + c.away + '">' + g.away.score + "</td></tr>" +
      rh + '<td class="t" style="color:' + c.home + '">' + g.home.score + "</td></tr>"));
    // the game-flow line: home lead above the middle, away lead below -- between a light grey line along the top and
    // one along the bottom, with "(logo) SAS lead" / "(logo) NYK lead" just inside them (the line stays clear of those)
    var W = 330, H = 112, PAD = 23, end = gameEnd(g), maxAbs = 5;
    g.flow.forEach(function (f) { maxAbs = Math.max(maxAbs, Math.abs(f[1] - f[2])); });
    var X = function (t) { return 4 + (W - 8) * t / end; }, Y = function (m) { return H / 2 - (H / 2 - PAD) * m / maxAbs; };
    var d = "M " + X(0).toFixed(1) + " " + Y(0).toFixed(1), prevY = Y(0);
    g.flow.forEach(function (f) {
      var y = Y(f[1] - f[2]);
      d += " L " + X(f[0]).toFixed(1) + " " + prevY.toFixed(1) + " L " + X(f[0]).toFixed(1) + " " + y.toFixed(1);
      prevY = y;
    });
    d += " L " + X(end).toFixed(1) + " " + prevY.toFixed(1);
    var qlines = "";
    for (var q = 1; q < 4; q++) qlines += '<line x1="' + X(q * 720) + '" x2="' + X(q * 720) + '" y1="1" y2="' + (H - 1) + '" stroke="#2a2721"/>';
    var svg = el("div", "ls-flow",
      '<svg class="ls-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Score margin through the game">' + qlines +
      '<line x1="0" x2="' + W + '" y1="0.6" y2="0.6" stroke="#c9c3b8" stroke-opacity=".38" stroke-width="1.2"/>' +
      '<line x1="0" x2="' + W + '" y1="' + (H - 0.6) + '" y2="' + (H - 0.6) + '" stroke="#c9c3b8" stroke-opacity=".38" stroke-width="1.2"/>' +
      '<line x1="4" x2="' + (W - 4) + '" y1="' + H / 2 + '" y2="' + H / 2 + '" stroke="#3a362e" stroke-dasharray="3 3"/>' +
      svgLogo(g.home, 5, 6, 12) + '<text x="21" y="15.5" font-size="9.5" font-weight="700" fill="' + c.home + '">' + esc(g.home.tri) + ' lead</text>' +
      svgLogo(g.away, 5, H - 18, 12) + '<text x="21" y="' + (H - 8.5) + '" font-size="9.5" font-weight="700" fill="' + c.away + '">' + esc(g.away.tri) + ' lead</text>' +
      // the margin line is the whole game's, so it's gold
      '<defs><linearGradient id="lsGold' + g.id + '" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="#B8860B"/>' +
      '<stop offset=".5" stop-color="#F5D370"/><stop offset="1" stop-color="#B8860B"/></linearGradient></defs>' +
      '<path d="' + d + '" fill="none" stroke="url(#lsGold' + g.id + ')" stroke-width="1.8" stroke-linejoin="round"/></svg>');
    body.appendChild(svg);
    drawIn(svg.querySelector("path"));
    renderTiles(body, g);
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
    var wrap = el("div", "ls-court", '<svg class="ls-svg" viewBox="-252 -2 504 381.5" role="img" aria-label="Shots in game order">' +
      courtLines() + '<g></g></svg>');
    body.appendChild(wrap);
    var layer = wrap.querySelector("g:last-of-type");
    var stats = el("div", "ls-stats ls-stats-roomy", '<div><span>Plotted</span><b class="n">0</b></div><div><span>FG%</span><b class="f">–</b></div>' +
      '<div><span>Threes</span><b class="t">0/0</b></div><div><span>eFG%</span><b class="e">–</b></div>' +
      '<div><span>In the paint</span><b class="p">0/0</b></div><div><span>Points</span><b class="pts">0</b></div>' +
      '<div><span>Mid-range</span><b class="mr">0/0</b></div><div><span>Avg. distance</span><b class="ad">–</b></div>' +
      '<div><span>Longest make</span><b class="lm">–</b></div>');
    body.appendChild(stats);
    var who = null;
    if (sub && sub !== "all") {
      if (sub.indexOf("team:") === 0) who = sub.slice(5);
      else if (byId[sub]) who = byId[sub].team;
    }
    if (who) stats.style.setProperty("--ls-num", sideColor(g, who));
    else stats.classList.add("gold");
    var i = 0, made = 0, tpm = 0, tpa = 0, pm = 0, pa = 0, pts = 0, mm = 0, ma = 0, dist = 0, longest = 0, timer = null, alive = true;
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
      var paint = Math.abs(s[3]) <= 80 && s[4] <= 142.5, ft = Math.sqrt(s[3] * s[3] + s[4] * s[4]) / 10;   // feet from the rim
      if (paint) { pa++; pm += s[5]; }                                            // inside the paint
      else if (s[6] !== 3) { ma++; mm += s[5]; }                                  // a two from outside the paint
      dist += ft;
      if (s[5]) { pts += s[6]; longest = Math.max(longest, ft); }
    }
    function update() {
      stats.querySelector(".n").textContent = i + "/" + shots.length;
      stats.querySelector(".f").textContent = i ? Math.round(100 * made / i) + "%" : "–";
      stats.querySelector(".t").textContent = tpm + "/" + tpa;
      stats.querySelector(".e").textContent = i ? Math.round(100 * (made + 0.5 * tpm) / i) + "%" : "–";
      stats.querySelector(".p").textContent = pm + "/" + pa;
      stats.querySelector(".pts").textContent = pts;
      stats.querySelector(".mr").textContent = mm + "/" + ma;
      stats.querySelector(".ad").textContent = i ? (dist / i).toFixed(1) + " ft" : "–";
      stats.querySelector(".lm").textContent = longest ? Math.round(longest) + " ft" : "–";
    }
    function restart() {
      layer.innerHTML = ""; i = made = tpm = tpa = pm = pa = pts = mm = ma = dist = longest = 0; update();
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
    body.appendChild(el("div", "ls-player", '<img alt="" loading="lazy" src="' + esc(headshotOf(p)) + '" onerror="this.style.visibility=\'hidden\'">' +
      '<div><div class="nm">' + esc(p.name) + '</div><div class="tm">' + logoImg(team, 14) + esc(team.city + " " + team.name) + "</div>" +
      (p.min ? '<div class="mn">' + esc(p.min) + " min</div>" : "") + "</div>"));
    var ts = p.fga + 0.44 * p.fta ? 100 * p.pts / (2 * (p.fga + 0.44 * p.fta)) : null;
    var efg = p.fga ? 100 * (p.fgm + 0.5 * p.tpm) / p.fga : null;
    var pct = function (v) { return v == null ? "–" : v.toFixed(1) + "%"; };
    var s1 = el("div", "ls-stats ls-stats-roomy",
      '<div><span>Points</span><b>0</b></div><div><span>Rebounds</span><b>0</b></div><div><span>Assists</span><b>0</b></div>' +
      '<div><span>FG</span><b>' + p.fgm + "/" + p.fga + '</b></div><div><span>3PT</span><b>' + p.tpm + "/" + p.tpa + '</b></div>' +
      '<div><span>FT</span><b>' + p.ftm + "/" + p.fta + '</b></div>' +
      '<div><span>Steals</span><b>' + p.stl + '</b></div><div><span>Blocks</span><b>' + p.blk + '</b></div><div><span>Turnovers</span><b>' + p.tov + '</b></div>' +
      '<div><span>TS%</span><b>' + pct(ts) + '</b></div><div><span>eFG%</span><b>' + pct(efg) + '</b></div>' +
      '<div><span>+/-</span><b>' + (p.pm > 0 ? "+" : "") + p.pm + "</b></div>");
    s1.style.setProperty("--ls-num", col);
    body.appendChild(s1);
    var bs = s1.querySelectorAll("b");
    countUp(bs[0], p.pts, 1200); countUp(bs[1], p.reb, 1200); countUp(bs[2], p.ast, 1200);
    // points through the game
    var W = 270, H = 56, end = gameEnd(g), pts = [[0, 0]], tot = 0;
    (g.scoring || []).forEach(function (s) { if (s[1] === p.id) { tot += s[2]; pts.push([s[0], tot]); } });
    pts.push([end, tot]);
    var X = function (t) { return 3 + (W - 6) * t / end; }, Y = function (v) { return H - 4 - (H - 10) * v / Math.max(10, tot); };
    var d = "M " + pts.map(function (q, k) {
      return X(q[0]).toFixed(1) + " " + Y(k ? pts[k - 1][1] : 0).toFixed(1) + " L " + X(q[0]).toFixed(1) + " " + Y(q[1]).toFixed(1);
    }).join(" L ");
    var svg = el("div", "ls-ptg", '<div class="ls-title" style="margin-bottom:6px">Points through the game</div>' +
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
    var box = el("div", "ls-race");                   // fills the window; each row is 1/8 of it (see CSS)
    body.appendChild(box);
    var rows = top.map(function (p) {
      // the team's logo and the player's picture, no name (the picture's hover text names him)
      var r = el("div", "ls-rrow", '<span class="n" title="' + esc(p.name || lastName(p)) + '">' + logoImg(teamOf(g, p.team), 22) +
        '<img class="hs" alt="' + esc(p.name || lastName(p)) + '" loading="lazy" src="' +
        esc(headshotOf(p)) + '" onerror="this.style.visibility=\'hidden\'"></span><span class="b"><i style="background:' +
        (p.team === "home" ? c.home : c.away) + '"></i></span><span class="v" style="color:' + (p.team === "home" ? c.home : c.away) + '">0</span>');
      r.style.height = (100 / Math.max(1, top.length)) + "%";
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
        r.style.transform = "translateY(" + (rank * 100) + "%)";
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
    if (!nodes.length) { body.appendChild(el("div", "ls-foot", "No assists recorded for " + logoImg(team, 13) + esc(team.name) + " in this game.")); return; }
    var maxN = 1, list = [];
    Object.keys(pairs).forEach(function (k) {
      var ab = k.split(">");
      if (nodes.indexOf(ab[0]) >= 0 && nodes.indexOf(ab[1]) >= 0) { list.push([ab[0], ab[1], pairs[k]]); maxN = Math.max(maxN, pairs[k]); }
    });
    list.sort(function (a, b) { return a[2] - b[2]; });
    var wrap = el("div", "ls-aweb");
    body.appendChild(wrap);
    var best = list[list.length - 1];
    body.appendChild(el("div", "ls-foot", logoImg(team, 13) + esc(team.name) + " · thicker line = more assists" +
      (best ? " · most: " + esc(lastName(byId[best[0]])) + " → " + esc(lastName(byId[best[1]])) + " (" + best[2] + ")" : "")));
    // The web is drawn to the window's own shape, as wide as it is: the players sit on an oval that reaches out to
    // near the window's sides. Every name is centred on its dot -- except one that would then run off the window's
    // side: that one is written from its dot inward (left-aligned on the left side, right-aligned on the right).
    var dots = [], alive = true, drawnAt = "", measureCtx = null;
    function nameWidth(s) {
      try {
        if (!measureCtx) {
          measureCtx = document.createElement("canvas").getContext("2d");
          measureCtx.font = "700 11px " + (getComputedStyle(wrap).fontFamily || "Arial, Helvetica, sans-serif");
        }
        return measureCtx.measureText(s).width;
      } catch (e) { return s.length * 6.6; }
    }
    function draw() {
      var box = wrap.getBoundingClientRect();
      var W = Math.round(box.width) || 300, H = Math.round(box.height) || 330;
      if (W < 120 || H < 120) { W = 300; H = 330; }
      if (drawnAt === W + "x" + H && wrap.firstChild) return;
      drawnAt = W + "x" + H;
      var cx = W / 2, cy = H / 2 + 2, big = 12, R = W / 2 - big - 3, RY = H / 2 - 30, pos = {};
      nodes.forEach(function (id, i) {
        var a = -Math.PI / 2 + 2 * Math.PI * i / nodes.length;
        pos[id] = [cx + R * Math.cos(a), cy + RY * Math.sin(a)];
      });
      var paths = "", labels = "";
      list.forEach(function (e) {
        var p1 = pos[e[0]], p2 = pos[e[1]];
        var mx = (p1[0] + p2[0]) / 2, my = (p1[1] + p2[1]) / 2;
        var qx = mx + (cx - mx) * 0.35, qy = my + (cy - my) * 0.35;
        paths += '<path class="arc" data-n="' + e[2] + '" d="M ' + p1[0].toFixed(1) + " " + p1[1].toFixed(1) + " Q " + qx.toFixed(1) + " " + qy.toFixed(1) +
          " " + p2[0].toFixed(1) + " " + p2[1].toFixed(1) + '" fill="none" stroke="' + col + '" stroke-opacity="' + (0.25 + 0.55 * e[2] / maxN).toFixed(2) +
          '" stroke-width="' + (1 + 5 * e[2] / maxN).toFixed(1) + '" stroke-linecap="round"/>';
      });
      nodes.forEach(function (id) {
        var p = pos[id], pl = byId[id] || {}, r = 6 + 6 * involved[id] / involved[nodes[0]];
        var below = p[1] >= cy, half = nameWidth(lastName(pl)) / 2 + 2;
        var anchor = p[0] - half < 2 ? "start" : p[0] + half > W - 2 ? "end" : "middle";
        var tx = anchor === "start" ? Math.max(2, p[0] - r) : anchor === "end" ? Math.min(W - 2, p[0] + r) : p[0];
        labels += '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="' + r.toFixed(1) + '" fill="#161513" stroke="' + col + '" stroke-width="2"/>' +
          '<text x="' + tx.toFixed(1) + '" y="' + (p[1] + (below ? r + 13 : -r - 6)).toFixed(1) + '" text-anchor="' + anchor +
          '" font-size="11" font-weight="700" fill="#f0f0f0">' + esc(lastName(pl)) + "</text>";
      });
      wrap.innerHTML = '<svg class="ls-svg" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Who assisted whom">' +
        paths + '<g class="balls"></g>' + labels + "</svg>";
      dots = [];
      if (REDUCE) return;
      var arcs = wrap.querySelectorAll("path.arc"), balls = wrap.querySelector("g.balls");
      Array.prototype.forEach.call(arcs, function (a, i) {
        var len = a.getTotalLength ? a.getTotalLength() : 0;
        var b = document.createElementNS(SVGNS, "circle");
        b.setAttribute("r", 3.4); b.setAttribute("fill", "#FFF0B8"); b.setAttribute("opacity", 0);
        balls.appendChild(b);
        dots.push({ a: a, b: b, len: len, period: 2600 - 1200 * (+a.getAttribute("data-n")) / maxN, off: (i * 0.37) % 1 });
      });
    }
    draw();
    var ro = window.ResizeObserver ? new ResizeObserver(function () { if (alive) draw(); }) : null;
    if (ro) ro.observe(wrap);
    if (REDUCE) return function () { alive = false; if (ro) ro.disconnect(); };
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
    return function () { alive = false; if (ro) ro.disconnect(); };
  }

  // ------------------------------------------------------------ 6. team comparison
  function renderCompare(body, g) {
    var c = colors(g), h = g.home.stats || {}, a = g.away.stats || {};
    var rows = [["FG%", a.fgPct, h.fgPct, "%"], ["3PT%", a.tpPct, h.tpPct, "%"], ["Rebounds", a.reb, h.reb], ["Assists", a.ast, h.ast],
      ["Paint pts", a.paint, h.paint], ["Fast break", a.fastBreak, h.fastBreak], ["2nd chance", a.secondChance, h.secondChance],
      ["Turnovers", a.tov, h.tov], ["Pts off TOs", a.tovPts, h.tovPts], ["Bench pts", a.benchPts, h.benchPts]];
    var grid = el("div", "ls-cmp");
    // each team's logo, centered over its column of team-coloured bars
    grid.appendChild(el("div", "ls-cmp-row ls-cmp-head", '<span></span><span class="lg" title="' + esc(g.away.city + " " + g.away.name) + '">' +
      logoImg(g.away, 50) + '</span><span></span><span class="lg" title="' + esc(g.home.city + " " + g.home.name) + '">' + logoImg(g.home, 50) +
      "</span><span></span>"));
    rows.forEach(function (r) {
      if (r[1] == null && r[2] == null) return;
      var va = +r[1] || 0, vh = +r[2] || 0, max = Math.max(va, vh, 1);
      var row = el("div", "ls-cmp-row", '<span class="l" style="color:' + c.away + '">' + va + (r[3] || "") + '</span><span class="bar left"><i style="background:' + c.away +
        '"></i></span><span class="lbl">' + r[0] + '</span><span class="bar"><i style="background:' + c.home + '"></i></span><span class="r" style="color:' + c.home + '">' +
        vh + (r[3] || "") + "</span>");
      grid.appendChild(row);
      var bars = row.querySelectorAll("i");
      requestAnimationFrame(function () { requestAnimationFrame(function () {
        bars[0].style.width = (100 * va / max) + "%"; bars[1].style.width = (100 * vh / max) + "%";
      }); });
    });
    body.appendChild(grid);
  }

  // Season numbers come from the dashboard itself (streamlit/app.py, "lineup numbers for the website"): it's opened,
  // hidden, as <dashboard>?lineups=SAS&season=2025-26 and posts back that team's season lineups -- every 2-, 3-, 4-
  // and 5-man group with its net rating and minutes together, the same numbers as its On/Off Lineup Network page with
  // a minimum of 0 minutes. Kept for 6 hours in this browser so the next visit shows them at once. The NBA and ESPN
  // number players differently, so players are matched by name.
  var DASHBOARD = (root.getAttribute("data-dashboard") || "https://bradleyanalytics.streamlit.app/").replace(/\/?$/, "/");
  var LINEUP_KEEP_MS = 6 * 3600 * 1000;
  var lineupFiles = {};
  function seasonOf(when) {
    var p = etDay(when).split("-"), y = parseInt(p[0], 10), m = parseInt(p[1], 10), s0 = m >= 8 ? y : y - 1;
    return s0 + "-" + String(s0 + 1).slice(2);
  }
  function askDashboard(season, tri) {
    return new Promise(function (resolve) {
      var f = document.createElement("iframe"), done = false, timer = null;
      f.title = "Lineup numbers";
      f.setAttribute("aria-hidden", "true");
      f.tabIndex = -1;
      // on the screen (a browser pauses frames it considers hidden) but invisible and out of the way
      f.style.cssText = "position:fixed;right:0;bottom:0;width:24px;height:24px;border:0;opacity:0;pointer-events:none;z-index:-1";
      function fromFrame(src) {
        try { for (var w = src; w; w = (w.parent === w ? null : w.parent)) { if (w === f.contentWindow) return true; } } catch (e) {}
        return false;
      }
      function onMessage(e) {
        var d = e.data;
        if (!d || d.type !== "ba-lineups" || d.team !== tri || d.season !== season || !fromFrame(e.source)) return;
        finish(d.data && d.data.groups ? d.data : null);
      }
      function finish(v) {
        if (done) return;
        done = true;
        clearTimeout(timer);
        window.removeEventListener("message", onMessage);
        setTimeout(function () { if (f.parentNode) f.parentNode.removeChild(f); }, 0);
        resolve(v);
      }
      window.addEventListener("message", onMessage);
      timer = setTimeout(function () { finish(null); }, 120000);
      f.src = DASHBOARD + "?embed=true&lineups=" + encodeURIComponent(tri) + "&season=" + encodeURIComponent(season);
      document.body.appendChild(f);
    });
  }
  function seasonLineups(season, tri) {
    var key = season + "/" + tri, store = "ba-lineups:" + key;
    if (!lineupFiles[key]) {
      var kept = null;
      try { kept = JSON.parse(localStorage.getItem(store) || "null"); } catch (e) {}
      if (kept && kept.data && Date.now() - kept.at < LINEUP_KEEP_MS) lineupFiles[key] = Promise.resolve(kept.data);
      else {
        lineupFiles[key] = askDashboard(season, tri).then(function (data) {
          if (data) { try { localStorage.setItem(store, JSON.stringify({ at: Date.now(), data: data })); } catch (e) {} }
          else delete lineupFiles[key];                  // try again next time
          return data;
        });
      }
    }
    return lineupFiles[key];
  }
  function nbaIdsFor(data, players) {
    var full = {}, initial = {};
    Object.keys(data.players || {}).forEach(function (id) {
      var n = String(data.players[id] || ""), parts = n.split(" ");
      full[normName(n)] = id;
      initial[normName(n.charAt(0) + parts.slice(1).join(" "))] = id;
    });
    return players.map(function (p) {
      var n = String((p && p.name) || ""), parts = n.split(" ");
      return full[normName(n)] || initial[normName(n.charAt(0) + parts.slice(1).join(" "))] || null;
    });
  }
  // a player's picture: the feed's own, else ESPN's (ESPN player IDs) or the NBA's (the saved games use NBA IDs)
  function headshotOf(p) {
    if (!p) return "";
    if (p.img) return p.img;
    return p.id ? (source === "espn" ? "https://a.espncdn.com/i/headshots/nba/players/full/" : HEADSHOT) + p.id + ".png" : "";
  }

  // ------------------------------------------------------------ lineup network
  // One team's five on the floor right now (a finished game: its starting five) around a pentagon, every pair joined
  // by a line (thicker = a bigger net rating together; the team's colour when they've outscored the other team, grey
  // dashes when they've been outscored), and under it all five together plus the best four, trio and duo inside those
  // five -- their pictures, net rating and minutes together. A menu switches between this season's numbers (the
  // default) and this game's. The groups light up in turn (see the end).
  function fmtNet(v) { return v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(1); }
  function fmtMin(sec) { return Math.round(sec / 60) + " min"; }
  function renderLineups(body, g, sub, card, mode) {
    var side = sub === "away" ? "away" : "home", team = teamOf(g, side), byId = playerById(g);
    var five = ((g.live ? g.onNow : g.starters) || {})[side] || [];
    if (five.length < 2) {
      body.appendChild(el("div", "ls-foot", "No lineup data for " + logoImg(team, 13) + esc(team.name) + " in this game yet."));
      return;
    }
    if (mode !== "live") {
      var wait = el("div", "ls-foot", "Loading this season's lineup numbers…");
      body.appendChild(wait);
      var alive = true, stop = null;
      seasonLineups(seasonOf(g.when), team.tri).then(function (data) {
        if (!alive) return;
        body.removeChild(wait);
        var groups = {}, ids = data ? nbaIdsFor(data, five.map(function (id) { return byId[id]; })) : [];
        var nbaOf = {};
        five.forEach(function (id, i) { nbaOf[id] = ids[i]; });
        [2, 3, 4, 5].forEach(function (k) {
          groups[k] = combos(five, k).map(function (grp) {
            var keys = grp.map(function (id) { return nbaOf[id]; });
            var hit = null;
            if (data && keys.every(Boolean)) {
              var key = keys.slice().sort(function (a, b) { return a - b; }).join("-");
              hit = ((data.groups || {})[k] || {})[key] || null;
            }
            return { ids: grp, net: hit ? hit[0] : null, min: hit ? hit[1] : 0, weight: hit ? hit[1] : 0 };
          });
        });
        stop = drawLineups(body, g, side, five, groups, card, true);
      });
      return function () { alive = false; if (stop) stop(); };
    }
    var b = fiveBreakdown(g, side, five), groups = {};
    [2, 3, 4, 5].forEach(function (k) {
      groups[k] = b[k].map(function (r) { return { ids: r.ids, net: r.poss >= 2 ? r.net : 0, min: r.sec / 60, weight: r.poss }; });
    });
    return drawLineups(body, g, side, five, groups, card);
  }
  function drawLineups(body, g, side, five, groups, card, seasonNumbers) {
    var col = sideColor(g, side), byId = playerById(g);
    // last names -- with a first initial for two players who share one
    var nm = {}, count = {};
    five.forEach(function (id) { var l = lastName(byId[id]); count[l] = (count[l] || 0) + 1; });
    five.forEach(function (id) { var p = byId[id] || {}, l = lastName(p); nm[id] = count[l] > 1 ? String(p.name || "").charAt(0) + ". " + l : l; });
    var W = 330, H = 180, cx = W / 2, cy = 94, R = 70, pos = {};
    five.forEach(function (id, i) {
      var a = -Math.PI / 2 + 2 * Math.PI * i / five.length;
      pos[id] = [cx + R * Math.cos(a), cy + R * Math.sin(a)];
    });
    var edges = "";
    groups[2].slice().sort(function (x, y) { return Math.abs(x.net || 0) - Math.abs(y.net || 0); }).forEach(function (r) {
      var p1 = pos[r.ids[0]], p2 = pos[r.ids[1]], v = r.net == null ? 0 : r.net, w = 1 + Math.min(5, Math.abs(v) / 8);
      edges += '<line class="ls-lu-edge" data-a="' + esc(r.ids[0]) + '" data-b="' + esc(r.ids[1]) + '" x1="' + p1[0].toFixed(1) + '" y1="' + p1[1].toFixed(1) +
        '" x2="' + p2[0].toFixed(1) + '" y2="' + p2[1].toFixed(1) + '" stroke="' + (v >= 0 ? col : "#6f6a62") + '" stroke-width="' + w.toFixed(1) +
        '" stroke-opacity="' + (v >= 0 ? 0.85 : 0.7) + '"' + (v < 0 || r.net == null ? ' stroke-dasharray="4 3"' : "") +
        ' stroke-linecap="round"><title>' + esc(nm[r.ids[0]] + " + " + nm[r.ids[1]]) + ": " + fmtNet(r.net) + "</title></line>";
    });
    var nodes = "";
    five.forEach(function (id) {
      var p = pos[id], below = p[1] > cy + 5;
      nodes += '<circle class="ls-lu-node" data-id="' + esc(id) + '" cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="7" fill="#161513" stroke="' + col + '" stroke-width="2.2"/>' +
        '<text x="' + p[0].toFixed(1) + '" y="' + (p[1] + (below ? 19 : -11)).toFixed(1) + '" text-anchor="middle" font-size="10.5" font-weight="700" fill="#f0f0f0">' +
        esc(nm[id]) + "</text>";
    });
    var web = el("div", "ls-lu-web", '<svg class="ls-svg ls-lu-svg" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Net rating of every pair in this five">' +
      edges + nodes + "</svg>");
    web.style.setProperty("--team", col);
    body.appendChild(web);
    // the best group of each size inside these five. Season numbers: the highest net rating, exactly as the dashboard's
    // On/Off Lineup Network ranks them with a minimum of 0 minutes. This game's numbers: ranked by net rating pulled
    // toward 0 for small samples (so a few hot possessions don't beat a long good stretch), preferring real samples.
    function best(list) {
      var withNet = list.filter(function (r) { return r.net != null; });
      if (seasonNumbers) return withNet.sort(function (x, y) { return y.net - x.net || y.min - x.min; })[0] || null;
      var ok = withNet.filter(function (r) { return r.weight >= 5; });
      if (!ok.length) ok = withNet;
      var score = function (r) { return r.net * r.weight / (r.weight + 25); };
      return ok.sort(function (x, y) { return score(y) - score(x); })[0] || null;
    }
    var rows = [["All five", groups[5][0]], ["Best four", best(groups[4])], ["Best trio", best(groups[3])], ["Best duo", best(groups[2])]];
    var html = "";
    rows.forEach(function (r) {
      var x = r[1];
      var faces = x ? x.ids.map(function (id) {
        var p = byId[id] || {};
        return '<span class="ls-face" title="' + esc(p.name || "") + '" style="background-image:url(\'' + esc(headshotOf(p)) + '\')"></span>';
      }).join("") : "";
      html += '<div class="ls-lu-row"><span class="k">' + r[0] + '</span><span class="w' + (x && x.ids.length > 4 ? " n5" : "") + '">' + faces + '</span><b style="color:' +
        (x && x.net != null && x.net < 0 ? "#a9a39a" : col) + '">' + (x ? fmtNet(x.net) : "–") + '</b><span class="m">' + (x && x.min ? Math.round(x.min) + " min" : "") + "</span></div>";
    });
    var list = el("div", "ls-lu-list", html);
    list.style.setProperty("--team", col);
    body.appendChild(list);

    // the animation: every 2 seconds the next group lights up -- all five, then the best four, trio and duo inside
    // them, then back to all five -- its connecting lines glowing in the team colour while its line (and its players'
    // pictures) grow
    var svg = web.querySelector("svg"), rowEls = list.querySelectorAll(".ls-lu-row");
    var steps = rows.map(function (r, i) { return { ids: r[1] ? r[1].ids : null, row: rowEls[i] }; }).filter(function (x) { return x.ids; });
    if (!steps.length) return;
    function light(k) {
      var st = steps[k], ids = st.ids;
      Array.prototype.forEach.call(svg.querySelectorAll(".ls-lu-edge"), function (e) {
        e.classList.toggle("on", ids.indexOf(e.getAttribute("data-a")) >= 0 && ids.indexOf(e.getAttribute("data-b")) >= 0);
      });
      Array.prototype.forEach.call(svg.querySelectorAll(".ls-lu-node"), function (n) { n.classList.toggle("on", ids.indexOf(n.getAttribute("data-id")) >= 0); });
      Array.prototype.forEach.call(rowEls, function (r) { r.classList.toggle("on", r === st.row); });
    }
    svg.classList.add("anim");
    list.classList.add("anim");
    var k = 0, alive = true;
    light(0);
    if (REDUCE) return;
    var timer = setInterval(function () {
      if (!alive || (card && card._hidden)) return;
      k = (k + 1) % steps.length;
      light(k);
    }, 2000);
    return function () { alive = false; clearInterval(timer); };
  }

  // ------------------------------------------------------------ win probability
  // The home team's chance to win after every score, from: the margin, the time left, the game's pace (possessions
  // still to come), home court, and how each team's five on the floor at that moment has played together this game
  // (every duo, trio, four and the five -- see fiveStrength). The same model gives the other chances (overtime, a
  // 10-point win) and the projected final score.
  function normCdf(z) {
    var t = 1 / (1 + 0.2316419 * Math.abs(z)), d = 0.3989423 * Math.exp(-z * z / 2);
    var p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
    return z > 0 ? 1 - p : p;
  }
  function teamPoss(g, side, upTo) {
    var n = 0;
    (g.stints || []).forEach(function (st) { if (upTo == null || st.t1 <= upTo + 0.01) n += possOf(side === "home" ? st.h : st.a); });
    return n;
  }
  function paceAt(g, t) {
    var played = Math.max(1, t), poss = (teamPoss(g, "home", t) + teamPoss(g, "away", t)) / 2;
    return (poss + 99 * 0.25) / (played / 2880 + 0.25);          // possessions per 48 minutes, leaning on ~99 early on
  }
  function sidePace(g, side, t) {                      // this team's own possessions per 48 minutes so far
    var played = Math.max(1, Math.min(t, (g.stints || []).reduce(function (m, st) { return Math.max(m, st.t1); }, 0) || t));
    return (teamPoss(g, side, t) / (played / 2880)).toFixed(1);
  }
  function stintAt(g, t) {
    var list = g.stints || [];
    for (var i = 0; i < list.length; i++) if (list[i].t0 <= t && t <= list[i].t1) return list[i];
    return list[list.length - 1] || null;
  }
  function winModel(g, t, margin, final) {
    var left = t < 2880 ? 2880 - t : Math.max(0, periodEnd(Math.floor((t - 2880) / 300) + 5) - t);
    if (final || left <= 0) return { p: margin > 0 ? 1 : margin < 0 ? 0 : 0.5, mu: margin, sd: 0, left: 0, poss: 0 };
    var st = stintAt(g, t), edge = 0;
    if (st) edge = fiveStrength(g, "home", st.home, t) - fiveStrength(g, "away", st.away, t);
    var poss = paceAt(g, t) * left / 2880;
    var mu = margin + 2.5 * left / 2880 + edge / 100 * poss * 0.5;
    var sd = Math.max(0.6, 13 * Math.sqrt(left / 2880));
    return { p: normCdf(mu / sd), mu: mu, sd: sd, left: left, poss: poss, edge: edge };
  }
  function renderWinProb(body, g) {
    var c = colors(g), end = gameEnd(g), last = g.flow[g.flow.length - 1] || [0, 0, 0];
    var tNow = g.live ? Math.max(last[0], g.now || 0) : end;
    var pts = g.flow.map(function (f) { return [f[0], winModel(g, f[0], f[1] - f[2], false).p]; });
    var nowM = winModel(g, tNow, g.home.score - g.away.score, g.final);
    pts.push([tNow, nowM.p]);
    var ph = nowM.p, pa = 1 - ph;
    var pct = function (v) { return v >= 0.995 && v < 1 ? ">99%" : v <= 0.005 && v > 0 ? "<1%" : Math.round(v * 100) + "%"; };
    body.appendChild(el("div", "ls-wp-top",
      '<span class="t" style="color:' + c.away + '">' + triTag(g.away, 18) + ' <b>' + pct(pa) + '</b></span>' +
      '<span class="bar"><i style="width:' + (pa * 100).toFixed(1) + "%;background:" + c.away + '"></i><i style="width:' + (ph * 100).toFixed(1) +
      "%;background:" + c.home + '"></i></span>' +
      '<span class="t r" style="color:' + c.home + '"><b>' + pct(ph) + "</b> " + triTag(g.home, 18) + "</span>"));
    // the home team's chance through the game (above the middle line: home favoured)
    var W = 272, H = 84, X = function (t) { return 3 + (W - 6) * t / Math.max(end, tNow); }, Y = function (p) { return 4 + (H - 8) * (1 - p); };
    var d = "", prev = null;
    pts.forEach(function (q, i) {
      d += (i ? " L " + X(q[0]).toFixed(1) + " " + Y(prev).toFixed(1) + " L " : "M ") + X(q[0]).toFixed(1) + " " + Y(q[1]).toFixed(1);
      prev = q[1];
    });
    var qlines = "";
    for (var q = 1; q < 4; q++) qlines += '<line x1="' + X(q * 720) + '" x2="' + X(q * 720) + '" y1="3" y2="' + (H - 3) + '" stroke="#2a2721"/>';
    var gid = "lsWp" + g.id;
    var svg = el("div", null, '<svg class="ls-svg" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Win probability through the game">' +
      '<defs><clipPath id="' + gid + 'a"><rect x="0" y="0" width="' + W + '" height="' + (H / 2) + '"/></clipPath>' +
      '<clipPath id="' + gid + 'b"><rect x="0" y="' + (H / 2) + '" width="' + W + '" height="' + (H / 2) + '"/></clipPath></defs>' + qlines +
      '<line x1="0" x2="' + W + '" y1="0.6" y2="0.6" stroke="#c9c3b8" stroke-opacity=".38" stroke-width="1.2"/>' +
      '<line x1="0" x2="' + W + '" y1="' + (H - 0.6) + '" y2="' + (H - 0.6) + '" stroke="#c9c3b8" stroke-opacity=".38" stroke-width="1.2"/>' +
      '<line x1="3" x2="' + (W - 3) + '" y1="' + (H / 2) + '" y2="' + (H / 2) + '" stroke="#3a362e" stroke-dasharray="3 3"/>' +
      '<path d="' + d + '" fill="none" stroke="' + c.home + '" stroke-width="1.8" clip-path="url(#' + gid + 'a)"/>' +
      '<path d="' + d + '" fill="none" stroke="' + c.away + '" stroke-width="1.8" clip-path="url(#' + gid + 'b)"/>' +
      svgLogo(g.home, 4, 3, 11) + svgLogo(g.away, 4, H - 14, 11) + "</svg>");
    body.appendChild(svg);
    // other chances (a finished game: how it got there)
    var lead = ph >= 0.5 ? "home" : "away", leadTeam = teamOf(g, lead), sgn = lead === "home" ? 1 : -1, chips = [];
    if (!g.final && nowM.sd > 0) {
      var mu = nowM.mu, sd = nowM.sd;
      if (tNow < 2880) chips.push(["Overtime", pct(normCdf((0.5 - mu) / sd) - normCdf((-0.5 - mu) / sd))]);
      chips.push([triTag(leadTeam, 12) + " by 10+", pct(1 - normCdf((9.5 - sgn * mu) / sd))]);
      var ppH = teamPoss(g, "home") ? g.home.score / teamPoss(g, "home") : 1.1, ppA = teamPoss(g, "away") ? g.away.score / teamPoss(g, "away") : 1.1;
      chips.push(["On pace for", logoImg(g.away, 11) + Math.round(g.away.score + ppA * nowM.poss) + "–" + Math.round(g.home.score + ppH * nowM.poss) +
        logoImg(g.home, 11).replace('margin-right:4px', "")]);
    } else {
      var winner = g.home.score > g.away.score ? "home" : "away", low = 1, lowT = 0, sure = null;
      pts.forEach(function (q) {
        var pw = winner === "home" ? q[1] : 1 - q[1];
        if (pw < low) { low = pw; lowT = q[0]; }
      });
      for (var i = pts.length - 1; i >= 0; i--) { var pw2 = winner === "home" ? pts[i][1] : 1 - pts[i][1]; if (pw2 < 0.9) { sure = pts[Math.min(pts.length - 1, i + 1)][0]; break; } }
      chips.push([triTag(teamOf(g, winner), 12) + "'s low point", pct(low) + " · " + clockAt(lowT)]);
      if (sure != null) chips.push(["90%+ from", clockAt(sure)]);
    }
    var chipBox = el("div", "ls-wp-chips", chips.map(function (x) { return "<div><span>" + x[0] + "</span><b>" + x[1] + "</b></div>"; }).join(""));
    chipBox.style.gridTemplateColumns = "repeat(" + chips.length + ", minmax(0, 1fr))";
    body.appendChild(chipBox);
    // who's on pace: pace, efficiency, and the five on the floor
    var sh = g.home.stats || {}, sa = g.away.stats || {};
    var pair = function (v) { var p = String(v || "0-0").split("-"); return [num(p[0]), num(p[1])]; };
    var efg = function (st) { var fg = pair(st.fg), tp = pair(st.tp); return fg[1] ? 100 * (fg[0] + 0.5 * tp[0]) / fg[1] : null; };
    var possH = teamPoss(g, "home"), possA = teamPoss(g, "away");
    var ftRate = function (st) { var fg = pair(st.fg), ft = pair(st.ft); return fg[1] ? (ft[1] / fg[1]).toFixed(2) : "–"; };
    var fiveH = ((g.live ? g.onNow : g.starters) || {}).home || [], fiveA = ((g.live ? g.onNow : g.starters) || {}).away || [];
    var fH = fiveH.length > 1 ? lineupTotals(g, "home", fiveH).net : null, fA = fiveA.length > 1 ? lineupTotals(g, "away", fiveA).net : null;
    var rows = [
      ["Pace", sidePace(g, "away", tNow), sidePace(g, "home", tNow)],
      ["Off. rating", possA ? (100 * g.away.score / possA).toFixed(1) : "–", possH ? (100 * g.home.score / possH).toFixed(1) : "–"],
      ["eFG%", efg(sa) == null ? "–" : efg(sa).toFixed(1) + "%", efg(sh) == null ? "–" : efg(sh).toFixed(1) + "%"],
      ["TOV%", possA ? (100 * num(sa.tov) / possA).toFixed(1) + "%" : "–", possH ? (100 * num(sh.tov) / possH).toFixed(1) + "%" : "–"],
      ["3PT%", sa.tpPct != null ? sa.tpPct.toFixed(1) + "%" : "–", sh.tpPct != null ? sh.tpPct.toFixed(1) + "%" : "–"],
      ["FT rate", ftRate(sa), ftRate(sh)],
      ["Biggest lead", String(num(sa.biggestLead)), String(num(sh.biggestLead))],
      [g.live ? "Five on floor" : "Starting five", fmtNet(fA), fmtNet(fH)]
    ];
    body.appendChild(el("div", "ls-wp-table",
      '<div class="h"><span style="color:' + c.away + '">' + triTag(g.away, 13) + '</span><span></span><span style="color:' + c.home + '">' + triTag(g.home, 13) + "</span></div>" +
      rows.map(function (r) { return '<div><b style="color:' + c.away + '">' + r[1] + '</b><span>' + r[0] + '</span><b style="color:' + c.home + '">' + r[2] + "</b></div>"; }).join("")));
  }

  // ------------------------------------------------------------ ALL GAMES (the last window)
  // Every game of one day -- the score, the time left and each game's win probability -- with the games closest to
  // the finish first: live games by least time left, then finished games, then games still to tip off. Its menu is
  // the tape's day picker: during the season the last 7 days that had games (picking one moves the tape and every
  // window to that day); during the Finals and the offseason the Finals dates (picking one moves every window to that
  // day's game, while the tape keeps the whole series). A game picked in the ticker doesn't change this window.
  function dayLabel(d) {
    try { return new Date(d + "T12:00:00-05:00").toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: "America/New_York" }); }
    catch (e) { return d; }
  }
  // The last 6 minutes of a game: the 4th quarter from 6:00 down, or any overtime (5 minutes long).
  function crunchTime(g) {
    if (!g || !g.live) return false;
    if (g.crunch != null) return g.crunch;
    var m = /^(Q4|\d*OT)\s+(?:(\d+):)?(\d+(?:\.\d+)?)$/.exec(qTick(g.tick || g.status || "").trim());
    return !!m && ((+m[2] || 0) * 60 + parseFloat(m[3])) <= 360;
  }
  function watchGame(e) {
    var g = brief(e), st = e.status || (e.competitions[0] || {}).status || {}, p = parseInt(st.period, 10) || 1;
    var clk = clockLeft(st.displayClock), margin = g.home.score - g.away.score;
    if (g.live) g.crunch = p >= 4 && clk <= 360 && !/HALFTIME|END_PERIOD/i.test(String((st.type || {}).name || ""));
    if (g.live) {
      var left = p <= 4 ? (4 - p) * 720 + clk : clk;               // regulation left (or this overtime)
      var R = p <= 4 ? left : clk;
      g.left = p <= 4 ? left : clk / 100;                          // overtime: always among the closest
      g.pHome = R <= 0 ? (margin > 0 ? 1 : margin < 0 ? 0 : 0.5) : normCdf((margin + 2.5 * R / 2880) / Math.max(0.6, 13 * Math.sqrt(R / 2880)));
    } else if (g.final) { g.left = 0; g.pHome = margin > 0 ? 1 : 0; }
    else { g.left = null; g.pHome = null; }
    return g;
  }
  function makeWatchCard() {
    var card = el("div", "ls-card wide ls-watch");
    var top = el("div", "ls-card-top");
    top.appendChild(el("div", "ls-title", "All games"));
    var pickers = el("div", "ls-pickers");
    top.appendChild(pickers);
    card.appendChild(top);
    var body = el("div", "ls-body");
    card.appendChild(body);
    var today = etDay(new Date().toISOString());
    var firstDay = index.mode === "season" ? index.day
      : ((index.games.filter(function (g) { return g.id === index["default"]; })[0] || index.games[index.games.length - 1] || {}).day);
    var state = { day: firstDay || (index.days || [])[0] };
    var dayPick = makePicker("All games: date", function (v) { state.day = v; draw(); setDay(v); });
    pickers.appendChild(dayPick);
    dayPick._set((index.days || []).map(function (d) {
      return [d, esc(dayLabel(d)) + (d === today ? ' <span class="ls-live-word">today</span>' : d > today ? ' <span class="ls-live-word">upcoming</span>' : "")];
    }), state.day);
    function gamesOn(day) {
      if (source !== "espn") return Promise.resolve(index.games.filter(function (g) { return g.day === day; }));
      return scoreboard(day === today ? null : day).then(function (b) { return ((b && b.events) || []).filter(realEvent).map(watchGame); });
    }
    function draw() {
      var want = state.day;
      if (!want) { body.innerHTML = '<div class="ls-foot">No recent games to show.</div>'; return; }
      gamesOn(want).then(function (games) {
        if (want !== state.day) return;
        games.sort(function (a, b) {
          var ka = a.live ? 0 : a.final ? 1 : 2, kb = b.live ? 0 : b.final ? 1 : 2;
          if (ka !== kb) return ka - kb;
          if (ka === 0) return a.left - b.left;
          if (ka === 1) return Math.abs(a.home.score - a.away.score) - Math.abs(b.home.score - b.away.score);
          return String(a.when).localeCompare(String(b.when));
        });
        var html = '<div class="ls-w-head"><span>Game</span><span class="c">Time left</span><span class="c">Win prob.</span></div>';
        games.forEach(function (g) {
          var c = colors(g), time, prob = "";
          if (g.live) time = '<i class="ls-dot" aria-hidden="true"></i><span' + (crunchTime(g) ? ' class="crunch"' : "") + ">" +
            esc(qTick(g.tick || g.status)) + "</span>";
          else if (g.final) time = '<span>' + esc(qTick(g.tick || "Final")) + "</span>";
          else {
            var tip = g.status;
            try { tip = new Date(g.when).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }); } catch (e) {}
            time = '<span>' + esc(tip) + "</span>";
          }
          if (g.pHome != null) {
            var fav = g.pHome >= 0.5 ? "home" : "away", pf = fav === "home" ? g.pHome : 1 - g.pHome;
            var pct = pf >= 0.995 && pf < 1 ? ">99%" : Math.round(pf * 100) + "%";
            prob = '<span class="bar"><i style="width:' + ((1 - g.pHome) * 100).toFixed(1) + "%;background:" + c.away + '"></i><i style="width:' +
              (g.pHome * 100).toFixed(1) + "%;background:" + c.home + '"></i></span><b style="color:' + (fav === "home" ? c.home : c.away) + '">' +
              logoImg(teamOf(g, fav), 12) + '<span class="tri">' + esc(teamOf(g, fav).tri) + "&nbsp;</span>" + (g.final ? "won" : pct) + "</b>";
          } else prob = '<span class="na">–</span>';
          html += '<div class="ls-w-row' + (g.live ? " live" : "") + '"><span class="gm">' + logoImg(g.away, 15) + '<span class="sa" style="color:' + c.away + '">' +
            '<span class="tri">' + esc(g.away.tri) + " </span>" + g.away.score + '</span><span class="d">-</span><span class="sh" style="color:' + c.home + '">' +
            g.home.score + '<span class="tri"> ' + esc(g.home.tri) + "</span></span>" + logoImg(g.home, 15) + '</span><span class="tm">' + time + '</span><span class="pr">' + prob + "</span></div>";
        });
        if (!games.length) html += '<div class="ls-foot">No games this day.</div>';
        body.innerHTML = '<div class="ls-watch-list">' + html + "</div>";
        centerTimes();
      }).catch(function () {
        body.innerHTML = '<div class="ls-foot">This day\'s games couldn\'t be loaded right now.</div>';
      });
    }
    // Each row's time left sits exactly halfway between that row's home-team logo and its win probability (the
    // column is shared by every row, so a row with a shorter game line has its time nudged over to its own middle).
    function centerTimes() {
      // the win probability starts where its bar does (the same spot in every row)
      var bar = body.querySelector(".ls-w-row .pr .bar"), barW = bar ? bar.getBoundingClientRect().width : 0;
      Array.prototype.forEach.call(body.querySelectorAll(".ls-w-row"), function (row) {
        var gm = row.querySelector(".gm"), tm = row.querySelector(".tm"), pr = row.querySelector(".pr");
        var last = gm && gm.lastElementChild;
        if (!last || !tm || !pr || !tm.firstChild) return;
        tm.style.transform = "";
        var a = last.getBoundingClientRect(), p = pr.getBoundingClientRect(), rt = document.createRange();
        rt.selectNodeContents(tm);
        var t = rt.getBoundingClientRect(), probLeft = p.left + Math.max(0, (p.width - barW) / 2);
        if (!a.width || !t.width || !p.width) return;
        var shift = (a.right + probLeft) / 2 - (t.left + t.right) / 2;
        if (Math.abs(shift) > 0.4) tm.style.transform = "translateX(" + shift.toFixed(1) + "px)";
      });
    }
    if (window.ResizeObserver) new ResizeObserver(function () { centerTimes(); }).observe(body);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(centerTimes);
    body.addEventListener("load", function () { centerTimes(); }, true);     // (a logo arriving can change a row)
    draw();
    // live scores refresh every minute: redraw when this window is on today
    card._refresh = function () { if (state.day === etDay(new Date().toISOString()) || index.games.some(function (g) { return g.live; })) draw(); };
    return card;                                        // (no _showGame: a game picked in the ticker doesn't change it)
  }


  // ------------------------------------------------------------ HOT HAND / MOMENTUM RUN
  // A player with a hot hand in this game -- 3 or more made shots in a row, or 60%+ shooting on 8 or more shots -- or
  // a team on a momentum run going into it (3 or more wins in a row, or 8 or more of its last 10). Its menu offers only
  // those; the window is titled HOT HAND for a player and MOMENTUM RUN for a team, with the same layout: the picture
  // and name, the numbers, and every shot (or each of the last 10 games) in order, with the streak lit up.
  var formCache = {};
  function teamForm(team, g) {
    // the team's finished games before this one (this one too once it's over), from ESPN's schedule
    if (source !== "espn" || !team || !team.id) return Promise.resolve(null);
    var year = parseInt(seasonOf(g.when).slice(0, 4), 10) + 1, key = team.id + ":" + year;
    if (!formCache[key]) {
      var url = ESPN + "teams/" + team.id + "/schedule?season=" + year + "&seasontype=";
      formCache[key] = Promise.all([getJSON(url + "2").catch(function () { return null; }), getJSON(url + "3").catch(function () { return null; })])
        .then(function (res) {
          var games = [];
          res.forEach(function (sch) {
            ((sch && sch.events) || []).forEach(function (e) {
              var c = (e.competitions || [])[0] || {}, st = ((c.status || e.status || {}).type || {});
              if (!st.completed) return;
              var us = null, them = null;
              (c.competitors || []).forEach(function (t) { if (String(t.id || (t.team && t.team.id)) === String(team.id)) us = t; else them = t; });
              if (!us || !them) return;
              var sc = function (t) { return num(t.score && typeof t.score === "object" ? (t.score.value != null ? t.score.value : t.score.displayValue) : t.score); };
              var a = sc(us), b = sc(them);
              games.push({ id: String(e.id), when: e.date, win: us.winner != null ? !!us.winner : a > b, pts: a, opp: b,
                           vs: triOf((them.team || {})), home: us.homeAway === "home" });
            });
          });
          games.sort(function (x, y) { return String(x.when).localeCompare(String(y.when)); });
          return games;
        }).catch(function () { return null; });
    }
    return formCache[key].then(function (games) {
      if (!games) return null;
      var upTo = games.filter(function (x) { return g.final ? String(x.when) <= String(g.when) || x.id === String(g.id) : String(x.when) < String(g.when); });
      var last = upTo.slice(-10);
      if (!last.length) return null;
      var streak = 0, kind = last[last.length - 1].win;
      for (var i = upTo.length - 1; i >= 0 && upTo[i].win === kind; i--) streak++;
      var w = upTo.filter(function (x) { return x.win; }).length;
      return { last: last, wins10: last.filter(function (x) { return x.win; }).length, streak: streak, winning: kind,
               record: w + "-" + (upTo.length - w), games: upTo.length };
    });
  }
  function momentum(f) { return !!f && ((f.winning && f.streak >= 3) || (f.last.length >= 10 && f.wins10 >= 8)); }
  function shotRun(g, pid) {
    var seq = (g.shots || []).filter(function (s) { return String(s[1]) === String(pid); });
    var best = 0, bestEnd = -1, run = 0;
    seq.forEach(function (s, i) { run = s[5] ? run + 1 : 0; if (run > best) { best = run; bestEnd = i; } });
    return { seq: seq, best: best, bestStart: bestEnd - best + 1, bestEnd: bestEnd, now: run };
  }
  function hotHand(g, p) {
    var r = shotRun(g, p.id);
    return r.best >= 3 || (p.fga >= 8 && p.fgm / p.fga >= 0.6);
  }
  function hotItems(g) {
    var items = [];
    (g.players || []).filter(function (p) { return hotHand(g, p); }).sort(function (a, b) {
      return shotRun(g, b.id).best - shotRun(g, a.id).best || b.pts - a.pts;
    }).forEach(function (p) { items.push([String(p.id), esc(p.short || p.name) + " · " + triTag(teamOf(g, p.team), 14)]); });
    ["away", "home"].forEach(function (side) {
      if (g.form && momentum(g.form[side])) items.push(["team:" + side, triTag(teamOf(g, side), 14) + " " + esc(teamOf(g, side).name)]);
    });
    return items;
  }
  function hotTitle(g, sub) { return sub && String(sub).indexOf("team:") === 0 ? "Momentum run" : "Hot hand"; }
  function prepareHot(g) {
    if (g.form) return g.form;
    return Promise.all([teamForm(g.away, g), teamForm(g.home, g)]).then(function (f) { g.form = { away: f[0], home: f[1] }; return g.form; });
  }
  function renderHot(body, g, sub, card) {
    var c = colors(g);
    if (!sub) {
      body.appendChild(el("div", "ls-hot-none", "No hot hands in this game" + (g.live ? " yet" : "") + ".<br><span>A hot hand: 3+ made shots in a row, " +
        "or 60%+ shooting on 8+ shots. A momentum run: 3+ wins in a row, or 8 of the last 10.</span>"));
      return;
    }
    var isTeam = String(sub).indexOf("team:") === 0, alive = true, timer = null;
    if (isTeam) {
      var side = sub.slice(5), team = teamOf(g, side), col = side === "home" ? c.home : c.away, f = (g.form || {})[side];
      if (!f) return;
      var avg = function (k) { return f.last.reduce(function (a, x) { return a + x[k]; }, 0) / f.last.length; };
      var margin = avg("pts") - avg("opp");
      // won-lost over the last 10 games that fit (home games, road games, games decided by 5 or fewer)
      var wl = function (keep) { var gs = f.last.filter(keep), w = gs.filter(function (x) { return x.win; }).length; return gs.length ? w + "-" + (gs.length - w) : "–"; };
      body.appendChild(el("div", "ls-player ls-hot-head", '<span class="ls-hot-logo">' + logoImg(team, 62) + "</span>" +
        '<div><div class="nm">' + esc(team.city + " " + team.name) + '</div><div class="tm">' + esc(f.record) + " this season</div>" +
        '<div class="mn">' + (f.winning && f.streak >= 3 ? f.streak + " wins in a row" : f.wins10 + " of the last 10 won") + "</div></div>"));
      var s1 = el("div", "ls-stats ls-stats-roomy",
        "<div><span>Last 10</span><b>" + f.wins10 + "-" + (f.last.length - f.wins10) + "</b></div>" +
        "<div><span>Streak</span><b>" + (f.winning ? "W" : "L") + f.streak + "</b></div>" +
        "<div><span>Avg margin</span><b>" + (margin > 0 ? "+" : margin < 0 ? "−" : "") + Math.abs(margin).toFixed(1) + "</b></div>" +
        "<div><span>Points</span><b>" + avg("pts").toFixed(1) + "</b></div>" +
        "<div><span>Allowed</span><b>" + avg("opp").toFixed(1) + "</b></div>" +
        "<div><span>Best win</span><b>" + (function () { var m = Math.max.apply(null, f.last.map(function (x) { return x.pts - x.opp; })); return m > 0 ? "+" + m : "–"; })() + "</b></div>" +
        "<div><span>Home</span><b>" + wl(function (x) { return x.home; }) + "</b></div>" +
        "<div><span>Road</span><b>" + wl(function (x) { return !x.home; }) + "</b></div>" +
        "<div><span>Close games</span><b>" + wl(function (x) { return Math.abs(x.pts - x.opp) <= 5; }) + "</b></div>");
      s1.style.setProperty("--ls-num", col);
      body.appendChild(s1);
      var run0 = f.last.length - (f.winning ? Math.min(f.streak, f.last.length) : 0);
      var chips = f.last.map(function (x, i) {
        return '<span class="ls-hot-chip' + (x.win ? " w" : " l") + (i >= run0 ? " run" : "") + '" title="' + (x.home ? "vs " : "at ") + esc(x.vs) + " " + x.pts + "-" + x.opp + '">' +
          '<b>' + (x.win ? "W" : "L") + "</b><i>" + x.pts + "-" + x.opp + "</i></span>";
      }).join("");
      var seqT = el("div", "ls-hot-seq", '<div class="ls-title">Last ' + f.last.length + " games, oldest first</div>" + '<div class="ls-hot-row chips">' + chips + "</div>");
      seqT.style.setProperty("--team", col);
      body.appendChild(seqT);
      reveal(seqT.querySelectorAll(".ls-hot-chip"));
      return function () { alive = false; clearTimeout(timer); };
    }
    var p = playerById(g)[sub];
    if (!p) return;
    var tm = teamOf(g, p.team), pc = p.team === "home" ? c.home : c.away, r = shotRun(g, p.id);
    var tpm = r.seq.filter(function (x) { return x[5] && x[6] === 3; }).length, tpa = r.seq.filter(function (x) { return x[6] === 3; }).length;
    body.appendChild(el("div", "ls-player ls-hot-head", '<img alt="" loading="lazy" src="' + esc(headshotOf(p)) + '" onerror="this.style.visibility=\'hidden\'">' +
      '<div><div class="nm">' + esc(p.name) + '</div><div class="tm">' + logoImg(tm, 14) + esc(tm.city + " " + tm.name) + "</div>" +
      '<div class="mn">' + (r.best >= 3 ? r.best + " makes in a row" : Math.round(100 * p.fgm / Math.max(1, p.fga)) + "% from the field") + "</div></div>"));
    var dots = r.seq.map(function (x, i) {
      return '<span class="ls-hot-dot' + (x[5] ? " m" : " x") + (x[6] === 3 ? " three" : "") + (i >= r.bestStart && i <= r.bestEnd && r.best >= 3 ? " run" : "") +
        '" title="' + (x[5] ? "Make" : "Miss") + (x[6] === 3 ? " (3)" : "") + " · " + esc(clockAt(x[0])) + '"></span>';
    }).join("");
    var seqP = el("div", "ls-hot-seq" + (r.seq.length <= 16 ? " big" : ""), '<div class="ls-title">Every shot, in order</div><div class="ls-hot-row">' + dots + "</div>" +
      '<div class="ls-hot-key"><span><i class="ls-hot-dot m"></i>make</span><span><i class="ls-hot-dot x"></i>miss</span><span><i class="ls-hot-dot m three"></i>three</span></div>');
    seqP.style.setProperty("--team", pc);
    body.appendChild(seqP);
    reveal(seqP.querySelectorAll(".ls-hot-row .ls-hot-dot"));
    var s2 = el("div", "ls-stats ls-stats-roomy",
      "<div><span>FG</span><b>" + p.fgm + "/" + p.fga + "</b></div>" +
      "<div><span>FG%</span><b>" + (p.fga ? (100 * p.fgm / p.fga).toFixed(1) + "%" : "–") + "</b></div>" +
      "<div><span>Points</span><b>" + p.pts + "</b></div>" +
      "<div><span>Best run</span><b>" + r.best + "</b></div>" +
      "<div><span>" + (g.live ? "Current run" : "Closing run") + "</span><b>" + r.now + "</b></div>" +
      "<div><span>3PT</span><b>" + tpm + "/" + tpa + "</b></div>");
    s2.style.setProperty("--ls-num", pc);
    // quarter by quarter: made / attempted, with a bar for the percentage (above the numbers)
    var per = {};
    r.seq.forEach(function (x) { var q = Math.min(5, x[7] || 1); per[q] = per[q] || [0, 0]; per[q][1]++; if (x[5]) per[q][0]++; });
    var qs = [1, 2, 3, 4].concat(per[5] ? [5] : []);
    var qBox = el("div", "ls-hot-q", qs.map(function (q) {
      var v = per[q] || [0, 0];
      return "<div><span>" + (q === 5 ? "OT" : "Q" + q) + "</span><b>" + v[0] + "/" + v[1] + '</b><em><i style="width:' +
        (v[1] ? Math.round(100 * v[0] / v[1]) : 0) + '%"></i></em></div>';
    }).join(""));
    qBox.style.gridTemplateColumns = "repeat(" + qs.length + ", minmax(0, 1fr))";
    qBox.style.setProperty("--team", pc);
    body.appendChild(qBox);
    body.appendChild(s2);
    // they appear one after another, then the streak lights up
    function reveal(list) {
      var k = 0;
      Array.prototype.forEach.call(list, function (n) { n.classList.add("hide"); });
      (function step() {
        if (!alive) return;
        if (card && card._hidden) { timer = setTimeout(step, 300); return; }
        if (k < list.length) { list[k].classList.remove("hide"); k++; timer = setTimeout(step, Math.max(40, Math.min(160, 2400 / list.length))); }
        else body.classList.add("ls-hot-lit");
      })();
    }
    return function () { alive = false; clearTimeout(timer); body.classList.remove("ls-hot-lit"); };
  }

  // ------------------------------------------------------------ 7. count-up tiles
  // how long each team was ahead (seconds): the score margin between one score and the next
  function leadTimes(g) {
    var flow = g.flow || [], last = flow[flow.length - 1] || [0, 0, 0];
    var tEnd = g.live ? Math.max(last[0], g.now || 0) : gameEnd(g);
    var t0 = 0, m = 0, out = { home: 0, away: 0 };
    function add(t) { var dt = Math.max(0, t - t0); if (m > 0) out.home += dt; else if (m < 0) out.away += dt; t0 = Math.max(t0, t); }
    flow.forEach(function (f) { add(f[0]); m = f[1] - f[2]; });
    add(tEnd);
    return out;
  }
  // the six boxes: lead changes, biggest visitor lead, biggest home lead / times tied, visitor's time in the lead,
  // home team's time in the lead. A team's box is labelled with its logo, as tall as the two lines of words beside it
  // ("BIGGEST" over "LEAD", "LEAD" over "TIME").
  function teamLabel(team, line1, line2) {
    return '<span class="tl">' + logoImg(team, 22) + '<span class="tw">' + esc(line1) + "<br>" + esc(line2) + "</span></span>";
  }
  function renderTiles(body, g) {
    var h = g.home.stats || {}, a = g.away.stats || {};
    var c = colors(g), lt = leadTimes(g);
    var tiles = [[g.leadChanges || 0, esc("Lead changes")],
      [num(a.biggestLead), teamLabel(g.away, "Biggest", "lead"), c.away],
      [num(h.biggestLead), teamLabel(g.home, "Biggest", "lead"), c.home],
      [g.timesTied || 0, esc("Times tied")],
      [lt.away, teamLabel(g.away, "Lead", "time"), c.away, mmss],
      [lt.home, teamLabel(g.home, "Lead", "time"), c.home, mmss]];
    var box = el("div", "ls-tiles ls-tiles3");
    tiles.forEach(function (t) {
      var d = el("div", "ls-tile" + (t[2] ? "" : " gold"), "<b>0</b><span>" + t[1] + "</span>");
      if (t[2]) { d.querySelector("b").style.color = t[2]; d.querySelector("span").style.color = t[2]; }
      box.appendChild(d);
      countUp(d.querySelector("b"), t[0], 1400, t[3]);
    });
    body.appendChild(box);
  }

  // ------------------------------------------------------------ ticker: every game, clickable
  // "(logo) BOS 73 – 37 NYK (logo) (breathing dot) 3rd 7:37". Clicking a game shows it in every card below.
  function tickerItem(g, copy) {
    var c = colors(g);
    var st = g.live ? (g.tick || g.status) : (g.final ? (g.tick || "Final") : (g.tick || g.status || ""));
    var tag = index.mode === "finals" && g.label ? '<span class="lbl">' + esc(g.label) + "</span>" : "";
    return '<button type="button" class="ls-tk' + (g.live ? " live" : "") + (g.id === (index.selected || index["default"]) ? " on" : "") +
      '" data-id="' + esc(g.id) + '"' + (copy ? ' tabindex="-1" aria-hidden="true"' : ' aria-label="Show ' + esc(gameOptionLabel(g)) + ' in every card"') + ">" +
      tag + logoImg(g.away, 18) + '<span class="t" style="color:' + c.away + '">' + esc(g.away.tri) + '</span><span class="s" style="color:' + c.away + '">' +
      g.away.score + '</span><span class="d">–</span><span class="s" style="color:' + c.home + '">' + g.home.score + '</span><span class="t" style="color:' +
      c.home + '">' + esc(g.home.tri) + "</span>" + logoImg(g.home, 18) +
      (g.live ? '<i class="ls-dot" aria-hidden="true"></i>' : "") + '<span class="st">' + esc(st) + "</span></button>";
  }
  function renderTicker() {
    var track = root.querySelector(".ls-ticker-track");
    if (!track || !index) return;
    var games = index.games || [];
    if (!games.length) { track.innerHTML = ""; return; }
    // enough copies of the list to fill the bar, then the whole thing twice for a seamless loop
    var reps = Math.max(1, Math.ceil(8 / games.length)), one = "";
    for (var r = 0; r < reps; r++) {
      games.forEach(function (g) { one += tickerItem(g, r > 0) + '<span class="sep" aria-hidden="true">|</span>'; });
    }
    track.innerHTML = one + one.replace(/<button type="button" class="ls-tk/g, '<button type="button" tabindex="-1" aria-hidden="true" class="ls-tk')
      .replace(/ aria-label="[^"]*"/g, "");
    requestAnimationFrame(function () {
      var half = track.scrollWidth / 2;
      if (half > 0) track.style.animationDuration = Math.max(20, half / 42).toFixed(1) + "s";     // ~42 px a second
    });
  }
  // under the badge: during the Finals stretch the series ("NYK wins 4-1"); otherwise the date of the games shown
  function longDay(iso) {
    try { return new Date(iso).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric", timeZone: "America/New_York" }); }
    catch (e) { return String(iso || "").slice(0, 10); }
  }
  function renderHeader() {
    var h = headerText(), badge = root.querySelector(".ls-badge"), sub = root.querySelector(".ls-sub");
    if (!badge) return;
    badge.classList.toggle("live", h.live);
    badge.classList.toggle("date", !!h.date);          // a date reads "Wednesday, November 21, 2026" (not in capitals)
    badge.querySelector("span").textContent = h.badge;
    if (sub) { sub.textContent = h.sub; sub.style.display = h.sub ? "" : "none"; }
  }
  function forEachCard(fn) { Array.prototype.forEach.call(root.querySelectorAll(".ls-card"), fn); }
  // a day picked in ALL GAMES: during the season the tape and every window move to that day; during the Finals and
  // the offseason the tape keeps every Finals game and the windows switch to that day's game
  function setDay(day) {
    if (!index || !day) return;
    if (index.mode !== "season") {
      var g = index.games.filter(function (x) { return x.day === day; })[0];
      if (g) selectGame(g.id);
      return;
    }
    var today = etDay(new Date().toISOString());
    var fresh = day === today ? scoreboard().then(function (b) { return ((b && b.events) || []).filter(realEvent).map(brief); })
      : Promise.resolve(index.dayGames[day]);
    fresh.then(function (games) {
      if (games) index.dayGames[day] = games;
      applyDay(index, day);
      renderTicker();
      renderHeader();
      forEachCard(function (c) { if (c._setGames) c._setGames(); });
      if (root._toStart) root._toStart();
      manageRefresh();
    }).catch(function () {});
  }
  function selectGame(id) {
    if (!id) return;
    index.selected = id;
    // a game that isn't among the windows' games (today's, while they still show the last game day): the windows
    // switch to the tape's games
    var inCards = (index.cardGames || index.games).some(function (g) { return g.id === id; });
    if (!inCards) {
      index.cardGames = index.games;
      forEachCard(function (c) { if (c._setGames) c._setGames(); });
    }
    Array.prototype.forEach.call(root.querySelectorAll(".ls-tk"), function (b) { b.classList.toggle("on", b.getAttribute("data-id") === id); });
    Array.prototype.forEach.call(root.querySelectorAll(".ls-card"), function (card) { if (card._showGame) card._showGame(id); });
    if (root._toStart) root._toStart();                      // the cards start over from the first one
  }

  // ------------------------------------------------------------ auto-scroll
  function autoScroll(vp) {
    if (REDUCE) return;
    // Moves only while nobody is using it: a mouse over the cards stops it and it carries on the moment the mouse
    // leaves; on a touch screen it stays still while a finger is on it (or a dropdown is open) and for 3 seconds
    // after, then carries on.
    var pos = vp.scrollLeft, hovering = false, touching = false, waitUntil = performance.now() + 2500, visible = true, holdEnd = 0;
    function syncFrom(ms) { waitUntil = Math.max(waitUntil, performance.now() + ms); pos = vp.scrollLeft; }
    vp.addEventListener("pointerenter", function (e) { if (e.pointerType === "mouse") hovering = true; });
    vp.addEventListener("pointerleave", function (e) { if (e.pointerType === "mouse") { hovering = false; pos = vp.scrollLeft; } });
    vp.addEventListener("touchstart", function () { touching = true; }, { passive: true });
    vp.addEventListener("touchend", function () { touching = false; syncFrom(3000); }, { passive: true });
    vp.addEventListener("touchcancel", function () { touching = false; syncFrom(3000); }, { passive: true });
    var hadPicker = false;
    root._toStart = function () { pos = 0; holdEnd = 0; vp.scrollLeft = 0; };
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) { visible = es[0].isIntersecting; }, { threshold: 0.2 }).observe(vp);
    }
    (function step(now) {
      var max = vp.scrollWidth - vp.clientWidth;
      var pickerOpen = !!(openPicker && vp.contains(openPicker));
      if (pickerOpen) hadPicker = true;
      else if (hadPicker) { hadPicker = false; if (!hovering) syncFrom(3000); }
      if (hovering || touching || pickerOpen) pos = vp.scrollLeft;
      else if (visible && now >= waitUntil && max > 4) {
        if (holdEnd) {
          if (now >= holdEnd) {
            holdEnd = 0;
            vp.scrollTo({ left: 0, behavior: "smooth" });
            waitUntil = now + 2600;
            pos = 0;
          }
        } else {
          if (Math.abs(vp.scrollLeft - Math.round(pos)) > 2) pos = vp.scrollLeft;     // moved by hand: carry on from there
          pos += 0.7;
          if (pos >= max) { pos = max; holdEnd = now + 2500; }
          vp.scrollLeft = Math.round(pos);
        }
      }
      requestAnimationFrame(step);
    })(performance.now());
  }

  // ------------------------------------------------------------ one height for every window
  // Every window is as tall as the shot chart window: its court and stats, ending just under the last line of stats.
  // (The windows' contents are laid out to fit in that; ALL GAMES scrolls inside it on a busy night.)
  function fitHeights() {
    var track = root.querySelector(".ls-track"), shot = track && track.querySelector(".ls-card-shot");
    if (!shot || !shot.offsetWidth) return;
    shot.style.height = "auto";
    var h;
    if (shot.querySelector(".ls-court") && shot.querySelector(".ls-stats")) h = shot.getBoundingClientRect().height;
    else {                                   // an upcoming game in it: the same height, worked out from its shape
      var cs = getComputedStyle(shot), inner = shot.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      h = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom) + (parseFloat(cs.rowGap) || 9) +
        shot.querySelector(".ls-card-top").getBoundingClientRect().height + inner * 381.5 / 504 + 14 + 126.4;
    }
    shot.style.height = "";
    if (h > 120) track.style.setProperty("--ls-card-h", Math.ceil(h + 1) + "px");
  }
  var fitTimer = null;
  window.addEventListener("resize", function () { clearTimeout(fitTimer); fitTimer = setTimeout(fitHeights, 150); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { fitHeights(); });

  // ------------------------------------------------------------ build
  function build() {
    renderHeader();
    var track = root.querySelector(".ls-track");
    track.innerHTML = "";
    function teamItems(g) { return [["home", logoImg(g.home, 14) + esc(g.home.name)], ["away", logoImg(g.away, 14) + esc(g.away.name)]]; }
    var cards = [
      makeCard({ title: function (g) {
                   if (g.live) return '<i class="ls-dot ls-dot-title" aria-hidden="true"></i>Live game';
                   if (g.pre) return etDay(g.when) > etDay(new Date().toISOString()) ? "Upcoming game" : "Today's game";
                   return "Final score";
                 },
                 name: "Final score", wide: true, render: renderScore }),
      makeCard({ title: "Shot chart", sub: "player", subItems: function (g) { return playerItems(g, true); }, render: renderShots,
                 cls: "ls-card-shot", onDrawn: fitHeights }),
      makeCard({ title: "Player card", sub: "player", subItems: function (g) { return playerItems(g, false); }, render: renderPlayer }),
      makeCard({ title: "Team comparison", render: renderCompare }),
      makeCard({ title: "Lineup network", wide: true, sub: "team", subItems: teamItems, render: renderLineups,
                 mode: { label: "net ratings", def: "season", items: [["season", "Season Net Ratings"], ["live", "Live Game Net Ratings"]] } }),
      makeCard({ title: "Win probability", render: renderWinProb }),
      makeCard({ title: "Assist web", sub: "team", subItems: teamItems, render: renderAssists }),
      makeCard({ title: hotTitle, name: "Hot hand", sub: "player or team", subItems: hotItems, prepare: prepareHot, render: renderHot }),
      makeCard({ title: "Scoring race", render: renderRace }),
      makeWatchCard(),
    ];
    cards.forEach(function (c) { track.appendChild(c); });
    renderTicker();
    root.querySelector(".ls-ticker-track").addEventListener("click", function (e) {
      var b = e.target && e.target.closest ? e.target.closest(".ls-tk") : null;
      if (b) { selectGame(b.getAttribute("data-id")); b.blur(); }
    });
    // the ticker only stops while a mouse is over it (CSS); on a touch screen it stays still for 3 seconds after a tap
    var tk = root.querySelector(".ls-ticker"), tkTimer = null;
    tk.addEventListener("touchstart", function () { clearTimeout(tkTimer); tk.classList.add("hold"); }, { passive: true });
    tk.addEventListener("touchend", function () { clearTimeout(tkTimer); tkTimer = setTimeout(function () { tk.classList.remove("hold"); }, 3000); }, { passive: true });
    if ("IntersectionObserver" in window) {
      var vp = root.querySelector(".ls-viewport");
      var io = new IntersectionObserver(function (es) {
        es.forEach(function (e) { e.target._hidden = !e.isIntersecting; });
      }, { root: vp, threshold: 0.05 });
      cards.forEach(function (c) { io.observe(c); });
    }
    autoScroll(root.querySelector(".ls-viewport"));
  }

  function start(data) {
    if (!data || !data.games || !data.games.length) return false;
    index = data;
    if (!index["default"]) index["default"] = index.games[0].id;
    if (!index.cardGames) index.cardGames = index.games;
    if (!index.days) {                                      // the backup data (data/live): its games' days
      index.days = [];
      index.games.forEach(function (g) { if (g.day && index.days.indexOf(g.day) < 0) index.days.push(g.day); });
      index.days.sort().reverse();
    }
    root.hidden = false;
    build();
    manageRefresh();
    return true;
  }
  // Every minute while it matters -- a game is live, or (during the season) today is shown and its games haven't
  // all finished -- fresh scores for the tape, the header and ALL GAMES, and windows showing a live game redraw. The
  // moment today's first game tips off, the windows move from the last game day to today's games.
  var refreshTimer = null;
  function needsRefresh() {
    if (!index || source !== "espn") return false;
    if (index.games.some(function (g) { return g.live; })) return true;
    return index.mode === "season" && index.day === etDay(new Date().toISOString()) && !index.games.every(function (g) { return g.final; });
  }
  function manageRefresh() {
    if (needsRefresh() && !refreshTimer) refreshTimer = setInterval(refreshLive, 60000);
    else if (!needsRefresh() && refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
  }
  function refreshLive() {
    if (document.hidden) return;
    var today = etDay(new Date().toISOString());
    scoreboard().then(function (b) {
      var fresh = ((b && b.events) || []).filter(realEvent).map(brief), byId = {};
      fresh.forEach(function (g) { byId[g.id] = g; });
      var liveNow = {};
      index.games.forEach(function (g) {
        var n = byId[g.id];
        if (!n) return;
        if (g.live || n.live) liveNow[g.id] = 1;
        g.home.score = n.home.score; g.away.score = n.away.score; g.live = n.live; g.final = n.final; g.status = n.status; g.tick = n.tick;
      });
      Object.keys(liveNow).forEach(function (id) { delete cache[id]; });
      if (index.mode === "season" && index.day === today) {
        var wasWaiting = index.cardGames !== index.games;
        index.dayGames[today] = index.games;
        if (wasWaiting && index.games.some(started)) { applyDay(index, today); forEachCard(function (c) { if (c._setGames) c._setGames(); }); }
      }
      forEachCard(function (card) { if (card._refresh) card._refresh(liveNow); });
      renderTicker();
      renderHeader();
      manageRefresh();
    }).catch(function () {});
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
        known[g.id].live = g.live; known[g.id].final = g.final; known[g.id].status = g.status; known[g.id].tick = g.tick; } });
      Array.prototype.forEach.call(root.querySelectorAll(".ls-card"), function (card) {
        if (card._refresh) card._refresh(liveNow);
      });
      renderTicker();
      var badge = root.querySelector(".ls-badge");
      var anyLive = index.games.some(function (g) { return g.live; });
      badge.classList.toggle("live", anyLive);
    }).catch(function () {});
  }
  espnIndex().then(function (data) {
    if (!start(data)) throw new Error("no ESPN games");
  }).catch(function () {
    source = "static";
    getJSON(BASE + "index.json").then(start).catch(function () { /* no data anywhere: the strip stays hidden */ });
  });
})();
