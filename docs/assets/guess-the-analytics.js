/* Guess the Analytics: guessing games built on real numbers, each answer revealed with a chart.

   THE DAILY TEN (the same ten rounds for everyone, on the leaderboard; 10 points a round, the closest-guess round
   scores by how close you are):
     Higher or lower   which of two players has more of a stat (points, threes, assists, rebounds, stocks, FG%)
     Team showdown     which team had the better offensive / defensive / net rating, pace, eFG%, rebounding, turnovers
     Lineup lab        which five-man lineup had the better net / offensive / defensive rating or +/-
     Whose shots?      a player's shot chart by zone, four names: pick his
     Whose numbers?    a player's stat profile, four names: pick his
     Which team?       a team's profile (where it shoots from, its four factors), four teams: pick it
     Over or under     is his number over or under the line?
     Closest guess     slide to your guess of a team's number; points for being close
   PRACTICE: any one game, as many rounds as you like (not on the leaderboard).

   Data: ESPN (this season's players and teams), the NBA's stats for 2025-26 lineups, shot zones and team ratings
   (data/lineups.json and data/analytics.json). Pictures are loaded small and ahead of time, so rounds show at once. */
(function () {
  "use strict";
  var B = window.BAG, root = document.getElementById("ga-app");
  if (!B || !root) return;
  var GAME = "guess-the-analytics", DAY = B.day(), N = 10;
  var MODES = {
    player: { name: "Higher or lower", desc: "Which player has more?" },
    team: { name: "Team showdown", desc: "Which team was better at it?" },
    lineup: { name: "Lineup lab", desc: "Which five won its minutes?" },
    shots: { name: "Whose shots?", desc: "A shot chart, four names" },
    whose: { name: "Whose numbers?", desc: "A stat line, four names" },
    which: { name: "Which team?", desc: "A team's profile, four teams" },
    ou: { name: "Over or under", desc: "Is he over or under the line?" },
    close: { name: "Closest guess", desc: "Slide to your guess" }
  };
  var DAILY = ["player", "team", "lineup", "shots", "whose", "which", "ou", "player", "close", "lineup"];
  var PSTATS = [["pts", "points per game", ""], ["tpm", "threes made per game", ""], ["ast", "assists per game", ""], ["reb", "rebounds per game", ""], ["stocks", "steals + blocks per game", ""], ["fgp", "field goal %", "%"], ["tpp", "3-point %", "%"]];
  var TSTATS = [["off", "offensive rating", true, ""], ["def", "defensive rating", false, ""], ["net", "net rating", true, ""], ["pace", "pace (possessions per 48)", true, ""], ["efg", "effective FG%", true, "%"], ["oreb", "offensive rebound %", true, "%"], ["tov", "turnover %", false, "%"], ["ast", "assist %", true, "%"]];
  var LSTATS = [["net", "net rating", true, ""], ["off", "offensive rating", true, ""], ["def", "defensive rating", false, ""], ["pm", "+/-", true, ""], ["ts", "true shooting %", true, "%"]];
  var ZN = ["At the rim", "Paint", "Mid-range", "Left corner 3", "Right corner 3", "Above the break 3"];
  var TRI_NAME = {}; Object.keys(B.names).forEach(function (k) { TRI_NAME[k] = B.names[k]; });

  // ------------------------------------------------------------ rounds
  var D = null;
  function load() {
    return Promise.all([B.players().catch(function () { return []; }), B.analytics(), B.lineups().catch(function () { return []; })]).then(function (r) {
      var pl = r[0].filter(function (p) { return p.gp >= Math.max(2, Math.min(15, maxGp(r[0]) * 0.5)) && p.min >= 22; });
      pl.forEach(function (p) { p.stocks = p.stl + p.blk; });
      var A = r[1], teams = Object.keys(A.teams).map(function (t) { var x = A.teams[t]; x.tri = t; return x; });
      var lz = [0, 1, 2, 3, 4, 5].map(function (i) { var m = 0, a = 0; teams.forEach(function (t) { m += t.zones[i][0]; a += t.zones[i][1]; }); return m / a; });
      D = { players: pl, teams: teams, shooters: A.shooters, lineups: r[2], league: lz };
    });
  }
  function maxGp(list) { return list.reduce(function (m, p) { return Math.max(m, p.gp); }, 0); }
  function make(kind, rnd) {
    var pick = function (a) { return a[Math.floor(rnd() * a.length)]; }, guard = 0;
    if (kind === "lineup" && D.lineups.length < 4) kind = "player";
    if ((kind === "player" || kind === "whose" || kind === "ou") && D.players.length < 8) kind = "team";
    if (kind === "player") {
      var s = pick(PSTATS), a = pick(D.players), b = pick(D.players);
      while ((b === a || Math.abs(a[s[0]] - b[s[0]]) < (s[2] ? 1.5 : 0.4) || (s[0] === "tpp" && (a.tpa < 2.5 || b.tpa < 2.5))) && guard++ < 80) { b = pick(D.players); if (s[0] === "tpp" && a.tpa < 2.5) a = pick(D.players); }
      return { kind: kind, q: "Who has more " + s[1] + "?", sub: "This season", opts: [card(a), card(b)], vals: [a[s[0]], b[s[0]]], high: true, unit: s[2], label: s[1] };
    }
    if (kind === "team") {
      var t = pick(TSTATS), x = pick(D.teams), y = pick(D.teams);
      while ((y === x || Math.abs(x[t[0]] - y[t[0]]) < 0.6) && guard++ < 80) y = pick(D.teams);
      return { kind: kind, q: (t[2] ? "Which team had the better " : "Which team had the lower ") + t[1] + "?", sub: "2025-26", opts: [tcard(x), tcard(y)], vals: [x[t[0]], y[t[0]]], high: t[2], unit: t[3], label: t[1] };
    }
    if (kind === "lineup") {
      var ls = pick(LSTATS), l1 = pick(D.lineups), l2 = pick(D.lineups);
      while ((l2 === l1 || Math.abs(l1[ls[0]] - l2[ls[0]]) < 2) && guard++ < 80) l2 = pick(D.lineups);
      return { kind: kind, q: "Which lineup had the better " + ls[1] + "?", sub: "2025-26, five-man lineups", opts: [lcard(l1), lcard(l2)], vals: [l1[ls[0]], l2[ls[0]]], high: ls[2], unit: ls[3], label: ls[1] };
    }
    if (kind === "shots") {
      var pool = D.shooters, who = pick(pool), opts = [who];
      while (opts.length < 4 && guard++ < 80) { var o = pick(pool); if (opts.indexOf(o) < 0) opts.push(o); }
      shuffle(opts, rnd);
      return { kind: kind, q: "Whose shot chart is this?", sub: "2025-26, every shot by zone", who: who, choices: opts.map(scard), answer: opts.indexOf(who) };
    }
    if (kind === "whose") {
      var w = pick(D.players), op = [w];
      while (op.length < 4 && guard++ < 80) { var c = pick(D.players); if (op.indexOf(c) < 0) op.push(c); }
      shuffle(op, rnd);
      return { kind: kind, q: "Whose numbers are these?", sub: "This season, per game", who: w, choices: op.map(card), answer: op.indexOf(w) };
    }
    if (kind === "which") {
      var tm = pick(D.teams), ot = [tm];
      while (ot.length < 4 && guard++ < 80) { var u = pick(D.teams); if (ot.indexOf(u) < 0) ot.push(u); }
      shuffle(ot, rnd);
      return { kind: kind, q: "Which team is this?", sub: "2025-26: where it shot from and its four factors", who: tm, choices: ot.map(tcard), answer: ot.indexOf(tm) };
    }
    if (kind === "ou") {
      var st = pick(PSTATS.slice(0, 5)), p = pick(D.players), v = p[st[0]], line = Math.round((v + (rnd() < 0.5 ? -1 : 1) * Math.max(0.5, v * (0.08 + rnd() * 0.14))) * 2) / 2;
      if (line === v) line += 0.5;
      return { kind: kind, q: "Over or under " + line.toFixed(1) + " " + st[1] + "?", sub: "This season", p: p, line: line, val: v, label: st[1], opts: [card(p)] };
    }
    var cs = pick([["net", "net rating", -15, 15, 0.1], ["off", "offensive rating", 105, 125, 0.1], ["def", "defensive rating", 104, 124, 0.1], ["pace", "pace", 94, 106, 0.1]]), team = pick(D.teams);
    return { kind: "close", q: "What was the " + B.esc(team.name) + "’ " + cs[1] + "?", sub: "2025-26 · slide to your guess", team: team, stat: cs, val: team[cs[0]] };
  }
  function shuffle(a, rnd) { for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(rnd() * (i + 1)), t = a[i]; a[i] = a[j]; a[j] = t; } }
  function card(p) { return { name: p.name, sub: p.team + (p.pos ? " · " + p.pos : ""), img: B.face(p.id, 140), round: true }; }
  function tcard(t) { return { name: t.name, sub: t.w + "-" + t.l, img: B.logo(t.tri), round: false }; }
  function lcard(l) { return { name: l.names.join(" · "), sub: l.team + " · " + Math.round(l.min) + " min", img: B.logo(l.team), faces: (l.ids || []).map(B.nbaFace), round: false }; }
  function scard(s) { return { name: s.name, sub: s.team, img: B.nbaFace(s.id), round: true }; }
  function imagesOf(r) {
    var out = [];
    (r.opts || []).concat(r.choices || []).forEach(function (o) { out.push(o.img); (o.faces || []).forEach(function (f) { out.push(f); }); });
    return out;
  }

  // ------------------------------------------------------------ charts
  function bars(r, win) {
    var vals = r.vals, max = Math.max(Math.abs(vals[0]), Math.abs(vals[1])) || 1, min = Math.min(vals[0], vals[1]);
    var scale = function (v) { return r.label.indexOf("rating") >= 0 && min > 50 ? 8 + (v - min * 0.97) / (max - min * 0.97) * 92 : Math.max(4, Math.abs(v) / max * 100); };
    return '<div class="ga-bars">' + r.opts.map(function (o, i) {
      return '<div class="ga-bar' + (i === win ? " win" : "") + '"><span class="n">' + B.esc(o.name.split(" · ")[0].length > 18 ? o.sub : o.name) + '</span><i><b style="width:0" data-w="' + scale(vals[i]).toFixed(1) + '"></b></i><span class="v">' + (vals[i] > 0 && r.label === "+/-" || (r.label === "net rating" && vals[i] > 0) ? "+" : "") + vals[i].toFixed(1) + (r.unit || "") + "</span></div>";
    }).join("") + "</div>";
  }
  // a half court split into the six zones, each coloured by how its FG% compares with the league's
  function shotChart(zones, hide) {
    var col = function (i) { var a = zones[i][1]; if (!a) return "#26231e"; var d = zones[i][0] / a - D.league[i]; return d > 0.04 ? "#c9473b" : d > 0.015 ? "#d97b57" : d > -0.015 ? "#a99a72" : d > -0.04 ? "#5f8fb3" : "#3c6b9c"; };
    var vol = zones.reduce(function (s, z) { return s + z[1]; }, 0) || 1;
    var lab = function (i, x, y) { var z = zones[i]; return '<g class="ga-zl"><text x="' + x + '" y="' + y + '">' + (z[1] ? Math.round(100 * z[0] / z[1]) + "%" : "–") + '</text><text class="s" x="' + x + '" y="' + (y + 15) + '">' + z[0] + "/" + z[1] + " · " + Math.round(100 * z[1] / vol) + "% of shots</text></g>"; };
    return '<svg class="ga-shots" viewBox="0 0 500 360" role="img" aria-label="Shot chart by zone">' +
      '<rect width="500" height="360" fill="' + col(5) + '"/>' +
      '<path d="M30 0 V140 A237.5 237.5 0 0 0 470 140 V0 Z" fill="' + col(2) + '"/>' +
      '<rect x="170" y="0" width="160" height="190" fill="' + col(1) + '"/>' +
      '<path d="M210 0 V52.5 A40 40 0 0 0 290 52.5 V0 Z" fill="' + col(0) + '"/>' +
      '<rect x="0" y="0" width="30" height="140" fill="' + col(3) + '"/><rect x="470" y="0" width="30" height="140" fill="' + col(4) + '"/>' +
      '<g fill="none" stroke="rgba(10,10,10,.75)" stroke-width="2.5"><path d="M30 0 V140 A237.5 237.5 0 0 0 470 140 V0"/><rect x="170" y="0" width="160" height="190"/><path d="M210 0 V52.5 A40 40 0 0 0 290 52.5 V0"/><circle cx="250" cy="190" r="60"/></g>' +
      '<circle cx="250" cy="52.5" r="7.5" fill="none" stroke="#ff6a2e" stroke-width="2.5"/><line x1="220" y1="40" x2="280" y2="40" stroke="#eee" stroke-width="3"/>' +
      lab(0, 250, 84) + lab(1, 250, 150) + lab(2, 250, 245) + lab(3, 15, 70).replace(/x="15"/g, 'x="15" transform="rotate(-90 15 70)"') + lab(4, 485, 70).replace(/x="485"/g, 'x="485" transform="rotate(90 485 70)"') + lab(5, 250, 330) +
      "</svg>" + (hide ? "" : "") +
      '<div class="ga-key"><span style="background:#3c6b9c"></span>cold<span style="background:#a99a72"></span>league average<span style="background:#c9473b"></span>hot</div>';
  }
  function profile(p) {
    var axes = [["PTS", p.pts / 32], ["REB", p.reb / 13], ["AST", p.ast / 10], ["3PM", p.tpm / 4.5], ["STL", p.stl / 2], ["BLK", p.blk / 2.5]];
    var cx = 130, cy = 118, R = 88, ang = function (i) { return -Math.PI / 2 + i * Math.PI / 3; };
    var poly = function (k) { return axes.map(function (_, i) { return (cx + Math.cos(ang(i)) * R * k).toFixed(1) + "," + (cy + Math.sin(ang(i)) * R * k).toFixed(1); }).join(" "); };
    var pts = axes.map(function (a, i) { var r = R * Math.max(0.06, Math.min(1, a[1])); return (cx + Math.cos(ang(i)) * r).toFixed(1) + "," + (cy + Math.sin(ang(i)) * r).toFixed(1); }).join(" ");
    return '<svg class="ga-radar" viewBox="0 0 260 240">' + [0.33, 0.66, 1].map(function (k) { return '<polygon points="' + poly(k) + '" fill="none" stroke="#34302a"/>'; }).join("") +
      '<polygon points="' + pts + '" fill="rgba(212,175,55,.28)" stroke="#F5D370" stroke-width="2"/>' +
      axes.map(function (a, i) { return '<text x="' + (cx + Math.cos(ang(i)) * (R + 17)).toFixed(1) + '" y="' + (cy + Math.sin(ang(i)) * (R + 17) + 4).toFixed(1) + '" text-anchor="middle" fill="#a9a39a" font-size="11" font-family="Arial">' + a[0] + "</text>"; }).join("") + "</svg>" +
      '<div class="ga-line">' + [["PTS", p.pts], ["REB", p.reb], ["AST", p.ast], ["3PM", p.tpm], ["STL", p.stl], ["BLK", p.blk], ["FG%", p.fgp]].map(function (k) { return "<span><b>" + k[1].toFixed(1) + "</b>" + k[0] + "</span>"; }).join("") + "</div>";
  }
  function teamProfile(t) {
    var tot = t.zones.reduce(function (s, z) { return s + z[1]; }, 0);
    var f = [["eFG%", t.efg, 50, 58], ["TOV%", t.tov, 12, 17, true], ["OREB%", t.oreb, 24, 40], ["Pace", t.pace, 95, 105], ["Off Rtg", t.off, 106, 122], ["Def Rtg", t.def, 106, 122, true]];
    return '<div class="ga-tp"><div class="ga-mix">' + t.zones.map(function (z, i) { return '<span style="flex:' + z[1] + '" title="' + ZN[i] + '"><b>' + Math.round(100 * z[1] / tot) + "%</b>" + ZN[i].replace("Above the break 3", "Above-break 3").replace(" corner 3", " corner") + "</span>"; }).join("") + "</div>" +
      '<div class="ga-ff">' + f.map(function (x) { var k = Math.max(0.05, Math.min(1, (x[1] - x[2]) / (x[3] - x[2]))); return '<div><span>' + x[0] + '</span><i><b style="width:' + (k * 100).toFixed(0) + '%"></b></i><em>' + x[1].toFixed(1) + "</em></div>"; }).join("") + "</div></div>";
  }

  // ------------------------------------------------------------ the game
  var rounds = [], i = 0, score = 0, marks = [], practice = null;
  function optHTML(o, k, big) {
    return '<button type="button" class="ga-opt' + (big ? " big" : "") + '" data-k="' + k + '">' +
      (o.faces && o.faces.length ? '<span class="ga-five">' + o.faces.map(function (f) { return '<img alt="" src="' + B.esc(f) + '" onerror="this.style.visibility=\'hidden\'">'; }).join("") + "</span>" :
        '<img class="' + (o.round ? "face" : "logo") + '" alt="" src="' + B.esc(o.img) + '" onerror="this.style.visibility=\'hidden\'">') +
      "<b>" + B.esc(o.name) + "</b><span>" + B.esc(o.sub) + "</span></button>";
  }
  function head(r) {
    var M = MODES[r.kind];
    return '<div class="ga-top"><span>' + (practice ? "Practice · " + B.esc(M.name) : "Round " + (i + 1) + " of " + rounds.length + " · " + B.esc(M.name)) + '</span><span>Score <b>' + score + "</b></span></div>" +
      '<div class="ga-prog">' + (practice ? "" : rounds.map(function (_, k) { return '<i class="' + (k < marks.length ? (marks[k] >= 10 ? "ok" : marks[k] > 0 ? "part" : "no") : k === i ? "now" : "") + '"></i>'; }).join("")) + "</div>" +
      '<h3 class="ga-q">' + r.q + '</h3><p class="ga-sub">' + B.esc(r.sub) + "</p>";
  }
  function show() {
    if (!practice && i >= rounds.length) return finish();
    var r = practice ? make(practice, Math.random) : rounds[i];
    if (practice) rounds[i] = r;
    if (!practice && rounds[i + 1]) B.preload(imagesOf(rounds[i + 1]));
    var html = head(r);
    if (r.kind === "player" || r.kind === "team" || r.kind === "lineup") {
      html += '<div class="ga-pair' + (r.kind === "lineup" ? " lu" : "") + '">' + r.opts.map(function (o, k) { return optHTML(o, k, true); }).join('<span class="ga-vs">vs</span>') + "</div>";
    } else if (r.kind === "ou") {
      html += '<div class="ga-one">' + optHTML(r.opts[0], 0, true) + '</div><div class="ga-ou"><button type="button" class="gm-btn" data-ou="1">Over</button><button type="button" class="gm-btn ghost" data-ou="0">Under</button></div>';
    } else if (r.kind === "close") {
      var s = r.stat;
      html += '<div class="ga-one"><img class="logo big" alt="" src="' + B.esc(B.logo(r.team.tri)) + '"></div><div class="ga-slide"><output>' + ((s[2] + s[3]) / 2).toFixed(1) + '</output><input type="range" min="' + s[2] + '" max="' + s[3] + '" step="0.1" value="' + ((s[2] + s[3]) / 2) + '" aria-label="Your guess"><div class="ga-ends"><span>' + s[2] + "</span><span>" + s[3] + '</span></div><button type="button" class="gm-btn ga-lock">Lock it in</button></div>';
    } else {
      html += '<div class="ga-clue">' + (r.kind === "shots" ? shotChart(r.who.zones) : r.kind === "whose" ? profile(r.who) : teamProfile(r.who)) + "</div>" +
        '<div class="ga-opts">' + r.choices.map(function (o, k) { return optHTML(o, k); }).join("") + "</div>";
    }
    root.innerHTML = html + '<div class="ga-after"></div>';
    if (r.kind === "player" || r.kind === "team" || r.kind === "lineup") {
      var right = (r.high ? r.vals[0] >= r.vals[1] : r.vals[0] <= r.vals[1]) ? 0 : 1;
      root.querySelectorAll(".ga-opt").forEach(function (b) { b.addEventListener("click", function () { answer(+b.getAttribute("data-k") === right ? 10 : 0, b, right, bars(r, right)); }); });
    } else if (r.kind === "ou") {
      var over = r.val > r.line;
      root.querySelectorAll("[data-ou]").forEach(function (b) { b.addEventListener("click", function () { var ok = (b.getAttribute("data-ou") === "1") === over; root.querySelectorAll("[data-ou]").forEach(function (x) { x.disabled = true; }); answer(ok ? 10 : 0, null, -1, '<p class="ga-big">' + r.val.toFixed(1) + '<span>' + B.esc(r.label) + " · the line was " + r.line.toFixed(1) + "</span></p>"); }); });
    } else if (r.kind === "close") {
      var inp = root.querySelector(".ga-slide input"), out = root.querySelector(".ga-slide output");
      inp.addEventListener("input", function () { out.textContent = (+inp.value).toFixed(1); });
      root.querySelector(".ga-lock").addEventListener("click", function () {
        inp.disabled = true; this.disabled = true;
        var g = +inp.value, span = r.stat[3] - r.stat[2], off = Math.abs(g - r.val), pts = Math.max(0, Math.round(10 * (1 - off / (span * 0.3))));
        answer(pts, null, -1, '<p class="ga-big">' + r.val.toFixed(1) + "<span>your guess " + g.toFixed(1) + " · off by " + off.toFixed(1) + "</span></p>" + closeBar(r, g));
      });
    } else {
      root.querySelectorAll(".ga-opt").forEach(function (b) { b.addEventListener("click", function () { var k = +b.getAttribute("data-k"); answer(k === r.answer ? 10 : 0, b, r.answer, "<p>" + B.esc(r.choices[r.answer].name) + " (" + B.esc(r.choices[r.answer].sub) + ").</p>"); }); });
    }
  }
  function closeBar(r, g) {
    var s = r.stat, pos = function (v) { return Math.max(0, Math.min(100, (v - s[2]) / (s[3] - s[2]) * 100)).toFixed(1) + "%"; };
    var others = D.teams.map(function (t) { return '<i class="o" style="left:' + pos(t[s[0]]) + '"></i>'; }).join("");
    return '<div class="ga-scale">' + others + '<i class="you" style="left:' + pos(g) + '"><em>You</em></i><i class="real" style="left:' + pos(r.val) + '"><em>' + B.esc(r.team.tri) + "</em></i></div><p class=\"gm-note\">Every team's " + B.esc(s[1]) + " on the line.</p>";
  }
  function answer(pts, btn, rightIdx, reveal) {
    root.querySelectorAll(".ga-opt").forEach(function (b, k) { b.disabled = true; if (k === rightIdx) b.classList.add("right"); });
    if (btn && pts < 10) btn.classList.add("wrong");
    score += pts; marks.push(pts);
    var after = root.querySelector(".ga-after");
    after.innerHTML = '<p class="ga-verdict ' + (pts >= 10 ? "ok" : pts > 0 ? "part" : "no") + '">' + (pts >= 10 ? "Right." : pts > 0 ? "+" + pts + ", close." : "Not this time.") + "</p>" + reveal +
      '<div class="gm-row"><button type="button" class="gm-btn ga-next">' + (practice ? "Next round" : i < rounds.length - 1 ? "Next" : "See your score") + "</button>" + (practice ? '<button type="button" class="gm-btn ghost ga-menu">All games</button>' : "") + "</div>";
    requestAnimationFrame(function () { setTimeout(function () { after.querySelectorAll(".ga-bar b").forEach(function (b) { b.style.width = b.getAttribute("data-w") + "%"; }); }, 30); });
    after.querySelector(".ga-next").addEventListener("click", function () { i++; show(); });
    var m = after.querySelector(".ga-menu"); if (m) m.addEventListener("click", menu);
    after.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  function finish() {
    var best = B.store("ga2:" + DAY); if (best == null || score > best) B.store("ga2:" + DAY, score);
    root.innerHTML = '<div class="tp-score big">' + score + "<span>out of 100</span></div>" +
      '<div class="ga-dots">' + marks.map(function (a, k) { return '<i class="' + (a >= 10 ? "ok" : a > 0 ? "part" : "no") + '" title="' + MODES[rounds[k].kind].name + '"></i>'; }).join("") + "</div>" +
      '<div class="gm-row c"><button type="button" class="gm-btn ga-post">Post to the leaderboard</button><button type="button" class="gm-btn ghost ga-menu">More games</button></div><p class="gm-note ga-saved"></p>';
    root.querySelector(".ga-menu").addEventListener("click", menu);
    root.querySelector(".ga-post").addEventListener("click", function () {
      this.disabled = true;
      B.askName().then(function (n) { return B.submit(GAME, DAY, { name: n, score: score, extra: { right: marks.filter(function (m) { return m >= 10; }).length + "/" + marks.length }, detail: { marks: marks } }); })
        .then(function (res) { root.querySelector(".ga-saved").textContent = res.rank ? "Posted: #" + res.rank + " today." : "Saved."; board(); });
    });
  }
  function menu() {
    practice = null;
    var best = B.store("ga2:" + DAY);
    root.innerHTML = '<div class="ga-menuwrap"><div class="ga-daily"><span class="gm-k">The daily ten</span><b>Ten rounds, every game mixed in</b><p>The same rounds for everyone today, on the leaderboard.' + (best != null ? " Your best today: <b>" + best + "</b>." : "") + '</p><button type="button" class="gm-btn ga-start">' + (best != null ? "Play again" : "Play today’s ten") + "</button></div>" +
      '<span class="gm-k">Or practice one game</span><div class="ga-modes">' + Object.keys(MODES).map(function (k) { return '<button type="button" class="ga-mode" data-m="' + k + '"><b>' + B.esc(MODES[k].name) + "</b><span>" + B.esc(MODES[k].desc) + "</span></button>"; }).join("") + "</div></div>";
    root.querySelector(".ga-start").addEventListener("click", function () { var rnd = B.seeded("ga2" + DAY); rounds = DAILY.map(function (k) { return make(k, rnd); }); B.preload(imagesOf(rounds[0]).concat(imagesOf(rounds[1]))); i = 0; score = 0; marks = []; show(); });
    root.querySelectorAll(".ga-mode").forEach(function (b) { b.addEventListener("click", function () { practice = b.getAttribute("data-m"); rounds = []; i = 0; score = 0; marks = []; show(); }); });
  }
  function board() { B.renderBoard(document.getElementById("ga-board"), GAME, DAY, { cols: [["right", "Right"]], format: function (s) { return String(Math.round(s)); } }); }

  root.innerHTML = '<p class="gm-empty">Loading today&rsquo;s rounds…</p>';
  load().then(function () {
    var rnd = B.seeded("ga2" + DAY), first = DAILY.slice(0, 3).map(function (k) { return make(k, rnd); });
    first.forEach(function (r) { B.preload(imagesOf(r)); });             // the first rounds' pictures start loading now
    menu();
  }).catch(function () { root.innerHTML = '<p class="gm-empty">Couldn&rsquo;t load today&rsquo;s rounds right now.</p>'; });
  board();
})();
