"""
interactive.py

Shared framework that adds hover (desktop) tooltips on top of the app's
existing matplotlib chart images, without changing how those images are
generated, saved, or shared -- add_to_tableau_dashboard and
offer_share_to_community keep receiving the SAME figure, since this
renders a SEPARATE, purely visual HTML/SVG overlay positioned on top of
an <img> showing that figure, not a replacement for the figure itself.

Each call site builds a list of "hotspots" -- shapes in the SAME data
coordinates already used to plot that chart (so a shot at LOC_X=10,
LOC_Y=20 is described using x=10, y=20, not some separately-tracked
pixel position) -- and this module converts them into real pixel
positions using the actual matplotlib transform for that Axes, computed
from the SAME drawn figure a person sees, not a guessed layout.

Hotspot dict shape:
    {
        "ax": <the Axes this point/shape belongs to>,
        "shape": "circle" | "rect" | "polygon" | "path" | "image",
        # circle:  "x", "y", "r_px" (r_px is in PIXELS, since a
        #          hit-radius is a screen-space concept, not a data one)
        # rect:    "x0","y0","x1","y1" (opposite corners, DATA coords)
        # polygon: "points": [(x,y), ...] in DATA coords
        # path:    "points": [(x,y), ...] in DATA coords, drawn as a
        #          poly-line hit region "stroke_px" wide (for arcs/edges)
        # image:   "artist": the AnnotationBbox a headshot/logo was drawn
        #          with, "image": that PIL image -- the hover target is the
        #          picture's own visible (non-transparent) area, and it is
        #          never drawn: no dot ever appears on top of a picture.
        #          Dimming darkens exactly the picture's own shape.
        "tooltip": "<div>...</div>",   # HTML already built by the caller
        "mask_players": True,  # (bands) never paint over any player marker/picture
    }

Pinned tooltips (ctrl/cmd+click) are part of the picture: dragging the
chart out, right-click "Save image as" / "Copy image", and the
"Download .png" button all produce the chart WITH every pinned pop-up
(and the highlighting that goes with it) drawn into the image.
"""

import base64
import html as _html
import io
import json as _json
import math as _math

import streamlit as st
import streamlit.components.v1 as components

GOLD = "#D4AF37"
GREEN = "#2fae63"
RED = "#d1483f"
MISS_GRAY = "#9A9A9A"

# Same crop + resolution as st.pyplot (bbox_inches="tight", pad_inches=0.1, dpi=200), so an interactive chart and a
# plain one sit in the page with identical padding and sharpness.
DPI = 200
PAD_IN = 0.1


def _esc(s):
    return _html.escape(str(s), quote=True)


# ---------------------------------------------------------------- tooltip content helpers

def wl_badge(win):
    cls = "w" if win else "l"
    text = "W" if win else "L"
    return f'<span class="wl {cls}">{text}</span>'


def game_context_html(date_str, win, team_score, opp_score, opponent, stat_line=None, extra=None):
    """
    The shared "date / W-L + score / opponent / stats" block used by
    the Shot Chart, Season Trend Chart, and Calendar Heat Map, so all
    three read identically as specified.
    """
    out = (
        f'<div class="tip-stat">{wl_badge(win)} {int(team_score)}-{int(opp_score)}'
        f' · vs {_esc(opponent)}</div>'
        f'<div class="legend">{_esc(date_str)}</div>'
    )
    if stat_line:
        out += f'<div class="legend">{_esc(stat_line)}</div>'
    if extra:
        out += f'<div class="tip-note">{_esc(extra)}</div>'
    return out


def bar_compare_html(title, subject_label, subject_pct, league_pct, note=None):
    """The "<name> vs League average" two-bar compare used by the Heat
    Map and Hex Shot Chart tooltips. subject_label is the real player's
    last name or the team's name -- never "You": these are generated
    visualizations, not personal uploaded-stat charts."""
    label = _esc(subject_label)
    out = (
        f'<div class="tip-title">{_esc(title)}</div>'
        f'<div class="bar-row"><span style="width:auto; max-width:64px;">{label}</span><div class="bar">'
        f'<div class="fill" style="width:{max(0, min(100, subject_pct)):.0f}%"></div></div></div>'
        f'<div class="bar-row"><span>Lg avg</span><div class="bar">'
        f'<div class="fill muted" style="width:{max(0, min(100, league_pct)):.0f}%"></div></div></div>'
    )
    if note:
        out += f'<div class="tip-note">{_esc(note)}</div>'
    return out


def donut_html(title, lines, slice_pct, slice_color=GOLD, track_color="#3a362c", caption=None, legend=None,
               slice_label=None, track_label=None):
    """Kept for any caller that still wants the old ring; the Passing Web now uses pie_html()."""
    return pie_html(title, [(slice_pct, slice_label or f"{slice_pct:.0f}%", slice_color),
                            (100 - slice_pct, track_label or f"{100 - slice_pct:.0f}%", track_color)])


def pie_html(title, slices, note=None):
    """
    A compact pop-up that is almost entirely one pie chart: a small name line on top, then the pie filling the rest
    of the (narrow) pop-up. slices: [(percent, "62% 3PA", color), ...] -- each label is written in WHITE inside its
    own slice (a thin dark outline keeps white readable on a light slice). note: an optional small line under the pie.
    """
    cx = cy = 60.0
    r = 58.0
    total = sum(max(0.0, p) for p, _, _ in slices) or 1.0
    parts, labels = [], []
    start = -_math.pi / 2
    for pct, label, color in slices:
        frac = max(0.0, pct) / total
        if frac <= 0:
            continue
        end = start + frac * 2 * _math.pi
        if frac >= 0.9995:
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>')
        else:
            x0, y0 = cx + r * _math.cos(start), cy + r * _math.sin(start)
            x1, y1 = cx + r * _math.cos(end), cy + r * _math.sin(end)
            large = 1 if frac > 0.5 else 0
            parts.append(f'<path d="M{cx},{cy} L{x0:.2f},{y0:.2f} A{r},{r} 0 {large} 1 {x1:.2f},{y1:.2f} Z" '
                         f'fill="{color}" stroke="#1c1a15" stroke-width="1.2"/>')
        mid = (start + end) / 2
        lr = r * (0.5 if frac < 0.999 else 0.0)
        lx, ly = cx + lr * _math.cos(mid), cy + lr * _math.sin(mid)
        pct_txt, _, unit_txt = str(label).partition(" ")
        big = 17 if frac >= 0.2 else 12
        small = 11 if frac >= 0.2 else 8.5
        labels.append(
            f'<text x="{lx:.1f}" y="{ly - 2:.1f}" text-anchor="middle" font-size="{big}" font-weight="700" '
            f'fill="#ffffff" stroke="#000" stroke-opacity=".55" stroke-width="2.4" paint-order="stroke">{_esc(pct_txt)}</text>'
            f'<text x="{lx:.1f}" y="{ly + small + 1:.1f}" text-anchor="middle" font-size="{small}" font-weight="600" '
            f'fill="#ffffff" stroke="#000" stroke-opacity=".55" stroke-width="2" paint-order="stroke">{_esc(unit_txt)}</text>')
        start = end
    title_html = f'<div class="tip-title pie-name">{_esc(title)}</div>' if title else ""
    note_html = f'<div class="pie-note">{_esc(note)}</div>' if note else ""
    return (f'<div class="pie-tip">{title_html}<svg viewBox="0 0 120 120" width="100%" height="auto" '
            f'style="display:block">{"".join(parts)}{"".join(labels)}</svg>{note_html}</div>')


def _arc_pts(r, t0, t1, n=18):
    """Points on a circle around the hoop, angles in degrees from straight out (+y), positive = right (x > 0)."""
    return [(r * _math.sin(_math.radians(t0 + (t1 - t0) * i / n)), r * _math.cos(_math.radians(t0 + (t1 - t0) * i / n)))
            for i in range(n + 1)]


