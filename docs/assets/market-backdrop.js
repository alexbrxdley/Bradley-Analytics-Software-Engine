/* Bradley Quant -- animated market backdrop (drifting grid)

   Written to be cheap on phones. The earlier version re-allocated its
   full-screen canvas on EVERY resize event (measured: 60 events = 60
   reallocations, ~316 MB of pixel-buffer churn in about a second) and
   redrew at 60 fps forever. Phones fire bursts of resize events while
   pinch-zooming or when the address bar slides, and that churn -- on top
   of the dashboard iframe -- is the kind of load that makes a mobile
   browser reload the whole page. Now:
     - resizes are debounced and only re-allocate when the size really changed
     - size comes from the layout viewport, which pinch-zoom does not change
     - the animation pauses while the page is zoomed or the tab is hidden
     - ~30 fps, 1x pixel density on touch screens (the grid is 1px lines)
*/
(function () {
  var canvas = document.getElementById("bq-backdrop");
  if (!canvas) return;

  var mq = window.matchMedia ? function (q) { return window.matchMedia(q).matches; } : function () { return false; };
  var reduce = mq("(prefers-reduced-motion: reduce)");
  var coarse = mq("(pointer: coarse)");
  var ctx = canvas.getContext("2d");
  var dpr = coarse ? 1 : Math.min(window.devicePixelRatio || 1, 2);
  var w = 0, h = 0, t = 0, last = 0, running = false, chain = 0, resizeTimer = null;

  function layoutSize() {
    var de = document.documentElement;
    return { w: de.clientWidth || window.innerWidth, h: de.clientHeight || window.innerHeight };
  }
  function isZoomed() {
    var vv = window.visualViewport;
    return !!vv && Math.abs(vv.scale - 1) > 0.02;
  }

  function resize(force) {
    var s = layoutSize();
    // A few dozen px of height change is just the mobile address bar; the
    // canvas is stretched to the viewport by CSS, so it doesn't need a new buffer.
    if (!force && Math.abs(s.w - w) < 2 && Math.abs(s.h - h) < 150) return;
    w = s.w;
    h = s.h;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!running) draw();
  }

  function drawGrid() {
    var size = 64;
    var gx = -((t * 0.18) % size);
    var gy = -((t * 0.06) % size);
    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(212, 175, 55, 0.12)";
    ctx.beginPath();
    for (var x = gx; x < w + size; x += size) {
      ctx.moveTo(Math.floor(x) + 0.5, 0);
      ctx.lineTo(Math.floor(x) + 0.5, h);
    }
    for (var y = gy; y < h + size; y += size) {
      ctx.moveTo(0, Math.floor(y) + 0.5);
      ctx.lineTo(w, Math.floor(y) + 0.5);
    }
    ctx.stroke();
  }
  function draw() {
    ctx.clearRect(0, 0, w, h);
    drawGrid();
  }

  function start() {
    if (reduce || running || document.hidden || isZoomed()) return;
    running = true;
    var mine = ++chain;
    (function loop(now) {
      if (!running || mine !== chain) return;
      requestAnimationFrame(loop);
      if (now - last < 33) return;      // ~30 fps: the grid drifts under 0.2px per frame
      last = now;
      t += 2;                            // two steps per drawn frame keeps the original drift speed
      draw();
    })(0);
  }
  function stop() { running = false; }

  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { if (!isZoomed()) resize(false); }, 200);
  });
  document.addEventListener("visibilitychange", function () { if (document.hidden) stop(); else start(); });
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", function () { if (isZoomed()) stop(); else start(); });
  }

  resize(true);
  draw();
  start();
})();
