/* GM Daily Challenge: a front office for a day. Every day the same team for everyone, its biggest need (where it ranked
   worst in the league last season), the evidence, and today's rules. Build one trade -- send players and picks, take
   back players from up to two other teams -- that clears the CBA's salary matching, fits the roster, gets the other
   GMs to say yes, and fixes the need.

   Rosters and contracts: the Bradley salary table (2026-27 on, with options). Ratings: Bradley ratings. Team numbers:
   2025-26, from the NBA's stats (data/analytics.json) and ESPN. Cap figures: the 2026-27 cap, tax and aprons.

   Salary matching (2023 CBA, simplified to one trade): a team over the cap after the trade can take back the greater of
   125% of what it sends + $250K, or 200% + $250K up to what it sends + the indexed $7.5M cushion; over the first apron,
   no more than it sends; over the second apron it also can't combine two players' salaries. Rosters stay at 15 or fewer.

   Will they say yes: each player's trade value comes from his rating, his age and how his contract compares with what a
   player like him is worth (like MyNBA's trade value); picks have value too, more to a rebuilding team. A team says yes
   when what it gets is worth at least what it gives.

   Grade (0-100): how much the need is fixed (its projected league rank and number after the trade, weighted by the
   minutes the players play), how much better or worse the rotation gets, what it does to the payroll and tax bill, and
   what it costs in picks and value. First version of the model, to be tuned. */
