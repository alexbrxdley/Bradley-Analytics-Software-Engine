"""
home_tape.py -- the Home page's animated "tape": a slowly scrolling row of windows, one per kind of visualization the
dashboard makes (court charts, advanced charts, league comparisons, the four Search by Criteria tools and the On/Off
Lineup Network), each drawing a small animated version of that chart, with buttons that open that part of the sidebar.

Everything is plain HTML + SVG + CSS animation (no script, nothing downloaded): it draws instantly and never waits on
the NBA's servers. The buttons are tags with a data-tape-nav number; the page's click hook (app.py, bqMain) clicks the
matching hidden Streamlit button, whose callback opens the section -- the same way AI Search's links do.
"""

import html
import math
import random

import streamlit as st

# A sample of Jayson Tatum's real 2024-25 shots: [x feet from the rim (left -), y feet from the rim, made]
_SHOTS = [[-19.6,24.3,0],[-22.1,11.5,0],[8.6,13.6,1],[-2.8,27.2,0],[-5.3,25.6,1],[14.5,7.3,1],[-10.9,26.6,0],[-13.2,23.3,0],[-15.7,21.5,1],[-1.3,3.9,1],[10.2,13.4,1],[-1.7,0.9,1],[13.1,22.1,0],[3.6,1.7,0],[-1.2,1.6,1],[4.4,2.5,1],[18.1,18.3,1],[21.7,11.8,1],[0.4,1.1,1],[-10.9,28.8,0],[3.6,1.3,0],[3.9,28.7,1],[-6.9,2.7,1],[13.6,23.2,0],[16.3,24.1,1],[-1.1,5.0,1],[-21.2,17.4,0],[-15.0,21.0,0],[-0.2,2.1,1],[-8.6,25.2,0],[13.4,5.7,0],[15.1,20.5,0],[-12.9,10.2,0],[-22.8,3.4,0],[-22.9,-1.4,0],[-10.9,28.0,0],[-0.1,0.9,1],[-0.6,0.6,1],[-14.3,22.4,0],[0.5,26.5,1],[-14.0,22.1,0],[10.7,24.5,1],[22.9,-0.6,0],[-1.7,2.1,0],[0.5,9.4,0],[-12.0,5.6,1],[-15.1,20.1,1],[22.7,-0.4,0],[-11.2,24.8,0],[-15.2,20.4,0],[-0.9,2.9,1],[-3.3,5.8,1],[-15.0,9.7,1],[-2.8,27.6,1],[-4.7,17.8,0],[15.7,20.5,1],[-11.9,22.7,0],[13.6,17.2,1],[0.9,0.2,1],[18.4,17.9,0],[5.4,6.8,0],[5.5,30.9,0],[13.0,24.2,1],[-12.3,25.2,0],[-9.2,17.2,0],[0.9,1.5,1],[6.0,4.4,1],[0.2,26.9,1],[-17.2,20.1,0],[-10.5,16.9,1],[8.1,10.5,0],[1.0,7.4,0],[-4.2,27.1,0],[-3.8,27.2,0],[-13.4,22.4,0],[0.5,0.2,1],[3.3,18.8,1],[-9.8,2.8,0],[-22.7,11.3,0],[-15.8,24.2,1],[-15.3,19.9,0],[-6.5,7.1,0],[3.6,3.4,1],[13.8,22.2,0],[-12.1,22.2,0],[-0.2,1.5,0],[0.2,1.5,1],[-1.3,1.9,1],[1.7,13.7,1],[13.5,22.1,0],[3.1,0.9,1],[-14.5,25.3,1],[3.9,1.9,0],[10.0,24.4,0],[-20.7,3.6,1],[1.8,1.1,1],[13.1,0.5,0],[14.7,20.5,0],[-15.8,23.6,0],[-9.7,9.9,0],[0.7,0.2,1],[-20.6,15.6,1],[-0.7,2.5,0],[-14.2,22.7,1],[-13.2,25.1,1],[-13.0,21.1,1],[-0.6,1.7,1],[-0.5,-0.6,0],[1.1,25.8,1],[1.0,29.4,1],[-2.1,6.0,1],[2.9,0.2,1],[-0.4,0.2,1],[-20.7,18.9,0],[1.2,1.4,0],[5.3,-0.0,0],[13.0,7.3,1],[0.4,0.5,1],[-15.0,24.2,1],[0.7,20.1,1],[6.5,1.7,1],[19.9,14.6,1],[-8.3,24.8,0],[17.2,21.1,1],[9.8,24.7,0],[-10.9,34.7,1],[-0.1,1.7,1],[7.6,25.1,1],[-1.0,15.3,0],[-8.8,24.7,1],[5.6,25.2,0],[-19.6,16.9,0],[-1.0,1.3,1],[8.1,12.8,0],[0.7,0.8,0],[-12.7,21.9,0],[1.2,26.6,0],[-15.1,20.6,0],[-6.4,26.0,0],[-3.2,1.1,1],[-9.7,17.4,1],[0.1,0.4,1],[-0.5,1.4,1],[-2.8,29.4,0],[-18.1,23.3,1],[-11.6,11.3,1],[-4.4,2.1,1],[-7.5,25.6,0],[-9.3,26.9,0],[0.9,-0.2,1],[2.9,24.0,1],[8.2,25.1,1],[-7.8,24.2,0],[-1.7,20.8,1],[21.9,12.7,0],[-13.6,3.1,0],[13.2,24.1,0],[-14.5,22.4,0],[-5.3,18.9,0],[-22.7,10.2,1],[-0.6,1.6,1],[-12.5,22.4,0],[0.4,0.5,1],[-0.7,1.1,0],[16.5,3.5,0],[-8.0,13.2,0],[-9.3,25.1,0],[10.9,24.0,1],[1.5,7.6,1],[-3.9,0.9,0],[2.9,27.8,1],[9.7,13.0,1],[-8.8,25.6,1],[-8.3,26.6,0],[-1.6,1.1,1],[-7.8,16.8,0],[-1.0,10.9,1],[1.1,0.5,1],[-0.7,1.3,1],[2.5,27.8,0],[-0.4,0.8,1],[-9.9,24.3,0],[-1.0,30.2,1],[8.2,23.5,0],[-8.5,17.9,0],[-9.2,24.2,1],[-13.1,22.0,0],[-1.1,0.8,1],[0.0,32.2,0],[-13.6,22.4,0],[11.3,14.4,0],[-3.3,25.6,0],[11.2,1.7,0],[2.5,1.1,1],[-11.9,25.2,0],[-3.3,2.4,0],[-6.9,27.6,0],[-18.9,17.6,1],[6.0,13.0,0],[3.8,27.3,1],[-7.7,25.6,0],[2.3,30.0,0],[-11.4,24.3,0],[1.6,1.9,0],[-5.6,1.7,0],[-5.1,25.6,0],[-8.5,3.2,0],[5.3,29.1,1],[1.1,2.5,0],[2.1,0.8,1],[0.0,-0.0,1],[-5.9,25.3,0],[-2.3,2.9,0],[-13.7,20.8,0],[0.6,0.9,1],[-10.5,25.8,0],[-10.9,23.2,0],[2.2,2.9,0],[4.9,6.0,1],[-17.4,19.6,1],[-2.7,10.3,0],[2.6,18.5,0],[2.1,1.9,1],[-0.4,-0.1,1],[-7.0,14.8,1],[-18.5,23.9,0],[-0.1,9.0,1],[-1.7,1.9,1],[3.9,1.1,0],[0.6,0.5,1]]

