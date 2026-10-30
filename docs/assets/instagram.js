/* The @bradleyanalytics Instagram profile and latest posts, in the site's own dark style.

   The posts come from Behold (behold.so), which keeps a public JSON copy of the profile's latest posts up to date:
   connect the Instagram account there once, create a JSON feed, and put its feed ID in docs/_config.yml as
   behold_feed_id. Until then (or if Behold can't be reached) a link card to the profile is shown instead.

   Markup: <div class="ba-insta" data-feed="FEED_ID" data-count="12"></div> */
(function () {
  "use strict";
  var PROFILE = "https://www.instagram.com/bradleyanalytics/";
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  function k(n) { n = +n || 0; return n >= 1e6 ? (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M" : n >= 1e4 ? Math.round(n / 1e3) + "K" : n >= 1e3 ? (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K" : String(n); }
  var IG = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="5" stroke="currentColor" stroke-width="1.8"/>' +
    '<circle cx="12" cy="12" r="4.2" stroke="currentColor" stroke-width="1.8"/><circle cx="17.4" cy="6.6" r="1.2" fill="currentColor"/></svg>';
  function fallback(box) {
    box.innerHTML = '<a class="ig-card ig-fallback" href="' + PROFILE + '" target="_blank" rel="noopener">' +
      '<span class="ig-avatar"><img src="assets/footer-icon.png?v=2" alt=""></span>' +
      '<span class="ig-who"><b>@bradleyanalytics</b><span>Bradley Analytics on Instagram</span></span>' +
      '<span class="ig-follow">' + IG + "Follow</span></a>";
  }
  function render(box, d, count) {
    var posts = (Array.isArray(d) ? d : d.posts || []).slice(0, count);
    var user = (!Array.isArray(d) && d.username) || "bradleyanalytics";
    var head = '<a class="ig-card" href="' + PROFILE + '" target="_blank" rel="noopener">' +
      '<span class="ig-avatar"><img src="' + esc(d.profilePictureUrl || "assets/footer-icon.png?v=2") + '" alt=""></span>' +
      '<span class="ig-who"><b>@' + esc(user) + "</b><span>" +
      (d.followersCount != null ? (d.postsCount != null ? "<i>" + k(d.postsCount) + "</i> posts &nbsp; " : "") + "<i>" + k(d.followersCount) + "</i> followers &nbsp; <i>" + k(d.followsCount) + "</i> following"
        : "Bradley Analytics on Instagram") + "</span></span>" +
      '<span class="ig-follow">' + IG + "Follow</span></a>";
    var grid = posts.map(function (p) {
      var sz = p.sizes || {}, src = (sz.medium && sz.medium.mediaUrl) || p.img || p.thumbnailUrl || p.mediaUrl || "";
      var video = p.mediaType === "VIDEO" || p.isReel, many = p.mediaType === "CAROUSEL_ALBUM";
      return '<a class="ig-post" href="' + esc(p.permalink || PROFILE) + '" target="_blank" rel="noopener" title="' + esc((p.prunedCaption || p.caption || "").slice(0, 140)) + '">' +
        '<img loading="lazy" src="' + esc(src) + '" alt="' + esc((p.prunedCaption || p.caption || "Instagram post").slice(0, 100)) + '">' +
        (video ? '<span class="ig-kind" aria-label="Video">&#9654;</span>' : many ? '<span class="ig-kind" aria-label="Several photos">&#10697;</span>' : "") + "</a>";
    }).join("");
    box.innerHTML = head + (grid ? '<div class="ig-grid">' + grid + "</div>" : "") +
      '<a class="ig-more" href="' + PROFILE + '" target="_blank" rel="noopener">See more on Instagram <span aria-hidden="true">&#8599;</span></a>';
  }
  function mount(box) {
    var feed = (box.getAttribute("data-feed") || "").trim(), count = parseInt(box.getAttribute("data-count"), 10) || 9;
    if (!feed) { fallback(box); return; }
    // the live feed (the latest 6 on Behold's free plan), topped up from the site's own archive of older posts
    var live = fetch("https://feeds.behold.so/" + encodeURIComponent(feed)).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
    var archive = fetch("data/instagram.json", { cache: "no-cache" }).then(function (r) { return r.ok ? r.json() : { posts: [] }; }).catch(function () { return { posts: [] }; });
    Promise.all([live.catch(function () { return null; }), archive]).then(function (r) {
      var d = r[0], old = (r[1] && r[1].posts) || [];
      if (!d && !old.length) { fallback(box); return; }
      d = d || { posts: [] };
      var seen = {}, posts = (d.posts || []).concat(old).filter(function (p) { if (seen[p.id]) return false; seen[p.id] = 1; return true; });
      posts.sort(function (a, b) { return String(b.timestamp || "").localeCompare(String(a.timestamp || "")); });
      d.posts = posts;
      render(box, d, count);
    });
  }
  function go() { Array.prototype.forEach.call(document.querySelectorAll(".ba-insta"), mount); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", go); else go();
})();
