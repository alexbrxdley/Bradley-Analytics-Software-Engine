/* On a phone the menu bar scrolls away with the page; scrolling back up a little brings it back (sliding down from the
   top), and scrolling down tucks it away again, so another page is always one swipe up away. On a computer the bar
   already stays at the top. */
(function () {
  "use strict";
  var nav, ph = 0, last = 0, peek = false, acc = 0, mq = window.matchMedia && matchMedia("(max-width: 800px)");
  function sticky() { var cs = getComputedStyle(nav); return cs.position === "sticky" || cs.position === "fixed" && !peek; }
  function set(on) {
    if (on === peek) return;
    peek = on;
    if (on) { ph = nav.offsetHeight; document.body.style.paddingTop = ph + "px"; nav.classList.add("nav-peek"); requestAnimationFrame(function () { nav.classList.add("nav-in"); }); }
    else { nav.classList.remove("nav-in", "nav-peek"); document.body.style.paddingTop = ""; var open = nav.querySelector(".nav-open"); if (open && window.baCloseNav) window.baCloseNav(); }
  }
  function hide() { if (!peek) return; nav.classList.remove("nav-in"); setTimeout(function () { if (!nav.classList.contains("nav-in")) set(false); }, 220); }
  function onScroll() {
    var y = window.pageYOffset || 0, d = y - last; last = y;
    if (!mq || !mq.matches || (!peek && sticky())) return;
    if (y <= (ph || nav.offsetHeight)) { set(false); acc = 0; return; }        // at the top it's in its own place
    if (nav.querySelector(".nav-links.nav-open")) return;                      // (the menu is open: leave it)
    acc = (d < 0) === (acc < 0) ? acc + d : d;
    if (acc < -24) set(true);
    else if (acc > 12 && peek) hide();
  }
  function go() {
    nav = document.querySelector(".site-nav"); if (!nav) return;
    last = window.pageYOffset || 0;
    window.addEventListener("scroll", onScroll, { passive: true });
    if (mq && mq.addEventListener) mq.addEventListener("change", function () { if (!mq.matches) set(false); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", go); else go();
})();
