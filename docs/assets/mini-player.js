/* The highlights player, like YouTube's on a phone. Loaded on every page (_includes/head-extra.html).

   BAMini.open({ vid, title, anchor }) plays a YouTube video. The player is one element on the page's body, so nothing on
   the page (a transform, a stacking order, the dashboard) can hide or clip it:
   - docked: laid exactly over its place on the page (the anchor), scrolling with it;
   - floating: scroll the anchor away and it moves to a corner of the screen, still playing. Drag it by its bar to any
     corner, the top ones too (over the menu); it snaps there. Make it bigger or smaller by dragging any of its edges, or
     by pinching its bar with two fingers. Its red x puts it back in its place, still playing.
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

  function src(vid, start, auto) {
    return "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(vid) + "?autoplay=" + (auto ? 1 : 0) + "&rel=0&modestbranding=1&playsinline=1&enablejsapi=1" +
      (start > 1 ? "&start=" + Math.floor(start) : "") + "&origin=" + encodeURIComponent(location.origin);
  }
  function build(o) {
    box = document.createElement("div");
    box.className = "bam";
    box.innerHTML = '<div class="bam-bar"><span class="bam-t">' + esc(o.title) + "</span>" +
      ("documentPictureInPicture" in window ? '<button type="button" class="bam-pop" aria-label="Pop the video out into its own window" title="Pop out"><svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><rect x="1.5" y="2.5" width="13" height="10" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="8" y="7" width="5" height="4" rx=".8" fill="currentColor"/></svg></button>' : "") +
      '<button type="button" class="bam-x" aria-label="Close">&times;</button></div>' +
      '<div class="bam-v"><iframe src="' + src(o.vid, o.start || 0, o.autoplay !== false) + '" title="' + esc(o.title) + '" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe></div>' +
      '<i class="bam-e l"></i><i class="bam-e r"></i><i class="bam-e t"></i><i class="bam-e b"></i>';
    document.body.appendChild(box);
    var fr = box.querySelector("iframe");
    fr.addEventListener("load", function () { try { fr.contentWindow.postMessage(JSON.stringify({ event: "listening", id: 1, channel: "widget" }), "*"); } catch (e) {} });
    box.querySelector(".bam-x").addEventListener("click", function (e) { e.stopPropagation(); xClick(); });
    var pop = box.querySelector(".bam-pop"); if (pop) pop.addEventListener("click", function (e) { e.stopPropagation(); popOut(); });
    wireMove(); wireSize();
  }
  // what the video is doing (YouTube tells the page, once asked): to pick it up on the next page at the same second
  window.addEventListener("message", function (e) {
    if (!box || !/youtube/.test(e.origin)) return;
    var d; try { d = typeof e.data === "string" ? JSON.parse(e.data) : e.data; } catch (er) { return; }
    if (!d || d.event !== "infoDelivery" || !d.info) return;
    if (typeof d.info.currentTime === "number") info.t = d.info.currentTime;
    if (typeof d.info.playerState === "number") info.playing = d.info.playerState === 1 || d.info.playerState === 3;
  });

  // ------------------------------------------------------------ docked over its place, or floating in a corner
  var mode = "dock", held = false, corner = ls(C_KEY) || "tr", width = ls(W_KEY) || 0;
  function defW() { return innerWidth < 700 ? Math.round(innerWidth * 0.62) : 400; }
  function lay() {
    if (!box) return;
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
  function wireMove() {
    var bar = box.querySelector(".bam-bar"), drag = null, pts = {}, pinch = null;
    bar.addEventListener("pointerdown", function (e) {
      if (e.target.closest("button")) return;
      pts[e.pointerId] = [e.clientX, e.clientY];
      try { bar.setPointerCapture(e.pointerId); } catch (er) {}
      var ids = Object.keys(pts);
      if (ids.length === 2 && mode === "float") { var a = pts[ids[0]], b = pts[ids[1]]; pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, w: width }; drag = null; return; }
      if (mode !== "float") return;
      var r = box.getBoundingClientRect(); drag = { dx: e.clientX - r.left, dy: e.clientY - r.top };
      box.classList.add("moving"); e.preventDefault();
    });
    bar.addEventListener("pointermove", function (e) {
      if (pts[e.pointerId]) pts[e.pointerId] = [e.clientX, e.clientY];
      if (pinch) { var ids = Object.keys(pts); if (ids.length === 2) { var a = pts[ids[0]], b = pts[ids[1]]; width = pinch.w * Math.hypot(a[0] - b[0], a[1] - b[1]) / pinch.d; lay(); } return; }
      if (!drag) return;
      box.style.left = (e.clientX - drag.dx) + "px"; box.style.top = (e.clientY - drag.dy) + "px";
    });
    function up(e) {
      delete pts[e.pointerId];
      if (pinch) { if (!Object.keys(pts).length) { pinch = null; ls(W_KEY, Math.round(width)); } return; }
      if (!drag) return; drag = null; box.classList.remove("moving");
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

  var api = {
    open: function (o) {
      if (cur && cur.vid === o.vid && box) { cur.title = o.title || cur.title; cur.onClose = o.onClose; watch(o.anchor); return; }   // already playing it: just give it its place
      if (box) close();
      cur = { vid: o.vid, title: o.title || "Highlights", onClose: o.onClose };
      info = { t: o.start || 0, playing: true };
      build({ vid: o.vid, title: cur.title, start: o.start, autoplay: o.autoplay });
      watch(o.anchor);
    },
    adopt: function (vid, anchor, onClose) { if (cur && cur.vid === vid && box) { cur.onClose = onClose; watch(anchor); return true; } return false; },
    release: function () { if (cur) watch(null); },          // its place is gone: keep playing in the corner
    close: close,
    vid: function () { return cur ? cur.vid : null; }
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
