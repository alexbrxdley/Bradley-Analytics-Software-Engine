/* 82-0 Fantasy Draft, after 82-0.com: eight picks. Each pick spins a random team and a random season (1996-97 to
   2025-26); you draft one player off that team's roster that season, into an open spot: five starters (PG, SG, SF, PF, C)
   and three bench spots (a PG/SG, a SG/SF/PF and a PF/C). A player goes where he played (a listed SF can also play SG or PF, and so on): his position
   buttons put him there, and a drafted player can be dragged to any other open spot he can play (or swapped with one who can). One respin of the team and one of the season per
   draft. Every spin is random (two slot reels, the team and the season, spin and land); the daily leaderboard keeps
   each player's best record of the day.

   The record: each player's value is his points (era-adjusted: scoring is worth more in the low-scoring years around
   2000 than in today's), rebounds, assists, steals and blocks per game that season, the starters at full weight and
   the bench at 70%. The team's total turns into wins out of 82 (an average NBA eight is about 160, so 41-41; every 3
   more is about a win, and 82-0 takes eight near-MVP seasons), plus or minus the fit of the eight: a playmaker, a rim
   protector, rebounding, a go-to scorer, defensive hands, and not too many players who need the ball.

   Stats: ESPN, by season. */
(function () {
  "use strict";
  var B = window.BAG, root = document.getElementById("fd-app");
  if (!B || !root) return;
  var GAME = "fantasy-draft", DAY = B.day(), FIRST = 1997, LAST = 2026;
  // [key, name, weight, positions it takes, label]
  var SLOTS = [["PG", "Point guard", 1, ["PG"], "PG"], ["SG", "Shooting guard", 1, ["SG"], "SG"], ["SF", "Small forward", 1, ["SF"], "SF"], ["PF", "Power forward", 1, ["PF"], "PF"], ["C", "Center", 1, ["C"], "C"],
    ["B1", "Bench guard", 0.7, ["PG", "SG"], "PG/SG"], ["B2", "Bench wing", 0.7, ["SG", "SF", "PF"], "SG/SF/PF"], ["B3", "Bench big", 0.7, ["PF", "C"], "PF/C"]];
  // the positions a player played, from ESPN's listing (G: either guard spot, F: either forward spot, and so on)
  var POS = { PG: ["PG"], SG: ["SG"], SF: ["SF"], PF: ["PF"], C: ["C"], G: ["PG", "SG"], F: ["SF", "PF"], GF: ["SG", "SF"], FC: ["PF", "C"], CF: ["PF", "C"], FG: ["SG", "SF"] };
  // most players play the spots next to their listed one too (Tatum and Pierce at SF or PF, a combo guard at either
  // guard spot, a big at PF or C): each listed spot also opens its neighbors
  var NEAR = { PG: ["PG", "SG"], SG: ["SG", "PG", "SF"], SF: ["SF", "SG", "PF"], PF: ["PF", "SF", "C"], C: ["C", "PF"] };
  var ORDER = ["PG", "SG", "SF", "PF", "C"];
  // where each player actually played, season by season (data/positions.json: NBA.com's G/F/C listing narrowed by his
  // height and box score -- Wembanyama C, Tatum and Pierce SF/PF, Paul PG...). ESPN's coarse listing is only the fallback.
  var POSTAB = null;
  var posReady = B.getJSON ? B.getJSON("data/positions.json").then(function (d) { POSTAB = d; }).catch(function () {}) :
    fetch("data/positions.json").then(function (r) { return r.json(); }).then(function (d) { POSTAB = d; }).catch(function () {});
  function nkey(n) {
    return String(n || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/-/g, " ").replace(/[^a-z ]/g, "")
      .trim().replace(/\s+(jr|sr|ii|iii|iv)$/, "").replace(/\s+/g, " ");
  }
  function tablePos(p, y) {
    var e = POSTAB && POSTAB[nkey(p && p.name)];
    if (!e) return null;
    if (typeof e === "string") return e.split("/");
    var best = null;
    Object.keys(e).sort().forEach(function (k) { if (!best || +k <= y) best = e[k]; });
    return best ? best.split("/") : null;
  }
  function positions(p, y) {
    var t = tablePos(p, y || (p && p.year) || (state.spin && state.spin.year));
    if (t) return ORDER.filter(function (x) { return t.indexOf(x) >= 0; });
    var k = String((p && p.pos) || "").toUpperCase().replace(/[^A-Z]/g, ""), base = POS[k] || (k ? [] : ["PG", "SG", "SF", "PF"]), out = {};
    base.forEach(function (x) { out[x] = 1; });
    return ORDER.filter(function (x) { return out[x]; });
  }
  function posLabel(p, y) { return positions(p, y).join("/") || (p && p.pos) || "–"; }
  function canPlay(i, p) { return SLOTS[i][3].some(function (x) { return positions(p).indexOf(x) >= 0; }); }
  function season(y) { return (y - 1) + "-" + String(y).slice(2); }
  // league scoring per team per game, by season (the year it ended): an approximate table for the era adjustment
  var PPG = { 1997: 96.9, 1998: 95.6, 1999: 91.6, 2000: 97.5, 2001: 94.8, 2002: 95.5, 2003: 95.1, 2004: 93.4, 2005: 97.2, 2006: 97.0, 2007: 98.7,
    2008: 99.9, 2009: 100.0, 2010: 100.4, 2011: 99.6, 2012: 96.3, 2013: 98.1, 2014: 101.0, 2015: 100.0, 2016: 102.7, 2017: 105.6, 2018: 106.3,
    2019: 111.2, 2020: 111.8, 2021: 112.1, 2022: 110.6, 2023: 114.7, 2024: 114.2, 2025: 113.8, 2026: 114.5 };
  function era(y) { return 104 / (PPG[y] || 104); }
  function apts(p, y) { return p.pts * era(y || p.year); }
  function line(p, y) { return apts(p, y) + p.reb + p.ast + p.stl + p.blk; }
  var AVG = 160 / 7.1;                                        // an average player's value in one spot
  function fit(team) {                                       // what the eight has, and what it's missing
    var t = team.filter(Boolean), st = team.slice(0, 5).filter(Boolean), out = [];
    if (t.length < 3) return out;
    var mx = function (f) { return Math.max.apply(null, t.map(f)); };
    if (mx(function (p) { return p.ast; }) >= 7) out.push({ k: "Floor general", w: 2, d: "A 7-assist playmaker" });
    else if (t.length >= 6 && mx(function (p) { return p.ast; }) < 5) out.push({ k: "No playmaker", w: -3, d: "Nobody averages 5 assists" });
    if (mx(function (p) { return p.blk; }) >= 1.8) out.push({ k: "Rim protector", w: 2, d: "1.8+ blocks a game" });
    else if (t.length >= 6 && mx(function (p) { return p.blk; }) < 1) out.push({ k: "Soft at the rim", w: -2, d: "Nobody blocks a shot a game" });
    if (st.length === 5 && st.reduce(function (a, p) { return a + p.reb; }, 0) >= 40) out.push({ k: "Owns the glass", w: 1.5, d: "Starters: 40+ rebounds" });
    if (mx(function (p) { return apts(p); }) >= 27) out.push({ k: "Go-to scorer", w: 1.5, d: "27+ points, era-adjusted" });
    if (st.length === 5 && st.reduce(function (a, p) { return a + p.stl; }, 0) >= 7.5) out.push({ k: "Quick hands", w: 1, d: "Starters: 7.5+ steals" });
    var stars = t.filter(function (p) { return apts(p) >= 24; }).length;
    if (stars >= 3) out.push({ k: "One ball", w: -1.5 * (stars - 2), d: stars + " players who need 24+ shots' worth" });
    return out;
  }
  // where a click on a position puts him: that starting spot if it's open, else the bench spot that takes it
  function targets(p, team) {
    var out = [];
    positions(p).forEach(function (pos) {
      var st = SLOTS.findIndex(function (s, i) { return i < 5 && s[0] === pos; });
      if (st >= 0 && !team[st]) { out.push({ i: st, label: pos }); return; }
      var bn = SLOTS.findIndex(function (s, i) { return i >= 5 && !team[i] && s[3].indexOf(pos) >= 0; });
      if (bn >= 0) out.push({ i: bn, label: pos, bench: true });
    });
    return out;
  }
  function record(team) {
    var tot = 0, proj = 0;                                     // (an open spot counts as an average player, for the projection)
    SLOTS.forEach(function (s, i) { var p = team[i]; if (p) { tot += line(p) * s[2]; proj += line(p) * s[2]; } else proj += AVG * s[2]; });
    var f = fit(team), bonus = f.reduce(function (a, x) { return a + x.w; }, 0);
    // a real team's eight adds up to about 160 (41-41); the best real teams about 200 (~54 wins); every win is ~3.1 more
    var w = Math.round(Math.max(0, Math.min(82, 41 + (proj - 160) * 0.32 + bonus))); if (proj < 285 && w >= 82) w = 81;
    return { wins: w, total: tot, fit: f, bonus: bonus };
  }
  function tier(w) { return w >= 82 ? "82-0" : w >= 62 ? "Title favorite" : w >= 52 ? "Contender" : w >= 44 ? "Playoffs" : w >= 37 ? "Play-in" : "Lottery"; }

  // ------------------------------------------------------------ spins: the same for everyone today
  var rnd, state;
  function reset() { rnd = Math.random; state = { team: Array(8).fill(null), pick: 0, spin: null, respin: { team: 1, year: 1 }, picks: [] }; }
  var seasons = {};
  function loadSeason(y) {
    if (!seasons[y]) seasons[y] = B.players(y).then(function (list) {
      var teams = {};
      list.filter(function (p) { return p.gp >= 10; }).forEach(function (p) {
        (p.teams && p.teams.length ? p.teams : [{ tri: p.team, name: B.names[p.team] || p.team }]).forEach(function (t) {
          (teams[t.tri] = teams[t.tri] || { tri: t.tri, name: t.name || B.names[t.tri] || t.tri, logo: t.logo || "", players: [] }).players.push(p);
        });
      });
      Object.keys(teams).forEach(function (k) { if (teams[k].players.length < 8) delete teams[k]; else teams[k].players.sort(function (a, b) { return line(b) - line(a); }); });
      return teams;
    });
    return seasons[y];
  }
  function spinYear() { return FIRST + Math.floor(rnd() * (LAST - FIRST + 1)); }
  function spin(keepYear) {
    var y = keepYear || spinYear(), r = rnd();
    return loadSeason(y).then(function (teams) {
      var keys = Object.keys(teams).sort(); if (!keys.length) throw new Error("no teams");
      var t = teams[keys[Math.floor(r * keys.length)]];
      return { year: y, team: t, teams: teams };
    });
  }
  // franchises under their old ESPN codes (Nets in New Jersey, Sonics -> Thunder, Grizzlies in Vancouver...)
  var FR = { NJ: "BKN", NJN: "BKN", SEA: "OKC", VAN: "MEM", CHH: "CHA", NOH: "NO", NOK: "NO", NOP: "NO", GSW: "GS", SAS: "SA", NYK: "NY", UTA: "UTAH", WAS: "WSH", PHO: "PHX" };
  function fr(t) { return FR[t] || t; }
  function respinYear() {
    var keep = state.spin.team, y0 = state.spin.year, tries = 0;
    function go() {
      tries++;
      var y = spinYear(); if (y === y0) y = y < LAST ? y + 1 : y - 1;
      return loadSeason(y).then(function (teams) {
        var k = Object.keys(teams).filter(function (t) { return fr(t) === fr(keep.tri); })[0];
        if (k) return { year: y, team: teams[k], teams: teams };
        if (tries < 25) return go();
        return { year: y0, team: keep, teams: state.spin.teams };
      });
    }
    return go();
  }
  function respinTeam() {
    var y = state.spin.year, r = rnd();
    return loadSeason(y).then(function (teams) { var keys = Object.keys(teams).sort().filter(function (k) { return k !== state.spin.team.tri; }); return { year: y, team: teams[keys[Math.floor(r * keys.length)]], teams: teams }; });
  }

  // ------------------------------------------------------------ the screen
  // the phone's player card: the spot (gold) and his rating on the left, his picture in the middle with his name over it,
  // his own positions, team logo and season on the right. No picture: his initials in a circle.
  // "Shai Gilgeous-Alexander" -> first name on one line, the rest on the next
  function twoLines(n) { var i = String(n).indexOf(" "); return i < 0 ? B.esc(n) : B.esc(n.slice(0, i)) + "<br>" + B.esc(n.slice(i + 1)); }
  // a player's team logo as it was that season: the Seattle SuperSonics, the New Jersey Nets, the Vancouver Grizzlies,
  // the Charlotte Bobcats... (ESPN's own logos for those teams); today's logo for everyone else
  var OLD = { SEA: "bd458c44-2d33-47eb-cebc-35d3d4ac595c", NJ: "926db769-d35e-e282-9d7e-a05001d774ab", NJN: "926db769-d35e-e282-9d7e-a05001d774ab",
              VAN: "af5d4942-aeb5-2d07-2a8a-f70b54617e51" };
  var OLDNAMES = { "seattle supersonics": "SEA", "new jersey nets": "NJ", "vancouver grizzlies": "VAN" };
  function oldLogo(tri) { return OLD[tri] ? "https://a.espncdn.com/guid/" + OLD[tri] + "/logos/default.png" : ""; }
  function teamLogo(p) { return (/\/guid\//.test(p.logo || "") ? p.logo : "") || oldLogo(p.tri) || B.logo(p.tri); }   // (ESPN keeps its old-team logos under /guid/)
  function initials(p) { return p.name.split(" ").map(function (x) { return x.charAt(0); }).join("").slice(0, 2); }
  function yy(y) { return String((y - 1) % 100).padStart(2, "0") + "-" + String(y % 100).padStart(2, "0"); }   // 2024 -> "23-24"
  // corners: the spot (gold) top-left, his own positions top-right; beside his ears: his rating (left) and his team's
  // logo with the season (right); his picture in the middle, his name along the bottom
  function card(p, s, i) {
    return '<div class="fd-card"><span class="fd-cpos">' + B.esc(s[4]).replace(/\//g, "/<wbr>") + '</span><span class="fd-cpp">' + B.esc(posLabel(p)).replace(/\//g, "/<wbr>") + "</span>" +
      '<div class="fd-cimg"><span class="fd-cini">' + B.esc(initials(p)) + '</span><img alt="" loading="lazy" src="' + B.esc(B.face(p.id, 260)) + '" onerror="this.remove()"></div>' +
      '<span class="fd-crt">' + line(p).toFixed(1) + "<small>RTG</small></span>" +
      '<span class="fd-cyr"><img class="fd-clogo" alt="" src="' + B.esc(teamLogo(p)) + '" onerror="this.style.visibility=\'hidden\'">' + yy(p.year) + "</span>" +
      '<b class="fd-cnm' + (p.name.length > 16 ? " long" : "") + '">' + B.esc(p.name) + "</b></div>";
  }
  function face(p, cls) {
    var ini = p.name.split(" ").map(function (s) { return s.charAt(0); }).join("").slice(0, 2);
    return '<span class="fd-face ' + (cls || "") + '"><b>' + B.esc(ini) + '</b><img alt="" loading="lazy" src="' + B.esc(B.face(p.id, 96)) + '" onerror="this.remove()"></span>';
  }
  function logoImg(t) { return '<img class="fd-logo" alt="" src="' + B.esc(t.logo || B.logo(t.tri)) + '" onerror="this.style.visibility=\'hidden\'">'; }
  function meter(rec) {                                        // the projected record, up against the right side
    return '<div class="fd-meter"><div class="fd-rec"><span class="gm-k">Projected record</span><b>' + (rec ? rec.wins + "-" + (82 - rec.wins) : "— – —") + "</b></div></div>";
  }
  function draw() {
    var rec = state.pick ? record(state.team) : null, sp = state.spin, open = SLOTS.map(function (s, i) { return !state.team[i]; });
    root.innerHTML = '<div class="fd">' +
      '<div class="fd-top"><div><span class="gm-k">Pick ' + Math.min(8, state.pick + 1) + " of 8</span><div class=\"fd-day\">" + (state.pick < 8 ? "Spin, then draft" : "Your eight") + "</div></div>" + meter(rec) + "</div>" +
      '<div class="fd-grid"><div class="fd-draft">' +
        (state.pick < 8 ? '<div class="fd-spin">' + (sp ? logoImg(sp.team) + '<div class="fd-sn"><span class="gm-k">This spin</span><b>' + B.esc(sp.team.name) + '</b><em>' + season(sp.year) + '</em><small class="fd-era">' + (Math.abs(era(sp.year) - 1) < 0.02 ? "Average scoring era" : (era(sp.year) > 1 ? "Low-scoring era: points count " : "High-scoring era: points count ") + "×" + era(sp.year).toFixed(2)) + "</small></div>" : '<div class="fd-sn"><b>Spinning…</b></div>') +
          '<div class="fd-re"><button type="button" class="gm-btn ghost fd-rt"' + (state.respin.team && sp ? "" : " disabled") + ">Respin team · " + state.respin.team + ' left</button><button type="button" class="gm-btn ghost fd-ry"' + (state.respin.year && sp ? "" : " disabled") + ">Respin season · " + state.respin.year + " left</button></div></div>" +
          '<div class="fd-table" role="table">' + (sp ? '<div class="fd-th" role="row"><span>Player</span><span>PTS</span><span>REB</span><span>AST</span><span>STL</span><span>BLK</span><span title="PTS (era-adjusted) + REB + AST + STL + BLK">Value</span><span>Draft</span></div>' +
            sp.team.players.map(function (p) {
              var y = sp.year, can = targets(p, state.team), taken = state.team.some(function (x) { return x && x.name === p.name; });
              return '<div class="fd-tr' + (can.length && !taken ? "" : " off") + '" role="row">' + '<span class="fd-pl">' + face(p) + "<span><b>" + B.esc(p.name) + "</b><i>" + B.esc(posLabel(p, y)) + " · " + p.gp + " GP</i></span></span>" +
                [p.pts, p.reb, p.ast, p.stl, p.blk].map(function (v) { return "<span>" + v.toFixed(1) + "</span>"; }).join("") + '<span class="fd-tot">' + line(p, y).toFixed(1) + "</span>" +
                '<span class="fd-to">' + (taken ? "<em>Drafted</em>" : can.length ? can.map(function (t) { return '<button type="button" class="fd-slotbtn' + (t.bench ? " bench" : "") + '" data-i="' + t.i + '" data-n="' + B.esc(p.name) + '" title="' + B.esc(SLOTS[t.i][1]) + '">' + t.label + (t.bench ? "<small>bench</small>" : "") + "</button>"; }).join("") : "<em>No open spot</em>") + "</span></div>";
            }).join("") : '<p class="gm-empty">Loading the roster…</p>') + "</div>"
        : finale()) +
      '</div><aside class="fd-team"><span class="gm-k">Your eight</span>' + (state.pick ? ("ontouchstart" in window ? '<span class="fd-draghint">Hold a player, then drag him to another spot he can play</span>' : '<span class="fd-draghint">Drag a player to another spot he can play</span>') : "") + '' + SLOTS.map(function (s, i) {
        var p = state.team[i];
        return (i === 5 ? '<div class="fd-sep">Bench</div>' : "") + '<div class="fd-slot' + (p ? " full" : "") + '" data-i="' + i + '"><span class="fd-posw"><span class="fd-pos' + (i >= 5 ? " b" : "") + '">' + s[4] + "</span>" + (p ? '<span class="fd-ppos">' + B.esc(posLabel(p)) + "</span>" : "") + "</span>" +
          (p ? '<span class="fd-dimg"><b>' + B.esc(initials(p)) + '</b><img alt="" loading="lazy" src="' + B.esc(B.face(p.id, 260)) + '" onerror="this.remove()"></span>' +
               '<span class="fd-sl"><b>' + twoLines(p.name) + '</b><i><img class="fd-slogo" alt="" src="' + B.esc(teamLogo(p)) + '" onerror="this.style.visibility=\'hidden\'">' + yy(p.year) + "</i></span>" +
               '<span class="fd-tot">' + line(p).toFixed(1) + "</span>" + card(p, s, i) : '<span class="fd-sl"><i>' + s[1] + "</i></span>") + "</div>";
      }).join("") + '<div class="fd-sum">Team value <b>' + (rec ? rec.total.toFixed(1) : "0.0") + "</b><span>PTS (era-adjusted) + REB + AST + STL + BLK, bench at 70%. Open spots count as average players in the projection.</span></div>" +
      chips(rec) + "</aside></div></div>";
    wire();
  }
  function chips(rec) {
    if (!rec || !rec.fit.length) return '<p class="fd-fitnote">Fit counts too: a playmaker, a rim protector, rebounding, a go-to scorer, and not too many players who need the ball.</p>';
    return '<div class="fd-fit">' + rec.fit.map(function (x) { return '<span class="' + (x.w > 0 ? "up" : "down") + '" title="' + B.esc(x.d) + '">' + B.esc(x.k) + " <b>" + (x.w > 0 ? "+" : "") + x.w + "</b></span>"; }).join("") + "</div>";
  }
  function playoffs(w) { return w >= 82 ? "16-0 through the playoffs. The perfect season." : w >= 66 ? "Champions." : w >= 60 ? "Lose in the Finals." : w >= 52 ? "Out in the conference finals." : w >= 46 ? "Out in the second round." : w >= 42 ? "Out in the first round." : w >= 37 ? "Out in the play-in." : "A lottery pick."; }
  function finale() {
    var rec = record(state.team), best = B.store("fd2:best");
    return '<div class="fd-final"><span class="gm-k">Your season</span><div class="fd-big" data-w="' + rec.wins + '">0-0</div>' +
      '<div class="fd-sim" aria-hidden="true">' + Array(83).join("<i></i>") + "</div>" +
      '<div class="fd-after"><div class="fd-tier">' + B.esc(tier(rec.wins)) + "</div>" + '<p class="fd-po">' + B.esc(playoffs(rec.wins)) + "</p>" +
      (rec.wins >= 82 ? '<p class="fd-perfect">82-0. Perfect.</p>' : "") + chips(rec) +
      '<p class="gm-note">Team total ' + rec.total.toFixed(1) + (best ? " · your best ever: <b>" + best + "-" + (82 - best) + "</b>" : "") + "</p>" +
      '<div class="gm-row"><button type="button" class="gm-btn fd-post">Post to the leaderboard</button><button type="button" class="gm-btn ghost fd-again">Draft again</button></div><p class="gm-note fd-saved"></p>' +
      '<p class="gm-note">Drafting again uses the same spins as your first draft today.</p></div></div>';
  }
  function wire() {
    root.querySelectorAll(".fd-slotbtn").forEach(function (b) {
      b.addEventListener("click", function () {
        var slot = +b.getAttribute("data-i"), name = b.getAttribute("data-n");
        var p = state.spin.team.players.filter(function (x) { return x.name === name; })[0];
        state.team[slot] = { id: p.id, name: p.name, pos: p.pos, pts: p.pts, reb: p.reb, ast: p.ast, stl: p.stl, blk: p.blk, from: state.spin.team.name + " · " + season(state.spin.year), tri: state.spin.team.tri, year: state.spin.year, logo: state.spin.team.logo || "" };
        var before = record(state.team.map(function (x, k) { return k === slot ? null : x; })).wins;
        state.pick++; state.spin = null;
        var after = record(state.team).wins, dw = after - before;
        if (state.pick >= 8) { done(); draw(); simulate(); return; }
        draw(); next();
        toast(p.name + ": " + (dw >= 0 ? "+" : "") + dw + " win" + (Math.abs(dw) === 1 ? "" : "s"), dw >= 0);
      });
    });
    dragSlots();
    var rt = root.querySelector(".fd-rt"), ry = root.querySelector(".fd-ry");
    if (rt) rt.addEventListener("click", function () { state.respin.team--; var keep = state.spin; state.spin = null; draw(); state.spin = keep; respinTeam().then(function (s) { state.spin = null; reels(s, "team", function () { show(s); }); }); });
    if (ry) ry.addEventListener("click", function () { state.respin.year--; var keep = state.spin; state.spin = null; draw(); state.spin = keep; respinYear().then(function (s) { state.spin = null; reels(s, "year", function () { show(s); }); }); });
    var post = root.querySelector(".fd-post");
    if (post) post.addEventListener("click", function () {
      post.disabled = true;
      var rec = record(state.team), detail = { team: state.team.map(function (p, i) { return SLOTS[i][0] + ": " + p.name + " (" + p.from + ")"; }),
          rows: state.team.map(function (p, i) { return { s: SLOTS[i][0], n: p.name, t: p.tri, y: p.year, l: p.logo || "" }; }), fit: rec.fit.map(function (x) { return x.k + " " + (x.w > 0 ? "+" : "") + x.w; }) };
      B.askName().then(function (n) {
        var e = { name: n, score: rec.wins, extra: { rec: rec.wins + "-" + (82 - rec.wins), tot: rec.total.toFixed(1) }, detail: detail };
        return B.submit(GAME, DAY, e).then(function (r) { return [r]; });
      }).then(function (r) { root.querySelector(".fd-saved").textContent = r[0].rank ? "Posted: #" + r[0].rank + " today." : "Saved."; boards(); });
    });
    var again = root.querySelector(".fd-again");
    if (again) again.addEventListener("click", function () { begin(); });
  }
  function simulate() {
    var big = root.querySelector(".fd-big"), cells = root.querySelectorAll(".fd-sim i"), after = root.querySelector(".fd-after");
    if (!big || !cells.length) return;
    var w = +big.getAttribute("data-w"), r = B.seeded("fdsim" + DAY + state.team.map(function (p) { return p.name; }).join()), res = [];
    for (var k = 0; k < 82; k++) res.push(k < w);
    for (var j = 81; j > 0; j--) { var x = Math.floor(r() * (j + 1)), t = res[j]; res[j] = res[x]; res[x] = t; }   // the order the wins come in
    var quick = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches, n = 0, W = 0;
    after.classList.add("wait");
    (function go() {
      var many = quick ? 82 : 2;
      for (var m = 0; m < many && n < 82; m++, n++) { cells[n].className = res[n] ? "w" : "l"; if (res[n]) W++; }
      big.textContent = W + "-" + (n - W);
      if (n < 82) setTimeout(go, 38); else after.classList.remove("wait");
    })();
  }
  function toast(t, up) {
    var box = root.querySelector(".fd-team"); if (!box) return;
    var e = document.createElement("div"); e.className = "fd-toast " + (up ? "up" : "down"); e.textContent = t; box.appendChild(e);
    setTimeout(function () { e.remove(); }, 2600);
  }
  // dragging a drafted player to another spot he can play: an open one, or swapping with a player who can play his
  function dragSlots() {
    root.querySelectorAll(".fd-slot.full").forEach(function (el) {
      var from = +el.getAttribute("data-i"), ghost = null, over = null, ok = null;
      function begin() {
        var p = state.team[from];
        ok = SLOTS.map(function (s, i) { var q = state.team[i]; return i !== from && canPlay(i, p) && (!q || canPlay(from, q)); });
        ghost = el.cloneNode(true); ghost.className = "fd-slot full fd-ghost"; ghost.style.width = el.offsetWidth + "px"; document.body.appendChild(ghost);
        el.classList.add("fd-from");
        root.querySelectorAll(".fd-slot").forEach(function (t) { var i = +t.getAttribute("data-i"); t.classList.toggle(ok[i] ? "fd-can" : "fd-cant", i !== from); });
        if (navigator.vibrate) try { navigator.vibrate(12); } catch (e) {}
      }
      function at(x, y) {
        ghost.style.left = (x - 20) + "px"; ghost.style.top = (y - 20) + "px";
        var t = document.elementFromPoint(x, y), s2 = t && t.closest && t.closest(".fd-slot:not(.fd-ghost)");
        if (over && over !== s2) over.classList.remove("fd-over");
        over = s2 && ok[+s2.getAttribute("data-i")] ? s2 : null;
        if (over) over.classList.add("fd-over");
      }
      function finish() {
        if (!ghost) return;
        ghost.remove(); ghost = null;
        var p = state.team[from];
        if (over) { var to = +over.getAttribute("data-i"), q = state.team[to]; state.team[to] = p; state.team[from] = q || null; }
        over = null; draw(); if (state.pick >= 8) simulate();
      }
      // a mouse (or pen): press and drag
      el.addEventListener("pointerdown", function (e) {
        if (e.pointerType === "touch" || e.button > 0) return;
        var sx = e.clientX, sy = e.clientY;
        function move(ev) { if (!ghost) { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) < 6) return; begin(); } ev.preventDefault(); at(ev.clientX, ev.clientY); }
        function up() { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); window.removeEventListener("pointercancel", up); finish(); }
        window.addEventListener("pointermove", move, { passive: false }); window.addEventListener("pointerup", up); window.addEventListener("pointercancel", up);
      });
      // a finger: hold for a moment (the page would scroll otherwise), then drag; a quick swipe still scrolls the page
      var hold = 0, sx = 0, sy = 0;
      el.addEventListener("touchstart", function (e) {
        if (e.touches.length !== 1) return;
        var t = e.touches[0]; sx = t.clientX; sy = t.clientY;
        clearTimeout(hold);
        hold = setTimeout(function () { hold = 0; begin(); at(sx, sy); }, 220);
      }, { passive: true });
      el.addEventListener("touchmove", function (e) {
        var t = e.touches[0];
        if (ghost) { e.preventDefault(); at(t.clientX, t.clientY); return; }
        if (hold && Math.hypot(t.clientX - sx, t.clientY - sy) > 10) { clearTimeout(hold); hold = 0; }   // (a scroll)
      }, { passive: false });
      el.addEventListener("touchend", function () { clearTimeout(hold); hold = 0; finish(); });
      el.addEventListener("touchcancel", function () { clearTimeout(hold); hold = 0; if (ghost) { ghost.remove(); ghost = null; over = null; draw(); } });
      el.addEventListener("contextmenu", function (e) { if (ghost) e.preventDefault(); });
    });
  }
  function done() { var rec = record(state.team), best = B.store("fd2:best"); if (best == null || rec.wins > best) B.store("fd2:best", rec.wins); }
  // the two slot reels: teams and seasons blur past and land on the spin (both reels, or just the one respun)
  var ALLTRI = ["ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GS", "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NO", "NY", "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SA", "TOR", "UTAH", "WSH"];
  function reels(s, which, done) {
    var box = root.querySelector(".fd-spin");
    var quick = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!box || quick) { done(); return; }
    var N = 26, tris = [], yrs = [];
    for (var k = 0; k < N; k++) { tris.push(ALLTRI[Math.floor(Math.random() * ALLTRI.length)]); yrs.push(FIRST + Math.floor(Math.random() * (LAST - FIRST + 1))); }
    tris.push(s.team.tri); yrs.push(s.year);
    var spinT = which !== "year", spinY = which !== "team";
    var tItems = (spinT ? tris : [s.team.tri]).map(function (t, k, a) {
      var last = k === a.length - 1, logo = last ? (s.team.logo || B.logo(t)) : B.logo(t);
      return '<div class="fd-ri"><img alt="" src="' + B.esc(logo) + '" onerror="this.style.visibility=\'hidden\'"><b>' + B.esc(last ? s.team.name : (B.names[t] || t)) + "</b></div>";
    }).join("");
    var yItems = (spinY ? yrs : [s.year]).map(function (y) { return '<div class="fd-ri"><em>' + season(y) + "</em></div>"; }).join("");
    box.innerHTML = '<div class="fd-slots" aria-live="polite"><div class="fd-reel t"><div class="fd-strip">' + tItems + '</div></div><div class="fd-reel y"><div class="fd-strip">' + yItems + "</div></div></div>";
    var left = 2;
    [[".fd-reel.t .fd-strip", spinT, 1500], [".fd-reel.y .fd-strip", spinY, 1950]].forEach(function (r) {
      var st = box.querySelector(r[0]), n = st.children.length, h = st.children[0].offsetHeight || 56;
      if (!r[1] || n < 2) { st.parentNode.classList.add("landed"); if (--left === 0) setTimeout(done, 300); return; }
      st.style.transform = "translateY(0)";
      void st.offsetHeight;
      st.style.transition = "transform " + r[2] + "ms cubic-bezier(.12,.62,.18,1.02)";
      st.style.transform = "translateY(" + (-(n - 1) * h) + "px)";
      setTimeout(function () { st.parentNode.classList.add("landed"); if (--left === 0) setTimeout(done, 420); }, r[2] + 40);
    });
  }
  function show(s) {
    state.spin = s; draw();
    B.preload(s.team.players.slice(0, 14).map(function (p) { return B.face(p.id, 96); }));
    var reel = root.querySelector(".fd-spin"); if (reel) { reel.classList.remove("go"); void reel.offsetWidth; reel.classList.add("go"); }
  }
  function next() { spin().then(function (s) { reels(s, "both", function () { show(s); }); }).catch(function () { root.querySelector(".fd-table").innerHTML = '<p class="gm-empty">Couldn&rsquo;t load that season. <button type="button" class="gm-btn ghost fd-retry">Try again</button></p>'; root.querySelector(".fd-retry").addEventListener("click", next); }); }
  function begin() { reset(); draw(); posReady.then(next, next); }

  function boards() {
    B.renderBoard(document.getElementById("fd-board"), GAME, DAY, { cols: [["tot", "Total"]], scoreLabel: "Record", format: function (s) { return Math.round(s) + "-" + (82 - Math.round(s)); }, onView: view, viewLabel: "Team" });
  }
  // each player of a posted team: spot, name, team (as its logo) and season. Older posts only kept a line of text
  // ("PG: Kobe Bryant (Los Angeles Lakers · 2005-06)"), read back here.
  function viewRows(d) {
    if (d.rows && d.rows.length) return d.rows;
    var byName = {}; Object.keys(B.names || {}).forEach(function (t) { byName[String(B.names[t]).toLowerCase()] = t; });
    return (d.team || []).map(function (line) {
      var m = /^([^:]+):\s*(.*?)\s*\((.*?)\s*·\s*(\d{4})-(\d{2})\)\s*$/.exec(line);
      if (!m) return { s: "", n: line };
      var tn = m[3].toLowerCase(), t = OLDNAMES[tn] || byName[tn] || Object.keys(byName).filter(function (k) { return k.indexOf(tn) >= 0 || tn.indexOf(k) >= 0; }).map(function (k) { return byName[k]; })[0];
      return { s: m[1], n: m[2], t: t || "", y: +m[4] + 1 };
    });
  }
  function view(e) {
    var shade = document.createElement("div"); shade.className = "gm-shade";
    shade.innerHTML = '<div class="gm-modal"><button type="button" class="gm-x" aria-label="Close">&times;</button><h3>' + B.esc(e.name) + "&rsquo;s team · " + Math.round(e.score) + "-" + (82 - Math.round(e.score)) + '</h3><ul class="fd-viewlist">' + viewRows(e.detail || {}).map(function (r) {
        return '<li><span class="fd-vs">' + B.esc(r.s) + '</span><span class="fd-vn">' + B.esc(r.n) + "</span>" +
          (r.t ? '<img class="fd-vlogo" alt="" title="' + B.esc(B.names[r.t] || r.t) + '" src="' + B.esc(teamLogo({ logo: r.l, tri: r.t })) + '" onerror="this.style.visibility=\'hidden\'">' : "") +
          '<span class="fd-vy">' + (r.y ? yy(r.y) : "") + "</span></li>";
      }).join("") + "</ul>" +
      (((e.detail || {}).fit || []).length ? '<p class="gm-note">Fit: ' + B.esc(e.detail.fit.join(" · ")) + "</p>" : "") + "</div>";
    document.body.appendChild(shade);
    shade.querySelector(".gm-x").addEventListener("click", function () { shade.remove(); });
    shade.addEventListener("click", function (ev) { if (ev.target === shade) shade.remove(); });
  }

  begin();
  boards();
})();