GREEN = "#16a34a"
GREEN_HI = "#22c55e"
MISS = "#9a9a9a"
GOLD = "#D4AF37"

# (title, subtitle, drawing, [(button label, nav)])
_PLAYER, _TEAM, _CRIT, _ONOFF = "Search by Player", "Search by Team", "Search by Criteria", "On/Off Lineup Network"


def _f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------------------------- drawings
def _court(stroke="#e9e9e9", w=0.35):
    """A half court in feet, rim at (0, 0), drawn with the baseline at the bottom (y is flipped by the caller's
    transform). viewBox units: feet."""
    arc_y = math.sqrt(23.75 ** 2 - 22 ** 2)
    return (f'<g fill="none" stroke="{stroke}" stroke-width="{w}" opacity=".85">'
            f'<path d="M-25 -4.75H25"/>'
            f'<rect x="-8" y="-4.75" width="16" height="19"/>'
            f'<path d="M-6 14.25A6 6 0 0 1 6 14.25"/>'
            f'<path d="M-6 14.25A6 6 0 0 0 6 14.25" stroke-dasharray="1 1"/>'
            f'<path d="M-22 -4.75V{_f(arc_y)}A23.75 23.75 0 0 0 22 {_f(arc_y)}V-4.75"/>'
            f'<path d="M-4 0A4 4 0 0 0 4 0"/>'
            f'<path d="M-3 -1H3"/><circle cx="0" cy="0" r=".75"/>'
            f'</g>')


