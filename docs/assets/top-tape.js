/* The skinny live tape at the top of every page (_includes/nav.html).

   It always shows the games that matter right now, whatever day the home page's ALL GAMES window is set to:
   - today's games (live, upcoming, and those already over today), Eastern time, the day rolling over at 6 a.m.;
   - with none today, the next day with games (up to two weeks ahead);
   - with none ahead either (after the Finals, before the schedule is out), the most recent games: the last series
     played if it was the playoffs (the Finals), otherwise the last game day.
   Clicking a game goes to the home page's live game windows showing that game (on the home page itself it just scrolls
   down to them). Read straight from ESPN's public scoreboard; every 15 seconds while a game is live, every minute
   otherwise, only while the tab is open. */
(function () {
  "use strict";
  var box = document.getElementById("ba-top-tape");
  if (!box || !window.fetch || !window.requestAnimationFrame) return;
  var tk = box.querySelector(".ls-ticker"), track = box.querySelector(".ls-ticker-track");
  var SB = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?limit=200&dates=";
  var REDUCE = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  var CELTICS = "https://www.2kratings.com/wp-content/uploads/Boston-Celtics-Current-Logo.svg";
  var TRI = { GS: "GSW", NY: "NYK", SA: "SAS", NO: "NOP", UTAH: "UTA", WSH: "WAS", PHO: "PHX", BRK: "BKN", CHO: "CHA" };
  var COLORS = { ATL: "#E03A3E", BOS: "#18A659", BKN: "#C9C9C9", CHA: "#00778B", CHI: "#E0314B", CLE: "#FDBB30", DAL: "#1E7FD6", DEN: "#FEC524",
    DET: "#E0314B", GSW: "#FFC72C", HOU: "#E0314B", IND: "#FDBB30", LAC: "#3B82F6", LAL: "#FDB927", MEM: "#7D95C9", MIA: "#F25C54", MIL: "#EEE1C6",
    MIN: "#1F4399", NOP: "#B6995A", NYK: "#F58426", OKC: "#2E9BE6", ORL: "#2F8FE0", PHI: "#3B82F6", PHX: "#E56020", POR: "#E03A3E", SAC: "#A57FDB",
    SAS: "#C4CED4", TOR: "#E0314B", UTA: "#4F008F", WAS: "#E31837" };
  var ALT = { ATL: "#C1D32F", BOS: "#BA9653", BKN: "#FFFFFF", CHA: "#8C7FD6", CHI: "#FFFFFF", CLE: "#E07C95", DAL: "#B8C4CA", DEN: "#6F93D6",
    DET: "#3E8EDE", GSW: "#6F9BE8", HOU: "#C4CED4", IND: "#6F93D6", LAC: "#E0314B", LAL: "#9B6FD6", MEM: "#F5B112", MIA: "#F9A01B", MIL: "#2FA36B",
    MIN: "#78BE20", NOP: "#6F93D6", NYK: "#3E8EDE", OKC: "#F05133", ORL: "#C4CED4", PHI: "#ED174C", PHX: "#9B7FD6", POR: "#FFFFFF", SAC: "#C4CED4",
    SAS: "#FFFFFF", TOR: "#C4CED4", UTA: "#FFFFFF", WAS: "#6F93D6" };

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function getJSON(u) { return fetch(u, { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }); }
  function etDay(d) { try { return new Date(d).toLocaleDateString("en-CA", { timeZone: "America/New_York" }); } catch (e) { return new Date(d).toISOString().slice(0, 10); } }
  function ymd(day) { return day.replace(/-/g, ""); }
  function addDays(day, n) { var d = new Date(day + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
  function hexRgb(h) { h = String(h).replace("#", ""); if (h.length === 3) h = h.replace(/./g, "$&$&"); return [0, 2, 4].map(function (i) { return parseInt(h.substr(i, 2), 16) || 0; }); }
  function gap(a, b) { var x = hexRgb(a), y = hexRgb(b); return Math.sqrt(Math.pow(x[0] - y[0], 2) + Math.pow(x[1] - y[1], 2) + Math.pow(x[2] - y[2], 2)); }
  function ordinal(p) { p = parseInt(p, 10) || 0; return p > 4 ? (p > 5 ? p - 4 : "") + "OT" : "Q" + p; }

  // ------------------------------------------------------------ ESPN's scoreboard -> the tape's games
  function shape(ev) {
    var comp = (ev.competitions || [])[0] || {}, st = comp.status || ev.status || {}, ty = st.type || {};
    var cs = comp.competitors || [];
    function side(which) {
      var c = cs.filter(function (x) { return x.homeAway === which; })[0] || {}, t = c.team || {}, tri = TRI[t.abbreviation] || t.abbreviation || "";
      return { tri: tri, score: c.score || "0", logo: tri === "BOS" ? CELTICS : (t.logo || (t.abbreviation ? "https://a.espncdn.com/i/teamlogos/nba/500/" + String(t.abbreviation).toLowerCase() + ".png" : "")), color: "", alt: "" };     // (the same team colours as the windows' tape)
    }
    var g = { id: String(ev.id), when: comp.date || ev.date, state: ty.state || "pre", name: String(ty.name || ""), period: st.period, clock: st.displayClock || "",
      home: side("home"), away: side("away"), playoff: (ev.season || {}).type === 3 || /playoff|final/i.test(JSON.stringify(comp.notes || "")) };
    g.day = etDay(new Date(new Date(g.when).getTime() - 6 * 3600e3));
    return g;
  }
  function games(sb) { return (sb.events || []).map(shape).sort(function (a, b) { return new Date(a.when) - new Date(b.when); }); }
  function pickGames() {
    var today = etDay(Date.now() - 6 * 3600e3);
    return getJSON(SB + ymd(today)).then(function (sb) {
      var g = games(sb);
      if (g.length) return g;
      return getJSON(SB + ymd(addDays(today, 1)) + "-" + ymd(addDays(today, 14))).then(function (sb2) {
        var ahead = games(sb2);
        if (ahead.length) { var d = ahead[0].day; return ahead.filter(function (x) { return x.day === d; }); }
        // nothing ahead: the most recent games -- the last series if it was the playoffs (the Finals)
        return getJSON(SB + ymd(addDays(today, -150)) + "-" + ymd(addDays(today, -1))).then(function (sb3) {
          var past = games(sb3).filter(function (x) { return x.state === "post"; });
          if (!past.length) return [];
          var last = past[past.length - 1];
          if (last.playoff) {
            var pair = [last.home.tri, last.away.tri].sort().join("-");
            return past.filter(function (x) { return [x.home.tri, x.away.tri].sort().join("-") === pair; });
          }
          return past.filter(function (x) { return x.day === last.day; });
        });
      });
    });
  }

  // ------------------------------------------------------------ the tape
  function colors(g) {
    var a = g.home.color || COLORS[g.home.tri] || "#D4AF37", b = g.away.color || COLORS[g.away.tri] || "#e8e8e8";
    if (gap(a, b) < 110) { var alt = g.away.alt || ALT[g.away.tri] || "#e8e8e8"; b = gap(a, alt) >= 110 ? alt : "#e8e8e8"; }
    return { home: a, away: b };
  }
  function status(g) {
    if (g.state === "in") {
      if (/HALFTIME/i.test(g.name)) return "Half";
      if (/END_PERIOD/i.test(g.name)) return "End " + ordinal(g.period);
      return ordinal(g.period) + " " + g.clock;
    }
    if (g.state === "post") return (parseInt(g.period, 10) || 0) > 4 ? "Final/" + ordinal(g.period) : "Final";
    var d = new Date(g.when), today = etDay(Date.now() - 6 * 3600e3);
    var t = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    return g.day === today ? t : d.toLocaleDateString("en-US", { weekday: "short" }) + " " + t;
  }
  function logo(t) { return t.logo ? '<img class="ls-logo" alt="" width="18" height="18" style="width:18px;height:18px" src="' + esc(t.logo) + '" onerror="this.style.visibility=\'hidden\'">' : ""; }
  function item(g, copy) {
    var c = colors(g), live = g.state === "in", pre = g.state === "pre";
    return '<a class="ls-tk' + (live ? " live" : "") + '" href="index.html?game=' + esc(g.id) + "&day=" + esc(g.day) + '#live-strip" data-id="' + esc(g.id) +
      '" data-day="' + esc(g.day) + '"' + (copy ? ' tabindex="-1" aria-hidden="true"' : ' aria-label="' + esc(g.away.tri + " at " + g.home.tri + ", " + status(g)) + ': open in the live game windows"') + ">" +
      logo(g.away) + '<span class="t" style="color:' + c.away + '">' + esc(g.away.tri) + "</span>" +
      (pre ? '<span class="d">at</span>' : '<span class="s" style="color:' + c.away + '">' + esc(g.away.score) + '</span><span class="d">–</span><span class="s" style="color:' + c.home + '">' + esc(g.home.score) + "</span>") +
      '<span class="t" style="color:' + c.home + '">' + esc(g.home.tri) + "</span>" + logo(g.home) +
      (live ? '<i class="ls-dot" aria-hidden="true"></i>' : "") + '<span class="st">' + esc(status(g)) + "</span></a>";
  }
  var list = [], sig = "";
  function render() {
    if (!list.length) { box.hidden = true; return; }
    box.hidden = false;
    var s = list.map(function (g) { return g.id + g.state + g.away.score + g.home.score + status(g); }).join("|");
    if (s === sig) return;
    sig = s;
    var reps = Math.max(1, Math.ceil(8 / list.length)), one = "";
    for (var r = 0; r < reps; r++) list.forEach(function (g) { one += item(g, r > 0) + '<span class="sep" aria-hidden="true">|</span>'; });
    track.innerHTML = one + one.replace(/<a class="ls-tk/g, '<a tabindex="-1" aria-hidden="true" class="ls-tk').replace(/ aria-label="[^"]*"/g, "");
  }
  track.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest(".ls-tk");
    if (!a) return;
    // on the home page: straight down to the windows, now showing that game
    if (window.BALive && document.getElementById("live-strip")) { e.preventDefault(); window.BALive.show(a.getAttribute("data-id"), a.getAttribute("data-day")); }
  });

  // ------------------------------------------------------------ its motion: slides by itself, drag / swipe / trackpad
  (function motion() {
    if (REDUCE) return;
    tk.classList.add("js-drive");
    var x = 0, v = 0, last = null, hover = false, holdUntil = 0, drag = null, movedAt = -1e9, SPEED = 42;
    function wrap() { var h = track.scrollWidth / 2; if (h > 1) x = ((x % h) - h) % h; }
    (function frame(now) {
      requestAnimationFrame(frame);
      if (last === null) last = now;
      var dt = Math.min(0.1, (now - last) / 1000); last = now;
      if (!drag) {
        if (Math.abs(v) > 8) { x += v * dt; v *= Math.pow(0.03, dt); }
        else { v = 0; if (!hover && now >= holdUntil) x -= SPEED * dt; }
      }
      wrap();
      track.style.transform = "translate3d(" + x.toFixed(2) + "px,0,0)";
    })(performance.now());
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
        if (drag.type !== "mouse" && Math.abs(e.clientY - drag.y0) > Math.abs(dx)) { drag = null; return; }
        drag.moved = true; drag.start = x - dx; tk.classList.add("dragging");
        try { tk.setPointerCapture(e.pointerId); } catch (er) {}
      }
      var now = performance.now();
      v = Math.max(-2500, Math.min(2500, 0.75 * v + 0.25 * ((e.clientX - drag.lx) / Math.max(8, now - drag.lt) * 1000)));
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
    tk.addEventListener("click", function (e) { if (performance.now() - movedAt < 300) { e.stopPropagation(); e.preventDefault(); } }, true);
    tk.addEventListener("dragstart", function (e) { e.preventDefault(); });
    tk.addEventListener("wheel", function (e) {
      if (Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
      e.preventDefault(); x -= e.deltaX; v = 0; holdUntil = performance.now() + 2500;
    }, { passive: false });
  })();

  // ------------------------------------------------------------ keeping it current
  var timer = null;
  function refresh() {
    clearTimeout(timer);
    if (document.hidden) { timer = setTimeout(refresh, 60e3); return; }
    pickGames().then(function (g) { list = g; render(); }).catch(function () {}).then(function () {
      var live = list.some(function (g) { return g.state === "in"; });
      var soon = list.some(function (g) { return g.state === "pre" && new Date(g.when) - Date.now() < 15 * 60e3; });
      timer = setTimeout(refresh, live ? 15e3 : soon ? 30e3 : 60e3);
    });
  }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) refresh(); });
  refresh();
})();
