/* Gets the Bradley Analytics Book ready before anyone opens it: on any page of the site, once the page has loaded and
   the browser is idle, the Book's small page pictures and its first big pages are fetched quietly into the browser's
   cache, so the Portfolio page shows them at once. Once a visit; skipped on slow connections and Data Saver. */
(function () {
  "use strict";
  if (/portfolio/.test(location.pathname)) return;           // (that page loads them itself)
  try { if (sessionStorage.getItem("ba.book.pre")) return; } catch (e) {}
  var c = navigator.connection || {};
  if (c.saveData || /2g/.test(c.effectiveType || "")) return;
  function go() {
    fetch("data/book.json").then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
      if (!d || !d.pictures || !d.pages) return;            // (only the site's own copies: never Google's)
      try { sessionStorage.setItem("ba.book.pre", "1"); } catch (e) {}
      var ext = d.ext || ".webp", list = d.pages.map(function (p) { return d.pictures + "s/" + p + ext; })
        .concat(d.pages.slice(0, 12).map(function (p) { return d.pictures + "l/" + p + ext; }));
      var busy = 0;
      (function pump() {
        while (busy < 3 && list.length) { busy++; var im = new Image(); im.onload = im.onerror = function () { busy--; setTimeout(pump, 30); }; im.src = list.shift(); }
      })();
    }).catch(function () {});
  }
  addEventListener("load", function () { (window.requestIdleCallback || function (f) { setTimeout(f, 1500); })(go, { timeout: 4000 }); });
})();
