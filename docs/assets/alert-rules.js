/* What's worth an alert. One file, used in two places so they never drift apart:
   - the website (assets/notify.js), which follows the night's games itself while the site is open in a tab;
   - the alert server (worker/src/index.js imports this file), which sends them when the site is closed.

   Alert types (prefs.types[kind]; a type a subscriber hasn't seen yet counts as on):
     tipoff     a game starts
     final      a game ends (the winner's top scorer)
     close      within 5 points in the last 5 minutes of the 4th
     big        40+ points, 20+ rebounds, 15+ assists, 50-point nights
     upset      an underdog leading late in the 4th; a team erasing a 15-point deficit to lead
     clutch     a game going to overtime (each one); a team winning it in the final minute after trailing or tied
     stat       a triple-double, and a triple-double watch in the 4th (one stat away)
     injury     a player's injury status changes (from ESPN's injury report), for your teams and players
     highlights a game's YouTube highlights are up
     recap      a 9 a.m. recap of last night: your teams' results and the top performance
     games      the day's games are ready to play (Today's Play, 82-0, GM Challenge), at 5 p.m.
     trade      trades, signings and waivers (your teams and players; with nothing picked, trades only)

   Each alert: { kind, teams, player, title, body, url, tag, img, imgs (two logos), round + ring (a player's face) } */
