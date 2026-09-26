"""
hotspots.py

One function per chart type, each building the `hotspots` list
render_interactive_chart() (interactive.py) needs. Every function
takes the SAME data the corresponding build_* function in visuals.py
already receives (or the fig/ax it already produced) -- no new data
fetching happens here beyond what a couple of call sites already do
one line up (see app.py's own changes for those).

Real-data notes, so the reasoning behind a couple of non-obvious
choices doesn't get lost:

- Per-shot / per-game context (Shot Chart, Team Shot Chart, Season
  Trend, Calendar Heat Map) needs a real final score, which
  ShotChartDetail/PlayerGameLog don't carry directly -- it comes from
  nba_data.get_game_context_lookup(), joined by calendar date via
  game_context_date_key() rather than a raw string match, since the
  exact GAME_DATE format isn't confirmed identical across those three
  endpoints. If a particular game isn't in the lookup (team join
  failed, or the date didn't parse), the tooltip still shows whatever
  it has (date, or date+quarter+distance for a shot) rather than
  fabricating a score.

- Clutch Impact Clock: each quarter's pop-up shows that quarter's season
  split (the numbers on the clock face) plus a per-game trend line of the
  points scored IN that quarter -- from nba_data.get_quarter_game_logs(),
  i.e. PlayerGameLogs/TeamGameLogs with a Period filter (4 calls total,
  not one box score per game).

- Passing Web: receiver_makes/receiver_extra_stats (FGA/FG3A) come
  straight from PlayerDashPtPass via the app's existing call site --
  real tracking data, not derived.
"""

import html as _html
import math
import random

import numpy as np

from interactive import wl_badge, bar_compare_html, stat_line_tip, GOLD, pie_html, sparkline_html, zone_court_html
from nba_data import game_context_date_key

MID = "\u00b7"  # real middle-dot character -- see interactive.py's note on why not "&middot;"


def _short_season(season):
    """'2024-25' -> \"'24-'25\" -- the compact format requested for
    season labels on axes and in hovers. Leaves anything that isn't a
    plain YYYY-YY season string untouched (team names, etc.)."""
    s = str(season)
    if len(s) == 7 and s[4] == "-" and s[:4].isdigit() and s[5:].isdigit():
        return f"'{s[2:4]}-'{s[5:]}"
    return s


def _short_label(label):
    """Every stat label in stats_config.py is 'PTS (Points)' style --
    the hover only ever wants the short abbreviation, not both."""
    return label.split(" (")[0].strip()


def _fmt_date(date_val):
    """"November 21, 2026" -- the one date format every hover across
    the app uses (Shot Chart, Season Trend, Calendar Heat Map)."""
    import pandas as pd
    try:
        return pd.to_datetime(date_val).strftime("%B %-d, %Y")
    except (ValueError, TypeError):
        try:
            return pd.to_datetime(date_val).strftime("%B %d, %Y").replace(" 0", " ")
        except (ValueError, TypeError):
            return str(date_val)


def _esc(s):
    return _html.escape(str(s), quote=True)


def _fmt_clock(period, minutes_remaining, seconds_remaining):
    try:
        p = int(period)
        q = f"Q{p}" if p <= 4 else f"OT{p - 4}"
        return f"{q} {MID} {int(minutes_remaining)}:{int(seconds_remaining):02d}"
    except (TypeError, ValueError):
        return ""


def _game_tip(date_key, game_lookup, extra_lines=None):
    """The shared date/W-L/score/opponent block, gracefully degraded
    if a game isn't in the lookup (still shows what it has)."""
    ctx = game_lookup.get(date_key) if date_key else None
    out = ""
    if ctx and ctx.get("team_pts") is not None:
        out += f'<div class="tip-stat">{wl_badge(ctx["win"])} {int(ctx["team_pts"])}-{int(ctx["opp_pts"])} {MID} vs {_esc(ctx["opponent"])}</div>'
    elif ctx:
        out += f'<div class="tip-stat">{wl_badge(ctx["win"])} vs {_esc(ctx["opponent"])}</div>'
    if date_key:
        out += f'<div class="legend">{_esc(_fmt_date(date_key))}</div>'
    for line in (extra_lines or []):
        out += f'<div class="legend">{_esc(line)}</div>'
    return out


# ---------------------------------------------------------------- Shot Chart / Team Shot Chart

def shot_chart_hotspots(ax, shots_df, game_lookup, show_player_name, r_px=9):
    hotspots = []
    for _, row in shots_df.iterrows():
        try:
            x, y = float(row["LOC_X"]), float(row["LOC_Y"])
            made = bool(row["SHOT_MADE_FLAG"])
        except (KeyError, ValueError, TypeError):
            continue
        date_key = game_context_date_key(row.get("GAME_DATE"))
        dist = row.get("SHOT_DISTANCE")
        clock = _fmt_clock(row.get("PERIOD"), row.get("MINUTES_REMAINING"), row.get("SECONDS_REMAINING"))
        dist_text = ""
        if dist is not None:
            try:
                dist_i = int(float(dist))
                dist_text = f"3PT, {dist_i} ft" if dist_i >= 22 else f"{dist_i} ft"
            except (ValueError, TypeError):
                pass
        head = ("Make" if made else "Miss") + (f" {MID} {dist_text}" if dist_text else "")
        if show_player_name and row.get("PLAYER_NAME"):
            head = f'{_esc(row["PLAYER_NAME"])} {MID} {head}'
        tip = f'<div class="tip-title">{head}</div>' + _game_tip(date_key, game_lookup, [clock] if clock else [])
        hotspots.append({"ax": ax, "shape": "circle", "x": x, "y": y, "r_px": r_px, "tooltip": tip})
    return hotspots


# ---------------------------------------------------------------- Heat Map
# Each hover region is the outline of one court zone's OWN share of the drawn fog: the exact density grid the heat
# map itself was drawn from (build_heat_map(..., return_hotspot_data=True)), split into each zone's contribution with
# the same kernel, and traced where that contribution is clearly visible. So an outline sits exactly on the patch of
# fog it describes, and only zones holding a real share of the attempts get one -- a stray 0/1 corner shot gets no
# region at all.

_HEAT_ZONE_NAMES = {
    "paint": "Paint", "lmid": "Left mid-range", "rmid": "Right mid-range", "lc3": "Left corner 3",
    "rc3": "Right corner 3", "lw3": "Left wing 3", "rw3": "Right wing 3", "top3": "Top of the key 3",
}
_HEAT_ZONE_TYPE = {"paint": "paint", "lmid": "mid", "rmid": "mid", "lc3": "c3", "rc3": "c3",
                   "lw3": "w3", "rw3": "w3", "top3": "top3"}