def _passing_zone_shapes():
    """
    Outlines of the Passing Web's 12 court areas (the same areas visuals.court_zone_key_from_xy() sorts shots into),
    in shot-chart coordinates: {zone: [outer polygon, optional hole polygon]}. Only used to draw the pop-up's mini court.
    """
    R, YTOP = 237.5, 300.0
    junction = _math.degrees(_math.atan2(220, _math.sqrt(R * R - 220 * 220)))      # where the arc meets the corner line
    t_lane = _math.degrees(_math.atan2(80, _math.sqrt(R * R - 80 * 80)))           # arc above each lane line
    top_x = YTOP * _math.tan(_math.radians(22.5))
    ray_y = 80 / _math.tan(_math.radians(67.5))                                    # 67.5 deg line, at the lane line
    ra = [(-40, -47.5)] + _arc_pts(40, -90, 90) + [(40, -47.5)]
    right = {
        "wing_mid": [(80, ray_y), (80, _math.sqrt(R * R - 80 * 80))] + _arc_pts(R, t_lane, 67.5),
        "base_mid": [(80, -47.5), (80, ray_y), (R * _math.sin(_math.radians(67.5)), R * _math.cos(_math.radians(67.5))),
                     (220, -47.5)],
        "c3": [(220, -47.5), (220, 89.5), (250, 89.5), (250, -47.5)],
        "w3": _arc_pts(R, 22.5, junction) + [(250, 89.5), (250, YTOP), (top_x, YTOP)],
    }
    mirror = lambda pts: [(-x, y) for x, y in pts]
    return {
        "ra": [ra],
        "paint": [[(-80, -47.5), (-80, 142.5), (80, 142.5), (80, -47.5)], ra],
        "mid_c": [[(-80, 142.5)] + _arc_pts(R, -t_lane, t_lane) + [(80, 142.5)]],
        "top3": [_arc_pts(R, -22.5, 22.5) + [(top_x, YTOP), (-top_x, YTOP)]],
        "rmid_wing": [right["wing_mid"]], "lmid_wing": [mirror(right["wing_mid"])],
        "rmid_base": [right["base_mid"]], "lmid_base": [mirror(right["base_mid"])],
        "rc3": [right["c3"]], "lc3": [mirror(right["c3"])],
        "rw3": [right["w3"]], "lw3": [mirror(right["w3"])],
    }


_ZONE_SHAPES = _passing_zone_shapes()
# where each area's numbers are written (shot-chart coordinates, inside the area)
_ZONE_LABEL_AT = {
    "ra": (0, 8), "paint": (0, 92), "mid_c": (0, 182),
    "lmid_wing": (-146, 146), "rmid_wing": (146, 146), "lmid_base": (-150, 18), "rmid_base": (150, 18),
    "lc3": (-235, 22), "rc3": (235, 22), "lw3": (-196, 212), "rw3": (196, 212), "top3": (0, 266),
}


def zone_court_html(title, zone_stats, headline=None, note=None, lines=None):
    """
    A pop-up that is mostly a small half court split into the Passing Web's 12 areas. Each area is shaded by its
    share, and -- like the Hex Shot Chart's zone labels -- has its numbers written on top of it: the share in large
    type and "made/attempts" under it. zone_stats: {zone: {"share": 0-1, "made": int, "att": float}}; areas missing
    from it are drawn empty. The biggest area gets a bright outline.
    """
    def P(x, y):
        return f"{x:.1f},{300 - y:.1f}"

    shares = {z: float(v.get("share") or 0) for z, v in (zone_stats or {}).items()}
    top = max(shares, key=shares.get) if shares else None
    peak = max(shares.values()) if shares else 0
    shapes, texts = [], []
    for zone, polys in _ZONE_SHAPES.items():
        share = shares.get(zone, 0.0)
        d = " ".join("M" + " L".join(P(x, y) for x, y in poly) + " Z" for poly in polys)
        if share > 0 and peak > 0:
            fill = f'fill="{GOLD}" fill-opacity="{0.12 + 0.78 * share / peak:.2f}"'
        else:
            fill = 'fill="#24211b"'
        stroke = 'stroke="#F5D370" stroke-width="4"' if zone == top else 'stroke="#141310" stroke-width="2"'
        shapes.append(f'<path d="{d}" fill-rule="evenodd" {fill} {stroke}/>')
        if share > 0:
            lx, ly = _ZONE_LABEL_AT[zone]
            narrow = zone in ("lc3", "rc3")
            big, small = (19, 14) if narrow else (28, 19)
            st_ = zone_stats[zone]
            made, att = int(st_.get("made") or 0), float(st_.get("att") or 0)
            sub = f"{made}/{att:.0f}" if att else f"{made}"
            y0 = 300 - ly
            texts.append(
                f'<text x="{lx}" y="{y0 - 2:.1f}" text-anchor="middle" font-size="{big}" font-weight="700" fill="#fff" '
                f'stroke="#000" stroke-opacity=".6" stroke-width="4" paint-order="stroke">{share * 100:.0f}%</text>'
                f'<text x="{lx}" y="{y0 + small + 1:.1f}" text-anchor="middle" font-size="{small}" font-weight="600" '
                f'fill="#ece6d2" stroke="#000" stroke-opacity=".6" stroke-width="3.5" paint-order="stroke">{sub}</text>')
    court = (
        '<g fill="none" stroke="#8a8474" stroke-width="2.2">'
        f'<line x1="-250" y1="347.5" x2="250" y2="347.5"/><rect x="-80" y="{300 - 142.5}" width="160" height="190"/>'
        f'<circle cx="0" cy="{300 - 142.5}" r="60"/><path d="M -40 300 A 40 40 0 0 1 40 300"/>'
        '<circle cx="0" cy="300" r="7.5"/><line x1="-30" y1="307.5" x2="30" y2="307.5"/>'
        f'<path d="M -220 347.5 L -220 {300 - 89.5} A 237.5 237.5 0 0 1 220 {300 - 89.5} L 220 347.5"/></g>')
    parts = [f'<div class="tip-title">{_esc(title)}</div>']
    if headline:
        parts.append(f'<div class="tip-stat court-head">{_esc(headline)}</div>')
    for ln in lines or []:
        parts.append(f'<div class="legend">{_esc(ln)}</div>')
    parts.append(f'<svg viewBox="-252 -2 504 352" width="100%" style="display:block;margin-top:4px">'
                 f'{"".join(shapes)}{court}{"".join(texts)}</svg>')
    if note:
        parts.append(f'<div class="pie-note" style="text-align:left">{_esc(note)}</div>')
    return f'<div class="court-tip">{"".join(parts)}</div>'


def sparkline_html(values, caption, color=GOLD, fmt="{:.0f}"):
    """
    A small season-trend line chart for inside a pop-up: x = every game of the season in order, y = the value in
    that game, with a dashed season-average line. values: list of numbers (oldest game first).
    """
    vals = [float(v) for v in values if v is not None]
    if len(vals) < 2:
        return ""
    w, h, pl, pr, pt, pb = 176.0, 62.0, 16.0, 4.0, 5.0, 12.0
    lo, hi = 0.0, max(vals) if max(vals) > 0 else 1.0
    n = len(vals)

    def px(i):
        return pl + (w - pl - pr) * i / (n - 1)

    def py(v):
        return pt + (h - pt - pb) * (1 - (v - lo) / (hi - lo))

    pts = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(vals))
    area = f"{px(0):.1f},{py(0):.1f} " + pts + f" {px(n - 1):.1f},{py(0):.1f}"
    avg = sum(vals) / n
    best_i = max(range(n), key=lambda i: vals[i])
    svg = (
        f'<svg class="spark" viewBox="0 0 {w:.0f} {h:.0f}" width="100%" height="auto" style="display:block">'
        f'<line x1="{pl}" y1="{py(0):.1f}" x2="{w - pr}" y2="{py(0):.1f}" stroke="#3a372f" stroke-width="1"/>'
        f'<polygon points="{area}" fill="{color}" fill-opacity=".16"/>'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.4" stroke-linejoin="round"/>'
        f'<line x1="{pl}" y1="{py(avg):.1f}" x2="{w - pr}" y2="{py(avg):.1f}" stroke="#ececea" stroke-opacity=".7" '
        f'stroke-width="1" stroke-dasharray="3 2"/>'
        f'<circle cx="{px(best_i):.1f}" cy="{py(vals[best_i]):.1f}" r="2.2" fill="#fff"/>'
        f'<text x="{pl - 3}" y="{py(hi) + 3:.1f}" text-anchor="end" font-size="7.5" fill="#9c988e">{_esc(fmt.format(hi))}</text>'
        f'<text x="{pl - 3}" y="{py(0):.1f}" text-anchor="end" font-size="7.5" fill="#9c988e">0</text>'
        f'<text x="{pl}" y="{h - 2:.1f}" font-size="7.5" fill="#9c988e">Game 1</text>'
        f'<text x="{w - pr}" y="{h - 2:.1f}" text-anchor="end" font-size="7.5" fill="#9c988e">Game {n}</text>'
        f'</svg>'
    )
    return (f'<div class="spark-wrap"><div class="spark-cap">{_esc(caption)} '
            f'<span class="spark-avg">(avg {_esc(fmt.format(avg))})</span></div>{svg}</div>')