def _svg(body, vb="-26 -6 52 46", flip=True):
    inner = f'<g transform="translate(0 34) scale(1 -1)">{body}</g>' if flip else body
    return f'<svg class="bt-svg" viewBox="{vb}" preserveAspectRatio="xMidYMid meet">{inner}</svg>'


def _shot_chart():
    dots = []
    for i, (x, y, m) in enumerate(_SHOTS):
        d = 0.2 + (i * 0.021)
        col = GREEN_HI if m else MISS
        dots.append(f'<circle class="bt-pop" cx="{x}" cy="{y}" r=".62" fill="{col}" style="--d:{d:.2f}s"/>')
    return _svg(_court() + "".join(dots))


def _radar():
    labels = ["Scoring", "Playmaking", "Rebounding", "Defense", "Efficiency"]
    vals = [0.95, 0.72, 0.8, 0.62, 0.7]
    cx, cy, R = 0, 0, 15
    ang = [(-90 + 72 * k) * math.pi / 180 for k in range(5)]
    grid = "".join(
        f'<polygon points="{" ".join(f"{_f(cx + R * f * math.cos(a))},{_f(cy + R * f * math.sin(a))}" for a in ang)}" '
        f'fill="none" stroke="#3a3a3a" stroke-width=".18"/>' for f in (0.25, 0.5, 0.75, 1))
    spokes = "".join(f'<path d="M0 0L{_f(R * math.cos(a))} {_f(R * math.sin(a))}" stroke="#3a3a3a" stroke-width=".18"/>'
                     for a in ang)
    pts = " ".join(f"{_f(R * v * math.cos(a))},{_f(R * v * math.sin(a))}" for v, a in zip(vals, ang))
    poly = (f'<g class="bt-grow"><polygon points="{pts}" fill="{GREEN}" fill-opacity=".38" stroke="{GREEN_HI}" '
            f'stroke-width=".45"/></g>')
    dots = "".join(f'<circle class="bt-pop" cx="{_f(R * v * math.cos(a))}" cy="{_f(R * v * math.sin(a))}" r=".7" '
                   f'fill="{GOLD}" style="--d:{1.6 + k * 0.25:.2f}s"/>' for k, (v, a) in enumerate(zip(vals, ang)))
    labs = "".join(f'<text x="{_f(19 * math.cos(a))}" y="{_f(19 * math.sin(a) + 0.8)}" text-anchor="middle" '
                   f'class="bt-lbl">{t}</text>' for t, a in zip(labels, ang))
    return _svg(grid + spokes + poly + dots + labs, vb="-26 -21 52 42", flip=False)


