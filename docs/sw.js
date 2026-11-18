/* The site's service worker: it shows the live game alerts (assets/notify.js) and, when the notification server in
   worker/ is set up, receives them while the site is closed. It doesn't cache anything: pages always load fresh. */
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });

// the alert's picture, drawn as the page draws it: a game's two team logos side by side as they are (see-through, no
// circle), or a player's face cut into a see-through circle with a ring in his team's colour
var CELTICS_PNG = "assets/logos/Boston-Celtics-Current-Logo.png";
function bitmap(src) {
  return fetch(new URL(src, self.registration.scope).href, { mode: "cors" }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.blob(); }).then(createImageBitmap);
}
function icon(m) {
  var srcs = (m.imgs && m.imgs.filter(Boolean).length ? m.imgs : [m.img]).filter(Boolean);
  if (!srcs.length || typeof OffscreenCanvas === "undefined" || typeof createImageBitmap === "undefined") return Promise.resolve(srcs[0] || "assets/icon-192.png");
  var timeout = new Promise(function (r) { setTimeout(function () { r(srcs[0]); }, 4000); });
  var draw = Promise.all(srcs.map(function (u) { return bitmap(u).catch(function () { return null; }); })).then(function (ims) {
    var N = 192, c = new OffscreenCanvas(N, N), x = c.getContext("2d"), got = ims.filter(Boolean);
    if (!got.length) throw new Error("no pictures");
    if (m.round && got.length === 1) {
      var im = got[0], w = im.width, h = im.height;
      x.save(); x.beginPath(); x.arc(N / 2, N / 2, N / 2 - 8, 0, Math.PI * 2); x.clip();
      var k = (N - 16) * 1.25 / h; x.drawImage(im, N / 2 - w * k / 2, 8 - h * k * 0.04, w * k, h * k);
      x.restore();
      x.beginPath(); x.arc(N / 2, N / 2, N / 2 - 4.5, 0, Math.PI * 2); x.lineWidth = 7; x.strokeStyle = m.ring || "#D4AF37"; x.stroke();
    } else {
      var n = ims.length, cell = N / n;
      ims.forEach(function (im, i) { if (!im) return; var k2 = (cell * (n > 1 ? 0.96 : 0.92)) / Math.max(im.width, im.height); x.drawImage(im, cell * i + cell / 2 - im.width * k2 / 2, N / 2 - im.height * k2 / 2, im.width * k2, im.height * k2); });
    }
    return c.convertToBlob({ type: "image/png" });
  }).then(function (blob) { return blob.arrayBuffer(); }).then(function (buf) {
    var b = new Uint8Array(buf), s = "";
    for (var i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
    return "data:image/png;base64," + btoa(s);
  }).catch(function () { return srcs[0]; });
  return Promise.race([draw, timeout]);
}

self.addEventListener("push", function (e) {
  var m = {};
  try { m = e.data ? e.data.json() : {}; } catch (err) { m = { body: e.data ? e.data.text() : "" }; }
  e.waitUntil(icon(m).then(function (ic) {
    return self.registration.showNotification(m.title || "Bradley Analytics", {
      body: m.body || "",
      tag: m.tag || undefined,
      icon: ic,
      badge: "favicon-32x32.png",
      data: { url: m.url || "index.html#live-strip" }
    });
  }));
});

self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  var url = new URL((e.notification.data && e.notification.data.url) || "index.html#live-strip", self.registration.scope).href;
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].url === url && "focus" in list[i]) return list[i].focus();
    }
    return self.clients.openWindow ? self.clients.openWindow(url) : null;
  }));
});