def stat_line_tip(title, lines):
    """A simple title + one line per stat, for the many charts whose
    hover is just \"here's the number(s) behind this point\"."""
    out = f'<div class="tip-title">{_esc(title)}</div>'
    for line in lines:
        out += f'<div class="tip-stat">{_esc(line)}</div>'
    return out


# ---------------------------------------------------------------- coordinate transform

def _to_px(ax, x, y, fig_h_px, crop_x0=0.0, crop_y1=None):
    """One data-space point on `ax` -> pixel coords in the SAVED
    (tight-cropped) image (origin top-left, matching HTML/SVG), using
    the real transform for that Axes -- not an approximated layout."""
    dx, dy = ax.transData.transform((x, y))
    top = crop_y1 if crop_y1 is not None else fig_h_px
    return dx - crop_x0, top - dy


def _silhouette_b64(pil_img, max_px=180):
    """The picture's own shape in solid black (its transparency kept), as a PNG data URI -- used to darken exactly a
    headshot/logo (never a box or dot around it), and to keep hover bands from painting over it."""
    from PIL import Image
    im = pil_img.convert("RGBA")
    im.thumbnail((max_px, max_px))
    alpha = im.getchannel("A")
    black = Image.new("RGBA", im.size, (0, 0, 0, 255))
    black.putalpha(alpha)
    buf = io.BytesIO()
    black.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), alpha


def _picture_b64(pil_img, max_px=240):
    """The picture itself (colour, transparency kept) as a small WebP data URI, for the zoom-in copy."""
    im = pil_img.convert("RGBA")
    im.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    try:
        im.save(buf, "WEBP", quality=88, method=4)
        mime = "image/webp"
    except Exception:
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        mime = "image/png"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _opaque_fraction_box(alpha):
    """(left, top, right, bottom) of the picture's visible pixels, as fractions of its own size."""
    bb = alpha.point(lambda a: 255 if a > 40 else 0).getbbox()
    if not bb:
        return 0.0, 0.0, 1.0, 1.0
    w, h = alpha.size
    return bb[0] / w, bb[1] / h, bb[2] / w, bb[3] / h


# ---------------------------------------------------------------- main render entry point

_CSS = """
:root {
  --bg:#0b0a08; --line:#2c2a25; --gold:#D4AF37; --text:#ececea; --muted:#9c988e;
  --green:#2fae63; --red:#d1483f;
}
* { box-sizing:border-box; }
html, body { margin:0; padding:0; overflow:hidden; background:transparent; }
body { font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; color:var(--text); }
.ic-wrap { width:100%; }
.ic-media { position:relative; width:100%; overflow:hidden; }
.ic-media img { width:100%; height:auto; display:block; -webkit-user-drag:element; user-select:none; }
.ic-media.glow img { filter:drop-shadow(0 0 10px rgba(255,255,255,.75)); }
.ic-media > svg { position:absolute; top:0; left:0; width:100%; height:100%; pointer-events:none; }
.ic-media.baked > svg, .ic-media.baked .tip.pinned { visibility:hidden; }
.ic-media.baked .tip.pinned .pin-close { visibility:visible; }
.dim-overlay { fill:#000; transition:fill-opacity .15s ease, opacity .15s ease; pointer-events:none; }
image.dim-overlay { opacity:0; }
.front-dup { transition:opacity .15s ease; }
.zoom-dup { transform-box:fill-box; transform-origin:center; transition:transform .18s ease, opacity .12s ease; pointer-events:none; }
@keyframes goldShift { 0% { background-position:0% 50%; } 100% { background-position:300% 50%; } }
.gold-anim {
  background:linear-gradient(90deg,#9c7a1e,#F5D370,#fff6da,#F5D370,#9c7a1e) !important;
  background-size:300% 100% !important; -webkit-background-clip:text !important; background-clip:text !important;
  color:transparent !important; -webkit-text-fill-color:transparent !important;
  animation:goldShift 6s linear infinite; font-weight:700; display:inline-block;
}
.tip { position:absolute; z-index:5; background:#0c0c0c; border-radius:10px;
  padding:19px 10px 7px; font-size:11.5px; line-height:1.4; opacity:0; pointer-events:none; transition:opacity .1s;
  box-shadow:0 6px 18px rgba(0,0,0,.45); width:200px;
  border:2px solid transparent;
  /* gradient black inside (the dashboard's own black-to-black gradient), animated gold-gradient border */
  background-image:linear-gradient(135deg,#1A1A1A 0%,#0b0b0b 55%,#030303 100%),
    linear-gradient(90deg,#9c7a1e,#F5D370,#fff6da,#F5D370,#9c7a1e);
  background-origin:border-box; background-clip:padding-box, border-box;
  background-size:100% 100%, 300% 100%;
  animation:goldShift 6s linear infinite;
}
/* top-right corner of every hover pop-up: how to keep it on screen */
.tip::after { content:"Hold ctrl and click"; position:absolute; top:4px; right:8px; font:700 8.5px/1 Arial, Helvetica,
  sans-serif; color:#8c8c8c; letter-spacing:.02em; white-space:nowrap; pointer-events:none; }
.tip.pinned::after { content:none; }
.tip.pinned { padding-top:8px; }
.tip.show { opacity:1; }
.tip.pie { width:132px; padding:18px 6px 6px; }
.tip.court { width:252px; padding:18px 7px 7px; }
.tip.pinned.pie { padding-top:5px; }
.tip.pinned.court { padding-top:6px; }
.court-head { font-size:11px; }
.tip.pinned { pointer-events:auto; cursor:grab; user-select:none; -webkit-user-select:none; touch-action:none; }
.tip.pinned.dragging { cursor:grabbing; transition:none; box-shadow:0 10px 26px rgba(0,0,0,.6); }
.tip-title { font-weight:600; color:var(--gold); margin-bottom:2px; }
.pie-name { text-align:center; font-size:11px; margin:0 12px 3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.pie-note { text-align:center; font-size:10px; line-height:1.3; color:#d8d2c0; margin:5px 2px 0; white-space:normal; }
.tip-stat { color:var(--text); margin-bottom:3px; }
.tip-note { color:var(--muted); font-size:11px; margin-top:4px; }
.legend { color:var(--muted); font-size:11px; line-height:1.4; }
.spark-wrap { margin-top:6px; padding-top:5px; border-top:1px solid #2f2c25; }
.spark-cap { color:var(--muted); font-size:10.5px; margin-bottom:2px; }
.spark-avg { color:#ececea; opacity:.8; }
.tip .match { font-size:19px; }
.wl { display:inline-block; padding:1px 6px; border-radius:4px; font-weight:700; font-size:11px; }
.wl.w { background:rgba(47,174,99,.20); color:#5fd68a; }
.wl.l { background:rgba(209,72,63,.20); color:#ff8b83; }
.bar-row { display:flex; align-items:center; gap:6px; font-size:10px; color:var(--muted); margin-top:3px; }
.bar-row span { width:40px; flex-shrink:0; }
.bar { flex:1; height:5px; background:#2a2720; border-radius:3px; overflow:hidden; }
.bar .fill { height:100%; background:var(--gold); }
.bar .fill.muted { background:var(--muted); }
.hint { border-radius:10px; padding:10px 12px; margin-bottom:8px; background:linear-gradient(135deg,#1A1A1A 0%,#070707 73%); position:relative; }
.hint::before { content:""; position:absolute; inset:0; border-radius:10px; padding:1.5px;
  background:linear-gradient(90deg,#9c7a1e,#F5D370,#fff6da,#F5D370,#9c7a1e); background-size:300% 100%;
  animation:goldShift 6s linear infinite;
  -webkit-mask:linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0); -webkit-mask-composite:xor; mask-composite:exclude;
  pointer-events:none; }
.hint-title { font-weight:600; font-size:12.5px; margin-bottom:4px; }
.hint-body { color:#c9c9c9; font-size:11.5px; line-height:1.45; }
.hint-body .tip-line { display:block; margin-top:3px; }
.pin-close { position:absolute; top:2px; right:5px; cursor:pointer; color:var(--muted); font-size:13px; pointer-events:auto; }
.pin-close:hover { color:var(--text); }

/* "Download .png" -- drawn to match the dashboard's own Streamlit buttons exactly (the "Add to Tableau Dashboard"
   button right under it): full width, dark fill, 2px gold-gradient border, shimmering gold bold text, gold glow on
   hover. Measured values: see BUTTON_* in render_interactive_chart(). */
@keyframes bqGoldTextShimmer { from { background-position:0px 0; } to { background-position:-320px 0; } }
.ic-dl-row { margin-top:BTN_GAPpx; }
.ic-dl { position:relative; width:100%; min-height:BTN_Hpx; padding:BTN_PADY BTN_PADX; border:none; border-radius:10px;
  background:linear-gradient(135deg,#1A1A1A 0%,#050505 100%); cursor:pointer; display:flex; align-items:center;
  justify-content:center; transition:box-shadow .2s ease; font-family:Arial, sans-serif; }
.ic-dl::before { content:""; position:absolute; inset:0; border-radius:10px; padding:2px;
  background:linear-gradient(135deg,#B8860B,#F5D370,#B8860B); background-size:200% 100%; background-position:0% 0;
  transition:background-position 1s ease;
  -webkit-mask:linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0); -webkit-mask-composite:xor; mask-composite:exclude;
  pointer-events:none; }
.ic-dl:hover { box-shadow:0 0 14px 2px rgba(212,175,55,.55); }
.ic-dl:hover::before { background-position:100% 0; }
.ic-dl span { font-family:"Source Sans", "Source Sans Pro", sans-serif; font-size:BTN_FONTpx; line-height:BTN_LH; font-weight:bold;
  background:linear-gradient(90deg,#8a6410 0%,#D4AF37 18%,#FFF0B8 34%,#F5D370 50%,#D4AF37 66%,#B8860B 82%,#8a6410 100%);
  background-size:320px 100%; background-repeat:repeat-x; animation:bqGoldTextShimmer 5s linear infinite;
  -webkit-background-clip:text; background-clip:text; color:transparent; }
"""

