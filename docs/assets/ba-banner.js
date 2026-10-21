/* Bradley Analytics animated banner (website home page).
   Drawn live on a <canvas>, so it stays sharp at every screen size and runs smoothly on phones (the old banner was a
   7 MB animated image, which phones decode in jumps). Transparent background; 1536 x 480 design units.

   Layers, bottom to top: two courts in chalk; Jayson Tatum's 2023-24 shot chart dropping in, in animated gold, on
   all four half courts (the two in the middle are mostly under the logo); on each half court a five-man possession run
   as a diagram (numbered O's with their X defenders, arrows drawn just ahead of every move: solid = cut, wavy =
   dribble, dashed = pass, bar = screen) that brings the ball up from half court, runs a real set, finishes with a
   shot, and jogs back to half court for the next one; the two words; the gold frame -- one continuous rectangle with
   sharp corners -- with its flowing gradient and a glint running around it; the logo, drawn in four layers so its
   basketball can be animated gradient gold with a slow white-and-gold glare sweeping across it, under the letters'
   glow, and its silver ring lit like polished metal: a silver-blue sheen from the upper left and an occasional glint.

   Usage: BABanner.mount(canvasElement, { logo: [{ size: 962, under: 'assets/ba-logo-962-under.webp', ball: ..., glow: ...,
                                                   letters: ... }, { size: 1440, ... }],
                                          font: 'assets/fonts/playfair-400.woff2' }) */
