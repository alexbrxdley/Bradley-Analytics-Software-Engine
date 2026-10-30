/* Live game notifications, on phones and computers: the bell in the menu bar.

   Alerts: the types in assets/alert-rules.js (tip-offs, finals, close games, clutch finishes and overtime, upsets and
   comebacks, big nights, triple-doubles, highlights, injuries, trades, a morning recap and a game reminder), for every
   game or only the teams and players picked.

   How they're sent:
   - While the site is open in a tab (any page), this script itself follows the night's games from ESPN's public
     scoreboard once a minute and shows the alerts. Nothing to set up.
   - When the notification server is set up (worker/, see worker/README.md, then push_worker_url and push_public_key
     in _config.yml), turning alerts on also subscribes this browser to it, and the alerts arrive even when the site is
     closed. The server runs the same checks (worker/src/alerts.js mirrors detect() below).

   On a phone or tablet the bell first puts the site on the home screen: with the browser's own "add to home screen"
   pop-up where the browser has one (Chrome, Edge, Samsung Internet on Android), otherwise with three short steps
   (Share, Add to Home Screen, then open it from the home screen and turn alerts on). iPhones and iPads can only send a
   website's notifications from its home screen app (iOS 16.4 and later). Opening the app goes to the home page. */
(function () {
  "use strict";
  var CFG = window.BA_PUSH || {};
  var WORKER = (CFG.worker || "").replace(/\/+$/, ""), KEY = CFG.key || "";
  var STORE = "ba-notify", SEEN = "ba-notify-state", LOCK = "ba-notify-lock", NUDGED = "ba-notify-nudged";
  var SB = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=";
  var CELTICS = "https://www.2kratings.com/wp-content/uploads/Boston-Celtics-Current-Logo.svg";
  // the rules (what's worth an alert, and who wants it) live in assets/alert-rules.js, shared with the alert server
  var R = window.BAAlerts;
  if (!R) return;
  var CELTICS_LOGO = R.CELTICS_LOGO, TEAMS = R.TEAMS, TYPES = R.KINDS;
  var detect = R.detect, allowed = R.allowed, pictureFor = R.pictureFor, gameDay = R.gameDay;
  var ua = navigator.userAgent || "";
  var IOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  var MOBILE = IOS || /Android|Mobi|Silk|Kindle|BlackBerry|Opera Mini|IEMobile/i.test(ua) ||
    (window.matchMedia && matchMedia("(pointer: coarse)").matches && Math.min(screen.width, screen.height) < 820);
  var STANDALONE = (window.matchMedia && matchMedia("(display-mode: standalone)").matches) || navigator.standalone === true;
  var CAN_NOTIFY = "Notification" in window && "serviceWorker" in navigator;
  var CAN_PUSH = CAN_NOTIFY && "PushManager" in window && !!WORKER && !!KEY;
  var installEvt = null;

  // ------------------------------------------------------------ storage (a private window can refuse it: then nothing is kept)
  function load(k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } }
  function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function prefs() {
    var p = load(STORE, null) || {}, types = {};
    TYPES.forEach(function (t) { types[t[0]] = !p.types || p.types[t[0]] === undefined ? true : !!p.types[t[0]]; });   // (a new type starts on)
    return { on: !!p.on, mode: p.mode || "", types: types, teams: p.teams || [], players: p.players || [] };
  }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function logo(t) { return t === "BOS" ? CELTICS : "https://a.espncdn.com/i/teamlogos/nba/500/" + t.toLowerCase() + ".png"; }
  function fold(s) { return String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z ]/g, "").trim(); }
  window.BANotifyDetect = detect;                      // (used by the tests)

  // ------------------------------------------------------------ showing an alert
  function swReg() {
    if (!("serviceWorker" in navigator)) return Promise.reject(new Error("no service worker"));
    return navigator.serviceWorker.register("sw.js").then(function () { return navigator.serviceWorker.ready; });
  }
  // the picture in an alert: a game's two team logos side by side, just as they are (no circle, no border, see-through
  // background), or a player's face cut into a see-through circle with a ring in his team's colour
  function loadImg(src) {
    return new Promise(function (resolve, reject) {
      var im = new Image(); im.crossOrigin = "anonymous";
      im.onload = function () { resolve(im); }; im.onerror = reject; im.src = src;
      setTimeout(reject, 4000);
    });
  }
  function iconFor(m) {
    var srcs = (m.imgs && m.imgs.filter(Boolean).length ? m.imgs : [m.img]).filter(Boolean);
    if (!srcs.length) return Promise.resolve("assets/icon-192.png");
    return Promise.all(srcs.map(function (u) { return loadImg(u).catch(function () { return u === CELTICS_LOGO ? loadImg(CELTICS).catch(function () { return null; }) : null; }); })).then(function (ims) {
      var N = 192, c = document.createElement("canvas"); c.width = c.height = N;
      var x = c.getContext("2d"), got = ims.filter(Boolean);
      if (!got.length) return srcs[0];
      if (m.round && got.length === 1) {
        var im = got[0], w = im.naturalWidth || 200, h = im.naturalHeight || 200;
        x.save(); x.beginPath(); x.arc(N / 2, N / 2, N / 2 - 8, 0, Math.PI * 2); x.clip();
        var k = (N - 16) * 1.25 / h; x.drawImage(im, N / 2 - w * k / 2, 8 - h * k * 0.04, w * k, h * k);
        x.restore();
        x.beginPath(); x.arc(N / 2, N / 2, N / 2 - 4.5, 0, Math.PI * 2); x.lineWidth = 7; x.strokeStyle = m.ring || "#D4AF37"; x.stroke();
      } else {
        var n = ims.length, cell = N / n;
        ims.forEach(function (im, i) {
          if (!im) return;
          var w2 = im.naturalWidth || 200, h2 = im.naturalHeight || 200, k2 = (cell * (n > 1 ? 0.96 : 0.92)) / Math.max(w2, h2);
          x.drawImage(im, cell * i + cell / 2 - w2 * k2 / 2, N / 2 - h2 * k2 / 2, w2 * k2, h2 * k2);
        });
      }
      try { return c.toDataURL("image/png"); } catch (e) { return srcs[0]; }
    });
  }
  function show(m) {
    if (!CAN_NOTIFY || Notification.permission !== "granted") return;
    iconFor(m).then(function (icon) {
      var opts = { body: m.body, tag: m.tag, icon: icon, badge: "favicon-32x32.png", data: { url: m.url || "index.html#live-strip" } };
      swReg().then(function (r) { return r.showNotification(m.title, opts); }).catch(function () { try { new Notification(m.title, opts); } catch (e) {} });
    });
  }

  // ------------------------------------------------------------ following tonight's games while the site is open
  var watching = 0;
  function tick() {
    var p = prefs();
    if (!p.on || p.mode === "push" || Notification.permission !== "granted") return;
    var now = Date.now(), lock = load(LOCK, null), me = window.__baNotifyId || (window.__baNotifyId = Math.random().toString(36).slice(2));
    if (lock && lock.id !== me && now - lock.t < 90e3) return;        // another open tab is already following the games
    save(LOCK, { id: me, t: now });
    var seen = load(SEEN, {}), day = gameDay();
    if (seen._day !== day) seen = { _day: day, inj: seen.inj, injx: seen.injx, tx: seen.tx, hl: seen.hl, recap: seen.recap, remind: seen.remind, nt: seen.nt };
    var jobs2 = [];
    var jobs = [fetch(SB + day, { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (sb) {
      var out = detect(sb, seen);
      R.due(seen, now).forEach(function (k) {
        if (k === "games") { var m = R.reminder(sb); if (m) out.push(m); }
        if (k === "recap") jobs2.push(fetch(SB + gameDay(now - 864e5)).then(function (r) { return r.json(); }).then(function (y) { var m = R.recapFor(y, p); return m ? [m] : []; }).catch(function () { return []; }));
      });
      return out;
    }).catch(function () { return []; })];
    if (now - (seen.nt || 0) > 10 * 60e3) {                 // every 10 minutes: the injury report, transactions, highlights
      seen.nt = now;
      jobs.push(fetch("data/news.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (n) { return R.detectNews(n, seen); }).catch(function () { return []; }));
      jobs.push(fetch("data/highlights-recent.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (h) { return R.detectHighlights(h, seen); }).catch(function () { return []; }));
    }
    Promise.all(jobs).then(function (a) { return Promise.all(jobs2).then(function (b) { return a.concat(b); }); }).then(function (lists) {
      [].concat.apply([], lists).filter(function (m) { return allowed(m, p); }).slice(0, 8).forEach(function (m) {
        var pic = pictureFor(m, p); m.img = pic.img; m.imgs = pic.imgs; show(m);
      });
      save(SEEN, seen);
    });
  }
  function watch() {
    if (watching) return;
    watching = setInterval(tick, 60e3);
    tick();
  }

  // ------------------------------------------------------------ the server (when it's set up)
  function b64u(s) {
    var pad = "=".repeat((4 - s.length % 4) % 4), b = atob((s + pad).replace(/-/g, "+").replace(/_/g, "/"));
    var a = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) a[i] = b.charCodeAt(i); return a;
  }
  function post(path, body) {
    return fetch(WORKER + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json().catch(function () { return {}; }); });
  }
  function subscribe(p) {
    return swReg().then(function (reg) {
      return reg.pushManager.getSubscription().then(function (s) {
        return s || reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64u(KEY) });
      });
    }).then(function (sub) { return post("/subscribe", { subscription: sub.toJSON(), prefs: { types: p.types, teams: p.teams, players: p.players } }); });
  }
  function unsubscribe() {
    return swReg().then(function (reg) { return reg.pushManager.getSubscription(); }).then(function (s) {
      if (!s) return;
      var ep = s.endpoint;
      return s.unsubscribe().then(function () { return post("/unsubscribe", { endpoint: ep }).catch(function () {}); });
    }).catch(function () {});
  }

  // ------------------------------------------------------------ the panel
  var bell, shade;
  function close() {
    if (!shade) return;
    var s = shade; shade = null;
    s.classList.remove("show");
    document.removeEventListener("keydown", onKey);
    setTimeout(function () { s.remove(); }, 220);
    var pt = document.querySelector(".nt-point"); if (pt) pt.remove();
    if (bell) bell.focus();
  }
  function onKey(e) { if (e.key === "Escape") close(); }
  function open(html, after) {
    if (shade) shade.remove();
    shade = document.createElement("div");
    shade.className = "nt-shade";
    shade.innerHTML = '<div class="nt-panel" role="dialog" aria-modal="true" aria-labelledby="nt-title"><button class="nt-x" type="button" aria-label="Close">&times;</button>' + html + "</div>";
    document.body.appendChild(shade);
    shade.addEventListener("click", function (e) { if (e.target === shade) close(); });
    shade.querySelector(".nt-x").addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    requestAnimationFrame(function () { shade.classList.add("show"); });
    if (after) after(shade.querySelector(".nt-panel"));
    var f = shade.querySelector(".nt-panel button:not(.nt-x), .nt-panel input"); if (f) f.focus({ preventScroll: true });
  }

  var SHARE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V3.5"/><path d="M7.5 8 12 3.5 16.5 8"/><path d="M8 11H6.5A1.5 1.5 0 0 0 5 12.5v7A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5v-7a1.5 1.5 0 0 0-1.5-1.5H16"/></svg>';
  var PLUS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><rect x="3.5" y="3.5" width="17" height="17" rx="4"/><path d="M12 8v8M8 12h8"/></svg>';
  var BELL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M6 10a6 6 0 1 1 12 0c0 4.2 1.6 6 2.4 6.8.3.3.1.7-.3.7H3.9c-.4 0-.6-.4-.3-.7C4.4 16 6 14.2 6 10Z"/><path d="M9.8 20.2a2.4 2.4 0 0 0 4.4 0" stroke-linecap="round"/></svg>';

  // a phone or tablet whose browser has no "add to home screen" pop-up of its own: the steps, one at a time
  function homeSteps() {
    var steps = [
      ["Get live game alerts", "On a mobile device, alerts come from the Bradley Analytics app on your home screen. Adding it takes two taps.", BELL],
      ["1. Tap Share", "Tap your browser's <b>Share</b> button (or its menu button).", SHARE],
      ["2. Add to Home Screen", "Choose <b>Add to Home Screen</b>, then confirm.", PLUS],
      ["3. Turn on alerts", "Open Bradley Analytics from your home screen, tap the bell at the top, and choose your alerts.", BELL]
    ];
    var html = '<h2 id="nt-title">Live game alerts</h2><div class="nt-steps">' + steps.map(function (s, i) {
      return '<div class="nt-step' + (i ? "" : " on") + '"><div class="nt-step-art" aria-hidden="true">' + s[2] + "</div><h3>" + s[0] + "</h3><p>" + s[1] + "</p></div>";
    }).join("") + '</div><div class="nt-row"><button type="button" class="nt-btn ghost nt-back" hidden>Back</button><button type="button" class="nt-btn nt-next">Show me how</button></div>' +
      '<div class="nt-dots">' + steps.map(function (s, i) { return "<i" + (i ? "" : ' class="on"') + "></i>"; }).join("") + "</div>";
    open(html, function (pn) {
      var i = 0, els = pn.querySelectorAll(".nt-step"), dots = pn.querySelectorAll(".nt-dots i"), next = pn.querySelector(".nt-next"), back = pn.querySelector(".nt-back");
      function go(n) {
        i = Math.max(0, Math.min(els.length - 1, n));
        els.forEach(function (e, k) { e.classList.toggle("on", k === i); });
        dots.forEach(function (e, k) { e.classList.toggle("on", k === i); });
        back.hidden = i === 0;
        next.textContent = i === 0 ? "Show me how" : i === els.length - 1 ? "Got it" : "Next";
      }
      next.addEventListener("click", function () { if (i === els.length - 1) close(); else go(i + 1); });
      back.addEventListener("click", function () { go(i - 1); });
    });
  }

  // the browser's own "add to home screen" pop-up (Chrome, Edge and Samsung Internet on Android, and computers that offer
  // it); then the alert choices
  function askInstall() {
    var e = installEvt; installEvt = null;
    try { e.prompt(); } catch (err) { settings(); return; }
    Promise.resolve(e.userChoice).then(function (c) {
      if (c && c.outcome === "accepted") toast("<b>Bradley Analytics is on your home screen.</b> Now choose your alerts.", 5000, true);
      settings();
    }).catch(function () { settings(); });
  }

  function settings() {
    var p = prefs();
    var granted = CAN_NOTIFY && Notification.permission === "granted", denied = CAN_NOTIFY && Notification.permission === "denied";
    var html = '<h2 id="nt-title">Live game alerts</h2>' +
      "<p>" + (p.on ? "Alerts are on" + (p.mode === "push" ? "." : " while Bradley Analytics is open in a tab.") : "Get an alert the moment something happens in tonight's games.") + "</p>" +
      '<div class="nt-h">Alert me for</div><div class="nt-opts">' + TYPES.map(function (t) {
        return '<label class="nt-opt"><input type="checkbox" data-type="' + t[0] + '"' + (p.types[t[0]] ? " checked" : "") + '><span class="sw" aria-hidden="true"></span><span><b>' + t[1] + "</b><small>" + t[2] + "</small></span></label>";
      }).join("") + "</div>" +
      '<div class="nt-h">Teams</div><div class="nt-teams">' +
      TEAMS.map(function (t) { return '<button type="button" class="nt-team" data-team="' + t + '" aria-pressed="' + (p.teams.indexOf(t) >= 0) + '"><img alt="" loading="lazy" src="' + logo(t) + '">' + t + "</button>"; }).join("") + "</div>" +
      '<div class="nt-h">Players</div><form class="nt-players"><input type="text" placeholder="e.g. Luka Doncic" autocomplete="off" aria-label="Player name"><button type="submit" class="nt-btn ghost">Add</button></form>' +
      '<div class="nt-chips"></div><div class="nt-hint">Pick any mix of teams and players. Teams: everything about their games, plus their injuries and moves. Players: their big nights, injuries and moves. Nothing picked: every game (injury alerts need a pick).</div>' +
      '<div class="nt-row">' +
      (p.on ? '<button type="button" class="nt-btn nt-save">Save</button><button type="button" class="nt-btn ghost nt-test">Send a test</button><button type="button" class="nt-btn ghost nt-off">Turn off</button>'
        : '<button type="button" class="nt-btn nt-on"' + (denied ? " disabled" : "") + ">" + BELL.replace("<svg", '<svg width="16" height="16"') + "Turn on alerts</button>") +
      (installEvt ? '<button type="button" class="nt-btn ghost nt-install">Add to Home Screen</button>' : "") + "</div>" +
      '<div class="nt-status" role="status">' + (denied ? "Notifications are blocked for this site. Allow them in your browser's site settings, then come back." : "") + "</div>";
    open(html, function (pn) {
      var status = pn.querySelector(".nt-status"), chips = pn.querySelector(".nt-chips"), players = p.players.slice();
      function say(t, cls) { status.textContent = t; status.className = "nt-status" + (cls ? " " + cls : ""); }
      function drawChips() {
        chips.innerHTML = players.map(function (n, i) { return '<span class="nt-chip">' + esc(n) + '<button type="button" data-i="' + i + '" aria-label="Remove ' + esc(n) + '">&times;</button></span>'; }).join("");
      }
      drawChips();
      chips.addEventListener("click", function (e) { var b = e.target.closest("button[data-i]"); if (b) { players.splice(+b.getAttribute("data-i"), 1); drawChips(); } });
      pn.querySelector(".nt-players").addEventListener("submit", function (e) {
        e.preventDefault(); var inp = this.querySelector("input"), v = inp.value.trim();
        if (v && players.length < 25 && players.map(fold).indexOf(fold(v)) < 0) { players.push(v); drawChips(); }
        inp.value = ""; inp.focus();
      });
      pn.querySelectorAll(".nt-team").forEach(function (b) { b.addEventListener("click", function () { b.setAttribute("aria-pressed", b.getAttribute("aria-pressed") === "true" ? "false" : "true"); }); });
      function read() {
        var q = prefs(); q.types = {};
        pn.querySelectorAll("[data-type]").forEach(function (c) { q.types[c.getAttribute("data-type")] = c.checked; });
        q.teams = Array.prototype.map.call(pn.querySelectorAll('.nt-team[aria-pressed="true"]'), function (b) { return b.getAttribute("data-team"); });
        q.players = players.slice();
        return q;
      }
      function turnOn(q) {
        q.on = true; q.mode = "local"; save(STORE, q);
        if (!CAN_PUSH) { say("Alerts are on while Bradley Analytics is open in a tab.", "ok"); return Promise.resolve(); }
        say("Turning on…");
        return subscribe(q).then(function () { q.mode = "push"; save(STORE, q); say("Alerts are on, even when the site is closed.", "ok"); })
          .catch(function () { say("Alerts are on while Bradley Analytics is open in a tab (the alert server couldn't be reached).", "ok"); });
      }
      var on = pn.querySelector(".nt-on");
      if (on) on.addEventListener("click", function () {
        var q = read();
        if (!CAN_NOTIFY) { say("This browser can't show notifications.", "err"); return; }
        Promise.resolve(Notification.requestPermission()).then(function (perm) {
          if (perm !== "granted") { say(perm === "denied" ? "Notifications are blocked for this site. Allow them in your browser's site settings." : "Notifications weren't allowed.", "err"); return; }
          return turnOn(q).then(function () {
            refreshBell(); watch();
            show({ tag: "ba-welcome", title: "Alerts are on", body: "Tonight's games, right here.", url: "index.html#live-strip" });
            setTimeout(function () { if (shade) settings(); }, 900);
          });
        });
      });
      var sv = pn.querySelector(".nt-save");
      if (sv) sv.addEventListener("click", function () {
        var q = read();
        save(STORE, q);
        if (q.mode === "push" && CAN_PUSH) subscribe(q).then(function () { say("Saved.", "ok"); }).catch(function () { say("Saved here; the alert server couldn't be reached.", "err"); });
        else say("Saved.", "ok");
      });
      var ts = pn.querySelector(".nt-test");
      if (ts) ts.addEventListener("click", function () {
        show({ tag: "ba-test", title: "Mavericks 101, Lakers 99", body: "2:14 left in the 4th", img: "https://a.espncdn.com/i/teamlogos/nba/500/dal.png", imgs: ["https://a.espncdn.com/i/teamlogos/nba/500/dal.png", "https://a.espncdn.com/i/teamlogos/nba/500/lal.png"], url: "index.html#live-strip" });
        say(Notification.permission === "granted" ? "Test sent." : "Notifications aren't allowed for this site.", Notification.permission === "granted" ? "ok" : "err");
      });
      var off = pn.querySelector(".nt-off");
      if (off) off.addEventListener("click", function () {
        var q = read(); q.on = false; var was = q.mode; q.mode = ""; save(STORE, q);
        if (was === "push") unsubscribe();
        if (watching) { clearInterval(watching); watching = 0; }
        refreshBell(); settings();
      });
      var ins = pn.querySelector(".nt-install");
      if (ins) ins.addEventListener("click", function () {
        var e = installEvt; installEvt = null; ins.remove();
        if (e) { e.prompt(); }
      });
    });
  }

  function panel() {
    save(NUDGED, 1);
    if (bell) bell.classList.remove("nudge");
    // on a phone or tablet the site goes on the home screen first: with the browser's own pop-up where it has one,
    // otherwise with the steps (iPhones and iPads can only send alerts from the home screen app)
    if (MOBILE && !STANDALONE) {
      if (installEvt) { askInstall(); return; }
      if (IOS || !CAN_NOTIFY) { homeSteps(); return; }
    }
    if (!CAN_NOTIFY) {
      open('<h2 id="nt-title">Live game alerts</h2><p>This browser can\'t show notifications. Try Chrome, Edge, Firefox or Safari.</p>');
      return;
    }
    settings();
  }
  function refreshBell() {
    if (!bell) return;
    var p = prefs();
    bell.classList.toggle("on", p.on);
    bell.setAttribute("aria-label", p.on ? "Live game alerts: on" : "Live game alerts");
    bell.title = p.on ? "Live game alerts: on" : "Live game alerts";
  }
  function toast(html, ms, plain) {
    var t = document.createElement("div"); t.className = "nt-toast"; t.innerHTML = html; document.body.appendChild(t);
    requestAnimationFrame(function () { t.classList.add("show"); });
    t.addEventListener("click", function () { t.remove(); if (!plain) panel(); });
    setTimeout(function () { t.classList.remove("show"); setTimeout(function () { t.remove(); }, 300); }, ms || 6000);
  }

  function go() {
    bell = document.querySelector(".ba-bell");
    window.addEventListener("beforeinstallprompt", function (e) { e.preventDefault(); installEvt = e; });
    if (!bell) return;
    bell.hidden = false;
    refreshBell();
    bell.addEventListener("click", function (e) { e.stopPropagation(); panel(); });
    if (!load(NUDGED, 0)) {
      bell.classList.add("nudge");
      // one gentle pointer to the bell, the first time someone visits the home or Live page on a phone
      if (/page-(home|live)/.test(document.body.className) && matchMedia("(max-width: 800px)").matches)
        setTimeout(function () { if (!shade && !load(NUDGED, 0)) toast("<b>Live game alerts:</b> tip-offs, finals, close games and big nights. Tap the bell to turn them on.", 7000); }, 15000);
    }
    var p = prefs();
    if (p.on && CAN_NOTIFY) {
      if (Notification.permission !== "granted") { p.on = false; save(STORE, p); refreshBell(); }
      else {
        swReg().catch(function () {});
        if (p.mode !== "push") watch();
        else if (CAN_PUSH && Date.now() - load("ba-notify-sync", 0) > 864e5)     // once a day: re-send the subscription (browsers renew them)
          subscribe(p).then(function () { save("ba-notify-sync", Date.now()); }).catch(function () {});
      }
    }
    if (/[?&]alerts=1/.test(location.search)) panel();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", go); else go();
})();
