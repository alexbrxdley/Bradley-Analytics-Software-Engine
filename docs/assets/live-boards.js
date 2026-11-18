/* Live Leaderboards, under the home page's live windows: one big window that opens from its button.

   Players | Teams across the top, then:
   - Players: Leaderboards (the top 10 in a stat; the Bradley 3-Point Shooting Rating first) and Season Averages (every
     player's per-game numbers in one sortable, searchable table).
   - Teams: Leaderboards, Season Averages (all 30 teams) and Standings (both conferences, by seed).
   Everything is read straight from ESPN's public NBA feeds in the visitor's browser, and read again every two minutes
   while the window is open, so it follows the night's games.

   The Bradley 3-Point Shooting Rating here is worked out from this season's totals with the dashboard's formula
   (python/bradley_ratings.py, settings.json): each qualified shooter's 3P% -- pulled toward the league average by 100
   "average" attempts, so a small sample can't top the list -- and his threes attempted per 36 minutes are each
   percentile-ranked against the league, then blended 70% / 30% into a 0-100 score. Current season only; the qualifier is
   30 attempts, scaled down early in the season (3 attempts per game played so far, never under 5). */
(function () {
  "use strict";
  var box = document.getElementById("live-boards");
  if (!box || !window.fetch) return;
  var LEADERS = "https://site.api.espn.com/apis/site/v3/sports/basketball/nba/leaders";
  var PLAYERS = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/statistics/byathlete?region=us&lang=en&contentorigin=espn&isqualified=false&page=1&limit=1000&sort=offensive.avgPoints:desc";
  var TEAMS = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/statistics/byteam?region=us&lang=en&contentorigin=espn&sort=team.offensive.avgPoints:desc";
  var STANDINGS = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings";
  var REFRESH = 120e3;
  var RATING = { minAttempts: 30, perGame: 3, floor: 5, k: 100, pctWeight: 0.7, volWeight: 0.3 };
  var CELTICS = "https://www.2kratings.com/wp-content/uploads/Boston-Celtics-Current-Logo.svg";   // (the Celtics' logo rule)
  var PLAYER_STATS = [["pointsPerGame", "Points"], ["reboundsPerGame", "Rebounds"], ["assistsPerGame", "Assists"], ["stealsPerGame", "Steals"],
    ["blocksPerGame", "Blocks"], ["3PointsMadePerGame", "3-Pointers"], ["fieldGoalPercentage", "FG%"], ["3PointPct", "3P%"],
    ["FreeThrowPct", "FT%"], ["PER", "PER"], ["doubleDouble", "Double-doubles"], ["minutesPerGame", "Minutes"]];
  // team leaderboards: [key, label, decimals, lowest first]
  var TEAM_STATS = [["pts", "Points", 1], ["opp", "Opp. points", 1, true], ["diff", "Point diff.", 1], ["reb", "Rebounds", 1], ["ast", "Assists", 1],
    ["stl", "Steals", 1], ["blk", "Blocks", 1], ["tpm", "3-Pointers", 1], ["fgp", "FG%", 1], ["tpp", "3P%", 1], ["ftp", "FT%", 1], ["to", "Turnovers", 1, true]];
  var P_COLS = [["gp", "GP", 0], ["min", "MIN", 1], ["pts", "PTS", 1], ["reb", "REB", 1], ["ast", "AST", 1], ["stl", "STL", 1], ["blk", "BLK", 1], ["to", "TO", 1],
    ["fgp", "FG%", 1], ["tpm", "3PM", 1], ["tpp", "3P%", 1], ["ftp", "FT%", 1], ["b3", "B3PT", 1]];
  var T_COLS = [["gp", "GP", 0], ["pts", "PTS", 1], ["opp", "OPP", 1], ["diff", "DIFF", 1], ["reb", "REB", 1], ["ast", "AST", 1], ["stl", "STL", 1], ["blk", "BLK", 1],
    ["to", "TO", 1], ["fgp", "FG%", 1], ["tpm", "3PM", 1], ["tpp", "3P%", 1], ["ftp", "FT%", 1]];

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  function getJSON(u) { return fetch(u, { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }); }
  function logoOf(tri, href) {
    if (String(tri).toUpperCase() === "BOS") return CELTICS;
    return href || (tri ? "https://a.espncdn.com/i/teamlogos/nba/500/" + String(tri).toLowerCase() + ".png" : "");
  }
  function fmt(v, d) { return v == null || isNaN(v) ? "–" : (+v).toFixed(d); }

  // ------------------------------------------------------------ the data (each read at most once per refresh)
  var data = {}, fetchedAt = {};
  function load(key, url, shape) {
    if (data[key] && Date.now() - fetchedAt[key] < REFRESH) return data[key];
    var p = getJSON(url).then(shape);
    p.catch(function () { if (data[key] === p) delete data[key]; });
    data[key] = p; fetchedAt[key] = Date.now();
    return p;
  }
  function percentRanks(vals) {                    // pandas rank(pct=True): average rank of ties / n
    var idx = vals.map(function (v, i) { return [v, i]; }).sort(function (a, b) { return a[0] - b[0]; });
    var out = new Array(vals.length), i = 0, n = vals.length;
    while (i < n) {
      var j = i; while (j + 1 < n && idx[j + 1][0] === idx[i][0]) j++;
      var r = ((i + 1) + (j + 1)) / 2 / n;
      for (var k = i; k <= j; k++) out[idx[k][1]] = r;
      i = j + 1;
    }
    return out;
  }
  function players() {
    return load("players", PLAYERS, function (d) {
      var at = {};
      (d.categories || []).forEach(function (c) { if (c.names) at[c.name] = c.names; });
      function stat(a, cat, name) {
        var c = (a.categories || []).filter(function (x) { return x.name === cat; })[0], i = (at[cat] || []).indexOf(name);
        if (!c || i < 0) return null;
        var v = (c.values || c.totals || [])[i];
        return v == null || v === "" ? null : parseFloat(v);
      }
      var rows = (d.athletes || []).map(function (a) {
        var p = a.athlete || {};
        return { id: p.id, name: p.displayName, short: p.shortName, team: p.teamShortName || "", pos: (p.position && p.position.abbreviation) || "",
          head: (p.headshot && p.headshot.href) || "", gp: stat(a, "general", "gamesPlayed"), min: stat(a, "general", "avgMinutes"),
          mins: stat(a, "general", "minutes"), pts: stat(a, "offensive", "avgPoints"), reb: stat(a, "general", "avgRebounds"),
          ast: stat(a, "offensive", "avgAssists"), stl: stat(a, "defensive", "avgSteals"), blk: stat(a, "defensive", "avgBlocks"),
          to: stat(a, "offensive", "avgTurnovers"), fgp: stat(a, "offensive", "fieldGoalPct"), tpm: stat(a, "offensive", "avgThreePointFieldGoalsMade"),
          tpp: stat(a, "offensive", "threePointFieldGoalPct"), ftp: stat(a, "offensive", "freeThrowPct"),
          m3: stat(a, "offensive", "threePointFieldGoalsMade") || 0, x3: stat(a, "offensive", "threePointFieldGoalsAttempted") || 0, b3: null };
      });
      // the Bradley 3-Point Shooting Rating
      var maxGp = rows.reduce(function (m, r) { return Math.max(m, r.gp || 0); }, 0);
      var need = Math.max(RATING.floor, Math.min(RATING.minAttempts, Math.round(maxGp * RATING.perGame)));
      var pool = rows.filter(function (r) { return r.x3 >= need && r.mins > 0; });
      if (pool.length >= 5) {
        var lgM = 0, lgX = 0; pool.forEach(function (r) { lgM += r.m3; lgX += r.x3; });
        var avg = lgX ? lgM / lgX : 0.36;
        var pr = percentRanks(pool.map(function (r) { return (r.m3 + RATING.k * avg) / (r.x3 + RATING.k); }));
        var vr = percentRanks(pool.map(function (r) { return r.x3 * 36 / r.mins; }));
        pool.forEach(function (r, i) { r.b3 = 100 * (RATING.pctWeight * pr[i] + RATING.volWeight * vr[i]); });
      }
      return { rows: rows, need: need };
    });
  }
  function leaders() {
    return load("leaders", LEADERS, function (d) { return ((d.leaders || {}).categories) || d.categories || []; });
  }
  function teams() {
    return load("teams", TEAMS, function (d) {
      var names = {};
      (d.categories || []).forEach(function (c) { if (c.names && !names[c.name]) names[c.name] = c.names; });
      return (d.teams || []).map(function (t) {
        function stat(cat, name, opp) {
          var c = (t.categories || []).filter(function (x) {
            var isOpp = String(x.splitId) === "900" || /^opponent/i.test(x.displayName || "");
            return x.name === cat && (!!opp === isOpp);
          })[0];
          var i = (names[cat] || []).indexOf(name);
          if (!c || i < 0) return null;
          var v = (c.values || c.totals || [])[i];
          return v == null || v === "" ? null : parseFloat(v);
        }
        var tm = t.team || {}, pts = stat("offensive", "avgPoints"), opp = stat("offensive", "avgPoints", true);
        return { tri: tm.abbreviation, name: tm.displayName, short: tm.shortDisplayName || tm.name, logo: logoOf(tm.abbreviation, tm.logos && tm.logos[0] && tm.logos[0].href),
          gp: stat("general", "gamesPlayed"), pts: pts, opp: opp, diff: pts != null && opp != null ? pts - opp : null,
          reb: stat("general", "avgRebounds"), ast: stat("offensive", "avgAssists"), stl: stat("defensive", "avgSteals"), blk: stat("defensive", "avgBlocks"),
          to: stat("offensive", "avgTurnovers"), fgp: stat("offensive", "fieldGoalPct"), tpm: stat("offensive", "avgThreePointFieldGoalsMade"),
          tpp: stat("offensive", "threePointFieldGoalPct"), ftp: stat("offensive", "freeThrowPct") };
      });
    });
  }
  function standings() {
    return load("standings", STANDINGS, function (d) {
      return (d.children || []).map(function (conf) {
        var es = ((conf.standings || {}).entries || []).map(function (e) {
          var st = {}; (e.stats || []).forEach(function (s) { st[s.name] = s; if (s.type && !st[s.type]) st[s.type] = s; });
          return { team: e.team || {}, st: st, seed: +((st.playoffSeed || {}).value) || 99 };
        }).sort(function (a, b) { return a.seed - b.seed; });
        return { name: conf.name, entries: es };
      });
    });
  }

  // ------------------------------------------------------------ drawing
  function lbRow(rank, name, sub, head, tri, logo, val, frac, extra) {
    return '<li class="lb-row"><span class="lb-rk">' + rank + "</span>" +
      (head != null ? '<span class="lb-face"><img loading="lazy" alt="" src="' + esc(head) + '" onerror="this.style.visibility=\'hidden\'"></span>'
        : '<span class="lb-face team"><img loading="lazy" alt="" src="' + esc(logo) + '"></span>') +
      '<span class="lb-nm"><b>' + esc(name) + "</b><span>" + (logo && head != null ? '<img class="lb-logo" alt="" src="' + esc(logo) + '">' : "") + esc(tri || "") +
      (sub ? " · " + esc(sub) : "") + "</span></span>" +
      '<span class="lb-val"><b>' + esc(val) + "</b>" + (extra ? "<i>" + esc(extra) + "</i>" : "") + "</span>" +
      '<span class="lb-bar"><i style="width:' + Math.max(4, Math.min(100, frac * 100)).toFixed(1) + '%"></i></span></li>';
  }
  function msg(t) { return '<p class="lb-empty">' + esc(t) + "</p>"; }
  function chips(list, cur, gold) {
    return '<div class="lb-tabs" role="tablist">' + list.map(function (c, i) {
      return '<button type="button" role="tab" class="lb-tab' + (gold && i === 0 ? " gold" : "") + (c[0] === cur ? " on" : "") + '" data-stat="' + esc(c[0]) +
        '" aria-selected="' + (c[0] === cur) + '">' + esc(c[1]) + "</button>";
    }).join("") + "</div>";
  }

  // sortable table: cols [key, label, decimals]; first column is the name
  function table(rows, cols, sort, nameCell, filter) {
    var key = sort.key, dir = sort.dir;
    var list = rows.filter(filter || function () { return true; }).slice().sort(function (a, b) {
      var x = a[key], y = b[key];
      if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
      return dir * (y - x);
    });
    return '<div class="lbx-tablewrap"><table class="lbx-table"><thead><tr><th class="rk">#</th><th class="nm">' + (sort.nameLabel || "Player") + "</th>" +
      cols.map(function (c) {
        return '<th data-key="' + c[0] + '" class="' + (c[0] === key ? "on" : "") + '" title="Sort by ' + c[1] + '">' + c[1] +
          (c[0] === key ? '<span class="ar">' + (dir > 0 ? "▼" : "▲") + "</span>" : "") + "</th>";
      }).join("") + "</tr></thead><tbody>" +
      (list.length ? list.map(function (r, i) {
        return "<tr><td class=\"rk\">" + (i + 1) + '</td><td class="nm">' + nameCell(r) + "</td>" +
          cols.map(function (c) { return '<td class="' + (c[0] === key ? "on" : "") + '">' + fmt(r[c[0]], c[2]) + "</td>"; }).join("") + "</tr>";
      }).join("") : '<tr><td colspan="' + (cols.length + 2) + '" class="lbx-none">No players match.</td></tr>') + "</tbody></table></div>";
  }

  // ------------------------------------------------------------ the window
  var win = box.querySelector(".lbx-win"), openBtn = box.querySelector(".lbx-open"), body = box.querySelector(".lbx-body"),
    seg = box.querySelector(".lbx-seg"), views = box.querySelector(".lbx-views");
  var state = { who: "players", view: "leaders", pstat: "b3pt", tstat: "pts", psort: { key: "pts", dir: 1 }, tsort: { key: "pts", dir: 1, nameLabel: "Team" }, q: "" };
  var VIEWS = { players: [["leaders", "Leaderboards"], ["averages", "Season Averages"]],
    teams: [["leaders", "Leaderboards"], ["averages", "Season Averages"], ["standings", "Standings"]] };
  var timer = null, drawSeq = 0;

  function drawTabs() {
    Array.prototype.forEach.call(seg.querySelectorAll("button"), function (b) {
      var on = b.getAttribute("data-who") === state.who;
      b.classList.toggle("on", on); b.setAttribute("aria-selected", on);
    });
    views.innerHTML = VIEWS[state.who].map(function (v) {
      return '<button type="button" role="tab" data-view="' + v[0] + '" class="' + (v[0] === state.view ? "on" : "") + '" aria-selected="' + (v[0] === state.view) + '">' + v[1] + "</button>";
    }).join("");
  }
  function draw(keepScroll) {
    var seq = ++drawSeq, scrollEl = body.querySelector(".lbx-tablewrap"), top = keepScroll && scrollEl ? scrollEl.scrollTop : 0, left = keepScroll && scrollEl ? scrollEl.scrollLeft : 0;
    if (!body.innerHTML) body.innerHTML = msg("Loading…");
    var done = function (html) {
      if (seq !== drawSeq) return;
      body.innerHTML = html;
      var w = body.querySelector(".lbx-tablewrap"); if (w && keepScroll) { w.scrollTop = top; w.scrollLeft = left; }
      var s = body.querySelector(".lbx-search input"); if (s && document.activeElement !== s && keepScroll === "search") { s.focus(); s.setSelectionRange(s.value.length, s.value.length); }
    };
    var fail = function () { done(msg("Couldn't load the numbers right now. They'll be tried again in a moment.")); };
    var P = state.who === "players", V = state.view;
    if (P && V === "leaders") {
      var list = [["b3pt", "Bradley 3PT Rating"]].concat(PLAYER_STATS);
      if (state.pstat === "b3pt") {
        players().then(function (d) {
          var top = d.rows.filter(function (r) { return r.b3 != null; }).sort(function (a, b) { return b.b3 - a.b3; }).slice(0, 10);
          done(chips(list, "b3pt", true) + (top.length ? '<ol class="lb-list">' + top.map(function (r, i) {
            return lbRow(i + 1, r.name, r.pos, r.head, r.team, logoOf(r.team), r.b3.toFixed(1), r.b3 / 100, (r.tpp != null ? r.tpp.toFixed(1) : "–") + "% on " + Math.round(r.x3) + " 3PA");
          }).join("") + "</ol>" : msg("Not enough threes taken yet this season.")) +
            '<div class="lb-note">0-100. 70% shooting (3P%, adjusted for how many threes it\'s built on), 30% volume (threes per 36 minutes), each ranked against the league. This season only; at least ' + d.need + " three-point attempts.</div>");
        }).catch(fail);
      } else {
        leaders().then(function (cats) {
          var c = cats.filter(function (x) { return x.name === state.pstat; })[0];
          var ls = c ? (c.leaders || []).slice(0, 10) : [], max = ls.length ? Math.max.apply(null, ls.map(function (l) { return +l.value || 0; })) : 1;
          done(chips(list, state.pstat, true) + (ls.length ? '<ol class="lb-list">' + ls.map(function (l, i) {
            var a = l.athlete || {}, tm = l.team || {}, tri = tm.abbreviation || "";
            return lbRow(i + 1, a.displayName, (a.position && a.position.abbreviation) || "", (a.headshot && a.headshot.href) || "", tri,
              logoOf(tri, tm.logos && tm.logos[0] && tm.logos[0].href), l.displayValue, max ? (+l.value || 0) / max : 0);
          }).join("") + "</ol>" : msg("No leaders yet.")) + '<div class="lb-note">' + esc((c && c.displayName) || "") + ", qualified players.</div>");
        }).catch(fail);
      }
    } else if (P && V === "averages") {
      players().then(function (d) {
        var q = state.q.trim().toLowerCase();
        done('<div class="lbx-search"><input type="search" placeholder="Search players or teams" aria-label="Search players or teams" value="' + esc(state.q) + '"><span>' +
          d.rows.length + " players, per game</span></div>" +
          table(d.rows, P_COLS, state.psort, function (r) {
            return '<img class="lb-logo" alt="" loading="lazy" src="' + esc(logoOf(r.team)) + '"><b>' + esc(r.name) + '</b><span class="tm">' + esc(r.team) + "</span>";
          }, q ? function (r) { return (r.name + " " + r.team).toLowerCase().indexOf(q) >= 0; } : null) +
          '<div class="lb-note">Tap a column to sort. B3PT: the Bradley 3-Point Shooting Rating (shooters with at least ' + d.need + " attempts).</div>");
      }).catch(fail);
    } else if (!P && V === "leaders") {
      teams().then(function (rows) {
        var st = TEAM_STATS.filter(function (x) { return x[0] === state.tstat; })[0] || TEAM_STATS[0];
        var top = rows.filter(function (r) { return r[st[0]] != null; }).sort(function (a, b) { return st[3] ? a[st[0]] - b[st[0]] : b[st[0]] - a[st[0]]; }).slice(0, 10);
        var vals = top.map(function (r) { return r[st[0]]; }), lo = Math.min.apply(null, vals.concat([0])), hi = Math.max.apply(null, vals);
        done(chips(TEAM_STATS, st[0]) + (top.length ? '<ol class="lb-list">' + top.map(function (r, i) {
          var v = r[st[0]], frac = st[3] ? (v ? Math.min.apply(null, vals) / v : 0) : (hi - lo ? (v - lo) / (hi - lo) : 1);
          return lbRow(i + 1, r.name, r.gp != null ? r.gp + " GP" : "", null, r.tri, r.logo, (st[0] === "diff" && v > 0 ? "+" : "") + fmt(v, st[2]), frac);
        }).join("") + "</ol>" : msg("No team numbers yet.")) + '<div class="lb-note">' + esc(st[1]) + " per game" + (st[3] ? ", lowest first." : ".") + "</div>");
      }).catch(fail);
    } else if (!P && V === "averages") {
      teams().then(function (rows) {
        done(table(rows, T_COLS, state.tsort, function (r) {
          return '<img class="lb-logo" alt="" loading="lazy" src="' + esc(r.logo) + '"><b>' + esc(r.short || r.name) + '</b><span class="tm">' + esc(r.tri) + "</span>";
        }) + '<div class="lb-note">Per game. OPP: points allowed. Tap a column to sort.</div>');
      }).catch(fail);
    } else {
      standings().then(function (confs) {
        done('<div class="sd">' + confs.map(function (conf) {
          var v = function (x, k) { return x.st[k] ? x.st[k].displayValue : "–"; };
          return '<div class="sd-conf"><h3>' + esc(conf.name) + '</h3><table class="sd-table"><thead><tr><th class="l">Team</th><th>W</th><th>L</th><th>PCT</th><th>GB</th><th class="x">L10</th><th>STRK</th></tr></thead><tbody>' +
            conf.entries.map(function (x, i) {
              var t = x.team, tri = t.abbreviation || "";
              return '<tr class="' + (i === 5 ? "cut6" : i === 9 ? "cut10" : "") + '"><td class="l"><span class="sd-seed">' + (i + 1) + '</span><img alt="" loading="lazy" src="' + esc(logoOf(tri, t.logos && t.logos[0] && t.logos[0].href)) + '">' +
                '<span class="sd-nm">' + esc(t.shortDisplayName || t.displayName || tri) + '</span><span class="sd-tri">' + esc(tri) + "</span></td>" +
                "<td>" + v(x, "wins") + "</td><td>" + v(x, "losses") + "</td><td>" + v(x, "winPercent") + "</td><td>" + v(x, "gamesBehind") + '</td><td class="x">' +
                (x.st["Last Ten Games"] ? x.st["Last Ten Games"].displayValue : (x.st.lasttengames ? x.st.lasttengames.displayValue : "–")) + "</td><td>" + v(x, "streak") + "</td></tr>";
            }).join("") + "</tbody></table></div>";
        }).join("") + '<div class="sd-key">Top 6: playoffs (gold line). 7-10: play-in.</div></div>');
      }).catch(fail);
    }
  }

  function setOpen(on, quiet) {
    win.hidden = !on;
    openBtn.setAttribute("aria-expanded", on);
    openBtn.classList.toggle("open", on);
    clearInterval(timer); timer = null;
    if (on) {
      drawTabs(); draw();
      timer = setInterval(function () { if (!document.hidden) draw(true); }, REFRESH + 1000);
      var r = win.getBoundingClientRect();
      if (!quiet && r.top > window.innerHeight - 120) win.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
  openBtn.addEventListener("click", function () { setOpen(win.hidden); });
  window.BABoards = { open: setOpen, isOpen: function () { return !win.hidden; } };
  var closeBtn = box.querySelector(".lbx-close");
  if (closeBtn) closeBtn.addEventListener("click", function () { setOpen(false); openBtn.focus(); });
  seg.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-who]"); if (!b || b.getAttribute("data-who") === state.who) return;
    state.who = b.getAttribute("data-who"); state.view = "leaders"; body.innerHTML = ""; drawTabs(); draw();
  });
  views.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-view]"); if (!b) return;
    state.view = b.getAttribute("data-view"); body.innerHTML = ""; drawTabs(); draw();
  });
  body.addEventListener("click", function (e) {
    var c = e.target.closest(".lb-tab[data-stat]");
    if (c) { if (state.who === "players") state.pstat = c.getAttribute("data-stat"); else state.tstat = c.getAttribute("data-stat"); draw(); return; }
    var th = e.target.closest("th[data-key]");
    if (th) {
      var s = state.who === "players" ? state.psort : state.tsort, k = th.getAttribute("data-key");
      if (s.key === k) s.dir = -s.dir; else { s.key = k; s.dir = 1; }
      draw(true);
    }
  });
  var qTimer = null;
  body.addEventListener("input", function (e) {
    if (!e.target.matches(".lbx-search input")) return;
    state.q = e.target.value;
    clearTimeout(qTimer); qTimer = setTimeout(function () { draw("search"); }, 120);
  });
})();
