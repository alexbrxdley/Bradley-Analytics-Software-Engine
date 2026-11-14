/* The highlights player, like YouTube's on a phone. Loaded on every page (_includes/head-extra.html).

   BAMini.open({ vid, title, anchor }) plays a YouTube video. The player is one element on the page's body, so nothing on
   the page (a transform, a stacking order, the dashboard) can hide or clip it:
   - it starts playing at once (muted for a split second where the browser insists, then with sound);
   - its own controls (play/pause, the time bar, sound, full screen, open in the YouTube app) instead of YouTube's: on a
     computer they show while the mouse is over the video; on a phone a tap shows them for a moment;
   - docked: laid exactly over its place on the page (the anchor), scrolling with it, under the menu bar;
   - floating: scroll the anchor away and it moves to a corner of the screen, still playing. Drag it (the video or its
     bar) to any corner, the top ones too, over the menu; it snaps there. Make it bigger or smaller with two fingers
     (pinch), or by dragging any of its edges with a mouse. Its red x puts it back in its place, still playing.
   - across pages: going to another page of the site, it comes back floating on the new page at the second it was at
     (the browser may need a tap to start it again). Its x there closes it.
   - where the browser can (Chrome and Edge on computers), its pop-out button moves it into a small always-on-top window
     that keeps playing over other apps. On iPhone, play it full screen and use the player's own picture-in-picture
     button: it then keeps playing after leaving the site. */
