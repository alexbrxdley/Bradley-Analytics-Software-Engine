/* Bradley Quant -- animated market backdrop (drifting grid) */
(function () {
  var canvas = document.getElementById("bq-backdrop");
  if (!canvas) return;

  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var ctx = canvas.getContext("2d");
  var dpr = Math.min(window.devicePixelRatio || 1, 2);
  var w = 0, h = 0;

  function resize() {
    w = window.innerWidth;
    h = window.innerHeight;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();
  window.addEventListener("resize", resize);

  var t = 0;

  function drawGrid() {
    var size = 64;
    var gx = -((t * 0.18) % size);
    var gy = -((t * 0.06) % size);
    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(212, 175, 55, 0.055)";
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

  function frame() {
    ctx.clearRect(0, 0, w, h);
    drawGrid();
    if (!reduce) {
      t += 1;
      requestAnimationFrame(frame);
    }
  }
  frame();
})();