def _league_bars():
    rows = [("PTS", 17.9), ("OFF RTG", 10.5), ("REB", 7.2), ("AST", 4.1), ("TS%", 1.8), ("STL", 0.9)]
    out = ['<path d="M14 2V40" stroke="#777" stroke-width=".25"/>']
    for k, (lab, v) in enumerate(rows):
        y = 3 + k * 6.2
        w = abs(v) * 1.65
        x = 14 if v >= 0 else 14 - w
        col = GREEN if v >= 0 else "#b91c1c"
        out.append(f'<text x="12" y="{y + 3.1:.1f}" text-anchor="end" class="bt-lbl">{lab}</text>')
        out.append(f'<rect class="bt-bar{" neg" if v < 0 else ""}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="4.2" '
                   f'fill="{col}" style="--d:{0.3 + k * 0.28:.2f}s"/>')
        tx = x + w + 1 if v >= 0 else x - 1
        out.append(f'<text class="bt-pop bt-lbl" x="{tx:.1f}" y="{y + 3.1:.1f}" text-anchor="{"start" if v >= 0 else "end"}" '
                   f'style="--d:{1.3 + k * 0.28:.2f}s"><tspan class="bt-num">{"+" if v > 0 else ""}{v}'
                   f'</tspan></text>')
    out.append('<text x="30" y="44" text-anchor="middle" class="bt-lbl dim">vs league average</text>')
    return _svg("".join(out), vb="0 0 52 46", flip=False)


def _scatter():
    rnd = random.Random(11)
    pts = []
    for i in range(46):
        x = rnd.uniform(4, 46)
        y = 40 - (x * 0.62 + rnd.gauss(0, 5.2))
        y = min(40, max(4, y))
        pts.append((x, y))
    out = ['<path d="M3 41H49M3 41V2" stroke="#777" stroke-width=".3"/>',
           '<path d="M30 2H49V20Z" fill="#16a34a" fill-opacity=".14"/>']
    for i, (x, y) in enumerate(pts):
        out.append(f'<circle class="bt-pop" cx="{x:.1f}" cy="{y:.1f}" r=".95" fill="{GREEN_HI}" fill-opacity=".85" '
                   f'style="--d:{0.15 + i * 0.05:.2f}s"/>')
    out.append('<path class="bt-draw" pathLength="1" d="M4 38.5L48 8" stroke="#F5D370" stroke-width=".45" fill="none" '
               'stroke-dasharray="1 .6" style="--d:2.7s"/>')
    hx, hy = max(pts, key=lambda p: p[0] - p[1])
    out.append(f'<circle class="bt-ring" cx="{hx:.1f}" cy="{hy:.1f}" r="2.2" fill="none" stroke="{GOLD}" '
               f'stroke-width=".45" style="--d:3.2s"/>')
    out.append('<text x="26" y="45" text-anchor="middle" class="bt-lbl dim">TS%</text>'
               '<text x="1" y="22" text-anchor="middle" class="bt-lbl dim" transform="rotate(-90 1 22)">USG%</text>')
    return _svg("".join(out), vb="-1 0 52 46", flip=False)


def _ring(n, r, cx=0.0, cy=0.0, start=-90):
    return [(cx + r * math.cos((start + 360 * k / n) * math.pi / 180), cy + r * math.sin((start + 360 * k / n) * math.pi / 180))
            for k in range(n)]


def _edge_color(v):
    """-1..1 -> red..yellow..green (the networks' net-rating scale)."""
    if v < 0:
        t = -v
        return f"rgb(220,{int(200 - 160 * t)},{int(60 - 30 * t)})"
    return f"rgb({int(230 - 200 * v)},{int(215 - 30 * v)},{int(90 - 20 * v)})"


def _lineups():
    rnd = random.Random(5)
    nodes = _ring(10, 16)
    out = []
    pairs = [(a, b) for a in range(10) for b in range(a + 1, 10) if rnd.random() < 0.42]
    for k, (a, b) in enumerate(pairs):
        (x1, y1), (x2, y2) = nodes[a], nodes[b]
        v = rnd.uniform(-1, 1)
        w = 0.25 + abs(v) * 0.55
        out.append(f'<path class="bt-draw" pathLength="1" d="M{x1:.1f} {y1:.1f}L{x2:.1f} {y2:.1f}" stroke="{_edge_color(v)}" '
                   f'stroke-width="{w:.2f}" stroke-opacity=".85" fill="none" style="--d:{0.2 + k * 0.07:.2f}s"/>')
    for k, (x, y) in enumerate(nodes):
        out.append(f'<g class="bt-pop" style="--d:{0.05 * k:.2f}s"><circle cx="{x:.1f}" cy="{y:.1f}" r="2.3" '
                   f'fill="#111" stroke="{GREEN_HI}" stroke-width=".45"/>'
                   f'<circle cx="{x:.1f}" cy="{y - 0.4:.1f}" r=".85" fill="#cfcfcf"/>'
                   f'<path d="M{x - 1.5:.1f} {y + 1.6:.1f}Q{x:.1f} {y - 0.1:.1f} {x + 1.5:.1f} {y + 1.6:.1f}" fill="#cfcfcf"/></g>')
    return _svg("".join(out), vb="-22 -20 44 40", flip=False)