(function () {
  'use strict';
  var W = 1536, H = 480;
  var LOOP = 20;                    // two half-court sets per court, 10 s each
  var clamp = function (x, a, b) { a = a === undefined ? 0 : a; b = b === undefined ? 1 : b; return Math.min(b, Math.max(a, x)); };
  var seg = function (t, a, b) { return clamp((t - a) / (b - a)); };
  var lerp = function (a, b, t) { return a + (b - a) * t; };
  var eSine = function (x) { return 0.5 - 0.5 * Math.cos(Math.PI * clamp(x)); };
  var eOut = function (x) { x = clamp(x); return 1 - Math.pow(1 - x, 3); };
  var mod = function (a, n) { return ((a % n) + n) % n; };

  // ------------------------------------------------------------------ geometry (design units = px of a 1536-wide banner)
  var PXF = 7.22, CY = 240;                                       // px per foot; the courts' centre line
  var FR = { x0: 48, y0: 47, x1: 1489, y1: 433, th: 12 };         // gold frame, outer edges
  var IN = { x0: 60, y0: 59, x1: 1477, y1: 421 };                 // inside the frame
  var SC = 481 / 2048, LCX = 1026.4219, LCY = 1027.5435;         // logo artwork: ring centre in its 2048 px master
  var LOGO = { cx: 768, cy: 240, size: 481 };
  LOGO.ro = 1014.4 * SC; LOGO.ri = 972.8 * SC; LOGO.x = LOGO.cx - LCX * SC; LOGO.y = LOGO.cy - LCY * SC;
  var RIM = [5.25, 0];
  // court feet -> banner px. Left court: baseline at the left edge. Right court: mirrored left-right, and its plays
  // and shots are mirrored top-bottom too, so the two sides never look like copies.
  function mapL(p) { return [IN.x0 + p[0] * PXF, CY + p[1] * PXF]; }
  function mapR(p) { return [IN.x1 - p[0] * PXF, CY - p[1] * PXF]; }
  // the two half courts next to the logo (each court's far end), played the other way round, also flipped
  function mapLi(p) { return [IN.x0 + (94 - p[0]) * PXF, CY - p[1] * PXF]; }
  function mapRi(p) { return [IN.x1 - (94 - p[0]) * PXF, CY + p[1] * PXF]; }

  // ------------------------------------------------------------------ smooth paths
  // Centripetal Catmull-Rom through the waypoints: players run in rounded curves, never in corners.
  function spline(pts, per) {
    per = per || 18;
    if (pts.length < 2) return pts.slice();
    var P = [pts[0]].concat(pts, [pts[pts.length - 1]]);
    var out = [];
    for (var i = 1; i < P.length - 2; i++) {
      var p0 = P[i - 1], p1 = P[i], p2 = P[i + 1], p3 = P[i + 2];
      var d = function (a, b) { return Math.pow(Math.max(1e-4, Math.hypot(b[0] - a[0], b[1] - a[1])), 0.5); };
      var t0 = 0, t1 = t0 + d(p0, p1), t2 = t1 + d(p1, p2), t3 = t2 + d(p2, p3);
      for (var j = 0; j < per; j++) {
        var t = t1 + (t2 - t1) * j / per;
        var A1 = lerp2(p0, p1, (t - t0) / (t1 - t0)), A2 = lerp2(p1, p2, (t - t1) / (t2 - t1)), A3 = lerp2(p2, p3, (t - t2) / (t3 - t2));
        var B1 = lerp2(A1, A2, (t - t0) / (t2 - t0)), B2 = lerp2(A2, A3, (t - t1) / (t3 - t1));
        out.push(lerp2(B1, B2, (t - t1) / (t2 - t1)));
      }
    }
    out.push(pts[pts.length - 1]);
    return out;
  }
  function lerp2(a, b, t) { if (!isFinite(t)) t = 0; return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]; }
  function measure(pts) { var L = [0]; for (var i = 1; i < pts.length; i++) L.push(L[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])); return L; }
  function along(path, f) {                       // point + direction at fraction f of the length
    var L = path.L, tot = L[L.length - 1], dd = clamp(f) * tot, i = 1;
    while (i < L.length - 1 && L[i] < dd) i++;
    var k = (dd - L[i - 1]) / Math.max(1e-6, L[i] - L[i - 1]);
    var a = path.pts[i - 1], b = path.pts[i];
    return { p: [lerp(a[0], b[0], k), lerp(a[1], b[1], k)], dir: [b[0] - a[0], b[1] - a[1]], i: i };
  }
  function upto(path, f) { if (f >= 1) return path.pts; var a = along(path, f); return path.pts.slice(0, a.i).concat([a.p]); }
  function mkPath(pts) { var s = spline(pts); return { pts: s, L: measure(s) }; }
  function wavy(pts, amp, wl) {                   // dribble notation: a smooth wave along the path, calm at both ends
    var path = { pts: pts, L: measure(pts) }, tot = path.L[path.L.length - 1], out = [], n = Math.max(2, Math.ceil(tot / 0.12));
    for (var j = 0; j <= n; j++) {
      var f = j / n, dist = f * tot, a = along(path, f), dl = Math.hypot(a.dir[0], a.dir[1]) || 1;
      var s = Math.sin(dist / wl * Math.PI * 2) * amp * eSine(dist / 1.2) * eSine((tot - dist - 1.3) / 1.0);
      out.push([a.p[0] - a.dir[1] / dl * s, a.p[1] + a.dir[0] / dl * s]);
    }
    return out;
  }

  // ------------------------------------------------------------------ the possessions
  // Two half-court sets, 10 s each, chained so the second ends on the first one's starting spots: the loop never
  // jumps and nobody leaves the half court. The words BRADLEY / ANALYTICS sit across the middle of each court, so the
  // actions run along the sidelines and the baseline, where they can be seen. Arrows are drawn only for the play
  // itself; the short reset into the next set has none.
  // A - side pick-and-roll into a corner three: the 5 comes up to set a ball screen for the 1 on the wing, the 1 turns
  //   the corner, the 5 rolls, the 4 lifts and the 2 slides up from the far corner. The 3's man helps on the drive,
  //   and the 1 kicks it to the 3 in the corner for three. The 5 takes it out of the net and outlets to the 1.
  // B - Floppy: the 2 starts under the rim; the 5 and the 4 set a staggered double screen on one side, the 3 a single
  //   screen on the other. The 2 curls off the stagger to the wing, catches from the 1 and lets a three go; the 3
  //   pops to the opposite wing. Rebound, outlet, and everyone resets into the pick-and-roll.
  var SPOTS = { 1: [27.5, 15], 2: [3.6, -22.2], 3: [3.6, 22.2], 4: [25.5, -14], 5: [19, 8.5] };
  var POSS = 10;
  var A = [
    { who: 5, t: [0.6, 1.5], via: [[24, 11], [28.4, 12.2]], kind: 'screen' },
    { who: 1, t: [1.55, 3.0], via: [[26.5, 11], [22, 8.6], [16.5, 8.4]], kind: 'dribble' },
    { who: 5, t: [1.75, 3.2], via: [[23, 8], [16, 4.5], [10, 2.6]] },
    { who: 4, t: [1.8, 3.1], via: [[29, -9.5], [31, -5.5]] },
    { who: 2, t: [2.0, 3.2], via: [[7, -23], [10.5, -22.6]] },
    { pass: [1, 3], t: [3.1, 3.65] },
    { shot: 3, t: [3.85, 4.85] },
    { who: 5, t: [4.0, 4.9], via: [[7.6, 1.6], [6.6, 1.2]] },
    { grab: 5, t: 5.05 },
    { pass: [5, 1], t: [5.6, 6.3] },
    { who: 1, t: [5.2, 8.0], via: [[26, 2], [32, -7]], kind: 'reset' },
    { who: 5, t: [5.5, 7.8], via: [[11, -7.6]], kind: 'reset' },
    { who: 2, t: [5.3, 8.1], via: [[8, -12], [7.6, -1.2]], kind: 'reset' },
    { who: 4, t: [5.4, 8.2], via: [[22, -11], [16.2, -13.4]], kind: 'reset' },
    { who: 3, t: [5.3, 8.0], via: [[6.5, 15], [10.6, 7.6]], kind: 'reset' },
  ];
  var B = [
    { who: 5, t: [0.55, 1.0], via: [[12, -8.4]], kind: 'screen' },
    { who: 4, t: [0.65, 1.15], via: [[17, -14.1]], kind: 'screen' },
    { who: 3, t: [0.55, 1.0], via: [[11.4, 8.3]], kind: 'screen' },
    { who: 2, t: [1.2, 2.75], via: [[9, -4.6], [13, -9.9], [18.2, -15.9], [23.4, -19.5]] },
    { who: 3, t: [1.5, 2.9], via: [[16, 14], [22, 18.5]] },
    { pass: [1, 2], t: [2.8, 3.25] },
    { shot: 2, t: [3.5, 4.55] },
    { who: 5, t: [3.7, 4.6], via: [[8.2, -3.2], [6.7, -1.4]] },
    { grab: 5, t: 4.75 },
    { pass: [5, 1], t: [5.3, 6.0] },
    { who: 1, t: [5.0, 8.0], via: [[31, 4]], kind: 'reset', back: true },
    { who: 2, t: [5.1, 8.1], via: [[12, -22]], kind: 'reset', back: true },
    { who: 3, t: [5.2, 8.0], via: [[12, 21.5]], kind: 'reset', back: true },
    { who: 4, t: [5.2, 7.8], via: [[21, -14.5]], kind: 'reset', back: true },
    { who: 5, t: [5.4, 8.2], via: [[12, 5]], kind: 'reset', back: true },
  ];
  // defenders who leave their man for a moment: they slide toward the spot, then close out
  var HELP = [
    { who: 3, t0: 2.15, t1: 3.3, spot: [13, 11] },          // A: the 3's man helps on the drive, leaving the corner open
    { who: 1, t0: 1.15, t1: 2.4, spot: [26.5, 13.5] },      // A: the 1's man is caught on the screen
    { who: 2, t0: 11.3, t1: 12.8, spot: [12.4, -7.2] },     // B: the 2's man is caught on the stagger
  ];

  // One 20 s timeline, A then B: every move starts where the player is, and B's reset ends on his starting spot.
  function buildTimeline() {
    var pos = {}, acts = [], passes = [], shots = [], grabs = [];
    for (var k = 1; k <= 5; k++) pos[k] = SPOTS[k].slice();
    [[A, 0], [B, POSS]].forEach(function (pair) {
      var list = pair[0], off = pair[1];
      list.slice().sort(function (a, b) { return (a.t[0] || a.t) - (b.t[0] || b.t); }).forEach(function (a) {
        if (a.pass) { passes.push({ from: a.pass[0], to: a.pass[1], t0: a.t[0] + off, t1: a.t[1] + off }); return; }
        if (a.shot) { shots.push({ who: a.shot, t0: a.t[0] + off, t1: a.t[1] + off }); return; }
        if (a.grab) { grabs.push({ who: a.grab, t: a.t + off }); return; }
        var pts = [pos[a.who]].concat(a.via, a.back ? [SPOTS[a.who]] : []);
        var path = mkPath(pts);
        acts.push({ who: a.who, t0: a.t[0] + off, t1: a.t[1] + off, path: path, kind: a.kind || 'cut',
                    wave: a.kind === 'dribble' ? mkWave(path) : null });
        pos[a.who] = pts[pts.length - 1].slice();
      });
    });
    var byWho = {}; for (var w = 1; w <= 5; w++) byWho[w] = acts.filter(function (a) { return a.who === w; });
    return { acts: acts, byWho: byWho, passes: passes, shots: shots, grabs: grabs };
  }
  function mkWave(path) { var w = wavy(path.pts, 0.42, 2.6); return { pts: w, L: measure(w) }; }
  var TL = buildTimeline();

  function playerAt(w, t) {                         // where O number w is at time t (0..LOOP)
    var list = TL.byWho[w], p = SPOTS[w];
    for (var i = 0; i < list.length; i++) {
      var a = list[i];
      if (t < a.t0) break;
      p = t >= a.t1 ? a.path.pts[a.path.pts.length - 1] : along(a.path, eSine(seg(t, a.t0, a.t1))).p;
    }
    return p;
  }
  function ballAt(t) {                              // {p, air, inHand, shot}
    var ev = [];
    TL.passes.forEach(function (p) { ev.push({ t: p.t0, k: 'pass', e: p }); });
    TL.shots.forEach(function (s) { ev.push({ t: s.t0, k: 'shot', e: s }); });
    TL.grabs.forEach(function (g) { ev.push({ t: g.t, k: 'grab', e: g }); });
    ev.sort(function (a, b) { return a.t - b.t; });
    var holder = 1, state = null;
    for (var i = 0; i < ev.length; i++) {
      var e = ev[i];
      if (t < e.t) break;
      if (e.k === 'pass') { if (t < e.e.t1) state = { pass: e.e }; else { holder = e.e.to; state = null; } }
      else if (e.k === 'shot') { if (t < e.e.t1) state = { shot: e.e }; else { state = { loose: e.e }; holder = null; } }
      else if (e.k === 'grab') { holder = e.e.who; state = null; }
    }
    if (state && state.pass) {
      var p0 = handPos(state.pass.from, state.pass.t0), p1 = handPos(state.pass.to, state.pass.t1);
      var u = eSine(seg(t, state.pass.t0, state.pass.t1));
      return { p: lerp2(p0, p1, u), pass: state.pass };
    }
    if (state && state.shot) return { shot: state.shot };
    if (state && state.loose) {                      // through the net and a couple of small bounces under the rim
      var age = t - state.loose.t1, b = Math.abs(Math.sin(age * 9)) * Math.exp(-age * 4) * 0.8;
      return { p: [RIM[0] + 0.6 + age * 0.9, RIM[1] + 0.2], lift: b };
    }
    return { p: handPos(holder, t) };
  }
  function handPos(w, t) { var p = playerAt(w, t); return [p[0] - 1.25, p[1] - 1.25]; }
  function defenderAt(w, t) {                       // X: between his man and the rim, a beat behind him
    var o = playerAt(w, mod(t - 0.28, LOOP)), dx = RIM[0] - o[0], dy = RIM[1] - o[1], d = Math.hypot(dx, dy) || 1;
    var g = Math.min(3.4, d * 0.32), x = [o[0] + dx / d * g, o[1] + dy / d * g];
    HELP.forEach(function (h) {
      if (h.who !== w) return;
      var k = eSine(seg(t, h.t0, h.t0 + 0.45)) * (1 - eSine(seg(t, h.t1, h.t1 + 0.6)));
      if (k > 0) x = lerp2(x, h.spot, k);
    });
    return x;
  }

  // ------------------------------------------------------------------ Jayson Tatum, 2023-24: every shot, in game order
  var SHOTS = [135,248,0,132,235,0,-23,6,0,143,218,1,-109,190,1,-131,236,1,-173,197,1,61,27,0,-176,198,0,190,70,0,-99,267,0,50,268,1,-152,141,1,156,217,0,-18,22,0,76,235,0,-110,253,0,-97,231,0,238,51,0,-219,130,0,5,-2,1,0,0,1,195,178,0,-228,-8,0,140,74,0,4,13,1,-38,42,1,-83,253,0,170,14,1,203,163,1,-2,15,0,129,32,1,-179,102,0,-33,11,1,88,227,0,-114,277,0,-163,42,0,49,260,0,-206,174,0,1,25,0,9,13,1,-100,86,1,118,223,0,59,136,0,140,221,0,-27,149,0,-69,22,0,10,1,1,11,20,1,-135,15,0,16,6,0,-87,176,1,71,258,0,40,52,1,16,29,1,-137,253,0,-11,6,1,12,284,0,-2,38,1,174,40,1,-3,259,0,27,26,1,20,16,1,227,101,1,-176,205,1,70,252,0,103,148,0,-29,47,0,7,10,1,-153,211,0,-115,237,0,-21,20,1,-141,204,1,-53,152,1,170,208,0,-225,-21,1,-104,5,0,107,174,0,-170,178,1,61,251,0,-4,14,1,124,41,0,-17,6,1,-2,251,0,4,8,1,-7,5,1,40,191,1,2,13,1,0,-3,1,-230,31,0,16,257,0,28,10,0,9,5,1,-28,6,0,-5,13,0,12,257,1,-151,217,0,-74,29,0,-138,222,1,-5,2,1,-161,214,0,-7,27,1,-6,16,1,-123,251,0,-22,12,1,188,183,0,-2,293,0,85,17,0,2,27,1,125,246,1,-47,30,0,-125,221,0,37,73,0,-1,35,1,-228,83,0,0,41,1,-183,178,0,-2,11,1,145,45,1,31,-4,0,23,-1,1,-136,224,0,15,255,1,-78,243,1,227,43,0,136,42,0,-123,225,0,-16,1,1,-67,248,0,51,47,1,1,0,1,-39,11,1,-228,29,1,229,62,1,4,20,1,-138,13,1,-169,179,1,132,67,1,-15,164,1,-150,222,0,103,29,0,85,152,1,-16,49,0,0,0,0,16,5,1,-72,149,0,71,262,1,-167,205,0,227,88,1,10,30,1,20,30,1,77,236,1,11,-5,1,174,178,1,-176,162,0,-12,11,0,45,22,0,7,15,0,71,232,0,-4,245,1,6,46,1,22,9,1,53,37,0,127,219,0,70,263,1,-129,101,0,45,267,0,-4,106,0,-44,260,1,-9,269,1,9,5,1,10,2,1,63,237,0,-132,83,1,-27,23,1,37,254,0,-31,48,0,-9,8,1,-14,6,1,2,10,1,12,11,0,-31,14,0,-225,43,1,43,251,0,18,6,1,-100,31,1,-121,219,1,-9,248,0,-16,58,1,-180,168,0,-92,45,0,-138,205,0,-11,6,1,2,6,1,151,-11,0,1,5,1,6,15,1,217,149,0,11,65,0,-227,-3,0,-11,256,1,141,214,0,161,26,0,-218,127,0,-107,62,0,-195,156,1,1,11,1,-218,162,0,54,50,1,-93,256,0,-27,36,1,118,89,1,-176,209,1,39,34,0,1,17,1,156,230,0,4,34,1,-28,27,1,189,158,0,190,183,0,-142,275,1,-249,160,1,28,6,0,170,173,0,2,26,1,5,2,1,-98,99,1,1,4,1,115,243,0,127,223,0,-42,302,0,83,54,1,-143,228,0,-1,2,1,147,29,1,27,46,0,206,171,0,158,98,0,-169,195,0,-239,55,1,-62,268,0,-152,27,1,-165,220,1,113,138,0,11,27,1,-159,220,1,233,64,1,-158,214,1,17,6,1,153,228,0,141,232,1,-186,195,0,173,220,0,-179,-15,1,-148,34,1,-6,6,0,121,227,0,-172,210,0,-22,67,0,96,239,1,-145,103,1,42,241,1,32,257,0,-5,19,0,2,8,0,105,151,0,-2,14,1,112,101,0,114,243,1,-16,51,0,0,0,1,15,13,0,9,20,0,0,0,0,0,0,0,10,6,1,-47,32,1,7,10,1,-2,0,0,-104,41,1,-6,8,1,-29,247,1,-5,1,1,151,156,0,-1,166,1,-138,230,0,0,17,1,-126,218,1,-103,230,1,-223,14,0,224,80,0,-10,14,1,-1,4,1,33,272,1,20,257,1,-120,94,1,-164,199,0,-2,243,0,134,209,1,-5,23,1,114,17,0,163,215,0,145,223,0,13,26,1,-61,290,1,175,218,0,131,34,0,6,23,1,7,33,0,-12,14,0,6,22,0,-135,232,1,48,106,1,-234,109,0,-11,24,1,124,221,0,-2,27,1,-137,145,0,15,24,1,-39,277,1,-107,245,0,44,253,1,-150,223,0,-152,222,0,-27,49,0,-49,32,0,-15,283,0,123,243,0,-2,8,1,38,247,1,-21,17,0,-5,17,1,-21,263,0,-39,252,1,99,232,1,-116,281,0,17,8,1,-50,49,0,32,7,0,-17,290,0,85,252,1,58,130,0,118,221,0,-143,231,0,-26,31,0,69,135,1,-40,163,1,-180,206,1,76,255,0,-96,117,1,-97,152,0,138,231,0,-207,169,0,18,10,1,-123,249,0,12,17,1,-15,13,1,17,28,1,154,226,0,186,193,1,-162,223,1,22,29,1,116,247,0,235,84,0,156,29,0,132,214,0,-9,11,1,44,7,1,1,6,1,103,236,0,92,246,0,21,2,1,-69,285,0,26,10,0,9,21,0,-228,71,1,125,90,1,-23,264,0,70,252,1,39,42,0,-175,218,0,-33,19,0,-140,256,1,27,29,0,197,160,1,141,17,0,118,237,0,-23,28,0,15,5,1,-107,239,0,147,207,0,181,175,0,-124,80,1,0,37,1,108,124,1,107,241,1,81,277,0,170,248,0,-14,172,0,7,29,0,0,0,0,102,241,0,2,37,1,5,36,1,-87,258,0,-11,12,1,-199,184,0,48,262,0,23,18,1,99,267,1,-22,32,0,-15,26,1,91,241,0,21,13,1,85,128,1,121,265,0,10,13,1,15,11,1,143,127,0,148,226,0,-96,256,0,-18,25,1,-120,162,0,-216,166,1,71,72,1,104,134,0,20,11,0,42,58,0,0,0,0,0,0,1,-4,4,1,-152,233,1,-18,15,1,-142,235,0,27,17,1,123,65,0,16,27,0,-146,62,0,130,68,0,-89,257,1,150,59,0,94,274,0,-134,229,1,-113,252,1,-72,-15,0,0,0,0,137,100,0,34,34,1,-121,252,0,9,39,1,-141,231,0,-151,238,1,-69,193,0,-150,251,0,67,283,0,-47,64,1,157,214,0,61,262,1,1,253,0,51,98,0,32,26,0,-69,243,0,167,154,0,16,32,0,-70,255,0,146,255,0,18,263,1,39,25,1,34,267,0,2,13,1,-116,263,1,-217,136,1,-194,177,1,-200,148,1,44,55,0,189,172,0,45,85,1,-157,52,1,137,42,0,-212,139,0,21,15,1,-121,240,1,176,195,0,116,234,0,-77,74,0,-119,194,0,-10,34,0,10,17,1,5,44,0,74,258,0,-55,273,0,-16,126,1,1,27,1,13,34,1,92,237,0,7,13,1,156,242,1,141,227,0,36,279,0,36,36,0,-228,61,0,18,2,0,-218,164,0,-114,251,1,-22,21,1,-207,190,0,12,36,1,-124,83,0,-152,220,0,11,15,1,124,32,0,-5,7,1,1,13,1,157,200,0,-29,34,1,-183,207,0,-25,32,0,42,7,0,-50,109,0,-88,260,0,-23,21,0,20,20,1,-21,16,1,66,50,0,-28,25,0,0,0,0,-163,196,1,50,39,0,-4,12,0,154,78,1,-176,67,1,2,4,1,-21,254,1,-183,178,1,55,247,0,-123,215,1,-89,239,0,-48,246,0,233,13,0,-59,240,1,-15,0,1,-20,247,0,-140,66,1,1,27,0,-136,-10,1,48,11,0,125,36,0,-230,116,1,94,132,1,132,153,1,-227,64,0,11,15,0,-42,1,0,-43,246,1,4,11,1,-66,36,0,12,8,1,-154,223,0,-4,109,0,10,7,1,-2,18,1,-20,10,0,-13,15,1,-13,270,0,104,258,0,66,143,0,234,52,1,-29,42,0,-9,15,1,11,62,0,147,225,1,143,239,1,138,246,0,-76,257,1,229,25,0,-185,225,1,132,235,0,-60,48,0,153,251,1,-72,257,1,-190,227,0,9,269,0,81,164,1,26,170,1,23,8,1,54,52,1,197,183,1,98,259,0,-75,248,1,-130,216,0,194,188,1,-185,188,1,49,71,0,-2,9,1,140,219,1,-112,121,0,2,-5,1,-6,15,0,158,279,1,224,20,1,-81,137,0,96,247,0,-77,251,0,-102,157,0,-21,258,1,141,89,0,-163,63,0,-165,210,1,23,26,1,-20,10,1,126,224,0,132,232,0,170,189,1,-185,192,0,-12,24,1,-75,37,0,16,27,1,16,27,1,146,225,1,94,158,0,-116,167,0,1,6,1,36,29,0,-44,31,1,147,206,1,72,115,1,-27,86,0,-110,65,0,113,235,0,-6,23,1,-11,120,0,-123,176,0,-1,24,1,-59,124,1,-116,253,0,120,241,1,-145,220,1,60,272,1,-113,178,1,12,19,1,-125,240,1,-31,285,0,-234,83,0,13,188,0,110,55,1,39,18,0,17,11,0,21,25,0,159,10,0,6,6,1,-81,173,1,-20,253,1,-140,58,0,-123,17,1,189,-6,0,-147,211,0,-18,42,0,-116,151,0,0,6,1,-55,128,0,-1,0,1,85,253,0,-6,1,1,-167,254,0,67,196,0,-212,139,0,-31,259,0,-7,55,1,-24,6,1,143,38,1,156,45,0,123,240,0,-83,107,0,1,26,1,-165,225,1,114,256,0,-143,7,1,-211,177,1,-42,61,1,65,132,0,18,13,0,-135,243,0,-34,36,0,146,216,1,-179,211,0,157,63,0,234,33,0,-50,63,0,-238,70,0,-140,123,1,-1,1,1,-98,265,0,67,279,1,-61,53,1,181,42,0,-115,253,0,1,2,1,1,6,0,173,180,0,167,216,0,-113,260,0,7,26,1,-56,23,0,-136,29,1,-143,216,0,74,95,0,21,153,1,22,32,0,-4,148,0,0,16,1,-45,25,0,-125,119,0,12,3,1,12,64,0,76,194,0,-27,10,0,69,50,0,-7,27,1,12,258,0,-56,195,1,-66,74,0,132,47,0,25,10,0,65,246,0,-229,15,0,28,20,0,-99,237,1,-165,200,0,-89,239,0,141,79,0,-9,16,1,-80,125,1,61,73,1,180,197,0,-4,91,1,-119,229,0,-12,253,1,-89,156,1,15,26,0,-151,215,0,100,231,0,18,15,0,66,239,1,-54,151,1,-23,7,1,17,17,1,-116,230,0,5,-6,1,-192,174,0,4,31,0,-15,15,1,-22,2,1,103,235,0,-88,127,0,-186,210,0,-151,0,1,180,13,0,206,154,0,54,11,0,-169,188,1,-195,150,1,69,252,1,10,6,0,0,0,1,21,256,0,-189,204,0,21,48,1,-23,27,1,-26,31,1,-183,203,1,-121,48,0,18,48,0,-10,25,1,9,12,1,21,15,1,-127,238,1,-158,222,0,129,43,0,7,49,0,0,0,0,0,0,0,2,27,0,-13,127,0,-19,49,1,-137,222,0,115,71,1,-150,43,1,15,271,0,26,25,1,151,206,0,-2,271,1,15,7,1,134,234,0,-135,223,0,47,25,0,-120,241,1,26,23,1,-43,26,0,0,6,1,-53,269,0,-6,13,1,-5,4,1,120,228,0,28,13,1,-59,264,1,1,11,1,-108,236,1,-142,175,1,-34,64,1,-1,6,1,-92,257,1,-48,288,0,-140,162,1,113,239,0,15,30,1,-150,127,0,118,240,1,121,256,0,-31,187,0,-157,219,0,200,163,0,7,60,0,-217,121,1,-116,267,0,72,32,0,11,278,1,87,249,1,-55,31,0,-232,57,0,62,47,1,-74,89,0,118,250,1,131,209,0,-12,15,1,-202,173,1,118,240,0,0,0,0,0,0,0,48,26,1,55,44,0,36,29,0,25,24,1,0,2,1,-184,204,0,0,25,1,50,42,0,-21,267,0,-33,31,0,234,48,1,114,240,0,103,152,1,10,24,1,98,246,1,72,239,1,-213,147,1,-99,267,1,-207,172,0,96,223,1,92,50,0,-164,205,0,-1,5,1,154,205,0,112,199,0,-20,260,0,-235,2,0,-135,49,1,142,215,0,-158,216,1,148,199,0,-6,5,1,-194,158,0,120,16,0,145,215,0,154,210,0,-212,172,0,-9,29,1,34,27,1,-175,215,1,141,220,0,6,31,1,-17,32,1,-200,188,0,32,34,0,168,230,0,23,0,1,-51,267,0,34,2,0,-98,252,0,-195,174,0,-82,259,0,-150,211,1,-74,268,0,164,47,1,-77,163,1,104,236,1,-7,5,1,165,195,0,18,18,0,18,24,1,-38,15,0,-1,6,1,-152,219,0,-1,15,1,-1,21,1,-178,198,1,6,132,1,40,54,1,-20,62,0,36,25,1,141,207,0,17,41,0,38,46,1,-176,206,1,45,244,0,-129,231,1,99,21,1,-93,84,1,-108,80,1,-30,40,1,148,216,0,72,25,1,135,138,0,241,27,0,-15,29,0,36,63,1,32,19,0,18,-1,1,17,14,0,-5,-4,1,12,-6,1,-124,47,0,-36,247,1,12,243,1,-152,185,1,2,194,0,25,255,1,-107,158,1,7,271,0,-11,37,0,4,14,1,141,203,0,10,-2,1,125,235,0,-132,218,0,-94,258,0,-184,233,1,6,4,1,147,11,0,65,249,0,-28,26,0,-185,2,1,-10,26,1,148,69,0,190,172,0,-28,10,1,-100,242,0,-28,178,1,-181,194,0,-235,20,1,-28,24,1,-224,151,1,-70,155,0,229,52,0,-17,8,1,212,147,0,78,18,0,-143,162,0,1,143,1,-142,218,0,-163,200,1,-1,16,0,-2,53,0,-123,52,0,131,92,1,135,212,0,-94,229,1,146,201,0,7,9,1,-168,189,1,161,199,0,6,9,0,165,19,1,-44,247,1,-105,226,1,40,261,0,7,0,1,164,215,0,-140,29,1,23,8,1,-76,239,0,17,10,0,-2,257,1,-5,4,1,-29,249,0,-212,139,1,-147,42,0,53,256,0,-218,127,0,-16,8,1,137,214,0,-13,13,1,-126,232,1,158,199,0,116,218,0,18,13,1,-234,11,0,109,99,0,-28,25,1,40,253,0,2,82,0,-29,26,0,5,7,1,-85,192,1,136,232,0,-49,278,0,1,47,1,21,40,0,4,31,1,21,23,0,-2,11,1,20,15,0,92,169,0,-126,226,0,13,135,1,23,90,1,-56,115,1,43,7,1,38,13,0,-145,233,0,-159,222,1,194,184,1,-147,227,0,154,227,1,-21,25,0,43,27,0,65,62,1,-161,200,1,143,201,0,-189,203,1,-60,145,0,7,35,1,-93,35,0,-131,17,0,1,32,1,2,24,1,-1,22,1,-81,256,1,-141,232,1,-69,256,1,-164,7,1,-142,235,1,-60,260,0,-9,250,1,-9,17,0,78,295,1,-1,3,1,-131,221,1,-6,-1,1,161,219,1,-173,183,1,-98,230,0,-156,197,0,-150,11,0,1,-3,0,142,214,0,7,16,0,-75,38,0,1,11,1,-138,79,0,5,1,0,-203,170,0,-32,95,0,116,115,0,-77,237,1,27,167,1,-65,251,1,48,22,0,-15,10,0,-109,232,0,-4,16,1,0,17,0,-16,11,1,-157,204,0,32,16,0,-21,13,0,224,33,0,2,5,1,0,4,0,-47,248,0,-10,20,0,88,22,0,100,138,1,-168,195,1,11,162,0,115,73,0,20,68,0,-119,239,1,151,194,0,-18,13,1,91,17,0,-235,62,0,-2,31,0,40,263,1,51,157,0,110,231,1,189,172,0,32,278,1,59,113,0,67,104,0,0,0,0,1,16,1,-64,117,0,4,12,1,-20,10,1,232,42,0,169,25,0,110,241,0,-116,225,1,28,30,0,-28,20,1,4,15,1,67,42,0,-105,229,0,6,4,1,-17,32,0,5,29,1,-15,90,1,-167,204,0,-146,207,0,18,25,1,97,239,1,112,230,0,38,163,0,7,54,0,-25,23,0,-1,58,1,32,31,0,31,32,1,67,26,1,172,-8,0,31,262,1,-161,184,0,-162,197,1,-208,180,0,-32,-2,1,-138,64,0,-50,251,1,-43,34,0,0,0,1,146,52,0,-121,236,0,-229,126,0,-1,33,1,10,256,0,7,27,1,-156,43,0,-47,64,1,-66,247,1,-34,65,0,50,28,1,39,80,1,92,239,0,2,8,1,-56,257,0,-98,267,1,148,154,1,-136,236,1,9,10,1,0,8,1,131,269,0,-16,11,1,-205,155,1,-230,106,1,-52,49,0,18,24,1,-140,236,0,64,192,0,-75,251,0,59,52,0,51,74,0,224,47,1,157,226,1,169,209,0,-21,24,1,113,248,1,135,231,0,-237,155,0,-29,13,1,-51,269,1,-6,183,0,-146,267,1,-213,162,0,121,267,0,-9,269,0,0,81,0,-51,273,1,-206,49,0,130,43,0,-70,246,1,-9,7,1,-49,254,1,10,131,0,-7,275,0,-76,122,1,-119,241,1,134,228,1,-85,126,0,-161,137,0,-71,42,1,-67,64,1,136,210,0,105,143,0,-80,201,0,-23,257,0,-50,25,1,-75,109,0,-25,180,0,-163,53,1,151,27,0,148,141,0,5,8,1,129,-6,0,-143,216,1,-4,5,1,42,264,0,11,0,1,-206,-13,1,-31,275,1,88,168,0,-29,20,0,-186,159,0,-93,51,0,-235,-15,0,-214,116,0,17,8,1,112,266,0,-51,80,1,112,237,1,-4,22,1,-7,4,0,13,11,0,17,251,1,-1,1,1,135,218,0,-120,87,1,1,1,1,-44,85,0,-114,226,0,0,21,0,-124,226,0,-1,15,1,93,164,0,-221,122,0,62,189,1,-120,17,0,2,65,0,0,0,1,25,260,0,0,18,1,-49,155,1,-1,4,0,0,0,1,4,9,1,109,257,0,-4,4,0,-107,20,0,0,11,1,-102,236,1,4,50,1,0,8,0,228,81,0,-119,18,0,-28,258,0,-34,260,0,-2,6,1,-104,111,0,2,1,1,-13,256,1,2,11,0,0,0,0,0,0,1,-27,83,0,-189,165,0,-4,13,1,26,1,1,-16,-6,1,157,35,1,98,15,0,22,69,0,138,177,0,154,104,1,-190,173,1,-2,4,1,-5,253,1,-170,200,0,-152,10,1,45,277,0,-45,257,1,75,168,0,12,6,1,103,239,0,-131,220,1,107,234,0,-172,183,1,-15,250,0,-7,5,1,-96,240,0,2,147,0,-205,126,1,116,124,0,118,-4,0,-5,4,1,0,8,1,1,10,1,-129,244,1,-83,262,0,-18,21,0,145,216,0,-221,153,0,-23,128,1,-54,31,0,0,0,1,-129,111,0,190,169,0,0,10,1,164,201,0,223,2,1,-77,54,0,-24,-1,1,-154,228,0,-40,14,0,0,0,1,-33,189,1,-15,184,0,-228,19,1,129,77,0,142,219,0,-119,88,1,-17,274,0,1,8,1,-195,176,0,-197,180,0,1,20,1,23,37,0,25,6,0,-1,-1,1,112,244,0,-27,280,1,-17,17,0,-15,172,0,-59,262,0,-76,142,0,-219,153,1,6,8,0,6,5,1,-212,7,0,-4,63,0,-1,20,1,134,232,0,-159,121,1,-159,208,0,-103,240,1,35,274,1,-6,26,1,162,224,0,4,6,1,194,227,1,113,240,0,113,163,0,-1,1,1,-110,193,0,-36,279,1,-109,238,0,-4,2,1,94,244,0,-213,159,0,125,225,0,202,151,0,2,22,1,77,47,1,222,122,0,-27,19,0,5,17,1,-1,57,0,-43,52,0,0,0,0,-104,128,0,20,21,1,158,217,0,-23,260,0,22,11,1,9,284,0,-4,8,1,13,327,1,-173,256,0,15,25,1,223,-8,0,-132,239,1,32,43,1,10,6,0,130,32,0,-178,95,1,114,147,1,-116,143,0,121,155,1,-136,231,0,-5,24,1,4,9,1,168,191,0,1,16,1,23,11,0,74,244,1,-40,278,0,142,215,1,-2,10,1,23,270,0,161,232,0,0,32,1,120,242,0,-5,32,1,39,266,1,20,27,0,-11,13,0,-139,23,0,109,256,0,7,52,1];                           // flat [x*10, y*10, made] (x across the court, y from the rim, feet)
  var NS = SHOTS.length / 3;
  // A steady stream: about 7 times a second another of his shots lands (in game order), stays a moment, then slowly fades, so the
  // chart never fills up and never empties. Each court takes every 9th shot, the two courts different ones.
  var STREAM = { every: 9, life: 9, hold: 1.4 };
  var DOTS = [[], [], [], []];
  (function () {
    var all = [];
    for (var i = 0; i < NS; i++) {
      var lx = SHOTS[i * 3] / 10, ly = SHOTS[i * 3 + 1] / 10, m = SHOTS[i * 3 + 2];
      var ft = [RIM[0] + ly, lx];
      if (ft[0] > 44 || Math.abs(ft[1]) > 24.3) continue;   // keep heaves off the chart
      all.push({ f: ft, m: m });
    }
    [0, 4, 2, 6].forEach(function (start, side) {   // (every 9th shot: the left court from the 1st, the right from the 5th,
                                                    //  the two half courts by the logo from the 3rd and 7th)
      var pick = all.filter(function (d, i) { return i % STREAM.every === start; });
      pick.forEach(function (d, j) { DOTS[side].push({ f: d.f, m: d.m, a: LOOP * j / pick.length }); });
    });
  })();

  // ------------------------------------------------------------------ colours
  var GOLD_STOPS = [[150, 108, 16], [212, 175, 55], [247, 216, 124], [212, 175, 55]];
  function goldAt(u) {                              // u in 0..1 around a dark -> mid -> light -> mid -> dark cycle
    u = mod(u, 1) * 4; var i = Math.floor(u), k = u - i, a = GOLD_STOPS[i], b = GOLD_STOPS[(i + 1) % 4];
    return [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)];
  }
  var rgb = function (c, a) { return 'rgba(' + Math.round(c[0]) + ',' + Math.round(c[1]) + ',' + Math.round(c[2]) + ',' + (a === undefined ? 1 : a) + ')'; };
  var CH = function (a) { return 'rgba(255,255,255,' + a + ')'; };

  // ------------------------------------------------------------------ the banner object
  function Banner(canvas, opts) {
    this.cv = canvas; this.opts = opts || {}; this.ctx = canvas.getContext('2d');
    this.scale = 1; this.visible = true; this.paused = false; this.time = 0;
  }
  Banner.prototype.off = function () {
    var c = document.createElement('canvas'); c.width = this.cv.width; c.height = this.cv.height; return c;
  };
  // The logo comes in more than one size (opts.logo: [{ size, under, ball, glow, letters }, ...] smallest first), each in
  // four layers: the disc and silver ring, the basketball's lines (as a mask), the letters' glow, the letters. The
  // smallest one at least as large as the logo will be drawn is used, so it is only ever scaled DOWN -- never
  // stretched, never soft.
  var LAYERS = ['under', 'ball', 'glow', 'letters'];
  function logoSources(o) { return o.logo.slice(); }
  function loadLayers(pick) {
    return Promise.all(LAYERS.map(function (k) { return loadImg(pick[k]); })).then(function (imgs) {
      var out = {}; LAYERS.forEach(function (k, i) { out[k] = imgs[i]; }); return out;
    });
  }
  function loadImg(src) {
    return new Promise(function (ok, no) { var i = new Image(); i.decoding = 'async'; i.onload = function () { ok(i); }; i.onerror = no; i.src = src; });
  }
  Banner.prototype.measure = function () {
    var r = this.cv.getBoundingClientRect(), cssW = r.width || this.cv.parentNode.clientWidth || W;
    var dpr = Math.min(window.devicePixelRatio || 1, cssW < 700 ? 3 : 2);
    var w = Math.min(4096, Math.max(320, Math.round(cssW * dpr)));
    return { cssW: cssW, w: w, h: Math.round(w * H / W), logoPx: Math.round(LOGO.size * w / W) };
  };
  Banner.prototype.pickLogo = function (px) {
    var list = logoSources(this.opts), pick = list[list.length - 1];
    for (var i = 0; i < list.length; i++) if (list[i].size >= px) { pick = list[i]; break; }
    return pick;
  };
  Banner.prototype.load = function () {
    var self = this, o = this.opts, pick = this.pickLogo(this.measure().logoPx);
    var pFont = (o.font && window.FontFace) ? new FontFace('BAPlayfair', 'url(' + o.font + ')').load().then(function (f) { document.fonts.add(f); return 'BAPlayfair'; })
      .catch(function () { return 'Playfair Display'; }) : Promise.resolve('Playfair Display');
    return Promise.all([loadLayers(pick), pFont]).then(function (r) { self.logo = r[0]; self.logoSrc = pick.size; self.font = r[1]; });
  };
  Banner.prototype.resize = function () {
    var self = this, m = this.measure();
    this.glyph = clamp(860 / m.cssW, 1, 1.5);
    var pick = this.pickLogo(m.logoPx);
    if (pick.size !== this.logoSrc && (this.logo.under.naturalWidth || 0) < m.logoPx) {   // grew past the loaded logo: fetch the bigger one
      this.logoSrc = pick.size;
      loadLayers(pick).then(function (imgs) { self.logo = imgs; self.layers = null; self.resize(); }).catch(function () {});
    }
    if (m.w === this.cv.width && m.h === this.cv.height && this.layers) return;
    this.cv.width = m.w; this.cv.height = m.h; this.scale = m.w / W;
    this.buildLayers();
  };
  Banner.prototype.ctxOf = function (c) { var x = c.getContext('2d'); x.setTransform(this.scale, 0, 0, this.scale, 0, 0); return x; };
  Banner.prototype.buildLayers = function () {
    var s = this.scale, self = this;
    // courts (static chalk)
    var courts = this.off(), cx = this.ctxOf(courts);
    drawCourt(cx, mapL); drawCourt(cx, mapR);
    // the words, with their soft glow
    var words = this.off(), wx = this.ctxOf(words);
    wx.font = '400 68.5px "' + this.font + '", "Playfair Display", Georgia, serif'; wx.textBaseline = 'alphabetic'; wx.fillStyle = '#ffffff';
    [['BRADLEY', 294.5], ['ANALYTICS', 1240.5]].forEach(function (pair) {
      var txt = pair[0], sp = 7, ws = [], tot = -sp;
      for (var i = 0; i < txt.length; i++) { ws.push(wx.measureText(txt[i]).width); tot += ws[i] + sp; }
      var passes = [[0.55, 26], [0.35, 9], [0, 0]];
      passes.forEach(function (ps) {
        wx.shadowColor = 'rgba(255,255,255,' + ps[0] + ')'; wx.shadowBlur = ps[1] * s;
        var x = pair[1] - tot / 2;
        for (var j = 0; j < txt.length; j++) { wx.fillText(txt[j], x, 265); x += ws[j] + sp; }
      });
      wx.shadowBlur = 0;
    });
    // where the plays pass behind the words they dim, so the words stay clean
    var mask = this.off(), mx = this.ctxOf(mask);
    mx.filter = 'blur(' + (7 * s) + 'px)'; mx.fillStyle = 'rgba(0,0,0,0.55)';
    [[112, 206, 478, 275], [1022, 206, 1460, 275]].forEach(function (b) { roundRect(mx, b[0], b[1], b[2] - b[0], b[3] - b[1], 14); mx.fill(); });
    mx.filter = 'none';
    // the frame's bevel, one piece all the way round: a fine light line along its outer edge (brighter along the top),
    // a soft shade along its inner edge
    var bev = this.off(), bx = this.ctxOf(bev);
    frameRing(bx); bx.save(); bx.clip('evenodd');
    var lg = bx.createLinearGradient(0, FR.y0, 0, FR.y1);
    lg.addColorStop(0, 'rgba(255,255,255,0.42)'); lg.addColorStop(0.5, 'rgba(255,255,255,0.22)'); lg.addColorStop(1, 'rgba(255,255,255,0.14)');
    bx.lineJoin = 'miter'; bx.miterLimit = 10;
    outerPath(bx, 0.9); bx.lineWidth = 1.8; bx.strokeStyle = lg; bx.stroke();
    innerPath(bx, -0.9); bx.lineWidth = 2.6; bx.strokeStyle = 'rgba(0,0,0,0.30)'; bx.stroke();
    innerPath(bx, -2.6); bx.lineWidth = 1.2; bx.strokeStyle = 'rgba(0,0,0,0.12)'; bx.stroke();
    bx.restore();
    var lsz = Math.round(LOGO.size * s);
    var L = {}; LAYERS.forEach(function (k) { L[k] = k === 'glow' ? smoothLogo(self.logo[k], lsz) : scaledLogo(self.logo[k], lsz); });
    var bc = document.createElement('canvas'); bc.width = bc.height = lsz;           // the gold basketball, drawn each frame
    this.logoL = { L: L, ball: bc, x: Math.round(LOGO.x * s), y: Math.round(LOGO.y * s), k: lsz / 2048, size: lsz };
    this.layers = { courts: courts, words: words, mask: mask, bevel: bev, play: this.off() };
  };

  function roundRect(c, x, y, w, h, r) {
    c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
  }
  function strokePts(c, P, o) {
    if (P.length < 2) return;
    c.beginPath(); c.moveTo(P[0][0], P[0][1]); for (var i = 1; i < P.length; i++) c.lineTo(P[i][0], P[i][1]);
    c.setLineDash(o.dash || []); c.lineWidth = o.width || 2; c.strokeStyle = o.color; c.lineCap = 'round'; c.lineJoin = 'round'; c.stroke(); c.setLineDash([]);
  }
  function arc(cx, cy, r, a0, a1, n) { var o = []; n = n || 90; for (var i = 0; i <= n; i++) { var a = a0 + (a1 - a0) * i / n; o.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]); } return o; }
  function drawCourt(c, map) {
    var col = 'rgba(255,255,255,0.3)';
    var S = function (pts, o) { o = o || {}; strokePts(c, pts.map(map), { color: col, width: o.width || 1.8, dash: o.dash }); };
    var R = 5.25, a3 = Math.asin(22 / 23.75);
    S([[0, -8], [19, -8], [19, 8], [0, 8]]);
    S(arc(19, 0, 6, -Math.PI / 2, Math.PI / 2)); S(arc(19, 0, 6, Math.PI / 2, Math.PI * 1.5), { dash: [5, 5] });
    [7, 10, 13, 16].forEach(function (fx) { S([[fx, -8], [fx, -8.9]]); S([[fx, 8], [fx, 8.9]]); });
    S([[4, -3], [4, 3]], { width: 2.2 }); S([[4, 0], [R - 0.75, 0]]); S(arc(R, 0, 0.75, 0, Math.PI * 2, 30));
    S(arc(R, 0, 4, -Math.PI / 2, Math.PI / 2));
    S([[0, -22], [R + Math.cos(a3) * 23.75, -22]]); S([[0, 22], [R + Math.cos(a3) * 23.75, 22]]);
    S(arc(R, 0, 23.75, -a3, a3));
    S([[28, -25.2], [28, -24.1]]); S([[28, 25.2], [28, 24.1]]);
    S([[47, -25.2], [47, 25.2]]); S(arc(47, 0, 6, 0, Math.PI * 2)); S(arc(47, 0, 2, 0, Math.PI * 2, 40));
    var F = 94, Rf = F - R;
    S(arc(Rf, 0, 23.75, Math.PI - a3, Math.PI + a3)); S([[F - 19, -8], [F - 19, 8]]); S(arc(F - 19, 0, 6, Math.PI / 2, Math.PI * 1.5));
    S([[F - 28, -25.2], [F - 28, -24.1]]); S([[F - 28, 25.2], [F - 28, 24.1]]);
  }
  function arrowHead(c, p, dir, color, size) {
    var d = Math.hypot(dir[0], dir[1]) || 1, ux = dir[0] / d, uy = dir[1] / d; size = size || 8;
    c.beginPath(); c.moveTo(p[0] + ux * size * 0.35, p[1] + uy * size * 0.35);
    c.lineTo(p[0] - ux * size - uy * size * 0.55, p[1] - uy * size + ux * size * 0.55);
    c.lineTo(p[0] - ux * size * 0.62, p[1] - uy * size * 0.62);
    c.lineTo(p[0] - ux * size + uy * size * 0.55, p[1] - uy * size - ux * size * 0.55); c.closePath(); c.fillStyle = color; c.fill();
  }
  function screenBar(c, p, dir, color) {
    var d = Math.hypot(dir[0], dir[1]) || 1, nx = -dir[1] / d, ny = dir[0] / d, s = 8.5 * G;
    c.beginPath(); c.moveTo(p[0] + nx * s, p[1] + ny * s); c.lineTo(p[0] - nx * s, p[1] - ny * s);
    c.lineWidth = 3 * G; c.strokeStyle = color; c.lineCap = 'round'; c.stroke();
  }
  function tailDir(P) { var n = P.length, k = Math.max(0, n - 4); return [P[n - 1][0] - P[k][0], P[n - 1][1] - P[k][1]]; }

  // ------------------------------------------------------------------ one court, one moment
  var LEAD = 0.65, KEEP = 0.9, FADE = 0.7;
  var G = 1;                                      // glyph scale: players, arrows and the ball grow on narrow screens so they stay readable
  function drawPossession(c, map, t) {
    // arrows: drawn out just ahead of each move, held while it happens, then faded
    TL.acts.forEach(function (a) {
      if (a.kind === 'reset') return;
      var s0 = a.t0 - LEAD, end = a.t1 + KEEP, life = end + FADE - s0;
      var dt = mod(t - s0, LOOP); if (dt >= life) return;
      var f = eOut(dt / LEAD), al = dt < life - FADE ? 1 : (life - dt) / FADE;
      var path = a.wave || a.path, P = upto(path, f).map(map); if (P.length < 2) return;
      var col = CH(0.5 * al);
      strokePts(c, P, { width: 2.1 * G, color: col });
      if (a.kind === 'screen') { if (f > 0.97) screenBar(c, P[P.length - 1], tailDir(upto(a.path, 1).map(map)), col); }
      else if (f > 0.08) arrowHead(c, P[P.length - 1], tailDir(P), col, 8 * G);
    });
    TL.passes.forEach(function (ps) {
      var dur = ps.t1 - ps.t0, life = dur + KEEP + FADE, dt = mod(t - ps.t0, LOOP); if (dt >= life) return;
      var p0 = handPos(ps.from, ps.t0), p1 = handPos(ps.to, ps.t1), mid = lerp2(p0, p1, 0.5);
      var nx = -(p1[1] - p0[1]) * 0.12, ny = (p1[0] - p0[0]) * 0.12;
      var path = { pts: spline([p0, [mid[0] + nx, mid[1] + ny], p1], 16) }; path.L = measure(path.pts);
      var f = eSine(Math.min(1, dt / dur)), al = dt < life - FADE ? 1 : (life - dt) / FADE;
      var P = upto(path, f).map(map), col = CH(0.55 * al);
      strokePts(c, P, { width: 2.1 * G, color: col, dash: [7 * G, 6 * G] });
      if (f > 0.1) arrowHead(c, P[P.length - 1], tailDir(P), col, 8 * G);
    });
    // defenders (X, numbered) then the offence (numbered O's)
    c.textAlign = 'center'; c.textBaseline = 'middle';
    c.font = '700 ' + (9 * G).toFixed(1) + 'px Arial, Helvetica, sans-serif';
    for (var w = 1; w <= 5; w++) {
      var dpt = map(defenderAt(w, t)), x = dpt[0], y = dpt[1], s = 6.2 * G;
      c.beginPath(); c.moveTo(x - s, y - s); c.lineTo(x + s, y + s); c.moveTo(x + s, y - s); c.lineTo(x - s, y + s);
      c.lineWidth = 2.2 * G; c.strokeStyle = CH(0.5); c.lineCap = 'round'; c.stroke();
      c.fillStyle = CH(0.6); c.fillText(String(w), x + 9.5 * G, y + 7.5 * G);
    }
    c.font = '700 ' + (11 * G).toFixed(1) + 'px Arial, Helvetica, sans-serif';
    for (var o = 1; o <= 5; o++) {
      var op = map(playerAt(o, t));
      c.beginPath(); c.arc(op[0], op[1], 10 * G, 0, Math.PI * 2); c.lineWidth = 2.2 * G; c.strokeStyle = CH(0.78); c.stroke();
      c.fillStyle = CH(0.88); c.fillText(String(o), op[0], op[1] + 0.5);
    }
    // the ball
    var b = ballAt(t);
    if (b.shot) drawShot(c, map, b.shot, t);
    else {
      var bp = map(b.p), lift = (b.lift || 0) * PXF;
      c.beginPath(); c.arc(bp[0], bp[1] - lift, 3.6 * G, 0, Math.PI * 2); c.fillStyle = CH(0.95); c.fill();
    }
    // the rim lights up on a make
    TL.shots.forEach(function (sh) {
      var age = mod(t - sh.t1, LOOP); if (age > 0.9) return;
      var rp = map(RIM), k = age / 0.9;
      c.beginPath(); c.arc(rp[0], rp[1], (0.9 + 3.4 * eOut(k)) * PXF, 0, Math.PI * 2);
      c.lineWidth = 2.6 * (1 - k) + 0.4; c.strokeStyle = rgb([247, 216, 124], 0.9 * (1 - k)); c.stroke();
      c.beginPath(); c.arc(rp[0], rp[1], 0.75 * PXF + 1.5, 0, Math.PI * 2); c.lineWidth = 2.4; c.strokeStyle = rgb([255, 240, 190], 0.95 * (1 - k)); c.stroke();
    });
  }
  function drawShot(c, map, sh, t) {               // the ball's flight: up from the shooter's hands, over, down into the rim
    var u = seg(t, sh.t0, sh.t1);
    var from = handPos(sh.who, sh.t0), dist = Math.hypot(from[0] - RIM[0], from[1] - RIM[1]);
    var peak = 3 + dist * 0.42;                       // feet of "height": the arc bows out toward half court
    var nx = -(RIM[1] - from[1]) / (dist || 1), ny = (RIM[0] - from[0]) / (dist || 1);
    if (nx < 0) { nx = -nx; ny = -ny; }
    var pos = function (v) { var g = lerp2(from, RIM, v), hgt = peak * 4 * v * (1 - v);
      var m = map([g[0] + nx * hgt * 0.42, g[1] + ny * hgt * 0.42]); return [m[0], m[1], hgt]; };
    // a gold trail behind the ball
    var n = 18, u0 = Math.max(0, u - 0.32);
    for (var i = 0; i < n; i++) {
      var v0 = lerp(u0, u, i / n), v1 = lerp(u0, u, (i + 1) / n), a = pos(v0), b = pos(v1), k = (i + 1) / n;
      c.beginPath(); c.moveTo(a[0], a[1]); c.lineTo(b[0], b[1]); c.lineWidth = 1 + 2.4 * k; c.lineCap = 'round';
      c.strokeStyle = rgb(goldAt(0.55 + 0.2 * k), 0.85 * k); c.stroke();
    }
    var g = map(lerp2(from, RIM, u)), bp = pos(u), r = (3.6 + bp[2] * 0.22) * G;
    c.beginPath(); c.ellipse(g[0], g[1], 3.2, 1.8, 0, 0, Math.PI * 2); c.fillStyle = 'rgba(0,0,0,0.35)'; c.fill();   // its shadow on the floor
    var glow = c.createRadialGradient(bp[0], bp[1], 0, bp[0], bp[1], r * 2.6);
    glow.addColorStop(0, 'rgba(255,240,190,0.55)'); glow.addColorStop(1, 'rgba(255,240,190,0)');
    c.fillStyle = glow; c.beginPath(); c.arc(bp[0], bp[1], r * 2.6, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.arc(bp[0], bp[1], r, 0, Math.PI * 2); c.fillStyle = CH(0.98); c.fill();
    // a gold ring where the shot went up
    var rel = map(from), ka = seg(t, sh.t0, sh.t0 + 0.7);
    if (ka < 1) { c.beginPath(); c.arc(rel[0], rel[1], 4 + 16 * eOut(ka), 0, Math.PI * 2); c.lineWidth = 1.6; c.strokeStyle = rgb([247, 216, 124], 0.8 * (1 - ka)); c.stroke(); }
  }
  // Each shot is a metal disc: makes in gold, misses in silver, every disc shaded with its own gradient whose light
  // sweeps slowly across the court.
  var SILVER = [[112, 114, 122], [196, 198, 206], [248, 248, 252], [196, 198, 206]];
  function metalAt(stops, u) {
    u = mod(u, 1) * 4; var i = Math.floor(u), k = u - i, a = stops[i], b = stops[(i + 1) % 4];
    return [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)];
  }
  function drawChart(c, map, t, dots, phase) {
    var R = 6.8 * (0.6 + 0.4 * G);
    for (var i = 0; i < dots.length; i++) {
      var d = dots[i], age = mod(t - d.a, LOOP); if (age >= STREAM.life) continue;
      var al = 1 - eSine((age - STREAM.hold) / (STREAM.life - STREAM.hold)); if (al <= 0.02) continue;
      var k = age < 0.34 ? (age < 0.2 ? 1.6 * eOut(age / 0.2) : lerp(1.6, 1, (age - 0.2) / 0.14)) : 1;
      var p = map(d.f), r = R * k, stops = d.m ? GOLD_STOPS : SILVER;
      if (Math.hypot(p[0] - LOGO.cx, p[1] - LOGO.cy) < LOGO.ro - r - 2) continue;    // wholly under the logo: never seen
      var u = phase + p[0] / 700 + p[1] / 1400;          // where this disc sits in the slow sweep of light
      var g = c.createLinearGradient(p[0] - r, p[1] - r, p[0] + r, p[1] + r);
      g.addColorStop(0, rgb(metalAt(stops, u + 0.5)));
      g.addColorStop(0.42, rgb(metalAt(stops, u + 0.12)));
      g.addColorStop(1, rgb(metalAt(stops, u - 0.22)));
      c.globalAlpha = al * (d.m ? 0.95 : 0.85);
      c.beginPath(); c.arc(p[0], p[1], r, 0, Math.PI * 2); c.fillStyle = g; c.fill();
      c.lineWidth = 0.8; c.strokeStyle = 'rgba(0,0,0,0.35)'; c.stroke();     // a thin edge so touching discs stay apart
      if (d.m && age < 0.8) {                         // a make lands with a gold ripple
        var q = age / 0.8;
        c.globalAlpha = 0.75 * (1 - q);
        c.beginPath(); c.arc(p[0], p[1], r + 2 + 12 * eOut(q), 0, Math.PI * 2); c.lineWidth = 1.4;
        c.strokeStyle = rgb(metalAt(GOLD_STOPS, u + 0.5)); c.stroke();
      }
    }
    c.globalAlpha = 1;
  }

  // ------------------------------------------------------------------ the frame and the ring
  // The frame is one continuous rectangle with sharp corners, inside and out (not four bars meeting at the corners):
  // its gold flows around it in one piece -- a conic gradient whose colours follow the distance around the frame --
  // and a glint (a white-hot core in a warm gold halo) runs around it, a second one half a lap behind.
  var PER = 2 * (FR.x1 - FR.x0) + 2 * (FR.y1 - FR.y0), BAR_T = 12, FRR = 0;
  function rrect(c, x0, y0, x1, y1, r) {
    if (r <= 0) { c.moveTo(x0, y0); c.lineTo(x1, y0); c.lineTo(x1, y1); c.lineTo(x0, y1); c.closePath(); return; }
    c.moveTo(x0 + r, y0); c.arcTo(x1, y0, x1, y1, r); c.arcTo(x1, y1, x0, y1, r); c.arcTo(x0, y1, x0, y0, r); c.arcTo(x0, y0, x1, y0, r); c.closePath();
  }
  function outerPath(c, inset) { inset = inset || 0; c.beginPath(); rrect(c, FR.x0 + inset, FR.y0 + inset, FR.x1 - inset, FR.y1 - inset, FRR - inset); }
  function innerPath(c, inset) {
    inset = inset || 0; var th = FR.th - inset;
    c.beginPath(); rrect(c, FR.x0 + th, FR.y0 + th, FR.x1 - th, FR.y1 - th, Math.max(0, FRR - th));
  }
  function frameRing(c) {                          // the frame's own shape (fill or clip it with 'evenodd')
    c.beginPath(); rrect(c, FR.x0, FR.y0, FR.x1, FR.y1, FRR);
    var th = FR.th; rrect(c, FR.x0 + th, FR.y0 + th, FR.x1 - th, FR.y1 - th, Math.max(0, FRR - th));
  }
  function frameColor(sPos, t) {
    var u = sPos / PER, v = 0.5 + 0.5 * Math.cos(2 * Math.PI * (3 * u - t / BAR_T));
    var D = [150, 108, 16], M = [212, 175, 55], L = [247, 216, 124];
    return v < 0.5 ? [lerp(D[0], M[0], v * 2), lerp(D[1], M[1], v * 2), lerp(D[2], M[2], v * 2)]
                   : [lerp(M[0], L[0], (v - .5) * 2), lerp(M[1], L[1], (v - .5) * 2), lerp(M[2], L[2], (v - .5) * 2)];
  }
  var FCX = (FR.x0 + FR.x1) / 2, FCY = (FR.y0 + FR.y1) / 2, FHW = (FR.x1 - FR.x0 - FR.th) / 2, FHH = (FR.y1 - FR.y0 - FR.th) / 2;
  function perimAtAngle(a) {                       // the distance around the frame (from its top-left) in direction a
    var cs = Math.cos(a), sn = Math.sin(a), d = Math.min(FHW / Math.max(1e-9, Math.abs(cs)), FHH / Math.max(1e-9, Math.abs(sn)));
    var x = FCX + cs * d, y = FCY + sn * d, w = 2 * FHW, h = 2 * FHH, x0 = FCX - FHW, y0 = FCY - FHH;
    if (Math.abs(y - y0) < 0.01) return x - x0;
    if (Math.abs(x - (x0 + w)) < 0.01) return w + (y - y0);
    if (Math.abs(y - (y0 + h)) < 0.01) return w + h + (x0 + w - x);
    return 2 * w + h + (y0 + h - y);
  }
  function pointAtPerim(u) {                       // the frame's centre line at a fraction u of the way round
    var w = 2 * FHW, h = 2 * FHH, x0 = FCX - FHW, y0 = FCY - FHH, d = mod(u, 1) * 2 * (w + h);
    if (d < w) return [x0 + d, y0];
    if ((d -= w) < h) return [x0 + w, y0 + d];
    if ((d -= h) < w) return [x0 + w - d, y0 + h];
    return [x0, y0 + h - (d - w)];
  }
  var NANG = 120, ANG = []; (function () { for (var i = 0; i <= NANG; i++) ANG.push(perimAtAngle(2 * Math.PI * i / NANG) / (2 * (2 * FHW + 2 * FHH)) * PER); })();
  function drawFrame(c, t) {
    c.save();
    frameRing(c);
    if (c.createConicGradient) {
      var g = c.createConicGradient(0, FCX, FCY);
      for (var i = 0; i <= NANG; i++) g.addColorStop(i / NANG, rgb(frameColor(ANG[i], t)));
      c.fillStyle = g;
    } else {
      var lg = c.createLinearGradient(FR.x0, 0, FR.x1, 0);
      for (var j = 0; j <= 12; j++) lg.addColorStop(j / 12, rgb(frameColor(PER * j / 24, t)));
      c.fillStyle = lg;
    }
    c.fill('evenodd');
    c.clip('evenodd');
    // the glints: a white-hot core in a warm gold halo, sliding round the frame
    c.globalCompositeOperation = 'lighter';
    [0, 0.5].forEach(function (k) {
      var p = pointAtPerim(0.5 * t / BAR_T + k), r = 46;
      var rg = c.createRadialGradient(p[0], p[1], 0, p[0], p[1], r);
      rg.addColorStop(0, 'rgba(255,252,240,0.85)'); rg.addColorStop(0.12, 'rgba(255,240,200,0.55)');
      rg.addColorStop(0.4, 'rgba(247,216,124,0.18)'); rg.addColorStop(1, 'rgba(247,216,124,0)');
      c.fillStyle = rg; c.fillRect(p[0] - r, p[1] - r, 2 * r, 2 * r);
    });
    c.restore();
  }
  // The logo never moves and is never resampled while running: it is scaled once (in halving steps, so it stays sharp
  // in every browser) to the exact pixel size it is shown at, and drawn on whole pixels. Only a light travels around
  // its silver ring.
  function scaledLogo(img, size) {
    try { return lanczosLogo(img, size); } catch (e) { /* e.g. pixels unreadable: fall back to the browser's scaler */ }
    return smoothLogo(img, size);
  }
  function smoothLogo(img, size) {                 // the browser's own scaler, in halving steps (for the soft glow)
    var src = img, w = img.naturalWidth || img.width;
    while (w / 2 >= size * 1.15) {
      w = Math.round(w / 2);
      var h = document.createElement('canvas'); h.width = h.height = w;
      var hx = h.getContext('2d'); hx.imageSmoothingEnabled = true; hx.imageSmoothingQuality = 'high';
      hx.drawImage(src, 0, 0, w, w); src = h;
    }
    var o = document.createElement('canvas'); o.width = o.height = size;
    var ox = o.getContext('2d'); ox.imageSmoothingEnabled = true; ox.imageSmoothingQuality = 'high';
    ox.drawImage(src, 0, 0, size, size);
    return o;
  }
  // Lanczos-3 resampling (the same filter used to make the logo files), done once per size in plain JavaScript, so the
  // logo comes out exactly as sharp in every browser instead of depending on each browser's own image scaler.
  function lanczosWeights(n0, n1) {
    var sc = n0 / n1, sup = 3 * Math.max(1, sc), out = [];
    var L = function (x) { if (x === 0) return 1; if (x <= -3 || x >= 3) return 0; var px = Math.PI * x; return 3 * Math.sin(px) * Math.sin(px / 3) / (px * px); };
    for (var i = 0; i < n1; i++) {
      var c = (i + 0.5) * sc - 0.5, a = Math.max(0, Math.ceil(c - sup)), b = Math.min(n0 - 1, Math.floor(c + sup)), ws = [], tot = 0;
      for (var j = a; j <= b; j++) { var w = L((j - c) / Math.max(1, sc)); ws.push(w); tot += w; }
      for (var k = 0; k < ws.length; k++) ws[k] /= tot;
      out.push({ a: a, w: ws });
    }
    return out;
  }
  function lanczosLogo(img, size) {
    var n0 = img.naturalWidth || img.width;
    var c0 = document.createElement('canvas'); c0.width = c0.height = n0;
    var x0 = c0.getContext('2d'); x0.drawImage(img, 0, 0);
    var src = x0.getImageData(0, 0, n0, n0).data, N = n0 * n0;
    var pm = new Float32Array(N * 4);                    // premultiplied, so edges never pick up colour from clear pixels
    for (var p = 0; p < N; p++) { var al = src[p * 4 + 3] / 255; pm[p * 4] = src[p * 4] * al; pm[p * 4 + 1] = src[p * 4 + 1] * al; pm[p * 4 + 2] = src[p * 4 + 2] * al; pm[p * 4 + 3] = src[p * 4 + 3]; }
    var W8 = lanczosWeights(n0, size);
    var mid = new Float32Array(size * n0 * 4);           // horizontal pass: n0 x n0 -> size x n0
    for (var y = 0; y < n0; y++) {
      var row = y * n0;
      for (var i = 0; i < size; i++) {
        var f = W8[i], r = 0, g = 0, bl = 0, a = 0;
        for (var k = 0; k < f.w.length; k++) { var q = (row + f.a + k) * 4, w = f.w[k]; r += pm[q] * w; g += pm[q + 1] * w; bl += pm[q + 2] * w; a += pm[q + 3] * w; }
        var o = (y * size + i) * 4; mid[o] = r; mid[o + 1] = g; mid[o + 2] = bl; mid[o + 3] = a;
      }
    }
    var out = document.createElement('canvas'); out.width = out.height = size;
    var ox = out.getContext('2d'), id = ox.createImageData(size, size), d = id.data;
    for (var yy = 0; yy < size; yy++) {                  // vertical pass: size x n0 -> size x size
      var fv = W8[yy];
      for (var xx = 0; xx < size; xx++) {
        var R = 0, Gc = 0, Bc = 0, Ac = 0;
        for (var kk = 0; kk < fv.w.length; kk++) { var qq = ((fv.a + kk) * size + xx) * 4, ww = fv.w[kk]; R += mid[qq] * ww; Gc += mid[qq + 1] * ww; Bc += mid[qq + 2] * ww; Ac += mid[qq + 3] * ww; }
        var oo = (yy * size + xx) * 4, aa = Math.max(0, Math.min(255, Ac));
        if (aa > 0.5) { var un = 255 / aa; d[oo] = R * un; d[oo + 1] = Gc * un; d[oo + 2] = Bc * un; }   // (the array clamps to 0-255)
        d[oo + 3] = aa;
      }
    }
    ox.putImageData(id, 0, 0);
    return out;
  }
  // The logo, layer by layer (device pixels; LL = { L: layers, ball, x, y, k, size }, k = device px per master px): the
  // disc and silver ring; the basketball in animated gradient gold -- its light drifting slowly along the gold, and
  // every few seconds a white-and-gold glare sweeping across it -- under the letters' glow (screen) and the letters;
  // then the silver ring's own silver-blue glare.
  var BALL_T = 12, BALL_SWEEP = 3.6;               // a glare every 12 s, taking 3.6 s to cross the ball
  // the basketball's gold: the logo's own gradient (deep gold, gold, light gold, near-white, gold, deep gold), as a loop
  var BALL_GOLD = [[138, 101, 8], [184, 134, 11], [245, 211, 112], [255, 240, 184], [224, 184, 72], [184, 134, 11]];
  function ballGold(u) {
    u = mod(u, 1) * BALL_GOLD.length; var i = Math.floor(u), k = u - i, a = BALL_GOLD[i], b = BALL_GOLD[(i + 1) % BALL_GOLD.length];
    return [lerp(a[0], b[0], k), lerp(a[1], b[1], k), lerp(a[2], b[2], k)];
  }
  function drawLogo(c, LL, t) {
    var Ly = LL.L, x = LL.x, y = LL.y, n = LL.size;
    c.drawImage(Ly.under, x, y);
    var b = LL.ball, bx = b.getContext('2d'), u = mod(t, BALL_T) / BALL_SWEEP;
    // the ball is painted afresh every frame while the glare crosses it, otherwise every third frame (its gold drifts slowly)
    LL.n = (LL.n || 0) + 1;
    if (u >= 1 && LL.painted && LL.n % 3 && Math.abs(t - LL.painted) < 0.2) { finishLogo(c, LL, Ly, b, x, y, t); return; }
    LL.painted = t;
    bx.setTransform(1, 0, 0, 1, 0, 0); bx.globalCompositeOperation = 'source-over'; bx.clearRect(0, 0, n, n);
    var g = bx.createLinearGradient(0, 0, n, n), ph = t / 24;
    for (var i = 0; i <= 24; i++) g.addColorStop(i / 24, rgb(ballGold(i / 24 - ph)));
    bx.fillStyle = g; bx.fillRect(0, 0, n, n);
    var sp = bx.createRadialGradient(n * 0.3, n * 0.24, 0, n * 0.3, n * 0.24, n * 0.55);   // a soft standing sheen
    sp.addColorStop(0, 'rgba(255,248,225,0.30)'); sp.addColorStop(1, 'rgba(255,248,225,0)');
    bx.fillStyle = sp; bx.fillRect(0, 0, n, n);
    if (u < 1) {                                     // the glare: a bright band crossing the ball corner to corner
      var e = eSine(u), d = lerp(-0.3, 1.3, e) * n, w = n * 0.17, a = Math.min(1, 2.2 * Math.sin(Math.PI * u));
      var gl = bx.createLinearGradient(d - w, d - w, d + w, d + w);
      gl.addColorStop(0, 'rgba(255,236,170,0)'); gl.addColorStop(0.3, 'rgba(255,226,140,' + (0.55 * a).toFixed(3) + ')');
      gl.addColorStop(0.47, 'rgba(255,255,255,' + a.toFixed(3) + ')'); gl.addColorStop(0.53, 'rgba(255,255,255,' + a.toFixed(3) + ')');
      gl.addColorStop(0.7, 'rgba(255,226,140,' + (0.55 * a).toFixed(3) + ')'); gl.addColorStop(1, 'rgba(255,236,170,0)');
      bx.globalCompositeOperation = 'lighter'; bx.fillStyle = gl; bx.fillRect(0, 0, n, n); bx.globalCompositeOperation = 'source-over';
    }
    bx.globalCompositeOperation = 'destination-in'; bx.drawImage(Ly.ball, 0, 0); bx.globalCompositeOperation = 'source-over';
    finishLogo(c, LL, Ly, b, x, y, t);
  }
  function finishLogo(c, LL, Ly, b, x, y, t) {
    c.drawImage(b, x, y);
    c.save(); c.globalCompositeOperation = 'screen'; c.drawImage(Ly.glow, x, y); c.restore();
    c.drawImage(Ly.letters, x, y);
    drawRingShine(c, LL, t);
  }
  // The silver ring's light, as a polished ring under one light from the upper left: a broad silver sheen there (white
  // in the middle, icy blue at its edges) that sways gently as if the light moved a little, a faint reflection opposite,
  // and now and then a sharp glint that flares up, slides a short way along the sheen with a silver-blue bloom and a
  // small star flare, and fades -- never a spot circling the ring.
  var GLINT_T = 9, GLINT_LEN = 2.6;
  function ringClip(c, cx, cy, ro, ri) {
    c.beginPath(); c.arc(cx, cy, ro - 0.3, 0, Math.PI * 2); c.arc(cx, cy, ri + 0.3, 0, Math.PI * 2, true); c.clip('evenodd');
  }
  function drawRingShine(c, L, t) {
    if (!c.createConicGradient) return;
    var cx = L.x + LCX * L.k, cy = L.y + LCY * L.k, ro = 1014.4 * L.k, ri = 972.8 * L.k, rw = ro - ri, rm = (ro + ri) / 2;
    var th = -Math.PI * 0.75 + 0.33 * Math.sin(2 * Math.PI * t / 14) + 0.08 * Math.sin(2 * Math.PI * t / 5.3);
    var breathe = 0.85 + 0.15 * Math.sin(2 * Math.PI * t / 6.1);
    c.save();
    ringClip(c, cx, cy, ro, ri);
    var g = c.createConicGradient(th - Math.PI, cx, cy);         // (the sheen sits at 0.5, the reflection at 0 / 1)
    var A = function (a) { return (a * breathe).toFixed(3); };
    [[0, 'rgba(225,236,255,' + A(0.2) + ')'], [0.035, 'rgba(160,190,240,' + A(0.06) + ')'], [0.07, 'rgba(160,190,240,0)'],
     [0.36, 'rgba(150,185,245,0)'], [0.41, 'rgba(160,195,255,' + A(0.16) + ')'], [0.46, 'rgba(225,236,255,' + A(0.45) + ')'],
     [0.5, 'rgba(255,255,255,' + A(0.62) + ')'], [0.54, 'rgba(225,236,255,' + A(0.45) + ')'], [0.59, 'rgba(160,195,255,' + A(0.16) + ')'],
     [0.64, 'rgba(150,185,245,0)'], [0.93, 'rgba(160,190,240,0)'], [0.965, 'rgba(160,190,240,' + A(0.06) + ')'],
     [1, 'rgba(225,236,255,' + A(0.2) + ')']].forEach(function (st) { g.addColorStop(st[0], st[1]); });
    c.fillStyle = g; c.fillRect(cx - ro - 2, cy - ro - 2, ro * 2 + 4, ro * 2 + 4);
    // the glint
    var u = mod(t - 2, GLINT_T) / GLINT_LEN, gx = 0, gy = 0, ga = 0;
    if (u < 1) {
      ga = Math.pow(Math.sin(Math.PI * u), 1.6);
      var ag = th - 0.5 + 1.0 * eSine(u);
      var gg = c.createConicGradient(ag - Math.PI, cx, cy);
      [[0.47, 'rgba(170,200,255,0)'], [0.488, 'rgba(200,222,255,' + (0.6 * ga).toFixed(3) + ')'], [0.5, 'rgba(255,255,255,' + ga.toFixed(3) + ')'],
       [0.512, 'rgba(200,222,255,' + (0.6 * ga).toFixed(3) + ')'], [0.53, 'rgba(170,200,255,0)']].forEach(function (st) { gg.addColorStop(st[0], st[1]); });
      c.fillStyle = gg; c.fillRect(cx - ro - 2, cy - ro - 2, ro * 2 + 4, ro * 2 + 4);
      gx = cx + Math.cos(ag) * rm; gy = cy + Math.sin(ag) * rm;
    }
    c.restore();
    c.save(); c.globalCompositeOperation = 'screen';
    // a soft bloom over the sheen, and a stronger one with a small star flare where the glint is
    var sx = cx + Math.cos(th) * rm, sy = cy + Math.sin(th) * rm, sr = rw * 3;
    var sb = c.createRadialGradient(sx, sy, 0, sx, sy, sr);
    sb.addColorStop(0, 'rgba(220,232,255,' + (0.22 * breathe).toFixed(3) + ')'); sb.addColorStop(1, 'rgba(150,185,255,0)');
    c.fillStyle = sb; c.fillRect(sx - sr, sy - sr, 2 * sr, 2 * sr);
    if (ga > 0.01) {
      var r = rw * 3.6, rg = c.createRadialGradient(gx, gy, 0, gx, gy, r);
      rg.addColorStop(0, 'rgba(245,250,255,' + (0.85 * ga).toFixed(3) + ')'); rg.addColorStop(0.2, 'rgba(190,215,255,' + (0.4 * ga).toFixed(3) + ')');
      rg.addColorStop(1, 'rgba(130,170,255,0)');
      c.fillStyle = rg; c.fillRect(gx - r, gy - r, 2 * r, 2 * r);
      var fl = rw * 5.5 * ga, w = Math.max(0.6, rw * 0.07);
      [[1, 0], [0, 1]].forEach(function (d) {
        var lg = c.createLinearGradient(gx - d[0] * fl, gy - d[1] * fl, gx + d[0] * fl, gy + d[1] * fl);
        lg.addColorStop(0, 'rgba(200,222,255,0)'); lg.addColorStop(0.5, 'rgba(255,255,255,' + (0.7 * ga).toFixed(3) + ')'); lg.addColorStop(1, 'rgba(200,222,255,0)');
        c.fillStyle = lg;
        if (d[0]) c.fillRect(gx - fl, gy - w / 2, 2 * fl, w); else c.fillRect(gx - w / 2, gy - fl, w, 2 * fl);
      });
    }
    c.restore();
  }

  // ------------------------------------------------------------------ one frame
  Banner.prototype.render = function (t) {
    var c = this.ctx, L = this.layers, s = this.scale, cw = this.cv.width, chh = this.cv.height; G = this.glyph || 1;
    c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, cw, chh);
    // courts, chart and plays on their own layer (kept inside the frame and off the logo, dimmed behind the words)
    var p = L.play.getContext('2d'); p.setTransform(1, 0, 0, 1, 0, 0); p.clearRect(0, 0, cw, chh);
    p.drawImage(L.courts, 0, 0);
    p.setTransform(s, 0, 0, s, 0, 0);
    p.save(); p.beginPath(); p.rect(IN.x0, IN.y0, IN.x1 - IN.x0, IN.y1 - IN.y0); p.arc(LOGO.cx, LOGO.cy, LOGO.ro + 1.5, 0, Math.PI * 2, true); p.clip();
    // the right court runs 5 s ahead (its shots fall between the left's); the two half courts by the logo 2.5 s and
    // 7.5 s ahead
    var tl = mod(t, LOOP), tr = mod(t + 5, LOOP), tli = mod(t + 2.5, LOOP), tri = mod(t + 7.5, LOOP), phase = t / 9;
    drawChart(p, mapL, tl, DOTS[0], phase);
    drawChart(p, mapR, tr, DOTS[1], phase + 0.5);
    drawChart(p, mapLi, tli, DOTS[2], phase + 0.25);
    drawChart(p, mapRi, tri, DOTS[3], phase + 0.75);
    drawPossession(p, mapL, tl);
    drawPossession(p, mapR, tr);
    drawPossession(p, mapLi, tli);
    drawPossession(p, mapRi, tri);
    p.restore();
    p.setTransform(1, 0, 0, 1, 0, 0); p.globalCompositeOperation = 'destination-out'; p.drawImage(L.mask, 0, 0); p.globalCompositeOperation = 'source-over';
    c.drawImage(L.play, 0, 0);
    c.drawImage(L.words, 0, 0);
    c.setTransform(s, 0, 0, s, 0, 0);
    drawFrame(c, t);
    c.setTransform(1, 0, 0, 1, 0, 0); c.drawImage(L.bevel, 0, 0);
    drawLogo(c, this.logoL, t);
  };

  Banner.prototype.start = function () {
    var self = this;
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.resize();
    this.time = this.opts.startAt || 0;
    if (this.opts.time !== undefined || reduce) { this.render(this.opts.time !== undefined ? this.opts.time : 6.5); this.onFirst(); return; }
    var last = null, slow = 0, minGap = 0, drawn = 0;
    var tick = function (now) {
      requestAnimationFrame(tick);
      if (last === null) last = now;
      var dt = Math.min(0.1, (now - last) / 1000);     // a hidden tab or a stall never makes the plays jump ahead
      if (!self.visible || (now - drawn < minGap)) { last = now; if (!self.paused) self.time += self.visible ? dt : 0; return; }
      last = now; drawn = now;
      if (!self.paused) self.time += dt;
      var c0 = performance.now();
      self.render(self.time);
      var cost = performance.now() - c0;
      slow = slow * 0.95 + (cost > 14 ? 0.05 : 0);    // a slow device draws every other frame instead of stuttering
      minGap = slow > 0.5 ? 30 : 0;
      if (!self.shown) self.onFirst();
    };
    requestAnimationFrame(tick);
    if ('IntersectionObserver' in window) new IntersectionObserver(function (es) { self.visible = es[0].isIntersecting; }).observe(this.cv);
    var rz; window.addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(function () { self.resize(); }, 120); });
  };
  Banner.prototype.pause = function (on) { this.paused = on === undefined ? !this.paused : !!on; return this.paused; };
  Banner.prototype.onFirst = function () { this.shown = true; this.cv.classList.add('ba-banner-on'); if (this.opts.onReady) this.opts.onReady(); };

  window.BABanner = {
    mount: function (canvas, opts) {
      var b = new Banner(canvas, opts);
      b.load().then(function () { b.start(); }).catch(function (e) { if (window.console) console.warn('banner:', e); if (opts && opts.onError) opts.onError(e); });
      return b;
    },
    _Banner: Banner
  };
})();
