/* Today's Play: one of today's games, four plays you draw like a real playbook.

   Play 1: the away team's offense against the home team's defense   Play 3: the home team's defense against the away offense
   Play 2: the home team's offense against the away team's defense   Play 4: the away team's defense against the home offense

   OFFENSE. The five starters are on the floor (their pictures, ringed in the team's colour; the ones you can move glow).
   Drag a player to where he goes, and when you let go pick what he does there:
     ball handler   Dribble here (zig-zag line)        Drive and shoot        Dribble and pull up
     off the ball   Cut here (arrow)   Spot up here   Set a screen for… (line ends in a T)   Screen and roll / Screen and pop
   Tap a player without dragging him for the actions that don't move him: the ball handler can Pass to… (dotted line),
   Hand off to…, or Shoot from here; anyone else can Set a screen for… from where he stands or Cut to the rim.
   Every action is numbered in the order you draw it. The play ends with a shot (if you don't call one, whoever has the
   ball at the end shoots).

   DEFENSE. The other team runs a set from its playbook (pick-and-roll, Spain pick-and-roll, Horns, floppy, post-up,
   isolation; picked from its personnel), drawn on the court. Drag your defenders to where they start and tap each to
   give him his job: guard tight, sag and help, switch screens, drop, hedge, trap the ball, or deny.

   HOW A PLAY IS SCORED. The play is run step by step against the defense. Every defender carries a "lag": how many feet
   behind his man he is. Cuts and drives build it (the players' speed and handle against the defender's), screens build
   it (how close the screen is to the man it's set for, how big the screener is, and the defense's coverage: a switch
   leaves a mismatch, a drop gives up the pull-up but guards the rim, a hedge or a trap leaves the roller open), help
   on a drive opens up the kick-out, a pass across the floor makes the defense shift. Passes can be picked off (longer,
   through defenders, by a worse passer), and the shot clock runs. The shot's chance comes from the shooter's Bradley
   ratings from that spot, how open he is, the rim protection and the spacing around him.
   Offense: your success rate is the chance the possession scores. Defense: the offense takes its best look at the end
   of its set; your success rate is the chance it doesn't score. Your score is the average of the four plays; your Off
   Rtg and Def Rtg are the points per 100 possessions your offense scores and your defense allows.
   This is a first version of the model, to be tuned. */