def _shots_by_area():
    cx, cy, r = -15.0, 16.0, 6.5
    dots = []
    for i, (x, y, m) in enumerate(_SHOTS):
        inside = (x - cx) ** 2 + (y - cy) ** 2 <= r * r
        if inside:
            dots.append(f'<circle class="bt-lit" cx="{x}" cy="{y}" r=".72" fill="{GREEN_HI if m else "#e5e7eb"}" '
                        f'style="--d:{2.2 + (i % 17) * 0.06:.2f}s"/>')
        else:
            dots.append(f'<circle cx="{x}" cy="{y}" r=".5" fill="#5b5b5b" opacity=".55"/>')
    circle = (f'<path class="bt-draw" pathLength="1" d="M{cx} {cy + r}A{r} {r} 0 1 1 {cx} {cy - r}A{r} {r} 0 1 1 {cx} {cy + r}" '
              f'fill="none" stroke="#F5D370" stroke-width=".6" style="--d:.5s"/>'
              f'<circle class="bt-fill" cx="{cx}" cy="{cy}" r="{r}" fill="{GOLD}" style="--d:1.6s"/>')
    return _svg(_court() + "".join(dots) + circle)


def _passing():
    hub = (0.0, 6.0)
    mates = [(-17.0, 21.0, 1.0), (-7.0, 30.0, 0.55), (9.0, 29.0, 0.8), (18.0, 19.0, 0.4), (0.0, -1.5, 0.95)]
    out = [_court(stroke="#bdbdbd", w=0.3)]
    for k, (x, y, s) in enumerate(mates):
        out.append(f'<path class="bt-draw" pathLength="1" d="M{hub[0]} {hub[1]}L{x} {y}" stroke="{GREEN}" '
                   f'stroke-width="{0.5 + s * 1.5:.2f}" stroke-linecap="round" fill="none" style="--d:{0.6 + k * 0.4:.2f}s"/>')
    for k, (x, y, s) in enumerate(mates + [(hub[0], hub[1], 0)]):
        big = k == len(mates)
        rr = 3.2 if big else 2.4
        out.append(f'<g class="bt-pop" style="--d:{0.1 + k * 0.12:.2f}s"><circle cx="{x}" cy="{y}" r="{rr}" fill="#111" '
                   f'stroke="{GOLD if big else GREEN_HI}" stroke-width=".5"/>'
                   f'<circle cx="{x}" cy="{y + rr * 0.18:.1f}" r="{rr * 0.36:.2f}" fill="#d6d6d6"/>'
                   f'<path d="M{x - rr * 0.65:.1f} {y - rr * 0.62:.1f}Q{x} {y + rr * 0.05:.1f} {x + rr * 0.65:.1f} {y - rr * 0.62:.1f}" '
                   f'fill="#d6d6d6"/></g>')
    return _svg("".join(out))