_JS = r"""
(function () {
  var root = document.getElementById('ROOT_ID');
  var svg = root.querySelector('.ic-media > svg');
  var media = root.querySelector('.ic-media');
  var img = root.querySelector('.ic-media img');
  var tip = root.querySelector('.tip');
  var content = TOOLTIP_MAP;
  var groups = GROUP_MAP;      // key -> group id (or null)
  var restLevel = REST_MAP;    // key -> baseline dim opacity when nothing is active
  var dimLevel = DIM_MAP;      // key -> dim opacity applied to this element when a SIBLING is active
  var outlineMap = OUTLINE_MAP; // key -> true if this shape gets a traced outline stroke when active
  var outlineAlwaysMap = OUTLINEALWAYS_MAP; // key -> outline at a constant 50% while ANY sibling in its group is active
  var stripeFor = STRIPE_MAP;  // key -> list of OTHER keys that stay bright when this one is active (diagonal bands)
  var frontDup = FRONT_MAP;    // key -> true if this shape has a "bring to front" duplicate marker
  var activeFill = ACTIVEFILL_MAP;     // key -> fill-opacity when THIS key itself is active (default 0 = invisible)
  var activeStroke = ACTIVESTROKE_MAP; // key -> stroke-opacity when THIS key itself is active
  var geoms = GEOM_LIST;       // [{key, shape, ...pixel-space geometry}] -- the hit-testing source of truth
  var VB_W = VIEWBOX_W, VB_H = VIEWBOX_H;
  var OVERLAY_CSS = OVERLAYCSS_STR;
  var TIP_CSS = TIPCSS_STR;
  var FILE_NAME = FILENAME_STR;
  var FALLBACK_SIZING = FALLBACK_BOOL;

  // The dashboard's buttons are set in Streamlit's own bundled font ("Source Sans"). This frame is a separate page,
  // so the same @font-face rules are copied in from the app (same origin), making "Download .png" match the
  // "Add to Tableau Dashboard" button under it letter for letter.
  (function copyButtonFont() {
    try {
      var pd = window.parent.document, css = '';
      for (var i = 0; i < pd.styleSheets.length; i++) {
        var sheet = pd.styleSheets[i], rules;
        try { rules = sheet.cssRules; } catch (e) { continue; }
        for (var j = 0; j < rules.length; j++) {
          var rule = rules[j];
          if (rule.type === 5 && /Source Sans/i.test(rule.style.getPropertyValue('font-family'))) {
            var base = sheet.href || pd.baseURI;
            css += rule.cssText.replace(/url\((["']?)([^"')]+)\1\)/g, function (m, q, u) {
              try { return 'url("' + new URL(u, base).href + '")'; } catch (e) { return m; }
            }) + '\n';
          }
        }
      }
      if (css) { var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st); }
    } catch (e) {}
  })();

  // Hover starts on (a mouse is assumed), and only switches off the first time a REAL touch is seen -- a
  // touchscreen laptop still gets hover with its mouse.
  var isTouch = false;
  window.addEventListener('touchstart', function once() { isTouch = true; }, { passive: true, once: true });

  var locked = null;   // a key whose front-marker/brightness stays on after the mouse leaves
  var shown = null;
  var pins = [];

  function dimEl(key) { return svg.querySelector('.dim-overlay[data-key="' + key + '"]'); }
  function frontEl(key) { return svg.querySelector('.front-dup[data-key="' + key + '"]'); }
  function zoomEl(key) { return svg.querySelector('.zoom-dup[data-key="' + key + '"]'); }
  var ZOOM = 1.3;
  function setDim(el, fill, stroke) {
    if (el.tagName.toLowerCase() === 'image') { el.style.opacity = fill; return; }
    el.style.fillOpacity = fill;
    if (stroke !== undefined) el.style.strokeOpacity = stroke;
  }

  function applyGroupState(activeKey) {
    var activeSet = {};
    if (activeKey) activeSet[activeKey] = true;
    if (locked) activeSet[locked] = true;
    pins.forEach(function (p) { activeSet[p.key] = true; });
    var activeKeys = Object.keys(activeSet);

    // Union of "keep bright" members across EVERY active key (the live hover, the locked marker, every pin).
    var keepBrightSet = {};
    activeKeys.forEach(function (ak) {
      keepBrightSet[ak] = true;
      if (stripeFor[ak]) stripeFor[ak].forEach(function (m) { keepBrightSet[m] = true; });
    });
    var anyActiveIsStripe = activeKeys.some(function (ak) { return !!stripeFor[ak]; });

    Object.keys(groups).forEach(function (k) {
      var el = dimEl(k);
      var isActive = !!activeSet[k];
      var keepBright = !!keepBrightSet[k];
      var isStripe = !!stripeFor[k];
      var g = groups[k];
      var sameGroupActive = activeKeys.some(function (ak) { return groups[ak] === g; });
      if (el) {
        if (isActive) {
          setDim(el, activeFill[k] != null ? activeFill[k] : 0,
                 activeStroke[k] != null ? activeStroke[k] : (outlineMap[k] ? 0.9 : 0));
        } else {
          var f;
          if (keepBright) f = 0;
          else if (sameGroupActive && (!isStripe || anyActiveIsStripe)) f = dimLevel[k] != null ? dimLevel[k] : 0.6;
          else f = restLevel[k] || 0;
          setDim(el, f, (outlineAlwaysMap[k] && sameGroupActive && anyActiveIsStripe) ? 0.5 : 0);
        }
      }
      var fd = frontEl(k);
      if (fd) fd.style.opacity = isActive ? 1 : 0;
      // Zoom: the hovered/pinned player -- or every player inside a hovered band -- grows a little; nobody else
      // changes at all.
      var zd = zoomEl(k);
      if (zd) {
        var on = !isStripe && keepBright;
        zd.style.opacity = on ? 1 : 0;
        zd.style.transform = on ? 'scale(' + ZOOM + ')' : 'scale(1)';
      }
    });
  }
  applyGroupState(null);

  // Keeps a pop-up fully inside the chart: to the right of the pointer if it fits, otherwise to the left; below the
  // pointer if it fits, otherwise pulled up -- measured from the pop-up's REAL size, not an assumed one.
  function position(evt, el) {
    var rect = media.getBoundingClientRect();
    var cx = evt.clientX - rect.left, cy = evt.clientY - rect.top;
    var w = el.offsetWidth, h = el.offsetHeight;
    var x = cx + 14;
    if (x + w > rect.width - 4) x = cx - 14 - w;
    x = Math.max(4, Math.min(x, rect.width - w - 4));
    var y = cy - 10;
    if (y + h > rect.height - 4) y = rect.height - h - 4;
    y = Math.max(4, y);
    el.style.left = x + 'px'; el.style.top = y + 'px';
  }
  function fillTip(el, key) {
    el.innerHTML = content[key];
    el.classList.toggle('pie', content[key].indexOf('pie-tip') !== -1);
    el.classList.toggle('court', content[key].indexOf('court-tip') !== -1);
  }

  function makePinnedTip(key, evt) {
    var el = document.createElement('div');
    el.className = 'tip show pinned';
    fillTip(el, key);
    el.insertAdjacentHTML('beforeend', '<span class="pin-close">&times;</span>');
    media.appendChild(el);
    position(evt, el);
    el.querySelector('.pin-close').addEventListener('click', function (e) {
      e.stopPropagation();
      el.remove();
      pins = pins.filter(function (p) { return p.el !== el; });
      applyGroupState(shown);
      recompose();
    });
    makeDraggable(el);
    pins.push({ key: key, el: el });
    applyGroupState(shown);
    recompose();
  }

  // A pinned pop-up can be dragged anywhere inside the chart (so it never has to sit on top of something you want
  // to see). It stays fully inside the chart, and wherever it's dropped is where it appears in a dragged-out,
  // copied, saved or downloaded picture.
  function makeDraggable(el) {
    var startX = 0, startY = 0, startLeft = 0, startTop = 0, activeId = null, moved = false;
    el.addEventListener('pointerdown', function (e) {
      if (e.button !== 0 || e.target.closest('.pin-close')) return;
      e.preventDefault(); e.stopPropagation();
      // the one being moved sits above the other pinned pop-ups (moved in the page BEFORE capturing the pointer --
      // moving an element drops its pointer capture)
      if (media.lastElementChild !== el) media.appendChild(el);
      activeId = e.pointerId; moved = false;
      startX = e.clientX; startY = e.clientY;
      startLeft = parseFloat(el.style.left) || 0; startTop = parseFloat(el.style.top) || 0;
      try { el.setPointerCapture(e.pointerId); } catch (err) {}
      el.classList.add('dragging');
    });
    el.addEventListener('pointermove', function (e) {
      if (activeId !== e.pointerId) return;
      var dx = e.clientX - startX, dy = e.clientY - startY;
      if (!moved && Math.abs(dx) + Math.abs(dy) < 2) return;
      moved = true;
      var maxL = media.clientWidth - el.offsetWidth, maxT = media.clientHeight - el.offsetHeight;
      el.style.left = Math.max(0, Math.min(startLeft + dx, maxL)) + 'px';
      el.style.top = Math.max(0, Math.min(startTop + dy, maxT)) + 'px';
    });
    function end(e) {
      if (activeId !== e.pointerId) return;
      activeId = null;
      try { el.releasePointerCapture(e.pointerId); } catch (err) {}
      el.classList.remove('dragging');
      if (moved) {
        // keep the stacking order of pins the same as on screen, then redraw the picture with the new spot
        pins.sort(function (a, b) {
          return Array.prototype.indexOf.call(media.children, a.el) - Array.prototype.indexOf.call(media.children, b.el);
        });
        recompose();
      }
    }
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
    el.addEventListener('lostpointercapture', end);
    el.addEventListener('click', function (e) { e.stopPropagation(); });
  }

  function show(key, evt) {
    if (shown !== key) { fillTip(tip, key); }
    tip.classList.add('show'); position(evt, tip); shown = key; applyGroupState(key);
  }
  function hide() { tip.classList.remove('show'); shown = null; applyGroupState(null); }

  // ---- Exact geometric hit-testing (the SVG shapes are pointer-events:none and purely visual -- this alone
  // decides what's hovered, so it never blocks a right-click or a drag on the image underneath). ----
  function distToSeg(px, py, x1, y1, x2, y2) {
    var dx = x2 - x1, dy = y2 - y1;
    var len2 = dx * dx + dy * dy;
    var t = len2 === 0 ? 0 : ((px - x1) * dx + (py - y1) * dy) / len2;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
  }
  function pointInPolygon(x, y, pts) {
    var inside = false;
    for (var i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      var xi = pts[i][0], yi = pts[i][1], xj = pts[j][0], yj = pts[j][1];
      if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
    }
    return inside;
  }
  function hitOne(g, x, y) {
    if (g.shape === 'circle') return Math.hypot(x - g.cx, y - g.cy) <= g.r;
    if (g.shape === 'rect') return x >= g.x0 && x <= g.x1 && y >= g.y0 && y <= g.y1;
    if (g.shape === 'ellipse') { var ex = (x - g.cx) / g.rx, ey = (y - g.cy) / g.ry; return ex * ex + ey * ey <= 1; }
    if (g.shape === 'polygon') return pointInPolygon(x, y, g.pts);
    if (g.shape === 'path') {
      for (var i = 0; i < g.pts.length - 1; i++) {
        if (distToSeg(x, y, g.pts[i][0], g.pts[i][1], g.pts[i + 1][0], g.pts[i + 1][1]) <= g.sw / 2) return true;
      }
      return false;
    }
    return false;
  }
  var pointGeoms = geoms.filter(function (g) { return !stripeFor[g.key]; });
  var stripeGeoms = geoms.filter(function (g) { return !!stripeFor[g.key]; });
  function hitTest(x, y) {
    // Specific shapes (players, wedges, edges) win over the large background bands they sit inside; among
    // overlapping pictures, the one drawn on top wins.
    for (var i = pointGeoms.length - 1; i >= 0; i--) if (hitOne(pointGeoms[i], x, y)) return pointGeoms[i].key;
    for (var j = stripeGeoms.length - 1; j >= 0; j--) if (hitOne(stripeGeoms[j], x, y)) return stripeGeoms[j].key;
    return null;
  }
  function toViewBox(evt) {
    var r = svg.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    return [(evt.clientX - r.left) * (VB_W / r.width), (evt.clientY - r.top) * (VB_H / r.height)];
  }

  root.addEventListener('mousemove', function (evt) {
    if (baked && evt.buttons === 0) unbake();
    if (isTouch || evt.target.closest('.ic-dl-row')) { if (shown) hide(); return; }
    var p = toViewBox(evt);
    if (!p) return;
    var key = (evt.target.closest('.tip.pinned')) ? null : hitTest(p[0], p[1]);
    if (key) show(key, evt);
    else if (shown) hide();
  });
  root.addEventListener('mouseleave', function () { if (!isTouch && shown) hide(); });

  root.addEventListener('click', function (evt) {
    if (isTouch || evt.target.closest('.tip.pinned') || evt.target.closest('.ic-dl-row')) return;
    var p = toViewBox(evt);
    var key = p ? hitTest(p[0], p[1]) : null;
    if (!key) return;
    // Ctrl/Cmd+click pins this pop-up in place (as many as you like) -- and pinned pop-ups become part of the
    // picture when it's dragged out, saved, copied or downloaded.
    if (evt.ctrlKey || evt.metaKey) { makePinnedTip(key, evt); return; }
    if (frontDup[key]) { locked = (locked === key) ? null : key; applyGroupState(shown); recompose(); }
  });

  // ---- Pinned pop-ups INSIDE the picture ------------------------------------------------------------------
  // A browser drag / "Save image as" / "Copy image" can only ever take an <img>'s own pixels, never HTML floating
  // on top of it. So every time the pins change, the chart is re-drawn once onto a canvas WITH the pinned pop-ups
  // (and their highlighting) painted in, and the moment a drag or right-click starts on the chart the <img> is
  // switched to that version (the live overlay is hidden meanwhile, so nothing is drawn twice). It switches back
  // as soon as the mouse moves again with no button held.
  var ORIG_SRC = img.getAttribute('src');
  var baseImg = new Image();
  baseImg.src = ORIG_SRC;
  var composedURL = null, composeToken = 0, baked = false;

  function overlayMarkup() {
    // The highlight state that belongs to the pins alone (not whatever the mouse happens to be over right now).
    applyGroupState(null);
    var clone = svg.cloneNode(true);
    applyGroupState(shown);
    clone.removeAttribute('style');
    clone.setAttribute('x', 0); clone.setAttribute('y', 0);
    clone.setAttribute('width', VB_W); clone.setAttribute('height', VB_H);
    return new XMLSerializer().serializeToString(clone);
  }
  function tipsMarkup() {
    var ser = new XMLSerializer();
    return pins.map(function (p) {
      var c = p.el.cloneNode(true);
      var x = c.querySelector('.pin-close'); if (x) x.remove();
      c.style.visibility = 'visible';
      return ser.serializeToString(c);
    }).join('');
  }
  function buildComposite(done) {
    var W = baseImg.naturalWidth || img.naturalWidth, H = baseImg.naturalHeight || img.naturalHeight;
    var cw = media.clientWidth, ch = media.clientHeight;
    if (!W || !H || !cw || !ch) { done(null); return; }
    var out = '<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + VB_W + ' ' + VB_H + '">' +
      '<style>' + OVERLAY_CSS + '</style>' + overlayMarkup() +
      '<g transform="scale(' + (VB_W / cw) + ',' + (VB_H / ch) + ')"><foreignObject x="0" y="0" width="' + cw + '" height="' + ch + '">' +
      '<div xmlns="http://www.w3.org/1999/xhtml" class="ic-cap" style="position:relative;width:' + cw + 'px;height:' + ch + 'px;' +
      'font:13px/1.45 -apple-system,BlinkMacSystemFont,&quot;Segoe UI&quot;,Roboto,Helvetica,Arial,sans-serif;color:#ececea;">' +
      '<style>' + TIP_CSS + '</style>' + tipsMarkup() + '</div></foreignObject></g></svg>';
    var ov = new Image();
    ov.onload = function () {
      try {
        var canvas = document.createElement('canvas');
        canvas.width = W; canvas.height = H;
        var ctx = canvas.getContext('2d');
        ctx.drawImage(baseImg, 0, 0, W, H);
        ctx.drawImage(ov, 0, 0, W, H);
        done(canvas.toDataURL('image/png'));
      } catch (e) { done(null); }
    };
    ov.onerror = function () { done(null); };
    ov.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(out);
  }
  function recompose() {
    var token = ++composeToken;
    if (!pins.length && !locked) { composedURL = null; return; }
    buildComposite(function (url) {
      if (token !== composeToken) return;
      composedURL = url;
      if (url) { var warm = new Image(); warm.src = url; }   // decoded ahead of time, so the switch is instant
    });
  }
  function bake() {
    if (baked || !composedURL || !pins.length) return;
    baked = true;
    img.src = composedURL;
    media.classList.add('baked');
  }
  function unbake() {
    if (!baked) return;
    baked = false;
    img.src = ORIG_SRC;
    media.classList.remove('baked');
  }
  media.addEventListener('mousedown', function (e) { if (!e.target.closest('.tip.pinned')) bake(); }, true);
  media.addEventListener('contextmenu', function (e) { if (!e.target.closest('.tip.pinned')) bake(); }, true);
  img.addEventListener('dragstart', function (e) {
    bake();
    try { e.dataTransfer.setData('DownloadURL', 'image/png:' + FILE_NAME + ':' + img.src); } catch (err) {}
  });
  img.addEventListener('dragend', function () { unbake(); });
  document.addEventListener('mouseup', function (e) { if (e.button === 0) setTimeout(function () { if (!dragging) unbake(); }, 0); });
  var dragging = false;
  img.addEventListener('dragstart', function () { dragging = true; });
  img.addEventListener('dragend', function () { dragging = false; });

  // ---- "Download .png": the chart exactly as it looks now, pinned pop-ups included. ----
  // "Download .png" copies the size of the dashboard's REAL buttons (the "Add to Tableau Dashboard" button right under
  // this chart): its height, padding, corner radius, label font/size/weight and the gap between page elements are
  // read from the live page, so the three buttons always match whatever theme/font size the app is running with.
  function matchDashboardButton() {
    try {
      var pw = window.parent, fe = window.frameElement;
      if (!fe) return false;
      var ec = fe.closest('[data-testid="stElementContainer"]');
      var ref = null, n = ec ? ec.nextElementSibling : null;
      for (var i = 0; n && i < 4 && !ref; i++, n = n.nextElementSibling) {
        ref = n.querySelector('[data-testid="stButton"] button, [data-testid="stDownloadButton"] button');
      }
      if (!ref) ref = pw.document.querySelector('[class*="st-key-no_icon_"] [data-testid="stButton"] button');
      if (!ref) return false;
      var bcs = pw.getComputedStyle(ref), lab = ref.querySelector('p') || ref, lcs = pw.getComputedStyle(lab);
      var btn = root.querySelector('.ic-dl'), span = root.querySelector('.ic-dl span'), row = root.querySelector('.ic-dl-row');
      btn.style.minHeight = bcs.minHeight; btn.style.padding = bcs.padding; btn.style.borderRadius = bcs.borderRadius;
      span.style.fontSize = lcs.fontSize; span.style.lineHeight = lcs.lineHeight; span.style.fontWeight = lcs.fontWeight;
      span.style.fontFamily = lcs.fontFamily; span.style.letterSpacing = lcs.letterSpacing;
      var gap = ec && ec.parentElement ? pw.getComputedStyle(ec.parentElement).rowGap : '';
      if (gap && gap !== 'normal') row.style.marginTop = gap;
      return true;
    } catch (e) { return false; }
  }
  if (!matchDashboardButton()) {
    var matchTries = 0;
    var matchTimer = setInterval(function () { if (matchDashboardButton() || ++matchTries > 40) clearInterval(matchTimer); }, 250);
  }
  window.addEventListener('resize', matchDashboardButton);

  var dlBtn = root.querySelector('.ic-dl');
  if (dlBtn) {
    dlBtn.addEventListener('click', function () {
      function save(url) {
        var a = document.createElement('a');
        a.href = url || ORIG_SRC;
        a.download = FILE_NAME;
        document.body.appendChild(a);
        a.click();
        a.remove();
      }
      if (pins.length || locked) buildComposite(save); else save(ORIG_SRC);
    });
  }

  // Fallback sizing for a Streamlit without st.iframe(height="content"): size this frame to its real content
  // height (on a phone the picture is far shorter than a height worked out for a wide screen).
  function fitFrame() {
    if (!FALLBACK_SIZING) return;
    var h = Math.ceil(root.getBoundingClientRect().height);
    try {
      if (window.frameElement) { window.frameElement.style.height = h + 'px'; window.frameElement.setAttribute('height', h); }
    } catch (e) {}
  }
  if (img.complete) fitFrame(); else img.addEventListener('load', fitFrame);
  window.addEventListener('resize', fitFrame);
})();
"""