(function () {
  "use strict";
  if (window.BAMini) return;
  var KEY = "ba.mini.now", W_KEY = "ba.mini.w", C_KEY = "ba.mini.corner";
  var box = null, cur = null, io = null, ro = null, timer = null, info = { t: 0, playing: false };
  function ss(k, v) { try { if (v === undefined) return JSON.parse(sessionStorage.getItem(k) || "null"); if (v === null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) { return null; } }
  function ls(k, v) { try { if (v === undefined) return JSON.parse(localStorage.getItem(k) || "null"); localStorage.setItem(k, JSON.stringify(v)); } catch (e) { return null; } }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  var BAR = 30;

  var TOUCH = window.matchMedia && matchMedia("(hover: none)").matches;
  function src(vid, start, auto, own) {
    return "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(vid) + "?autoplay=" + (auto ? 1 : 0) + (auto && TOUCH ? "&mute=1" : "") +
      (own ? "&controls=0&disablekb=1&fs=0&iv_load_policy=3" : "") + "&rel=0&modestbranding=1&playsinline=1&enablejsapi=1" +
      (start > 1 ? "&start=" + Math.floor(start) : "") + "&origin=" + encodeURIComponent(location.origin);
  }
  function build(o) {
    box = document.createElement("div");
    box.className = "bam";
    box.innerHTML = '<div class="bam-bar"><span class="bam-t">' + esc(o.title) + "</span>" +
      ("documentPictureInPicture" in window ? '<button type="button" class="bam-pop" aria-label="Pop the video out into its own window" title="Pop out"><svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><rect x="1.5" y="2.5" width="13" height="10" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="8" y="7" width="5" height="4" rx=".8" fill="currentColor"/></svg></button>' : "") +
      '<button type="button" class="bam-x" aria-label="Close">&times;</button></div>' +
      '<div class="bam-v"><iframe src="' + src(o.vid, o.start || 0, o.autoplay !== false, true) + '" title="' + esc(o.title) + '" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>' +
      '<div class="bam-ui"><button type="button" class="bam-pp" aria-label="Play or pause">' + ICON.pause + '</button><button type="button" class="bam-snd" hidden>' + ICON.mute + "Tap for sound</button>" +
      '<div class="bam-ctl"><span class="bam-time">0:00</span><input class="bam-seek" type="range" min="0" max="1000" value="0" aria-label="Seek">' +
      '<button type="button" class="bam-mu" aria-label="Sound">' + ICON.vol + '</button><button type="button" class="bam-yt" aria-label="Open in the YouTube app" title="Open in YouTube">' + ICON.yt + "</button>" +
      '<button type="button" class="bam-fs" aria-label="Full screen">' + ICON.fs + "</button></div></div></div>" +
      '<i class="bam-e l"></i><i class="bam-e r"></i><i class="bam-e t"></i><i class="bam-e b"></i>';
    document.body.appendChild(box);
    var fr = box.querySelector("iframe");
    fr.addEventListener("load", function () { try { fr.contentWindow.postMessage(JSON.stringify({ event: "listening", id: 1, channel: "widget" }), "*"); } catch (e) {} });
    box.querySelector(".bam-x").addEventListener("click", function (e) { e.stopPropagation(); xClick(); });
    var pop = box.querySelector(".bam-pop"); if (pop) pop.addEventListener("click", function (e) { e.stopPropagation(); popOut(); });
    wireMove(); wireSize(); wireUI();
  }
  var ICON = {
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z" fill="currentColor"/></svg>',
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor"/></svg>',
    vol: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9z" fill="currentColor"/><path d="M16 8.5a5 5 0 0 1 0 7M18.5 6a8.5 8.5 0 0 1 0 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    mute: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9z" fill="currentColor"/><path d="M16 9l5 6M21 9l-5 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    yt: '<svg viewBox="0 0 28 20" aria-hidden="true"><rect width="28" height="20" rx="5" fill="#ff0033"/><path d="M11 5.5v9l8-4.5z" fill="#fff"/></svg>',
    fs: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
  };
  // talking to the YouTube player (its iframe API, by messages)
  function cmd(func, args) { var f = box && box.querySelector("iframe"); try { f.contentWindow.postMessage(JSON.stringify({ event: "command", func: func, args: args || [] }), "*"); } catch (e) {} }
  function mmss(t) { t = Math.max(0, Math.floor(t || 0)); return Math.floor(t / 60) + ":" + ("0" + t % 60).slice(-2); }
  var uiT = 0, wantSound = true, soundTries = 0;
  var uiAt = 0;
  function showUI(ms) { if (!box) return; if (!box.classList.contains("ui")) uiAt = Date.now(); box.classList.add("ui"); clearTimeout(uiT); uiT = setTimeout(function () { if (box && !mouseIn) box.classList.remove("ui"); }, ms || 1200); }
  var mouseIn = false;
  function paint() {
    if (!box) return;
    box.querySelector(".bam-pp").innerHTML = info.playing ? ICON.pause : ICON.play;
    box.querySelector(".bam-mu").innerHTML = info.muted ? ICON.mute : ICON.vol;
    box.querySelector(".bam-time").textContent = mmss(info.t) + (info.dur ? " / " + mmss(info.dur) : "");
    var sk = box.querySelector(".bam-seek"); if (!sk._drag && info.dur) sk.value = Math.round(info.t / info.dur * 1000);
    box.querySelector(".bam-snd").hidden = !(info.muted && wantSound && soundTries > 2);
  }
  function wireUI() {
    var ui = box.querySelector(".bam-ui"), sk = box.querySelector(".bam-seek");
    var on = function (sel, f) { box.querySelector(sel).addEventListener("click", function (e) { e.stopPropagation(); if (Date.now() - gestureAt < 400) return; f(); showUI(1500); }); };
    on(".bam-pp", function () { cmd(info.playing ? "pauseVideo" : "playVideo"); info.playing = !info.playing; paint(); });
    on(".bam-mu", function () { if (info.muted) { cmd("unMute"); cmd("setVolume", [100]); wantSound = true; } else { cmd("mute"); wantSound = false; } info.muted = !info.muted; paint(); });
    on(".bam-snd", function () { cmd("unMute"); cmd("setVolume", [100]); info.muted = false; paint(); });
    on(".bam-yt", function () { cmd("pauseVideo"); window.open("https://www.youtube.com/watch?v=" + encodeURIComponent(cur.vid) + "&t=" + Math.floor(info.t) + "s", "_blank", "noopener"); });
    on(".bam-fs", function () {
      var v = box.querySelector(".bam-v"), f = box.querySelector("iframe");
      var req = v.requestFullscreen || v.webkitRequestFullscreen;
      if (document.fullscreenElement || document.webkitFullscreenElement) (document.exitFullscreen || document.webkitExitFullscreen).call(document);
      else if (req) req.call(v); else if (f.webkitEnterFullscreen) f.webkitEnterFullscreen();
      else window.open("https://www.youtube.com/watch?v=" + encodeURIComponent(cur.vid) + "&t=" + Math.floor(info.t) + "s", "_blank", "noopener");
    });
    ["pointerdown", "touchstart"].forEach(function (ev) { sk.addEventListener(ev, function (e) { e.stopPropagation(); sk._drag = true; }, { passive: true }); });
    sk.addEventListener("input", function () { if (info.dur) { info.t = sk.value / 1000 * info.dur; paint(); } });
    sk.addEventListener("change", function () { sk._drag = false; if (info.dur) cmd("seekTo", [sk.value / 1000 * info.dur, true]); showUI(1500); });
    box.addEventListener("pointerenter", function (e) { if (e.pointerType === "mouse") { mouseIn = true; clearTimeout(uiT); box.classList.add("ui"); } });
    box.addEventListener("pointerleave", function (e) { if (e.pointerType === "mouse") { mouseIn = false; box.classList.remove("ui"); } });
    box.addEventListener("pointermove", function (e) { if (e.pointerType === "mouse") box.classList.add("ui"); });
  }
  // what the video is doing (YouTube tells the page, once asked): to pick it up on the next page at the same second
  window.addEventListener("message", function (e) {
    if (!box || !/youtube/.test(e.origin)) return;
    var d; try { d = typeof e.data === "string" ? JSON.parse(e.data) : e.data; } catch (er) { return; }
    if (!d || d.event !== "infoDelivery" || !d.info) return;
    if (typeof d.info.currentTime === "number") info.t = d.info.currentTime;
    if (typeof d.info.playerState === "number") info.playing = d.info.playerState === 1 || d.info.playerState === 3;
    if (typeof d.info.duration === "number" && d.info.duration > 0) info.dur = d.info.duration;
    if (typeof d.info.muted === "boolean") info.muted = d.info.muted;
    // it started muted (a phone's rule for starting by itself): turn the sound on as soon as it plays
    if (info.playing && info.muted && wantSound && soundTries < 4) { soundTries++; cmd("unMute"); cmd("setVolume", [100]); }
    paint();
  });

  // ------------------------------------------------------------ docked over its place, or floating in a corner
  var mode = "dock", held = false, corner = ls(C_KEY) || "tr", width = ls(W_KEY) || 0;
  function defW() { return innerWidth < 700 ? Math.round(innerWidth * 0.62) : 400; }
  function lay(force) {
    if (!box || (moving && force !== true)) return;                             // (a phone's toolbar resizing the window mid-drag mustn't snap it back)
    if (mode === "dock" && cur.anchor && document.body.contains(cur.anchor)) {
      var r = cur.anchor.getBoundingClientRect();
      box.className = "bam dock";
      box.style.width = r.width + "px"; box.style.left = (r.left + scrollX) + "px"; box.style.top = (r.top + scrollY) + "px";
      return;
    }
    width = Math.max(200, Math.min(width || defW(), innerWidth - 20, 960));
    var h = width * 9 / 16 + BAR, x = corner.charAt(1) === "l" ? 10 : innerWidth - width - 10, y = corner.charAt(0) === "t" ? 10 : innerHeight - h - 10;
    box.className = "bam float" + (box.classList.contains("moving") ? " moving" : "");
    box.setAttribute("data-corner", corner);
    box.style.width = width + "px"; box.style.left = x + "px"; box.style.top = y + "px";
  }
  function setMode(m) {
    if (m === "dock" && !(cur.anchor && document.body.contains(cur.anchor))) m = "float";
    mode = m;
    if (cur.anchor) cur.anchor.classList.toggle("away", m === "float");
    lay();
  }
  function watch(anchor) {
    if (io) io.disconnect(); if (ro) ro.disconnect(); io = ro = null;
    cur.anchor = anchor || null; held = false;
    if (anchor) {
      anchor.style.setProperty("--bam-bar", BAR + "px");
      // just opened: it scrolls into view in its place first, and only floats if you then scroll away
      var since = Date.now();
      var judge = function (vis) { if (vis > 0.35) { held = false; setMode("dock"); } else if (!held && Date.now() - since > 900) setMode("float"); };
      if ("IntersectionObserver" in window) {
        io = new IntersectionObserver(function (es) { judge(es[es.length - 1].intersectionRatio); }, { threshold: [0, 0.2, 0.35, 0.6, 1] });
        io.observe(anchor);
      }
      try { anchor.scrollIntoView({ behavior: "smooth", block: "nearest" }); } catch (e) {}
      setTimeout(function () {
        if (!cur || cur.anchor !== anchor) return;
        var r = anchor.getBoundingClientRect(), seen = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0)) / (r.height || 1);
        judge(seen);
      }, 950);
      if ("ResizeObserver" in window) { ro = new ResizeObserver(lay); ro.observe(anchor); ro.observe(document.body); }
    }
    setMode(anchor ? "dock" : "float");
  }
  function xClick() {
    if (mode === "float" && cur.anchor && document.body.contains(cur.anchor)) { held = true; setMode("dock"); return; }   // back in its place
    close();
  }
  function close() {
    if (io) io.disconnect(); if (ro) ro.disconnect(); io = ro = null;
    if (cur && cur.anchor) cur.anchor.classList.remove("away");
    if (box) box.remove();
    var was = cur; box = null; cur = null; ss(KEY, null);
    if (was && was.onClose) was.onClose();
  }

  // ------------------------------------------------------------ moving it (by its bar) and sizing it (by its edges)
  var moving = false, gestureAt = 0;
  function wireMove() {
    [box.querySelector(".bam-bar"), box.querySelector(".bam-ui")].forEach(grab);
  }
  function grab(bar) {
    var drag = null, pts = {}, pinch = null, start = null;
    bar.addEventListener("pointerdown", function (e) {
      if (e.target.closest("button, input") && !Object.keys(pts).length) return;      // (a second finger can land on a button: still a pinch)
      start = { x: e.clientX, y: e.clientY, t: Date.now(), ui: box.classList.contains("ui") && Date.now() - uiAt > 250 };
      pts[e.pointerId] = [e.clientX, e.clientY];
      try { bar.setPointerCapture(e.pointerId); } catch (er) {}
      var ids = Object.keys(pts);
      if (ids.length === 2 && mode === "float") { var a = pts[ids[0]], b = pts[ids[1]]; pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, w: width }; drag = null; return; }
      if (mode !== "float") return;
      var r = box.getBoundingClientRect(); drag = { dx: e.clientX - r.left, dy: e.clientY - r.top, live: false };
      e.preventDefault();
    });
    bar.addEventListener("pointermove", function (e) {
      if (pts[e.pointerId]) pts[e.pointerId] = [e.clientX, e.clientY];
      if (pinch) { var ids = Object.keys(pts); if (ids.length === 2) { var a = pts[ids[0]], b = pts[ids[1]]; width = pinch.w * Math.hypot(a[0] - b[0], a[1] - b[1]) / pinch.d; moving = true; gestureAt = Date.now(); box.classList.add("moving"); lay(true); } return; }
      if (!drag) return;
      if (!drag.live && start && Math.hypot(e.clientX - start.x, e.clientY - start.y) < 6) return;
      if (!drag.live) { drag.live = true; moving = true; box.classList.add("moving"); }
      box.style.left = (e.clientX - drag.dx) + "px"; box.style.top = (e.clientY - drag.dy) + "px"; gestureAt = Date.now();
    });
    function up(e) {
      delete pts[e.pointerId];
      if (pinch) { gestureAt = Date.now(); if (!Object.keys(pts).length) { pinch = null; moving = false; box.classList.remove("moving"); ls(W_KEY, Math.round(width)); } return; }
      var tap = start && Math.hypot(e.clientX - start.x, e.clientY - start.y) < 6 && Date.now() - start.t < 400;
      if (tap && bar.classList.contains("bam-ui")) {                // a tap on the video: the controls (a second tap: play/pause)
        var fingers = e.pointerType !== "mouse";
        gestureAt = Date.now();                                    // (the click that follows this tap mustn't hit the controls it shows)
        if (!fingers || start.ui) { cmd(info.playing ? "pauseVideo" : "playVideo"); info.playing = !info.playing; paint(); }
        showUI(fingers ? 1200 : 1500);
      }
      start = null;
      if (!drag) return;
      var was = drag.live; drag = null; moving = false; box.classList.remove("moving");
      if (!was) return;
      var r = box.getBoundingClientRect();
      corner = (r.top + r.height / 2 < innerHeight / 2 ? "t" : "b") + (r.left + r.width / 2 < innerWidth / 2 ? "l" : "r");
      ls(C_KEY, corner); lay();
    }
    bar.addEventListener("pointerup", up); bar.addEventListener("pointercancel", up);
  }
  function wireSize() {
    Array.prototype.forEach.call(box.querySelectorAll(".bam-e"), function (h) {
      var rs = null, side = h.classList.contains("l") ? "l" : h.classList.contains("r") ? "r" : h.classList.contains("t") ? "t" : "b";
      h.addEventListener("pointerdown", function (e) {
        if (mode !== "float") return;
        rs = { x: e.clientX, y: e.clientY, w: width }; try { h.setPointerCapture(e.pointerId); } catch (er) {}
        box.classList.add("moving"); e.preventDefault(); e.stopPropagation();
      });
      h.addEventListener("pointermove", function (e) {
        if (!rs) return;
        var dx = e.clientX - rs.x, dy = (e.clientY - rs.y) * 16 / 9;
        // dragging an edge away from the corner it sits in makes it bigger
        var d = side === "l" ? -dx : side === "r" ? dx : side === "t" ? -dy : dy;
        if ((side === "l" && corner.charAt(1) === "l") || (side === "r" && corner.charAt(1) === "r") || (side === "t" && corner.charAt(0) === "t") || (side === "b" && corner.charAt(0) === "b")) d = -d;
        width = rs.w + d; lay();
      });
      function end() { if (!rs) return; rs = null; box.classList.remove("moving"); ls(W_KEY, Math.round(width)); }
      h.addEventListener("pointerup", end); h.addEventListener("pointercancel", end);
    });
  }

  // ------------------------------------------------------------ its own window (Chrome and Edge on computers)
  function popOut() {
    if (!("documentPictureInPicture" in window) || !cur) return;
    var o = cur, t = info.t;
    documentPictureInPicture.requestWindow({ width: 480, height: 270 }).then(function (pw) {
      pw.document.body.style.cssText = "margin:0;background:#000;overflow:hidden";
      pw.document.title = o.title;
      var f = pw.document.createElement("iframe");
      f.src = src(o.vid, t, true); f.allow = "autoplay; encrypted-media; fullscreen";
      f.style.cssText = "border:0;width:100vw;height:100vh;display:block";
      pw.document.body.appendChild(f);
      close();
    }).catch(function () {});
  }

  // ------------------------------------------------------------ to the next page
  function save() {
    if (!cur) return;
    ss(KEY, { vid: cur.vid, title: cur.title, t: info.t, playing: info.playing, at: Date.now() });
  }
  window.addEventListener("pagehide", save);
  document.addEventListener("visibilitychange", function () { if (document.hidden) save(); });

  // ------------------------------------------------------------ watchable where the viewer is
  // A game can come with several videos (data/highlights.json: the NBA's own, plus "alts" from other channels) and the
  // countries each is blocked in. The viewer's country is guessed from the time zone (no request, nothing stored); the
  // first video not blocked there plays, and if YouTube still refuses one (an error from the player), the next one does.
  var TZ_CC = { "Europe/London": "GB", "Europe/Dublin": "IE", "Europe/Lisbon": "PT", "Europe/Madrid": "ES", "Europe/Paris": "FR",
    "Europe/Brussels": "BE", "Europe/Amsterdam": "NL", "Europe/Luxembourg": "LU", "Europe/Berlin": "DE", "Europe/Zurich": "CH",
    "Europe/Vienna": "AT", "Europe/Rome": "IT", "Europe/Malta": "MT", "Europe/Copenhagen": "DK", "Europe/Oslo": "NO",
    "Europe/Stockholm": "SE", "Europe/Helsinki": "FI", "Europe/Warsaw": "PL", "Europe/Prague": "CZ", "Europe/Bratislava": "SK",
    "Europe/Budapest": "HU", "Europe/Ljubljana": "SI", "Europe/Zagreb": "HR", "Europe/Belgrade": "RS", "Europe/Sarajevo": "BA",
    "Europe/Skopje": "MK", "Europe/Tirane": "AL", "Europe/Athens": "GR", "Europe/Sofia": "BG", "Europe/Bucharest": "RO",
    "Europe/Istanbul": "TR", "Europe/Kiev": "UA", "Europe/Kyiv": "UA", "Europe/Vilnius": "LT", "Europe/Riga": "LV",
    "Europe/Tallinn": "EE", "Europe/Moscow": "RU", "Europe/Minsk": "BY", "Europe/Chisinau": "MD", "Atlantic/Reykjavik": "IS",
    "Asia/Nicosia": "CY", "Europe/Monaco": "MC", "Europe/Andorra": "AD", "Asia/Tokyo": "JP", "Asia/Seoul": "KR",
    "Asia/Shanghai": "CN", "Asia/Hong_Kong": "HK", "Asia/Taipei": "TW", "Asia/Manila": "PH", "Asia/Singapore": "SG",
    "Asia/Kolkata": "IN", "Asia/Calcutta": "IN", "Asia/Dubai": "AE", "Asia/Jerusalem": "IL", "Australia/Sydney": "AU",
    "Australia/Melbourne": "AU", "Australia/Perth": "AU", "Australia/Brisbane": "AU", "Pacific/Auckland": "NZ",
    "America/Toronto": "CA", "America/Vancouver": "CA", "America/Montreal": "CA", "America/Mexico_City": "MX",
    "America/Sao_Paulo": "BR", "America/Argentina/Buenos_Aires": "AR", "Africa/Lagos": "NG", "Africa/Johannesburg": "ZA" };
  function viewerCC() {
    try { var tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; if (TZ_CC[tz]) return TZ_CC[tz]; if (/^America\//.test(tz)) return "US"; } catch (e) {}
    return "";
  }
  function watchable(v, cc) {
    if (!v || !v.id) return false;
    if (!cc) return true;
    if (v.allowed && v.allowed.indexOf(cc) < 0) return false;
    return !(v.blocked && v.blocked.indexOf(cc) >= 0);
  }
  // the videos to try, in order: the ones watchable here first (the NBA's own first among them)
  function playlist(o) {
    var all = [{ id: o.vid, blocked: o.blocked, allowed: o.allowed }].concat(o.alts || []), cc = viewerCC();
    var ok = all.filter(function (v) { return watchable(v, cc); }), rest = all.filter(function (v) { return !watchable(v, cc) && v.id; });
    return ok.concat(rest).map(function (v) { return v.id; });
  }
  function nextVideo() {                                   // YouTube refused this one: the next one, in place
    if (!cur || !cur.queue || !cur.queue.length || !box) return false;
    var nv = cur.queue.shift(), f = box.querySelector("iframe");
    cur.vid = nv; info = { t: 0, playing: true };
    f.src = src(nv, 0, true, true);
    return true;
  }
  window.addEventListener("message", function (e) {
    if (!box || !/youtube/.test(e.origin)) return;
    var d; try { d = typeof e.data === "string" ? JSON.parse(e.data) : e.data; } catch (er) { return; }
    if (d && d.event === "onError") nextVideo();
  });

  var api = {
    open: function (o) {
      var q = playlist(o);
      if (q.length) o = Object.assign({}, o, { vid: q[0] });
      if (cur && cur.vid === o.vid && box) { cur.title = o.title || cur.title; cur.onClose = o.onClose; watch(o.anchor); return; }   // already playing it: just give it its place
      if (box) close();
      cur = { vid: o.vid, title: o.title || "Highlights", onClose: o.onClose, queue: q.slice(1), all: q };
      info = { t: o.start || 0, playing: true };
      build({ vid: o.vid, title: cur.title, start: o.start, autoplay: o.autoplay });
      watch(o.anchor);
    },
    adopt: function (vid, anchor, onClose) { if (cur && cur.vid === vid && box) { cur.onClose = onClose; watch(anchor); return true; } return false; },
    release: function () { if (cur) watch(null); },          // its place is gone: keep playing in the corner
    close: close,
    vid: function () { return cur ? cur.vid : null; },
    has: function (id) { return !!(cur && (cur.vid === id || (cur.all || []).indexOf(id) >= 0)); }
  };
  window.BAMini = api;
  addEventListener("resize", lay);
  setInterval(function () { if (box && mode === "dock") lay(); }, 400);   // (the page's layout can shift under it)

  // a video that was playing on the page before this one picks up where it was
  var was = ss(KEY);
  if (was && was.vid && Date.now() - was.at < 30 * 60e3 && was.playing) {
    var go = function () { api.open({ vid: was.vid, title: was.title, start: was.t, anchor: null }); };
    if (document.body) go(); else document.addEventListener("DOMContentLoaded", go);
  } else ss(KEY, null);
})();