def _onoff():
    rnd = random.Random(9)
    nodes = _ring(14, 15.5, cx=-3)
    out = []
    for a in range(14):
        for b in range(a + 1, 14):
            if rnd.random() < 0.3:
                (x1, y1), (x2, y2) = nodes[a], nodes[b]
                v = rnd.uniform(-1, 1)
                out.append(f'<path class="bt-flick" d="M{x1:.1f} {y1:.1f}L{x2:.1f} {y2:.1f}" stroke="{_edge_color(v)}" '
                           f'stroke-width="{0.2 + abs(v) * 0.4:.2f}" style="--d:{rnd.uniform(0, 4):.2f}s"/>')
    for k, (x, y) in enumerate(nodes):
        on = k % 3 != 1
        out.append(f'<circle class="bt-pulse" cx="{x:.1f}" cy="{y:.1f}" r="1.7" fill="#111" '
                   f'stroke="{GREEN_HI if on else "#ef4444"}" stroke-width=".5" style="--d:{k * 0.3:.2f}s"/>')
    out.append('<defs><linearGradient id="btScale" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#dc2626"/>'
               '<stop offset=".5" stop-color="#eab308"/><stop offset="1" stop-color="#16a34a"/>'
               '</linearGradient></defs>'
               '<rect x="17" y="-15" width="1.6" height="30" fill="url(#btScale)"/>'
               '<text x="20" y="-13" class="bt-lbl sm">+20</text><text x="20" y="15" class="bt-lbl sm">-20</text>')
    return _svg("".join(out), vb="-22 -20 46 40", flip=False)


def _cards():
    adv = lambda cat: [(_PLAYER, {"page": _PLAYER, "viz_category": cat}), (_TEAM, {"page": _TEAM, "viz_category": cat})]
    return [
        ("Court Charts", "Shot charts, hex charts, heat maps", _shot_chart(), adv("Court")),
        ("Advanced Charts", "Radars, trends, splits and more", _radar(), adv("Advanced")),
        ("League Comparing Charts", "Anyone vs. the league", _league_bars(), adv("League Comparison")),
        ("Search by Stats", "Scatter Plot", _scatter(), [("Open Stats search", {"page": _CRIT, "tool": 0})]),
        ("Search by Lineups", "Lineup Network", _lineups(), [("Open Lineups search", {"page": _CRIT, "tool": 1})]),
        ("Search by Shots", "Shots by area", _shots_by_area(), [("Open Shots search", {"page": _CRIT, "tool": 2})]),
        ("Search by Passing", "Passing Web", _passing(), [("Open Passing search", {"page": _CRIT, "tool": 3})]),
        ("On/Off Lineup Network", "Who plays best together", _onoff(), [("Open On/Off Lineup Network", {"page": _ONOFF})]),
    ]