def build_hotspot_svg(hotspots, fig_h_px, crop_x0=0.0, crop_y1=None, renderer=None):
    """
    Builds the purely-visual dim-overlay/front-dup SVG layer (all pointer-events:none, so it never blocks a
    right-click or a drag on the image underneath), plus a geometry list for the JS side's own exact hit-testing.
    """
    defs = []
    zoom_parts = []          # enlarged copies of players, drawn on top of everything
    mask_parts = []          # every player marker/picture, cut out of the bands so a band never paints over a player
    dim_parts = []
    front_parts = []
    tooltip_map = {}
    group_map = {}
    rest_map = {}
    dim_map = {}
    outline_map = {}
    outline_always_map = {}
    stripe_map = {}
    front_map = {}
    active_fill_map = {}
    active_stroke_map = {}
    geom_list = []
    for i, hs in enumerate(hotspots):
        key = f"h{i}"
        tooltip_map[key] = hs["tooltip"]
        group = hs.get("group")
        group_map[key] = group
        rest_map[key] = hs.get("rest_level", 0)
        dim_map[key] = hs.get("dim_level", 0.6 if group else 0)
        outline_map[key] = bool(hs.get("outline", False))
        outline_always_map[key] = bool(hs.get("outline_always_when_group_active", False))
        stripe_map[key] = [f"h{j}" for j in hs["stripe_for"]] if hs.get("stripe_for") is not None else None
        front_map[key] = bool(hs.get("front_dup", False))
        active_fill_map[key] = hs.get("active_fill")
        active_stroke_map[key] = hs.get("active_stroke")
        fill_color = hs.get("fill_color", "#000")
        outline_color = hs.get("outline_color", "var(--gold)")
        outline_dash = hs.get("outline_dash", "4 3")
        dash_attr = f' stroke-dasharray="{outline_dash}"' if outline_dash else ''
        stroke_attrs = f' stroke="{outline_color}" stroke-width="2"{dash_attr} stroke-opacity="0"' if outline_map[key] else ''
        mask_attr = ' mask="url(#ba-players-out)"' if hs.get("mask_players") else ''
        ax = hs.get("ax")
        shape = hs["shape"]
        geom = None
        if shape == "circle":
            px, py = _to_px(ax, hs["x"], hs["y"], fig_h_px, crop_x0, crop_y1)
            r = hs.get("r_px", 12)
            # The hit tolerance is a little more generous than the visual radius -- a real cursor doesn't land on the
            # exact center pixel, and a chart squeezed into a narrow column shrinks a fixed target along with it.
            geom_list.append({"key": key, "shape": "circle", "cx": px, "cy": py, "r": max(r, 13)})
            mask_parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{r:.2f}" fill="#000"/>')
            if hs.get("zoom"):
                zoom_parts.append(f'<circle class="zoom-dup" data-key="{key}" cx="{px:.2f}" cy="{py:.2f}" r="{r:.2f}" '
                                  f'fill="{hs.get("zoom_color", "#D4AF37")}" stroke="#fff" stroke-width="1.2" '
                                  f'style="opacity:0;transform:scale(1)"/>')
            if group:
                geom = f'<circle class="dim-overlay" data-key="{key}" cx="{px:.2f}" cy="{py:.2f}" r="{r:.2f}" style="fill:{fill_color}" fill-opacity="{rest_map[key]}"{stroke_attrs}/>'
            if front_map[key]:
                fc = hs.get("front_color", "var(--gold)")
                front_parts.append(f'<circle class="front-dup" data-key="{key}" cx="{px:.2f}" cy="{py:.2f}" '
                                   f'r="{r * 1.15:.2f}" fill="{fc}" stroke="#fff" stroke-width="1.5" opacity="0"/>')
        elif shape == "image":
            # A headshot/logo: hovering anywhere on the picture itself (its visible pixels' own box) opens its
            # pop-up, and nothing is ever drawn on top of it -- dimming darkens exactly the picture's own shape.
            # The picture's own box -- NOT the AnnotationBbox's, which adds padding around the picture (that padding is
            # what made a darkened/cut-out copy look like a dark halo around each player).
            art = hs["artist"]
            inner = getattr(art, "offsetbox", None)
            bb = (inner if inner is not None else art).get_window_extent(renderer)
            left, right = bb.x0 - crop_x0, bb.x1 - crop_x0
            top, bottom = crop_y1 - bb.y1, crop_y1 - bb.y0
            sil_uri, alpha = _silhouette_b64(hs["image"])
            fl, ft, fr, fb = _opaque_fraction_box(alpha)
            bw, bh = right - left, bottom - top
            hl, ht, hr, hb = left + fl * bw, top + ft * bh, left + fr * bw, top + fb * bh
            geom_list.append({"key": key, "shape": "rect", "x0": hl, "y0": ht, "x1": hr, "y1": hb})
            img_attrs = f'x="{left:.2f}" y="{top:.2f}" width="{bw:.2f}" height="{bh:.2f}" href="{sil_uri}" preserveAspectRatio="none"'
            mask_parts.append(f'<image {img_attrs}/>')
            if group and (dim_map[key] or rest_map[key]):
                geom = f'<image class="dim-overlay" data-key="{key}" {img_attrs} style="opacity:{rest_map[key]}"/>'
            if hs.get("zoom"):
                # A full-colour copy of the picture laid exactly over it, which scales up (from its own centre) when
                # this player is hovered/pinned or sits in a hovered band -- the "zoom in".
                zoom_uri = _picture_b64(hs["image"], max_px=int(min(360, max(bw, bh) * 1.3 * 1.5)))
                zoom_parts.append(f'<image class="zoom-dup" data-key="{key}" x="{left:.2f}" y="{top:.2f}" '
                                  f'width="{bw:.2f}" height="{bh:.2f}" href="{zoom_uri}" preserveAspectRatio="none" '
                                  f'style="opacity:0;transform:scale(1)"/>')
        elif shape == "rect":
            x0, y0 = _to_px(ax, hs["x0"], hs["y0"], fig_h_px, crop_x0, crop_y1)
            x1, y1 = _to_px(ax, hs["x1"], hs["y1"], fig_h_px, crop_x0, crop_y1)
            left, top = min(x0, x1), min(y0, y1)
            right, bottom = max(x0, x1), max(y0, y1)
            geom_list.append({"key": key, "shape": "rect", "x0": left, "y0": top, "x1": right, "y1": bottom})
            if group:
                geom = f'<rect class="dim-overlay" data-key="{key}" x="{left:.2f}" y="{top:.2f}" width="{right-left:.2f}" height="{bottom-top:.2f}" style="fill:{fill_color}" fill-opacity="{rest_map[key]}"{stroke_attrs}{mask_attr}/>'
        elif shape == "polygon":
            pts = [_to_px(ax, x, y, fig_h_px, crop_x0, crop_y1) for x, y in hs["points"]]
            geom_list.append({"key": key, "shape": "polygon", "pts": [[round(x, 2), round(y, 2)] for x, y in pts]})
            if group:
                if hs.get("smooth"):
                    # A soft, organic outline (quadratic curves through each edge's midpoint) instead of sharp
                    # corners -- hit-testing still uses the straight-line points above, which it stays close to.
                    n = len(pts)
                    start = ((pts[0][0] + pts[n - 1][0]) / 2, (pts[0][1] + pts[n - 1][1]) / 2)
                    d = f"M {start[0]:.2f} {start[1]:.2f} "
                    for i2 in range(n):
                        cur, nxt = pts[i2], pts[(i2 + 1) % n]
                        mid = ((cur[0] + nxt[0]) / 2, (cur[1] + nxt[1]) / 2)
                        d += f"Q {cur[0]:.2f} {cur[1]:.2f} {mid[0]:.2f} {mid[1]:.2f} "
                    d += "Z"
                    geom = f'<path class="dim-overlay" data-key="{key}" d="{d}" style="fill:{fill_color}" fill-opacity="{rest_map[key]}"{stroke_attrs}{mask_attr}/>'
                else:
                    pts_str = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
                    geom = f'<polygon class="dim-overlay" data-key="{key}" points="{pts_str}" style="fill:{fill_color}" fill-opacity="{rest_map[key]}"{stroke_attrs}{mask_attr}/>'
        elif shape == "path":
            pts = [_to_px(ax, x, y, fig_h_px, crop_x0, crop_y1) for x, y in hs["points"]]
            sw = hs.get("stroke_px", 14)
            geom_list.append({"key": key, "shape": "path", "pts": [[round(x, 2), round(y, 2)] for x, y in pts], "sw": max(sw, 16)})
            if group:
                d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)
                geom = f'<path class="dim-overlay" data-key="{key}" d="{d}" fill="none" stroke="#000" stroke-width="{sw}" stroke-opacity="{rest_map[key]}"/>'
        if group and geom:
            dim_parts.append(geom)

    if any(hs.get("mask_players") for hs in hotspots):
        defs.append('<mask id="ba-players-out" maskUnits="userSpaceOnUse" x="-10000" y="-10000" width="20000" height="20000">'
                    '<rect x="-10000" y="-10000" width="20000" height="20000" fill="#fff"/>'
                    + "".join(mask_parts) + '</mask>')
    # Bands (big background shapes) first, players on top of them -- a player is never covered by a band.
    band_parts = [p for p in dim_parts if 'mask="url(#ba-players-out)"' in p]
    other_parts = [p for p in dim_parts if 'mask="url(#ba-players-out)"' not in p]
    body = ((f'<defs>{"".join(defs)}</defs>' if defs else "") + "".join(band_parts) + "".join(other_parts)
            + "".join(front_parts) + "".join(zoom_parts))
    return (body, tooltip_map, group_map, rest_map, dim_map, outline_map, stripe_map, front_map, geom_list,
            active_fill_map, active_stroke_map, outline_always_map)