(function () {
  "use strict";
  var B = window.BAG, root = document.getElementById("tp-app");
  if (!B || !root) return;
  var NS = "http://www.w3.org/2000/svg", HOOP = [250, 52.5], FT = 10, W = 500, H = 470;
  var GAME = "todays-play", DAY = B.day(), MAX_STEPS = 9;
  // where the five start: 1 at the top, 2 on the right wing, 3 on the left wing, 4 in the right corner, 5 at the left block
  var START = [[250, 292], [425, 195], [75, 195], [462, 40], [168, 86]];
  var ROLES = [
    ["tight", "Guard tight", "Up on his man, no space"], ["sag", "Sag and help", "Off his man, helps on drives"],
    ["switch", "Switch screens", "Swaps men on every screen"], ["drop", "Drop", "Big drops back to guard the rim"],
    ["hedge", "Hedge", "Jumps out at the ball handler, recovers"], ["trap", "Trap the ball", "Doubles the ball on the screen"],
    ["deny", "Deny", "Takes away the pass to his man"]];
  var ROLE_SHORT = { tight: "TIGHT", sag: "SAG", "switch": "SWITCH", drop: "DROP", hedge: "HEDGE", trap: "TRAP", deny: "DENY" };

  // ------------------------------------------------------------ geometry
  function dist(a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1]); }
  function ft(a, b) { return dist(a, b) / FT; }
  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function lerp(a, b, k) { return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k]; }
  function unit(a, b) { var d = dist(a, b) || 1; return [(b[0] - a[0]) / d, (b[1] - a[1]) / d]; }
  function zone(p) {
    var r = ft(p, HOOP), corner = p[1] < 140 && (p[0] < 32 || p[0] > 468);
    if (r < 4.5) return "rim";
    if (corner || r >= 23.75) return "three";
    if (r < 10) return "paint";
    return "mid";
  }
  function threeSpot(p) {                                    // the nearest spot just behind the arc
    if (p[1] < 140) return [p[0] < 250 ? 18 : 482, Math.max(25, Math.min(130, p[1]))];
    var u = unit(HOOP, p); return [HOOP[0] + u[0] * 252, HOOP[1] + u[1] * 252];
  }
  function segDist(p, a, b) {                                // distance from p to the segment a-b
    var dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy || 1, t = clamp(((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L, 0, 1);
    return dist(p, [a[0] + t * dx, a[1] + t * dy]);
  }
  function plen(path) { var L = 0; for (var i = 1; i < path.length; i++) L += dist(path[i - 1], path[i]); return L / FT; }
  function simplify(path) {                                  // keep a dragged path light: about one point per 20 units
    var out = [path[0]];
    for (var i = 1; i < path.length - 1; i++) if (dist(out[out.length - 1], path[i]) >= 20) out.push(path[i]);
    out.push(path[path.length - 1]);
    return out.map(function (p) { return [Math.round(p[0]), Math.round(p[1])]; });
  }

  // ------------------------------------------------------------ players
  function R(p, k, d) { var v = p && p.r && p.r[k]; return v ? v : d; }
  function isBig(p) { return /C/.test(p.pos) || (/F/.test(p.pos) && (p.reb || 0) >= 7.5); }
  function attrs(p, rating) {                               // the ratings the model uses (from Bradley's, or from his stats)
    var r = rating || {}, s = function (k, f) { return r[k] || Math.round(f); };
    var big = isBig(p);
    return {
      "Three-Point Shot": s("Three-Point Shot", 45 + (p.tpp || 30) * 0.9 * Math.min(1, (p.tpa || 0) / 3 + 0.35)),
      "Mid-Range Shot": s("Mid-Range Shot", 50 + (p.fgp || 44) * 0.5), "Close Shot": s("Close Shot", 55 + (p.fgp || 45) * 0.5),
      "Driving Layup": s("Driving Layup", 50 + Math.min(35, (p.pts || 8) * 1.3)), "Ball Handle": s("Ball Handle", big ? 45 : 55 + (p.ast || 2) * 4),
      "Pass Vision": s("Pass Vision", 45 + (p.ast || 2) * 5), "Perimeter Defense": s("Perimeter Defense", big ? 55 : 62 + (p.stl || 0.8) * 8),
      "Interior Defense": s("Interior Defense", big ? 65 + (p.blk || 0.5) * 8 : 50), Block: s("Block", 35 + (p.blk || 0.4) * 22),
      Steal: s("Steal", 40 + (p.stl || 0.8) * 20), Speed: s("Speed", big ? 55 : 72), "Help Defense IQ": s("Help Defense IQ", 65),
      "Player Rating": s("Player Rating", 60 + Math.min(30, (p.pts || 5) + (p.reb || 2) * 0.5 + (p.ast || 1) * 0.6))
    };
  }
  function starters(players, ratings, tri) {
    var team = players.filter(function (p) { return p.team === tri && p.gp > 0; }).sort(function (a, b) { return b.min * Math.min(1, b.gp / 3) - a.min * Math.min(1, a.gp / 3); });
    var top = team.slice(0, 5);
    if (top.length < 5) return null;
    // order them 1-5: guards by assists, bigs last
    var score = function (p) { return (isBig(p) ? 20 : 0) + (/F/.test(p.pos) ? 8 : 0) - (p.ast || 0) * 1.5 + (p.reb || 0) * 0.6; };
    top.sort(function (a, b) { return score(a) - score(b); });
    return top.map(function (p, i) {
      var r = B.ratingFor(ratings, p);
      return { id: p.id, name: p.name, last: p.name.split(" ").slice(1).join(" ") || p.name, pos: p.pos, big: isBig(p), tri: tri, slot: i,
        img: B.face(p.id, 110), r: attrs(p, r), stat: p };
    });
  }
  function scheme(five, tri) {                              // how the CPU defends screens
    var big = five[4], perim = (R(five[0], "Perimeter Defense", 65) + R(five[1], "Perimeter Defense", 65) + R(five[2], "Perimeter Defense", 65)) / 3;
    if (R(big, "Block", 50) >= 72 || R(big, "Interior Defense", 60) >= 82) return { kind: "drop", label: "drop coverage, the big stays home at the rim" };
    if (perim >= 76 && R(big, "Speed", 55) >= 60) return { kind: "switch", label: "switching every screen" };
    if (R(big, "Speed", 55) >= 64) return { kind: "hedge", label: "hedging hard on the ball" };
    return { kind: "man", label: "fighting over screens, help from the weak side" };
  }

  // ------------------------------------------------------------ the CPU's playbook (for the defensive rounds)
  // each set: the steps, using the same actions you draw (1 = point guard ... 5 = center); `star` is their best scorer
  function playbook(five) {
    var bestI = 0; five.forEach(function (p, i) { if (R(p, "Player Rating", 0) > R(five[bestI], "Player Rating", 0)) bestI = i; });
    var star = five[bestI], sets = [];
    var shooters = five.map(function (p, i) { return [R(p, "Three-Point Shot", 50), i]; }).sort(function (a, b) { return b[0] - a[0]; });
    var s1 = shooters[0][1] === 0 ? shooters[1][1] : shooters[0][1];
    if (!star.big) {
      sets.push({ name: "High pick-and-roll", desc: star.last + " comes off a high screen from the 5, who rolls to the rim; the shooters spot up.",
        steps: bestI === 0 ? [
          { t: "screen", who: 4, path: [START[4], [210, 200], [268, 262]], for: 0, after: "roll", afterEnd: [262, 70] },
          { t: "dribble", who: 0, path: [START[0], [310, 250], [338, 188]] },
          { t: "move", who: 3, path: [START[3], [466, 70]], sub: "spot" }] :
          [{ t: "pass", who: 0, to: bestI }, { t: "screen", who: 4, path: [START[4], [170, 150], START[bestI][0] < 250 ? [START[bestI][0] + 34, START[bestI][1] + 10] : [START[bestI][0] - 34, START[bestI][1] + 10]], for: bestI, after: "roll", afterEnd: [252, 72] },
            { t: "dribble", who: bestI, path: [START[bestI], [250, 205], [228, 150]] }] });
      sets.push({ name: "Spain pick-and-roll", desc: "A pick-and-roll at the top, then a back screen on the roller's defender: the screener pops to the arc.",
        steps: [{ t: "screen", who: 4, path: [START[4], [215, 210], [266, 262]], for: 0, after: "roll", afterEnd: [252, 74] },
          { t: "screen", who: s1, path: [START[s1], [250, 196], [250, 118]], for: 4, after: "pop", afterEnd: [250, 300] },
          { t: "dribble", who: 0, path: [START[0], [318, 236], [332, 176]] }] });
      sets.push({ name: "Floppy", desc: "Their best shooter runs off staggered screens from the 4 and the 5 to catch it on the wing.",
        steps: [{ t: "move", who: s1, path: [START[s1], [250, 70]], sub: "cut" },
          { t: "screen", who: 4, path: [START[4], [205, 110]], for: s1 },
          { t: "screen", who: 3, path: [START[3], [300, 108]], for: s1 },
          { t: "move", who: s1, path: [[250, 70], [96, 160], [70, 200]], sub: "cut" },
          { t: "pass", who: 0, to: s1 }] });
    } else {
      sets.push({ name: "Post-up", desc: star.last + " seals his man on the block; the guards space the floor for the kick-out.",
        steps: [{ t: "move", who: bestI, path: [START[bestI], [190, 110], [178, 92]], sub: "cut" },
          { t: "pass", who: 0, to: bestI === 0 ? 1 : 0 }, { t: "move", who: 2, path: [START[2], [24, 50]], sub: "spot" },
          { t: "pass", who: bestI === 0 ? 1 : 0, to: bestI }, { t: "dribble", who: bestI, path: [[178, 92], [214, 74]] }] });
      sets.push({ name: "Horns", desc: "Both bigs at the elbows; the 4 sets the screen and pops while " + star.last + " rolls hard.",
        steps: [{ t: "move", who: 4, path: [START[4], [192, 196]], sub: "cut" }, { t: "move", who: 3, path: [START[3], [308, 196]], sub: "cut" },
          { t: "screen", who: 3, path: [[308, 196], [270, 254]], for: 0, after: "pop", afterEnd: [362, 238] },
          { t: "dribble", who: 0, path: [START[0], [205, 245], [176, 186]] },
          { t: "move", who: 4, path: [[192, 196], [236, 70]], sub: "cut" }] });
    }
    sets.push({ name: "Isolation", desc: "Everyone clears to the corners and wings; " + star.last + " takes his man one-on-one.",
      steps: (bestI === 0 ? [] : [{ t: "pass", who: 0, to: bestI }]).concat([
        { t: "move", who: bestI === 3 ? 4 : 3, path: [START[bestI === 3 ? 4 : 3], [470, 30]], sub: "spot" },
        { t: "dribble", who: bestI, path: [START[bestI], lerp(START[bestI], HOOP, 0.45), lerp(START[bestI], HOOP, 0.72)] }]) });
    return sets;
  }

  // ------------------------------------------------------------ the simulation
  // st: { pos: offense positions, guard: guard[i] = defender on offense i, lag: lag[i] (ft) of the man on i, ball,
  //       clock, risk (chance of a turnover so far), rim: rim protector index or -1, help: helper index, notes[] }
  function newState(off, defn, roles, kind) {
    return { pos: off.map(function (p) { return p.at.slice(); }), dpos: defn.map(function (d) { return d.at.slice(); }),
      guard: [0, 1, 2, 3, 4], lag: [0, 0, 0, 0, 0], ball: 0, clock: 4, risk: 0, notes: [], roles: roles, kind: kind, trapped: -1, switched: false };
  }
  function roleOf(st, d) { return st.roles ? st.roles[d] : (st.kind === "drop" && d === 4 ? "drop" : st.kind === "switch" ? "switch" : st.kind === "hedge" ? "hedge" : "man"); }
  function startLag(st, off, defn) {                         // where you put your defenders before the play: off position = lag
    off.forEach(function (o, i) {
      var d = st.guard[i], ideal = lerp(st.pos[i], HOOP, 4.4 * FT / Math.max(dist(st.pos[i], HOOP), 1)), gap = ft(st.dpos[d], ideal);
      var role = roleOf(st, d);
      st.lag[i] = Math.max(0, gap - (role === "sag" ? 6 : 2.5)) * 0.55 + (role === "sag" ? 1.2 : 0) + (role === "tight" || role === "deny" ? -0.8 : 0);
    });
  }
  function moveBuild(o, d, distFt, toward, handle) {         // feet a mover gains on his defender
    var quick = (R(o, "Speed", 70) - R(d, "Speed", 65)) / 22, skill = handle ? (R(o, "Ball Handle", 60) - R(d, "Perimeter Defense", 65)) / 18 : 0;
    return clamp(distFt * 0.1 + quick + skill + (toward ? 1.2 : 0), -1, 6);
  }
  function step(st, a, off, defn) {
    var i = a.who, d = st.guard[i], o = off[i], dd = defn[d], role = roleOf(st, d);
    if (a.t === "move" || a.t === "dribble") {
      var from = st.pos[i], end = a.path[a.path.length - 1], L = plen(a.path), toward = ft(end, HOOP) < ft(from, HOOP) - 4;
      var g = moveBuild(o, dd, L, toward, a.t === "dribble");
      if (role === "tight" || role === "deny") g *= 0.7;
      if (role === "sag" && a.t === "move" && !toward) g += 1;
      st.lag[i] = clamp(st.lag[i] + g, -2, 12);
      st.pos[i] = end;
      st.clock += a.t === "dribble" ? 1.2 + L / 9 : 0.8 + L / 14;
      if (a.t === "dribble" && ft(end, HOOP) < 13) {         // a drive draws help: the nearest helper leaves his man
        var best = -1, bd = 1e9;
        for (var k = 0; k < 5; k++) if (k !== i) { var dk = st.guard[k], h = dist(defPos(st, k), end) + (roleOf(st, dk) === "sag" ? -60 : 0); if (h < bd) { bd = h; best = k; } }
        if (best >= 0) { st.lag[best] += 3.5 + R(defn[st.guard[best]], "Help Defense IQ", 65) / 60; st.lag[i] = Math.max(-1, st.lag[i] - 2.5); st.helpOn = best; st.notes.push(o.last + "'s drive pulls help off " + off[best].last); }
      }
      if (a.t === "dribble") st.risk += clamp(0.012 + (65 - R(o, "Ball Handle", 60)) / 900 + (st.trapped === i ? 0.05 : 0), 0.003, 0.08);
    } else if (a.t === "screen") {
      var j = a.for, spot = a.path[a.path.length - 1], q = clamp(1 - ft(spot, st.pos[j]) / 10, 0, 1);
      st.pos[i] = spot; st.clock += 1 + plen(a.path) / 14;
      if (q <= 0.05) { st.notes.push(o.last + "'s screen is too far from " + off[j].last + " to hit anyone"); }
      else {
        var size = (o.big ? 1.2 : 0.85), cov = roleOf(st, st.guard[i]), dj = st.guard[j];
        if (cov === "switch" || roleOf(st, dj) === "switch") {
          st.guard[j] = st.guard[i]; st.guard[i] = dj; st.lag[j] = 0.8 * q; st.lag[i] = 0.6 * q; st.switched = true;
          st.notes.push("They switch: " + defn[st.guard[j]].last + " now guards " + off[j].last);
        } else if (cov === "drop") { st.lag[j] += 4.2 * q * size; st.lag[i] += a.after === "pop" ? 6 * q : 0.8 * q; st.rimHold = st.guard[i]; st.notes.push("The big drops: space for a pull-up" + (a.after === "pop" ? ", and the popper is open" : "")); }
        else if (cov === "hedge") { st.lag[j] += 1.4 * q; st.lag[i] += 4.5 * q * size; st.notes.push("A hard hedge: the screener slips free"); }
        else if (cov === "trap") { st.lag[j] = -3; st.trapped = j; st.lag[i] += 7.5 * q * size; var w = (i + 2) % 5 === j ? (i + 3) % 5 : (i + 2) % 5; st.lag[w] += 2.5; st.notes.push("They trap " + off[j].last + ": the screener is wide open behind it"); }
        else { st.lag[j] += 3.2 * q * size; st.lag[i] += 1.5 * q; st.notes.push(o.last + "'s screen frees " + off[j].last); }
        if (a.after) {
          var ae = a.afterEnd || (a.after === "roll" ? [HOOP[0] + (spot[0] - HOOP[0]) * 0.18, HOOP[1] + 28] : threeSpot(spot));
          st.pos[i] = ae; st.lag[i] += a.after === "roll" ? 1.2 : 0.8; st.clock += 1.4;
        }
      }
    } else if (a.t === "pass" || a.t === "dho") {
      var to = a.to, A = st.pos[i], Bp = st.pos[to], len = ft(A, Bp), lane = 0;
      for (var m = 0; m < 5; m++) { var dp = defPos(st, m); if (m !== i && m !== to && segDist(dp, A, Bp) < 3.5 * FT) lane++; }
      var rcvDef = st.guard[to], deny = roleOf(st, rcvDef) === "deny" && st.lag[to] < 2;
      var risk = a.t === "dho" ? 0.008 : 0.01 + len / 30 * 0.035 + lane * 0.045 + (deny ? 0.06 : 0) + (st.trapped === i ? 0.05 : 0);
      risk *= 1.25 - R(o, "Pass Vision", 65) / 160;
      st.risk += clamp(risk, 0.004, 0.25);
      if (a.t === "dho") { st.pos[to] = lerp(A, Bp, 0.15); st.lag[to] += 2.4 * (off[i].big ? 1.15 : 0.9); st.notes.push(o.last + " hands it off to " + off[to].last); }
      else {
        st.lag[to] = Math.max(st.lag[to] - len / 18, st.lag[to] * 0.7);   // the defender closes out while the ball is in the air
        if ((A[0] - 250) * (Bp[0] - 250) < 0) for (var n = 0; n < 5; n++) if (n !== to) st.lag[n] += 0.5;   // a swing makes everyone shift
        if (st.helpOn === to) st.notes.push("The kick-out finds " + off[to].last + " where the help came from");
      }
      st.helpOn = -1; st.trapped = -1; st.ball = to; st.clock += 1;
    }
  }
  function defPos(st, i) {                                   // where the man guarding offense i stands (for drawing and lanes)
    var p = st.pos[i], d = st.guard[i], role = roleOf(st, d), u = unit(p, HOOP), lag = st.lag[i];
    if (st.rimHold === d) return [HOOP[0] + (p[0] - HOOP[0]) * 0.25, HOOP[1] + 55];
    var off = (role === "sag" && st.ball !== i ? 9 : 4.4) + Math.max(0, lag);
    var base = [p[0] + u[0] * Math.min(off, ft(p, HOOP) - 1) * FT, p[1] + u[1] * Math.min(off, ft(p, HOOP) - 1) * FT];
    if (lag > 2.5) { var side = [u[1], -u[0]]; base = [base[0] + side[0] * lag * 3, base[1] + side[1] * lag * 3]; }
    return [clamp(base[0], 12, 488), clamp(base[1], 12, 458)];
  }
  function makeChance(o, z) {
    var f = function (v, lo, hi) { return lo + clamp((v - 25) / 74, 0, 1) * (hi - lo); };
    if (z === "three") return f(R(o, "Three-Point Shot", 60), 0.2, 0.45);
    if (z === "rim") return f(Math.max(R(o, "Driving Layup", 60), R(o, "Close Shot", 60)), 0.5, 0.8);
    if (z === "paint") return f(R(o, "Close Shot", 60), 0.36, 0.6);
    return f(R(o, "Mid-Range Shot", 60), 0.3, 0.5);
  }
  function shot(st, i, off, defn) {                          // the chance the possession scores if i shoots now
    var spot = st.pos[i], z = zone(spot), d = defn[st.guard[i]], o = off[i];
    var base = makeChance(o, z), lag = st.lag[i] + (roleOf(st, st.guard[i]) === "sag" && z === "three" ? 2.5 : 0);
    var open = clamp((3 + lag - 2) / 6, 0, 1);
    var dq = (z === "three" || z === "mid" ? R(d, "Perimeter Defense", 65) : R(d, "Interior Defense", 60)) - 65;
    var size = (z === "rim" || z === "paint") && !d.big && o.big ? 0.06 : (z !== "rim" && d.big && !o.big && st.switched ? 0.05 : 0);
    var p = base * (0.62 + 0.45 * open) - (1 - open) * dq / 350 + size;
    if (st.trapped === i) p *= 0.55;
    if (z === "rim" || z === "paint") {                      // rim protection: the best shot blocker near the rim
      var prot = 0;
      for (var k = 0; k < 5; k++) { var dk = st.guard[k]; if (dk === st.guard[i]) continue; var dp = defPos(st, k); if (ft(dp, HOOP) < 11 || st.rimHold === dk) prot = Math.max(prot, R(defn[dk], "Block", 45)); }
      p -= prot / 100 * 0.14;
    }
    var crowd = 0; for (var a = 0; a < 5; a++) if (a !== i) for (var b = a + 1; b < 5; b++) if (b !== i && ft(st.pos[a], st.pos[b]) < 7) crowd++;
    p -= crowd * 0.025;
    if (st.clock > 24) return { p: 0, z: z, open: 3 + lag, violation: true };
    p = clamp(p, 0.04, 0.88) * (1 - clamp(st.risk, 0, 0.6));
    return { p: p, z: z, pts: z === "three" ? 3 : 2, open: Math.max(0, 3 + lag) };
  }
  function run(steps, off, defn, opts) {
    var st = newState(off, defn, opts.roles, opts.kind);
    if (opts.roles) startLag(st, off, defn);
    var frames = [snap(st)];
    steps.forEach(function (a) {
      if (a.t === "shoot") return;
      var clock0 = st.clock;
      step(st, a, off, defn);
      var f = snap(st), path = a.t === "move" || a.t === "dribble" ? a.path : a.t === "screen" ? a.path.concat(a.after ? [st.pos[a.who]] : []) : null;
      if (a.with && frames.length > 1) {                      // at the same time as the action before it
        st.clock = Math.max(clock0, clock0 + (st.clock - clock0) * 0.25);
        var prev = frames[frames.length - 1]; f.paths = prev.paths || {}; frames[frames.length - 1] = f;
      } else { f.paths = {}; frames.push(f); }
      if (path && path.length > 1) f.paths[a.who] = path;
      if (a.t === "pass" || a.t === "dho") f.pass = [a.who, a.to];
    });
    var shooter = st.ball, last = steps[steps.length - 1];
    if (last && last.t === "shoot") shooter = last.who;
    var res = shot(st, shooter, off, defn);
    if (opts.best) {                                        // the CPU offense: shoot, or one more pass to the open man
      var base = st, pick = null;
      for (var k = 0; k < 5; k++) if (k !== base.ball) {
        var copy = JSON.parse(JSON.stringify(base)); step(copy, { t: "pass", who: base.ball, to: k }, off, defn);
        var r2 = shot(copy, k, off, defn);
        if (r2.p * (r2.pts || 2) > res.p * (res.pts || 2)) { res = r2; shooter = k; res.extraPass = true; pick = copy; }
      }
      if (pick) { frames.push(snap(pick)); st = pick; }
    }
    res.shooter = shooter; res.notes = st.notes; res.risk = st.risk; res.clock = st.clock;
    return { res: res, frames: frames };
  }
  function snap(st) { return { pos: st.pos.map(function (p) { return p.slice(); }), def: [0, 1, 2, 3, 4].map(function (i) { return { d: st.guard[i], at: defPos(st, i) }; }), ball: st.ball }; }

  // ------------------------------------------------------------ drawing
  function el(tag, a, parent) { var e = document.createElementNS(NS, tag); for (var k in a) e.setAttribute(k, a[k]); if (parent) parent.appendChild(e); return e; }
  var uid = 0;
  function court(svg) {
    var defs = el("defs", {}, svg);
    [["tpA", "#F4F1EA"], ["tpG", "#F5D370"], ["tpC", "#9fd3ff"]].forEach(function (m) {
      var mk = el("marker", { id: m[0], viewBox: "0 0 10 10", refX: 7, refY: 5, markerWidth: 5, markerHeight: 5, orient: "auto-start-reverse" }, defs);
      el("path", { d: "M0 0 L10 5 L0 10 z", fill: m[1] }, mk);
    });
    // a see-through parquet floor in very dark greys: squares of five planks, each square turned against its neighbours
    var pid = "tpPq" + (++uid), pat = el("pattern", { id: pid, width: 50, height: 50, patternUnits: "userSpaceOnUse" }, defs);
    var tones = ["rgba(38,38,38,.55)", "rgba(46,46,46,.55)", "rgba(33,33,33,.55)", "rgba(50,50,50,.55)", "rgba(42,42,42,.55)"];
    [[0, 0, 0], [25, 0, 1], [0, 25, 1], [25, 25, 0]].forEach(function (q) {
      for (var k = 0; k < 5; k++) {
        var r = q[2] ? { x: q[0], y: q[1] + k * 5, width: 25, height: 5 } : { x: q[0] + k * 5, y: q[1], width: 5, height: 25 };
        r.fill = tones[(k + q[0] / 25 + q[1] / 25 * 2) % 5]; r.stroke = "rgba(0,0,0,.45)"; r["stroke-width"] = 0.6;
        el("rect", r, pat);
      }
    });
    var g = el("g", { fill: "none", stroke: "rgba(240,232,214,.62)", "stroke-width": 2 }, svg);
    el("rect", { x: 0, y: 0, width: W, height: H, fill: "url(#" + pid + ")", stroke: "none" }, g);
    el("rect", { x: 2, y: 2, width: W - 4, height: H - 4 }, g);
    el("rect", { x: 170, y: 2, width: 160, height: 188, fill: "rgba(28,28,28,.5)" }, g);
    el("circle", { cx: 250, cy: 190, r: 60 }, g);
    el("path", { d: "M30 2 V140 A237.5 237.5 0 0 0 470 140 V2" }, g);
    el("path", { d: "M210 52.5 A40 40 0 0 0 290 52.5" }, g);
    el("line", { x1: 220, y1: 40, x2: 280, y2: 40, stroke: "#e8e2d4", "stroke-width": 3 }, g);
    el("circle", { cx: HOOP[0], cy: HOOP[1], r: 7.5, stroke: "#ff6a2e", "stroke-width": 2.5 }, g);
    el("path", { d: "M190 470 A60 60 0 0 1 310 470" }, g);
    return defs;
  }
  function along(pts, e) {                                   // the point a share e of the way along a path
    var L = 0, s = [], i; for (i = 1; i < pts.length; i++) { s.push(dist(pts[i - 1], pts[i])); L += s[i - 1]; }
    var want = L * e; for (i = 0; i < s.length; i++) { if (want <= s[i]) return lerp(pts[i], pts[i + 1], s[i] ? want / s[i] : 0); want -= s[i]; }
    return pts[pts.length - 1].slice();
  }
  function pd(pts) { return pts.map(function (p, i) { return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" "); }
  function zig(pts) {                                        // a dribble: the path as a zig-zag
    var out = [pts[0]], amp = 6, wl = 14;
    for (var i = 1; i < pts.length; i++) {
      var a = pts[i - 1], b = pts[i], L = dist(a, b), u = unit(a, b), n = [-u[1], u[0]], k = Math.max(1, Math.floor(L / wl));
      for (var j = 1; j <= k; j++) { var t = j / k, s = (j === k && i === pts.length - 1) ? 0 : (j % 2 ? amp : -amp); out.push([a[0] + (b[0] - a[0]) * t + n[0] * s, a[1] + (b[1] - a[1]) * t + n[1] * s]); }
    }
    return out;
  }
  function trim(pts, r) {                                    // stop a line short of the token at its end
    var a = pts[pts.length - 2] || pts[0], b = pts[pts.length - 1], L = dist(a, b);
    if (L < r + 2) return pts;
    var u = unit(a, b); return pts.slice(0, -1).concat([[b[0] - u[0] * r, b[1] - u[1] * r]]);
  }
  function badge(g, at, n) { var c = el("g", { transform: "translate(" + at[0].toFixed(1) + "," + at[1].toFixed(1) + ")" }, g); el("circle", { r: 8, fill: "#0e0d0b", stroke: "#F5D370", "stroke-width": 1.5 }, c); var t = el("text", { y: 3.6, "text-anchor": "middle", "font-size": 10, "font-weight": 700, fill: "#F5D370", "font-family": "Arial, sans-serif" }, c); t.textContent = n; }
  function mid(pts) { var L = 0, s = []; for (var i = 1; i < pts.length; i++) { var d = dist(pts[i - 1], pts[i]); s.push(d); L += d; } var want = L / 2; for (var j = 0; j < s.length; j++) { if (want <= s[j]) return lerp(pts[j], pts[j + 1], s[j] ? want / s[j] : 0); want -= s[j]; } return pts[pts.length - 1]; }
  // draws the steps (with where everyone is before each step) in playbook notation
  function drawSteps(g, steps, startPos, color) {
    var pos = startPos.map(function (p) { return p.slice(); }), ball = 0, white = color || "#F4F1EA", mk = color === "#9fd3ff" ? "url(#tpC)" : "url(#tpA)";
    var nums = [], c0 = 0; steps.forEach(function (a, k) { if (!(a.with && k)) c0++; nums.push(c0 - 1); });
    steps.forEach(function (a, n0) {
      var n = nums[n0];
      var line;
      if (a.t === "move" || a.t === "dribble") {
        var pts = trim(a.path, 6);
        line = el("path", { d: pd(a.t === "dribble" ? zig(pts) : pts), stroke: white, "stroke-width": 2.6, fill: "none", "marker-end": mk, "stroke-linejoin": "round", "stroke-linecap": "round" }, g);
        if (a.sub === "spot") { var e = a.path[a.path.length - 1]; el("circle", { cx: e[0], cy: e[1], r: 25, fill: "none", stroke: white, "stroke-width": 1.2, "stroke-dasharray": "3 4", opacity: 0.6 }, g); }
        pos[a.who] = a.path[a.path.length - 1];
        badge(g, mid(a.path), n + 1);
      } else if (a.t === "screen") {
        var sp = a.path[a.path.length - 1], prev = a.path.length > 1 ? a.path[a.path.length - 2] : pos[a.who];
        if (a.path.length > 1 && dist(a.path[0], sp) > 4) el("path", { d: pd(a.path), stroke: white, "stroke-width": 2.6, fill: "none", "stroke-linecap": "round" }, g);
        var u = dist(prev, sp) > 3 ? unit(prev, sp) : unit(sp, pos[a.for]), n2 = [-u[1], u[0]];
        el("line", { x1: sp[0] + n2[0] * 13, y1: sp[1] + n2[1] * 13, x2: sp[0] - n2[0] * 13, y2: sp[1] - n2[1] * 13, stroke: white, "stroke-width": 4, "stroke-linecap": "round" }, g);
        if (a.after) {
          var ae = a.afterEnd || (a.after === "roll" ? [HOOP[0] + (sp[0] - HOOP[0]) * 0.18, HOOP[1] + 28] : threeSpot(sp));
          el("path", { d: pd(trim([sp, ae], 6)), stroke: white, "stroke-width": 2.2, fill: "none", "marker-end": mk, "stroke-dasharray": a.after === "pop" ? "1 0" : "1 0" }, g);
          var lab = el("text", { x: ae[0], y: ae[1] - 10, "text-anchor": "middle", "font-size": 10, "font-weight": 700, fill: white, "font-family": "Arial, sans-serif", opacity: 0.75 }, g); lab.textContent = a.after === "roll" ? "ROLL" : "POP";
          pos[a.who] = ae;
        } else pos[a.who] = sp;
        badge(g, a.path.length > 1 && dist(a.path[0], sp) > 30 ? mid(a.path) : [sp[0] + u[0] * -16, sp[1] + u[1] * -16], n + 1);
      } else if (a.t === "pass" || a.t === "dho") {
        var A = pos[a.who], Bq = pos[a.to], seg = trim([A, Bq], 24).slice(-2);
        seg[0] = lerp(A, Bq, 24 / Math.max(dist(A, Bq), 1));
        el("path", { d: pd(seg), stroke: a.t === "pass" ? "#F5D370" : white, "stroke-width": 2.4, fill: "none", "marker-end": a.t === "pass" ? "url(#tpG)" : mk, "stroke-dasharray": a.t === "pass" ? "2 7" : "none", "stroke-linecap": "round" }, g);
        if (a.t === "dho") { var m2 = mid(seg), uu = unit(A, Bq), nn = [-uu[1], uu[0]]; [-4, 4].forEach(function (o) { el("line", { x1: m2[0] + uu[0] * o + nn[0] * 7, y1: m2[1] + uu[1] * o + nn[1] * 7, x2: m2[0] + uu[0] * o - nn[0] * 7, y2: m2[1] + uu[1] * o - nn[1] * 7, stroke: white, "stroke-width": 2 }, g); }); }
        if (a.t === "dho") pos[a.to] = lerp(A, Bq, 0.15);
        ball = a.to;
        badge(g, lerp(mid(seg), [mid(seg)[0] + 10, mid(seg)[1] - 10], 1), n + 1);
      } else if (a.t === "shoot") {
        var sp2 = pos[a.who], c = el("g", { transform: "translate(" + sp2[0] + "," + sp2[1] + ")" }, g);
        el("circle", { r: 29, fill: "none", stroke: "#F5D370", "stroke-width": 2, "stroke-dasharray": "4 3" }, c);
        var tx = el("text", { y: -33, "text-anchor": "middle", "font-size": 10, "font-weight": 700, fill: "#F5D370", "font-family": "Arial, sans-serif" }, c); tx.textContent = "SHOT · " + (n + 1);
      }
    });
    return { pos: pos, ball: ball };
  }
  // a player: his picture in a circle ringed in his team's colour (see-through inside); glowing when it's yours to move
  function token(g, p, at, color, opts) {
    var id = "tpc" + (++uid), t = el("g", { class: "tp-tok" + (opts.mine ? " mine" : "") + (opts.def ? " def" : ""), transform: "translate(" + at[0] + "," + at[1] + ")" }, g);
    var s = opts.def ? el("g", { transform: "scale(.8)" }, t) : t;
    var cp = el("clipPath", { id: id }, s); el("circle", { r: 18.5 }, cp);
    el("circle", { r: 19.5, fill: "rgba(10,10,10,.18)" }, s);
    var im = el("image", { href: p.img, x: -24, y: -19, width: 48, height: 35, "clip-path": "url(#" + id + ")", preserveAspectRatio: "xMidYMin slice" }, s);
    im.setAttributeNS("http://www.w3.org/1999/xlink", "href", p.img);
    el("circle", { r: 20, fill: "none", stroke: color, "stroke-width": 3.4, class: "tp-ring" + (opts.mine ? " tp-glow" : ""), style: "color:" + color }, s);
    var nm = el("text", { y: opts.def ? -21 : 32, "text-anchor": "middle", "font-size": opts.def ? 9 : 10.5, "font-weight": 700, fill: opts.def ? "#d9d3c6" : "#F4F1EA", "font-family": "Arial, sans-serif", "paint-order": "stroke", stroke: "#0b0b0b", "stroke-width": 3 }, t);
    nm.textContent = p.last.length > 12 ? p.last.slice(0, 11) + "." : p.last;
    if (opts.role) { var rl = el("text", { y: 27, "text-anchor": "middle", "font-size": 8.5, "font-weight": 700, fill: "#F5D370", "font-family": "Arial, sans-serif", "letter-spacing": ".06em", "paint-order": "stroke", stroke: "#0b0b0b", "stroke-width": 3 }, t); rl.textContent = opts.role; }
    return t;
  }
  function ballAt(g) { var b = el("g", { class: "tp-ball" }, g); el("circle", { r: 7, fill: "#e07a2a", stroke: "#2a1608", "stroke-width": 1.2 }, b); el("path", { d: "M-7 0H7M0-7V7", stroke: "#2a1608", "stroke-width": 1 }, b); return b; }
  function place(n, p) { n.setAttribute("transform", "translate(" + p[0].toFixed(1) + "," + p[1].toFixed(1) + ")"); }

  // ------------------------------------------------------------ the game of the day
  var game = null, games = [], five = {}, state = null, allPlayers = [], allRatings = [];
  // the day's games (today's, or the nearest day with games): every one can be played; one is the game of the day
  function pickGames() {
    var tries = [0, 1, 2, 3, 4, 5, 6, -1, -2, -3, -4, -5, -6, -7];
    function next(i) {
      if (i >= tries.length) return Promise.resolve([]);
      var d = B.day(tries[i]);
      return B.scoreboard(d).then(function (sb) {
        var ev = sb.events || []; if (!ev.length) return next(i + 1);
        var star = Math.floor(B.seeded("tp" + DAY)() * ev.length);
        return ev.map(function (e, k) {
          var comp = e.competitions[0], t = function (w) { return comp.competitors.filter(function (x) { return x.homeAway === w; })[0].team.abbreviation; };
          var st = (comp.status || {}).type || {};
          return { id: String(e.id), day: d, away: t("away"), home: t("home"), when: comp.date, star: k === star, status: st.state === "pre" ? B.time ? B.time(comp.date) : "" : st.shortDetail || "" };
        });
      }).catch(function () { return next(i + 1); });
    }
    return next(0);
  }
  function key() { return "tp2:" + DAY + ":" + game.id; }
  function rounds() {
    var A = game.away, Hm = game.home;
    return [{ off: A, def: Hm, mode: "off" }, { off: Hm, def: A, mode: "off" }, { off: A, def: Hm, mode: "def" }, { off: Hm, def: A, mode: "def" }];
  }
  function legend() {
    var arrow = function (c) { return '<path d="M48 2l9 5-9 5z" fill="' + c + '"/>'; };
    return '<div class="tp-legend" aria-label="What the lines mean">' +
      '<span><svg viewBox="0 0 60 14"><path d="M2 7H50" stroke="#F4F1EA" stroke-width="2.4"/>' + arrow("#F4F1EA") + "</svg>Cut / move</span>" +
      '<span><svg viewBox="0 0 60 14"><path d="M2 7l6-5 6 10 6-10 6 10 6-10 6 10 6-5" stroke="#F4F1EA" stroke-width="2" fill="none"/>' + arrow("#F4F1EA") + "</svg>Dribble</span>" +
      '<span><svg viewBox="0 0 60 14"><path d="M2 7H48" stroke="#F5D370" stroke-width="2.4" stroke-dasharray="2 6" stroke-linecap="round"/>' + arrow("#F5D370") + "</svg>Pass</span>" +
      '<span><svg viewBox="0 0 60 14"><path d="M2 7H52" stroke="#F4F1EA" stroke-width="2.4"/><path d="M53 0V14" stroke="#F4F1EA" stroke-width="4"/></svg>Screen</span>' +
      '<span><svg viewBox="0 0 60 14"><path d="M2 7H48" stroke="#F4F1EA" stroke-width="2.4"/><path d="M22 1V13M28 1V13" stroke="#F4F1EA" stroke-width="2"/>' + arrow("#F4F1EA") + "</svg>Hand-off</span>" +
      '<span><svg viewBox="0 0 60 14"><circle cx="30" cy="7" r="6" fill="none" stroke="#F4F1EA" stroke-width="1.4" stroke-dasharray="2 3"/></svg>Spot up</span>' +
      '<span><svg viewBox="0 0 60 14"><circle cx="30" cy="7" r="6" fill="none" stroke="#F5D370" stroke-width="2" stroke-dasharray="3 2"/></svg>Shot</span>' +
      '<span><svg viewBox="0 0 60 14"><circle cx="30" cy="7" r="6.5" fill="#0e0d0b" stroke="#F5D370" stroke-width="1.4"/><text x="30" y="10" text-anchor="middle" font-size="9" font-weight="700" fill="#F5D370" font-family="Arial">2</text></svg>Order</span></div>';
  }
  function teamTag(tri) { return '<span class="tp-team"><img alt="" src="' + B.esc(B.logo(tri)) + '">' + B.esc(B.names[tri] || tri) + "</span>"; }
  function nick(tri) { return (B.names[tri] || tri).split(" ").pop(); }
  function start() {
    root.innerHTML = '<p class="gm-empty">Loading today&rsquo;s games…</p>';
    Promise.all([pickGames(), B.players(), B.ratings().catch(function () { return []; })]).then(function (r) {
      games = r[0]; allPlayers = r[1]; allRatings = r[2];
      if (!games.length) { root.innerHTML = '<p class="gm-empty">No games to play right now. Check back on the next game day.</p>'; return; }
      var want = /[?&]game=(\d+)/.exec(location.search);
      choose((want && games.filter(function (g) { return g.id === want[1]; })[0]) || games.filter(function (g) { return g.star; })[0] || games[0]);
    }).catch(function () { root.innerHTML = '<p class="gm-empty">Couldn&rsquo;t load today&rsquo;s games right now.</p>'; });
  }
  function choose(g) {
    game = g;
    five[game.away] = starters(allPlayers, allRatings, game.away); five[game.home] = starters(allPlayers, allRatings, game.home);
    if (five[game.away] && five[game.home]) B.preload(five[game.away].concat(five[game.home]).map(function (p) { return p.img; }));
    intro(); showGameBoard();
  }
  function intro() {
    var done = B.store(key()), ready = five[game.away] && five[game.home];
    var pickList = '<div class="tp-games" role="listbox" aria-label="Pick a game">' + games.map(function (g) {
      var mine = B.store("tp2:" + DAY + ":" + g.id);
      return '<button type="button" class="tp-g' + (g.id === game.id ? " on" : "") + '" role="option" aria-selected="' + (g.id === game.id) + '" data-id="' + g.id + '">' +
        '<span class="tp-g-t"><img alt="" src="' + B.esc(B.logo(g.away)) + '"><b>' + B.esc(g.away) + '</b><i>at</i><img alt="" src="' + B.esc(B.logo(g.home)) + '"><b>' + B.esc(g.home) + "</b></span>" +
        '<span class="tp-g-s">' + (g.star ? '<em>Game of the day</em>' : "") + (mine ? "<strong>" + mine.total.toFixed(1) + "%</strong>" : "") + "</span></button>";
    }).join("") + "</div>";
    root.innerHTML = '<div class="tp-pick-h"><span class="gm-k">' + B.esc(B.niceDay(game.day)) + "&rsquo;s games</span><span class=\"tp-pick-n\">Pick any game to draw four plays for</span></div>" + pickList +
      '<div class="tp-head"><div class="tp-matchup">' + teamTag(game.away) + '<span class="tp-at">at</span>' + teamTag(game.home) + "</div></div>" +
      '<ol class="tp-steps">' + rounds().map(function (r, i) {
        return "<li><b>Play " + (i + 1) + "</b> " + (r.mode === "off" ? "Draw the " + B.esc(nick(r.off)) + "&rsquo; offense against the " + B.esc(nick(r.def)) + "&rsquo; defense" : "Set the " + B.esc(nick(r.def)) + "&rsquo; defense against the " + B.esc(nick(r.off)) + "&rsquo; offense") + "</li>";
      }).join("") + "</ol>" +
      legend() +
      (ready ? '<div class="gm-row"><button type="button" class="gm-btn tp-go">' + (done ? "Play again" : "Start drawing") + "</button>" +
      (done ? '<span class="gm-note">Your best for this game: <b>' + done.total.toFixed(1) + "%</b></span>" : "") + "</div>"
        : '<p class="gm-empty">This game&rsquo;s rosters aren&rsquo;t in yet. Pick another game.</p>');
    root.querySelectorAll(".tp-g").forEach(function (b) {
      b.addEventListener("click", function () { var g = games.filter(function (x) { return x.id === b.getAttribute("data-id"); })[0]; if (g && g.id !== game.id) choose(g); });
    });
    var go = root.querySelector(".tp-go");
    if (go) go.addEventListener("click", function () { state = { round: 0, results: [], plays: [] }; round(); });
  }

  // ------------------------------------------------------------ one play
  function round() {
    var Rd = rounds()[state.round], off = five[Rd.off], dfn = five[Rd.def], mine = Rd.mode;
    var offColor = B.colors[Rd.off] || "#D4AF37", defColor = B.colors[Rd.def] || "#cfc8ba";
    var sch = scheme(dfn, Rd.def), cpuSet = null, steps = [], roles = ["tight", "tight", "tight", "tight", "tight"];
    var offAt = START.map(function (p) { return p.slice(); });
    var defAt = START.map(function (p) { return lerp(p, HOOP, 4.4 * FT / dist(p, HOOP)); });
    if (mine === "def") {
      var sets = playbook(off); cpuSet = sets[Math.floor(B.seeded("tps" + DAY + state.round)() * sets.length)];
      steps = cpuSet.steps; roles = dfn.map(function (p) { return p.big ? "drop" : "tight"; });
    } else {                                                 // the CPU defense sags off the worst shooter
      var worst = 0; off.forEach(function (p, i) { if (R(p, "Three-Point Shot", 50) < R(off[worst], "Three-Point Shot", 50)) worst = i; });
      if (R(off[worst], "Three-Point Shot", 50) < 62) defAt[worst] = lerp(offAt[worst], HOOP, 0.45);
    }
    var history = [], ran = false, lastOut = null;
    root.innerHTML = '<div class="tp-bar"><span class="tp-round">Play ' + (state.round + 1) + " of 4</span>" +
      '<h3 class="tp-title">' + (mine === "off" ? "Draw the " + B.esc(nick(Rd.off)) + "&rsquo; offense" : "Set the " + B.esc(nick(Rd.def)) + "&rsquo; defense") + "</h3>" +
      '<span class="tp-vs">' + teamTag(Rd.off) + '<i>vs</i>' + teamTag(Rd.def) + "</span></div>" +
      '<p class="tp-help">' + (mine === "off"
        ? "Drag a glowing player to where he goes, then choose what he does there. Tap the ball handler to pass, hand off or shoot; tap anyone else to set a screen. The " + B.esc(nick(Rd.def)) + " are " + B.esc(sch.label) + "."
        : "<b>They run: " + B.esc(cpuSet.name) + ".</b> " + B.esc(cpuSet.desc) + " Drag your defenders to where they start and tap each one to give him his job.") + "</p>" +
      '<div class="tp-stage"><svg class="tp-court" viewBox="0 0 500 470" role="img" aria-label="Half court"></svg><div class="tp-pop" hidden></div><div class="tp-prompt" hidden></div></div>' + legend() +
      '<div class="tp-tools"><button type="button" class="tp-tool" data-act="undo">Undo</button><button type="button" class="tp-tool" data-act="reset">Reset</button>' +
      (mine === "def" ? '<button type="button" class="tp-tool" data-act="preview">Watch their set</button>' : "") +
      '<span class="tp-count"></span><button type="button" class="gm-btn tp-run">' + (mine === "off" ? "Run the play" : "Lock in the defense") + "</button></div>" +
      '<div class="tp-result" hidden></div>';
    var svg = root.querySelector(".tp-court"), pop = root.querySelector(".tp-pop"), prompt = root.querySelector(".tp-prompt"), stage = root.querySelector(".tp-stage");
    court(svg);
    var lines = el("g", {}, svg), toks = el("g", {}, svg), live = el("g", {}, svg);
    var offTok = [], defTok = [], ball;
    function current() {                                     // everyone's spot after the steps drawn so far
      var pos = offAt.map(function (p) { return p.slice(); }), b = 0;
      steps.forEach(function (a) {
        if (a.t === "move" || a.t === "dribble") pos[a.who] = a.path[a.path.length - 1];
        else if (a.t === "screen") pos[a.who] = a.after ? (a.afterEnd || (a.after === "roll" ? [HOOP[0] + (a.path[a.path.length - 1][0] - HOOP[0]) * 0.18, HOOP[1] + 28] : threeSpot(a.path[a.path.length - 1]))) : a.path[a.path.length - 1];
        else if (a.t === "pass") b = a.to;
        else if (a.t === "dho") { pos[a.to] = lerp(pos[a.who], pos[a.to], 0.15); b = a.to; }
      });
      return { pos: pos, ball: b, shot: steps.some(function (a) { return a.t === "shoot"; }) };
    }
    function draw() {
      lines.innerHTML = ""; toks.innerHTML = ""; offTok = []; defTok = [];
      var cur = current();
      drawSteps(lines, steps, offAt, mine === "def" ? "#9fd3ff" : null);
      // offense where it stands now (in a defense round: where the set starts, so you can see who you're guarding)
      var shownOff = mine === "off" ? cur.pos : offAt;
      var dl = el("g", {}, toks), ol = el("g", {}, toks);
      if (mine === "def") toks.appendChild(dl);
      dfn.forEach(function (p, i) { defTok.push(token(dl, p, defAt[i], defColor, { def: true, mine: mine === "def", role: mine === "def" ? ROLE_SHORT[roles[i]] : null })); });
      off.forEach(function (p, i) { offTok.push(token(ol, p, shownOff[i], offColor, { mine: mine === "off" && !ran })); });
      if (mine === "def" && ran) defTok.forEach(function (t) { t.classList.remove("mine"); });
      ball = ballAt(toks); var bp = shownOff[mine === "off" ? cur.ball : 0]; place(ball, [bp[0] + 15, bp[1] - 15]);
      var cnt = root.querySelector(".tp-count"); if (cnt) cnt.textContent = mine === "off" ? steps.length + " of " + MAX_STEPS + " actions" + (cur.shot ? " · shot called" : "") : "";
    }
    draw();
    function snapshot() { history.push(JSON.stringify({ steps: steps, defAt: defAt, roles: roles })); }
    function pt(e) { var r = svg.getBoundingClientRect(); return [clamp((e.clientX - r.left) / r.width * W, 12, W - 12), clamp((e.clientY - r.top) / r.height * H, 12, H - 12)]; }
    function screenXY(p) { var r = svg.getBoundingClientRect(), s = stage.getBoundingClientRect(); return [p[0] / W * r.width + r.left - s.left, p[1] / H * r.height + r.top - s.top]; }
    function closePop() { pop.hidden = true; pop.innerHTML = ""; }
    function menu(at, items, onCancel, together) {
      var xy = screenXY(at);
      withNext = false;
      pop.innerHTML = (together ? '<label class="tp-with"><input type="checkbox"> ' + B.esc(together) + "</label>" : "") + items.map(function (it, k) { return '<button type="button" data-k="' + k + '"' + (it.sub ? ' title="' + B.esc(it.sub) + '"' : "") + ">" + B.esc(it.label) + (it.sub ? "<small>" + B.esc(it.sub) + "</small>" : "") + "</button>"; }).join("") + '<button type="button" class="x" data-k="-1">Cancel</button>';
      pop.hidden = false;
      var cb = pop.querySelector(".tp-with input"); if (cb) cb.addEventListener("change", function () { withNext = cb.checked; });
      var sw = stage.clientWidth, pw = pop.offsetWidth, ph = pop.offsetHeight;
      pop.style.left = clamp(xy[0] - pw / 2, 4, sw - pw - 4) + "px";
      pop.style.top = (xy[1] + 30 + ph > stage.clientHeight ? Math.max(4, xy[1] - ph - 30) : xy[1] + 30) + "px";
      pop.querySelectorAll("button").forEach(function (b) {
        b.addEventListener("click", function (ev) { ev.stopPropagation(); var k = +b.getAttribute("data-k"); closePop(); if (k < 0) { if (onCancel) onCancel(); draw(); } else items[k].go(); });
      });
    }
    var picking = null;                                      // waiting for a tap on a teammate (screen for / pass to)
    function pick(text, valid, done) {
      picking = { valid: valid, done: done };
      prompt.textContent = text + " (tap him)"; prompt.hidden = false;
      offTok.forEach(function (t, i) { t.classList.toggle("tp-pickable", valid.indexOf(i) >= 0); });
    }
    function endPick() { picking = null; prompt.hidden = true; offTok.forEach(function (t) { t.classList.remove("tp-pickable"); }); }
    // a called shot stays the last thing in the play: new actions go in before it, and a pass away from the shooter takes it back
    function put(a) {
      var si = -1; steps.forEach(function (x, k) { if (x.t === "shoot") si = k; });
      if (withNext && a.t !== "shoot" && steps.some(function (x) { return x.t !== "shoot"; })) a.with = true;
      withNext = false;
      if (a.t === "shoot") { if (si >= 0) steps.splice(si, 1); steps.push(a); return; }
      if (si < 0) { steps.push(a); return; }
      var shotStep = steps[si]; steps.splice(si, 1); steps.push(a);
      if (current().ball === shotStep.who) steps.push(shotStep);
      else flash("The shot is off: " + off[shotStep.who].last + " gave up the ball. Pick a new shot.");
    }
    function add(a) { snapshot(); put(a); draw(); }
    function flash(t) { prompt.textContent = t; prompt.hidden = false; clearTimeout(flash.t); flash.t = setTimeout(function () { prompt.hidden = true; }, 2400); }
    var withNext = false;
    function others(i) { return [0, 1, 2, 3, 4].filter(function (k) { return k !== i; }); }
    function offMenu(i, path, moved) {
      var cur = current(), at = path[path.length - 1], hasBall = cur.ball === i, nm = off[i].last;
      if (steps.length >= MAX_STEPS + (cur.shot ? 1 : 0)) { flash("That's the most actions in one play. Run it, or undo one."); draw(); return; }
      var items = [];
      if (hasBall) {
        if (moved) items.push({ label: "Dribble here", go: function () { add({ t: "dribble", who: i, path: path }); } },
          { label: "Drive and shoot", sub: "Attack and finish", go: function () { snapshot(); put({ t: "dribble", who: i, path: path }); put({ t: "shoot", who: i }); draw(); } },
          { label: "Dribble, then pass to…", go: function () { snapshot(); put({ t: "dribble", who: i, path: path }); draw(); pick("Who does " + nm + " pass to?", others(i), function (j) { put({ t: "pass", who: i, to: j }); draw(); }); } });
        else items.push({ label: "Pass to…", go: function () { draw(); pick("Who does " + nm + " pass to?", others(i), function (j) { add({ t: "pass", who: i, to: j }); }); } },
          { label: "Hand off to…", sub: "A dribble hand-off", go: function () { draw(); pick("Who does " + nm + " hand it to?", others(i), function (j) { add({ t: "dho", who: i, to: j }); }); } },
          { label: cur.shot ? "Shoot from here instead" : "Shoot from here", go: function () { add({ t: "shoot", who: i }); } });
      } else {
        var scr = function (after) { return function () { draw(); pick("Who does " + nm + " screen for?", others(i), function (j) { add({ t: "screen", who: i, path: moved ? path : [at], for: j, after: after }); }); }; };
        if (moved) items.push({ label: "Cut here", go: function () { add({ t: "move", who: i, path: path, sub: "cut" }); } },
          { label: "Spot up here", sub: "Space the floor, wait for the ball", go: function () { add({ t: "move", who: i, path: path, sub: "spot" }); } });
        else items.push({ label: "Cut to the rim", go: function () { add({ t: "move", who: i, path: [at, lerp(at, [HOOP[0], HOOP[1] + 30], 0.85)], sub: "cut" }); } });
        items.push({ label: "Set a screen for…", go: scr(null) }, { label: "Screen and roll", sub: "Screen, then roll to the rim", go: scr("roll") }, { label: "Screen and pop", sub: "Screen, then pop to the arc", go: scr("pop") });
      }
      var last = steps.filter(function (x) { return x.t !== "shoot"; }).pop();
      menu(at, items, null, last && last.who !== i && !hasBall ? "At the same time as action " + steps.filter(function (x, k) { return x.t !== "shoot" && !(x.with && k); }).length : null);
    }
    function defMenu(i, at) {
      menu(at, ROLES.map(function (r) { return { label: r[1], sub: r[2], go: function () { roles[i] = r[0]; draw(); } }; }));
    }
    var drag = null;
    svg.addEventListener("pointerdown", function (e) {
      var t = e.target.closest(".tp-tok"); if (!t) return;
      if (picking) {
        var k = offTok.indexOf(t);
        if (k >= 0 && picking.valid.indexOf(k) >= 0) { e.preventDefault(); var f = picking.done; endPick(); f(k); }
        return;
      }
      if (!t.classList.contains("mine")) return;
      e.preventDefault(); closePop();
      var list = mine === "off" ? offTok : defTok, i = list.indexOf(t); if (i < 0) return;
      var from = mine === "off" ? current().pos[i] : defAt[i];
      drag = { i: i, path: [from.slice()], moved: false, t0: pt(e) };
      try { svg.setPointerCapture(e.pointerId); } catch (er) {}
    });
    svg.addEventListener("pointermove", function (e) {
      if (!drag) return;
      var p = pt(e);
      if (!drag.moved && dist(p, drag.t0) < 9) return;
      drag.moved = true;
      if (dist(drag.path[drag.path.length - 1], p) > 5) drag.path.push(p);
      place((mine === "off" ? offTok : defTok)[drag.i], p);
      if (mine === "off" && current().ball === drag.i) place(ball, [p[0] + 15, p[1] - 15]);
      live.innerHTML = "";
      el("path", { d: pd(drag.path), stroke: "#F5D370", "stroke-width": 2.5, fill: "none", "stroke-dasharray": "6 5", opacity: 0.9 }, live);
    });
    function up(e) {
      if (!drag) return;
      var d = drag; drag = null; live.innerHTML = "";
      if (mine === "def") {
        if (d.moved) { snapshot(); defAt[d.i] = d.path[d.path.length - 1].map(Math.round); draw(); }
        defMenu(d.i, mine === "def" ? defAt[d.i] : d.path[0]);
        return;
      }
      offMenu(d.i, d.moved ? simplify(d.path) : [d.path[0]], d.moved);
    }
    svg.addEventListener("pointerup", up); svg.addEventListener("pointercancel", function () { drag = null; live.innerHTML = ""; draw(); });
    stage.addEventListener("click", function (e) { if (picking && !e.target.closest(".tp-tok")) { endPick(); } });
    root.querySelectorAll(".tp-tool").forEach(function (b) {
      b.addEventListener("click", function () {
        var act = b.getAttribute("data-act"); closePop(); endPick();
        if (act === "undo") { var h = history.pop(); if (h) { h = JSON.parse(h); if (mine === "off") steps = h.steps; defAt = h.defAt; roles = h.roles; draw(); } }
        else if (act === "reset") { if (mine === "off") steps = []; else { defAt = START.map(function (p) { return lerp(p, HOOP, 4.4 * FT / dist(p, HOOP)); }); roles = dfn.map(function (p) { return p.big ? "drop" : "tight"; }); } history = []; draw(); }
        else if (act === "preview") animate(run(steps, mk(off, offAt), mk(dfn, defAt), { roles: roles, best: true }), null, true);
      });
    });
    function mk(list, at) { return list.map(function (p, i) { return { r: p.r, big: p.big, last: p.last, at: at[i] }; }); }
    root.querySelector(".tp-run").addEventListener("click", function () {
      closePop(); endPick();
      if (mine === "off" && !steps.length) { prompt.textContent = "Draw at least one action first."; prompt.hidden = false; setTimeout(function () { prompt.hidden = true; }, 2000); return; }
      var out = mine === "off" ? run(steps, mk(off, offAt), mk(dfn, defAt), { kind: sch.kind }) : run(steps, mk(off, offAt), mk(dfn, defAt), { roles: roles, best: true });
      var res = out.res, success = mine === "off" ? res.p * 100 : (1 - res.p) * 100;
      ran = true; lastOut = out; draw();
      var tools = root.querySelector(".tp-tools"); if (tools) tools.remove();
      var help = root.querySelector(".tp-help"); if (help) help.hidden = true;
      animate(out, function () {
        var pts = res.pts || 2, make = B.seeded("tpm" + DAY + state.round + steps.length)() < res.p;
        state.results.push({ mode: mine, success: success, p: res.p, pts: pts });
        state.plays.push({ mode: mine, off: Rd.off, def: Rd.def, steps: steps, defAt: defAt.map(function (p) { return p.map(Math.round); }), roles: mine === "def" ? roles : null, set: cpuSet && cpuSet.name, shooter: res.shooter, p: Math.round(res.p * 1000) / 10 });
        var box = root.querySelector(".tp-result"), who = off[res.shooter].name, zn = { three: "a three", rim: "a shot at the rim", paint: "a shot in the paint", mid: "a mid-range jumper" }[res.z];
        box.hidden = false;
        box.innerHTML = '<div class="tp-score">' + success.toFixed(1) + '%<span>' + (mine === "off" ? "chance the play scores" : "chance they don't score") + "</span></div>" +
          '<div class="gm-row tp-after"><button type="button" class="gm-btn tp-next">' + (state.round < 3 ? "Next play" : "See your score") + '</button>' +
          '<button type="button" class="gm-btn ghost tp-replay"><svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M12 5V2L7 6l5 4V7a5 5 0 1 1-5 5H5a7 7 0 1 0 7-7z" fill="currentColor"/></svg>Replay</button></div>' +
          (res.violation ? "<p>The shot clock runs out before the shot: too many actions for one possession.</p>" :
            "<p><b>" + B.esc(who) + "</b> gets " + zn + (res.extraPass ? " after one more pass" : "") + ", the closest defender about " + res.open.toFixed(0) + " ft away. " +
            (make ? "It goes in." : "It doesn't fall.") + "</p>") +
          (res.notes.length ? '<ul class="tp-notes">' + res.notes.slice(0, 5).map(function (n) { return "<li>" + B.esc(n) + "</li>"; }).join("") + "</ul>" : "") +
          '<p class="gm-note">Turnover risk ' + (res.risk * 100).toFixed(1) + "% · shot clock used " + Math.min(24, res.clock).toFixed(0) + " of 24 seconds</p>";
        var rb = box.querySelector(".tp-replay");
        rb.addEventListener("click", function () { if (rb.disabled) return; rb.disabled = true; draw(); animate(lastOut, function () { rb.disabled = false; }); });
        box.querySelector(".tp-next").addEventListener("click", function () {
          state.round++; if (state.round < 4) round(); else finishGame();
          if (root.getBoundingClientRect().top < 0) root.scrollIntoView({ block: "start" });   // back to the top of the next play
        });
        box.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    });
    // play it out: each step in turn, the defense reacting, then the shot
    function animate(out, done, preview) {
      var fr = out.frames, k = 1;
      var oT = offTok, dT = defTok;
      if (fr.length < 2) { shoot(fr[0], done); return; }
      (function next() {
        if (k >= fr.length) { if (!preview) shoot(fr[fr.length - 1], done); else setTimeout(draw, 700); return; }
        var A = fr[k - 1], Bf = fr[k], t0 = performance.now(), T = 800;
        (function tick(now) {
          var u = Math.min(1, (now - t0) / T), e = u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;
          var now2 = A.pos.map(function (p, i) { var path = Bf.paths && Bf.paths[i]; return path ? along([p].concat(path), e) : lerp(p, Bf.pos[i], e); });
          oT.forEach(function (t, i) { place(t, now2[i]); });
          Bf.def.forEach(function (x, i) { var was = A.def.filter(function (y) { return y.d === x.d; })[0] || x; place(dT[x.d], lerp(was.at, x.at, e)); });
          var bp = A.ball === Bf.ball ? now2[Bf.ball] : lerp(now2[A.ball], now2[Bf.ball], e); place(ball, [bp[0] + 15, bp[1] - 15]);
          if (u < 1) requestAnimationFrame(tick); else { k++; next(); }
        })(t0);
      })();
      function shoot(f, cb) {
        var from = f.pos[out.res.shooter], t0 = performance.now(), T = 750, make = B.seeded("tpm" + DAY + state.round + steps.length)() < out.res.p;
        if (out.res.violation) { cb && cb(); return; }
        (function tick(now) {
          var u = Math.min(1, (now - t0) / T), x = from[0] + (HOOP[0] - from[0]) * u, y = from[1] + (HOOP[1] - from[1]) * u - Math.sin(u * Math.PI) * 70;
          place(ball, [x, y]);
          if (u < 1) requestAnimationFrame(tick);
          else { var ring = el("circle", { cx: HOOP[0], cy: HOOP[1], r: 10, fill: "none", stroke: make ? "#3ecf8e" : "#ff5a4a", "stroke-width": 3 }, svg); if (ring.animate) ring.animate([{ r: 10, opacity: 1 }, { r: 44, opacity: 0 }], { duration: 700, fill: "forwards" }).onfinish = function () { ring.remove(); }; else setTimeout(function () { ring.remove(); }, 700); cb && cb(); }
        })(t0);
      }
    }
  }

  function totals(results) {
    var o = results.filter(function (r) { return r.mode === "off"; }), d = results.filter(function (r) { return r.mode === "def"; });
    var avg = function (a, f) { return a.reduce(function (s, r) { return s + f(r); }, 0) / (a.length || 1); };
    return { total: avg(results, function (r) { return r.success; }), offRtg: avg(o, function (r) { return r.p * r.pts * 100; }), defRtg: avg(d, function (r) { return r.p * r.pts * 100; }) };
  }
  function finishGame() {
    var t = totals(state.results), best = B.store(key());
    if (!best || t.total > best.total) B.store(key(), t);
    root.innerHTML = '<div class="tp-final"><div class="tp-score big">' + t.total.toFixed(1) + '%<span>your score: the average of your four plays</span></div>' +
      '<div class="tp-rtgs"><div><b>' + t.offRtg.toFixed(1) + '</b><span>Off Rtg</span></div><div><b>' + t.defRtg.toFixed(1) + '</b><span>Def Rtg</span></div></div>' +
      '<div class="tp-four">' + state.results.map(function (r, i) { return "<div><span>Play " + (i + 1) + " · " + (r.mode === "off" ? "offense" : "defense") + "</span><b>" + r.success.toFixed(1) + "%</b></div>"; }).join("") + "</div>" +
      '<div class="gm-row"><button type="button" class="gm-btn tp-save">Post to the leaderboard</button><button type="button" class="gm-btn ghost tp-see">See my plays</button><button type="button" class="gm-btn ghost tp-again">Play again</button><button type="button" class="gm-btn ghost tp-other">Another game</button></div><p class="gm-note tp-saved"></p></div>';
    var detail = { game: game, plays: state.plays, results: state.results.map(function (r) { return Math.round(r.success * 10) / 10; }) };
    root.querySelector(".tp-again").addEventListener("click", function () { state = { round: 0, results: [], plays: [] }; round(); });
    root.querySelector(".tp-other").addEventListener("click", function () { intro(); root.scrollIntoView({ block: "start" }); });
    root.querySelector(".tp-see").addEventListener("click", function () { viewPlays({ name: "Your", score: t.total, detail: detail }); });
    root.querySelector(".tp-save").addEventListener("click", function () {
      var btn = this; btn.disabled = true;
      B.askName().then(function (name) {
        var res = { name: name, score: Math.round(t.total * 10) / 10, extra: { off: Math.round(t.offRtg * 10) / 10, def: Math.round(t.defRtg * 10) / 10, game: game.away + "@" + game.home }, detail: detail };
        return Promise.all([B.submit(GAME, DAY, res), B.submit(GAME + "~" + game.id, DAY, res)]);
      }).then(function (r) {
        root.querySelector(".tp-saved").textContent = r[1].rank ? "Posted: #" + r[1].rank + " for " + game.away + " at " + game.home + (r[0].rank ? ", #" + r[0].rank + " overall today." : ".") : "Saved.";
        showBoard(); showGameBoard();
      });
    });
  }

  // ------------------------------------------------------------ the leaderboard, and anyone's four plays
  var boardEl = document.getElementById("tp-board"), gameBoardEl = document.getElementById("tp-board-game");
  function showBoard() { if (boardEl) B.renderBoard(boardEl, GAME, DAY, { cols: [["game", "Game"], ["off", "Off Rtg"], ["def", "Def Rtg"]], scoreLabel: "Score", onView: viewPlays, viewLabel: "See plays" }); }
  function showGameBoard() {                                 // the board of the game picked: everyone who drew plays for it
    if (!gameBoardEl || !game) return;
    var h = document.getElementById("tp-board-game-h"); if (h) h.textContent = "Leaderboard: " + game.away + " at " + game.home;
    gameBoardEl._tabs = false;
    B.renderBoard(gameBoardEl, GAME + "~" + game.id, DAY, { dayOnly: true, cols: [["off", "Off Rtg"], ["def", "Def Rtg"]], scoreLabel: "Score", onView: function (e) { viewPlays(e); }, viewLabel: "See plays" });
  }
  function viewPlays(e) {
    var d = e.detail || {}, plays = d.plays || [];
    var shade = document.createElement("div"); shade.className = "gm-shade";
    shade.innerHTML = '<div class="gm-modal wide"><button type="button" class="gm-x" aria-label="Close">&times;</button><h3>' + B.esc(e.name === "Your" ? "Your" : e.name + "&rsquo;s") + " plays · " + (+e.score).toFixed(1) + '%</h3><div class="tp-mini-grid"></div></div>';
    document.body.appendChild(shade);
    shade.querySelector(".gm-x").addEventListener("click", function () { shade.remove(); });
    shade.addEventListener("click", function (ev) { if (ev.target === shade) shade.remove(); });
    var grid = shade.querySelector(".tp-mini-grid");
    plays.forEach(function (pl, i) {
      var wrap = document.createElement("div"); wrap.className = "tp-mini";
      wrap.innerHTML = "<span>Play " + (i + 1) + " · " + B.esc(nick(pl.off || "")) + " " + (pl.mode === "off" ? "offense" : "vs. " + B.esc(nick(pl.def || "")) + " defense") + (pl.set ? " (" + B.esc(pl.set) + ")" : "") + " · <b>" + ((d.results || [])[i] != null ? d.results[i] + "%" : "") + "</b></span>";
      var svg = el("svg", { viewBox: "0 0 500 470" }); wrap.appendChild(svg); grid.appendChild(wrap);
      court(svg);
      var g = el("g", {}, svg), fin = drawSteps(g, pl.steps || [], START, pl.mode === "def" ? "#9fd3ff" : null);
      var oc = B.colors[pl.off] || "#D4AF37", dc = B.colors[pl.def] || "#cfc8ba";
      (pl.defAt || []).forEach(function (p, k) { el("circle", { cx: p[0], cy: p[1], r: 13, fill: "none", stroke: dc, "stroke-width": 3, "stroke-dasharray": "4 3" }, svg); if (pl.roles) { var t = el("text", { x: p[0], y: p[1] + 26, "text-anchor": "middle", "font-size": 10, "font-weight": 700, fill: "#F5D370", "font-family": "Arial, sans-serif" }, svg); t.textContent = ROLE_SHORT[pl.roles[k]] || ""; } });
      (pl.mode === "off" ? fin.pos : START).forEach(function (p, k) { el("circle", { cx: p[0], cy: p[1], r: 13, fill: "none", stroke: oc, "stroke-width": 3 }, svg); var t = el("text", { x: p[0], y: p[1] + 4, "text-anchor": "middle", "font-size": 11, "font-weight": 700, fill: "#F4F1EA", "font-family": "Arial, sans-serif" }, svg); t.textContent = k + 1; });
    });
  }

  start();
  showBoard();
})();