_CSS = """
<style>
/* the row slides by itself (app.py's page script moves it: it stops while a mouse is over it, and on a phone while a
   finger is on it and for 3 s after), and can be slid by hand: swipe on a phone; on a computer drag it, use the
   scroll bar under it, or shift + mouse wheel / a trackpad */
.bt-wrap { position: relative; margin: 6px 0 18px; overflow-x: auto; overflow-y: hidden; -webkit-overflow-scrolling: touch;
  scrollbar-width: thin; scrollbar-color: #6b5a24 #151412; padding-bottom: 10px; cursor: grab; overscroll-behavior-x: contain; }
.bt-wrap.dragging { cursor: grabbing; user-select: none; }
.bt-wrap.dragging .bt-btn, .bt-wrap.dragging .bt-viz { pointer-events: none; }
.bt-wrap::-webkit-scrollbar { height: 8px; }
.bt-wrap::-webkit-scrollbar-track { background: #151412; border-radius: 4px; }
.bt-wrap::-webkit-scrollbar-thumb { background: linear-gradient(90deg, #8a6410, #D4AF37, #8a6410); border-radius: 4px; }
.bt-wrap::-webkit-scrollbar-thumb:hover { background: #F5D370; }
.bt-head { display: flex; align-items: center; gap: 8px; margin: 2px 2px 10px; font: 700 12px/1 Arial, sans-serif;
  letter-spacing: .14em; text-transform: uppercase; color: #F5D370; }
.bt-head i { width: 8px; height: 8px; border-radius: 50%; background: #D4AF37; animation: btBreathe 1.6s ease-in-out infinite; }
.bt-head span.sub { color: #8c867b; font-weight: 400; letter-spacing: .04em; text-transform: none; font-size: 12px; margin-left: auto; }
@keyframes btBreathe { 0%,100% { transform: scale(.75); opacity: .55; box-shadow: 0 0 3px 0 rgba(212,175,55,.5); }
  50% { transform: scale(1.15); opacity: 1; box-shadow: 0 0 10px 3px rgba(212,175,55,.9); } }
.bt-track { display: flex; gap: 14px; width: max-content; padding: 2px 0 6px; }
.bt-card { width: 268px; flex: 0 0 268px; box-sizing: border-box; padding: 12px 13px 12px; border-radius: 14px;
  background: linear-gradient(160deg, #1b1916 0%, #0c0b0a 80%); border: 1px solid #2c2923; display: flex; flex-direction: column;
  gap: 8px; color: #f0f0f0; font-family: Arial, Helvetica, sans-serif; transition: border-color .2s, box-shadow .2s; }
.bt-card:hover { border-color: rgba(212,175,55,.6); box-shadow: 0 0 18px rgba(212,175,55,.12); }
.bt-title { font: 700 11px/1.2 Arial, sans-serif; letter-spacing: .12em; text-transform: uppercase; color: #D4AF37; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.bt-sub { font-family: "Playfair Display", serif; font-size: 15px; color: #fff; margin-top: -4px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.bt-rule { height: 1px; background: linear-gradient(90deg, rgba(212,175,55,.55), rgba(212,175,55,0)); }
.bt-svg { display: block; width: 100%; height: 190px; background: transparent; }
/* the drawing sits straight on the window's black gradient, and clicking it opens that part of the dashboard */
.bt-viz { cursor: pointer; border-radius: 6px; outline: none; transition: filter .2s; }
.bt-viz:hover, .bt-viz:focus-visible { filter: brightness(1.15) drop-shadow(0 0 6px rgba(212,175,55,.18)); }
.bt-svg text { font-family: Arial, sans-serif; }
.bt-lbl { font-size: 2.1px; fill: #cfc8ba; }
.bt-lbl.dim { fill: #8c867b; } .bt-lbl.sm { font-size: 1.9px; fill: #8c867b; }
.bt-num { font-weight: 700; fill: #F5D370; }
.bt-btns { display: flex; gap: 6px; flex-wrap: wrap; }
.bt-btn { flex: 1 1 0; text-align: center; white-space: nowrap; cursor: pointer; user-select: none; padding: 7px 8px; border-radius: 999px;
  font: 700 11.5px/1 Arial, sans-serif; color: #fff; border: 1px solid transparent;
  background: linear-gradient(135deg, #1a1a1a, #050505) padding-box, linear-gradient(135deg, #B8860B, #F5D370, #B8860B) border-box;
  transition: transform .15s, box-shadow .15s; }
.bt-btn:hover { transform: translateY(-1px); box-shadow: 0 0 12px rgba(212,175,55,.35); color: #F5D370; }
/* every window's animation runs on one 10 s loop: draw in, hold, fade, start over */
.bt-pop, .bt-bar, .bt-draw, .bt-ring, .bt-lit, .bt-fill, .bt-grow { animation-duration: 10s; animation-iteration-count: infinite;
  animation-delay: var(--d, 0s); animation-fill-mode: both; transform-box: fill-box; transform-origin: center; }
.bt-pop { animation-name: btPop; }
@keyframes btPop { 0% { opacity: 0; transform: scale(0); } 4% { opacity: 1; transform: scale(1.35); } 7% { transform: scale(1); }
  70% { opacity: 1; } 78%, 100% { opacity: 0; } }
.bt-bar { animation-name: btBar; transform-origin: left center; }
.bt-bar.neg { transform-origin: right center; }
@keyframes btBar { 0% { transform: scaleX(0); } 12% { transform: scaleX(1); } 72% { opacity: 1; transform: scaleX(1); }
  80%, 100% { opacity: 0; transform: scaleX(1); } }
.bt-draw { stroke-dasharray: 1 1; animation-name: btDraw; }
@keyframes btDraw { 0% { stroke-dashoffset: 1; opacity: 1; } 14% { stroke-dashoffset: 0; } 70% { opacity: 1; stroke-dashoffset: 0; }
  78%, 100% { opacity: 0; stroke-dashoffset: 0; } }
.bt-ring { animation-name: btRing; }
@keyframes btRing { 0% { opacity: 0; transform: scale(2.4); } 6% { opacity: 1; transform: scale(1); } 10%, 30%, 50% { transform: scale(1.25); }
  20%, 40%, 60% { transform: scale(1); } 66% { opacity: 1; } 74%, 100% { opacity: 0; } }
.bt-lit { animation-name: btLit; }
@keyframes btLit { 0% { opacity: .2; transform: scale(.6); } 5% { opacity: 1; transform: scale(1.6); } 9% { transform: scale(1); }
  70% { opacity: 1; } 80%, 100% { opacity: .2; transform: scale(.6); } }
.bt-fill { animation-name: btFill; }
@keyframes btFill { 0% { fill-opacity: 0; } 8% { fill-opacity: .16; } 60% { fill-opacity: .1; } 72%, 100% { fill-opacity: 0; } }
.bt-grow { animation-name: btGrow; transform-origin: 0 0; transform-box: view-box; }
@keyframes btGrow { 0% { transform: scale(0) rotate(-40deg); opacity: 0; } 14% { transform: scale(1.06) rotate(0); opacity: 1; }
  18% { transform: scale(1); } 70% { opacity: 1; } 80%, 100% { opacity: 0; transform: scale(1); } }
.bt-flick { fill: none; stroke-opacity: .2; animation: btFlick 4s ease-in-out var(--d, 0s) infinite both; }
@keyframes btFlick { 0%, 100% { stroke-opacity: .15; } 50% { stroke-opacity: .95; } }
.bt-pulse { animation: btPulse 4.2s ease-in-out var(--d, 0s) infinite both; transform-box: fill-box; transform-origin: center; }
@keyframes btPulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.3); } }
@media (prefers-reduced-motion: reduce) { .bt-pop, .bt-bar, .bt-draw, .bt-ring, .bt-lit, .bt-fill, .bt-grow, .bt-flick,
  .bt-pulse { animation: none !important; } }
@media (max-width: 640px) { .bt-head span.sub { display: none; } .bt-card { width: 236px; flex-basis: 236px; } .bt-svg { height: 168px; } }
/* the hidden Streamlit buttons the windows' buttons press */
div[class*="st-key-ba_tape_navs"] { display: none !important; }
</style>
"""