# The Streamlit button this app's "Download .png" button has to match -- measured on the running dashboard (Streamlit
# 1.61, baseFontSize 20): 50px tall, 5px x 15px padding, 17.5px bold label on a 28px line, 16px gap between elements.
BUTTON = {"H": 50, "PADY": "5px", "PADX": "15px", "FONT": 17.5, "LH": "28px", "GAP": 16}


def _css_with_button():
    css = _CSS
    for k, v in (("BTN_GAP", BUTTON["GAP"]), ("BTN_H", BUTTON["H"]), ("BTN_PADY", BUTTON["PADY"]),
                 ("BTN_PADX", BUTTON["PADX"]), ("BTN_FONT", BUTTON["FONT"]), ("BTN_LH", BUTTON["LH"])):
        css = css.replace(k + "px", f"{v}px" if isinstance(v, (int, float)) else str(v)).replace(k, str(v))
    return css


_OVERLAY_ONLY_CSS = ".dim-overlay{fill:#000;} image.dim-overlay{opacity:0;} .front-dup{} .zoom-dup{transform-box:fill-box;transform-origin:center;}"


def build_html_doc(fig, hotspots, key, dpi=DPI, hint_text=None, glow=False, fallback_sizing=False,
                   file_name="bradley-analytics-chart.png"):
    """
    Builds the self-contained HTML document (image + SVG dim/front overlay + tooltip + JS + "Download .png") for
    `fig`/`hotspots`, and returns (html_doc, estimated_height_px). Split out from render_interactive_chart so it can
    be tested without a Streamlit runtime.
    """
    fig.set_dpi(dpi)
    fig.canvas.draw()  # settles layout so get_tightbbox() and every artist's extent reflect the final render
    renderer = fig.canvas.get_renderer()

    # The same tight crop st.pyplot uses (bbox_inches="tight", 0.1in pad), computed from the SAME renderer and
    # threaded through every hit region's pixel math, so the picture and its hover shapes are cropped identically.
    try:
        tbb = fig.get_tightbbox(renderer)
        fig_w_in, fig_h_in = fig.get_size_inches()
        x0 = max(0.0, tbb.x0 - PAD_IN)
        y0 = max(0.0, tbb.y0 - PAD_IN)
        x1 = min(fig_w_in, tbb.x1 + PAD_IN)
        y1 = min(fig_h_in, tbb.y1 + PAD_IN)
        if x1 <= x0 or y1 <= y0:
            raise ValueError("degenerate tight bbox")
    except Exception:
        x0, y0, x1, y1 = 0.0, 0.0, *fig.get_size_inches()

    from matplotlib.transforms import Bbox
    crop_bbox = Bbox([[x0, y0], [x1, y1]])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, transparent=True, bbox_inches=crop_bbox)
    buf.seek(0)
    data_uri = "data:image/png;base64," + base64.b64encode(buf.read()).decode("ascii")

    px_w, px_h = (x1 - x0) * dpi, (y1 - y0) * dpi
    crop_x0_px, crop_y1_px = x0 * dpi, y1 * dpi
    root_id = f"ic-{key}"
    if any(h.get("shape") == "image" for h in hotspots):
        # savefig's cropped render leaves picture positions cached in the CROPPED frame; one normal draw puts them back
        # in the full-figure frame every other hover shape is measured in.
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()

    svg_body, tooltip_map, group_map, rest_map, dim_map, outline_map, stripe_map, front_map, geom_list, \
        active_fill_map, active_stroke_map, outline_always_map = build_hotspot_svg(
            hotspots, None, crop_x0=crop_x0_px, crop_y1=crop_y1_px, renderer=renderer)

    css = _css_with_button()
    js = (_JS.replace("ROOT_ID", root_id)
             .replace("TOOLTIP_MAP", _json.dumps(tooltip_map))
             .replace("GROUP_MAP", _json.dumps(group_map))
             .replace("REST_MAP", _json.dumps(rest_map))
             .replace("DIM_MAP", _json.dumps(dim_map))
             .replace("OUTLINEALWAYS_MAP", _json.dumps(outline_always_map))
             .replace("OUTLINE_MAP", _json.dumps(outline_map))
             .replace("STRIPE_MAP", _json.dumps(stripe_map))
             .replace("FRONT_MAP", _json.dumps(front_map))
             .replace("ACTIVEFILL_MAP", _json.dumps(active_fill_map))
             .replace("ACTIVESTROKE_MAP", _json.dumps(active_stroke_map))
             .replace("GEOM_LIST", _json.dumps(geom_list))
             .replace("VIEWBOX_W", f"{px_w:.2f}")
             .replace("VIEWBOX_H", f"{px_h:.2f}")
             .replace("OVERLAYCSS_STR", _json.dumps(_OVERLAY_ONLY_CSS))
             .replace("TIPCSS_STR", _json.dumps(css))
             .replace("FILENAME_STR", _json.dumps(file_name))
             .replace("FALLBACK_BOOL", "true" if fallback_sizing else "false"))

    hint_main = "Hover over different areas of the visualization or any data point to see an interactive display window."
    hint_tip = "Tip: Hold ctrl when clicking on a data point for it to remain displayed, then drag it wherever you like."
    if hint_text is not None:
        hint_main, hint_tip = hint_text, None
    hint_html = "" if not hotspots else f"""
  <div class="hint">
    <div class="hint-title gold-anim">Interacting with the visualization is only available on desktop display. Try it out!</div>
    <div class="hint-body">{_esc(hint_main)}{f'<span class="tip-line">{_esc(hint_tip)}</span>' if hint_tip else ''}</div>
  </div>"""

    html_doc = f"""<!doctype html><html><head><meta charset="utf-8">
<style>{css}</style></head><body>
<div class="ic-wrap" id="{root_id}">{hint_html}
  <div class="ic-media{' glow' if glow else ''}">
    <img src="{data_uri}" alt="chart" draggable="true"/>
    <svg viewBox="0 0 {px_w:.2f} {px_h:.2f}" preserveAspectRatio="none">{svg_body}</svg>
    <div class="tip"></div>
  </div>
  <div class="ic-dl-row"><button class="ic-dl" type="button"><span>Download .png</span></button></div>
</div>
<script>{js}</script>
</body></html>"""

    display_h = px_h * (760 / px_w) if px_w > 760 else px_h
    return html_doc, int(display_h) + (70 if hotspots else 0) + BUTTON["H"] + BUTTON["GAP"] + 8


def render_interactive_chart(fig, hotspots, key, dpi=DPI, hint_text=None, glow=False,
                             file_name="bradley-analytics-chart.png"):
    """
    Renders `fig` (a matplotlib Figure already built by one of visuals.py's build_* functions, unmodified) as an image
    with a hover overlay for `hotspots`, followed by the "Download .png" button. Does not mutate or replace `fig` --
    callers still pass the SAME fig to add_to_tableau_dashboard/offer_share_to_community exactly as before.

    Sized by Streamlit to its real content height (st.iframe(height="content")), so on a phone there is no empty
    space under the picture: a fixed height worked out for a wide desktop column is what left the big gap there.
    """
    use_content_height = hasattr(st, "iframe")
    html_doc, height = build_html_doc(fig, hotspots, key, dpi=dpi, hint_text=hint_text, glow=glow,
                                      fallback_sizing=not use_content_height, file_name=file_name)
    if use_content_height:
        try:
            st.iframe(html_doc, height="content")
            return
        except Exception:
            pass
    components.html(html_doc, height=height, scrolling=False)
