/* Bradley Analytics, the app (first draft). Everything here reads the live website and ESPN's public NBA feed, so the
   app keeps up with the website by itself. Settings, favourite teams and draft community posts are kept on the phone. */
(function () {
  "use strict";
  var B = window.BAG, $ = function (s, r) { return (r || document).querySelector(s); }, $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = B.esc;
  var SB = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?limit=100&dates=";
  var TEAM = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/";
  var ALL = Object.keys(B.names).sort(function (a, b) { return B.names[a].localeCompare(B.names[b]); });

  // ------------------------------------------------------------ settings (kept on the phone)
  function get(k, d) { try { var v = localStorage.getItem("baapp:" + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }
  function put(k, v) { try { localStorage.setItem("baapp:" + k, JSON.stringify(v)); } catch (e) {} }
  var ACCENTS = [["Gold", "#F5D370", "#B8862B"], ["Silver", "#F2F4F7", "#8E959E"], ["Rose gold", "#F6C6B0", "#B9725A"], ["Emerald", "#7EE2B0", "#1E8F5C"],
                 ["Royal", "#9CC2FF", "#2F5FD0"], ["Crimson", "#FF9A8F", "#C0262C"], ["Purple", "#D5B4FF", "#6F3FC7"]];
  var FLOORS = [["black", "Black parquet"], ["walnut", "Walnut"], ["plain", "Plain"]];
  var S = { accent: get("accent", 0), floor: get("floor", "black"), tilt: get("tilt", true), teams: get("teams", []), name: get("name", ""),
            widgets: get("widgets", ["today", "hubs", "news"]) };
  function applyAccent() {
    var a = ACCENTS[S.accent] || ACCENTS[0], r = document.documentElement.style;
    r.setProperty("--acc1", a[1]); r.setProperty("--acc2", a[2]); r.setProperty("--acc", a[1]);
    var m = $('meta[name="theme-color"]'); if (m) m.content = "#0a0a0a";
  }
  applyAccent();
  function toast(t) { var e = $("#toast"); e.textContent = t; e.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(function () { e.hidden = true; }, 2200); }

  // ------------------------------------------------------------ the floor: black parquet with silver seams that catch
  // the light as the phone tilts (and the whole floor leans a little with it)
  var Floor = (function () {
    var host = $(".bg"), cv = document.createElement("canvas"), cx = cv.getContext("2d");
    host.insertBefore(cv, host.firstChild);
    var base, mV, mH, scratch, W, H, dpr, tx = 0, ty = 0, gx = 0, gy = 0, dirty = true, b0 = null;
    var PAL = {
      black: { tones: ["#141414", "#181818", "#111111", "#1b1b1b", "#161616"], seam: "rgba(120,124,132,.30)", shine: [236, 240, 248], grain: "rgba(255,255,255,.025)" },
      walnut: { tones: ["#21160f", "#271a11", "#1c130c", "#2b1d13", "#241810"], seam: "rgba(150,120,80,.28)", shine: [255, 228, 170], grain: "rgba(255,220,180,.03)" }
    };
    function mk(w, h) { var c = document.createElement("canvas"); c.width = w; c.height = h; return c; }
    function build() {
      dpr = Math.min(2, window.devicePixelRatio || 1);
      W = Math.ceil(innerWidth * 1.18 * dpr); H = Math.ceil(innerHeight * 1.18 * dpr);
      cv.width = W; cv.height = H;
      base = mk(W, H); mV = mk(W, H); mH = mk(W, H); scratch = mk(W, H);
      var p = PAL[S.floor] || PAL.black, g = base.getContext("2d"), v = mV.getContext("2d"), h = mH.getContext("2d");
      if (S.floor === "plain") { g.fillStyle = "#0b0b0b"; g.fillRect(0, 0, W, H); dirty = true; return; }
      // squares of five planks, each square turned against its neighbours (the same floor as Today's Play)
      var sq = Math.round(76 * dpr), pl = sq / 5, rnd = seeded(7);
      v.strokeStyle = h.strokeStyle = "#fff"; v.lineWidth = h.lineWidth = Math.max(1, dpr * 0.9);
      for (var y = 0, r = 0; y < H + sq; y += sq, r++) for (var x = 0, c = 0; x < W + sq; x += sq, c++) {
        var turned = (r + c) % 2 === 1;
        for (var k = 0; k < 5; k++) {
          var bx = turned ? x : x + k * pl, by = turned ? y + k * pl : y, bw = turned ? sq : pl, bh = turned ? pl : sq;
          g.fillStyle = p.tones[(k + r * 2 + c) % 5]; g.fillRect(bx, by, bw, bh);
          // a little wood grain along each plank
          g.strokeStyle = p.grain; g.lineWidth = dpr * 0.6;
          for (var n = 0; n < 3; n++) {
            g.beginPath();
            if (turned) { var yy = by + (n + 0.5 + rnd() * 0.4) * bh / 3.4; g.moveTo(bx, yy); g.bezierCurveTo(bx + bw * .3, yy + rnd() * 2 - 1, bx + bw * .7, yy + rnd() * 2 - 1, bx + bw, yy); }
            else { var xx = bx + (n + 0.5 + rnd() * 0.4) * bw / 3.4; g.moveTo(xx, by); g.bezierCurveTo(xx + rnd() * 2 - 1, by + bh * .3, xx + rnd() * 2 - 1, by + bh * .7, xx, by + bh); }
            g.stroke();
          }
          // the seams: plank edges run with the planks, square edges both ways
          if (turned) { h.beginPath(); h.moveTo(bx, by); h.lineTo(bx + bw, by); h.stroke(); }
          else { v.beginPath(); v.moveTo(bx, by); v.lineTo(bx, by + bh); v.stroke(); }
        }
        if (turned) { v.beginPath(); v.moveTo(x, y); v.lineTo(x, y + sq); v.stroke(); }
        else { h.beginPath(); h.moveTo(x, y); h.lineTo(x + sq, y); h.stroke(); }
      }
      // dark silver seams everywhere; the shine is added on top as the phone tilts
      g.save(); g.globalAlpha = 1; g.globalCompositeOperation = "source-over";
      var tint = mk(W, H), t = tint.getContext("2d");
      t.fillStyle = p.seam; t.fillRect(0, 0, W, H); t.globalCompositeOperation = "destination-in"; t.drawImage(mV, 0, 0); t.drawImage(mH, 0, 0);
      g.drawImage(tint, 0, 0); g.restore();
      dirty = true;
    }
    function seeded(s) { return function () { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; }; }
    function shine(mask, horiz, pos, strength, col) {
      var s = scratch.getContext("2d");
      s.globalCompositeOperation = "source-over"; s.clearRect(0, 0, W, H);
      var L = horiz ? H : W, c = Math.max(0, Math.min(1, pos)), wid = 0.16;
      var gr = horiz ? s.createLinearGradient(0, 0, 0, H) : s.createLinearGradient(0, 0, W, 0);
      var rgb = col.join(",");
      gr.addColorStop(0, "rgba(" + rgb + ",0)");
      gr.addColorStop(Math.max(0, c - wid * 2.2), "rgba(" + rgb + ",0)");
      gr.addColorStop(Math.max(0, c - wid), "rgba(" + rgb + "," + (0.28 * strength) + ")");
      gr.addColorStop(c, "rgba(" + rgb + "," + (0.95 * strength) + ")");
      gr.addColorStop(Math.min(1, c + wid), "rgba(" + rgb + "," + (0.28 * strength) + ")");
      gr.addColorStop(Math.min(1, c + wid * 2.2), "rgba(" + rgb + ",0)");
      gr.addColorStop(1, "rgba(" + rgb + ",0)");
      s.fillStyle = gr; s.fillRect(0, 0, W, H);
      s.globalCompositeOperation = "destination-in"; s.drawImage(mask, 0, 0);
      cx.drawImage(scratch, 0, 0);
      void L;
    }
    function draw() {
      cx.globalCompositeOperation = "source-over";
      cx.drawImage(base, 0, 0);
      if (S.floor !== "plain") {
        var col = (PAL[S.floor] || PAL.black).shine;
        // up-and-down seams catch the light as the phone turns left/right; side-to-side seams as it tips forward/back
        shine(mV, false, 0.5 + gx * 0.62, 0.55 + 0.45 * Math.min(1, Math.abs(gx) * 1.4), col);
        shine(mH, true, 0.5 + gy * 0.62, 0.55 + 0.45 * Math.min(1, Math.abs(gy) * 1.4), col);
      }
      cv.style.transform = S.tilt ? "rotateX(" + (-gy * 5).toFixed(2) + "deg) rotateY(" + (gx * 5).toFixed(2) + "deg) translate(" + (-gx * 14).toFixed(1) + "px," + (-gy * 14).toFixed(1) + "px)" : "none";
    }
    function loop() {
      var ngx = gx + (tx - gx) * 0.12, ngy = gy + (ty - gy) * 0.12;
      if (dirty || Math.abs(ngx - gx) > 0.002 || Math.abs(ngy - gy) > 0.002) { gx = ngx; gy = ngy; draw(); dirty = false; }
      requestAnimationFrame(loop);
    }
    function clamp(v) { return Math.max(-1, Math.min(1, v)); }
    function onOrient(e) {
      if (!S.tilt || e.beta == null) return;
      if (b0 == null) b0 = e.beta;                              // however the phone is being held counts as level
      b0 += (e.beta - b0) * 0.004;                              // (and slowly follows a new way of holding it)
      tx = clamp((e.gamma || 0) / 28); ty = clamp((e.beta - b0) / 28);
    }
    var listening = false;
    function listen() { if (!listening) { listening = true; addEventListener("deviceorientation", onOrient); } }
    function needsAsk() { return window.DeviceOrientationEvent && typeof DeviceOrientationEvent.requestPermission === "function"; }
    function ask() {
      return DeviceOrientationEvent.requestPermission().then(function (r) { if (r === "granted") { listen(); put("motionOK", true); return true; } return false; }).catch(function () { return false; });
    }
    // computers: the mouse stands in for tilting
    addEventListener("mousemove", function (e) { if (!S.tilt || matchMedia("(hover: none)").matches) return; tx = clamp((e.clientX / innerWidth - 0.5) * 2); ty = clamp((e.clientY / innerHeight - 0.5) * 2); });
    var rt; addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(build, 200); });
    build(); requestAnimationFrame(loop);
    if (!needsAsk()) listen();
    return { rebuild: build, needsAsk: needsAsk, ask: ask, listen: listen, still: function () { tx = ty = 0; dirty = true; } };
  })();
  // iPhones ask before an app may read the tilt: one tap, once
  function motionPrompt() {
    if (!S.tilt || !Floor.needsAsk()) return;
    if (get("motionOK", false)) {                                // (already allowed: it still needs a tap each launch)
      var once = function () { Floor.ask(); removeEventListener("touchend", once, true); };
      addEventListener("touchend", once, true); return;
    }
    var box = document.createElement("div"); box.className = "motion-ask";
    box.innerHTML = '<span>Let the floor move as you tilt your phone?</span><button class="chip" type="button">Not now</button><button class="btn" type="button">Allow</button>';
    document.body.appendChild(box);
    box.querySelector(".btn").addEventListener("click", function () { Floor.ask().then(function () { box.remove(); }); });
    box.querySelector(".chip").addEventListener("click", function () { box.remove(); });
  }

  // ------------------------------------------------------------ pages and the tab bar
  var current = "home";
  function go(v) {
    if (!$("#v-" + v)) return;
    current = v;
    $$(".view").forEach(function (s) { s.classList.toggle("on", s.id === "v-" + v); });
    $$(".tabs button").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-go") === v); });
    $("main").scrollTop = 0;
    if (v === "mine") drawMine();
    if (v === "community") drawPosts();
    if (v === "profile") drawProfile();
    if (navigator.vibrate) try { navigator.vibrate(5); } catch (e) {}
  }
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-go],[data-open],[data-ext],[data-close]");
    if (!t) return;
    if (t.hasAttribute("data-go")) go(t.getAttribute("data-go"));
    else if (t.hasAttribute("data-open")) openPage(t.getAttribute("data-open"), (t.querySelector("b") || t).textContent);
    else if (t.hasAttribute("data-ext")) window.open(t.getAttribute("data-ext"), "_blank", "noopener");
    else if (t.hasAttribute("data-close")) { var sh = t.closest(".sheet"); sh.hidden = true; var f = sh.querySelector("iframe"); if (f) f.src = "about:blank"; }
  });
  // a website page (the games, portfolio...) opened over the app
  function openPage(url, title) { var v = $("#viewer"); v.querySelector(".sheet-t").textContent = title || ""; v.querySelector("iframe").src = url; v.hidden = false; }

  // ------------------------------------------------------------ today's games: the ticker and a row per game
  var games = [], gameTimer = null;
  function etDay() { return B.day().replace(/-/g, ""); }
  function parse(ev) {
    var c = (ev.competitions || [])[0] || {}, st = (ev.status || c.status || {}).type || {};
    var side = function (ha) { var t = (c.competitors || []).filter(function (x) { return x.homeAway === ha; })[0] || {}; var tm = t.team || {};
      return { tri: tm.abbreviation || "", name: tm.shortDisplayName || tm.displayName || "", logo: tm.logo || B.logo(tm.abbreviation || ""), score: t.score, rec: ((t.records || [])[0] || {}).summary || "" }; };
    return { id: ev.id, when: ev.date, day: (ev.date || "").slice(0, 10), home: side("home"), away: side("away"), state: st.state, live: st.state === "in", final: st.state === "post",
             detail: st.shortDetail || st.detail || "", clock: (ev.status || {}).displayClock, period: (ev.status || {}).period };
  }
  function loadGames() {
    return B.getJSON(SB + etDay()).then(function (d) {
      var list = (d.events || []).map(parse).sort(function (a, b) { return new Date(a.when) - new Date(b.when); });
      var changed = list.map(function (g) { return g.id; }).join() !== games.map(function (g) { return g.id; }).join();
      games = list;
      drawTicker(); if (changed) drawRows(); else updateRows(); drawStories();
      clearTimeout(gameTimer);
      gameTimer = setTimeout(loadGames, games.some(function (g) { return g.live; }) ? 10000 : 60000);
    }).catch(function () { clearTimeout(gameTimer); gameTimer = setTimeout(loadGames, 20000); if (!games.length) $("#games").innerHTML = '<p class="empty">Couldn&rsquo;t reach the scores. Pull down or check your connection.</p>'; });
  }
  function timeOf(g) { try { return new Date(g.when).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); } catch (e) { return ""; } }
  function status(g) { return g.live ? g.detail : g.final ? "Final" + (g.detail && /OT/.test(g.detail) ? " (" + g.detail.replace(/^Final\/?/, "") + ")" : "") : timeOf(g); }
  function tickItem(g) {
    var a = g.away, h = g.home, started = g.live || g.final, aw = +a.score > +h.score;
    var sc = function (t, win) { return started ? '<span class="s ' + (g.final ? (win ? "win" : "los") : "win") + '">' + esc(t.score) + "</span>" : ""; };
    return '<button class="tk" type="button" data-g="' + g.id + '"><img alt="" src="' + esc(a.logo) + '">' + esc(a.tri) + sc(a, aw) +
      (started ? "" : ' <span class="c">at</span> ') + '<img alt="" src="' + esc(h.logo) + '">' + esc(h.tri) + sc(h, !aw) +
      ' <span class="c' + (g.live ? " live" : "") + '">' + esc(status(g)) + "</span></button>";
  }
  function drawTicker() {
    var tr = $(".tick-track");
    if (!games.length) { tr.innerHTML = '<span class="tk"><span class="c">No games today</span></span>'; return; }
    var one = games.map(tickItem).join("");
    tr.innerHTML = one + one;                                     // (twice, so it loops without a gap)
    tr.style.setProperty("--tick-s", Math.max(25, games.length * 7) + "s");
  }
  $(".tick").addEventListener("click", function (e) {
    var b = e.target.closest(".tk[data-g]"); if (!b) return;
    if (current !== "home") go("home");
    var row = document.getElementById("g-" + b.getAttribute("data-g")); if (!row) return;
    setTimeout(function () {
      var m = $("main"); m.scrollTo({ top: row.offsetTop - $(".top").offsetHeight - 4, behavior: "smooth" });
      row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash");
    }, 30);
  });
  function head(g) {
    var a = g.away, h = g.home, started = g.live || g.final, aw = +a.score > +h.score;
    return '<div class="t"><img alt="" src="' + esc(a.logo) + '">' + esc(a.tri) + "</div>" + (started ? '<span class="sc' + (g.final && !aw ? " l" : "") + '">' + esc(a.score) + "</span>" : "") +
      '<span class="at">' + (started ? "–" : "at") + "</span>" + (started ? '<span class="sc' + (g.final && aw ? " l" : "") + '">' + esc(h.score) + "</span>" : "") +
      '<div class="t">' + esc(h.tri) + '<img alt="" src="' + esc(h.logo) + '"></div><span class="st' + (g.live ? " live" : "") + '">' + esc(status(g)) + "</span>";
  }
  // Each game's row is the website's own live windows for that game (app-game.html), scrolled sideways. A row is only
  // loaded when it's near the screen, and let go again when it's far away, so a busy night stays smooth.
  function drawRows() {
    var box = $("#games");
    if (!games.length) { box.innerHTML = '<p class="empty">No NBA games today.</p>'; return; }
    box.innerHTML = games.map(function (g) {
      return '<section class="game" id="g-' + g.id + '"><div class="gh">' + head(g) + '</div><div class="gw" data-id="' + g.id + '" data-day="' + esc(B.day()) + '"><div class="ph">Loading the game&hellip;</div></div></section>';
    }).join("");
    watchRows(); applyFeed();
  }
  function applyFeed() {
    var mine = feed === "mine";
    games.forEach(function (g) { var r = document.getElementById("g-" + g.id); if (r) r.hidden = mine && S.teams.indexOf(g.home.tri) < 0 && S.teams.indexOf(g.away.tri) < 0; });
    var none = mine && !games.some(function (g) { return S.teams.indexOf(g.home.tri) >= 0 || S.teams.indexOf(g.away.tri) >= 0; });
    var n = $("#feed-none"); if (none && !n) { n = document.createElement("p"); n.id = "feed-none"; n.className = "empty"; n.innerHTML = S.teams.length ? "None of your teams play today." : 'Pick your teams in <b>Your dashboard</b> first.'; $("#games").appendChild(n); }
    else if (!none && n) n.remove();
  }
  function updateRows() { games.forEach(function (g) { var r = document.getElementById("g-" + g.id); if (r) r.querySelector(".gh").innerHTML = head(g); }); }
  var rowIO = null, heights = {};
  function watchRows() {
    if (rowIO) rowIO.disconnect();
    var m = $("main");
    rowIO = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        var w = e.target, f = w.querySelector("iframe");
        if (e.isIntersecting && !f) {
          f = document.createElement("iframe");
          f.title = "Game windows"; f.loading = "eager"; f.setAttribute("allow", "autoplay; fullscreen; picture-in-picture; encrypted-media; web-share");
          f.src = "../app-game.html?id=" + encodeURIComponent(w.getAttribute("data-id")) + "&day=" + encodeURIComponent(w.getAttribute("data-day"));
          w.appendChild(f);
        }
      });
    }, { root: m, rootMargin: "120% 0px 120% 0px" });
    var far = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (e.isIntersecting) return;
        var f = e.target.querySelector("iframe");            // far off screen: let it go (it keeps its height)
        if (f) { e.target.style.minHeight = (heights[e.target.getAttribute("data-id")] || 420) + "px"; f.remove(); }
      });
    }, { root: m, rootMargin: "400% 0px 400% 0px" });
    $$(".gw").forEach(function (w) { rowIO.observe(w); far.observe(w); });
  }
  addEventListener("message", function (e) {
    var d = e.data || {}; if (!d.baGameHeight || !d.id) return;
    heights[d.id] = d.baGameHeight;
    var w = $('.gw[data-id="' + String(d.id).replace(/"/g, "") + '"]');
    if (w) { w.style.minHeight = d.baGameHeight + "px"; var f = w.querySelector("iframe"); if (f) f.style.height = d.baGameHeight + "px"; var ph = w.querySelector(".ph"); if (ph) ph.remove(); }
  });

  // ------------------------------------------------------------ your dashboard
  var WIDGETS = { today: "Your teams today", hubs: "Team hubs", news: "Your teams' news", leaders: "League leaders & awards race", standings: "Standings" };
  var editing = false, hubCache = {};
  $("#edit-mine").addEventListener("click", function () { editing = !editing; this.textContent = editing ? "Done" : "Edit"; this.classList.toggle("on", editing); drawMine(); });
  function teamPicker() {
    return '<div class="w"><h3>Favourite teams <small>tap to add or remove</small></h3><div class="teams-pick">' + ALL.map(function (t) {
      return '<button type="button" data-team="' + t + '" class="' + (S.teams.indexOf(t) >= 0 ? "on" : "") + '" aria-label="' + esc(B.names[t]) + '"><img alt="" src="' + esc(B.logo(t)) + '"></button>';
    }).join("") + "</div></div>";
  }
  function drawMine() {
    var box = $("#mine");
    if (editing || !S.teams.length) {
      box.innerHTML = teamPicker() + '<div class="w"><h3>On your dashboard</h3>' + Object.keys(WIDGETS).map(function (k) {
        return '<div class="wedit"><span>' + esc(WIDGETS[k]) + '</span><button class="toggle" type="button" data-w="' + k + '" aria-pressed="' + (S.widgets.indexOf(k) >= 0) + '"><i></i></button></div>';
      }).join("") + "</div>" + (S.teams.length ? "" : '<p class="note center">Pick your teams to build your dashboard.</p>');
      return;
    }
    box.innerHTML = S.widgets.map(function (k) { return '<div class="w" data-wid="' + k + '"><h3>' + esc(WIDGETS[k]) + "</h3><div class='wb'><p class='note'>Loading&hellip;</p></div></div>"; }).join("");
    S.widgets.forEach(function (k) { var b = $('[data-wid="' + k + '"] .wb'); if (b) fill(k, b); });
  }
  $("#mine").addEventListener("click", function (e) {
    var t = e.target.closest("[data-team]");
    if (t) { var k = t.getAttribute("data-team"), i = S.teams.indexOf(k); if (i >= 0) S.teams.splice(i, 1); else S.teams.push(k); put("teams", S.teams); t.classList.toggle("on", i < 0); return; }
    var w = e.target.closest("[data-w]");
    if (w) { var id = w.getAttribute("data-w"), j = S.widgets.indexOf(id); if (j >= 0) S.widgets.splice(j, 1); else S.widgets.push(id); put("widgets", S.widgets); w.setAttribute("aria-pressed", j < 0); return; }
    var g = e.target.closest("[data-jump]");
    if (g) { go("home"); var row = document.getElementById("g-" + g.getAttribute("data-jump")); if (row) setTimeout(function () { $("main").scrollTo({ top: row.offsetTop - $(".top").offsetHeight - 4, behavior: "smooth" }); }, 50); }
  });
  function hub(t) {
    if (!hubCache[t]) hubCache[t] = B.getJSON(TEAM + t.toLowerCase()).then(function (d) {
      var tm = d.team || {}, rec = ((tm.record || {}).items || [])[0] || {}, nx = (tm.nextEvent || [])[0] || {};
      return { rec: rec.summary || "", standing: tm.standingSummary || "", next: nx.shortName || "", when: nx.date || "" };
    }).catch(function () { return {}; });
    return hubCache[t];
  }
  function fill(k, b) {
    var mine = S.teams;
    if (k === "today") {
      var g = games.filter(function (x) { return mine.indexOf(x.home.tri) >= 0 || mine.indexOf(x.away.tri) >= 0; });
      b.innerHTML = g.length ? g.map(function (x) { return '<div class="row" data-jump="' + x.id + '"><img alt="" src="' + esc(x.away.logo) + '"><div class="grow"><b>' + esc(x.away.tri + " at " + x.home.tri) + "</b><span>" + esc(status(x)) + (x.live || x.final ? " · " + esc(x.away.score + "-" + x.home.score) : "") + '</span></div><img alt="" src="' + esc(x.home.logo) + '"></div>'; }).join("")
        : '<p class="note">None of your teams play today.</p>';
    } else if (k === "hubs") {
      b.innerHTML = '<div class="hubs">' + mine.map(function (t) { return '<button class="hub" type="button" data-ext="https://bradleyanalytics.streamlit.app/" style="--tc:' + (B.colors[t] || "#D4AF37") + '"><img alt="" src="' + esc(B.logo(t)) + '"><b>' + esc(B.names[t]) + '</b><span data-hub="' + t + '">&hellip;</span></button>'; }).join("") + "</div>";
      mine.forEach(function (t) { hub(t).then(function (h) { var s = b.querySelector('[data-hub="' + t + '"]'); if (s) s.textContent = [h.rec, h.standing, h.next && "Next: " + h.next].filter(Boolean).join(" · ") || "Team page"; }); });
    } else if (k === "news") {
      B.getJSON("../data/news.json").then(function (d) {
        var tx = (d.transactions || []).filter(function (x) { return mine.indexOf(x.team) >= 0; }).map(function (x) { return { t: x.team, h: x.name, p: x.desc, s: (x.date || "").slice(0, 10) }; });
        var inj = (d.injuries || []).filter(function (x) { return mine.indexOf(x.team) >= 0; }).map(function (x) { return { t: x.team, h: x.name + " · " + x.status, p: x.note }; });
        var all = tx.concat(inj).slice(0, 12);
        b.innerHTML = all.length ? all.map(function (x) { return '<div class="row"><img alt="" src="' + esc(B.logo(x.t)) + '"><div class="grow"><b>' + esc(x.h) + "</b><span>" + esc(x.p || "") + "</span></div></div>"; }).join("") : '<p class="note">No news for your teams right now.</p>';
      }).catch(function () { b.innerHTML = '<p class="note">Couldn&rsquo;t load the news.</p>'; });
    } else if (k === "leaders" || k === "standings") {
      b.innerHTML = '<p class="note">' + (k === "leaders" ? "Points, rebounds, assists and the MVP, Rookie and Defensive Player races" : "Both conferences, with your teams highlighted") + ' &mdash; coming in the next draft.</p><button class="chip" type="button" data-ext="https://bradleyanalytics.streamlit.app/">Open the dashboard</button>';
    }
  }

  // ------------------------------------------------------------ community (a draft: posts stay on this phone)
  function drawPosts() {
    var posts = get("posts", []);
    $("#posts").innerHTML = posts.length ? posts.map(function (p, i) {
      return '<div class="post"><div class="who"><i>' + esc(initials(p.by)) + "</i>" + esc(p.by) + " <small>" + esc(ago(p.t)) + "</small></div><p>" + esc(p.text) + '</p><div class="act"><button type="button" data-like="' + i + '" class="' + (p.liked ? "on" : "") + '">&#9829; ' + (p.likes || 0) + "</button></div></div>";
    }).join("") : '<p class="empty">No posts yet. Be the first.</p>';
  }
  $("#post-go").addEventListener("click", function () {
    var t = $("#post-text").value.trim(); if (!t) return;
    var posts = get("posts", []); posts.unshift({ by: S.name || "You", text: t, t: Date.now(), likes: 0 }); put("posts", posts);
    $("#post-text").value = ""; drawPosts(); toast("Posted");
  });
  $("#posts").addEventListener("click", function (e) {
    var b = e.target.closest("[data-like]"); if (!b) return;
    var posts = get("posts", []), p = posts[+b.getAttribute("data-like")]; if (!p) return;
    p.liked = !p.liked; p.likes = Math.max(0, (p.likes || 0) + (p.liked ? 1 : -1)); put("posts", posts); drawPosts();
  });
  function initials(n) { return String(n || "BA").split(/\s+/).map(function (x) { return x.charAt(0); }).join("").slice(0, 2).toUpperCase(); }
  function ago(t) { var m = Math.round((Date.now() - t) / 60000); return m < 1 ? "now" : m < 60 ? m + "m" : m < 1440 ? Math.round(m / 60) + "h" : Math.round(m / 1440) + "d"; }

  // ------------------------------------------------------------ profile + settings
  function drawProfile() {
    $("#me-name").value = S.name; $("#me-av").textContent = initials(S.name || "BA");
    $("#me-teams").textContent = S.teams.length ? S.teams.map(function (t) { return B.names[t]; }).join(", ") : "No favourite teams yet";
    $("#set-bg").innerHTML = FLOORS.map(function (f) { return '<button class="chip' + (S.floor === f[0] ? " on" : "") + '" type="button" data-floor="' + f[0] + '">' + f[1] + "</button>"; }).join("");
    $("#set-acc").innerHTML = ACCENTS.map(function (a, i) { return '<button type="button" data-acc="' + i + '" title="' + a[0] + '" class="' + (S.accent === i ? "on" : "") + '" style="background:linear-gradient(135deg,' + a[1] + "," + a[2] + ')"></button>'; }).join("");
    $("#set-tilt").setAttribute("aria-pressed", S.tilt);
  }
  $("#me-name").addEventListener("input", function () { S.name = this.value.trim(); put("name", S.name); $("#me-av").textContent = initials(S.name || "BA"); });
  $("#set-bg").addEventListener("click", function (e) { var b = e.target.closest("[data-floor]"); if (!b) return; S.floor = b.getAttribute("data-floor"); put("floor", S.floor); Floor.rebuild(); drawProfile(); });
  $("#set-acc").addEventListener("click", function (e) { var b = e.target.closest("[data-acc]"); if (!b) return; S.accent = +b.getAttribute("data-acc"); put("accent", S.accent); applyAccent(); drawProfile(); });
  $("#set-tilt").addEventListener("click", function () {
    S.tilt = !S.tilt; put("tilt", S.tilt); this.setAttribute("aria-pressed", S.tilt);
    if (S.tilt && Floor.needsAsk()) Floor.ask(); if (!S.tilt) Floor.still();
  });

  // ------------------------------------------------------------ the bell: notifications and articles
  $("#bell").addEventListener("click", function () {
    var sh = $("#news"), body = sh.querySelector(".sheet-body"); sh.hidden = false;
    body.innerHTML = '<p class="note center">Loading&hellip;</p>';
    B.getJSON("../data/news.json").then(function (d) {
      var items = (d.transactions || []).map(function (x) { return '<div class="news"><img alt="" src="' + esc(B.logo(x.team)) + '"><div><b>' + esc(x.name) + "</b> <small>" + esc((x.date || "").slice(0, 10)) + "</small><p>" + esc(x.desc) + "</p></div></div>"; });
      body.innerHTML = '<div class="card"><b>Post-game newsletters</b><p class="note" style="margin:6px 0 0">A short write-up after every game, and the week&rsquo;s best charts. Coming soon: you&rsquo;ll get them here and as notifications.</p></div>' +
        '<h2 class="h">Latest NBA moves</h2>' + (items.join("") || '<p class="note center">Nothing new.</p>');
    }).catch(function () { body.innerHTML = '<p class="note center">Couldn&rsquo;t load the news.</p>'; });
  });

  // ------------------------------------------------------------ the top: the name's menu, the + button
  var feed = "all";
  $("#brand").addEventListener("click", function (e) {
    e.stopPropagation(); var m = $("#brand-menu"), open = m.hidden; m.hidden = !open; this.setAttribute("aria-expanded", open);
  });
  document.addEventListener("click", function () { $("#brand-menu").hidden = true; $("#brand").setAttribute("aria-expanded", "false"); });
  $("#brand-menu").addEventListener("click", function (e) {
    var b = e.target.closest("[data-feed]"); if (!b) return;
    feed = b.getAttribute("data-feed");
    $$("#brand-menu [data-feed]").forEach(function (x) { x.setAttribute("aria-checked", x === b); });
    if (current !== "home") go("home"); applyFeed(); drawStories();
  });
  $("#new-post").addEventListener("click", function () { go("community"); setTimeout(function () { $("#post-text").focus(); }, 80); });
  function tabAvatar() { $("#tab-av").textContent = initials(S.name || "BA"); }
  tabAvatar(); $("#me-name").addEventListener("input", tabAvatar);

  // ------------------------------------------------------------ stories: each game's YouTube highlights
  // Today's finished games with highlights come first, then the latest earlier ones; today's games still to finish sit at
  // the end, dimmed, with their tip-off time (a tap goes to the game). Watched ones lose their gold ring.
  var HL = {}, stories = [];
  function loadHL() {
    return fetch("../data/highlights.json?t=" + Math.floor(Date.now() / 300000), { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (d) { HL = (d && d.games) || {}; drawStories(); }).catch(function () {});
  }
  function drawStories() {
    var seen = get("seen", {}), today = {}, list = [];
    games.forEach(function (g) { today[g.id] = g; });
    Object.keys(HL).forEach(function (id) {
      var v = HL[id]; if (!v || !v.id) return;
      var g = today[id], t = (v.teams || []), a = g ? g.away.tri : t[0], h = g ? g.home.tri : t[1];
      if (feed === "mine" && S.teams.indexOf(a) < 0 && S.teams.indexOf(h) < 0) return;
      list.push({ id: id, v: v, g: g, a: a, h: h, when: v.published || "", today: !!g });
    });
    list.sort(function (x, y) { return (y.today - x.today) || (y.when > x.when ? 1 : y.when < x.when ? -1 : 0); });
    stories = list.slice(0, 24);
    var later = games.filter(function (g) { return !HL[g.id] && !g.final && (feed !== "mine" || S.teams.indexOf(g.home.tri) >= 0 || S.teams.indexOf(g.away.tri) >= 0); });
    var html = stories.map(function (s, i) {
      return '<button class="sty' + (seen[s.v.id] ? " seen" : "") + '" type="button" data-story="' + i + '"><span class="ring"><span class="in"><img class="a" alt="" src="' + esc(B.logo(s.a)) + '"><img class="h" alt="" src="' + esc(B.logo(s.h)) + '"><i class="yt"></i></span></span><b>' + esc(s.a + " @ " + s.h) + "</b></button>";
    }).concat(later.map(function (g) {
      return '<button class="sty later" type="button" data-jump-g="' + g.id + '"><span class="ring"><span class="in"><img class="a" alt="" src="' + esc(g.away.logo) + '"><img class="h" alt="" src="' + esc(g.home.logo) + '"></span></span><b>' + esc(g.live ? "Live" : timeOf(g)) + "</b></button>";
    })).join("");
    $("#stories").innerHTML = html || "";
    $("#stories").hidden = !html;
  }
  $("#stories").addEventListener("click", function (e) {
    var s = e.target.closest("[data-story]"); if (s) { openStory(+s.getAttribute("data-story")); return; }
    var j = e.target.closest("[data-jump-g]"); if (!j) return;
    var row = document.getElementById("g-" + j.getAttribute("data-jump-g")); if (row) $("main").scrollTo({ top: row.offsetTop - $(".top").offsetHeight - 4, behavior: "smooth" });
  });
  var storyAt = -1;
  function openStory(i) {
    if (i < 0 || i >= stories.length) { closeStory(); return; }
    storyAt = i;
    var s = stories[i], v = s.v, g = s.g, box = $("#story");
    box.hidden = false; document.body.classList.add("story-on");
    box.querySelector(".story-bars").innerHTML = stories.map(function (x, k) { return "<i class='" + (k < i ? "done" : k === i ? "now" : "") + "'></i>"; }).join("");
    var score = g && (g.final || g.live) ? " " + g.away.score + "-" + g.home.score : "";
    var d = String(v.day || "").replace(/^(\d{4})(\d{2})(\d{2})$/, "$2/$3").replace(/^0/, "");
    box.querySelector(".story-who").innerHTML = '<img alt="" src="' + esc(B.logo(s.a)) + '"><span>' + esc(s.a + " @ " + s.h + score) + " <small>" + esc(d) + '</small></span><img alt="" src="' + esc(B.logo(s.h)) + '">';
    box.querySelector(".story-foot").innerHTML = g ? '<button class="chip" type="button" data-to-game="' + g.id + '">See the game windows</button>' : "";
    var seen = get("seen", {}); seen[v.id] = 1; put("seen", seen);
    if (window.BAMini) window.BAMini.open({ vid: v.id, blocked: v.blocked, allowed: v.allowed, alts: v.alts || [], title: s.a + " @ " + s.h + " Highlights",
      anchor: box.querySelector(".story-v"), autoplay: true, onClose: function () {} });
  }
  function closeStory() { $("#story").hidden = true; document.body.classList.remove("story-on"); storyAt = -1; if (window.BAMini) window.BAMini.close(); drawStories(); }
  $("#story .story-x").addEventListener("click", closeStory);
  $("#story .story-prev").addEventListener("click", function () { openStory(Math.max(0, storyAt - 1)); });
  $("#story .story-next").addEventListener("click", function () { openStory(storyAt + 1); });
  $("#story").addEventListener("click", function (e) {
    var b = e.target.closest("[data-to-game]"); if (!b) return;
    closeStory(); var row = document.getElementById("g-" + b.getAttribute("data-to-game"));
    if (row) setTimeout(function () { $("main").scrollTo({ top: row.offsetTop - $(".top").offsetHeight - 4, behavior: "smooth" }); }, 60);
  });
  (function swipeDown() {                                         // a swipe down closes it, as on Instagram
    var y0 = null, el = $("#story");
    el.addEventListener("touchstart", function (e) { y0 = e.touches[0].clientY; }, { passive: true });
    el.addEventListener("touchend", function (e) { if (y0 != null && e.changedTouches[0].clientY - y0 > 110) closeStory(); y0 = null; }, { passive: true });
  })();

  // ------------------------------------------------------------ the dashboard, under the games (opened when reached)
  new IntersectionObserver(function (es, o) {
    if (!es[0].isIntersecting) return; o.disconnect();
    var f = document.createElement("iframe"); f.title = "Bradley Analytics dashboard"; f.src = "https://bradleyanalytics.streamlit.app/?embed=true";
    f.setAttribute("allow", "clipboard-write; fullscreen"); $("#dash").appendChild(f);
    f.addEventListener("load", function () { var ph = $("#dash .ph"); if (ph) ph.remove(); });
  }, { root: $("main"), rootMargin: "50% 0px" }).observe($("#dash"));

  // ------------------------------------------------------------ start
  loadGames(); loadHL();
  setInterval(function () { if (!document.hidden) loadHL(); }, 5 * 60e3);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) loadGames(); });
  motionPrompt();
  if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("sw.js").catch(function () {});
})();