def _html(cards):
    def one(card, base):
        title, sub, svg, buttons = card
        btns = "".join(f'<span class="bt-btn" role="button" tabindex="0" data-tape-nav="{base + j}">{label}</span>'
                       for j, (label, _nav) in enumerate(buttons))
        # the drawing opens the window's first destination (for the three chart windows: Search by Player)
        viz = (f'<div class="bt-viz" role="button" tabindex="0" data-tape-nav="{base}" '
               f'title="Open {html.escape(buttons[0][1]["page"])}">{svg}</div>')
        return (f'<div class="bt-card"><div class="bt-title">{title}</div><div class="bt-sub">{sub}</div>'
                f'<div class="bt-rule"></div>{viz}<div class="bt-btns">{btns}</div></div>')

    bases, n = [], 0
    for c in cards:
        bases.append(n)
        n += len(c[3])
    row = "".join(one(c, b) for c, b in zip(cards, bases))
    return (_CSS + '<div class="bt-head"><i></i>Visualizations<span class="sub">Hover to pause, click any visualization to open'
            '</span></div><div class="bt-wrap"><div class="bt-track">' + row + '</div></div>')


@st.cache_data(show_spinner=False)
def _cached_html():
    cards = _cards()
    navs = [nav for c in cards for (_l, nav) in c[3]]
    return _html(cards), navs


def render(navigate):
    """Draws the tape. `navigate(nav)` opens a section (a button callback: it runs before the next run draws anything)."""
    html, navs = _cached_html()
    st.markdown(html, unsafe_allow_html=True)
    with st.container(key="ba_tape_navs"):
        for i, nav in enumerate(navs):
            st.button(f"tape {i}", key=f"ba_tape_nav_{i}", on_click=navigate, args=(dict(nav),))