(function (root) {
  "use strict";
  var SITE_LOGO = "assets/icon-192.png";
  // the Celtics' logo rule: 2kratings' logo, as the PNG copy the website keeps (an alert can't show an SVG)
  var CELTICS_LOGO = "assets/logos/Boston-Celtics-Current-Logo.png";
  var TEAM_RING = { ATL: "#E03A3E", BOS: "#18A659", BKN: "#C9C9C9", CHA: "#00778B", CHI: "#E0314B", CLE: "#FDBB30", DAL: "#1E7FD6", DEN: "#FEC524",
    DET: "#E0314B", GS: "#FFC72C", HOU: "#E0314B", IND: "#FDBB30", LAC: "#3B82F6", LAL: "#FDB927", MEM: "#7D95C9", MIA: "#F25C54", MIL: "#EEE1C6",
    MIN: "#1F4399", NO: "#B6995A", NY: "#F58426", OKC: "#2E9BE6", ORL: "#2F8FE0", PHI: "#3B82F6", PHX: "#E56020", POR: "#E03A3E", SAC: "#A57FDB",
    SA: "#C4CED4", TOR: "#E0314B", UTAH: "#4F008F", WSH: "#E31837" };
  var TEAMS = Object.keys(TEAM_RING);
  var KINDS = [
    ["tipoff", "Tip-off", "When a game starts"],
    ["final", "Final score", "When a game ends"],
    ["close", "Close game in the 4th", "Within 5 points in the last 5 minutes"],
    ["clutch", "Clutch & overtime", "Overtime, and games won in the final minute"],
    ["upset", "Upsets & comebacks", "An underdog leading late, a 15-point comeback"],
    ["big", "Big performances", "40+ points, 20+ rebounds, 15+ assists, 50-point nights"],
    ["stat", "Stat watch", "Triple-doubles, and one-stat-away watches in the 4th"],
    ["highlights", "Highlights ready", "A game's YouTube highlights are up"],
    ["injury", "Injuries & late scratches", "Injury report changes for your teams and players"],
    ["trade", "Trades & signings", "Your teams' moves (with no teams picked: trades)"],
    ["recap", "Morning recap", "9 a.m.: last night's results and the top performance"],
    ["games", "Game reminders", "5 p.m.: the day's games are ready to play"]
  ];
  function fold(s) { return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z ]/g, "").trim(); }
  function teamLogo(t) { return t === "BOS" ? CELTICS_LOGO : "https://a.espncdn.com/i/teamlogos/nba/500/" + String(t).toLowerCase() + ".png"; }
  function nyParts(now) {
    var d = new Date(now || Date.now()), o = {};
    try { new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour12: false, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).formatToParts(d).forEach(function (p) { o[p.type] = p.value; }); }
    catch (e) { return { day: d.toISOString().slice(0, 10).replace(/-/g, ""), hour: d.getUTCHours() - 4 }; }
    return { day: o.year + o.month + o.day, hour: +o.hour % 24, minute: +o.minute };
  }
  function gameDay(now) { return nyParts((now || Date.now()) - 6 * 3600e3).day; }   // the NBA's day, rolling over at 6 a.m. New York time
  function periodName(n) { return n <= 4 ? "Q" + n : (n === 5 ? "OT" : (n - 4) + "OT"); }
  function wants(p, teams, player) {
    if (!p.teams.length && !p.players.length) return true;
    if (teams.some(function (t) { return p.teams.indexOf(t) >= 0; })) return true;
    if (player) { var f = fold(player); return p.players.some(function (q) { q = fold(q); return q && (f === q || f.indexOf(q) >= 0 || f.split(" ").pop() === q); }); }
    return false;
  }
  function headOf(a) { var h = a && a.headshot; return typeof h === "string" ? h : (h && h.href) || ""; }
  function pct(c) {
    var r = (c.records || []).filter(function (x) { return x.type === "total" || x.name === "overall"; })[0], m = r && /(\d+)-(\d+)/.exec(r.summary || "");
    return m && +m[1] + +m[2] >= 4 ? { p: +m[1] / (+m[1] + +m[2]), g: +m[1] + +m[2] } : null;
  }

  // ------------------------------------------------------------ the night's games (ESPN's scoreboard, once a minute)
  function detect(sb, seen) {
    var out = [];
    (sb.events || []).forEach(function (ev) {
      var comp = (ev.competitions || [])[0]; if (!comp) return;
      var st = comp.status || ev.status || {}, type = st.type || {}, state = type.state || "pre";
      var cs = comp.competitors || [];
      var home = cs.filter(function (c) { return c.homeAway === "home"; })[0] || cs[0], away = cs.filter(function (c) { return c.homeAway === "away"; })[0] || cs[1];
      if (!home || !away) return;
      var H = home.team.abbreviation, A = away.team.abbreviation, hs = +home.score || 0, as = +away.score || 0;
      var g = seen[ev.id], first = !g;
      if (first) g = seen[ev.id] = { s: state, c: 0, b: [] };
      var period = +st.period || 0, clock = +st.clock || 0, url = "index.html?game=" + ev.id + "#live-strip";
      var nick = function (t) { return t.shortDisplayName || t.name || t.displayName || t.abbreviation; };
      var logoOf = function (c) { return c.team.abbreviation === "BOS" ? CELTICS_LOGO : (c.team.logo || teamLogo(c.team.abbreviation)); };
      var logos = {}; logos[A] = logoOf(away); logos[H] = logoOf(home);
      var pair = [logos[A], logos[H]];
      var lead = hs >= as ? home : away, trail = hs >= as ? away : home;
      var score = nick(lead.team) + " " + Math.max(hs, as) + ", " + nick(trail.team) + " " + Math.min(hs, as);
      var when = period > 4 ? periodName(period) : "Q" + period;
      var left = (st.displayClock || "") + " left in the " + (period > 4 ? periodName(period) : period === 4 ? "4th" : "Q" + period);
      var game = function (kind, tag, title, body, extra) {
        var m = { kind: kind, teams: [A, H], logos: logos, img: logos[H], imgs: pair, tag: ev.id + "-" + tag, title: title, body: body, url: url };
        for (var k in extra || {}) m[k] = extra[k];
        out.push(m);
      };
      // the underdog, worked out once before the game (or at the first look): the betting line, else the records
      if (g.dog === undefined && state !== "post") {
        g.dog = "";
        var od = (comp.odds || [])[0], mm = od && /^([A-Z]{2,4})\s+-(\d+(\.\d+)?)/.exec(od.details || "");
        if (mm && +mm[2] >= 7) g.dog = mm[1] === H ? A : mm[1] === A ? H : "";
        else { var ph = pct(home), pa = pct(away); if (ph && pa && Math.abs(ph.p - pa.p) >= 0.25) g.dog = ph.p < pa.p ? H : A; }
      }
      if (!first && g.s === "pre" && state === "in") game("tipoff", "tip", nick(away.team) + " at " + nick(home.team), "Tip-off");
      if (state === "in") {
        // deficits (the biggest each team has faced), for comebacks
        g.md = g.md || {}; g.md[A] = Math.max(g.md[A] || 0, hs - as); g.md[H] = Math.max(g.md[H] || 0, as - hs);
        g.cb = g.cb || [];
        [[away, as - hs], [home, hs - as]].forEach(function (x) {
          var t = x[0].team.abbreviation;
          if (x[1] > 0 && (g.md[t] || 0) >= 15 && g.cb.indexOf(t) < 0) {
            g.cb.push(t);
            game("upset", "cb-" + t, "Comeback: " + nick(x[0].team) + " erase a " + g.md[t] + "-point deficit", score + " · " + when + " " + (st.displayClock || ""), { img: logoOf(x[0]), imgs: null });
          }
        });
        // an underdog leading in the last 6 minutes
        if (g.dog && !g.up && period === 4 && clock <= 360) {
          var dog = g.dog === H ? home : away, ds = g.dog === H ? hs - as : as - hs;
          if (ds > 0) { g.up = 1; game("upset", "up", "Upset alert: " + nick(dog.team) + " lead", score + " · " + left, { img: logoOf(dog), imgs: null }); }
        }
        // overtime (each one)
        if (period > 4 && (g.ot || 4) < period) { g.ot = period; game("clutch", "ot" + period, (period === 5 ? "Overtime: " : periodName(period) + ": ") + nick(away.team) + " " + as + ", " + nick(home.team) + " " + hs, "Tied at the end of " + (period === 5 ? "regulation" : periodName(period - 1))); }
        else if (period > 4) g.ot = Math.max(g.ot || 0, period);
        // the last look before the end (to tell a late winner)
        var lp = comp.situation && comp.situation.lastPlay;
        g.lo = { p: period, cl: clock, hs: hs, as: as, lp: lp && lp.text ? String(lp.text).slice(0, 120) : "" };
      }
      if (!first && g.s !== "post" && state === "post") {
        var w = hs > as ? home : away, top = "";
        (w.leaders || []).forEach(function (L) { if (L.name === "points" && L.leaders && L.leaders[0]) top = " · " + L.leaders[0].athlete.displayName + " " + L.leaders[0].displayValue + " PTS"; });
        game("final", "final", score, "Final" + (period > 4 ? "/" + periodName(period) : "") + (g.dog && w.team.abbreviation === g.dog ? " · Upset" : "") + top, { img: logoOf(w) });
        // won in the final minute after trailing or tied at the last look
        var lo = g.lo;
        if (lo && lo.p >= 4 && lo.cl <= 60 && (w === home ? lo.hs <= lo.as : lo.as <= lo.hs))
          game("clutch", "win", "Clutch: " + nick(w.team) + " win it late", score + " · Final" + (period > 4 ? "/" + periodName(period) : "") + (lo.lp ? " · " + lo.lp : ""), { img: logoOf(w), imgs: null });
      }
      if (state === "in" && period === 4 && clock <= 300 && Math.abs(hs - as) <= 5 && (g.c || 0) < 4) {
        g.c = 4;
        game("close", "close", hs === as ? nick(away.team) + " " + as + ", " + nick(home.team) + " " + hs : score, left);
      }
      if (state !== "pre" && !(first && state === "post")) {
        [home, away].forEach(function (c) {
          var tri = c.team.abbreviation, ring = TEAM_RING[tri] || "#D4AF37", byCat = {};
          (c.leaders || []).forEach(function (L) { var t = L.leaders && L.leaders[0]; if (t && t.athlete) byCat[L.name] = t; });
          var face = function (ath) { var h = headOf(ath); return { img: h || logoOf(c), round: !!h, ring: ring }; };
          var player = function (kind, key, ath, title, body) {
            if (g.b.indexOf(key) >= 0) return;
            g.b.push(key);
            var f = face(ath);
            out.push({ kind: kind, teams: [tri], player: ath.displayName, img: f.img, round: f.round, ring: ring, tag: ev.id + "-" + key, title: title, body: body, url: url });
          };
          var tail = score + " · " + (state === "in" ? when + " " + (st.displayClock || "") : "Final");
          ["points", "rebounds", "assists"].forEach(function (cat) {
            var top = byCat[cat]; if (!top) return;
            var v = +top.value || parseFloat(top.displayValue) || 0, lab = { points: "PTS", rebounds: "REB", assists: "AST" }[cat];
            var bar = { points: v >= 50 ? 50 : 40, rebounds: 20, assists: 15 }[cat];
            if (v < bar) return;
            player("big", (top.athlete.id || top.athlete.displayName) + ":" + cat + ":" + bar, top.athlete, top.athlete.displayName + " · " + Math.round(v) + " " + lab, tail);
          });
          // triple-doubles: ESPN's top performer line lists the stats in double figures ("18 PTS, 12 REB, 12 AST")
          var r = byCat.rating;
          if (r && r.athlete) {
            var st3 = {}; String(r.displayValue || "").replace(/(\d+)\s+(PTS|REB|AST)/g, function (_, n, k) { st3[k] = +n; });
            var tens = ["PTS", "REB", "AST"].filter(function (k) { return (st3[k] || 0) >= 10; }), id = r.athlete.id || r.athlete.displayName;
            if (tens.length >= 3) player("stat", id + ":td", r.athlete, "Triple-double: " + r.athlete.displayName, (st3.PTS || 0) + " PTS, " + (st3.REB || 0) + " REB, " + (st3.AST || 0) + " AST \u00b7 " + tail);
            else if (tens.length === 2 && state === "in" && period >= 4) {
              var miss = ["PTS", "REB", "AST"].filter(function (k) { return tens.indexOf(k) < 0; })[0], cat2 = { PTS: "points", REB: "rebounds", AST: "assists" }[miss];
              var lead2 = byCat[cat2], v2 = lead2 && lead2.athlete && (lead2.athlete.id || lead2.athlete.displayName) === id ? (+lead2.value || parseFloat(lead2.displayValue) || 0) : 0;
              if (v2 >= 8) { st3[miss] = v2; player("stat", id + ":near", r.athlete, "Triple-double watch: " + r.athlete.displayName, (st3.PTS || 0) + " PTS, " + (st3.REB || 0) + " REB, " + (st3.AST || 0) + " AST · " + when + " " + (st.displayClock || "")); }
            }
          }
        });
      }
      g.s = state;
    });
    return out;
  }

  // ------------------------------------------------------------ the injury report and transactions (data/news.json)
  // news: { injuries: [{ id, name, team, status, note, img }], transactions: [{ date, team, desc }] }
  function detectNews(news, seen) {
    var out = [];
    if (!news) return out;
    var inj = {}, firstInj = !seen.inj;
    (news.injuries || []).forEach(function (x) { inj[x.id] = x; });
    if (!firstInj) {
      Object.keys(inj).forEach(function (id) {
        var x = inj[id], was = seen.inj[id];
        if (was === x.status) return;
        out.push({ kind: "injury", teams: [x.team], player: x.name, img: x.img || teamLogo(x.team), round: !!x.img, ring: TEAM_RING[x.team] || "#D4AF37",
          tag: "inj-" + id + "-" + x.status, title: x.name + " · " + x.status, body: (x.note || (was ? "Was " + was : "Added to the injury report")).slice(0, 170), url: "index.html#live-strip" });
      });
      Object.keys(seen.inj).forEach(function (id) {
        if (inj[id] || !seen.injx || !seen.injx[id]) return;
        var x = seen.injx[id];
        out.push({ kind: "injury", teams: [x.t], player: x.n, img: x.i || teamLogo(x.t), round: !!x.i, ring: TEAM_RING[x.t] || "#D4AF37",
          tag: "inj-" + id + "-off", title: x.n + " · off the injury report", body: "No longer listed (was " + seen.inj[id] + ")", url: "index.html#live-strip" });
      });
    }
    seen.inj = {}; seen.injx = {};
    Object.keys(inj).forEach(function (id) { var x = inj[id]; seen.inj[id] = x.status; seen.injx[id] = { n: x.name, t: x.team, i: x.img || "" }; });
    var firstTx = !seen.tx; seen.tx = seen.tx || [];
    (news.transactions || []).forEach(function (t) {
      var key = (t.date || "") + "|" + t.team + "|" + String(t.desc || "").slice(0, 60);
      if (seen.tx.indexOf(key) >= 0) return;
      seen.tx.push(key);
      if (firstTx) return;
      var tradeOnly = /trade|acquire/i.test(t.desc || "");
      out.push({ kind: "trade", teams: [t.team], player: t.desc, trade: tradeOnly, img: teamLogo(t.team), tag: "tx-" + key.slice(0, 40), title: (t.name || t.team) + (tradeOnly ? " · Trade" : " · Roster move"), body: String(t.desc || "").slice(0, 200), url: "index.html" });
    });
    seen.tx = seen.tx.slice(-300);
    return out;
  }

  // ------------------------------------------------------------ highlights (data/highlights-recent.json)
  function detectHighlights(hl, seen) {
    var out = [], games = (hl && hl.games) || {}, first = !seen.hl;
    seen.hl = seen.hl || [];
    Object.keys(games).forEach(function (gid) {
      var v = games[gid];
      if (seen.hl.indexOf(gid) >= 0) return;
      seen.hl.push(gid);
      if (first || !v.teams || v.teams.length !== 2) return;
      var d = String(v.day || ""), md = d.length === 8 ? +d.slice(4, 6) + "/" + +d.slice(6) : "";
      out.push({ kind: "highlights", teams: v.teams, img: teamLogo(v.teams[1]), imgs: [teamLogo(v.teams[0]), teamLogo(v.teams[1])], tag: "hl-" + gid,
        title: v.teams[0] + " vs " + v.teams[1] + (md ? " " + md : "") + " Highlights", body: "The highlights are up. Tap to watch.",
        url: "index.html?game=" + gid + (d.length === 8 ? "&day=" + d.slice(0, 4) + "-" + d.slice(4, 6) + "-" + d.slice(6) : "") + "#live-strip" });
    });
    seen.hl = seen.hl.slice(-400);
    return out;
  }

  // ------------------------------------------------------------ once a day: the morning recap and the evening reminder
  // due(seen, now): which of the two are due (each once a day, New York time)
  function due(seen, now) {
    var t = nyParts(now), out = [];
    if (t.hour >= 9 && t.hour < 12 && seen.recap !== t.day) { seen.recap = t.day; out.push("recap"); }
    if (t.hour >= 17 && t.hour < 20 && seen.remind !== t.day) { seen.remind = t.day; out.push("games"); }
    return out;
  }
  // last night's recap for one subscriber (sb: last night's scoreboard)
  function recapFor(sb, p) {
    var finals = [], best = null;
    (sb.events || []).forEach(function (ev) {
      var comp = (ev.competitions || [])[0]; if (!comp || ((comp.status || {}).type || {}).state !== "post") return;
      var cs = comp.competitors || []; if (cs.length < 2) return;
      var w = +cs[0].score >= +cs[1].score ? cs[0] : cs[1], l = w === cs[0] ? cs[1] : cs[0];
      var nk = function (c) { return c.team.shortDisplayName || c.team.name || c.team.abbreviation; };
      finals.push({ teams: [cs[0].team.abbreviation, cs[1].team.abbreviation], w: w.team.abbreviation, text: nk(w) + " " + w.score + ", " + nk(l) + " " + l.score });
      cs.forEach(function (c) {
        (c.leaders || []).forEach(function (L) {
          var t = L.name === "points" && L.leaders && L.leaders[0];
          if (t && t.athlete && (!best || (+t.value || 0) > best.v)) best = { v: +t.value || parseFloat(t.displayValue) || 0, name: t.athlete.displayName, img: headOf(t.athlete), tri: c.team.abbreviation };
        });
      });
    });
    if (!finals.length) return null;
    var mine = p.teams.length ? finals.filter(function (f) { return f.teams.some(function (t) { return p.teams.indexOf(t) >= 0; }); }) : [];
    var lines = (mine.length ? mine : finals.slice(0, 3)).map(function (f) { return f.text; });
    var body = lines.join(" · ") + (best ? " · Top: " + best.name + " " + Math.round(best.v) + " PTS" : "");
    var one = p.teams.length === 1 ? p.teams[0] : "";
    return { kind: "recap", teams: [], title: "Morning recap · " + finals.length + " game" + (finals.length === 1 ? "" : "s") + " last night", body: body.slice(0, 230), tag: "recap", url: "index.html#live-strip",
      img: one ? teamLogo(one) : best && best.img ? best.img : SITE_LOGO, round: !one && !!(best && best.img), ring: best ? TEAM_RING[best.tri] : "" };
  }
  function reminder(sb) {
    var n = (sb.events || []).filter(function (ev) { var c = (ev.competitions || [])[0]; return c && ((c.status || {}).type || {}).state === "pre"; }).length;
    if (!n) return null;
    return { kind: "games", teams: [], title: "Today's Play is ready", body: n + " game" + (n === 1 ? "" : "s") + " tonight: draw your plays, then try the 82-0 Draft and the GM Challenge.", tag: "games", url: "todays-play.html", img: SITE_LOGO };
  }

  function allowed(m, p) {
    if (p.types[m.kind] === false) return false;
    if (m.kind === "recap" || m.kind === "games") return true;
    if (m.kind === "injury") return !!(p.teams.length || p.players.length) && wants(p, m.teams, m.player);
    if (m.kind === "trade" && !p.teams.length && !p.players.length) return !!m.trade;
    return wants(p, m.teams, m.player);
  }
  // a game alert shows the logo of the team the subscriber follows when they follow just one of the two; else both
  function pictureFor(m, p) {
    if (m.logos && p && p.teams) {
      var f = m.teams.filter(function (t) { return p.teams.indexOf(t) >= 0; });
      if (f.length === 1 && m.logos[f[0]]) return { img: m.logos[f[0]], imgs: null };
    }
    return { img: m.img || "", imgs: m.imgs || null };
  }

  root.BAAlerts = { KINDS: KINDS, TEAMS: TEAMS, TEAM_RING: TEAM_RING, CELTICS_LOGO: CELTICS_LOGO, teamLogo: teamLogo, gameDay: gameDay, nyParts: nyParts,
    detect: detect, detectNews: detectNews, detectHighlights: detectHighlights, due: due, recapFor: recapFor, reminder: reminder,
    allowed: allowed, pictureFor: pictureFor, wants: wants };
})(typeof globalThis !== "undefined" ? globalThis : this);