(function () {
  "use strict";
  var B = window.BAG, root = document.getElementById("gmc-app");
  if (!B || !root) return;
  var GAME = "gm-challenge", DAY = B.day();
  var money = function (v) { return (v < 0 ? "−" : "") + "$" + (Math.abs(v) / 1e6).toFixed(1) + "M"; };
  var ord = function (n) { var s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
  var clamp = function (v, a, b) { return Math.max(a, Math.min(b, v)); };
  var NBA_TRI = { GSW: "GS", NYK: "NY", SAS: "SA", NOP: "NO", UTA: "UTAH", WAS: "WSH" };

  // ------------------------------------------------------------ the needs
  // value(team) = the team's number; per(p) = what one player adds to it (per game, at his minutes); low = lower is better
  var NEEDS = {
    three: { label: "Three-point shooting", short: "3P%", unit: "%", low: false, pct: true,
      team: function (t) { var z = t.zones; var m = z[3][0] + z[4][0] + z[5][0], a = z[3][1] + z[4][1] + z[5][1]; return { m: m / 82, a: a / 82, v: 100 * m / a }; },
      p: function (p) { return { m: p.tpm, a: p.tpa }; }, show: function (p) { return p.tpm.toFixed(1) + " 3PM · " + p.tpp.toFixed(1) + "%"; },
      fit: function (p) { return p.tpm * 1.4 + (p.tpp - 35) * 0.08 * Math.min(1, p.tpa / 3); } },
    def: { label: "Defense", short: "Def Rtg", unit: "", low: true,
      team: function (t) { return { v: t.def }; }, delta: function (inc, out) { return -(sum(inc, dImpact) - sum(out, dImpact)); },
      show: function (p) { return (p.stl + p.blk).toFixed(1) + " STL+BLK · DEF " + (p.dr || "–"); }, fit: function (p) { return dImpact(p); } },
    reb: { label: "Rebounding", short: "DREB%", unit: "%", low: false,
      team: function (t) { return { v: t.dreb }; }, delta: function (inc, out) { return (sum(inc, function (p) { return p.reb * share(p); }) - sum(out, function (p) { return p.reb * share(p); })) * 0.55; },
      show: function (p) { return p.reb.toFixed(1) + " REB"; }, fit: function (p) { return p.reb * share(p); } },
    tov: { label: "Ball security", short: "TOV%", unit: "%", low: true,
      team: function (t) { return { v: t.tov }; }, delta: function (inc, out) { return (sum(inc, function (p) { return p.tov * share(p); }) - sum(out, function (p) { return p.tov * share(p); })) * 0.9; },
      show: function (p) { return p.ast.toFixed(1) + " AST · " + p.tov.toFixed(1) + " TO"; }, fit: function (p) { return (p.ast + 1) / (p.tov + 0.6) * share(p); } },
    ast: { label: "Playmaking", short: "AST%", unit: "%", low: false,
      team: function (t) { return { v: t.ast }; }, delta: function (inc, out) { return (sum(inc, function (p) { return p.ast * share(p); }) - sum(out, function (p) { return p.ast * share(p); })) * 1.6; },
      show: function (p) { return p.ast.toFixed(1) + " AST"; }, fit: function (p) { return p.ast * share(p); } },
    off: { label: "Scoring", short: "Off Rtg", unit: "", low: false,
      team: function (t) { return { v: t.off }; }, delta: function (inc, out) { return (sum(inc, oImpact) - sum(out, oImpact)); },
      show: function (p) { return p.pts.toFixed(1) + " PTS · " + p.fgp.toFixed(1) + " FG%"; }, fit: function (p) { return oImpact(p); } },
    rim: { label: "Rim protection", short: "Opp. paint FG%", unit: "", low: false,
      team: function (t) { return { v: t.blk || 0 }; }, delta: function (inc, out) { return sum(inc, function (p) { return p.blk * share(p); }) - sum(out, function (p) { return p.blk * share(p); }); },
      show: function (p) { return p.blk.toFixed(1) + " BLK"; }, fit: function (p) { return p.blk * share(p) * 2 + (p.r["Interior Defense"] || 50) / 50; } }
  };
  NEEDS.rim.short = "BLK";
  function sum(a, f) { return a.reduce(function (s, p) { return s + f(p); }, 0); }
  function share(p) { return clamp((p.min || 12) / 34, 0.25, 1.1); }
  function dImpact(p) { return ((p.stl + p.blk) * 0.9 + ((p.r["Perimeter Defense"] || 60) + (p.r["Interior Defense"] || 55) - 120) * 0.035) * share(p); }
  function oImpact(p) { return ((p.pts - 10) * 0.12 + (p.fgp - 46) * 0.04 + (p.ast - 2) * 0.12 - (p.tov - 1.5) * 0.25) * share(p); }

  // ------------------------------------------------------------ value, like a trade value in MyNBA
  function fairSalary(r) { return clamp(Math.pow(Math.max(0, r - 68) / 29, 1.9) * 55e6, 2.3e6, 62e6); }
  function value(p, rebuilding) {
    var r = p.rating, age = p.age || 27, yrs = p.years.filter(function (y) { return y[0] > 0; }).length || 1;
    var base = Math.pow(Math.max(0, r - 62), 1.75) / 4;
    var ageF = age <= 22 ? 1.25 : age <= 25 ? 1.12 : age <= 29 ? 1 : age <= 32 ? 0.82 : 0.6;
    if (rebuilding) ageF *= age <= 24 ? 1.2 : age >= 30 ? 0.75 : 1;
    var surplus = p.years.slice(0, 4).reduce(function (s, y) { return s + (y[0] ? (fairSalary(r) - y[0]) / 1e6 : 0); }, 0) * 0.35;
    return Math.max(0, base * ageF + surplus * (r >= 78 ? 1 : 0.6) - (yrs >= 4 && r < 75 ? 6 : 0));
  }
  function pickValue(pk, rebuilding) { var v = pk.round === 1 ? 22 - (pk.year - 2027) * 1.5 : 3; return v * (rebuilding ? 1.35 : 1); }

  // ------------------------------------------------------------ data
  var S = null, deal = { out: [], picks: [], inc: [] }, done = false;
  function load() {
    return Promise.all([B.contracts(), B.analytics(), B.players(2026).catch(function () { return []; }), B.ratings().catch(function () { return []; }), B.teams(2026).catch(function () { return []; })]).then(function (r) {
      var C = r[0], A = r[1], stats = r[2], ratings = r[3], espnTeams = r[4];
      var byName = {}; stats.forEach(function (p) { byName[B.fold(p.name)] = p; });
      espnTeams.forEach(function (t) { if (A.teams[t.tri]) A.teams[t.tri].blk = t.blk; });
      var players = C.players.map(function (c) {
        var st = byName[B.fold(c.name)] || null, rt = B.ratingFor(ratings, { name: c.name, team: c.team }) || {};
        var s = st || { gp: 0, min: 10, pts: 4, reb: 2, ast: 1, stl: 0.4, blk: 0.3, tov: 0.6, fgp: 45, tpm: 0.4, tpa: 1.2, tpp: 33, pos: "" };
        var rating = rt["Player Rating"] || Math.round(clamp(58 + s.pts * 0.9 + s.reb * 0.5 + s.ast * 0.7 + (s.stl + s.blk) * 1.5, 60, 92));
        return { id: c.id, name: c.name, team: c.team, age: c.age, years: c.years, salary: c.years[0][0], rating: rating, r: rt, dr: rt["Perimeter Defense"] ? Math.round((rt["Perimeter Defense"] + rt["Interior Defense"]) / 2) : null,
          pos: (rt.pos || s.pos || "").replace(/^$/, "–"), gp: s.gp, min: s.min, pts: s.pts, reb: s.reb, ast: s.ast, stl: s.stl, blk: s.blk, tov: s.tov, fgp: s.fgp, tpm: s.tpm, tpa: s.tpa, tpp: s.tpp, rookie: !st };
      });
      var rnd = B.seeded("gmc2" + DAY), tris = Object.keys(A.teams).sort();
      var tri = tris[Math.floor(rnd() * tris.length)];
      var team = A.teams[tri];
      // the need: where the team ranked worst of the seven
      var ranks = Object.keys(NEEDS).map(function (k) {
        var N = NEEDS[k], vals = tris.map(function (t) { return [t, N.team(A.teams[t]).v]; }).sort(function (a, b) { return N.low ? a[1] - b[1] : b[1] - a[1]; });
        return { key: k, rank: vals.findIndex(function (x) { return x[0] === tri; }) + 1, vals: vals, v: N.team(team).v };
      }).sort(function (a, b) { return b.rank - a.rank || (rnd() - 0.5); });
      var need = ranks[0];
      var roster = players.filter(function (p) { return p.team === tri; }).sort(function (a, b) { return b.salary - a.salary; });
      var star = roster.slice().sort(function (a, b) { return b.rating - a.rating; })[0];
      var payroll = sum(roster, function (p) { return p.salary; });
      var rules = [{ k: "keep", text: "Keep " + star.name + ": he's not available." }];
      var extra = rnd();
      if (payroll > C.cap.tax) rules.push({ k: "cut", text: "Ownership wants the payroll down: take back less salary than you send." });
      else if (extra < 0.5) rules.push({ k: "tax", text: "Stay under the luxury tax (" + money(C.cap.tax) + ")." });
      else rules.push({ k: "future", text: "Don't add salary in 2028-29: protect the books for the summer." });
      rules.push({ k: "one", text: "One trade: players from up to two other teams, up to three players back." });
      var wins = {}; tris.forEach(function (t) { wins[t] = A.teams[t].w; });
      S = { C: C, A: A, players: players, tri: tri, team: team, need: need, ranks: ranks, roster: roster, star: star, payroll: payroll, rules: rules, wins: wins, cap: C.cap };
    });
  }

  // ------------------------------------------------------------ the trade's checks
  function maxIncoming(out, payAfter) {
    var cap = S.cap;
    if (payAfter <= cap.cap) return Infinity;
    if (payAfter > cap.apron1) return out;
    return Math.max(Math.min(2 * out + 250000, out + cap.cushion), 1.25 * out + 250000);
  }
  function check() {
    var out = sum(deal.out, function (p) { return p.salary; }), inc = sum(deal.inc, function (p) { return p.salary; }), after = S.payroll - out + inc;
    var res = { out: out, inc: inc, after: after, issues: [], ok: true }, lim = maxIncoming(out, after);
    if (!deal.inc.length && !deal.out.length) { res.ok = false; res.empty = true; return res; }
    if (!deal.inc.length) res.issues.push("Take back at least one player.");
    if (!deal.out.length && !deal.picks.length) res.issues.push("Send at least one player or pick.");
    if (inc > lim) res.issues.push("Salary doesn't match: you can take back up to " + money(lim) + " for " + money(out) + (after > S.cap.apron1 ? " (over the first apron: no more than you send)" : "") + ".");
    if (after > S.cap.apron2 && deal.out.length > 1) res.issues.push("Over the second apron you can't combine salaries: send one player.");
    var std = function (p) { return p.years[0][1] !== "2W"; }, now = S.roster.filter(std).length;
    var size = now - deal.out.filter(std).length + deal.inc.filter(std).length; res.size = size; res.limit = Math.max(15, now);
    if (size > res.limit) res.issues.push("That leaves " + size + " players on standard contracts: the limit is 15.");
    var partners = {}; deal.inc.forEach(function (p) { partners[p.team] = 1; });
    if (Object.keys(partners).length > 2) res.issues.push("Two other teams at most.");
    // the other teams' side: each must be able to take back what it's sent (spread evenly)
    Object.keys(partners).forEach(function (t) {
      var give = sum(deal.inc.filter(function (p) { return p.team === t; }), function (p) { return p.salary; }), share = (out * give / (inc || 1));
      var their = sum(S.players.filter(function (p) { return p.team === t; }), function (p) { return p.salary; }) - give + share;
      if (their > S.cap.cap && share > Math.max(1.25 * give + 250000, Math.min(2 * give + 250000, give + S.cap.cushion))) res.issues.push(B.names[t].split(" ").pop() + " can't take back that much salary.");
    });
    S.rules.forEach(function (r) {
      if (r.k === "keep" && deal.out.indexOf(S.star) >= 0) res.issues.push(S.star.name + " is off limits today.");
      if (r.k === "tax" && after > S.cap.tax) res.issues.push("That puts you over the tax line by " + money(after - S.cap.tax) + ".");
      if (r.k === "cut" && inc >= out) res.issues.push("Ownership's rule: take back less salary than you send.");
      if (r.k === "future") { var f = function (a) { return sum(a, function (p) { return p.years[2][0] || 0; }); }; if (f(deal.inc) > f(deal.out)) res.issues.push("That adds " + money(f(deal.inc) - f(deal.out)) + " in 2028-29."); }
    });
    // will they say yes
    res.partners = Object.keys(partners).map(function (t) {
      var reb = S.wins[t] < 38, give = deal.inc.filter(function (p) { return p.team === t; });
      var n = Object.keys(partners).length, get = (sum(deal.out, function (p) { return value(p, reb); }) + sum(deal.picks, function (k) { return pickValue(k, reb); })) / n;
      var lose = sum(give, function (p) { return value(p, reb); });
      return { tri: t, get: get, give: lose, yes: get >= lose * 0.95 - 0.5, rebuilding: reb };
    });
    res.partners.forEach(function (p) { if (!p.yes) res.issues.push("The " + B.names[p.tri].split(" ").pop() + " say no: they want more value back."); });
    res.ok = !res.issues.length;
    return res;
  }
  function projection() {
    var N = NEEDS[S.need.key], t = S.team, after;
    if (S.need.key === "three") { var base = N.team(t), dm = 0, da = 0; deal.inc.forEach(function (p) { dm += p.tpm * share(p); da += p.tpa * share(p); }); deal.out.forEach(function (p) { dm -= p.tpm * share(p); da -= p.tpa * share(p); }); after = 100 * (base.m + dm) / (base.a + da); }
    else after = N.team(t).v + N.delta(deal.inc, deal.out);
    var vals = S.need.vals.filter(function (x) { return x[0] !== S.tri; }).map(function (x) { return x[1]; });
    var rank = vals.filter(function (v) { return N.low ? v < after : v > after; }).length + 1;
    return { before: S.need.v, after: after, rank: rank };
  }
  // what a team that says no would take: the smallest thing you could add that gets them to yes (a pick, or a player)
  function counters(c) {
    var out = [];
    (c.partners || []).forEach(function (pt) {
      if (pt.yes) return;
      var n = c.partners.length, gap = (pt.give * 0.95 - 0.5 - pt.get) * n, opts = [];
      [2027, 2028, 2029, 2030, 2031, 2032].forEach(function (y) { [1, 2].forEach(function (rd) {
        if (deal.picks.some(function (k) { return k.year === y && k.round === rd; })) return;
        opts.push({ v: pickValue({ year: y, round: rd }, pt.rebuilding), label: y + " " + (rd === 1 ? "1st" : "2nd"), act: "pick", y: y, r: rd });
      }); });
      S.roster.forEach(function (p) {
        if (p === S.star || deal.out.indexOf(p) >= 0) return;
        var v = value(p, pt.rebuilding); if (v <= 0) return;
        var test = { out: deal.out.concat([p]) }, outSal = sum(test.out, function (q) { return q.salary; }), inSal = sum(deal.inc, function (q) { return q.salary; });
        if (inSal > maxIncoming(outSal, S.payroll - outSal + inSal) && S.payroll - outSal + inSal > S.cap.cap) return;
        opts.push({ v: v, label: p.name, act: "out", id: p.id, p: p });
      });
      var fits = opts.filter(function (o) { return o.v >= gap; }).sort(function (a, b) { return a.v - b.v; });
      var best = fits[0];
      var gm = B.names[pt.tri].split(" ").pop();
      out.push(best ? { tri: pt.tri, text: gm + ": \u201cAdd " + best.label + " and we have a deal.\u201d", o: best }
        : { tri: pt.tri, text: gm + ": \u201cThat\u2019s not close. Ask for less.\u201d" });
    });
    return out;
  }
  function talent(list) { var r = list.map(function (p) { return p.rating; }).sort(function (a, b) { return b - a; }).slice(0, 8), w = [1, 1, .95, .9, .85, .6, .5, .4]; return r.reduce(function (s, v, i) { return s + v * w[i]; }, 0) / 6.2; }
  function grade() {
    var c = check(), pr = projection(), after = S.roster.filter(function (p) { return deal.out.indexOf(p) < 0; }).concat(deal.inc);
    var fixed = clamp((S.need.rank - pr.rank) / Math.max(1, S.need.rank - 1), -0.5, 1);
    var dT = talent(after) - talent(S.roster);
    var taxB = Math.max(0, S.payroll - S.cap.tax), taxA = Math.max(0, c.after - S.cap.tax), dTax = (taxA - taxB) * 1.6 / 1e6 + (c.after - S.payroll) / 1e6 * 0.4;
    var vIn = sum(deal.inc, function (p) { return value(p); }), vOut = sum(deal.out, function (p) { return value(p); }) + sum(deal.picks, function (k) { return pickValue(k); });
    var parts = { need: clamp(50 + fixed * 50, 0, 100), talent: clamp(55 + dT * 9, 0, 100), cap: clamp(60 - dTax * 1.4, 0, 100), assets: clamp(55 + (vIn - vOut) * 0.9, 0, 100) };
    var score = parts.need * 0.45 + parts.talent * 0.3 + parts.cap * 0.15 + parts.assets * 0.1;
    return { score: Math.round(score * 10) / 10, parts: parts, proj: pr, check: c, dT: dT, letter: score >= 92 ? "A+" : score >= 85 ? "A" : score >= 80 ? "A−" : score >= 76 ? "B+" : score >= 72 ? "B" : score >= 68 ? "B−" : score >= 64 ? "C+" : score >= 58 ? "C" : score >= 50 ? "D" : "F" };
  }

  // ------------------------------------------------------------ the screen
  function face(p) { return '<img class="gmc-face" alt="" loading="lazy" src="' + B.esc(B.nbaFace(p.id)) + '" onerror="this.style.visibility=\'hidden\'">'; }
  function years(p) {
    return '<span class="gmc-yrs">' + p.years.map(function (y, i) {
      if (!y[0]) return i === 0 ? "" : (y[1] ? '<i class="fa">' + B.esc(y[1]) + "</i>" : "");
      return '<i class="' + (y[1] ? "op" : "") + '" title="' + S.C.seasons[i] + (y[1] ? " · " + y[1] : "") + '">' + (y[0] / 1e6).toFixed(1) + (y[1] && /PO|TO|MO/.test(y[1]) ? "<sup>" + y[1] + "</sup>" : "") + "</i>";
    }).join("") + "</span>";
  }
  function row(p, act, on) {
    var N = NEEDS[S.need.key];
    return '<div class="gmc-p' + (on ? " on" : "") + '">' + face(p) + '<div class="gmc-pb"><div class="gmc-l1"><b>' + B.esc(p.name) + '</b><span class="gmc-rt" title="Bradley rating">' + p.rating + "</span></div>" +
      '<div class="gmc-l2">' + B.esc(p.pos) + (p.age ? " · " + p.age : "") + (p.team !== S.tri ? ' · <img class="gmc-tl" alt="" src="' + B.esc(B.logo(p.team)) + '">' + B.esc(p.team) : "") + ' · <span class="gmc-need">' + B.esc(p.rookie ? "rookie" : N.show(p)) + "</span></div>" + years(p) + "</div>" +
      (act ? '<button type="button" class="gmc-add" data-act="' + act + '" data-id="' + p.id + '" aria-label="' + (on ? "Remove " : "Add ") + B.esc(p.name) + '">' + (on ? "&minus;" : "+") + "</button>" : "<span></span>") + "</div>";
  }
  function gauge(pay) {
    var c = S.cap, max = c.apron2 * 1.12, pct = function (v) { return clamp(v / max * 100, 0, 100).toFixed(1) + "%"; };
    return '<div class="gmc-gauge"><div class="gmc-gbar"><b style="width:' + pct(pay) + '"></b>' +
      [["Cap", c.cap], ["Tax", c.tax], ["1st apron", c.apron1], ["2nd apron", c.apron2]].map(function (m, k) { return '<i class="' + (k % 2 ? "dn" : "") + '" style="left:' + pct(m[1]) + '"><span>' + m[0] + "</span></i>"; }).join("") +
      '</div><div class="gmc-gnum">Payroll <b>' + money(pay) + "</b>" + (pay > c.tax ? ' · tax bill <b class="bad">' + money(taxBill(pay - c.tax)) + "</b>" : pay > c.cap ? " · " + money(c.tax - pay) + " under the tax" : " · " + money(c.cap - pay) + " in cap space") + "</div></div>";
  }
  function taxBill(over) { var b = 6064000, rates = [1, 1.25, 3.5, 4.75], bill = 0, i = 0; while (over > 0) { var ch = Math.min(over, b); bill += ch * (rates[i] || rates[3] + 0.5 * (i - 3)); over -= ch; i++; } return bill; }

  var filter = { q: "", chip: "fit" };
  function draw() {
    var t = S.team, N = NEEDS[S.need.key], c = check();
    var out = deal.out, inc = deal.inc;
    root.innerHTML = '<div class="gmc">' +
      '<header class="gmc-top"><img class="gmc-logo" alt="" src="' + B.esc(B.logo(S.tri)) + '"><div class="gmc-tn"><span class="gmc-k">You run · ' + B.esc(B.niceDay(DAY)) + "</span><b>" + B.esc(B.names[S.tri]) + "</b><span>" + t.w + "-" + t.l + " last season · " + S.roster.length + " players under contract</span></div>" + gauge(c.empty ? S.payroll : c.after) + "</header>" +
      '<div class="gmc-grid"><aside class="gmc-side">' +
        '<div class="gmc-card gold"><span class="gmc-k">The need</span><div class="gmc-needname">' + B.esc(N.label) + '</div><div class="gmc-needrank">' + ord(S.need.rank) + " of 30 in " + B.esc(N.short) + "</div></div>" +
        '<div class="gmc-card"><span class="gmc-k">The evidence · 2025-26</span><ul class="gmc-ev">' + S.ranks.slice(0, 5).map(function (r) { var M = NEEDS[r.key]; return "<li><span>" + B.esc(M.label) + '</span><b class="' + (r.rank >= 21 ? "bad" : r.rank <= 10 ? "good" : "") + '">' + (r.v || 0).toFixed(1) + (M.unit || "") + " · " + ord(r.rank) + "</b></li>"; }).join("") + "</ul></div>" +
        '<div class="gmc-card"><span class="gmc-k">Today&rsquo;s rules</span><ul class="gmc-rules">' + S.rules.map(function (r) { return "<li>" + B.esc(r.text) + "</li>"; }).join("") + "</ul></div>" +
      "</aside>" +
      '<main class="gmc-main"><div class="gmc-sides">' +
        '<div class="gmc-card"><span class="gmc-k">' + B.esc(S.tri) + " sends</span>" + (out.length || deal.picks.length ? out.map(function (p) { return row(p, "out", true); }).join("") + deal.picks.map(function (k, i) { return '<div class="gmc-p on pick"><span class="gmc-pk">' + k.year + "</span><div class=\"gmc-pn\"><b>" + k.year + " " + (k.round === 1 ? "1st" : "2nd") + '-round pick</b><span>Own</span></div><button type="button" class="gmc-add" data-act="pick-x" data-i="' + i + '">&minus;</button></div>'; }).join("") : '<p class="gmc-hint">Add players from your roster below.</p>') +
          '<div class="gmc-tot">Out <b>' + money(c.out || 0) + "</b></div></div>" +
        '<div class="gmc-card"><span class="gmc-k">' + B.esc(S.tri) + " gets</span>" + (inc.length ? inc.map(function (p) { return row(p, "inc", true); }).join("") : '<p class="gmc-hint">Find players on other teams below.</p>') +
          '<div class="gmc-tot">In <b>' + money(c.inc || 0) + "</b></div></div></div>" +
        '<div class="gmc-checks">' + (c.empty ? '<span class="gmc-chip">Build a trade to run the checks</span>' :
          '<span class="gmc-chip ' + (c.issues.some(function (x) { return /Salary|combine/.test(x); }) ? "bad" : "good") + '">Salary check</span>' +
          '<span class="gmc-chip ' + (c.size > c.limit ? "bad" : "good") + '">Roster ' + c.size + "/" + c.limit + "</span>" +
          c.partners.map(function (p) { var k = p.give ? clamp(p.get / p.give, 0, 1.6) : 1.6; return '<span class="gmc-accept ' + (p.yes ? "good" : "bad") + '"><img alt="" src="' + B.esc(B.logo(p.tri)) + '"><span class="gmc-meter"><b style="width:' + (k / 1.6 * 100).toFixed(0) + '%"></b><i></i></span>' + (p.yes ? "Yes" : "No") + (p.rebuilding ? " · rebuilding" : "") + "</span>"; }).join("")) + "</div>" +
        (c.issues.length && !c.empty ? '<ul class="gmc-issues">' + c.issues.map(function (x) { return "<li>" + B.esc(x) + "</li>"; }).join("") + "</ul>" : "") +
        (c.empty ? "" : outlook(c)) +
        '<div class="gm-row"><button type="button" class="gm-btn gmc-go"' + (c.ok && !done ? "" : " disabled") + '>Submit trade</button><button type="button" class="gm-btn ghost gmc-clear">Clear</button>' + (B.store("gmc2:" + DAY) ? '<span class="gm-note">Your best today: <b>' + B.store("gmc2:" + DAY).toFixed(1) + "</b></span>" : "") + "</div>" +
        '<div class="gmc-tabs" role="tablist"><button type="button" class="on" data-tab="mine">Your roster</button><button type="button" data-tab="league">League</button></div>' +
        '<div class="gmc-list" data-list="mine">' + S.roster.map(function (p) { return row(p, p === S.star ? null : "out", deal.out.indexOf(p) >= 0); }).join("") +
          '<div class="gmc-picks"><span class="gmc-k">Your picks</span>' + [2027, 2028, 2029, 2030, 2031, 2032].map(function (y) { return [1, 2].map(function (rd) { var on = deal.picks.some(function (k) { return k.year === y && k.round === rd; }); return '<button type="button" class="gmc-pick' + (on ? " on" : "") + '" data-act="pick" data-y="' + y + '" data-r="' + rd + '">' + y + " " + (rd === 1 ? "1st" : "2nd") + "</button>"; }).join(""); }).join("") + "</div></div>" +
        '<div class="gmc-list" data-list="league" hidden><div class="gmc-filter"><input type="search" placeholder="Search any player" value="' + B.esc(filter.q) + '" aria-label="Search players">' +
          [["fit", "Fits the need"], ["exp", "Expiring 2027"], ["cheap", "Under $15M"], ["young", "25 and under"], ["all", "Everyone"]].map(function (ch) { return '<button type="button" class="gmc-fchip' + (filter.chip === ch[0] ? " on" : "") + '" data-chip="' + ch[0] + '">' + ch[1] + "</button>"; }).join("") +
          '</div><div class="gmc-lrows"></div></div>' +
      "</main>" +
      '<aside class="gmc-side gmc-grade"><div class="gmc-card"><span class="gmc-k">Your grade</span><div class="gmc-letter">—</div><p class="gmc-hint">Graded on how much the need shrinks, what it does to the rotation and the books, and what you gave up.</p>' +
        '<ul class="gmc-ev"><li><span>' + B.esc(N.short) + "</span><b>" + S.need.v.toFixed(1) + " → ?</b></li><li><span>League rank</span><b>" + ord(S.need.rank) + " → ?</b></li><li><span>Rotation</span><b>?</b></li></ul></div>" +
        '<div class="gmc-card"><span class="gmc-k">Today&rsquo;s best trades</span><div class="gmc-best"><p class="gmc-hint">Unlocks after you submit.</p></div></div></aside>' +
      "</div></div>";
    wire();
    league();
  }
  // the trade as it stands: the need, the rotation, the wins, the books, and what the other GMs are saying
  function outlook(c) {
    var pr = projection(), N = NEEDS[S.need.key], after = S.roster.filter(function (p) { return deal.out.indexOf(p) < 0; }).concat(deal.inc);
    var dT = talent(after) - talent(S.roster), dW = Math.round(dT * 2.6), w0 = S.team.w;
    var tax0 = S.payroll > S.cap.tax ? taxBill(S.payroll - S.cap.tax) : 0, tax1 = c.after > S.cap.tax ? taxBill(c.after - S.cap.tax) : 0;
    var better = N.low ? pr.after < pr.before : pr.after > pr.before;
    var tile = function (k, v, cls, sub) { return '<div class="gmc-o"><span>' + k + '</span><b class="' + (cls || "") + '">' + v + "</b>" + (sub ? "<em>" + sub + "</em>" : "") + "</div>"; };
    var cs = counters(c);
    return '<div class="gmc-outlook"><span class="gmc-k">Where this trade leaves you</span><div class="gmc-os">' +
      tile(B.esc(N.short), pr.before.toFixed(1) + " → " + pr.after.toFixed(1), better ? "good" : "bad", ord(S.need.rank) + " → " + ord(pr.rank)) +
      tile("Rotation", (dT >= 0 ? "+" : "") + dT.toFixed(1), dT >= 0 ? "good" : "bad", "top-8 talent") +
      tile("Wins", w0 + " → " + (w0 + dW), dW >= 0 ? "good" : "bad", "on last season&rsquo;s " + w0) +
      tile("Tax bill", money(tax1), tax1 > tax0 ? "bad" : tax1 < tax0 ? "good" : "", tax1 === tax0 ? "no change" : (tax1 > tax0 ? "+" : "−") + money(Math.abs(tax1 - tax0)).replace("−", "")) +
      "</div>" +
      (cs.length ? '<div class="gmc-calls">' + cs.map(function (x, k) {
        return '<div class="gmc-call"><img alt="" src="' + B.esc(B.logo(x.tri)) + '"><span>' + B.esc(x.text) + "</span>" + (x.o ? '<button type="button" class="gm-btn ghost gmc-take" data-k="' + k + '">Add it</button>' : "") + "</div>";
      }).join("") + "</div>" : "") + "</div>";
  }
  function league() {
    var box = root.querySelector(".gmc-lrows"); if (!box) return;
    var N = NEEDS[S.need.key], q = B.fold(filter.q.trim());
    var list = S.players.filter(function (p) { return p.team !== S.tri; });
    if (q) list = list.filter(function (p) { return B.fold(p.name).indexOf(q) >= 0 || B.fold(B.names[p.team] || "").indexOf(q) >= 0; });
    if (filter.chip === "exp") list = list.filter(function (p) { return !p.years[1][0] || /PO|TO/.test(p.years[1][1]); });
    if (filter.chip === "cheap") list = list.filter(function (p) { return p.salary < 15e6; });
    if (filter.chip === "young") list = list.filter(function (p) { return p.age && p.age <= 25; });
    list.sort(filter.chip === "fit" ? function (a, b) { return (b.rookie ? -9 : N.fit(b)) - (a.rookie ? -9 : N.fit(a)); } : function (a, b) { return b.rating - a.rating; });
    box.innerHTML = list.slice(0, 60).map(function (p) { return row(p, "inc", deal.inc.indexOf(p) >= 0); }).join("") || '<p class="gmc-hint">No one matches.</p>';
    box.querySelectorAll(".gmc-add").forEach(function (b) { b.addEventListener("click", act); });
  }
  function act(e) {
    var b = e.currentTarget, a = b.getAttribute("data-act"), id = +b.getAttribute("data-id"), tab = (root.querySelector(".gmc-tabs .on") || {}).getAttribute ? root.querySelector(".gmc-tabs .on").getAttribute("data-tab") : "mine";
    var find = function (list) { return list.filter(function (p) { return p.id === id; })[0]; };
    if (a === "out") { var p = find(S.roster); var i = deal.out.indexOf(p); if (i >= 0) deal.out.splice(i, 1); else deal.out.push(p); }
    if (a === "inc") { var q = find(S.players); var j = deal.inc.indexOf(q); if (j >= 0) deal.inc.splice(j, 1); else if (deal.inc.length < 3) deal.inc.push(q); }
    if (a === "pick") { var y = +b.getAttribute("data-y"), rd = +b.getAttribute("data-r"), k = deal.picks.findIndex(function (x) { return x.year === y && x.round === rd; }); if (k >= 0) deal.picks.splice(k, 1); else deal.picks.push({ year: y, round: rd }); }
    if (a === "pick-x") deal.picks.splice(+b.getAttribute("data-i"), 1);
    var sy = window.scrollY; done = false; draw(); setTab(tab); window.scrollTo(0, sy);
  }
  function setTab(t) {
    root.querySelectorAll(".gmc-tabs button").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-tab") === t); });
    root.querySelectorAll(".gmc-list").forEach(function (l) { l.hidden = l.getAttribute("data-list") !== t; });
  }
  function wire() {
    root.querySelectorAll(".gmc-add, .gmc-pick").forEach(function (b) { b.addEventListener("click", act); });
    root.querySelectorAll(".gmc-tabs button").forEach(function (b) { b.addEventListener("click", function () { setTab(b.getAttribute("data-tab")); }); });
    var inp = root.querySelector(".gmc-filter input");
    inp.addEventListener("input", function () { filter.q = inp.value; league(); });
    root.querySelectorAll(".gmc-fchip").forEach(function (b) { b.addEventListener("click", function () { filter.chip = b.getAttribute("data-chip"); root.querySelectorAll(".gmc-fchip").forEach(function (x) { x.classList.toggle("on", x === b); }); league(); }); });
    root.querySelector(".gmc-clear").addEventListener("click", function () { deal = { out: [], picks: [], inc: [] }; done = false; draw(); });
    root.querySelector(".gmc-go").addEventListener("click", submit);
    var cs = null;
    root.querySelectorAll(".gmc-take").forEach(function (b) {
      b.addEventListener("click", function () {
        cs = cs || counters(check()); var o = (cs[+b.getAttribute("data-k")] || {}).o; if (!o) return;
        if (o.act === "pick") deal.picks.push({ year: o.y, round: o.r }); else if (deal.out.indexOf(o.p) < 0) deal.out.push(o.p);
        var sy = window.scrollY; done = false; draw(); window.scrollTo(0, sy);
      });
    });
  }
  function submit() {
    var g = grade(); if (!g.check.ok) return;
    done = true;
    var best = B.store("gmc2:" + DAY); if (best == null || g.score > best) B.store("gmc2:" + DAY, g.score);
    var N = NEEDS[S.need.key], box = root.querySelector(".gmc-grade");
    var bar = function (label, rank) { return '<div class="gmc-rbar"><span>' + label + '</span><i><b style="width:' + ((31 - rank) / 30 * 100).toFixed(0) + '%"></b></i><em>' + ord(rank) + "</em></div>"; };
    box.innerHTML = '<div class="gmc-card gold"><span class="gmc-k">Your grade</span><div class="gmc-letter on">' + g.letter + '</div><div class="gmc-score">' + g.score.toFixed(1) + " / 100</div>" +
      bar("Before", S.need.rank) + bar("After", g.proj.rank) +
      '<ul class="gmc-ev"><li><span>' + B.esc(N.short) + "</span><b>" + g.proj.before.toFixed(1) + " → " + g.proj.after.toFixed(1) + "</b></li>" +
      "<li><span>Need fixed</span><b>" + g.parts.need.toFixed(0) + "</b></li><li><span>Rotation</span><b>" + (g.dT >= 0 ? "+" : "") + g.dT.toFixed(1) + " · " + g.parts.talent.toFixed(0) + "</b></li>" +
      "<li><span>Books</span><b>" + money(g.check.after - S.payroll) + " · " + g.parts.cap.toFixed(0) + "</b></li><li><span>Value</span><b>" + g.parts.assets.toFixed(0) + "</b></li></ul>" +
      '<div class="gm-row"><button type="button" class="gm-btn gmc-post">Post to the leaderboard</button></div><p class="gm-note gmc-saved"></p></div>' +
      '<div class="gmc-card"><span class="gmc-k">Today&rsquo;s best trades</span><div class="gmc-best"></div></div>';
    root.querySelector(".gmc-go").disabled = true;
    bestTrades(box.querySelector(".gmc-best"));
    box.querySelector(".gmc-post").addEventListener("click", function () {
      var btn = this; btn.disabled = true;
      var sent = deal.out.map(function (p) { return p.name; }).concat(deal.picks.map(function (k) { return k.year + " " + (k.round === 1 ? "1st" : "2nd"); }));
      B.askName().then(function (n) {
        return B.submit(GAME, DAY, { name: n, score: g.score, extra: { out: sent.join(", "), in: deal.inc.map(function (p) { return p.name; }).join(", "), grade: g.letter },
          detail: { team: S.tri, need: S.need.key, out: sent, in: deal.inc.map(function (p) { return p.name + " (" + p.team + ")"; }), rank: [S.need.rank, g.proj.rank] } });
      }).then(function (r) { box.querySelector(".gmc-saved").textContent = r.rank ? "Posted: #" + r.rank + " today." : "Saved."; board(); bestTrades(box.querySelector(".gmc-best")); });
    });
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  function bestTrades(el) {
    B.board(GAME, DAY).then(function (b) {
      el.innerHTML = (b.board || []).slice(0, 5).map(function (r) { return '<div class="gmc-bt"><b>' + (+r.score).toFixed(1) + "</b><span>" + B.esc((r.extra || {}).out || "") + " → " + B.esc((r.extra || {}).in || "") + "</span><em>" + B.esc(r.name) + "</em></div>"; }).join("") || '<p class="gmc-hint">No trades posted yet today.</p>';
    });
  }
  function board() { B.renderBoard(document.getElementById("gmc-board"), GAME, DAY, { cols: [["grade", "Grade"], ["out", "Sent"], ["in", "Got"]], format: function (s) { return (+s).toFixed(1); } }); }

  root.innerHTML = '<p class="gm-empty">Loading today&rsquo;s front office…</p>';
  load().then(function () { B.preload(S.roster.map(function (p) { return B.nbaFace(p.id); })); draw(); })
    .catch(function (e) { root.innerHTML = '<p class="gm-empty">Couldn&rsquo;t load today&rsquo;s challenge right now.</p>'; if (window.console) console.error(e); });
  board();
})();
