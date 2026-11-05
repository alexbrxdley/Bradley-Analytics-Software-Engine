/* The animated cover of Blacktop on the Games page, painted like the game itself (games/blacktop, "dark deco"): a
   night court in Back Bay under a blood-red sky. CPU vs CPU -- Tatum (green, 0) against SGA (blue, 2): size-up,
   crossover, pull-up, swish through the chain net, then the other way.

   The scene is drawn in real perspective (a camera 6 ft up at the sideline): the blacktop with its worn paint, cracks
   and patches, the chain-link fence, two sodium lamps throwing pools of light and long shadows, a steel playground
   hoop. Behind it, Back Bay in layers: brownstones with bay windows and chimneys just past the fence, the landmarks
   (the Berkeley Building and its beacon, Copley Place, Old South's campanile, the Pru, 111 Huntington's crown, One
   Dalton, Trinity Church, the Hancock), a hazy far city, a big low moon, searchlights, drifting deco clouds, a plane.
   The still parts are painted once into layers; only what moves is drawn each frame. It runs only while it's on the
   screen, and holds a still frame for anyone who prefers reduced motion.

   Markup: <canvas class="bt-cover"></canvas> */
(function () {
  "use strict";
  var cv = document.querySelector("canvas.bt-cover");
  if (!cv || !cv.getContext) return;
  var x = cv.getContext("2d");
  var REDUCE = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  var W = 1000, H = 430, dpr = 1, scale = 1, ox = 0, oy = 0;
  function seeded(s) { return function () { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; }; }
  var rnd = seeded(11);
  var DECO = { sky0: "#040102", sky1: "#1a0504", sky2: "#521208", hor: "#b8401a", haze: "#7a240f", ink: "#090404", ink2: "#140706" };

  // ------------------------------------------------------------ the camera: 6 ft up, looking along the court
  var F = 573, CAMH = 8, HZ = 250, CX = 330, ZC = 37;      // ZC: the middle of the court, across
  function pj(X, z, h) { var s = F / z; return [CX + X * s, HZ + (CAMH - (h || 0)) * s]; }
  var CITY = HZ + 8;                                            // where the city meets the ground, far past the fence
  var RIM = { X: 33.75, z: ZC, h: 10 }, BOARD_X = 35;

  // ------------------------------------------------------------ layers painted once (at the canvas's real size)
  var layers = {};
  function layer(draw) {
    var c = document.createElement("canvas"); c.width = cv.width; c.height = cv.height;
    var g = c.getContext("2d"); g.setTransform(dpr * scale, 0, 0, dpr * scale, dpr * ox, dpr * oy);
    draw(g); return c;
  }

  // the sky's still part: the gradient, light pollution over the city, stars
  var stars = []; for (var i = 0; i < 90; i++) stars.push({ x: rnd() * W, y: rnd() * 110, r: 0.3 + rnd() * 0.9, p: rnd() * 6.28 });
  function paintSky(g) {
    var s = g.createLinearGradient(0, 0, 0, CITY);
    s.addColorStop(0, DECO.sky0); s.addColorStop(0.32, DECO.sky1); s.addColorStop(0.7, DECO.sky2); s.addColorStop(1, DECO.hor);
    g.fillStyle = s; g.fillRect(-20, -20, W + 40, CITY + 30);
    var glow = g.createRadialGradient(560, CITY + 40, 20, 560, CITY + 40, 520);            // the city's own glow
    glow.addColorStop(0, "rgba(255,120,60,.30)"); glow.addColorStop(1, "rgba(255,120,60,0)");
    g.fillStyle = glow; g.fillRect(-20, -20, W + 40, CITY + 30);
  }

  // Back Bay: far haze towers, the landmarks, then brownstones just past the fence
  var lit = [];                                             // windows that flicker now and then
  function windowsIn(g, x0, x1, top, base, opt) {
    opt = opt || {};
    var cw = opt.cw || 5, ch = opt.ch || 6, gx = opt.gx || 3, gy = opt.gy || 4;
    for (var wy = base - (opt.skip || 8); wy > top + 6; wy -= ch + gy) for (var wx = x0 + 3; wx < x1 - cw - 2; wx += cw + gx) {
      var r = rnd();
      if (r < (opt.on || 0.16)) {
        var warm = rnd() < 0.8, a = 0.45 + rnd() * 0.5;
        g.fillStyle = warm ? "rgba(255,190,120," + a + ")" : "rgba(170,200,255," + a * 0.7 + ")"; g.fillRect(wx, wy, cw, ch * 0.75);
        if (rnd() < 0.08) lit.push({ x: wx, y: wy, w: cw, h: ch * 0.75, p: rnd() * 6.28, s: 0.15 + rnd() * 0.4 });
      } else if (r < (opt.on || 0.16) + 0.25) { g.fillStyle = "rgba(255,120,80,.05)"; g.fillRect(wx, wy, cw, ch * 0.75); }
    }
  }
  function poly(g, pts, base) { g.beginPath(); pts.forEach(function (q, k) { var y = base - q[1]; if (k) g.lineTo(q[0], y); else g.moveTo(q[0], y); }); g.closePath(); }
  function inkGrad(g, top, base, far) {
    var s = g.createLinearGradient(0, base - top, 0, base);
    if (far) { s.addColorStop(0, "#2a0b07"); s.addColorStop(1, "#5a1a0b"); }
    else { s.addColorStop(0, DECO.ink); s.addColorStop(0.65, DECO.ink2); s.addColorStop(1, "#3a1209"); }
    return s;
  }
  function rim(g, pts, base, a) { g.strokeStyle = "rgba(255,95,45," + (a || 0.28) + ")"; g.lineWidth = 0.9; poly(g, pts, base); g.stroke(); }
  function uplight(g, x0, x1, top, base, h) {
    var s = g.createLinearGradient(0, base, 0, base - h);
    s.addColorStop(0, "rgba(255,150,90,.42)"); s.addColorStop(1, "rgba(255,150,90,0)");
    g.save(); g.clip(); g.fillStyle = s; g.fillRect(x0, base - h, x1 - x0, h); g.restore();
  }
  var B = CITY;
  var LANDMARKS = [
    // the Berkeley Building: stepped top and its weather beacon
    { pts: [[60, 0], [60, 84], [66, 84], [66, 104], [72, 104], [72, 120], [78, 120], [94, 138], [110, 120], [116, 120], [116, 104], [122, 104], [122, 84], [128, 84], [128, 0]], stone: true, beacon: [94, 176], spire: [94, 138, 170] },
    // Copley Place's two towers
    { pts: [[150, 0], [150, 112], [162, 120], [192, 120], [204, 112], [204, 0]], win: { on: 0.2 } },
    { pts: [[212, 0], [212, 96], [222, 102], [248, 102], [258, 96], [258, 0]], win: { on: 0.18 } },
    // Old South Church's campanile: arched belfry, steep cap
    { pts: [[286, 0], [286, 92], [284, 92], [284, 98], [288, 98], [288, 126], [292, 140], [296, 126], [296, 98], [300, 98], [300, 92], [298, 92], [298, 0]], stone: true, belfry: [292, 108] },
    // the Pru: the stepped hat and the mast
    { pts: [[330, 0], [330, 30], [346, 30], [346, 222], [350, 222], [350, 236], [354, 236], [354, 244], [394, 244], [394, 236], [398, 236], [398, 222], [402, 222], [402, 30], [418, 30], [418, 0]], mast: [374, 244, 288], band: [346, 210, 402, 215], win: { on: 0.22, cw: 3, ch: 4, gx: 2, gy: 3 } },
    // 111 Huntington: the ribbed crown
    { pts: [[436, 0], [436, 156], [474, 156], [474, 0]], crown: [455, 156, 18], win: { on: 0.2, cw: 3, ch: 4, gx: 2, gy: 3 } },
    // One Dalton: curved glass
    { pts: [[492, 0], [494, 204], [498, 214], [506, 222], [518, 222], [524, 214], [528, 204], [530, 0]], glass: true, win: { on: 0.12, cw: 2, ch: 3, gx: 2, gy: 3 } },
    // Trinity Church: the central tower, the turrets, the gable
    { pts: [[562, 0], [562, 30], [576, 44], [590, 30], [602, 30], [602, 56], [606, 56], [606, 70], [618, 92], [630, 70], [630, 56], [634, 56], [634, 30], [646, 30], [660, 44], [674, 30], [674, 0]], stone: true, turrets: [[604, 70], [632, 70]], arches: [618, 40] },
    // the Hancock: a glass slab with its notched edge
    { pts: [[716, 0], [720, 252], [790, 246], [792, 140], [796, 140], [796, 0]], glass: true, hancock: true },
    // the Boston Public Library: the long palazzo
    { pts: [[812, 0], [812, 30], [820, 34], [980, 34], [988, 30], [988, 0]], stone: true, bpl: true }
  ];
  // (the landmarks a little lower than life, so the tallest still fit the frame)
  LANDMARKS.forEach(function (b) {
    var k = 0.8, sy = function (q, i) { if (q) q[i] *= k; };
    b.pts.forEach(function (q) { q[1] *= k; });
    sy(b.beacon, 1); sy(b.spire, 1); sy(b.spire, 2); sy(b.mast, 1); sy(b.mast, 2); sy(b.band, 1); sy(b.band, 3); sy(b.crown, 1); sy(b.belfry, 1); sy(b.arches, 1);
    if (b.turrets) b.turrets.forEach(function (q) { q[1] *= k; });
  });
  function paintCity(g) {
    // far city in the haze
    var fr = seeded(3);
    for (var fx = -10; fx < W + 10; fx += 10 + fr() * 22) {
      var h = 40 + fr() * 90, w = 14 + fr() * 26, base = B + 2;
      g.fillStyle = inkGrad(g, h, base, true); g.fillRect(fx, base - h, w, h);
      for (var k = 0; k < 6; k++) if (fr() < 0.6) { g.fillStyle = "rgba(255,170,110," + (0.12 + fr() * 0.25) + ")"; g.fillRect(fx + 2 + fr() * (w - 4), base - fr() * h, 1.6, 1.6); }
    }
    var hz = g.createLinearGradient(0, B - 140, 0, B);
    hz.addColorStop(0, "rgba(122,36,15,0)"); hz.addColorStop(1, "rgba(150,48,20,.55)");
    g.fillStyle = hz; g.fillRect(-10, B - 140, W + 20, 142);
    // the landmarks
    LANDMARKS.forEach(function (b) {
      var xs = b.pts.map(function (q) { return q[0]; }), top = Math.max.apply(null, b.pts.map(function (q) { return q[1]; }));
      var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
      g.fillStyle = inkGrad(g, top, B); poly(g, b.pts, B); g.fill();
      if (b.glass) {                                         // glass holding the red sky and the moon
        g.save(); poly(g, b.pts, B); g.clip();
        var sh = g.createLinearGradient(x0, B - top, x1, B - top * 0.3);
        sh.addColorStop(0, "rgba(255,95,40,.20)"); sh.addColorStop(0.45, "rgba(120,30,14,.08)"); sh.addColorStop(0.55, "rgba(255,170,120,.20)"); sh.addColorStop(1, "rgba(0,0,0,.1)");
        g.fillStyle = sh; g.fillRect(x0, B - top, x1 - x0, top);
        g.strokeStyle = "rgba(255,140,90,.07)"; g.lineWidth = 0.6;
        for (var y = B - top; y < B; y += 4) { g.beginPath(); g.moveTo(x0, y); g.lineTo(x1, y - 1); g.stroke(); }
        if (b.hancock) { g.fillStyle = "rgba(255,200,160,.10)"; g.fillRect(746, B - top + 12, 10, top * 0.5); }
        g.restore();
      }
      if (b.win) { g.save(); poly(g, b.pts, B); g.clip(); windowsIn(g, x0, x1, B - top, B, b.win); g.restore(); }
      if (b.stone) { poly(g, b.pts, B); uplight(g, x0, x1, top, B, Math.min(80, top)); }
      rim(g, b.pts, B, b.stone ? 0.3 : 0.24);
      if (b.band) { g.fillStyle = "rgba(255,175,115,.6)"; g.fillRect(b.band[0], B - b.band[3], b.band[2] - b.band[0], b.band[3] - b.band[1]); }
      if (b.spire) { g.fillStyle = DECO.ink; g.fillRect(b.spire[0] - 1, B - b.spire[2], 2, b.spire[2] - b.spire[1]); }
      if (b.mast) { g.fillStyle = DECO.ink; g.fillRect(b.mast[0] - 1.2, B - b.mast[2], 2.4, b.mast[2] - b.mast[1]); }
      if (b.belfry) { g.fillStyle = "rgba(255,160,100,.55)"; [-3, 3].forEach(function (d) { g.beginPath(); g.moveTo(b.belfry[0] + d - 1.6, B - b.belfry[1]); g.lineTo(b.belfry[0] + d - 1.6, B - b.belfry[1] - 7); g.arc(b.belfry[0] + d, B - b.belfry[1] - 7, 1.6, Math.PI, 0); g.lineTo(b.belfry[0] + d + 1.6, B - b.belfry[1]); g.fill(); }); }
      if (b.crown) {
        var cx = b.crown[0], cy = B - b.crown[1], r = b.crown[2];
        g.fillStyle = DECO.ink; g.beginPath(); g.arc(cx, cy, r, Math.PI, 0); g.fill();
        var cg = g.createRadialGradient(cx, cy, 2, cx, cy, r); cg.addColorStop(0, "rgba(255,170,110,.55)"); cg.addColorStop(1, "rgba(255,120,70,.1)");
        g.strokeStyle = cg; g.lineWidth = 0.9;
        for (var k2 = 1; k2 < 10; k2++) { var an = Math.PI + k2 * Math.PI / 10; g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(an) * r, cy + Math.sin(an) * r); g.stroke(); }
        g.beginPath(); g.arc(cx, cy, r, Math.PI, 0); g.stroke();
      }
      if (b.turrets) b.turrets.forEach(function (q) { g.fillStyle = DECO.ink; g.beginPath(); g.moveTo(q[0] - 3.5, B - q[1]); g.lineTo(q[0], B - q[1] - 11); g.lineTo(q[0] + 3.5, B - q[1]); g.fill(); });
      if (b.arches) { g.fillStyle = "rgba(255,170,110,.5)"; [-8, 0, 8].forEach(function (d) { g.beginPath(); g.arc(b.arches[0] + d, B - b.arches[1], 2.6, Math.PI, 0); g.lineTo(b.arches[0] + d + 2.6, B - b.arches[1] + 6); g.lineTo(b.arches[0] + d - 2.6, B - b.arches[1] + 6); g.fill(); }); }
      if (b.bpl) { g.fillStyle = "rgba(255,180,120,.45)"; for (var ax = 826; ax < 976; ax += 11) { g.beginPath(); g.arc(ax, B - 22, 3.2, Math.PI, 0); g.lineTo(ax + 3.2, B - 12); g.lineTo(ax - 3.2, B - 12); g.fill(); } }
    });
    // brownstones just past the fence: bay windows, mansard roofs, chimneys, warm rooms
    var br = seeded(19), base2 = CITY + 8;
    for (var bx = -12; bx < W + 10;) {
      var bw = 34 + br() * 18, bh = 44 + br() * 20, mans = br() < 0.6;
      g.fillStyle = "#0d0605"; g.fillRect(bx, base2 - bh, bw, bh);
      if (mans) { g.beginPath(); g.moveTo(bx - 1, base2 - bh); g.lineTo(bx + 4, base2 - bh - 10); g.lineTo(bx + bw - 4, base2 - bh - 10); g.lineTo(bx + bw + 1, base2 - bh); g.fill(); }
      for (var c2 = 0; c2 < 2; c2++) if (br() < 0.7) { var chx = bx + 4 + br() * (bw - 10); g.fillRect(chx, base2 - bh - (mans ? 10 : 0) - 8, 4, 9); }
      g.fillStyle = "#120807"; g.fillRect(bx + bw * 0.12, base2 - bh + 8, bw * 0.34, bh - 8);    // the bay
      for (var fl = 0; fl < 3; fl++) for (var wn = 0; wn < 3; wn++) {
        var wx2 = bx + 5 + wn * (bw - 10) / 3, wy2 = base2 - bh + 12 + fl * 13;
        if (wy2 > base2 - 8) continue;
        var on = br() < 0.38;
        g.fillStyle = on ? "rgba(255," + (170 + Math.floor(br() * 40)) + ",110," + (0.55 + br() * 0.4) + ")" : "rgba(70,25,15,.6)";
        g.fillRect(wx2, wy2, 5, 7);
        if (on && br() < 0.3) { g.fillStyle = "rgba(20,8,6,.6)"; g.fillRect(wx2, wy2, 5, 3); }        // a drawn shade
        if (on && br() < 0.12) lit.push({ x: wx2, y: wy2, w: 5, h: 7, p: br() * 6.28, s: 0.1 + br() * 0.3, warm: true });
      }
      g.strokeStyle = "rgba(255,95,45,.18)"; g.lineWidth = 0.8; g.strokeRect(bx, base2 - bh, bw, bh);
      bx += bw + 1;
    }
  }

  // the blacktop, the fence, the lamps' poles and the hoop's steel
  var LAMPS = [{ X: -6, z: ZC + 31 }, { X: 26, z: ZC + 31 }];
  function paintCourt(g) {
    // the ground from the fence to the camera
    var far = pj(0, ZC + 37, 0)[1], s = g.createLinearGradient(0, far, 0, H);
    s.addColorStop(0, "#1a0e0c"); s.addColorStop(0.4, "#120a09"); s.addColorStop(1, "#070404");
    g.fillStyle = s; g.fillRect(-20, far, W + 40, H - far + 20);
    // asphalt grit
    var gr = seeded(5);
    for (var k = 0; k < 9000; k++) {
      var y = far + Math.pow(gr(), 0.8) * (H - far), sz = 0.3 + (y - far) / (H - far) * 1.6;
      g.fillStyle = gr() < 0.5 ? "rgba(255,230,210," + (0.02 + gr() * 0.05) + ")" : "rgba(0,0,0," + (0.15 + gr() * 0.25) + ")";
      g.fillRect(gr() * W, y, sz, sz * 0.6);
    }
    // patches and cracks
    [[-20, ZC - 15, 9, 5], [12, ZC + 13, 7, 4], [28, ZC - 19, 6, 3]].forEach(function (p) {
      var a = pj(p[0], p[1], 0), b = pj(p[0] + p[2], p[1], 0), c = pj(p[0] + p[2], p[1] + p[3], 0), d = pj(p[0], p[1] + p[3], 0);
      g.fillStyle = "rgba(0,0,0,.28)"; g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.lineTo(c[0], c[1]); g.lineTo(d[0], d[1]); g.fill();
    });
    g.strokeStyle = "rgba(0,0,0,.55)"; g.lineCap = "round";
    for (var c3 = 0; c3 < 14; c3++) {
      var X = -30 + gr() * 70, z = ZC - 22 + gr() * 50, p0 = pj(X, z, 0);
      g.lineWidth = 0.6 + gr() * 0.9; g.beginPath(); g.moveTo(p0[0], p0[1]);
      for (var st = 0; st < 6; st++) { X += (gr() - 0.5) * 4; z += (gr() - 0.5) * 3; var p1 = pj(X, z, 0); g.lineTo(p1[0], p1[1]); }
      g.stroke();
    }
    // the paint: worn white lines (drawn on their own canvas, then scuffed)
    var pc = document.createElement("canvas"); pc.width = cv.width; pc.height = cv.height;
    var p = pc.getContext("2d"); p.setTransform(dpr * scale, 0, 0, dpr * scale, dpr * ox, dpr * oy);
    p.strokeStyle = "rgba(238,230,214,.62)"; p.lineJoin = "round";
    function line(pts) { p.beginPath(); pts.forEach(function (q, i2) { var a2 = pj(q[0], q[1], 0); if (i2) p.lineTo(a2[0], a2[1]); else p.moveTo(a2[0], a2[1]); }); }
    function lw(z2) { return 0.18 * F / z2; }
    function arc(cx2, cz, r, a0, a1) { var pts = []; for (var t2 = a0; t2 <= a1 + 1e-6; t2 += (a1 - a0) / 48) pts.push([cx2 + Math.cos(t2) * r, cz + Math.sin(t2) * r]); return pts; }
    p.lineWidth = lw(45);
    line([[-60, ZC - 25], [39, ZC - 25]]); p.lineWidth = lw(ZC - 23); p.stroke();
    line([[-60, ZC + 25], [39, ZC + 25]]); p.lineWidth = lw(ZC + 25); p.stroke();
    line([[39, ZC - 25], [39, ZC + 25]]); p.lineWidth = lw(ZC); p.stroke();
    line([[-8, ZC - 25], [-8, ZC + 25]]); p.lineWidth = lw(ZC); p.stroke();
    line(arc(-8, ZC, 6, -Math.PI / 2, Math.PI / 2)); p.lineWidth = lw(ZC); p.stroke();
    line([[39, ZC - 8], [20, ZC - 8], [20, ZC + 8], [39, ZC + 8]]); p.stroke();                                  // the lane
    p.fillStyle = "rgba(190,40,30,.20)";                                                         // a faded red key
    line([[39, ZC - 8], [20, ZC - 8], [20, ZC + 8], [39, ZC + 8]]); p.closePath(); p.fill();
    line(arc(20, ZC, 6, Math.PI / 2, Math.PI * 1.5)); p.stroke();
    line([[39, ZC - 22], [25.5, ZC - 22]].concat(arc(RIM.X, ZC, 23.75, Math.PI - 1.18, Math.PI + 1.18).reverse().map(function (q) { return q; })).concat([[25.5, ZC + 22], [39, ZC + 22]])); p.stroke();
    // a faded BA at center court
    var cc = pj(-8, ZC, 0), sc = F / ZC;
    p.save(); p.translate(cc[0], cc[1]); p.scale(1, 0.3); p.font = "700 " + (5.2 * sc) + "px Georgia, serif"; p.textAlign = "center"; p.textBaseline = "middle";
    p.fillStyle = "rgba(212,175,55,.22)"; p.fillText("BA", 0, 0); p.restore();
    // scuff the paint
    p.globalCompositeOperation = "destination-out"; p.setTransform(1, 0, 0, 1, 0, 0);
    var sr = seeded(9); for (var k3 = 0; k3 < 2600; k3++) { p.fillStyle = "rgba(0,0,0," + (0.3 + sr() * 0.7) + ")"; p.fillRect(sr() * pc.width, sr() * pc.height, 1 + sr() * 3 * dpr, 1 + sr() * 2 * dpr); }
    g.save(); g.setTransform(1, 0, 0, 1, 0, 0); g.drawImage(pc, 0, 0); g.restore();
    // the chain-link fence along the far side
    var fz = ZC + 35, f0 = pj(-70, fz, 0), f1 = pj(80, fz, 0), ft = pj(0, fz, 12)[1], fb = f0[1];
    g.save(); g.beginPath(); g.rect(-20, ft, W + 40, fb - ft); g.clip();
    g.strokeStyle = "rgba(200,190,180,.13)"; g.lineWidth = 0.6;
    for (var mx = -40; mx < W + 40; mx += 4.2) { g.beginPath(); g.moveTo(mx, ft); g.lineTo(mx + (fb - ft), fb); g.moveTo(mx + (fb - ft), ft); g.lineTo(mx, fb); g.stroke(); }
    g.restore();
    g.fillStyle = "#151010";
    for (var px = -60; px <= 80; px += 10) { var a3 = pj(px, fz, 0), b3 = pj(px, fz, 12.2); g.fillRect(a3[0] - 1, b3[1], 2, a3[1] - b3[1]); }
    g.fillRect(-20, ft - 1.5, W + 40, 2);
    // the lamps' poles
    LAMPS.forEach(function (l) {
      var a4 = pj(l.X, l.z, 0), b4 = pj(l.X, l.z, 24);
      g.strokeStyle = "#1c1414"; g.lineWidth = 3.2; g.beginPath(); g.moveTo(a4[0], a4[1]); g.lineTo(b4[0], b4[1]); g.stroke();
      var c4 = pj(l.X + 2.4, l.z - 3, 24.5); g.lineWidth = 2; g.beginPath(); g.moveTo(b4[0], b4[1]); g.lineTo(c4[0], c4[1]); g.stroke();
      g.fillStyle = "#2a1f1c"; g.fillRect(c4[0] - 6, c4[1] - 2, 12, 4);
    });
    // the hoop's steel: pole, padding, arm, backboard
    var pb = pj(43, ZC, 0), pt = pj(43, ZC, 12.5), arm = pj(BOARD_X, ZC, 11.5);
    g.strokeStyle = "#2b2c31"; g.lineWidth = 0.55 * F / ZC; g.lineCap = "butt"; g.beginPath(); g.moveTo(pb[0], pb[1]); g.lineTo(pt[0], pt[1]); g.stroke();
    var pad = pj(43, ZC, 6);
    g.strokeStyle = "#13234a"; g.lineWidth = 0.75 * F / ZC; g.beginPath(); g.moveTo(pb[0], pb[1]); g.lineTo(pad[0], pad[1]); g.stroke();
    g.strokeStyle = "#2b2c31"; g.lineWidth = 0.3 * F / ZC; g.beginPath(); g.moveTo(pt[0], pt[1]); g.lineTo(arm[0], arm[1]); g.moveTo(pj(43, ZC, 10.5)[0], pj(43, ZC, 10.5)[1]); g.lineTo(arm[0], arm[1] + 6); g.stroke();
    var q = [pj(BOARD_X, ZC - 3.5, 9.2), pj(BOARD_X, ZC + 3.5, 9.2), pj(BOARD_X, ZC + 3.5, 13.2), pj(BOARD_X, ZC - 3.5, 13.2)];
    g.fillStyle = "#3a3b40"; g.strokeStyle = "rgba(230,224,210,.85)"; g.lineWidth = 1.6;
    g.beginPath(); q.forEach(function (v, k4) { if (k4) g.lineTo(v[0], v[1]); else g.moveTo(v[0], v[1]); }); g.closePath(); g.fill(); g.stroke();
    var sq = [pj(BOARD_X - 0.05, ZC - 1.1, 10), pj(BOARD_X - 0.05, ZC + 1.1, 10), pj(BOARD_X - 0.05, ZC + 1.1, 11.5), pj(BOARD_X - 0.05, ZC - 1.1, 11.5)];
    g.beginPath(); sq.forEach(function (v, k4) { if (k4) g.lineTo(v[0], v[1]); else g.moveTo(v[0], v[1]); }); g.closePath(); g.stroke();
  }

  // ------------------------------------------------------------ sizing (and re-painting the layers)
  function fit() {
    var r = cv.getBoundingClientRect();
    if (!r.width) return;
    dpr = Math.min(2, window.devicePixelRatio || 1);
    cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
    scale = Math.max(r.width / W, r.height / H);
    // (on a narrow screen the frame follows the play and the hoop, not the middle of the picture)
    ox = Math.max(r.width - W * scale, Math.min(0, r.width / 2 - 640 * scale)); oy = (r.height - H * scale) / 2;
    rnd = seeded(11); lit = [];
    layers.sky = layer(paintSky); layers.city = layer(paintCity); layers.court = layer(paintCourt);
  }
  function blit(c) { x.save(); x.setTransform(1, 0, 0, 1, 0, 0); x.drawImage(c, 0, 0); x.restore(); }

  // ------------------------------------------------------------ what moves
  var clouds = []; var cr = seeded(23);
  for (var c5 = 0; c5 < 11; c5++) clouds.push({ x: cr() * W * 1.4 - W * 0.2, y: 50 + cr() * 140, w: 220 + cr() * 420, h: 5 + cr() * 10, v: 2 + cr() * 6, a: 0.5 + cr() * 0.4, front: c5 % 3 === 0 });
  function moonAndLights(t) {
    stars.forEach(function (s) { x.globalAlpha = 0.2 + 0.3 * (0.5 + 0.5 * Math.sin(t * 1.3 + s.p)); x.fillStyle = "#fff1e6"; x.beginPath(); x.arc(s.x, s.y, s.r, 0, 6.283); x.fill(); });
    x.globalAlpha = 1;
    var mx = 238, my = 112, halo = x.createRadialGradient(mx, my, 20, mx, my, 170);
    halo.addColorStop(0, "rgba(255,150,90,.30)"); halo.addColorStop(1, "rgba(255,150,90,0)");
    x.fillStyle = halo; x.fillRect(mx - 170, my - 170, 340, 340);
    var md = x.createRadialGradient(mx - 10, my - 10, 4, mx, my, 38);
    md.addColorStop(0, "#ffe9cc"); md.addColorStop(0.8, "#f4bd8e"); md.addColorStop(1, "#e19a6c");
    x.fillStyle = md; x.beginPath(); x.arc(mx, my, 36, 0, 6.283); x.fill();
    x.fillStyle = "rgba(160,80,50,.16)"; [[-12, -6, 9], [10, 8, 7], [5, -16, 5], [-4, 14, 4], [16, -4, 3]].forEach(function (q) { x.beginPath(); x.arc(mx + q[0], my + q[1], q[2], 0, 6.283); x.fill(); });
    // searchlights from behind the city
    [[300, 0.8], [690, 1.15]].forEach(function (s, k) {
      var ang = -Math.PI / 2 + Math.sin(t * 0.22 * s[1] + k * 2) * 0.5, len = 360, bx = s[0], by = CITY;
      var ex = bx + Math.cos(ang) * len, ey = by + Math.sin(ang) * len, sg = x.createLinearGradient(bx, by, ex, ey);
      sg.addColorStop(0, "rgba(255,200,150,.18)"); sg.addColorStop(1, "rgba(255,200,150,0)");
      var nx = Math.cos(ang + Math.PI / 2) * 40, ny = Math.sin(ang + Math.PI / 2) * 40;
      x.fillStyle = sg; x.beginPath(); x.moveTo(bx - 2, by); x.lineTo(ex + nx, ey + ny); x.lineTo(ex - nx, ey - ny); x.lineTo(bx + 2, by); x.closePath(); x.fill();
    });
    // a plane crossing, very high
    var px = ((t * 14) % (W + 300)) - 150, py = 46 + Math.sin(t * 0.05) * 6;
    x.fillStyle = "rgba(255,80,60," + (Math.sin(t * 6) > 0.6 ? 0.95 : 0.15) + ")"; x.fillRect(px, py, 2, 2);
    x.fillStyle = "rgba(255,255,255," + (Math.sin(t * 6 + 2) > 0.85 ? 0.9 : 0.1) + ")"; x.fillRect(px + 5, py + 1, 1.6, 1.6);
  }
  function cloudsAt(t, front) {
    clouds.forEach(function (c) {
      if (c.front !== front) return;
      var cx = ((c.x + t * c.v) % (W + c.w * 2)) - c.w, y = c.y + (front ? 30 : 0);
      x.save(); x.globalAlpha = c.a * (front ? 0.5 : 0.85);
      var g = x.createLinearGradient(cx, 0, cx + c.w, 0);
      g.addColorStop(0, "rgba(26,5,4,0)"); g.addColorStop(0.15, DECO.sky1); g.addColorStop(0.85, DECO.sky1); g.addColorStop(1, "rgba(26,5,4,0)");
      x.fillStyle = g; x.beginPath(); x.ellipse(cx + c.w / 2, y, c.w / 2, c.h, 0, 0, 6.283); x.fill();
      var l2 = x.createLinearGradient(cx, 0, cx + c.w, 0);
      l2.addColorStop(0, "rgba(190,68,28,0)"); l2.addColorStop(0.5, "rgba(210,80,34,.6)"); l2.addColorStop(1, "rgba(190,68,28,0)");
      x.strokeStyle = l2; x.lineWidth = 1.5; x.beginPath(); x.ellipse(cx + c.w / 2, y + 1.5, c.w / 2 - 6, c.h, 0, 0.15, Math.PI - 0.15); x.stroke();
      x.restore();
    });
  }
  function cityLife(t) {
    lit.forEach(function (w) { var v = Math.sin(t * w.s + w.p); if (v < -0.6) { x.fillStyle = "rgba(15,6,5,.85)"; x.fillRect(w.x, w.y, w.w, w.h); } });
    var bc = LANDMARKS[0].beacon, on = 0.5 + 0.5 * Math.sin(t * 1.7);                  // the Berkeley beacon
    var bg = x.createRadialGradient(bc[0], B - bc[1], 1, bc[0], B - bc[1], 20);
    bg.addColorStop(0, "rgba(255,60,45," + on + ")"); bg.addColorStop(1, "rgba(255,60,45,0)");
    x.fillStyle = bg; x.fillRect(bc[0] - 20, B - bc[1] - 20, 40, 40);
    var m = LANDMARKS[4].mast;                                                           // the Pru's mast light
    x.fillStyle = "rgba(255,50,40," + (Math.sin(t * 3) > 0.2 ? 0.95 : 0.2) + ")"; x.beginPath(); x.arc(m[0], B - m[2], 2.2, 0, 6.283); x.fill();
    var hk = x.createLinearGradient(716, 0, 796, 0), sw = (Math.sin(t * 0.2) + 1) / 2;   // a slow glint across the Hancock
    hk.addColorStop(Math.max(0, sw - 0.12), "rgba(255,180,140,0)"); hk.addColorStop(sw, "rgba(255,190,150,.12)"); hk.addColorStop(Math.min(1, sw + 0.12), "rgba(255,180,140,0)");
    x.save(); poly(x, LANDMARKS[8].pts, B); x.clip(); x.fillStyle = hk; x.fillRect(716, B - 260, 80, 260); x.restore();
    // ground fog drifting between the city and the fence
    for (var k = 0; k < 3; k++) {
      var fx = ((t * (6 + k * 3) + k * 400) % (W + 700)) - 350, fg = x.createRadialGradient(fx, CITY + 6, 10, fx, CITY + 6, 320);
      fg.addColorStop(0, "rgba(170,70,40,.20)"); fg.addColorStop(1, "rgba(170,70,40,0)");
      x.save(); x.translate(0, CITY + 6); x.scale(1, 0.16); x.translate(0, -(CITY + 6)); x.fillStyle = fg; x.fillRect(fx - 320, CITY - 314, 640, 640); x.restore();
    }
  }
  // the sodium lamps: their heads, cones and pools of light
  function lamps(t) {
    LAMPS.forEach(function (l, k) {
      var head = pj(l.X + 2.4, l.z - 3, 24.2), flick = k === 1 ? 0.85 + 0.15 * Math.max(Math.sin(t * 13) , Math.sin(t * 3.1)) : 1;
      var pool = pj(l.X + 3, ZC + 5, 0), sc = F / (ZC + 5);
      x.save(); x.globalCompositeOperation = "lighter";
      var cone = x.createLinearGradient(head[0], head[1], pool[0], pool[1]);
      cone.addColorStop(0, "rgba(255,170,90," + 0.16 * flick + ")"); cone.addColorStop(1, "rgba(255,170,90,0)");
      x.fillStyle = cone; x.beginPath(); x.moveTo(head[0] - 5, head[1]); x.lineTo(pool[0] - 15 * sc, pool[1]); x.lineTo(pool[0] + 15 * sc, pool[1]); x.lineTo(head[0] + 5, head[1]); x.closePath(); x.fill();
      x.translate(pool[0], pool[1]); x.scale(1, 0.32);
      var pg = x.createRadialGradient(0, 0, 4, 0, 0, 22 * sc);
      pg.addColorStop(0, "rgba(255,165,85," + 0.30 * flick + ")"); pg.addColorStop(1, "rgba(255,165,85,0)");
      x.fillStyle = pg; x.beginPath(); x.arc(0, 0, 22 * sc, 0, 6.283); x.fill();
      x.restore();
      var hg = x.createRadialGradient(head[0], head[1] + 2, 1, head[0], head[1] + 2, 26);
      hg.addColorStop(0, "rgba(255,215,150," + flick + ")"); hg.addColorStop(0.3, "rgba(255,160,80," + 0.4 * flick + ")"); hg.addColorStop(1, "rgba(255,160,80,0)");
      x.fillStyle = hg; x.fillRect(head[0] - 26, head[1] - 24, 52, 52);
    });
  }

  // ------------------------------------------------------------ the players (drawn in feet, at their spot on the court)
  var P = [{ name: "TATUM", num: "0", jersey: "#0e7a3e", dark: "#07401f", trim: "#BA9653", skin: "#7a5238", score: 0 },
           { name: "SGA", num: "2", jersey: "#1f6fd1", dark: "#0e3a72", trim: "#F05133", skin: "#5c3b28", score: 0 }];
  function shadowAt(X, z) {
    LAMPS.forEach(function (l) {                                                      // a long shadow away from each lamp
      var f = pj(X, z, 0), dx = X - l.X, dz = z - l.z, d = Math.hypot(dx, dz) || 1, len = 7, e = pj(X + dx / d * len, z + dz / d * len, 0);
      x.save(); x.fillStyle = "rgba(0,0,0,.30)"; x.beginPath();
      var w = 0.7 * F / z; x.moveTo(f[0] - w, f[1]); x.lineTo(e[0] - w * 1.6, e[1]); x.lineTo(e[0] + w * 1.6, e[1]); x.lineTo(f[0] + w, f[1]); x.closePath(); x.fill(); x.restore();
    });
    var c = pj(X, z, 0), s = F / z; x.fillStyle = "rgba(0,0,0,.5)"; x.beginPath(); x.ellipse(c[0], c[1], 1.1 * s, 0.3 * s, 0, 0, 6.283); x.fill();
  }
  function figure(p, X, z, ph, o) {
    var s = F / z, f = pj(X, z, 0);
    shadowAt(X, z);
    x.save(); x.translate(f[0], f[1]); x.scale(s, s);
    x.lineCap = "round"; x.lineJoin = "round";
    var crouch = o.crouch || 0, lift = o.lift || 0, legA = Math.sin(ph) * 0.45, bob = Math.abs(Math.sin(ph)) * 0.08;
    var hip = -3.15 + crouch - lift, sh = hip - 2.05, head = sh - 0.62;
    // legs: thigh and calf, with shoes
    [[legA, 1], [-legA, -1]].forEach(function (L2, k) {
      var kx = Math.sin(L2[0]) * 0.7 + 0.15 * L2[1], fx = Math.sin(L2[0]) * 1.0 + 0.12 * L2[1], fy = -lift - 0.12;
      x.strokeStyle = k ? p.skin : shade(p.skin); x.lineWidth = 0.42;
      x.beginPath(); x.moveTo(0.15 * L2[1], hip + 0.4); x.lineTo(kx, (hip + fy) / 2 + 0.1 - crouch * 0.4); x.lineTo(fx, fy - 0.2); x.stroke();
      x.fillStyle = k ? "#f2eee6" : "#cfc9be"; x.beginPath(); x.ellipse(fx + 0.18, fy, 0.42, 0.17, 0, 0, 6.283); x.fill();
      x.fillStyle = p.trim; x.fillRect(fx - 0.1, fy - 0.12, 0.5, 0.06);
    });
    // shorts
    x.fillStyle = p.dark; x.beginPath(); x.moveTo(-0.62, hip - 0.25); x.lineTo(0.62, hip - 0.25); x.lineTo(0.72, hip + 1.05); x.lineTo(0.05, hip + 0.95); x.lineTo(-0.72, hip + 1.05); x.closePath(); x.fill();
    x.fillStyle = p.trim; x.fillRect(0.5, hip - 0.2, 0.16, 1.15);
    // jersey, lit from the lamps behind (a warm rim on one edge)
    var jg = x.createLinearGradient(-0.7, 0, 0.7, 0); jg.addColorStop(0, p.jersey); jg.addColorStop(1, p.dark);
    x.fillStyle = jg; x.beginPath(); x.moveTo(-0.58, sh + bob); x.lineTo(0.58, sh + bob); x.lineTo(0.66, hip); x.lineTo(-0.66, hip); x.closePath(); x.fill();
    x.strokeStyle = p.trim; x.lineWidth = 0.08; x.stroke();
    x.fillStyle = "#fff"; x.font = "700 0.85px Arial, sans-serif"; x.textAlign = "center"; x.fillText(p.num, 0.02, sh + 1.2 + bob);
    x.strokeStyle = "rgba(255,170,100,.55)"; x.lineWidth = 0.06; x.beginPath(); x.moveTo(-0.58, sh + bob); x.lineTo(-0.66, hip); x.stroke();
    // arms
    var hand = o.hand || [0.9, hip + 0.1], off = o.off || [-0.9, hip + 0.2];
    x.strokeStyle = p.skin; x.lineWidth = 0.3;
    x.beginPath(); x.moveTo(0.48, sh + 0.25 + bob); x.lineTo((0.48 + hand[0]) / 2 + 0.25, (sh + hand[1]) / 2 + 0.2); x.lineTo(hand[0], hand[1]); x.stroke();
    x.strokeStyle = shade(p.skin);
    x.beginPath(); x.moveTo(-0.48, sh + 0.25 + bob); x.lineTo((off[0] - 0.48) / 2 - 0.25, (sh + off[1]) / 2 + 0.2); x.lineTo(off[0], off[1]); x.stroke();
    // head, hair, headband
    x.fillStyle = p.skin; x.beginPath(); x.arc(0.05, head + bob, 0.42, 0, 6.283); x.fill();
    x.fillStyle = "#0d0a09"; x.beginPath(); x.arc(0.05, head - 0.08 + bob, 0.43, Math.PI * 1.02, Math.PI * 1.98); x.fill();
    x.fillStyle = p.trim; x.fillRect(-0.37, head - 0.2 + bob, 0.84, 0.12);
    x.restore();
    // the name, on the floor under him (like the game's player marker)
    var tag = pj(X, z, 0);
    x.save(); x.translate(tag[0], tag[1] + 3); x.scale(1, 0.42);
    x.strokeStyle = p.dark === "#07401f" ? "rgba(62,207,142,.8)" : "rgba(111,155,232,.8)"; x.lineWidth = 2.2;
    x.beginPath(); x.arc(0, 0, 1.25 * F / z, 0, 6.283); x.stroke(); x.restore();
    x.font = "700 11px Arial, sans-serif"; x.textAlign = "center";
    x.fillStyle = "rgba(0,0,0,.6)"; x.fillRect(tag[0] - 27, tag[1] + 12, 54, 15);
    x.fillStyle = "#F5D370"; x.fillText(p.name, tag[0], tag[1] + 23.5);
  }
  function shade(hex) { var n = parseInt(hex.slice(1), 16); return "rgb(" + Math.floor((n >> 16) * 0.72) + "," + Math.floor(((n >> 8) & 255) * 0.72) + "," + Math.floor((n & 255) * 0.72) + ")"; }
  function ball(X, z, h) {
    var c = pj(X, z, h), r = 0.42 * F / z;
    var g = x.createRadialGradient(c[0] - r * 0.35, c[1] - r * 0.35, r * 0.1, c[0], c[1], r);
    g.addColorStop(0, "#f39b4c"); g.addColorStop(1, "#a9501a");
    x.fillStyle = g; x.beginPath(); x.arc(c[0], c[1], r, 0, 6.283); x.fill();
    x.strokeStyle = "rgba(20,8,4,.7)"; x.lineWidth = Math.max(0.7, r * 0.12);
    x.beginPath(); x.moveTo(c[0] - r, c[1]); x.lineTo(c[0] + r, c[1]); x.moveTo(c[0], c[1] - r); x.lineTo(c[0], c[1] + r); x.stroke();
    var sh = pj(X, z, 0); x.fillStyle = "rgba(0,0,0," + Math.max(0, 0.4 - h * 0.03) + ")"; x.beginPath(); x.ellipse(sh[0], sh[1], r * 1.1, r * 0.35, 0, 0, 6.283); x.fill();
  }
  // the rim (back half, then front half) and the chain net, which swings when the ball goes through
  function rimHalf(front) {
    x.strokeStyle = "#ff6a2e"; x.lineWidth = 0.13 * F / RIM.z;
    x.beginPath();
    for (var k = 0; k <= 24; k++) { var a = (front ? 0 : Math.PI) + k * Math.PI / 24, p = pj(RIM.X + Math.cos(a) * 0.75, RIM.z + Math.sin(a) * 0.75, RIM.h); if (k) x.lineTo(p[0], p[1]); else x.moveTo(p[0], p[1]); }
    x.stroke();
  }
  function net(swing) {
    x.strokeStyle = "rgba(205,205,210,.75)"; x.lineWidth = 0.9;
    for (var k = 0; k < 10; k++) {
      var a = k * Math.PI * 2 / 10, top = [RIM.X + Math.cos(a) * 0.75, RIM.z + Math.sin(a) * 0.75];
      var bot = [RIM.X + Math.cos(a) * 0.42 + swing * 0.5, RIM.z + Math.sin(a) * 0.42];
      x.beginPath();
      for (var j = 0; j <= 6; j++) { var u = j / 6, sx = top[0] + (bot[0] - top[0]) * u + Math.sin(u * 3 + swing * 4) * swing * 0.15, p = pj(sx, top[1] + (bot[1] - top[1]) * u, RIM.h - u * 1.6); if (j) x.lineTo(p[0], p[1]); else x.moveTo(p[0], p[1]); }
      x.stroke();
    }
  }

  // ------------------------------------------------------------ the play, on a loop: size-up, crossover, pull-up, swish
  var CYCLE = 7.2, ZO = ZC - 7, ZD = ZC - 4.5;
  function play(t) {
    var k = Math.floor(t / CYCLE), u = (t % CYCLE) / CYCLE, o = P[k % 2], d = P[(k + 1) % 2];
    P[0].score = Math.floor((k + 1) / 2) % 11; P[1].score = Math.floor(k / 2) % 11;
    var X0 = 3, XS = 17, Xo, Xd, shoot = u > 0.62, made = u > 0.86;
    if (u < 0.35) Xo = X0 + Math.sin(u * 30) * 0.7;
    else if (u < 0.55) Xo = X0 + (u - 0.35) / 0.2 * (XS - X0);
    else Xo = XS;
    Xd = u < 0.35 ? Xo + 4.2 : u < 0.55 ? Xo + 4.2 - (u - 0.35) / 0.2 * 1.6 : XS + 2.6 + Math.min(1, (u - 0.55) * 6) * 0.5;
    var ph = t * (u < 0.55 ? 9 : 2), jump = shoot ? Math.max(0, Math.sin(Math.min(1, (u - 0.62) / 0.18) * Math.PI)) * 1.6 : 0;
    var bX, bz = ZO - 0.6, bh;
    if (!shoot) { var cross = u > 0.38 && u < 0.46; bX = Xo + (cross ? -0.9 : 0.9); bh = 0.42 + Math.abs(Math.sin(t * 9)) * 2.6; }
    else {
      var s = Math.min(1, (u - 0.62) / 0.24);
      bX = XS + 0.4 + (RIM.X - XS - 0.4) * s; bz = (ZO - 0.4) + (RIM.z - ZO + 0.4) * s; bh = 8.6 + jump + (RIM.h + 0.4 - 8.6 - jump) * s + Math.sin(s * Math.PI) * 6;
      if (made) { var m = Math.min(1, (u - 0.86) / 0.14); bX = RIM.X; bz = RIM.z; bh = RIM.h + 0.2 - m * (RIM.h - 0.42); }
    }
    rimHalf(false);
    var ballBehind = shoot && bz > (ZO + ZD) / 2;
    if (ballBehind) ball(bX, bz, bh);
    figure(d, Xd, ZD, t * 4, { crouch: 0.35, hand: [-0.9, -3.6 - (shoot ? 3.2 : 1.2)], off: [0.8, -3.9 - (shoot ? 1.8 : 0.4)], lift: shoot ? jump * 0.7 : 0 });
    figure(o, Xo, ZO, ph, shoot ? { lift: jump, crouch: u < 0.66 ? 0.3 : 0, hand: [0.35, -7.4], off: [-0.1, -7.2] } : { hand: [u > 0.38 && u < 0.46 ? -0.9 : 0.9, -3.0 + Math.abs(Math.sin(t * 9)) * 0.5] });
    if (!ballBehind) ball(bX, bz, bh);
    net(made ? Math.max(0, 1 - (u - 0.86) / 0.12) * Math.sin(t * 30) : 0);
    rimHalf(true);
    if (made && u < 0.95) {
      var rc = pj(RIM.X, RIM.z, RIM.h - 0.8);
      x.strokeStyle = "rgba(245,211,112," + (1 - (u - 0.86) / 0.09) + ")"; x.lineWidth = 2;
      x.beginPath(); x.ellipse(rc[0], rc[1], 18 + (u - 0.86) * 260, 6 + (u - 0.86) * 80, 0, 0, 6.283); x.stroke();
    }
    // the score bug
    x.fillStyle = "rgba(0,0,0,.62)"; x.fillRect(W / 2 - 112, 14, 224, 30);
    x.strokeStyle = "rgba(212,175,55,.6)"; x.lineWidth = 1; x.strokeRect(W / 2 - 112, 14, 224, 30);
    x.font = "700 15px Arial, sans-serif"; x.textAlign = "center";
    x.fillStyle = "#3ecf8e"; x.fillText("TATUM " + P[0].score, W / 2 - 52, 35);
    x.fillStyle = "#6f9be8"; x.fillText(P[1].score + " SGA", W / 2 + 52, 35);
    x.fillStyle = "#8d877d"; x.fillText("–", W / 2, 35);
  }

  // ------------------------------------------------------------ the loop
  var t0 = performance.now(), running = false, visible = true;
  function frame(now) {
    if (!layers.sky) { fit(); if (!layers.sky) { running = false; return; } }
    var t = REDUCE ? 3 : (now - t0) / 1000;
    x.setTransform(1, 0, 0, 1, 0, 0); x.clearRect(0, 0, cv.width, cv.height);
    blit(layers.sky);
    x.setTransform(dpr * scale, 0, 0, dpr * scale, dpr * ox, dpr * oy);
    moonAndLights(t); cloudsAt(t, false);
    blit(layers.city);
    x.setTransform(dpr * scale, 0, 0, dpr * scale, dpr * ox, dpr * oy);
    cityLife(t); cloudsAt(t, true);
    blit(layers.court);
    x.setTransform(dpr * scale, 0, 0, dpr * scale, dpr * ox, dpr * oy);
    lamps(t); play(t);
    x.setTransform(dpr, 0, 0, dpr, 0, 0);                                         // a soft vignette
    var r = cv.getBoundingClientRect(), v = x.createRadialGradient(r.width / 2, r.height / 2, r.height * 0.3, r.width / 2, r.height / 2, r.width * 0.75);
    v.addColorStop(0, "rgba(0,0,0,0)"); v.addColorStop(1, "rgba(0,0,0,.55)"); x.fillStyle = v; x.fillRect(0, 0, r.width, r.height);
    if (running && !REDUCE) requestAnimationFrame(frame); else running = false;
  }
  function start() { if (!running && visible) { running = true; requestAnimationFrame(frame); } }
  fit(); frame(performance.now());
  var rz = 0;
  window.addEventListener("resize", function () { clearTimeout(rz); rz = setTimeout(function () { fit(); if (!running) frame(performance.now()); }, 120); });
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (es) { visible = es[0].isIntersecting; if (visible) start(); else running = false; }).observe(cv);
  } else start();
  document.addEventListener("visibilitychange", function () { if (document.hidden) running = false; else start(); });
})();