HEAT_MIN_SHARE = 0.06      # a zone needs at least 6% of all attempts...
HEAT_MIN_FGA = 8           # ...and at least 8 attempts, to get an outline


def _league_pct_by_zone_type(league_avgs_df):
    """{zone type: league FG%} from ShotChartDetail's LeagueAverages table, left and right sides pooled."""
    out = {}
    if league_avgs_df is None or getattr(league_avgs_df, "empty", True):
        return out
    need = {"SHOT_ZONE_BASIC", "SHOT_ZONE_AREA", "FGA", "FGM"}
    if not need.issubset(league_avgs_df.columns):
        return out
    tot = {}
    for _, row in league_avgs_df.iterrows():
        basic, area = str(row["SHOT_ZONE_BASIC"]), str(row["SHOT_ZONE_AREA"])
        if basic in ("Restricted Area", "In The Paint (Non-RA)"):
            t = "paint"
        elif basic == "Mid-Range":
            t = "mid"
        elif "Corner 3" in basic:
            t = "c3"
        elif basic == "Above the Break 3":
            t = "top3" if area.startswith("Center") else "w3"
        else:
            continue
        a, m = tot.get(t, (0.0, 0.0))
        tot[t] = (a + float(row["FGA"] or 0), m + float(row["FGM"] or 0))
    for t, (a, m) in tot.items():
        if a > 0:
            out[t] = 100.0 * m / a
    return out


def _zone_contribution(points, grid_x, grid_y, cov):
    """Gaussian-kernel density of just `points` on the grid, with the heat map's own kernel covariance."""
    inv = np.linalg.inv(cov)
    norm = 1.0 / (2 * math.pi * math.sqrt(np.linalg.det(cov)))
    gx = grid_x.ravel()
    gy = grid_y.ravel()
    out = np.zeros(gx.shape[0])
    for start in range(0, len(points), 150):               # chunked: bounded memory even for a whole team's shots
        chunk = points[start:start + 150]
        dx = gx[:, None] - chunk[None, :, 0]
        dy = gy[:, None] - chunk[None, :, 1]
        q = inv[0, 0] * dx * dx + 2 * inv[0, 1] * dx * dy + inv[1, 1] * dy * dy
        out += np.exp(-0.5 * q).sum(axis=1)
    return (out * norm).reshape(grid_x.shape)


def _largest_loop(xs, ys, z, level):
    from contourpy import contour_generator
    pad = np.zeros((z.shape[0] + 2, z.shape[1] + 2))
    pad[1:-1, 1:-1] = z
    dx, dy = xs[1] - xs[0], ys[1] - ys[0]
    px = np.concatenate([[xs[0] - dx], xs, [xs[-1] + dx]])
    py = np.concatenate([[ys[0] - dy], ys, [ys[-1] + dy]])
    lines = contour_generator(x=px, y=py, z=pad).lines(level)
    best, best_area = None, 0.0
    for ln in lines:
        if len(ln) < 4:
            continue
        x, y = ln[:, 0], ln[:, 1]
        area = 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
        if area > best_area:
            best, best_area = ln, area
    return best


