/* ============================================================
   Live strip: the auto-scrolling row of animated cards right above
   the dashboard. The visitor's own browser reads ESPN's public NBA
   feed (site.api.espn.com -- it allows websites to read it; the
   NBA's own feed does not), so there is nothing to run or set up:
   the strip is always current.
     * A game on right now: the live games plus today's finished ones.
       While a game is live everything updates by itself about every
       second (the scores, the clock, the play-by-play windows) -- no
       reloading the page (see "live updates" at the end).
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
  // the skinny tape can sit elsewhere on the page (the home page has it at the very top, above the banner)
  var tapeBox = document.getElementById("ls-tape");
  var tickerNode = (tapeBox && tapeBox.querySelector(".ls-ticker")) || root.querySelector(".ls-ticker");
  function tickerTrack() { return tickerNode && tickerNode.querySelector(".ls-ticker-track"); }
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
  var loaded = {};                                  // id -> the game as last read (live updates replace it)
  function loadGame(id) {
    if (!cache[id]) {
      cache[id] = (source === "espn" ? getJSON(ESPN + "summary?event=" + id).then(function (s) { return fromSummary(s, id); })
        : getJSON(BASE + "games/" + id + ".json")).then(function (g) {
          g._at = Date.now();
          loaded[id] = g;
          return g;
        }).catch(function (e) { delete cache[id]; throw e; });
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
  // A team whose logo always comes from somewhere other than ESPN, wherever it appears in the strip (it wins over the
  // logo in ESPN's own feed). The Celtics use 2kratings' current logo, the same one as everywhere in the dashboard
  // (streamlit/teams.py, TEAM_LOGO_SOURCE): ESPN serves their alternate logo, not their primary one.
  var TEAM_LOGO = { BOS: "https://www.2kratings.com/wp-content/uploads/Boston-Celtics-Current-Logo.svg" };
  function logoFor(tri) {
    var t = String(tri || "").toUpperCase();
    if (TEAM_LOGO[t]) return TEAM_LOGO[t];
    return t ? "https://a.espncdn.com/i/teamlogos/nba/500/" + (ESPN_ABBR[t] || t.toLowerCase()) + ".png" : "";
  }
  function logoSrc(team) {
    var t = String((team && team.tri) || "").toUpperCase();
    return TEAM_LOGO[t] || (team && team.logo) || logoFor(t);
  }
  function logoImg(team, size) {
    var src = logoSrc(team);
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
    var src = logoSrc(team);
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
    var logo = TEAM_LOGO[tri] || t.logo || (t.logos && t.logos[0] && t.logos[0].href) || logoFor(tri);
    return { tri: tri, name: t.name || t.shortDisplayName || tri, city: t.location || "", logo: logo,
      score: num(c.score), color: TEAM_COLORS[tri] || "#D4AF37", alt: TEAM_ALT[tri] || "#e8e8e8", record: recordOf(c) };
  }
  // the team's season record ("3-1"): the summary's competitor has record[], the scoreboard's has records[]
  function recordOf(c) {
    var list = (c && (c.record || c.records)) || [];
    if (typeof list === "string") return list;
    var r = list.filter(function (x) { return x && (x.type === "total" || x.name === "overall" || x.name === "All Splits"); })[0] || list[0];
    var v = r && (r.summary || r.displayValue);
    return v && /^\d+-\d+$/.test(v) ? v : "";
  }
  function brief(e) {
    var c = e.competitions[0], st = (e.status || c.status || {}).type || {}, home = null, away = null;
    c.competitors.forEach(function (t) { if (t.homeAway === "home") home = teamBrief(t); else away = teamBrief(t); });
    var note = (c.notes || []).map(function (n) { return n.headline || ""; }).join(" ");
    var game = /game\s*(\d+)/i.exec(note);
    var stt = e.status || c.status || {}, lp = (c.situation || {}).lastPlay || null;
    return { id: String(e.id), label: game ? "Game " + game[1] : "", date: niceDay(e.date), day: etDay(e.date), when: e.date,
      status: st.shortDetail || st.detail || "", tick: clockText(stt), live: st.state === "in",
      final: st.state === "post", pre: st.state === "pre", series: "",
      period: parseInt(stt.period, 10) || 0, displayClock: stt.displayClock || "", statusName: String(st.name || ""),
      lastPlayId: lp ? String(lp.id || "") : "", espnHome: lp && lp.probability && lp.probability.homeWinPercentage != null ?
        num(lp.probability.homeWinPercentage) : null,
      finals: /nba finals/i.test(note) || !!(c.type && c.type.abbreviation === "FINAL"), home: home, away: away };
  }
  var boards = {};                                   // a past day's scoreboard, once fetched (today's is always fetched fresh)
  var knownDays = {};                                // every date in the season calendars seen so far
  // Always asked for one date, today's included: ESPN's scoreboard without a date is ITS current day, which on a day
  // with no games is the next day that has some -- before opening night that put the opener's games under "today"
  // two days early.
  function scoreboard(day) {
    var today = etDay(new Date().toISOString());
    day = day || today;
    if (day !== today && boards[day]) return boards[day];
    var p = getJSON(ESPN + "scoreboard?dates=" + day.replace(/-/g, "")).then(function (sb) {
      calendarDays(sb).forEach(function (d) { knownDays[d] = 1; });
      return sb;
    });
    if (day !== today) { boards[day] = p; p.catch(function () { delete boards[day]; }); }
    return p;
  }
  // that day's real games (and only that day's: a game is on the day it tips off, Eastern time)
  function gamesOfDay(sb, day) {
    return ((sb && sb.events) || []).filter(function (e) { return realEvent(e) && etDay(e.date) === day; }).map(brief);
  }
  function addDays(day, n) {
    var p = String(day).split("-"), d = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2] + n));
    return d.toISOString().slice(0, 10);
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
        return scoreboard(d).then(function (b) { return gamesOfDay(b, d); }).catch(function () { return []; });
      })).then(function (lists) {
        lists.forEach(function (games, k) { if (games.length && found.length < n) found.push({ day: chunk[k], games: games }); });
        return batch(i + 7);
      });
    }
    return batch(0);
  }
  // On a day with no games: tomorrow's games, when there are some ({ day, games }, else null). Only the day before a
  // game day shows its games as "UPCOMING GAMES"; two or more days before, the tape keeps the last games played.
  function nextGameDay(today) {
    var tomorrow = addDays(today, 1);
    return scoreboard(tomorrow).then(function (b) {
      var games = gamesOfDay(b, tomorrow);
      return games.length ? { day: tomorrow, games: games } : null;
    }).catch(function () { return null; });
  }
  function espnIndex() {
    var today = etDay(new Date().toISOString());
    return scoreboard(today).then(function (sb) {
      var lg = (sb.leagues || [])[0] || {}, season = lg.season || {};
      var seasonText = season.displayName || "";
      var days = calendarDays(sb);
      var todays = gamesOfDay(sb, today);
      if (todays.some(function (g) { return g.finals; })) return finalsIndex(days, today, seasonText).then(stamp);
      // during the season: the last 7 days that had games (today first when there are games today, even before tip-off);
      // with no games today but some tomorrow, tomorrow goes first ("UPCOMING GAMES")
      var cand = [today].concat(days.filter(function (d) { return d < today; }).reverse());
      var ahead = todays.length ? Promise.resolve(null) : nextGameDay(today);
      return Promise.all([findGameDays(cand, 7, today, todays), ahead]).then(function (res) {
        var found = res[0], next = res[1];
        if (found.length) {
          if (found[0].games.some(function (g) { return g.finals; })) return finalsIndex(days, today, seasonText).then(stamp);
          if (next) found.unshift(next);
          var idx = { mode: "season", label: "", season: seasonText, days: found.map(function (x) { return x.day; }), dayGames: {},
                      seasonStart: String(season.startDate || "").slice(0, 10), seasonYear: season.year };
          found.forEach(function (x) { idx.dayGames[x.day] = x.games; });
          applyDay(idx, found[0].day);
          return stamp(idx);
        }
        // nothing played yet this season (the offseason and preseason): the last Finals -- except on the day before
        // opening night, when the tape shows the opener's games ("UPCOMING GAMES") and the windows keep the Finals
        var prevYear = (parseInt(season.year, 10) || new Date().getFullYear()) - 1;
        var prevSeason = (prevYear - 1) + "-" + String(prevYear).slice(2);
        return scoreboard(prevYear + "-06-15").then(function (old) {
          return finalsIndex(calendarDays(old), today, prevSeason);
        }).catch(function () { return null; }).then(function (fin) {
          if (!next) return stamp(fin);
          var up = { mode: "season", label: "", season: seasonText, days: [next.day], dayGames: {},
                     seasonStart: String(season.startDate || "").slice(0, 10), seasonYear: season.year, preOpener: true };
          up.dayGames[next.day] = next.games;
          if (fin) {                                    // the Finals' days stay pickable in ALL GAMES
            up.cardsFallback = fin.games;
            fin.days.forEach(function (d) {
              up.days.push(d);
              up.dayGames[d] = fin.games.filter(function (g) { return g.day === d; });
            });
          }
          applyDay(up, next.day);
          return stamp(up);
        });
      });
    });
  }
  // the index remembers the day it was made for: past midnight (Eastern) the page reads the new day by itself
  function stamp(idx) { if (idx) idx.madeFor = etDay(new Date().toISOString()); return idx; }
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
      if (idx.cardsFallback) cards = idx.cardsFallback;            // the day before opening night: the last Finals
      else if (prev && (idx.dayGames[prev] || []).length) cards = idx.dayGames[prev];
    }
    idx.cardGames = cards;
    var live = cards.filter(function (g) { return g.live; })[0], done = cards.filter(started)[0];
    if (cards === idx.cardsFallback) done = cards.filter(started).slice(-1)[0];     // (the Finals: the last game)
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
          oreb: num(v.offensiveRebounds), dreb: num(v.defensiveRebounds), pf: num(v.fouls),
          pm: num(v.plusMinus), img: (ath.headshot || {}).href || "" };
        if (!p.starter) bench += p.pts;
        players.push(p);
      });
      (side === "home" ? home : away).stats.benchPts = bench;
    });
    var shots = [], flow = [[0, 0, 0]], assists = [], scoring = [], lastH = 0, lastA = 0, playT = {};
    // every countable thing each player did, in game order ([seconds, player id, +n]) -- for the LEADERBOARD
    var ev = { reb: [], oreb: [], dreb: [], ast: [], stl: [], blk: [], fgm: [], fga: [], tpm: [], tpa: [], ftm: [], fta: [], tov: [], pf: [] };
    (s.plays || []).forEach(function (pl) {
      var t = elapsed(pl.period && pl.period.number, pl.clock && pl.clock.displayValue);
      playT[String(pl.id)] = t;
      var side = sides[String(pl.team && pl.team.id)] === "home" ? 0 : 1;
      var parts = pl.participants || [], pid = parts[0] && parts[0].athlete ? String(parts[0].athlete.id) : null;
      var pid2 = parts[1] && parts[1].athlete ? String(parts[1].athlete.id) : null;
      var c = pl.coordinate || {}, type = String((pl.type && pl.type.text) || "");
      var txt = String(pl.text || ""), isFT = /free throw/i.test(type);
      if (pid) {
        if (/rebound/i.test(type) && !/team/i.test(type)) { ev.reb.push([t, pid, 1]); ev[/offensive/i.test(type) ? "oreb" : "dreb"].push([t, pid, 1]); }
        if (isFT) { ev.fta.push([t, pid, 1]); if (pl.scoringPlay) ev.ftm.push([t, pid, 1]); }
        else if (pl.shootingPlay && pl.pointsAttempted !== 1) {
          var three = pl.pointsAttempted === 3 || (pl.scoringPlay && pl.scoreValue === 3);
          ev.fga.push([t, pid, 1]); if (three) ev.tpa.push([t, pid, 1]);
          if (pl.scoringPlay) { ev.fgm.push([t, pid, 1]); if (three) ev.tpm.push([t, pid, 1]); }
          if (pl.scoringPlay && pid2 && /assist/i.test(txt)) ev.ast.push([t, pid2, 1]);
          if (pid2 && /\bblocks\b/i.test(txt)) ev.blk.push([t, pid2, 1]);
        }
        if (/turnover|traveling|double dribble|palming|backcourt|offensive goaltending|3-second|kicked ball|discontinue/i.test(type) ||
            (/turnover/i.test(txt) && !/foul$/i.test(type))) {
          ev.tov.push([t, pid, 1]);
          if (pid2 && /steal/i.test(txt)) ev.stl.push([t, pid2, 1]);
        } else if (/foul/i.test(type) && !/technical|turnover/i.test(type)) ev.pf.push([t, pid, 1]);
      }
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
          flow.push([Math.max(t, flow[flow.length - 1][0]), h, a]);     // (a play logged out of clock order never steps back)
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
    // both teams' injury reports, as ESPN has them now (ESPN keeps only the current report, also on an old game)
    var injuries = null;
    if (s.injuries) {
      injuries = { home: [], away: [] };
      s.injuries.forEach(function (ti) {
        var side = sides[String(ti.team && ti.team.id)];
        if (!side) return;
        (ti.injuries || []).forEach(function (it) {
          var a = it.athlete || {}, d = it.details || {}, ty = it.type || {};
          if (!a.displayName) return;
          injuries[side].push({ id: String(a.id || ""), name: a.displayName, short: a.shortName || a.displayName,
            img: (a.headshot || {}).href || "", pos: (a.position || {}).abbreviation || "", status: String(it.status || ty.description || ""),
            code: String(ty.abbreviation || ""), fantasy: String((d.fantasyStatus || {}).abbreviation || ""), date: it.date || "",
            kind: d.type || "", detail: d.detail || "", side: d.side || "", back: d.returnDate || "" });
        });
      });
    }
    var sit = live ? gameSituation(s, comp, players, sides, home, away) : null;
    // ESPN's own win probability after every play (its model: score, time, possession and the two teams' strength)
    var wp = [];
    (s.winprobability || []).forEach(function (w) {
      var t = playT[String(w.playId)];
      if (t == null || w.homeWinPercentage == null) return;
      if (wp.length && wp[wp.length - 1][0] === t) wp[wp.length - 1][1] = num(w.homeWinPercentage);
      else wp.push([t, num(w.homeWinPercentage)]);
    });
    var cst = comp.status || {};
    var g = { id: String(id), label: brief0.label || "", series: brief0.series || "", date: niceDay(comp.date), when: comp.date,
      status: status.shortDetail || status.detail || "", tick: clockText(comp.status), live: live, final: status.state === "post",
      pre: status.state === "pre", period: parseInt(cst.period, 10) || 0, displayClock: cst.displayClock || "",
      statusName: String(status.name || ""), espnHome: brief0.espnHome != null ? brief0.espnHome : null,
      clock: live ? (status.shortDetail || "") : "", home: home, away: away, players: players, shots: shots, flow: flow,
      assists: assists, scoring: scoring, events: ev, wp: wp, leadChanges: leadChanges, timesTied: timesTied,
      stints: lu.stints, onNow: lu.onNow, starters: lu.starters, now: lu.now, situation: sit, injuries: injuries };
    g.events.pm = lu.pm || [];
    setNow(g);
    return g;
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
    var stints = [], on = { home: starters.home.slice(), away: starters.away.slice() }, pmEv = [];
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
        if (e.dh || e.da) {                                       // every player on the floor: his +/- moves
          cur.home.forEach(function (id) { pmEv.push([e.t, id, e.dh - e.da]); });
          cur.away.forEach(function (id) { pmEv.push([e.t, id, e.da - e.dh]); });
        }
        var st = e.side === "home" ? cur.h : e.side === "away" ? cur.a : null;
        if (st) { if (e.fga) st.fga++; if (e.fta) st.fta++; if (e.oreb) st.oreb++; if (e.tov) st.tov++; }
      });
      close(live && per === maxPer ? now : periodEnd(per));
    }
    return { stints: stints, onNow: { home: on.home.slice(), away: on.away.slice() }, starters: starters, now: now, pm: pmEv };
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
  function lastName(p) {                             // "J. Smith Jr." -> "Smith Jr." (never just the suffix)
    var parts = String((p && (p.short || p.name)) || "").split(" "), k = parts.length - 1;
    if (k >= 1 && /^(jr\.?|sr\.?|ii|iii|iv)$/i.test(parts[k])) k--;
    return parts.slice(Math.max(0, k)).join(" ");
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
  // the period and clock at t seconds from the tip. A moment right on a period's end belongs to that period, not the
  // next one: a shot at the halftime buzzer is "Q2 0:00" (not "Q3 12:00"), a game-winner at the end of the first
  // overtime "OT 0:00" (not "OT2 5:00")
  function clockAt(t) {
    var u = Math.max(0, t - 0.001), q;
    if (u < 2880) { q = Math.min(4, Math.floor(u / 720) + 1); return "Q" + q + " " + mmss(Math.max(0, q * 720 - t)); }
    q = Math.floor((u - 2880) / 300) + 1;
    return "OT" + (q > 1 ? q : "") + " " + mmss(Math.max(0, 2880 + q * 300 - t));
  }
  function mmss(s) { s = Math.max(0, Math.round(s)); return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2); }
  // where a live game is right now, in seconds from the tip (g.tNow), from its period and game clock
  function setNow(g) {
    g.tNow = g.live && g.period ? elapsed(g.period, g.displayClock) : null;
    return g;
  }
  // "Q2 5:31", "Half", "End Q3", "OT 3:12"
  function liveClock(g) {
    return qTick(clockText({ type: { state: g.live ? "in" : g.final ? "post" : "pre", name: g.statusName, shortDetail: g.status },
                             period: g.period, displayClock: g.displayClock })) || qTick(g.tick || "");
  }
  // the right end of a game's time axis: the whole of regulation (and every overtime played so far)
  function axisEnd(g) {
    var end = gameEnd(g);
    if (g.live && g.period > 4) end = Math.max(end, periodEnd(g.period));
    return end;
  }
  // a breathing dot at a point of a chart, in the chart's own colour: where a live game is right now
  function nowDot(x, y, color) {
    var c = esc(color || "#F5D370");
    return '<g class="ls-now" transform="translate(' + x.toFixed(1) + " " + y.toFixed(1) + ')"><circle class="h" r="6" fill="' + c + '"/>' +
      '<circle class="c" r="3.1" fill="' + c + '"/></g>';
  }
  function playerById(g) {
    var m = {};
    (g.players || []).forEach(function (p) { m[p.id] = p; });
    return m;
  }
  function countUp(node, to, ms, fmt) {
    fmt = fmt || function (v) { return String(Math.round(v)); };
    if (REDUCE || QUIET) { node.textContent = fmt(to); return; }
    var t0 = performance.now();
    (function step(now) {
      if (node._liveSet) return;                    // a live update has already put the newest number there
      var p = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - p, 3);
      node.textContent = fmt(to * e);
      if (p < 1) requestAnimationFrame(step);
    })(t0);
  }
  function drawIn(path) {
    if (REDUCE || QUIET || !path || !path.getTotalLength) return;
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

  // ------------------------------------------------------------ updating a window in place
  // A live update draws the window again, quietly (QUIET: no count-ups, no lines drawing in, nothing fading in), off to
  // the side, and morph() then changes the window to match it: only what differs is touched -- a score's digits, a
  // line's points, a dot's place -- so nothing flickers, pictures never reload and running animations carry on.
  var QUIET = false;
  function morph(from, to, root) {                  // root: keep `from`'s own attributes, only its contents change
    if (from.nodeType === 1 && !root) {
      var fa = from.attributes, ta = to.attributes, i;
      for (i = fa.length - 1; i >= 0; i--) if (!to.hasAttribute(fa[i].name)) from.removeAttribute(fa[i].name);
      for (i = 0; i < ta.length; i++) if (from.getAttribute(ta[i].name) !== ta[i].value) from.setAttribute(ta[i].name, ta[i].value);
    }
    var want = Array.prototype.slice.call(to.childNodes);
    for (var k = 0; k < want.length; k++) {
      var f = from.childNodes[k], t = want[k];
      if (!f) { from.appendChild(t); continue; }
      if (f.nodeType !== t.nodeType || f.nodeName !== t.nodeName ||
          (f.nodeName === "IMG" && f.getAttribute("src") !== t.getAttribute("src"))) { from.replaceChild(t, f); continue; }
      if (f.nodeType === 3) {
        if (f.nodeValue !== t.nodeValue) { f.nodeValue = t.nodeValue; from._liveSet = true; bump(from); }
        continue;
      }
      if (f.nodeType === 1) morph(f, t);
      else if (f.nodeValue !== t.nodeValue) f.nodeValue = t.nodeValue;
    }
    while (from.childNodes.length > want.length) from.removeChild(from.lastChild);
  }
  // a score that just changed pulses once
  function bump(node) {
    if (REDUCE || !node.classList || !node.classList.contains("sc")) return;
    node.classList.remove("ls-bump"); void node.offsetWidth; node.classList.add("ls-bump");
  }

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
      morph(btn, el("button", null, '<span class="v">' + (cur ? cur[1] : "") + "</span>"), true);   // (in place: no flicker)
      if (box.classList.contains("open") && list.childNodes.length === items.length) return;   // an open list is left as it is
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

  // ------------------------------------------------------------ pop-ups on the windows' graphs
  // Every graph in the windows answers the pointer: with a mouse, hover over it; on a phone or tablet, hold a finger on
  // it (about a third of a second), then run the finger over it -- the page stays still meanwhile, and the pop-up sits
  // just above the finger. When the finger lifts the pop-up stays, with an x to close it. A window's render registers
  // what each of its graphs shows: card._tips[name] = function (x, y, svg, pt, target) -> { html, gx, gy } or null,
  // where the graph's wrapper carries data-tip="name"; x/y are in the graph's own (SVG) units, and gx/gy, when given,
  // put a guide line and a marker on the graph there.
  function installTips(card) {
    var tipEl = null, guide = null, mark = null, holdTimer = null, inspecting = false, start = null, last = null;
    function hostOf(t) { var h = t && t.closest ? t.closest("[data-tip]") : null; return h && card.contains(h) ? h : null; }
    function hostAt(pt) { return hostOf(document.elementFromPoint(pt.clientX, pt.clientY)); }
    function resolve(pt, host) {
      if (!host || !card._tips) return null;
      var fn = card._tips[host.getAttribute("data-tip")], svg = host.querySelector("svg");
      if (!fn) return null;
      var x = null, y = null;
      if (svg && svg.getScreenCTM) {
        var m = svg.getScreenCTM();
        if (m) { var q = svg.createSVGPoint(); q.x = pt.clientX; q.y = pt.clientY; q = q.matrixTransform(m.inverse()); x = q.x; y = q.y; }
      }
      var r = null;
      try { r = fn(x, y, svg, pt, document.elementFromPoint(pt.clientX, pt.clientY)); } catch (e) { r = null; }
      if (r) r.svg = svg;
      return r;
    }
    function clearGuide() { if (guide) { guide.remove(); guide = null; } if (mark) { mark.remove(); mark = null; } }
    function hide() {
      if (tipEl) { tipEl.classList.remove("show", "pinned"); }
      clearGuide();
    }
    function place(pt, touch) {
      var cb = card.getBoundingClientRect(), x = pt.clientX - cb.left, y = pt.clientY - cb.top;
      tipEl.style.left = "0px"; tipEl.style.top = "0px";
      var w = tipEl.offsetWidth, h = tipEl.offsetHeight, X, Y;
      if (touch) {
        X = x - w / 2; Y = y - h - 26;
        if (Y < 4) Y = y + 26;
      } else {
        X = x + 14; if (X + w > cb.width - 4) X = x - 14 - w;
        Y = y - h / 2;
      }
      tipEl.style.left = Math.max(4, Math.min(X, cb.width - w - 4)) + "px";
      tipEl.style.top = Math.max(4, Math.min(Y, cb.height - h - 4)) + "px";
    }
    function show(r, pt, touch) {
      if (!tipEl) { tipEl = el("div", "ls-tip"); tipEl.setAttribute("role", "tooltip"); card.appendChild(tipEl); }
      if (tipEl._html !== r.html) { tipEl.innerHTML = r.html; tipEl._html = r.html; }
      tipEl.classList.remove("pinned");
      tipEl.classList.add("show");
      clearGuide();
      if (r.svg && r.gx != null) {
        var vb = r.svg.viewBox && r.svg.viewBox.baseVal, top = vb ? vb.y : 0, bot = vb ? vb.y + vb.height : 100;
        guide = document.createElementNS(SVGNS, "line");
        guide.setAttribute("class", "ls-guide");
        guide.setAttribute("x1", r.gx); guide.setAttribute("x2", r.gx); guide.setAttribute("y1", top); guide.setAttribute("y2", bot);
        r.svg.appendChild(guide);
        if (r.gy != null) {
          mark = document.createElementNS(SVGNS, "circle");
          mark.setAttribute("class", "ls-guide-dot"); mark.setAttribute("cx", r.gx); mark.setAttribute("cy", r.gy); mark.setAttribute("r", r.gr || 3.6);
          r.svg.appendChild(mark);
        }
      } else if (r.svg && r.mx != null) {                    // a ring around the hovered point
        mark = document.createElementNS(SVGNS, "circle");
        mark.setAttribute("class", "ls-guide-ring"); mark.setAttribute("cx", r.mx); mark.setAttribute("cy", r.my); mark.setAttribute("r", r.mr || 9);
        r.svg.appendChild(mark);
      }
      place(pt, touch);
    }
    function at(pt, touch) {
      var r = resolve(pt, hostAt(pt));
      if (r) show(r, pt, touch); else hide();
      return r;
    }
    // a mouse
    card.addEventListener("pointermove", function (e) {
      if (e.pointerType !== "mouse") return;
      if (tipEl && tipEl.classList.contains("pinned")) return;
      var host = hostOf(e.target);
      if (!host) { if (tipEl && tipEl.classList.contains("show")) hide(); return; }
      at({ clientX: e.clientX, clientY: e.clientY }, false);
    });
    card.addEventListener("pointerleave", function (e) {
      if (e.pointerType === "mouse" && tipEl && !tipEl.classList.contains("pinned")) hide();
    });
    // a finger: hold, then run it over the graph; lift to keep the pop-up
    card.addEventListener("touchstart", function (e) {
      if (e.target.closest && e.target.closest(".ls-tip-x")) return;
      if (e.touches.length !== 1 || !hostOf(e.target)) { clearTimeout(holdTimer); return; }
      start = { clientX: e.touches[0].clientX, clientY: e.touches[0].clientY }; last = start;
      clearTimeout(holdTimer);
      holdTimer = setTimeout(function () {
        inspecting = true; card.classList.add("ls-inspecting");
        try { if (navigator.vibrate) navigator.vibrate(8); } catch (er) {}
        at(last, true);
      }, 320);
    }, { passive: true });
    card.addEventListener("touchmove", function (e) {
      if (!e.touches.length) return;
      last = { clientX: e.touches[0].clientX, clientY: e.touches[0].clientY };
      if (inspecting) { if (e.cancelable) e.preventDefault(); at(last, true); return; }
      if (start && Math.hypot(last.clientX - start.clientX, last.clientY - start.clientY) > 10) { clearTimeout(holdTimer); start = null; }
    }, { passive: false });
    function lift() {
      clearTimeout(holdTimer); start = null;
      if (!inspecting) return;
      inspecting = false; card.classList.remove("ls-inspecting");
      if (tipEl && tipEl.classList.contains("show")) {
        tipEl.classList.add("pinned");
        var x = el("button", "ls-tip-x", "&times;");
        x.type = "button"; x.setAttribute("aria-label", "Close");
        x.addEventListener("click", function (ev) { ev.stopPropagation(); hide(); });
        tipEl.appendChild(x); tipEl._html = null;
      }
    }
    card.addEventListener("touchend", lift);
    card.addEventListener("touchcancel", lift);
    card.addEventListener("contextmenu", function (e) { if (inspecting || hostOf(e.target) && e.pointerType !== "mouse" && start) e.preventDefault(); });
    card._hideTip = hide;
    card._tips = { text: function (x, y, svg, pt, target) {        // any item that carries its own words (data-t)
      var t = target && target.closest ? target.closest("[data-t]") : null;
      return t && card.contains(t) ? { html: '<div class="r">' + t.getAttribute("data-t") + "</div>" } : null;
    } };
  }
  // helpers for the pop-ups
  function tipTeamLine(team, color, text) { return '<div class="r">' + logoImg(team, 13) + '<span style="color:' + color + '">' + esc(team.tri) + "</span> " + text + "</div>"; }
  function distSeg(px, py, x1, y1, x2, y2) {
    var dx = x2 - x1, dy = y2 - y1, l2 = dx * dx + dy * dy, t = l2 ? Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / l2)) : 0;
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
  }
  function scoreAt(g, t) {                        // [home, away] after everything up to t
    var h = 0, a = 0;
    for (var i = 0; i < (g.flow || []).length && g.flow[i][0] <= t; i++) { h = g.flow[i][1]; a = g.flow[i][2]; }
    return [h, a];
  }
  function leadLine(g, h, a) {
    var c = colors(g);
    if (h === a) return '<div class="r">Tied at ' + h + "</div>";
    var home = h > a, team = home ? g.home : g.away;
    return tipTeamLine(team, home ? c.home : c.away, "by <b>" + Math.abs(h - a) + "</b>");
  }
  function scoreLine(g, h, a) {
    var c = colors(g);
    return '<div class="r sc">' + logoImg(g.away, 13) + '<b style="color:' + c.away + '">' + a + '</b><span class="d">–</span><b style="color:' + c.home + '">' + h + "</b>" + logoImg(g.home, 13) + "</div>";
  }

  // ------------------------------------------------------------ a card with its own dropdowns
  function makeCard(opts) {
    var card = el("div", "ls-card" + (opts.wide ? " wide" : "") + (opts.cls ? " " + opts.cls : ""));
    installTips(card);
    var top = el("div", "ls-card-top");
    var name = typeof opts.title === "function" ? (opts.name || "") : opts.title;
    var titleEl = el("div", "ls-title", esc(name));
    top.appendChild(titleEl);
    var pickers = el("div", "ls-pickers");
    top.appendChild(pickers);
    card.appendChild(top);
    var body = el("div", "ls-body");
    card.appendChild(body);
    var state = { gameId: index.selected || index["default"], sub: null, stop: null, update: null, key: null, pre: false,
                  mode: opts.mode ? opts.mode.def : null };

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
    function take(r) {                              // a window's render gives back a stop function, or { stop, update }
      state.stop = typeof r === "function" ? r : (r && r.stop) || null;
      state.update = (r && typeof r === "object" && r.update) || null;
    }
    function draw() {
      if (state.stop) { state.stop(); state.stop = null; }
      state.update = null;
      var want = state.gameId;
      loadGame(want).then(function (g) {
        return Promise.resolve(opts.prepare ? opts.prepare(g) : null).then(function () { return g; });
      }).then(function (g) {
        if (want !== state.gameId) return;            // another game was picked while this one loaded
        g = loaded[want] || g;
        if (subPick) fillSub(g);
        if (typeof opts.title === "function") titleEl.innerHTML = opts.title(g, state.sub);
        body.innerHTML = "";
        state.pre = !!(g.pre && !opts.pre);
        state.key = opts.liveKey ? opts.liveKey(g, state.sub, state.mode) : null;
        if (state.pre) renderPregame(body, g);         // not tipped off yet: nothing to draw (unless the window can)
        else take(opts.render(body, g, state.sub, card, state.mode));
        if (opts.onDrawn) opts.onDrawn();
      }).catch(function () {
        body.innerHTML = '<div class="ls-foot">This game couldn\'t be loaded right now.</div>';
      });
    }
    card._draw = draw;
    card._gameId = function () { return state.gameId; };
    // Live updates (see "live updates" at the end): g is the newest read of the game this window shows. clockOnly: only
    // the game clock moved -- just the windows that show where the game is right now follow it.
    card._liveUpdate = function (g, clockOnly) {
      if (!g || g.id !== state.gameId || opts.live === false) return;
      if (clockOnly && !opts.clock) return;
      if (state.pre) { if (!g.pre) draw(); return; }  // it just tipped off: the whole window
      Promise.resolve(opts.prepare && !clockOnly ? opts.prepare(g) : null).then(function () {
        if (g.id !== state.gameId || loaded[g.id] !== g) return;
        if (subPick && !clockOnly) fillSub(g);
        if (typeof opts.title === "function") { var t = opts.title(g, state.sub); if (titleEl.innerHTML !== t) titleEl.innerHTML = t; }
        if (state.update) { state.update(g, clockOnly); return; }
        if (opts.liveKey) {                           // windows that change only when something in particular does
          var k = opts.liveKey(g, state.sub, state.mode);
          if (k === state.key) return;
          state.key = k;
          if (opts.redraw) { draw(); return; }
        }
        quietRedraw(g);
      });
    };
    function quietRedraw(g) {
      var tmp = el("div", "ls-body");
      tmp.style.cssText = "position:absolute;left:0;top:0;width:" + body.clientWidth + "px;height:" + body.clientHeight + "px;visibility:hidden;pointer-events:none";
      card.appendChild(tmp);
      QUIET = true;
      var r = null;
      try { r = opts.render(tmp, g, state.sub, card, state.mode); } catch (e) { r = null; } finally { QUIET = false; }
      var stopIt = typeof r === "function" ? r : (r && r.stop);
      if (stopIt) stopIt();                           // (anything the quiet copy started)
      morph(body, tmp, true);
      if (tmp.parentNode) tmp.parentNode.removeChild(tmp);
      if (opts.onDrawn) opts.onDrawn();
    }
    // the ticker picked a game: this card shows it too
    card._showGame = function (id) {
      if (id === state.gameId) return;
      state.gameId = id;
      gamePick._set(gameItems(), id);
      draw();
    };
    // live updates: the scores in the game menu follow the scoreboard
    card._boardRefresh = function () { gamePick._set(gameItems(), state.gameId); };
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
  function renderScore(body, g, sub, card) {
    var c = colors(g);
    var homeWin = g.home.score >= g.away.score;
    // a live game: where it is, right above the away team -- a breathing red dot, then "Q2 5:31"
    if (g.live) body.appendChild(el("div", "ls-live-clock", '<i class="ls-dot" aria-hidden="true"></i><b>' + esc(liveClock(g)) + "</b>"));
    [["away", g.away, c.away, !homeWin], ["home", g.home, c.home, homeWin]].forEach(function (row) {
      // the team's logo first, its name and abbreviation, and its score in its own colour
      var extra = "";
      var sit = g.live && g.situation ? g.situation[row[0]] : null;
      if (sit) {
        if (sit.timeouts != null) extra += '<span class="ls-to">' + sit.timeouts + " TO</span>";
        if (sit.bonus) extra += '<span class="ls-bonus">BONUS</span>';
      }
      var r = el("div", "ls-team" + (row[3] && g.final ? " win" : ""),
        '<span class="tri">' + logoImg(row[1], 24) + '<span class="nm" style="color:' + row[2] + '">' + esc(row[1].city ? row[1].name : row[1].tri) +
        '</span> <span style="color:#8c867b;font-weight:400;font-size:12px">' + esc(row[1].tri) + "</span>" +
        (row[1].record ? '<span class="ls-rec">' + esc(row[1].record) + "</span>" : "") + extra + '</span><span class="sc" style="color:' +
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
    // A live game's line stops where the game is right now (a breathing dot there), not flat to the end of the game.
    var W = 330, H = 86, PAD = 20, end = axisEnd(g), maxAbs = 5;
    var lastT = g.flow.length ? g.flow[g.flow.length - 1][0] : 0, tNow = g.live ? Math.min(end, Math.max(lastT, g.tNow || 0)) : null;
    g.flow.forEach(function (f) { maxAbs = Math.max(maxAbs, Math.abs(f[1] - f[2])); });
    var X = function (t) { return 4 + (W - 8) * t / end; }, Y = function (m) { return H / 2 - (H / 2 - PAD) * m / maxAbs; };
    var d = "M " + X(0).toFixed(1) + " " + Y(0).toFixed(1), prevY = Y(0);
    g.flow.forEach(function (f) {
      var y = Y(f[1] - f[2]);
      d += " L " + X(f[0]).toFixed(1) + " " + prevY.toFixed(1) + " L " + X(f[0]).toFixed(1) + " " + y.toFixed(1);
      prevY = y;
    });
    d += " L " + X(tNow != null ? tNow : end).toFixed(1) + " " + prevY.toFixed(1);
    var qlines = "";
    for (var q = 1; q * 720 < Math.min(end, 2880) || 2880 + (q - 4) * 300 < end; q++) {
      var qx = X(q <= 4 ? q * 720 : 2880 + (q - 4) * 300);
      qlines += '<line x1="' + qx.toFixed(1) + '" x2="' + qx.toFixed(1) + '" y1="1" y2="' + (H - 1) + '" stroke="#2a2721"/>';
    }
    if (card) {
      card._tips = card._tips || {};
      card._tips.flow = function (x) {                 // the score and the lead at that moment of the game
        if (x == null) return null;
        var t = Math.max(0, Math.min(tNow != null ? tNow : end, (x - 4) / (W - 8) * end)), sa = scoreAt(g, t);
        return { html: '<div class="h">' + esc(t <= 0 ? "Tip-off" : clockAt(t)) + "</div>" + scoreLine(g, sa[0], sa[1]) + leadLine(g, sa[0], sa[1]),
                 gx: X(t), gy: Y(sa[0] - sa[1]) };
      };
    }
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
      '<path d="' + d + '" fill="none" stroke="url(#lsGold' + g.id + ')" stroke-width="1.8" stroke-linejoin="round"/>' +
      (tNow != null ? nowDot(X(tNow), prevY, "#F5D370") : "") + "</svg>");
    svg.setAttribute("data-tip", "flow");
    body.appendChild(svg);
    drawIn(svg.querySelector("path"));
    renderTiles(body, g);
  }

  // ------------------------------------------------------------ 2. shot chart replay
  function renderShots(body, g, sub, card) {
    var c = colors(g), byId = playerById(g);
    function pick(gg) {
      return (gg.shots || []).filter(function (s) {
        if (!sub || sub === "all") return true;
        if (sub === "team:home") return s[2] === 0;
        if (sub === "team:away") return s[2] === 1;
        return String(s[1]) === sub;
      });
    }
    var shots = pick(g);
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
    var i = 0, made = 0, tpm = 0, tpa = 0, pm = 0, pa = 0, pts = 0, mm = 0, ma = 0, dist = 0, longest = 0, timer = null, alive = true, holding = false;
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
      node._shot = s;
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
    function tally() {
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
      holding = false;
      layer.innerHTML = ""; i = made = tpm = tpa = pm = pa = pts = mm = ma = dist = longest = 0; tally();
      if (REDUCE || QUIET) { shots.forEach(add); i = shots.length; tally(); holding = true; return; }
      var gap = Math.max(35, Math.min(160, 9000 / Math.max(1, shots.length)));
      timer = setInterval(function () {
        if (!alive) return;
        if (card && card._hidden) return;
        if (i >= shots.length) { clearInterval(timer); holding = true; timer = setTimeout(restart, 3500); return; }
        add(shots[i]); i++; tally();
      }, gap);
    }
    wrap.setAttribute("data-tip", "shots");
    if (card) {
      card._tips = card._tips || {};
      card._tips.shots = function (x, y) {             // the shot nearest the pointer: who, made or missed, how far, when
        if (x == null) return null;
        var bestN = null, bd = 16;
        Array.prototype.forEach.call(layer.childNodes, function (n) {
          var sh = n._shot; if (!sh) return;
          var d = Math.hypot(x - sh[3], y - (TOP - sh[4]));
          if (d < bd) { bd = d; bestN = sh; }
        });
        if (!bestN) return null;
        var pl = byId[bestN[1]] || {}, ft = Math.round(Math.sqrt(bestN[3] * bestN[3] + bestN[4] * bestN[4]) / 10);
        var tm = teamOf(g, bestN[2] === 0 ? "home" : "away"), col2 = bestN[2] === 0 ? c.home : c.away;
        return { html: '<div class="h">' + logoImg(tm, 13) + '<span style="color:' + col2 + '">' + esc(pl.short || pl.name || tm.tri) + "</span></div>" +
                   '<div class="r"><b class="' + (bestN[5] ? "mk" : "ms") + '">' + (bestN[5] ? "Made" : "Missed") + "</b> " + bestN[6] + "PT · " + ft + " ft</div>" +
                   '<div class="r m">' + esc(clockAt(bestN[0])) + "</div>",
                 mx: bestN[3], my: TOP - bestN[4], mr: 11 };
      };
    }
    restart();
    // live: new shots join the replay; once it has played through they land on the court as they happen
    return { stop: function () { alive = false; clearInterval(timer); clearTimeout(timer); },
             update: function (g2, clockOnly) {
               if (clockOnly) return;
               byId = playerById(g2);
               shots = pick(g2);
               if (i > shots.length) { restart(); return; }
               if (holding) { while (i < shots.length) { add(shots[i]); i++; } }
               tally();
             } };
  }

  // ------------------------------------------------------------ 3. player card
  function renderPlayer(body, g, sub, card) {
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
    // points through the game (a live game: up to where it is now, with a breathing dot there)
    var W = 270, H = 56, end = axisEnd(g), pts = [[0, 0]], tot = 0;
    (g.scoring || []).forEach(function (s) { if (s[1] === p.id) { tot += s[2]; pts.push([s[0], tot]); } });
    var lastT = pts[pts.length - 1][0], stop = g.live ? Math.min(end, Math.max(lastT, g.tNow || 0)) : end;
    pts.push([stop, tot]);
    var X = function (t) { return 3 + (W - 6) * t / end; }, Y = function (v) { return H - 4 - (H - 10) * v / Math.max(10, tot); };
    var d = "M " + pts.map(function (q, k) {
      return X(q[0]).toFixed(1) + " " + Y(k ? pts[k - 1][1] : 0).toFixed(1) + " L " + X(q[0]).toFixed(1) + " " + Y(q[1]).toFixed(1);
    }).join(" L ");
    var svg = el("div", "ls-ptg", '<div class="ls-title" style="margin-bottom:6px">Points through the game</div>' +
      '<svg class="ls-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Points through the game">' +
      '<path d="' + d + ' L ' + X(stop).toFixed(1) + ' ' + (H - 4) + ' L ' + X(0) + ' ' + (H - 4) + ' Z" fill="' + col + '" fill-opacity=".12"/>' +
      '<path class="ln" d="' + d + '" fill="none" stroke="' + col + '" stroke-width="2"/>' + (g.live ? nowDot(X(stop), Y(tot), col) : "") + "</svg>");
    svg.setAttribute("data-tip", "ptg");
    body.appendChild(svg);
    drawIn(svg.querySelector("path.ln"));
    if (card) {
      card._tips = card._tips || {};
      card._tips.ptg = function (x) {                  // his points so far at that moment, and how the last basket came
        if (x == null) return null;
        var t = Math.max(0, Math.min(stop, (x - 3) / (W - 6) * end)), v = 0, lastS = null;
        (g.scoring || []).forEach(function (s) { if (s[1] === p.id && s[0] <= t) { v += s[2]; lastS = s; } });
        return { html: '<div class="h">' + esc(t <= 0 ? "Tip-off" : clockAt(t)) + '</div><div class="r"><b style="color:' + col + '">' + v + "</b> pts</div>" +
                   (lastS ? '<div class="r m">Last basket: ' + (lastS[2] === 1 ? "free throw" : lastS[2] + "-pointer") + " at " + esc(clockAt(lastS[0])) + "</div>" : ""),
                 gx: X(t), gy: Y(v) };
      };
    }
  }

  // ------------------------------------------------------------ 4. LEADERBOARD
  // The game's top 8 in one stat (Points by default; its menu has every stat that can be followed live), racing
  // through the game: the clock runs from the tip to the end -- of a live game, to where it is right now, never past
  // it -- holds there, and starts over. Each play-by-play count lands at its moment; at the end every number is the box
  // score's (minutes come from who was on the floor when).
  var LB_STATS = [["pts", "Points"], ["reb", "Rebounds"], ["ast", "Assists"], ["stl", "Steals"], ["blk", "Blocks"],
    ["tpm", "3-pointers made"], ["fgm", "Field goals made"], ["ftm", "Free throws made"], ["stocks", "Steals + blocks"],
    ["pra", "Points + rebounds + assists"], ["pm", "Plus/minus"], ["min", "Minutes"], ["oreb", "Offensive rebounds"],
    ["dreb", "Defensive rebounds"], ["fga", "Field goal attempts"], ["tpa", "3-point attempts"], ["fta", "Free throw attempts"],
    ["tov", "Turnovers"], ["pf", "Personal fouls"]];
  function lbItems() { return LB_STATS.map(function (x) { return [x[0], esc(x[1])]; }); }
  function minutesOf(m) {
    var s = String(m == null ? "0" : m);
    if (s.indexOf(":") >= 0) { var q = s.split(":"); return num(q[0]) + num(q[1]) / 60; }
    return num(s);
  }
  function boxValue(p, k) {
    if (k === "stocks") return num(p.stl) + num(p.blk);
    if (k === "pra") return num(p.pts) + num(p.reb) + num(p.ast);
    if (k === "min") return minutesOf(p.min);
    return num(p[k]);
  }
  function lbEvents(g, k) {
    var ev = g.events || {}, out = [];
    var lists = k === "pts" ? [g.scoring] : k === "stocks" ? [ev.stl, ev.blk] : k === "pra" ? [g.scoring, ev.reb, ev.ast] : [ev[k]];
    lists.forEach(function (l) { (l || []).forEach(function (e) { out.push(e); }); });
    return out.sort(function (a, b) { return a[0] - b[0]; });
  }
  function secondsOn(g, id, t) {                     // a player's seconds on the floor from the tip to t
    var sec = 0;
    (g.stints || []).forEach(function (st) {
      if (st.t0 >= t || (st.home.indexOf(id) < 0 && st.away.indexOf(id) < 0)) return;
      sec += Math.max(0, Math.min(t, st.t1) - st.t0);
    });
    return sec;
  }
  function renderLeaderboard(body, g, sub, card) {
    var key = sub || "pts", c, byId, ids = null, rows = [], events = [], end = 1, maxV = 1, finalV = {};
    var box = el("div", "ls-race");                   // fills the window; each row is 1/8 of it (see CSS)
    body.appendChild(box);
    var clock = el("div", "ls-foot ls-lb-clock", "");
    body.appendChild(clock);
    var t = 0, k = 0, vals = {}, timer = null, alive = true, holding = false;
    function setup(gg) {
      g = gg; c = colors(gg); byId = playerById(gg);
      var top = (gg.players || []).slice().sort(function (a, b) {
        return boxValue(b, key) - boxValue(a, key) || b.pts - a.pts;
      }).slice(0, 8);
      var newIds = top.map(function (p) { return p.id; });
      end = gg.live ? Math.max(1, Math.min(axisEnd(gg), gg.tNow != null ? gg.tNow : gameEnd(gg))) : gameEnd(gg);
      events = key === "min" ? [] : lbEvents(gg, key).filter(function (e) { return newIds.indexOf(e[1]) >= 0 && e[0] <= end + 0.01; });
      finalV = {};
      newIds.forEach(function (id) { finalV[id] = key === "min" ? secondsOn(gg, id, end) / 60 : boxValue(byId[id], key); });
      maxV = Math.max.apply(null, newIds.map(function (id) { return Math.abs(finalV[id]); }).concat([1]));
      if (!ids || newIds.join() !== ids.join()) { ids = newIds; build(top); }
    }
    function build(top) {
      box.innerHTML = "";
      rows = top.map(function (p) {
        // the team's logo and the player's picture, no name (the picture's hover text names him)
        var col = p.team === "home" ? c.home : c.away;
        var r = el("div", "ls-rrow", '<span class="n" title="' + esc(p.name || lastName(p)) + '">' + logoImg(teamOf(g, p.team), 22) +
          '<img class="hs" alt="' + esc(p.name || lastName(p)) + '" loading="lazy" src="' +
          esc(headshotOf(p)) + '" onerror="this.style.visibility=\'hidden\'"></span><span class="b"><i style="background:' +
          col + '"></i></span><span class="v" style="color:' + col + '">0</span>');
        r.style.height = (100 / Math.max(1, top.length)) + "%";
        r._col = col;
        box.appendChild(r);
        return r;
      });
    }
    function shown(id) {
      if (key === "min") return secondsOn(g, id, t) / 60;
      return t >= end ? finalV[id] : (vals[id] || 0);  // at the end: the box score exactly
    }
    function fmt(v) {
      if (key === "min") return mmss(v * 60);
      if (key === "pm") return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(Math.round(v));
      return String(Math.round(v));
    }
    function count() {
      while (k < events.length && events[k][0] <= t) { vals[events[k][1]] = (vals[events[k][1]] || 0) + events[k][2]; k++; }
    }
    function render() {
      var order = ids.slice().sort(function (a, b) { return shown(b) - shown(a) || ids.indexOf(a) - ids.indexOf(b); });
      ids.forEach(function (id, j) {
        var r = rows[j], v = shown(id), rank = order.indexOf(id), bar = r.querySelector("i");
        r.style.transform = "translateY(" + (rank * 100) + "%)";
        bar.style.width = (100 * Math.abs(v) / maxV) + "%";
        bar.style.background = v < 0 ? "#6f6a62" : r._col;
        r.querySelector(".v").textContent = fmt(v);
      });
      var lead = byId[order[0]];
      if (t >= end) clock.textContent = g.live ? liveClock(g) + (lead ? " · " + lead.name + " leads" : "")
                                               : "Final · " + (lead ? lead.name + " led the way" : "");
      else clock.textContent = clockAt(t);
    }
    function restart() {
      clearInterval(timer); clearTimeout(timer);
      t = 0; k = 0; vals = {}; holding = false; render();
      if (REDUCE || QUIET) { t = end; count(); holding = true; render(); return; }
      timer = setInterval(function () {
        if (!alive || (card && card._hidden)) return;
        t = Math.min(end, t + end / 90);
        count();
        render();
        if (t >= end) { clearInterval(timer); holding = true; timer = setTimeout(restart, 4000); }
      }, 110);
    }
    setup(g);
    restart();
    return { stop: function () { alive = false; clearInterval(timer); clearTimeout(timer); },
             update: function (g2) {                 // live: the newest numbers, and the clock's new "now"
               setup(g2);
               if (holding) t = end;
               else t = Math.min(t, end);
               k = 0; vals = {}; count();
               render();
             } };
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
    var dots = [], alive = true, drawnAt = "", measureCtx = null, posNow = {}, arcPts = [];
    wrap.setAttribute("data-tip", "assists");
    if (card) {
      card._tips = card._tips || {};
      card._tips.assists = function (x, y) {           // a player: assists given and received; a line: that pair, both ways
        if (x == null) return null;
        var hit = null, bd = 15;
        nodes.forEach(function (id) { var q = posNow[id]; if (!q) return; var d = Math.hypot(x - q[0], y - q[1]); if (d < bd) { bd = d; hit = id; } });
        if (hit) {
          var gave = 0, got = 0, top = null;
          Object.keys(pairs).forEach(function (k) {
            var ab = k.split(">");
            if (ab[0] === hit) { gave += pairs[k]; if (!top || pairs[k] > top[1]) top = [ab[1], pairs[k]]; }
            if (ab[1] === hit) got += pairs[k];
          });
          var pl = byId[hit] || {};
          return { html: '<div class="h" style="color:' + col + '">' + esc(pl.name || lastName(pl)) + "</div>" +
                     '<div class="r"><b>' + gave + "</b> assist" + (gave === 1 ? "" : "s") + " · <b>" + got + "</b> assisted basket" + (got === 1 ? "" : "s") + "</div>" +
                     (top ? '<div class="r m">Most to ' + esc(lastName(byId[top[0]])) + " (" + top[1] + ")</div>" : ""),
                   mx: posNow[hit][0], my: posNow[hit][1], mr: 14 };
        }
        var edge = null; bd = 7;
        arcPts.forEach(function (a) {
          for (var i = 1; i < a.pts.length; i++) {
            var d = distSeg(x, y, a.pts[i - 1][0], a.pts[i - 1][1], a.pts[i][0], a.pts[i][1]);
            if (d < bd) { bd = d; edge = a; }
          }
        });
        if (!edge) return null;
        var A = edge.a, B = edge.b, ab = pairs[A + ">" + B] || 0, ba = pairs[B + ">" + A] || 0;
        return { html: '<div class="h" style="color:' + col + '">' + esc(lastName(byId[A]) + " & " + lastName(byId[B])) + "</div>" +
                   (ab ? '<div class="r">' + esc(lastName(byId[A])) + " → " + esc(lastName(byId[B])) + ": <b>" + ab + "</b></div>" : "") +
                   (ba ? '<div class="r">' + esc(lastName(byId[B])) + " → " + esc(lastName(byId[A])) + ": <b>" + ba + "</b></div>" : "") };
      };
    }
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
      posNow = pos; arcPts = [];
      list.forEach(function (e) {                       // each line as points, for the pop-ups
        var p1 = pos[e[0]], p2 = pos[e[1]], mx = (p1[0] + p2[0]) / 2, my = (p1[1] + p2[1]) / 2;
        var qx = mx + (cx - mx) * 0.35, qy = my + (cy - my) * 0.35, ptsA = [];
        for (var k = 0; k <= 16; k++) {
          var u = k / 16, v = 1 - u;
          ptsA.push([v * v * p1[0] + 2 * v * u * qx + u * u * p2[0], v * v * p1[1] + 2 * v * u * qy + u * u * p2[1]]);
        }
        arcPts.push({ a: e[0], b: e[1], pts: ptsA });
      });
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
      var widen = function () { bars[0].style.width = (100 * va / max) + "%"; bars[1].style.width = (100 * vh / max) + "%"; };
      if (QUIET) widen();                             // (a live update: the bars slide from where they are)
      else requestAnimationFrame(function () { requestAnimationFrame(widen); });
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
      edges += '<line class="ls-lu-edge" data-a="' + esc(r.ids[0]) + '" data-b="' + esc(r.ids[1]) + '" data-net="' + (r.net == null ? "" : r.net) + '" data-min="' + (r.min || 0) + '" x1="' + p1[0].toFixed(1) + '" y1="' + p1[1].toFixed(1) +
        '" x2="' + p2[0].toFixed(1) + '" y2="' + p2[1].toFixed(1) + '" stroke="' + (v >= 0 ? col : "#6f6a62") + '" stroke-width="' + w.toFixed(1) +
        '" stroke-opacity="' + (v >= 0 ? 0.85 : 0.7) + '"' + (v < 0 || r.net == null ? ' stroke-dasharray="4 3"' : "") +
        ' stroke-linecap="round"/>';
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
    web.setAttribute("data-tip", "lineup");
    body.appendChild(web);
    if (card) {
      var scope = seasonNumbers ? "this season" : "this game";
      card._tips = card._tips || {};
      card._tips.lineup = function (x, y) {            // a player: his game and his best partner here; a line: that pair
        if (x == null) return null;
        var hit = null, bd = 13;
        five.forEach(function (id) { var d = Math.hypot(x - pos[id][0], y - pos[id][1]); if (d < bd) { bd = d; hit = id; } });
        if (hit) {
          var pl = byId[hit] || {}, mate = null;
          groups[2].forEach(function (r) { if (r.ids.indexOf(hit) >= 0 && r.net != null && (!mate || r.net > mate.net)) mate = r; });
          var other = mate ? mate.ids[0] === hit ? mate.ids[1] : mate.ids[0] : null;
          return { html: '<div class="h" style="color:' + col + '">' + esc(pl.name || nm[hit]) + "</div>" +
                     '<div class="r">' + (pl.pts || 0) + " pts · " + (pl.reb || 0) + " reb · " + (pl.ast || 0) + " ast</div>" +
                     '<div class="r m">' + (pl.min ? esc(pl.min) + " min · " : "") + "+/- " + (pl.pm > 0 ? "+" : "") + (pl.pm || 0) + " this game</div>" +
                     (other ? '<div class="r m">Best with ' + esc(nm[other]) + ": <b>" + fmtNet(mate.net) + "</b> " + scope + "</div>" : ""),
                   mx: pos[hit][0], my: pos[hit][1], mr: 11 };
        }
        var edge = null; bd = 6;
        groups[2].forEach(function (r) {
          var a = pos[r.ids[0]], b = pos[r.ids[1]], d = distSeg(x, y, a[0], a[1], b[0], b[1]);
          if (d < bd) { bd = d; edge = r; }
        });
        if (!edge) return null;
        return { html: '<div class="h" style="color:' + col + '">' + esc(nm[edge.ids[0]] + " + " + nm[edge.ids[1]]) + "</div>" +
                   '<div class="r"><b>' + fmtNet(edge.net) + "</b> net rating " + scope + "</div>" +
                   '<div class="r m">' + (edge.min ? Math.round(edge.min) + " min together" : "Not on the floor together yet") +
                   (edge.net != null ? " · " + (edge.net >= 0 ? "outscoring" : "outscored by") + " opponents" : "") + "</div>" };
      };
    }
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
  // The home team's chance to win after every play is ESPN's own (the summary's "winprobability", and on the scoreboard
  // the latest play's): its model of the score, the time left, who has the ball and the two teams' strength coming in.
  // Only if ESPN has none for a game does the window fall back to the estimate below: the margin, the time left, the
  // game's pace (possessions still to come), home court, and how each team's five on the floor has played together
  // this game (see fiveStrength). Either way the other chances (overtime, a 10-point win) and the projected final come
  // from the spread of outcomes for the time left, centred so they agree with the headline chance.
  // the inverse of normCdf (Acklam's approximation)
  function invNorm(p) {
    p = Math.min(1 - 1e-9, Math.max(1e-9, p));
    var a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239],
        b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572],
        c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783],
        d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416], q, r, lo = 0.02425;
    if (p < lo || p > 1 - lo) {
      q = Math.sqrt(-2 * Math.log(p < lo ? p : 1 - p));
      var v = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
      return p < lo ? v : -v;
    }
    q = p - 0.5; r = q * q;
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  }
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
    var left = t <= 2880 ? 2880 - t : Math.max(0, periodEnd(Math.floor((t - 2880 - 0.001) / 300) + 5) - t);   // (a period's last instant belongs to it)
    if (final || left <= 0) return { p: margin > 0 ? 1 : margin < 0 ? 0 : 0.5, mu: margin, sd: 0, left: 0, poss: 0 };
    var st = stintAt(g, t), edge = 0;
    if (st) edge = fiveStrength(g, "home", st.home, t) - fiveStrength(g, "away", st.away, t);
    var poss = paceAt(g, t) * left / 2880;
    var mu = margin + 2.5 * left / 2880 + edge / 100 * poss * 0.5;
    var sd = Math.max(0.6, 13 * Math.sqrt(left / 2880));
    return { p: normCdf(mu / sd), mu: mu, sd: sd, left: left, poss: poss, edge: edge };
  }
  function renderWinProb(body, g, sub, card) {
    var c = colors(g), end = axisEnd(g), last = g.flow[g.flow.length - 1] || [0, 0, 0];
    var tNow = g.live ? Math.min(end, Math.max(last[0], g.tNow || g.now || 0)) : end;
    var espn = g.wp && g.wp.length > 2;
    var pts = espn ? g.wp.filter(function (q) { return q[0] <= tNow; })
      : g.flow.map(function (f) { return [f[0], winModel(g, f[0], f[1] - f[2], false).p]; });
    var nowM = winModel(g, tNow, g.home.score - g.away.score, g.final);
    if (espn && !g.final) {                        // ESPN's chance now; the spread for the time left centred to match it
      var pNow = g.espnHome != null ? g.espnHome : pts.length ? pts[pts.length - 1][1] : nowM.p;
      nowM.p = pNow;
      if (nowM.sd > 0) nowM.mu = nowM.sd * invNorm(pNow);
    }
    pts.push([tNow, nowM.p]);
    for (var pi = 1; pi < pts.length; pi++) if (pts[pi][0] < pts[pi - 1][0]) pts[pi] = [pts[pi - 1][0], pts[pi][1]];   // (never back in time)
    var ph = nowM.p, pa = 1 - ph;
    var pct = function (v) { return v >= 0.995 && v < 1 ? ">99%" : v <= 0.005 && v > 0 ? "<1%" : Math.round(v * 100) + "%"; };
    body.appendChild(el("div", "ls-wp-top",
      '<span class="t" style="color:' + c.away + '">' + triTag(g.away, 18) + ' <b>' + pct(pa) + '</b></span>' +
      '<span class="bar"><i style="width:' + (pa * 100).toFixed(1) + "%;background:" + c.away + '"></i><i style="width:' + (ph * 100).toFixed(1) +
      "%;background:" + c.home + '"></i></span>' +
      '<span class="t r" style="color:' + c.home + '"><b>' + pct(ph) + "</b> " + triTag(g.home, 18) + "</span>"));
    // the home team's chance through the game (above the middle line: home favoured)
    var W = 272, H = 84, X = function (t) { return 3 + (W - 6) * t / Math.max(end, tNow); }, Y = function (p) { return 4 + (H - 8) * (1 - p); };
    var d = "";
    pts.forEach(function (q, i) { d += (i ? " L " : "M ") + X(q[0]).toFixed(1) + " " + Y(q[1]).toFixed(1); });
    var qlines = "";
    for (var q = 1; q < 4; q++) qlines += '<line x1="' + X(q * 720) + '" x2="' + X(q * 720) + '" y1="3" y2="' + (H - 3) + '" stroke="#2a2721"/>';
    var gid = "lsWp" + g.id;
    function favColor() {                           // the team favoured now; dead even: the team favoured last
      for (var i = pts.length - 1; i >= 0; i--) if (Math.abs(pts[i][1] - 0.5) > 1e-6) return pts[i][1] > 0.5 ? c.home : c.away;
      return c.home;
    }
    var svg = el("div", null, '<svg class="ls-svg" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Win probability through the game">' +
      '<defs><clipPath id="' + gid + 'a"><rect x="0" y="0" width="' + W + '" height="' + (H / 2) + '"/></clipPath>' +
      '<clipPath id="' + gid + 'b"><rect x="0" y="' + (H / 2) + '" width="' + W + '" height="' + (H / 2) + '"/></clipPath></defs>' + qlines +
      '<line x1="0" x2="' + W + '" y1="0.6" y2="0.6" stroke="#c9c3b8" stroke-opacity=".38" stroke-width="1.2"/>' +
      '<line x1="0" x2="' + W + '" y1="' + (H - 0.6) + '" y2="' + (H - 0.6) + '" stroke="#c9c3b8" stroke-opacity=".38" stroke-width="1.2"/>' +
      '<line x1="3" x2="' + (W - 3) + '" y1="' + (H / 2) + '" y2="' + (H / 2) + '" stroke="#3a362e" stroke-dasharray="3 3"/>' +
      '<path d="' + d + '" fill="none" stroke="' + c.home + '" stroke-width="1.8" clip-path="url(#' + gid + 'a)"/>' +
      '<path d="' + d + '" fill="none" stroke="' + c.away + '" stroke-width="1.8" clip-path="url(#' + gid + 'b)"/>' +
      svgLogo(g.home, 4, 3, 11) + svgLogo(g.away, 4, H - 14, 11) + (g.live ? nowDot(X(tNow), Y(nowM.p), favColor()) : "") + "</svg>");
    svg.setAttribute("data-tip", "wp");
    body.appendChild(svg);
    if (card) {
      card._tips = card._tips || {};
      card._tips.wp = function (x) {                   // both teams' chances at that moment, and the score then
        if (x == null) return null;
        var tEnd = Math.max(end, tNow), t = Math.max(0, Math.min(tNow, (x - 3) / (W - 6) * tEnd)), p = pts.length ? pts[0][1] : 0.5;
        for (var i = 0; i < pts.length; i++) {
          if (pts[i][0] > t) {
            var a0 = pts[i - 1] || pts[i], f = pts[i][0] > a0[0] ? (t - a0[0]) / (pts[i][0] - a0[0]) : 1;
            p = a0[1] + (pts[i][1] - a0[1]) * f; break;
          }
          p = pts[i][1];
        }
        var sa = scoreAt(g, t);
        return { html: '<div class="h">' + esc(t <= 0 ? "Tip-off" : clockAt(t)) + "</div>" +
                   tipTeamLine(g.home, c.home, "<b>" + pct(p) + "</b> to win") + tipTeamLine(g.away, c.away, "<b>" + pct(1 - p) + "</b> to win") +
                   scoreLine(g, sa[0], sa[1]),
                 gx: X(t), gy: Y(p) };
      };
    }
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

  // ------------------------------------------------------------ INJURY REPORT (the window before ALL GAMES)
  // Both teams' injury reports (ESPN's, as of today) and what they do to each team's +/-. From the team's season
  // lineups -- the same numbers the Lineup Network window reads from the dashboard -- each player's ON/OFF (the team's
  // net rating, per 100 possessions, with him on the floor minus with him off it), the share of the team's minutes he
  // played, and the team's net rating at full strength next to its net rating in the lineups with none of its OUT
  // players. The two teams' drops side by side give the INJURY EDGE: which team the injuries tilt the game toward.
  // Early in a season (fewer than INJ_MIN_MINUTES lineup minutes yet) the numbers are last season's.
  var INJ_MIN_MINUTES = 480;
  function prevSeasonOf(season) { var y = parseInt(season.slice(0, 4), 10) - 1; return y + "-" + String(y + 1).slice(2); }
  function fiveManMinutes(d) {
    var t = 0, five = (d && d.groups && d.groups["5"]) || {};
    Object.keys(five).forEach(function (k) { t += num(five[k][1]); });
    return t;
  }
  function injuryLineups(g, tri) {
    var season = seasonOf(g.when);
    return seasonLineups(season, tri).then(function (d) {
      if (d && fiveManMinutes(d) >= INJ_MIN_MINUTES) return { data: d, season: season };
      var prev = prevSeasonOf(season);
      return seasonLineups(prev, tri).then(function (p) {
        if (p && fiveManMinutes(p) > fiveManMinutes(d)) return { data: p, season: prev };
        return d && fiveManMinutes(d) > 0 ? { data: d, season: season } : null;
      });
    });
  }
  // net ratings over the team's 5-man lineups, weighted by minutes: all of them, the ones without any OUT player, and
  // for each listed player the lineups with him (on) and without him (off)
  function lineupSplits(d, outIds, ids) {
    var five = (d && d.groups && d.groups["5"]) || {};
    function acc() { return { s: 0, m: 0 }; }
    var all = acc(), without = acc(), per = {};
    ids.forEach(function (id) { if (id) per[id] = { on: acc(), off: acc() }; });
    Object.keys(five).forEach(function (key) {
      var v = five[key], net = parseFloat(v[0]), m = num(v[1]);
      if (!m || !isFinite(net)) return;
      var group = key.split("-");
      all.s += net * m; all.m += m;
      if (!outIds.some(function (id) { return group.indexOf(String(id)) >= 0; })) { without.s += net * m; without.m += m; }
      Object.keys(per).forEach(function (id) { var x = group.indexOf(id) >= 0 ? per[id].on : per[id].off; x.s += net * m; x.m += m; });
    });
    function avg(a) { return { net: a.m ? a.s / a.m : null, min: a.m }; }
    var out = { all: avg(all), without: avg(without), per: {} };
    Object.keys(per).forEach(function (id) { out.per[id] = { on: avg(per[id].on), off: avg(per[id].off) }; });
    return out;
  }
  // OUT (and doubtful) players count against the team; day-to-day / questionable ones are listed but not counted
  function injOut(p) { return /^(out|doubtful)/i.test(p.status) || /^(o|out|ofs|d)$/i.test(p.code) || /^(out|ofs)$/i.test(p.fantasy); }
  function signed(v, digits) {
    if (v == null || !isFinite(v)) return "–";
    var r = Math.abs(v) < Math.pow(10, -(digits == null ? 1 : digits)) / 2 ? 0 : v;
    return (r > 0 ? "+" : r < 0 ? "−" : "") + Math.abs(r).toFixed(digits == null ? 1 : digits);
  }
  function injWhen(p) {
    var bits = [p.kind && p.kind !== "Not Specified" ? [p.side, p.kind].filter(Boolean).join(" ") : "", p.detail].filter(Boolean);
    var label = bits.join(" · ");
    var today = etDay(new Date().toISOString());
    if (p.back && /^\d{4}-\d{2}-\d{2}/.test(p.back) && p.back.slice(0, 10) > today) {
      var dt = "";
      try { dt = new Date(p.back.slice(0, 10) + "T12:00:00-05:00").toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "America/New_York" }); } catch (e) {}
      if (dt) return (label ? label + " · " : "") + "back ~" + dt;
    }
    return label || (injOut(p) ? "out" : "day-to-day");
  }
  // a small net-rating scale: the hollow ring is full strength, the filled dot is without the OUT players
  function injScale(full, without, color) {
    var W = 92, H = 14, lim = 15;
    function X(v) { return 4 + (Math.max(-lim, Math.min(lim, v)) + lim) / (2 * lim) * (W - 8); }
    var svg = '<svg class="sc" viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" aria-hidden="true">' +
      '<line x1="4" y1="7" x2="' + (W - 4) + '" y2="7" stroke="#2c2923" stroke-width="3" stroke-linecap="round"/>' +
      '<line x1="' + X(0) + '" y1="2.5" x2="' + X(0) + '" y2="11.5" stroke="#5a554c" stroke-width="1"/>';
    if (full != null && without != null) {
      var drop = without < full - 0.05;
      svg += '<line x1="' + X(full).toFixed(1) + '" y1="7" x2="' + X(without).toFixed(1) + '" y2="7" stroke="' + (drop ? "#ff5a4a" : "#3ecf8e") + '" stroke-width="3" stroke-linecap="round"/>' +
        '<circle cx="' + X(full).toFixed(1) + '" cy="7" r="4" fill="#0c0b0a" stroke="' + color + '" stroke-width="1.6"/>' +
        '<circle cx="' + X(without).toFixed(1) + '" cy="7" r="3.4" fill="' + color + '"/>';
    } else if (full != null) {
      svg += '<circle cx="' + X(full).toFixed(1) + '" cy="7" r="4" fill="#0c0b0a" stroke="' + color + '" stroke-width="1.6"/>';
    }
    return svg + "</svg>";
  }
  // the window shows up a little before it scrolls into view: only then are the two teams' season lineups asked for
  function whenNearView(card) {
    return new Promise(function (resolve) {
      var vp = root.querySelector(".ls-viewport");
      if (!("IntersectionObserver" in window) || !vp) { resolve(); return; }
      var io = new IntersectionObserver(function (es) {
        if (es.some(function (e) { return e.isIntersecting; })) { io.disconnect(); resolve(); }
      }, { root: vp, rootMargin: "0px 500px 0px 500px", threshold: 0.01 });
      io.observe(card);
    });
  }
  function renderInjuries(body, g, sub, card) {
    if (!g.injuries) {
      body.appendChild(el("div", "ls-foot", "The injury report comes from ESPN's live feed, which can't be reached right now."));
      return;
    }
    var c = colors(g), alive = true, today = etDay(new Date().toISOString());
    var wrap = el("div", "ls-inj");
    var impact = el("div", "ls-inj-impact", '<div class="ls-inj-wait">Working out what the injuries do to each team\'s +/-<i>…</i></div>');
    wrap.appendChild(impact);
    ["away", "home"].forEach(function (side) {
      var team = teamOf(g, side), list = g.injuries[side].slice();
      list.sort(function (a, b) { return (injOut(b) ? 1 : 0) - (injOut(a) ? 1 : 0) || String(a.name).localeCompare(String(b.name)); });
      var nOut = list.filter(injOut).length, nDay = list.length - nOut;
      var sec = el("div", "ls-inj-team");
      sec.appendChild(el("div", "ls-inj-th", '<span class="nm" style="color:' + c[side] + '">' + logoImg(team, 18) + esc(team.city ? team.city + " " + team.name : team.name) +
        '</span><span class="ct" data-side="' + side + '">' + (list.length ? (nOut ? nOut + " out" : "") + (nOut && nDay ? " · " : "") + (nDay ? nDay + " day-to-day" : "") : "") + "</span>"));
      if (!list.length) sec.appendChild(el("div", "ls-inj-none", "Nobody on the report: full strength"));
      list.forEach(function (p) {
        var out = injOut(p);
        var row = el("div", "ls-inj-row", '<span class="ls-face" style="--team:' + c[side] + ";background-image:url('" + esc(p.img) + "')\"></span>" +
          '<span class="who"><b>' + esc(p.name) + "</b><i>" + esc(injWhen(p)) + "</i></span>" +
          '<span class="st ' + (out ? "out" : "dtd") + '">' + (out ? "OUT" : "DTD") + "</span>" +
          '<span class="oo" title="On/off: the team\'s net rating with him on the floor minus with him off it"><b>–</b><i>on/off</i></span>');
        row.title = p.name + " · " + (p.status || (out ? "Out" : "Day-To-Day")) + (p.kind ? " · " + p.kind : "") + (p.back ? " · expected back " + p.back.slice(0, 10) : "");
        row._p = p;
        sec.appendChild(row);
      });
      sec._side = side;
      wrap.appendChild(sec);
    });
    body.appendChild(wrap);
    var asOf = "";
    try { asOf = new Date().toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "America/New_York" }); } catch (e) {}
    var footText = (g.final && etDay(g.when) < today ? "Today's report for both teams. " : "") +
      "On/off = the team's net rating with him on the floor minus off it, per 100 possessions. Report: ESPN" + (asOf ? ", " + esc(asOf) : "") + ".";
    var foot = el("div", "ls-foot ls-inj-foot", footText);
    body.appendChild(foot);

    function fill(side, res) {
      var team = teamOf(g, side), list = g.injuries[side];
      var sec = Array.prototype.filter.call(wrap.querySelectorAll(".ls-inj-team"), function (x) { return x._side === side; })[0];
      if (!res || !res.data) return { side: side, team: team, ok: false };
      var ids = nbaIdsFor(res.data, list);
      var outIds = ids.filter(function (id, i) { return id && injOut(list[i]); });
      var sp = lineupSplits(res.data, outIds, ids), outShare = 0;
      Array.prototype.forEach.call(sec.querySelectorAll(".ls-inj-row"), function (row) {
        var i = list.indexOf(row._p), id = ids[i], oo = row.querySelector(".oo b");
        var x = id ? sp.per[id] : null;
        if (!x || !x.on.min || x.off.net == null) { oo.textContent = "–"; row.querySelector(".oo").title = "No " + res.season + " lineup minutes for him with this team"; return; }
        var v = x.on.net - x.off.net;
        oo.textContent = signed(v);
        oo.className = v >= 0.05 ? "up" : v <= -0.05 ? "down" : "";
        var share = sp.all.min ? x.on.min / sp.all.min : 0;
        if (injOut(row._p)) outShare += share;
        row.querySelector(".oo").title = res.season + ": team " + signed(x.on.net) + " with him on the floor, " + signed(x.off.net) + " with him off it · " +
          Math.round(share * 100) + "% of the team's lineup minutes";
        if (x.on.min < 60) row.querySelector(".oo").classList.add("thin");
      });
      var ct = sec.querySelector(".ct");
      if (ct && outIds.length && outShare > 0) ct.innerHTML = ct.innerHTML.replace(/^(\d+) out/, "$1 out (" + Math.round(Math.min(1, outShare) * 100) + "% of minutes)");
      return { side: side, team: team, ok: sp.all.net != null, full: sp.all.net, without: outIds.length ? sp.without.net : sp.all.net,
               withoutMin: sp.without.min, nOut: outIds.length, season: res.season };
    }
    function drawImpact(rs) {
      if (!alive) return;
      var good = rs.filter(function (r) { return r.ok; });
      if (!good.length) { impact.innerHTML = '<div class="ls-inj-wait">Season lineup numbers aren\'t available right now, so the +/- impact can\'t be worked out.</div>'; return; }
      var html = "";
      rs.forEach(function (r) {
        var col = c[r.side];
        if (!r.ok) { html += '<div class="ls-inj-imp"><span class="tl">' + logoImg(r.team, 16) + esc(r.team.tri) + '</span><span class="na">no lineup numbers</span></div>'; return; }
        var d = r.without - r.full, thin = r.nOut && r.withoutMin < 150;
        html += '<div class="ls-inj-imp"><span class="tl">' + logoImg(r.team, 16) + '<span style="color:' + col + '">' + esc(r.team.tri) + "</span></span>" +
          injScale(r.full, r.without, col) +
          '<span class="nums"><b>' + signed(r.full) + "</b><i>full</i>" + (r.nOut ? '<b class="' + (d < -0.05 ? "down" : "up") + '">' + signed(r.without) + "</b><i>without OUT" + (thin ? "*" : "") + "</i>" : '<i class="ok">nobody out</i>') + "</span></div>";
      });
      var both = rs.length === 2 && rs[0].ok && rs[1].ok;
      if (both) {                                  // just the edge: grey, the favoured team (if any) in its colour
        var dA = rs[0].without - rs[0].full, dH = rs[1].without - rs[1].full, edge = dH - dA;   // > 0: the injuries favor the home team
        if (Math.abs(edge) < 0.5) html += '<div class="ls-inj-edge">Injury edge: <b>even</b></div>';
        else {
          var fav = edge > 0 ? rs[1] : rs[0];
          html += '<div class="ls-inj-edge">Injury edge: ' + logoImg(fav.team, 14) + '<b style="color:' + c[fav.side] + '">' + esc(fav.team.tri) + " " + signed(Math.abs(edge)) +
            "</b></div>";
        }
      }
      impact.innerHTML = html;
      // which season's lineups, in the footnote at the bottom
      var seasons = good.map(function (r) { return r.season; }).filter(function (x, i, a) { return a.indexOf(x) === i; });
      var thinAny = rs.some(function (r) { return r.ok && r.nOut && r.withoutMin < 150; });
      foot.innerHTML = footText + " Lineups: " + esc(seasons.join(" / ")) + (thinAny ? " (*few minutes without them)" : "") + ".";
    }
    whenNearView(card).then(function () {
      if (!alive) return null;
      // one team at a time (each is a quiet visit to the dashboard); the home team's numbers are often already here
      // from the Lineup Network window
      var res = {};
      return injuryLineups(g, g.home.tri).then(function (r) { res.home = r; if (!alive) return null; return injuryLineups(g, g.away.tri); })
        .then(function (r) { res.away = r; return res; });
    }).then(function (res) {
      if (!alive || !res) return;
      drawImpact([fill("away", res.away), fill("home", res.home)]);
    }).catch(function () { drawImpact([{ side: "away", team: g.away, ok: false }, { side: "home", team: g.home, ok: false }]); });
    return function () { alive = false; };
  }

  // ------------------------------------------------------------ BOX SCORE (the window after INJURY REPORT)
  // One team's box score at a time (its menu has both teams, the away team first), then the team's totals and its
  // shooting percentages. Every column fits the window (only an up-and-down scroll; on a phone, players go by last name
  // and STL, BLK, OREB, DREB, TO and PF step aside). Click any column's title to sort by it (again to flip it); it opens
  // sorted by points, and the sorted column has an arrow by its title. During a live game the players on the floor have
  // a breathing dot in the team's colour, and every number follows the game. The team's best in points, rebounds and
  // assists are in gold.
  function boxItems(g) { return [["away", logoImg(g.away, 14) + esc(g.away.name)], ["home", logoImg(g.home, 14) + esc(g.home.name)]]; }
  var BOX_COLS = [   // [title, value shown, sort value, class (width; "opt": left out on a phone)]
    ["MIN", function (p) { return String(Math.round(minutesOf(p.min))); }, function (p) { return minutesOf(p.min); }, "w2"],
    ["PTS", "pts", null, "w2"], ["REB", "reb", null, "w2"], ["AST", "ast", null, "w2"], ["STL", "stl", null, "w2 opt"], ["BLK", "blk", null, "w2 opt"],
    ["FG", function (p) { return p.fgm + "-" + p.fga; }, function (p) { return num(p.fgm) * 1000 - num(p.fga); }, "w3"],
    ["3PT", function (p) { return p.tpm + "-" + p.tpa; }, function (p) { return num(p.tpm) * 1000 - num(p.tpa); }, "w3"],
    ["FT", function (p) { return p.ftm + "-" + p.fta; }, function (p) { return num(p.ftm) * 1000 - num(p.fta); }, "w3"],
    ["OREB", "oreb", null, "w4 opt"], ["DREB", "dreb", null, "w4 opt"], ["TO", "tov", null, "w2 opt"], ["PF", "pf", null, "w2 opt"],
    ["+/-", function (p) { var v = num(p.pm); return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v); }, function (p) { return num(p.pm); }, "w3"]];
  function boxLast(p) {                              // "M. Johnson Jr." -> "Johnson Jr."
    var parts = String(p.name || p.short || "").split(" "), k = parts.length - 1;
    if (k >= 1 && /^(jr\.?|sr\.?|ii|iii|iv)$/i.test(parts[k])) k--;
    while (k >= 1 && /^(de|da|del|della|di|du|la|le|van|von|der|den|st\.?)$/i.test(parts[k - 1])) k--;   // "de Larrea", "Van Vleet"
    return parts.slice(Math.max(0, k)).join(" ");
  }
  function renderBox(body, g, sub, card) {
    var side = sub === "home" ? "home" : "away", team = teamOf(g, side), col = sideColor(g, side);
    var list = (g.players || []).filter(function (p) { return p.team === side; });
    if (!list.length) { body.appendChild(el("div", "ls-foot", "No box score for " + logoImg(team, 13) + esc(team.name) + " yet.")); return; }
    var sort = (card && card._boxSort) || { k: "PTS", dir: -1 };
    var colOf = function (k) { return BOX_COLS.filter(function (c) { return c[0] === k; })[0]; };
    var sortVal = function (p) {
      if (sort.k === "NAME") return boxLast(p).replace(/^(de|da|del|della|di|du|la|le|van|von|der|den)\s+/i, "") + " " + (p.name || "");
      var c = colOf(sort.k) || colOf("PTS");
      return c[2] ? c[2](p) : num(p[c[1]]);
    };
    var rows = list.slice().sort(function (a, b) {
      var va = sortVal(a), vb = sortVal(b);
      var d = typeof va === "string" ? va.localeCompare(vb) : va - vb;
      return (d * sort.dir) || (b.pts - a.pts) || (minutesOf(b.min) - minutesOf(a.min));
    });
    var onFloor = g.live ? (((g.onNow || {})[side]) || []) : [];
    var best = {};
    ["pts", "reb", "ast"].forEach(function (k) { best[k] = Math.max.apply(null, list.map(function (p) { return num(p[k]); })); });
    function cell(p, c) {
      var v = typeof c[1] === "function" ? c[1](p) : String(num(p[c[1]]));
      var hi = typeof c[1] === "string" && best[c[1]] > 0 && num(p[c[1]]) === best[c[1]];
      return '<td class="' + c[3] + (hi ? " hi" : "") + (c[0] === sort.k ? " s" : "") + '">' + esc(v) + "</td>";
    }
    function row(p) {
      var on = onFloor.indexOf(p.id) >= 0;
      return '<tr><th title="' + esc(p.name) + '"><span class="nm">' + (on ? '<i class="on" style="background:' + col + '"></i>' : "") +
        '<span class="n">' + esc(p.short || p.name) + '</span><span class="n ln">' + esc(boxLast(p)) + '</span><span class="ps">' + esc(p.pos || "") + "</span></span></th>" +
        BOX_COLS.map(function (c) { return cell(p, c); }).join("") + "</tr>";
    }
    var sum = function (k) { return list.reduce(function (a, p) { return a + num(p[k]); }, 0); };
    var tot = { pts: sum("pts"), reb: sum("reb"), ast: sum("ast"), stl: sum("stl"), blk: sum("blk"), fgm: sum("fgm"), fga: sum("fga"),
      tpm: sum("tpm"), tpa: sum("tpa"), ftm: sum("ftm"), fta: sum("fta"), oreb: sum("oreb"), dreb: sum("dreb"), tov: sum("tov"), pf: sum("pf") };
    var pct = function (m, a) { return a ? (100 * m / a).toFixed(1) + "%" : "–"; };
    var arrow = function (k) { return k === sort.k ? '<span class="ar" aria-hidden="true">' + (sort.dir < 0 ? "▼" : "▲") + "</span>" : ""; };
    var aria = function (k) { return k === sort.k ? ' aria-sort="' + (sort.dir < 0 ? "descending" : "ascending") + '"' : ""; };
    var head = '<tr><th data-k="NAME"' + aria("NAME") + ">" + logoImg(team, 14) + '<span style="color:' + col + '">' + esc(team.tri) + "</span>" + arrow("NAME") + "</th>" +
      BOX_COLS.map(function (c) { return '<td class="' + c[3] + '" data-k="' + c[0] + '"' + aria(c[0]) + ">" + arrow(c[0]) + c[0] + "</td>"; }).join("") + "</tr>";
    var foot = '<tr class="tot"><th>Team</th>' + BOX_COLS.map(function (c) {
      return c[0] === "MIN" || c[0] === "+/-" ? '<td class="' + c[3] + '"></td>' : cell(tot, c).replace(" hi", "");
    }).join("") + "</tr>" +
      '<tr class="pct"><th></th>' + BOX_COLS.map(function (c) {
        var v = c[0] === "FG" ? pct(tot.fgm, tot.fga) : c[0] === "3PT" ? pct(tot.tpm, tot.tpa) : c[0] === "FT" ? pct(tot.ftm, tot.fta) : "";
        return '<td class="' + c[3] + '">' + v + "</td>";
      }).join("") + "</tr>";
    var html = '<table class="ls-box"><thead>' + head + "</thead><tbody>" + rows.map(row).join("") + foot + "</tbody></table>";
    var wrap = el("div", "ls-box-wrap", html);
    wrap.style.setProperty("--team", col);
    body.appendChild(wrap);
    if (card) {
      card._boxArgs = { g: g, sub: sub };
      if (!card._boxClick) {                          // (one listener per window: a click on a column title sorts by it)
        card._boxClick = true;
        card.addEventListener("click", function (e) {
          var h = e.target && e.target.closest ? e.target.closest(".ls-box thead [data-k]") : null;
          if (!h || !card._boxArgs) return;
          var k = h.getAttribute("data-k"), cur = card._boxSort || { k: "PTS", dir: -1 };
          card._boxSort = { k: k, dir: cur.k === k ? -cur.dir : (k === "NAME" ? 1 : -1) };
          var b = card.querySelector(".ls-body");
          if (!b) return;
          b.innerHTML = "";
          renderBox(b, card._boxArgs.g, card._boxArgs.sub, card);
        });
      }
    }
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
      // ESPN's own chance after the latest play; only without it the same simple estimate as before
      g.pHome = g.espnHome != null ? g.espnHome
        : R <= 0 ? (margin > 0 ? 1 : margin < 0 ? 0 : 0.5) : normCdf((margin + 2.5 * R / 2880) / Math.max(0.6, 13 * Math.sqrt(R / 2880)));
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
    var dayPick = makePicker("All games: date", function (v) { state.day = v; draw(); setDay(v); if (root._hdrDays) root._hdrDays(); });
    pickers.appendChild(dayPick);
    // The date menu: every day this season that had games (the regular season and playoffs -- not the preseason),
    // newest first, plus tomorrow's when it leads the tape. The menu shows 7 at a time and scrolls for the rest.
    var regStart = null;
    function seasonDays() {
      if (index.mode !== "season" || index.preOpener) return index.days || [];
      var today = etDay(new Date().toISOString()), start = regStart || index.seasonStart || "", set = {};
      (index.days || []).forEach(function (d) { set[d] = 1; });
      Object.keys(knownDays).forEach(function (d) { if (d <= today && d >= start) set[d] = 1; });
      return Object.keys(set).sort().reverse();
    }
    if (index.mode === "season" && index.seasonYear) {
      getJSON("https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/" + index.seasonYear + "/types/2").then(function (ty) {
        var d = String((ty && ty.startDate) || "").slice(0, 10);
        if (/^\d{4}-\d{2}-\d{2}$/.test(d)) { regStart = d; dayPick._set(dayItems(), state.day); if (root._hdrDays) root._hdrDays(); }
      }).catch(function () {});
    }
    function dayItems() {
      return seasonDays().map(function (d) {
        return [d, esc(dayLabel(d)) + (d === today ? '&nbsp;<span class="ls-live-word">today</span>' : d > today ? '&nbsp;<span class="ls-live-word">upcoming</span>' : "")];
      });
    }
    dayPick._set(dayItems(), state.day);
    function gamesOn(day) {
      if (source !== "espn") return Promise.resolve(index.games.filter(function (g) { return g.day === day; }));
      if (day === today && liveBoard && liveBoard.day === today) return Promise.resolve(liveBoard.events.map(watchGame));
      return scoreboard(day).then(function (b) {
        return ((b && b.events) || []).filter(function (e) { return realEvent(e) && etDay(e.date) === day; }).map(watchGame);
      });
    }
    function draw(quiet) {
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
        var html = '<div class="ls-w-head"><span>Game</span><span class="c">Time</span><span class="c">Win prob.</span></div>';
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
          var match = g.pre || (!g.live && !g.final)
            ? '<span class="sa" style="color:' + c.away + '"><span class="tri">' + esc(g.away.tri) + '</span></span><span class="d vs">vs.</span>' +
              '<span class="sh" style="color:' + c.home + '"><span class="tri">' + esc(g.home.tri) + "</span></span>"
            : '<span class="sa" style="color:' + c.away + '"><span class="tri">' + esc(g.away.tri) + " </span>" + g.away.score + '</span><span class="d">-</span>' +
              '<span class="sh" style="color:' + c.home + '">' + g.home.score + '<span class="tri"> ' + esc(g.home.tri) + "</span></span>";
          html += '<div class="ls-w-row' + (g.live ? " live" : "") + '"><span class="gm">' + logoImg(g.away, 15) + match + logoImg(g.home, 15) +
            '</span><span class="tm">' + time + '</span><span class="pr">' + prob + "</span></div>";
        });
        if (!games.length) html += '<div class="ls-foot">No games this day.</div>';
        var list = el("div", "ls-watch-list", html);
        if (quiet && body.firstChild && body.firstChild.className === "ls-watch-list") {
          var tmp = el("div"); tmp.appendChild(list); morph(body, tmp, true);     // a live update: only what changed
        } else { body.innerHTML = ""; body.appendChild(list); }
      }).catch(function () {
        body.innerHTML = '<div class="ls-foot">This day\'s games couldn\'t be loaded right now.</div>';
      });
    }
    draw();
    // live updates: today's list follows the scoreboard every second, in place
    card._boardRefresh = function () { if (state.day === etDay(new Date().toISOString())) draw(true); };
    card._days = function () { dayPick._set(dayItems(), state.day); if (root._hdrDays) root._hdrDays(); };
    card._dayTo = function (v) { if (v === state.day) return; state.day = v; dayPick._set(dayItems(), v); draw(); };
    root._dayItems = dayItems;
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
        return '<span class="ls-hot-chip' + (x.win ? " w" : " l") + (i >= run0 ? " run" : "") + '" data-t="' + (x.win ? "Win " : "Loss ") + (x.home ? "vs " : "at ") + esc(x.vs) + " " + x.pts + "-" + x.opp + '">' +
          '<b>' + (x.win ? "W" : "L") + "</b><i>" + x.pts + "-" + x.opp + "</i></span>";
      }).join("");
      var seqT = el("div", "ls-hot-seq", '<div class="ls-title">Last ' + f.last.length + " games, oldest first</div>" + '<div class="ls-hot-row chips" data-tip="text">' + chips + "</div>");
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
        '" data-t="Shot ' + (i + 1) + ": " + (x[5] ? "made" : "missed") + " " + x[6] + "PT · " + Math.round(Math.sqrt(x[3] * x[3] + x[4] * x[4]) / 10) + " ft · " + esc(clockAt(x[0])) + '"></span>';
    }).join("");
    var seqP = el("div", "ls-hot-seq" + (r.seq.length <= 16 ? " big" : ""), '<div class="ls-title">Every shot, in order</div><div class="ls-hot-row" data-tip="text">' + dots + "</div>" +
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
      if (QUIET) { body.classList.add("ls-hot-lit"); return; }      // a live update: everything at once
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
    var track = tickerTrack();
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
    if (root._hdrDays) root._hdrDays();
  }
  function forEachCard(fn) { Array.prototype.forEach.call(root.querySelectorAll(".ls-card"), fn); }
  // a day picked in ALL GAMES: during the season the tape and every window move to that day; during the Finals and
  // the offseason the tape keeps every Finals game and the windows switch to that day's game
  function setDay(day) {
    if (!index || !day) return Promise.resolve();
    if (index.mode !== "season") {
      var g = index.games.filter(function (x) { return x.day === day; })[0];
      if (g) selectGame(g.id);
      return Promise.resolve();
    }
    var today = etDay(new Date().toISOString());
    var fresh = day === today || !index.dayGames[day] ? scoreboard(day).then(function (b) { return gamesOfDay(b, day); })
      : Promise.resolve(index.dayGames[day]);
    return fresh.then(function (games) {
      if (games) index.dayGames[day] = games;
      applyDay(index, day);
      renderTicker();
      renderHeader();
      forEachCard(function (c) { if (c._setGames) c._setGames(); });
      if (root._toStart) root._toStart();
      manageRefresh();
      updateHighlights();
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
    if (tickerNode) Array.prototype.forEach.call(tickerNode.querySelectorAll(".ls-tk"), function (b) { b.classList.toggle("on", b.getAttribute("data-id") === id); });
    Array.prototype.forEach.call(root.querySelectorAll(".ls-card"), function (card) { if (card._showGame) card._showGame(id); });
    if (root._toStart) root._toStart();                      // the cards start over from the first one
    updateHighlights();
  }

  // ------------------------------------------------------------ YouTube game highlights
  // Once the game the windows show is over and the NBA has posted its highlights on YouTube, a long button above the
  // windows ("YouTube game highlights") opens the video right there, between the tape and the windows. The videos are
  // found by a GitHub Action (.github/workflows/highlights.yml) that reads the NBA's YouTube channel every few minutes
  // and saves each game's video in data/highlights.json.
  var HL_URL = "data/highlights.json", hlData = {}, hlOpenFor = null;
  var hlBox = root.querySelector(".ls-hl");
  function loadHighlights() {
    return fetch(HL_URL + "?t=" + Math.floor(Date.now() / 300000), { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (d) { hlData = (d && d.games) || d || {}; updateHighlights(); }).catch(function () {});
  }
  function shownGame() {
    if (!index) return null;
    var id = index.selected || index["default"], list = (index.cardGames || index.games || []);
    return list.filter(function (g) { return g.id === id; })[0] || (index.games || []).filter(function (g) { return g.id === id; })[0] || null;
  }
  function hlTitle(g) {                                       // "BKN vs BOS 10/27 Highlights"
    var d = String(g.day || "").split("-");
    return g.away.tri + " vs " + g.home.tri + (d.length === 3 ? " " + (+d[1]) + "/" + (+d[2]) : "") + " Highlights";
  }
  function updateHighlights() {
    if (!hlBox) return;
    var g = shownGame(), v = g && g.final ? hlData[g.id] : null, M = window.BAMini;
    if (!v || !v.id) { if (M && hlOpenFor) M.release(); hlBox.hidden = true; hlBox.innerHTML = ""; hlOpenFor = null; return; }
    if (hlOpenFor === g.id + ":" + v.id && hlBox.querySelector(".ls-yt-slot") && M && M.vid() === v.id) return;   // (already playing this one)
    if (M && hlOpenFor) M.release();                          // another game's video keeps playing in the corner
    hlOpenFor = null;
    hlBox.hidden = false;
    hlBox.innerHTML = '<button type="button" class="ls-yt-btn" aria-label="Play the YouTube game highlights of ' + esc(g.away.tri + " at " + g.home.tri) + '">' +
      '<svg viewBox="0 0 28 20" aria-hidden="true"><rect width="28" height="20" rx="5" fill="#ff0033"/><path d="M11 5.5v9l8-4.5z" fill="#fff"/></svg>YouTube game highlights</button>';
    function play() {
      hlOpenFor = g.id + ":" + v.id;
      hlBox.innerHTML = '<div class="ls-yt-slot"><span class="ls-yt-away">Playing in the corner</span></div>';
      var opts = { vid: v.id, title: hlTitle(g), anchor: hlBox.querySelector(".ls-yt-slot"), onClose: function () { hlOpenFor = null; updateHighlights(); } };
      if (window.BAMini) window.BAMini.open(opts);
    }
    hlBox.querySelector("button").addEventListener("click", play);
    if (M && M.vid() === v.id) play();                         // (it came along from another page: back in its place)
  }
  setInterval(function () { if (!document.hidden) loadHighlights(); }, 10 * 60e3);
  setInterval(function () { if (!document.hidden) updateHighlights(); }, 30e3);      // (a game that has just ended)

  // ------------------------------------------------------------ other scripts (the tape at the top of every page)
  // BALive.show(id, day): the windows (and this tape) go to that game -- its day first if it's on another day -- and the
  // page scrolls down to them.
  var pendingShow = null;
  function showGameFromOutside(id, day) {
    if (!index) { pendingShow = [id, day]; return; }
    var has = (index.games || []).some(function (g) { return g.id === id; });
    (has || !day ? Promise.resolve() : setDay(day)).then(function () { selectGame(id); scrollToWindows(); });
  }
  window.BALive = { show: showGameFromOutside };

  // ------------------------------------------------------------ the tape's motion
  // The tape slides by itself (about 42 px a second) and can be moved sideways by hand: dragged with a mouse, swiped on
  // a touch screen (it glides a little after a flick), or scrolled sideways on a trackpad. It waits while a mouse is
  // over it, and for 3 seconds after a swipe or a tap, then carries on. An up-and-down swipe still scrolls the page.
  function tickerMotion(tk) {
    var track = tk && tk.querySelector(".ls-ticker-track");
    if (!track || REDUCE) return;                     // (reduced motion: the tape stays put and scrolls like a list)
    tk.classList.add("js-drive");
    var x = 0, v = 0, last = null, hover = false, holdUntil = 0, drag = null, movedAt = -1e9, SPEED = 42;
    function wrap() { var h = track.scrollWidth / 2; if (h > 1) x = ((x % h) - h) % h; }     // (the list is there twice)
    function frame(now) {
      requestAnimationFrame(frame);
      if (last === null) last = now;
      var dt = Math.min(0.1, (now - last) / 1000); last = now;
      if (!drag) {
        if (Math.abs(v) > 8) { x += v * dt; v *= Math.pow(0.03, dt); }        // the glide after a flick
        else { v = 0; if (!hover && now >= holdUntil) x -= SPEED * dt; }
      }
      wrap();
      track.style.transform = "translate3d(" + x.toFixed(2) + "px,0,0)";
    }
    requestAnimationFrame(frame);
    tk.addEventListener("pointerenter", function (e) { if (e.pointerType === "mouse") hover = true; });
    tk.addEventListener("pointerleave", function (e) { if (e.pointerType === "mouse") hover = false; });
    tk.addEventListener("pointerdown", function (e) {
      if (e.button !== 0) return;
      drag = { id: e.pointerId, x0: e.clientX, y0: e.clientY, start: x, moved: false, lx: e.clientX, lt: performance.now(), type: e.pointerType };
      v = 0;
    });
    tk.addEventListener("pointermove", function (e) {
      if (!drag || e.pointerId !== drag.id) return;
      var dx = e.clientX - drag.x0;
      if (!drag.moved) {
        if (Math.abs(dx) < 6) return;
        if (drag.type !== "mouse" && Math.abs(e.clientY - drag.y0) > Math.abs(dx)) { drag = null; return; }   // the page is being scrolled
        drag.moved = true; drag.start = x - dx; tk.classList.add("dragging");
        try { tk.setPointerCapture(e.pointerId); } catch (er) {}
      }
      var now = performance.now();
      v = 0.75 * v + 0.25 * ((e.clientX - drag.lx) / Math.max(8, now - drag.lt) * 1000);
      v = Math.max(-2500, Math.min(2500, v));
      drag.lx = e.clientX; drag.lt = now;
      x = drag.start + dx;
    });
    function end(e) {
      if (!drag || (e && e.pointerId !== drag.id)) return;
      var now = performance.now();
      if (drag.moved) { movedAt = now; if (now - drag.lt > 90) v = 0; }
      if (drag.moved || drag.type !== "mouse") holdUntil = now + 3000;
      drag = null; tk.classList.remove("dragging");
    }
    tk.addEventListener("pointerup", end);
    tk.addEventListener("pointercancel", end);
    tk.addEventListener("click", function (e) {             // a drag that ends on a game isn't a click on it
      if (performance.now() - movedAt < 300) { e.stopPropagation(); e.preventDefault(); }
    }, true);
    tk.addEventListener("wheel", function (e) {              // a trackpad's sideways scroll
      if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
      e.preventDefault(); x -= e.deltaX; v = 0; holdUntil = performance.now() + 2500;
    }, { passive: false });
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
      if (root.classList.contains("ls-grid")) { requestAnimationFrame(step); return; }     // (full screen: every window at once)
      var max = vp.scrollWidth - vp.clientWidth;
      var pickerOpen = !!(openPicker && vp.contains(openPicker)) || !!vp.querySelector(".ls-tip.pinned, .ls-inspecting");
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

  // ------------------------------------------------------------ down to the windows (from the tape at the top)
  function scrollToWindows() {
    var nav = document.querySelector(".site-nav"), cs = nav && getComputedStyle(nav);
    var off = cs && (cs.position === "sticky" || cs.position === "fixed") ? nav.getBoundingClientRect().height + 10 : 10;
    window.scrollTo({ top: Math.max(0, root.getBoundingClientRect().top + window.pageYOffset - off), behavior: REDUCE ? "auto" : "smooth" });
  }

  // ------------------------------------------------------------ full screen
  // "Full screen" (above the tape) lays every window out at once over the whole screen, with the tape at its top; the
  // browser's own full screen where it has one (on an iPhone the page simply covers the screen). Esc, the browser's
  // own exit, or "Exit full screen" puts everything back.
  function setupFullScreen() {
    var btn = document.querySelector(".ls-full-btn"), exitBtn = root.querySelector(".ls-full-exit");
    if (!btn || !tickerNode) return;
    var home = tickerNode.parentNode, next = tickerNode.nextSibling, scrollY0 = 0, boardsHome = null, boardsWasOpen = false;
    function refit() { requestAnimationFrame(function () { fitHeights(); setTimeout(fitHeights, 250); }); }
    function enter() {
      if (root.classList.contains("ls-full")) return;
      scrollY0 = window.pageYOffset;
      root.classList.add("ls-grid", "ls-full");
      document.documentElement.classList.add("ls-full-on");
      if (home !== root) root.insertBefore(tickerNode, root.querySelector(".ls-viewport"));
      // the League Season Leaderboard comes along, open, under the windows
      var boards = document.getElementById("live-boards");
      if (boards) { boardsHome = [boards.parentNode, boards.nextSibling]; boardsWasOpen = !!(window.BABoards && window.BABoards.isOpen()); root.appendChild(boards); if (window.BABoards) window.BABoards.open(true, true); }
      var req = root.requestFullscreen || root.webkitRequestFullscreen;
      if (req) { try { var p = req.call(root); if (p && p.catch) p.catch(function () {}); } catch (e) {} }
      root.scrollTop = 0;
      if (exitBtn) exitBtn.focus({ preventScroll: true });
      refit();
    }
    function exit() {
      if (!root.classList.contains("ls-full")) return;
      root.classList.remove("ls-grid", "ls-full");
      document.documentElement.classList.remove("ls-full-on");
      if (home !== root) home.insertBefore(tickerNode, next);
      var boards = document.getElementById("live-boards");
      if (boards && boardsHome) { boardsHome[0].insertBefore(boards, boardsHome[1]); if (window.BABoards && !boardsWasOpen) window.BABoards.open(false, true); boardsHome = null; }
      var fs = document.fullscreenElement || document.webkitFullscreenElement;
      if (fs) { var ex = document.exitFullscreen || document.webkitExitFullscreen; try { var p = ex.call(document); if (p && p.catch) p.catch(function () {}); } catch (e) {} }
      window.scrollTo(0, scrollY0);
      refit();
    }
    btn.addEventListener("click", enter);
    if (exitBtn) exitBtn.addEventListener("click", exit);
    ["fullscreenchange", "webkitfullscreenchange"].forEach(function (ev) {
      document.addEventListener(ev, function () { if (!(document.fullscreenElement || document.webkitFullscreenElement)) exit(); });
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") exit(); });
  }

  // ------------------------------------------------------------ build
  function build() {
    renderHeader();
    var track = root.querySelector(".ls-track");
    track.innerHTML = "";
    function teamItems(g) { return [["home", logoImg(g.home, 14) + esc(g.home.name)], ["away", logoImg(g.away, 14) + esc(g.away.name)]]; }
    function teamFive(g, sub) { return (((g.live ? g.onNow : g.starters) || {})[sub === "away" ? "away" : "home"] || []).join("-"); }
    // (live: true by default -- each window follows a live game in place; clock: it also follows the game clock;
    // liveKey + redraw: drawn again only when that changes)
    var cards = [
      makeCard({ title: function (g) {
                   if (g.live) return '<i class="ls-dot ls-dot-title" aria-hidden="true"></i>Live game';
                   if (g.pre) return etDay(g.when) > etDay(new Date().toISOString()) ? "Upcoming game" : "Today's game";
                   return "Final score";
                 },
                 name: "Final score", wide: true, cls: "ls-score-card", render: renderScore, clock: true }),
      makeCard({ title: "Shot chart", sub: "player", subItems: function (g) { return playerItems(g, true); }, render: renderShots,
                 cls: "ls-card-shot", onDrawn: fitHeights }),
      makeCard({ title: "Player card", sub: "player", subItems: function (g) { return playerItems(g, false); }, render: renderPlayer, clock: true }),
      makeCard({ title: "Team comparison", render: renderCompare }),
      makeCard({ title: "Lineup network", wide: true, sub: "team", subItems: teamItems, render: renderLineups,
                 mode: { label: "net ratings", def: "season", items: [["season", "Season Net Ratings"], ["live", "Live Game Net Ratings"]] },
                 liveKey: function (g, sub, mode) { return teamFive(g, sub) + (mode === "live" ? "|" + Math.floor(Date.now() / 20000) : ""); },
                 redraw: true }),
      makeCard({ title: "Win probability", render: renderWinProb, clock: true }),
      makeCard({ title: "Assist web", sub: "team", subItems: teamItems, render: renderAssists, redraw: true,
                 liveKey: function (g, sub) { var side = sub === "away" ? 1 : 0; return (g.assists || []).filter(function (x) { return x[2] === side; }).length; } }),
      makeCard({ title: hotTitle, name: "Hot hand", sub: "player or team", subItems: hotItems, prepare: prepareHot, render: renderHot,
                 liveKey: function (g, sub) { return String(sub) + "|" + (g.shots || []).filter(function (x) { return String(x[1]) === String(sub); }).length; } }),
      makeCard({ title: "Leaderboard", sub: "stat", subItems: lbItems, render: renderLeaderboard, clock: true }),
      makeCard({ title: "Injury report", wide: true, pre: true, cls: "ls-inj-card", render: renderInjuries, live: false }),
      makeCard({ title: "Box score", wide: true, cls: "ls-box-card", sub: "team", subItems: boxItems, render: renderBox }),
      makeWatchCard(),
    ];
    cards.forEach(function (c) { track.appendChild(c); });
    renderTicker();
    if (tickerTrack()) tickerTrack().addEventListener("click", function (e) {
      var b = e.target && e.target.closest ? e.target.closest(".ls-tk") : null;
      if (!b) return;
      selectGame(b.getAttribute("data-id")); b.blur();
      // the tape above the banner: down to the windows, now showing that game
      if (!root.contains(tickerNode)) scrollToWindows();
    });
    tickerMotion(tickerNode);
    setupFullScreen();
    if ("IntersectionObserver" in window) {
      var vp = root.querySelector(".ls-viewport");
      var io = new IntersectionObserver(function (es) {
        es.forEach(function (e) { e.target._hidden = !e.isIntersecting; });
      }, { root: vp, threshold: 0.05 });
      cards.forEach(function (c) { io.observe(c); });
    }
    autoScroll(root.querySelector(".ls-viewport"));
    headerDayMenu();
  }
  // the date menu next to the header (TODAY'S GAMES / the date shown): the same list of every day with games as ALL
  // GAMES, opened by the site's standard arrow; picking a day moves the tape, the windows and ALL GAMES to it
  function headerDayMenu() {
    var slot = root.querySelector(".ls-daypick");
    if (!slot || !root._dayItems) return;
    var pick = makePicker("Pick a date with games", function (v) {
      setDay(v);
      forEachCard(function (c) { if (c._dayTo) c._dayTo(v); });
    });
    pick.classList.add("ls-hdr-pick");
    slot.innerHTML = ""; slot.appendChild(pick);
    var badge = root.querySelector(".ls-head .ls-badge");      // the title itself opens the date list too
    if (badge && !badge._pick) {
      badge._pick = true; badge.classList.add("ls-badge-pick"); badge.setAttribute("role", "button"); badge.tabIndex = 0;
      var open = function (e) { e.stopPropagation(); var b = slot.querySelector(".ls-pick-btn"); if (b) b.click(); };
      badge.addEventListener("click", open);
      badge.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(e); } });
    }
    root._hdrDays = function () { pick._set(root._dayItems(), index && index.mode === "season" ? index.day : (index.games.filter(function (g) { return g.id === index.selected; })[0] || {}).day); };
    root._hdrDays();
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
    if (tapeBox) tapeBox.hidden = false;
    build();
    manageRefresh();
    loadHighlights();
    // arriving from another page's tape: index.html?game=ID&day=YYYY-MM-DD#live-strip
    var q = /[?&]game=(\d+)/.exec(location.search), qd = /[?&]day=(\d{4}-\d{2}-\d{2})/.exec(location.search);
    if (pendingShow) { showGameFromOutside(pendingShow[0], pendingShow[1]); pendingShow = null; }
    else if (q) setTimeout(function () { showGameFromOutside(q[1], qd && qd[1]); }, 300);
    return true;
  }

  // ------------------------------------------------------------ live updates
  // While a game is live the page reads ESPN's scoreboard about once a second (only while the tab is open and the tape
  // is on the screen; every 10 seconds while it's scrolled away; not at all while the tab is in the background) and
  // updates everything in place: the tape's scores and clocks, the header, ALL GAMES and the live game's clock and
  // where-it-is-now dots. Whenever the scoreboard shows something new in a game a window is showing -- a score, a new
  // play, a new quarter -- that game's play-by-play is read again and every window showing it follows: the box score,
  // the shot chart, the lines, the leaderboard (ESPN's public feed itself is refreshed every few seconds). Before the
  // day's first tip-off it checks every 30 seconds (every 5 in the last 10 minutes), and the moment a game starts the
  // windows move to today's games. Past midnight (Eastern) the page moves to the new day by itself.
  var liveTimer = null, liveBoard = null, inflight = {}, onScreen = true;
  function anyLive() {
    return !!index && (index.games.some(function (g) { return g.live; }) || (index.cardGames || []).some(function (g) { return g.live; }));
  }
  function needsRefresh() {
    if (!index || source !== "espn") return false;
    if (anyLive()) return true;
    return index.mode === "season" && index.day === etDay(new Date().toISOString()) && !index.games.every(function (g) { return g.final; });
  }
  function pollGap() {
    if (!anyLive()) {
      var soon = index.games.some(function (g) { return g.pre && Date.parse(g.when) - Date.now() < 10 * 60000; });
      return soon ? 5000 : 30000;
    }
    return onScreen ? 1000 : 10000;
  }
  function manageRefresh() {
    if (liveTimer || !needsRefresh() || document.hidden) return;
    liveTimer = setTimeout(liveTick, pollGap());
  }
  function liveTick() {
    liveTimer = null;
    if (document.hidden || !index) return;              // picks up again the moment the tab is shown
    var today = etDay(new Date().toISOString());
    if (index.madeFor && index.madeFor !== today) { newDay(); return; }
    scoreboard(today).then(applyBoard).catch(function () {}).then(manageRefresh);
  }
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) return;
    clearTimeout(liveTimer); liveTimer = null;
    if (index && index.madeFor && index.madeFor !== etDay(new Date().toISOString())) newDay();
    else if (needsRefresh()) liveTick();
  });
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (es) {
      var was = onScreen;
      onScreen = es[0].isIntersecting;
      if (onScreen && !was && liveTimer && anyLive()) { clearTimeout(liveTimer); liveTimer = null; liveTick(); }
    }, { rootMargin: "200px 0px" }).observe(root);
  }
  // a page left open overnight: past midnight (Eastern) it reads the new day's games
  setInterval(function () {
    if (!document.hidden && index && index.madeFor && index.madeFor !== etDay(new Date().toISOString())) newDay();
  }, 5 * 60000);
  function newDay() {
    if (source !== "espn") return;
    espnIndex().then(function (nx) {
      if (!nx || !nx.games || !nx.games.length) return;
      cache = {}; loaded = {}; liveBoard = null;
      clearTimeout(liveTimer); liveTimer = null;
      start(nx);
    }).catch(function () {});
  }
  function copyLive(g, n) {
    ["live", "final", "pre", "status", "tick", "period", "displayClock", "statusName", "espnHome", "lastPlayId"].forEach(function (k) { g[k] = n[k]; });
    g.home.score = n.home.score; g.away.score = n.away.score;
    setNow(g);
  }
  function applyBoard(b) {
    var today = etDay(new Date().toISOString());
    var events = ((b && b.events) || []).filter(function (e) { return realEvent(e) && etDay(e.date) === today; });
    var byId = {};
    events.forEach(function (e) { var g = brief(e); byId[g.id] = g; });
    liveBoard = { day: today, events: events, games: byId };
    var seen = {};
    index.games.concat(index.cardGames || []).forEach(function (g) {
      if (seen[g.id] || !byId[g.id]) return;
      seen[g.id] = 1;
      copyLive(g, byId[g.id]);
    });
    if (index.mode === "season" && index.day === today) {
      index.dayGames[today] = index.games;
      // today's first tip-off: the windows move from the last game day to today's games
      if (index.cardGames !== index.games && index.games.some(started)) {
        applyDay(index, today);
        forEachCard(function (c) { if (c._setGames) c._setGames(); });
      }
    }
    patchTicker();
    renderHeader();
    forEachCard(function (c) { if (c._boardRefresh) c._boardRefresh(); });
    followGames(byId);
  }
  // every game a window is showing that's on today's scoreboard: a fresh read of its play-by-play when something
  // happened, otherwise just its clock
  function followGames(byId) {
    var shown = {};
    forEachCard(function (c) { var id = c._gameId && c._gameId(); if (id) shown[id] = 1; });
    Object.keys(shown).forEach(function (id) {
      var n = byId[id], g = loaded[id];
      if (!n || !g) return;
      var sig = [n.home.score, n.away.score, n.period, n.statusName, n.lastPlayId].join("|");
      if (g._sig == null) g._sig = sig;
      var changed = sig !== g._sig || (g.live !== n.live) || (g.pre && !n.pre);
      var stale = (n.live || g.live) && Date.now() - (g._at || 0) > 15000;
      if ((changed || stale) && !inflight[id] && (n.live || n.final || g.live)) {
        inflight[id] = 1;
        if (n.live) { copyLive(g, n); forEachCard(function (c) { if (c._liveUpdate) c._liveUpdate(g, true); }); }  // (the clock and score right away)
        getJSON(ESPN + "summary?event=" + id).then(function (s) {
          var fresh = fromSummary(s, id);
          fresh._at = Date.now(); fresh._sig = sig;
          if (g.form) fresh.form = g.form;
          if (fresh.live) copyLive(fresh, n);
          loaded[id] = fresh;
          cache[id] = Promise.resolve(fresh);
          forEachCard(function (c) { if (c._liveUpdate) c._liveUpdate(fresh, false); });
        }).catch(function () {}).then(function () { delete inflight[id]; });
      } else if (n.live) {
        copyLive(g, n);
        forEachCard(function (c) { if (c._liveUpdate) c._liveUpdate(g, true); });
      }
    });
  }
  // the tape's buttons, changed in place (rebuilding them would make the scrolling tape jump)
  function patchTicker() {
    var track = tickerTrack();
    if (!track || !index) return;
    var byId = {};
    index.games.forEach(function (g) { byId[g.id] = g; });
    var btns = track.querySelectorAll(".ls-tk"), missing = !btns.length;
    Array.prototype.forEach.call(btns, function (b) {
      var g = byId[b.getAttribute("data-id")];
      if (!g) { missing = true; return; }
      var copy = b.getAttribute("aria-hidden") === "true", tmp = el("div", null, tickerItem(g, copy)), nb = tmp.firstChild;
      if (copy) { nb.setAttribute("tabindex", "-1"); nb.setAttribute("aria-hidden", "true"); nb.removeAttribute("aria-label"); }
      morph(b, nb);
    });
    if (missing) renderTicker();
  }
  espnIndex().then(function (data) {
    if (!start(data)) throw new Error("no ESPN games");
  }).catch(function () {
    source = "static";
    getJSON(BASE + "index.json").then(start).catch(function () { /* no data anywhere: the strip stays hidden */ });
  });
})();