def heat_map_hotspots(ax, shots_df, league_avgs_df, subject_label, grid=None):
    """
    grid: {"xx", "yy", "density"} exactly as build_heat_map(..., return_hotspot_data=True) returned it.
    league_avgs_df: nba_data.get_zone_league_averages() (ShotChartDetail's LeagueAverages table).
    """
    from visuals import court_zone_key_from_xy
    if shots_df is None or shots_df.empty or not {"LOC_X", "LOC_Y", "SHOT_MADE_FLAG"}.issubset(shots_df.columns):
        return []
    pts = shots_df[["LOC_X", "LOC_Y"]].to_numpy(dtype=float)
    made = shots_df["SHOT_MADE_FLAG"].to_numpy(dtype=float)
    if len(pts) < 2:
        return []
    # The Passing Web's finer areas, folded back into the heat map's 8 zones: the rim and straightaway mid-range are
    # part of the paint fog, and each side's baseline and elbow mid-range are one "mid-range" zone.
    fold = {"ra": "paint", "paint": "paint", "mid_c": "paint", "lmid_base": "lmid", "lmid_wing": "lmid",
            "rmid_base": "rmid", "rmid_wing": "rmid"}
    zones = np.array([fold.get(z, z) for z in (court_zone_key_from_xy(x, y) for x, y in pts)])
    total = len(pts)

    # The heat map's own kernel (same data, same bandwidth rule as its gaussian_kde).
    from scipy.stats import gaussian_kde
    try:
        cov = gaussian_kde(pts.T).covariance
    except Exception:
        return []
    xs = np.linspace(-250, 250, 100)
    ys = np.linspace(-60, 356.7, 84)
    gxx, gyy = np.meshgrid(xs, ys)           # z[row=y, col=x], the layout contourpy expects
    # The hottest point of the whole chart only needs a coarse grid (it's a smooth surface).
    cxx, cyy = np.meshgrid(np.linspace(-250, 250, 50), np.linspace(-60, 356.7, 42))
    full_max = _zone_contribution(pts, cxx, cyy, cov).max() or 1.0

    league = _league_pct_by_zone_type(league_avgs_df)
    hotspots = []
    for zone_key, zone_name in _HEAT_ZONE_NAMES.items():
        sel = zones == zone_key
        fga = int(sel.sum())
        if fga < HEAT_MIN_FGA or fga / total < HEAT_MIN_SHARE:
            continue
        contrib = _zone_contribution(pts[sel], gxx, gyy, cov)
        peak = contrib.max()
        if peak <= 0:
            continue
        # Traced where this zone's own fog is clearly visible (15% of the chart's hottest point, the level where the
        # fog is plainly drawn), or at half its own peak for a lighter zone -- whichever is lower.
        level = min(0.15 * full_max, 0.5 * peak)
        loop = _largest_loop(xs, ys, contrib, level)
        if loop is None:
            continue
        step = max(1, len(loop) // 48)
        outline = [(float(x), float(y)) for x, y in loop[::step]]
        if len(outline) < 3:
            continue
        fgm = int(made[sel].sum())
        pct = 100.0 * fgm / fga
        share = 100.0 * fga / total
        lg = league.get(_HEAT_ZONE_TYPE[zone_key])
        tip = (f'<div class="tip-title">{_esc(zone_name)}</div>'
               f'<div class="tip-stat">{fgm}/{fga} {MID} {pct:.0f}% FG</div>')
        if lg is not None:
            tip += bar_compare_html("", subject_label, pct, lg).replace('<div class="tip-title"></div>', "")
        tip += f'<div class="tip-note">{share:.0f}% of {_esc(subject_label)}\'s attempts</div>'
        hotspots.append({"ax": ax, "shape": "polygon", "points": outline, "tooltip": tip, "smooth": True,
                         "group": "heat", "rest_level": 0, "dim_level": 0, "outline": True,
                         "outline_color": "#ffffff", "outline_dash": None})
    return hotspots


# ---------------------------------------------------------------- Hex Shot Chart
# build_hex_shot_chart() needs one small additive change to expose the
# per-hex records it already computes internally (see visuals.py diff);
# this just formats them.

def hex_chart_hotspots(ax, hex_records, subject_label):
    hotspots = []
    for rec in hex_records:
        fga, fgm = rec["fga"], rec["fgm"]
        if fga <= 0:
            continue
        pct = 100.0 * fgm / fga
        league_pct = 100.0 * rec["league_fgm"] / rec["league_fga"] if rec["league_fga"] > 0 else pct
        note = "Well above the league average from here" if pct - league_pct > 8 else (
            "Well below the league average from here" if league_pct - pct > 8 else "Roughly league-average from here")
        tip = bar_compare_html(f"{fgm}/{fga} {MID} {pct:.0f}%", subject_label, pct, league_pct, note)
        r_px = max(10, rec["radius"] * 0.9)
        hotspots.append({"ax": ax, "shape": "circle", "x": rec["cx"], "y": rec["cy"], "r_px": r_px, "tooltip": tip})
    return hotspots


# ---------------------------------------------------------------- Passing Web

def passing_web_hotspots(ax, passer_pos, final_positions, receiver_names, receiver_values, receiver_makes,
                          receiver_extra_stats, receiver_season_fg_pct=None, passer_name="", receiver_spot_notes=None,
                          receiver_zone_stats=None):
    """passer_pos/final_positions come straight from build_court_connection_map's
    own return_hotspot_data=True -- the real drawn positions after its
    collision-avoidance layout, not a re-derivation of that layout.
    Arcs are drawn as straight lines in the real chart, so the hit
    region is just the passer-to-receiver segment itself.

    receiver_season_fg_pct: optional list of each receiver's own
    OVERALL season FG% (not just off this passer) -- lets the hover
    show something the static visualization doesn't: whether this
    specific passing connection runs hotter or colder than that
    receiver's normal efficiency, as a donut rather than more text.
    """
    hotspots = []
    px, py = passer_pos
    receiver_season_fg_pct = receiver_season_fg_pct or [None] * len(receiver_names)
    # receiver_spot_notes: optional one line per receiver saying why he sits where he does ("Shoots most off X's
    # passes from the left corner 3 (~31% of those shots)"), shown under his pie.
    receiver_spot_notes = list(receiver_spot_notes or []) + [None] * len(receiver_names)
    # receiver_zone_stats: optional, per receiver, {area: {"share", "made", "att"}} -- where his shots right after this
    # passer's passes came from. When present the pop-up is a mini half court with those numbers on every area.
    receiver_zone_stats = list(receiver_zone_stats or []) + [None] * len(receiver_names)
    _parts = [w for w in str(passer_name or "").split() if w.lower().rstrip(".") not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    passer_last = _parts[-1] if _parts else "this player"
    total_passes = sum(receiver_values) if receiver_values else 0
    total_makes = sum(receiver_makes) if receiver_makes else 0
    for i, (name, passes, makes, extra, season_pct) in enumerate(
            zip(receiver_names, receiver_values, receiver_makes, receiver_extra_stats, receiver_season_fg_pct)):
        if i not in final_positions:
            continue
        rx, ry = final_positions[i]
        if receiver_zone_stats[i]:
            info = f"{int(passes)} passes from {passer_last}"
            if makes:
                info += f" {MID} {int(makes)} made shots off them"
            tip = zone_court_html(
                name, receiver_zone_stats[i], headline=receiver_spot_notes[i], lines=[info],
                note=f"% = share of his shots right after {passer_last}'s passes. Under it: baskets {passer_last} "
                     f"assisted / estimated attempts there.")
        elif extra and extra.get("fga"):
            fga = extra["fga"]
            fg3a = extra.get("fg3a", 0)
            fg3a_pct = 100.0 * fg3a / fga if fga else 0
            # A small pop-up that is almost all pie: 3PA share vs 2PA share, both percentages in white.
            tip = pie_html(name, [(fg3a_pct, f"{fg3a_pct:.0f}% 3PA", GOLD),
                                  (100 - fg3a_pct, f"{100 - fg3a_pct:.0f}% 2PA", "#5a5446")],
                           note=receiver_spot_notes[i])
        else:
            lines = [f"{int(passes)} passes received", f"{int(makes)} makes off those catches"]
            if receiver_spot_notes[i]:
                lines.append(receiver_spot_notes[i])
            tip = stat_line_tip(name, lines)
        hotspots.append({"ax": ax, "shape": "path", "points": [(px, py), (rx, ry)], "stroke_px": 16, "tooltip": tip})
        # The player's own image is a real, separate hoverable target
        # too -- not just the connecting line running through it.
        hotspots.append({"ax": ax, "shape": "circle", "x": rx, "y": ry, "r_px": 22, "tooltip": tip})

    # The passer's own hotspot -- real aggregate context (volume,
    # accuracy, and who it's concentrated with) that no single
    # receiver's own label can show.
    if receiver_values:
        top_i = max(range(len(receiver_values)), key=lambda i: receiver_values[i])
        top_share = 100.0 * receiver_values[top_i] / total_passes if total_passes else 0
        overall_pct = 100.0 * total_makes / sum(e.get("fga", 0) for e in receiver_extra_stats if e) \
            if any(e and e.get("fga") for e in receiver_extra_stats) else None
        lines = [f"{int(total_passes)} tracked passes {MID} {int(total_makes)} led to a make"]
        if overall_pct is not None:
            lines.append(f"{overall_pct:.0f}% FG on shots off these passes")
        lines.append(f"Most to {_esc(receiver_names[top_i])} ({top_share:.0f}% of passes)")
        passer_tip = stat_line_tip(passer_name, lines)
        hotspots.append({"ax": ax, "shape": "circle", "x": px, "y": py, "r_px": 22, "tooltip": passer_tip})
    return hotspots


# ---------------------------------------------------------------- Season Trend / Calendar Heat Map (shared per-game format)

def season_trend_hotspots(ax, x_values, dates, plot_values, stat_label, game_lookup, r_px=9, display_values=None,
                           display_suffix="", is_pct=False):
    """plot_values position the hotspot (matching whatever the chart
    actually draws -- raw, or a cumulative running total); display_values
    (defaulting to plot_values) is what the tooltip's headline number
    shows, so a cumulative chart's hover can read the real per-game
    stat rather than the running total it's positioned at."""
    hotspots = []
    short = _short_label(stat_label)
    display_values = display_values if display_values is not None else plot_values
    for x, date_val, plot_v, disp_v in zip(x_values, dates, plot_values, display_values):
        date_key = game_context_date_key(date_val)
        num = f"{disp_v:.1%}" if is_pct else f"{disp_v:,.0f}"
        tip = f'<div class="tip-title">{num} {_esc(short)}{display_suffix}</div>' + _game_tip(date_key, game_lookup)
        hotspots.append({"ax": ax, "shape": "circle", "x": x, "y": plot_v, "r_px": r_px, "tooltip": tip})
    return hotspots


def calendar_heat_map_hotspots(ax, cell_xy, dates, stat_values, stat_label, game_lookup, is_pct=False,
                                pts=None, reb=None, ast=None):
    hotspots = []
    short = _short_label(stat_label)
    pts = pts if pts is not None else [None] * len(dates)
    reb = reb if reb is not None else [None] * len(dates)
    ast = ast if ast is not None else [None] * len(dates)
    for (x, y), date_val, val, p, r, a in zip(cell_xy, dates, stat_values, pts, reb, ast):
        date_key = game_context_date_key(date_val)
        num = f"{val:.1%}" if is_pct else f"{val:,.0f}"
        tip = f'<div class="tip-title">{num} {_esc(short)}</div>'
        if p is not None:
            tip += f'<div class="tip-stat">{p:.0f} PTS / {r:.0f} REB / {a:.0f} AST</div>'
        tip += _game_tip(date_key, game_lookup)
        hotspots.append({"ax": ax, "shape": "rect", "x0": x - 0.5, "y0": y - 0.5, "x1": x + 0.5, "y1": y + 0.5,
                          "tooltip": tip})
    return hotspots


# ---------------------------------------------------------------- Archetype Radar (polar axes -- theta,r ARE the data coords)

def radar_hotspots(ax, stat_labels, percentiles, detail_lines):
    """detail_lines: list of lists -- one list of stat-line strings
    per category (e.g. ["8.1 RPG", "2.1 OREB/g (24.0 OREB%)", ...]),
    shown in full under that category's percentile, not just one
    summary line. Wedges dim each other on hover (group="radar")."""
    n = len(stat_labels)
    hotspots = []
    for i, (label, pct) in enumerate(zip(stat_labels, percentiles)):
        center = i / n * 2 * math.pi
        half = math.pi / n
        arc = np.linspace(center - half, center + half, 10)
        pts = [(0.0, 0.0)] + [(float(t), 100.0) for t in arc] + [(0.0, 0.0)]
        lines = detail_lines[i] if i < len(detail_lines) else []
        tip = f'<div class="tip-title">{_esc(label)}:</div><div class="tip-stat gold-anim">{pct:.0f}th percentile</div>'
        for line in lines:
            if line:
                tip += f'<div class="tip-stat">{_esc(line)}</div>'
        hotspots.append({"ax": ax, "shape": "polygon", "points": pts, "tooltip": tip,
                          "group": "radar", "rest_level": 0, "dim_level": 0.6})
    return hotspots


# ---------------------------------------------------------------- Clutch Impact Clock (polar, N zero-loc, clockwise)

def clutch_clock_hotspots(ax, quarter_stats, quarter_game_logs=None, color=GOLD):
    """
    One wedge per quarter. The pop-up shows that quarter's season numbers (the same ones printed on the clock face)
    and, at the bottom, a small season-trend line chart: every game of the season left to right, the points scored IN
    THAT QUARTER up the side, with a dashed season-average line.

    quarter_game_logs: {1..4: DataFrame with PTS per game, oldest first} from nba_data.get_quarter_game_logs(); a
    quarter missing from it just shows its season numbers.

    Best quarter glows brightest even at rest; the others are dimmed in proportion to how far below the best they rank.
    """
    quarter_game_logs = quarter_game_logs or {}
    # a very dark team colour (Suns, Nuggets, Wolves ...) would vanish on the dark pop-up: use gold instead
    try:
        _h = str(color).lstrip("#")
        _r, _g, _b = (int(_h[i:i + 2], 16) for i in (0, 2, 4))
        if 0.299 * _r + 0.587 * _g + 0.114 * _b < 70:
            color = GOLD
    except (ValueError, TypeError):
        color = GOLD
    hotspots = []
    pts_vals = [s["PTS"] for s in quarter_stats]
    best_pts, worst_pts = max(pts_vals), min(pts_vals)
    spread = (best_pts - worst_pts) or 1
    for q, stats in enumerate(quarter_stats):
        start = math.radians(q * 90)
        arc = np.linspace(start, start + math.pi / 2, 10)
        pts = [(0.0, 0.0)] + [(float(t), 1.0) for t in arc] + [(0.0, 0.0)]
        rest = 0.55 * (best_pts - stats["PTS"]) / spread
        tip = (f'<div class="tip-title">Q{q + 1}</div>'
               f'<div class="tip-stat">{stats["PTS"]:.1f} PTS {MID} {stats["FG_PCT"]:.0%} FG {MID} '
               f'{stats["PLUS_MINUS"]:+.1f} +/-</div>')
        log = quarter_game_logs.get(q + 1)
        if log is not None and len(log) >= 2 and "PTS" in log.columns:
            tip += sparkline_html(log["PTS"].astype(float).tolist(), f"Q{q + 1} points, game by game", color=color)
        hotspots.append({"ax": ax, "shape": "polygon", "points": pts, "tooltip": tip,
                         "group": "clock", "rest_level": rest, "dim_level": 0.6})
    return hotspots


# ---------------------------------------------------------------- Career Combo Chart

def combo_chart_hotspots(ax_bar, x_labels, bar_values, line_values, bar_label, line_label, records=None,
                          extra_lines=None):
    """records: optional list of season-record strings aligned to
    x_labels. extra_lines: optional list of extra stat-line strings
    (player PPG/RPG/APG, or team ORTG/DRTG) aligned to x_labels,
    shown below the record."""
    hotspots = []
    bar_short, line_short = _short_label(bar_label), _short_label(line_label)
    for i, (lbl, bv, lv) in enumerate(zip(x_labels, bar_values, line_values)):
        lines = [f"{bv:,.1f} {bar_short}", f"{lv:,.1f} {line_short}"]
        if extra_lines and i < len(extra_lines) and extra_lines[i]:
            lines.append(extra_lines[i])
        if records and i < len(records) and records[i]:
            lines.append(records[i])
        tip = stat_line_tip(_short_season(lbl), lines)
        hotspots.append({"ax": ax_bar, "shape": "rect", "x0": i - 0.3, "y0": 0, "x1": i + 0.3,
                          "y1": max(bv, 0.0001), "tooltip": tip})
    return hotspots


# ---------------------------------------------------------------- Scoring Splits Waterfall
# Real bars are POINT contributions (FT/2PT/3PT pts), not raw attempts
# -- this uses the real make% per type (needs attempts, passed in
# separately from the same stats row the points were computed from)
# and applies it as the "bright share of the bar" the spec described,
# labelled honestly against what the bar actually represents.

def waterfall_hotspots(ax, labels, point_values, makes, attempts):
    hotspots = []
    running = 0.0
    for label, val, m, a in zip(labels, point_values, makes, attempts):
        pct = 100.0 * m / a if a else 0.0
        tip = (f'<div class="tip-title">{_esc(label)}</div>'
               f'<div class="tip-stat">{val:,.0f} pts from this shot type</div>'
               f'<div class="tip-note">{int(m)}/{int(a)} {MID} {pct:.0f}% made</div>')
        hotspots.append({"ax": ax, "shape": "rect", "x0": len(hotspots) - 0.3, "y0": running,
                          "x1": len(hotspots) + 0.3, "y1": running + val, "tooltip": tip})
        running += val
    return hotspots


# ---------------------------------------------------------------- Tornado Chart

def tornado_hotspots(ax, labels, subject_values, league_avgs, is_pct_flags):
    hotspots = []
    for i, (label, sv, avg, is_pct) in enumerate(zip(labels, subject_values, league_avgs, is_pct_flags)):
        diff = sv - avg
        fmt = (lambda v: f"{v:.1%}") if is_pct else (lambda v: f"{v:,.1f}")
        tip = (f'<div class="tip-title">{_esc(label)}: {fmt(sv)}</div>'
               f'<div class="tip-stat">League average {fmt(avg)} {MID} {"+" if diff >= 0 else ""}{fmt(diff)}</div>')
        left, right = (0, diff) if diff >= 0 else (diff, 0)
        hotspots.append({"ax": ax, "shape": "rect", "x0": left, "y0": i - 0.3, "x1": right, "y1": i + 0.3,
                          "tooltip": tip})
    return hotspots


# ---------------------------------------------------------------- Shot Flow (Sankey)
# build_sankey_flow's own internal node/band layout would need a small
# additive return-value change (same pattern as the hex chart) to get
# exact drawn band polygons; until that's wired, this uses a
# left-stage rectangle per flow so hovering the zone's outgoing bands
# still shows the real count/percentage -- flagged in the summary as
# the one Sankey piece not yet pixel-matched to the drawn curve.

def sankey_hotspots(ax, stage_labels, flows):
    """
    Mirrors build_sankey_flow's own node_totals/node_positions/cursor
    layout exactly (same math, same order) so each hotspot polygon
    traces the real drawn band's smooth curve rather than a rough
    rectangle standing in for it.
    """
    n_stages = len(stage_labels)
    stage_x = np.linspace(0, 1, n_stages)

    node_totals = {}
    for stage_idx, nodes in enumerate(stage_labels):
        for node in nodes:
            total = sum(f[3] for f in flows if f[0] == stage_idx and f[1] == node)
            total += sum(f[3] for f in flows if f[0] == stage_idx - 1 and f[2] == node)
            node_totals[(stage_idx, node)] = max(total, 0.0001)

    node_positions = {}
    for stage_idx, nodes in enumerate(stage_labels):
        total_height = sum(node_totals[(stage_idx, n)] for n in nodes)
        gap = total_height * 0.08 / max(len(nodes) - 1, 1) if len(nodes) > 1 else 0
        y = 0
        for node in nodes:
            h = node_totals[(stage_idx, node)]
            node_positions[(stage_idx, node)] = (y, y + h)
            y += h + gap

    node_cursor_out = {k: v[0] for k, v in node_positions.items()}
    node_cursor_in = {k: v[0] for k, v in node_positions.items()}
    zone_totals = {}
    for from_stage, from_node, _, value in flows:
        zone_totals[(from_stage, from_node)] = zone_totals.get((from_stage, from_node), 0) + value

    hotspots = []
    for from_stage, from_node, to_node, value in flows:
        to_stage = from_stage + 1
        y0_bottom = node_cursor_out[(from_stage, from_node)]
        y0_top = y0_bottom + value
        node_cursor_out[(from_stage, from_node)] = y0_top
        y1_bottom = node_cursor_in[(to_stage, to_node)]
        y1_top = y1_bottom + value
        node_cursor_in[(to_stage, to_node)] = y1_top

        x0, x1 = stage_x[from_stage], stage_x[to_stage]
        xs = np.linspace(x0, x1, 16)
        smooth = 0.5 - 0.5 * np.cos(np.pi * (xs - x0) / (x1 - x0))
        top = y0_top + (y1_top - y0_top) * smooth
        bottom = y0_bottom + (y1_bottom - y0_bottom) * smooth
        pts = list(zip(xs, top)) + list(zip(xs[::-1], bottom[::-1]))

        pct = 100.0 * value / zone_totals[(from_stage, from_node)] if zone_totals[(from_stage, from_node)] else 0
        tip = (f'<div class="tip-title">{_esc(from_node)} \u2192 {_esc(to_node)}</div>'
               f'<div class="tip-stat">{int(value)} shots {MID} {pct:.0f}% of {_esc(from_node)}</div>')
        hotspots.append({"ax": ax, "shape": "polygon", "points": pts, "tooltip": tip})
    return hotspots


# ---------------------------------------------------------------- Bar Chart (League Comparison)

def bar_chart_hotspots(ax, names, values, stat_label, orientation="vertical", rank_ascending=False, is_pct=False):
    """names/values in the order the bars are DRAWN (build_bar_chart sorts them itself: descending left-to-right for
    vertical bars, ascending bottom-to-top for horizontal ones). Rank 1 is the best value (the lowest when the chart
    ranks lowest-first)."""
    hotspots = []
    vals = [float(v) for v in values]
    if not vals:
        return hotspots
    leader = min(vals) if rank_ascending else max(vals)
    short = _short_label(stat_label)
    fmt = (lambda v: f"{v:.1%}") if is_pct else (lambda v: f"{v:,.1f}")
    for i, (name, v) in enumerate(zip(names, vals)):
        rank = 1 + sum(1 for o in vals if (o < v if rank_ascending else o > v))
        gap = abs(leader - v)
        tip = (f'<div class="tip-title">{_esc(name)}</div>'
               f'<div class="tip-stat">{fmt(v)} {_esc(short)}</div>'
               f'<div class="tip-note">Rank {rank} of {len(vals)}'
               + (f" {MID} {fmt(gap)} behind the leader" if rank > 1 else "") + '</div>')
        if orientation == "vertical":
            hs = {"ax": ax, "shape": "rect", "x0": i - 0.4, "y0": 0, "x1": i + 0.4, "y1": v if v else 0.0001, "tooltip": tip}
        else:
            hs = {"ax": ax, "shape": "rect", "x0": 0, "y0": i - 0.4, "x1": v if v else 0.0001, "y1": i + 0.4, "tooltip": tip}
        hotspots.append(hs)
    return hotspots


# ---------------------------------------------------------------- Scatter Plot (League Comparison + Criteria)
# records: build_scatter_plot(..., return_hotspot_data=True)'s per-row list, in the order the rows were drawn. A row
# drawn as a headshot/logo gets an INVISIBLE hover target covering the picture itself (its visible pixels), so hovering
# anywhere on a player's face/body opens their pop-up and no dot is ever drawn on top of a picture. A row drawn as a
# plain dot keeps a dot-sized target.

def _fmt_val(v, label=""):
    """A stat value as the chart's own axis shows it: percentage stats (FG%, TS%, ...) are stored as 0-1 fractions and
    read as percents; everything else (including per-game counts under 1, like 0.9 FGM) is a plain number."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    is_pct = "%" in str(label).split(" (")[0] or str(label).upper().endswith("_PCT")
    return f"{v:.1%}" if is_pct and abs(v) <= 1.5 else f"{v:,.1f}"


def _player_target(ax, rec, tip, r_px=10, group=None, dot_color=None, zoom=False):
    """zoom=True: the player never darkens; instead they grow a little (their own picture/dot scaled up) while hovered
    or pinned, or while a band they're in is hovered."""
    if rec.get("artist") is not None and rec.get("image") is not None:
        hs = {"shape": "image", "artist": rec["artist"], "image": rec["image"], "tooltip": tip}
    else:
        hs = {"ax": ax, "shape": "circle", "x": rec["x"], "y": rec["y"], "r_px": r_px, "tooltip": tip}
        if group and not zoom:
            hs["front_dup"] = True
            hs["front_color"] = dot_color or rec.get("color") or GOLD
        hs["zoom_color"] = dot_color or rec.get("color") or GOLD
    if group:
        hs["group"] = group
    if zoom:
        hs["zoom"] = True
        hs["dim_level"] = 0
        hs["rest_level"] = 0
    return hs


def scatter_hotspots(ax, records, x_label, y_label):
    hotspots = []
    for rec in records:
        tip = stat_line_tip(str(rec["name"]), [f"{_short_label(x_label)}: {_fmt_val(rec['x'], x_label)}",
                                              f"{_short_label(y_label)}: {_fmt_val(rec['y'], y_label)}"])
        hotspots.append(_player_target(ax, rec, tip))
    return hotspots


def criteria_scatter_hotspots(ax, records, x_label, y_label, stripe_color=None, n_bands=8, noun="player",
                              x_higher_better=True, y_higher_better=True):
    """
    Used by every scatter plot (Search by Criteria, and the Scatter Plot in Search by Player / Search by Team), so
    they all behave the same. noun: "player" or "team" (band pop-ups). x/y_higher_better: False for a stat where
    lower is better -- the best band then sits at that end of the axis instead.

    Diagonal match bands running from the top-right corner of the plot (best in both stats) all the way to the
    bottom-left corner, every band the same width, covering the WHOLE plotting area (the plot's own padded edges
    included, so no corner is left without a band). A player's match % is how far along that same diagonal they sit
    (100% = the best value of both stats among these players, 0% = the lowest of both), so the band a player is drawn
    in is always the band that lists them.

    Every player sits in front of the bands (each marker/picture is cut out of the band tint). No player is ever
    darkened: hovering a player makes that player a little bigger, and hovering a band makes the players inside it a
    little bigger -- everyone else stays exactly as they are.
    """
    if not records:
        return []
    stripe_color = stripe_color or GOLD
    xs = [r["x"] for r in records]
    ys = [r["y"] for r in records]
    x_min, y_min = min(xs), min(ys)
    x_max, y_max = max(xs), max(ys)
    x_span = (x_max - x_min) or 1.0
    y_span = (y_max - y_min) or 1.0

    def norm(x, y):
        nx = (x - x_min) / x_span if x_higher_better else (x_max - x) / x_span
        ny = (y - y_min) / y_span if y_higher_better else (y_max - y) / y_span
        return nx, ny

    def denorm(nx, ny):
        return (x_min + nx * x_span if x_higher_better else x_max - nx * x_span,
                y_min + ny * y_span if y_higher_better else y_max - ny * y_span)

    point_hotspots, sums = [], []
    for rec in records:
        nx, ny = norm(rec["x"], rec["y"])
        s_val = max(0.0, min(2.0, nx + ny))
        sums.append(s_val)
        match = round(50 * s_val)
        tip = (f'<div class="tip-title">{_esc(rec["name"])}</div><div class="match gold-anim">{match}% match</div>'
               f'<div class="tip-stat">{_esc(_short_label(x_label))}: {_fmt_val(rec["x"], x_label)}</div>'
               f'<div class="tip-stat">{_esc(_short_label(y_label))}: {_fmt_val(rec["y"], y_label)}</div>')
        point_hotspots.append(_player_target(ax, rec, tip, group="criteria", dot_color=stripe_color, zoom=True))

    # The whole visible plot, in the same normalized units (it extends past the data on every side).
    (xl0, xl1), (yl0, yl1) = ax.get_xlim(), ax.get_ylim()
    bx0, by0 = norm(min(xl0, xl1), min(yl0, yl1))
    bx1, by1 = norm(max(xl0, xl1), max(yl0, yl1))   # (swapped ends for a lower-is-better axis -- same rectangle)
    plot_box = [(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)]

    def clip(poly, keep_hi, boundary):
        out = []
        for i in range(len(poly)):
            cur, prev = poly[i], poly[i - 1]
            cs, ps = cur[0] + cur[1], prev[0] + prev[1]
            cur_in = cs >= boundary - 1e-12 if keep_hi else cs <= boundary + 1e-12
            prev_in = ps >= boundary - 1e-12 if keep_hi else ps <= boundary + 1e-12
            if cur_in:
                if not prev_in:
                    t = (boundary - ps) / (cs - ps)
                    out.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
                out.append(cur)
            elif prev_in:
                t = (boundary - ps) / (cs - ps)
                out.append((prev[0] + t * (cur[0] - prev[0]), prev[1] + t * (cur[1] - prev[1])))
        return out

    width = 2.0 / n_bands
    band_hotspots = []
    for b in range(n_bands):
        hi = 2.0 - b * width                  # band b covers nx+ny in [lo, hi] (b = 0 is the best band)
        lo = hi - width
        poly = plot_box
        if b > 0:
            poly = clip(poly, keep_hi=False, boundary=hi)
        if b < n_bands - 1:
            poly = clip(poly, keep_hi=True, boundary=lo)
        if len(poly) < 3:
            continue
        members = [i for i, sv in enumerate(sums)
                   if (b == 0 or sv < hi - 1e-9) and (b == n_bands - 1 or sv >= lo - 1e-9)]
        m_hi, m_lo = round(50 * hi), round(50 * lo)
        names = [str(records[i]["name"]) for i in sorted(members, key=lambda i: -sums[i])]
        shown = ", ".join(_esc(n) for n in names[:5]) + (f" +{len(names) - 5} more" if len(names) > 5 else "")
        tip = (f'<div class="tip-title">{m_lo}-{m_hi}% match</div>'
               f'<div class="tip-stat">{len(members)} {noun}{"s" if len(members) != 1 else ""} in this band</div>'
               + (f'<div class="tip-note">{shown}</div>' if names else ""))
        band_hotspots.append({
            "ax": ax, "shape": "polygon", "points": [denorm(px, py) for px, py in poly],
            "tooltip": tip, "group": "criteria", "fill_color": stripe_color, "rest_level": 0, "dim_level": 0.25,
            "stripe_for": members, "outline": True, "outline_color": stripe_color, "outline_dash": None,
            "outline_always_when_group_active": True, "active_fill": 0.5, "active_stroke": 1.0,
            "mask_players": True,
        })
    # stripe_for indices are positions in the combined list, where the players come first
    return point_hotspots + band_hotspots


# ---------------------------------------------------------------- Box Plot

def box_plot_hotspots(ax, labels, data, names_data=None):
    """
    labels/data: same lists build_box_plot() itself receives (groups.keys()/
    values()), positions 1..N matching matplotlib's own boxplot()
    default positions. Quartiles/whiskers/outliers are computed with
    the same rule matplotlib's boxplot() uses by default (Q1/Q3 via
    linear-interpolated percentiles, whis=1.5xIQR), so the hover
    regions match what was actually drawn rather than an approximation.
    names_data: optional, same shape as data but each entry is the
    player name for that value, so an outlier hover can name who it
    is rather than just showing the number.
    """
    hotspots = []
    for i, (label, values) in enumerate(zip(labels, data), start=1):
        arr = np.asarray(values, dtype=float)
        if len(arr) == 0:
            continue
        names = names_data[i - 1] if names_data else [None] * len(arr)
        q1, med, q3 = np.percentile(arr, [25, 50, 75])
        iqr = q3 - q1
        lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        inlier_mask = (arr >= lo_fence) & (arr <= hi_fence)
        inliers = arr[inlier_mask]
        low = inliers.min() if len(inliers) else arr.min()
        high = inliers.max() if len(inliers) else arr.max()

        tip = (f'<div class="tip-title">{_esc(label)}</div>'
               f'<div class="tip-stat">Low {low:.1f} {MID} Median {med:.1f} {MID} High {high:.1f}</div>'
               f'<div class="tip-note">{len(arr)} players</div>')
        hotspots.append({"ax": ax, "shape": "rect", "x0": i - 0.15, "y0": q1, "x1": i + 0.15, "y1": q3, "tooltip": tip})
        for val, name in zip(arr[~inlier_mask], [n for n, keep in zip(names, inlier_mask) if not keep]):
            who = _esc(name) if name else _esc(label)
            otip = f'<div class="tip-title">{who}</div><div class="tip-stat">{val:.1f}, an outlier on this roster</div>'
            hotspots.append({"ax": ax, "shape": "circle", "x": i, "y": float(val), "r_px": 8, "tooltip": otip})
    return hotspots


# ---------------------------------------------------------------- On/Off column card

def onoff_column_hotspots(ax, columns, column_minutes):
    """
    Mirrors build_onoff_column_image's own layout math exactly (same
    col_width/row_height/header_y/col_centers formulas) so each row's
    hit region sits over the real printed value, not an approximation.
    """
    n_metrics = max(len(columns[0]["metrics"]), 1) if columns else 1
    col_width = 3.2
    row_height = 0.55
    fig_height = 1.8 + n_metrics * row_height
    header_y = fig_height - 1.0
    col_centers = [1.8 + i * col_width + col_width / 2 for i in range(len(columns))]

    hotspots = []
    row_y = header_y - 0.65
    for row_idx in range(n_metrics):
        for col_idx, col in enumerate(columns):
            metrics = col.get("metrics", [])
            if row_idx >= len(metrics):
                continue
            metric_label, value, _, _ = metrics[row_idx]
            if value is None:
                continue
            cx = col_centers[col_idx]
            y = row_y - row_idx * row_height
            mins = column_minutes[col_idx] if col_idx < len(column_minutes) else None
            _, _, pct_change, is_pct = metrics[row_idx]
            shown_val = f"{value:.1%}" if is_pct else f"{value:.1f}"
            tip = (f'<div class="tip-title">{_esc(col.get("label", ""))}</div>'
                   f'<div class="tip-stat">{_esc(metric_label)}: {shown_val}</div>'
                   + (f'<div class="tip-note">{pct_change:+.1f}% vs the team\'s season average</div>'
                      if pct_change is not None else '')
                   + (f'<div class="tip-note">{float(mins):,.0f} minutes sampled</div>' if mins is not None else ''))
            hotspots.append({"ax": ax, "shape": "rect", "x0": cx - col_width / 2 + 0.1, "y0": y - row_height / 2 + 0.05,
                              "x1": cx + col_width / 2 - 0.1, "y1": y + row_height / 2 - 0.05, "tooltip": tip})
    return hotspots


# ---------------------------------------------------------------- Lineup Network (2-man + 3/4/5-man)

def lineup_network_2man_hotspots(ax, pos, edges, value_label, minute_edges=None, league_ranks=None):
    """pos: dict player -> (x, y), as returned by build_network_diagram's
    own return_hotspot_data=True. edges: dict frozenset({a, b}) -> value,
    the SAME cleaned/averaged edges the figure was actually drawn from.
    minute_edges: matching dict frozenset({a, b}) -> minutes together,
    so the hover can explain the line's thickness, not just its color.
    league_ranks: matching dict frozenset({a, b}) -> (rank, pool_size)
    from a real league-wide query, for "#7 best duo in the league"."""
    minute_edges = minute_edges or {}
    league_ranks = league_ranks or {}
    hotspots = []
    by_player = {}
    for pair, v in edges.items():
        a, b = tuple(pair)
        by_player.setdefault(a, []).append((b, v))
        by_player.setdefault(b, []).append((a, v))
    for pair, v in edges.items():
        a, b = tuple(pair)
        if a not in pos or b not in pos:
            continue
        (ax_, ay), (bx, by) = pos[a], pos[b]
        lines = [f"{v:+.1f} {value_label}"]
        mins = minute_edges.get(pair)
        if mins is not None:
            lines.append(f"{mins:,.0f} min together")
        lg_rank = league_ranks.get(pair)
        if lg_rank:
            ord_map = {1: "st", 2: "nd", 3: "rd"}
            suffix = "th" if 11 <= lg_rank[0] % 100 <= 13 else ord_map.get(lg_rank[0] % 10, "th")
            lines.append(f"#{lg_rank[0]}{suffix} best duo in the league out of {lg_rank[1]} qualifying duos")
        tip = stat_line_tip(f"{a} + {b}", lines)
        hotspots.append({"ax": ax, "shape": "path", "points": [(ax_, ay), (bx, by)], "stroke_px": 14, "tooltip": tip})
    for name, (x, y) in pos.items():
        partners = by_player.get(name, [])
        if not partners:
            continue
        best = max(partners, key=lambda t: t[1])
        worst = min(partners, key=lambda t: t[1])
        avg_rating = sum(v for _, v in partners) / len(partners)
        tip = (f'<div class="tip-title">{_esc(name)} {MID} {avg_rating:+.1f} avg {value_label}</div>'
               f'<div class="tip-note">Averaged across their {len(partners)} pairing{"s" if len(partners) != 1 else ""} shown here</div>'
               f'<div class="tip-note">Best with {_esc(best[0])} ({best[1]:+.1f}) {MID} '
               f'worst with {_esc(worst[0])} ({worst[1]:+.1f})</div>')
        hotspots.append({"ax": ax, "shape": "circle", "x": x, "y": y, "r_px": 26, "tooltip": tip})
    return hotspots


def lineup_network_group_hotspots(panel_data, two_man_lookup, value_label, league_ranks=None):
    """panel_data: list of dicts as returned by build_lineup_shapes_diagram's
    own return_hotspot_data=True (players, ax, vertex, centre, rating,
    minutes) -- each group is its OWN small Axes, so hotspots span
    multiple different `ax` objects, unlike every other chart here.
    two_man_lookup: the same dict frozenset({a,b}) -> pairwise rating
    the figure itself was colored from, for real edge/node numbers.
    league_ranks: optional dict players-tuple -> (rank, pool_size) from
    a real league-wide lineup query, for "#7 trio in the league".

    Goes beyond restating the numbers already printed on the diagram:
    ranks each group's rating and minutes against the OTHER groups
    shown here, and ranks each pairwise edge against every other edge
    across all of them -- context the static image doesn't show."""
    hotspots = []
    league_ranks = league_ranks or {}
    ratings = [p["rating"] for p in panel_data]
    minutes_list = [p["minutes"] for p in panel_data if p["minutes"] is not None]
    all_pair_vals = sorted(
        {v for p in panel_data for a, b in _combos(p["players"]) if (v := two_man_lookup.get(frozenset({a, b}))) is not None},
        reverse=True)

    def _rank_of(value, pool, higher_is_better=True):
        pool_sorted = sorted(pool, reverse=higher_is_better)
        try:
            return pool_sorted.index(value) + 1
        except ValueError:
            return None

    for panel in panel_data:
        players, ax, vertex, centre = panel["players"], panel["ax"], panel["vertex"], panel["centre"]
        rating, minutes = panel["rating"], panel["minutes"]
        lines = [f"{rating:+.1f} {value_label}"]
        rank = _rank_of(rating, ratings)
        if rank and len(panel_data) > 1:
            lines.append(f"Rank {rank} of {len(panel_data)} shown here")
        if minutes is not None:
            lines.append(f"{minutes:,.0f} min together")
            m_rank = _rank_of(minutes, minutes_list)
            if m_rank and len(minutes_list) > 1:
                lines.append(f"{'Most' if m_rank == 1 else ('Least' if m_rank == len(minutes_list) else f'{m_rank} of {len(minutes_list)}')} minutes together, of these lineups")
        lg_rank = league_ranks.get(players)
        if lg_rank:
            ord_map = {1: "st", 2: "nd", 3: "rd"}
            suffix = "th" if 11 <= lg_rank[0] % 100 <= 13 else ord_map.get(lg_rank[0] % 10, "th")
            group_word = {2: "duo", 3: "trio", 4: "quad", 5: "5-man lineup"}.get(len(players), f"{len(players)}-man lineup")
            lines.append(f"#{lg_rank[0]}{suffix} best {group_word} in the league out of {lg_rank[1]} qualifying {group_word}s")
        tip = stat_line_tip(" + ".join(players), lines)
        hotspots.append({"ax": ax, "shape": "circle", "x": centre[0], "y": centre[1], "r_px": 30, "tooltip": tip})

        n = len(players)
        by_player = {}
        for i in range(n):
            a, b = players[i], players[(i + 1) % n]
            pair_val = two_man_lookup.get(frozenset({a, b}))
            by_player.setdefault(a, []).append((b, pair_val))
            by_player.setdefault(b, []).append((a, pair_val))
            if a not in vertex or b not in vertex:
                continue
            (ax_, ay), (bx, by) = vertex[a], vertex[b]
            if pair_val is not None:
                edge_lines = [f"{pair_val:+.1f} {value_label}"]
                p_rank = _rank_of(pair_val, all_pair_vals)
                if p_rank and len(all_pair_vals) > 1:
                    edge_lines.append(f"Rank {p_rank} of {len(all_pair_vals)} pairings shown across these lineups")
            else:
                edge_lines = ["Pairwise rating not available"]
            hotspots.append({"ax": ax, "shape": "path", "points": [(ax_, ay), (bx, by)], "stroke_px": 12,
                              "tooltip": stat_line_tip(f"{a} + {b}", edge_lines)})
        for p in players:
            if p not in vertex:
                continue
            partners = [(q, v) for q, v in by_player.get(p, []) if v is not None]
            if partners:
                best = max(partners, key=lambda t: t[1])
                worst = min(partners, key=lambda t: t[1])
                note = f'Best with {_esc(best[0])} ({best[1]:+.1f}) {MID} worst with {_esc(worst[0])} ({worst[1]:+.1f})' \
                    if best[0] != worst[0] else f'Pairs with {_esc(best[0])} at {best[1]:+.1f}'
            else:
                note = "No pairwise data available for this group"
            tip = f'<div class="tip-title">{_esc(p)}</div><div class="tip-note">{note}</div>'
            hotspots.append({"ax": ax, "shape": "circle", "x": vertex[p][0], "y": vertex[p][1], "r_px": 34, "tooltip": tip})
    return hotspots


def _combos(players):
    n = len(players)
    return [(players[i], players[(i + 1) % n]) for i in range(n)]
