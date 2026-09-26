"""
visuals.py (shot chart section)

Ports shot_chart.r's exact logic: made shots in team color, missed
shots in a neutral gray, both with the same dot size and opacity
values as the R version, drawn over the shared court from court.py.
"""

import math
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.text
import matplotlib.colors
import matplotlib.lines
import matplotlib.patches
import matplotlib.collections
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import urllib.request
import io
from PIL import Image
from court import new_court_figure, draw_court

# Exact values from settings.json's shot_chart + colors sections,
# confirmed against the real file rather than guessed
DOT_SIZE = 1.4 * 10  # R's geom_point size scales differently than matplotlib's s= parameter; *10 is a reasonable visual match, tuned by eye against the R output
MISSED_SHOT_OPACITY = 0.75
MADE_SHOT_OPACITY = 1.0
MISSED_SHOT_COLOR = "#9A9A9A"


def recolor_white_text(fig, target_color):
    """
    Walks every Text, Line2D, and Patch object in an already-built
    figure and flips any that are exactly pure white over to
    target_color, leaving everything else (team colors, muted greys
    like "#999999", semantic red/green delta indicators) untouched --
    confirmed directly via isolated testing that this selectivity
    works correctly before wiring it in anywhere, since a blanket
    recolor would also wreck the very red/green/team-color
    distinctions several charts rely on to convey meaning.

    Covers Line2D (court lines, plot lines -- e.g. draw_court()'s own
    white court markings) and Patch (rectangle/circle edges) in
    addition to Text (axis labels, titles, tick labels, legend text),
    not just text, since "black" is meant to mean "anywhere there's
    white, it's now black" -- a court chart with black text but still-
    white court lines wouldn't actually look any different on a light
    background, which is the whole point of this toggle.

    This is a deliberately external, post-hoc approach rather than
    threading a text_color parameter through every individual chart-
    building function's internals -- every chart in this app hardcodes
    color="white" directly on dozens of individual ax.text()/
    set_xlabel()/tick_params()/ax.plot() calls, and touching all of
    them individually across ~20 functions would be a large, high-risk
    change for what is fundamentally a single, mechanical
    "white becomes black" substitution once the figure already exists.

    A no-op when target_color is "white" (the default), so this is
    always safe to call unconditionally.
    """
    if target_color == "white":
        return

    def _is_white(color):
        try:
            return matplotlib.colors.to_rgba(color)[:3] == (1.0, 1.0, 1.0)
        except (ValueError, TypeError):
            return False

    for text_obj in fig.findobj(matplotlib.text.Text):
        if _is_white(text_obj.get_color()):
            text_obj.set_color(target_color)

    for line_obj in fig.findobj(matplotlib.lines.Line2D):
        if _is_white(line_obj.get_color()):
            line_obj.set_color(target_color)
        if _is_white(line_obj.get_markeredgecolor()):
            line_obj.set_markeredgecolor(target_color)
        if _is_white(line_obj.get_markerfacecolor()):
            line_obj.set_markerfacecolor(target_color)

    for patch_obj in fig.findobj(matplotlib.patches.Patch):
        if _is_white(patch_obj.get_edgecolor()):
            patch_obj.set_edgecolor(target_color)
        if _is_white(patch_obj.get_facecolor()):
            patch_obj.set_facecolor(target_color)

    # ax.scatter() returns a PathCollection, a completely different
    # object type from Line2D/Patch with its own array-based (one
    # color per point, not a single value) get/set_edgecolor and
    # get/set_facecolor -- confirmed via direct search that several
    # charts use a white edgecolor or facecolor on scatter markers
    # (e.g. a white-bordered highlight dot), none of which the Line2D/
    # Patch coverage above would ever touch.
    for collection_obj in fig.findobj(matplotlib.collections.Collection):
        edge_colors = collection_obj.get_edgecolor()
        if len(edge_colors) and any(_is_white(c) for c in edge_colors):
            new_edge = [target_color if _is_white(c) else c for c in edge_colors]
            collection_obj.set_edgecolor(new_edge)
        face_colors = collection_obj.get_facecolor()
        if len(face_colors) and any(_is_white(c) for c in face_colors):
            new_face = [target_color if _is_white(c) else c for c in face_colors]
            collection_obj.set_facecolor(new_face)


def build_shot_chart(shots_df, team_color, width=6, height=5):
    """
    shots_df: DataFrame with LOC_X, LOC_Y, SHOT_MADE_FLAG columns
    (the raw columns nba_api's ShotChartDetail returns).
    """
    fig, ax = new_court_figure(width=width, height=height)

    made = shots_df[shots_df["SHOT_MADE_FLAG"] == 1]
    missed = shots_df[shots_df["SHOT_MADE_FLAG"] == 0]

    ax.scatter(
        missed["LOC_X"], missed["LOC_Y"],
        s=DOT_SIZE, color=MISSED_SHOT_COLOR, alpha=MISSED_SHOT_OPACITY,
        edgecolors="none", zorder=2
    )
    ax.scatter(
        made["LOC_X"], made["LOC_Y"],
        s=DOT_SIZE, color=team_color, alpha=MADE_SHOT_OPACITY,
        edgecolors="none", zorder=3
    )

    draw_court(ax, color="white", lw=1.2)

    return fig


def _lighten_color(hex_color, amount=0.15):
    """Matches heat_map.r's lighten_color() exactly -- blends toward white by `amount`."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4))
    r = r + (1 - r) * amount
    g = g + (1 - g) * amount
    b = b + (1 - b) * amount
    return (r, g, b)


def build_heat_map(shots_df, team_color, width=6, height=5, grid_resolution=200, return_hotspot_data=False):
    """
    Ports heat_map.r's stat_density_2d logic: a 2D kernel density
    estimate of shot locations, colored from a lightened team color
    (low density) to the full team color (high density).

    Note: the R version's scale_alpha_continuous used range=c(0,5),
    which is invalid (alpha is only ever valid in [0,1] -- values
    above 1 just clamp to fully opaque). This uses a proper [0,1]
    range instead, normalized so the highest-density point reaches
    full opacity, matching the R version's visual intent without
    carrying over the invalid math.
    """
    from scipy.stats import gaussian_kde
    from matplotlib.colors import LinearSegmentedColormap

    fig, ax = new_court_figure(width=width, height=height)

    x = shots_df["LOC_X"].values
    y = shots_df["LOC_Y"].values

    # gaussian_kde needs at least 2 DISTINCT points to compute a
    # covariance matrix at all -- a player/team with only one shot in
    # the selected range (or a data hiccup returning an empty frame)
    # would otherwise crash the whole page instead of just this chart.
    if len(x) < 2 or (np.unique(x).size == 1 and np.unique(y).size == 1):
        ax.text(0, 150, "Not enough shots in this range to build a density map.",
                color="white", ha="center", va="center", fontsize=11, wrap=True)
        draw_court(ax, color="white", lw=1.2)
        fig.tight_layout()
        if return_hotspot_data:
            return fig, None
        return fig

    xx, yy = np.mgrid[-250:250:complex(0, grid_resolution), -60:356.7:complex(0, grid_resolution)]
    positions = np.vstack([xx.ravel(), yy.ravel()])
    values = np.vstack([x, y])
    kernel = gaussian_kde(values)
    density = np.reshape(kernel(positions), xx.shape)

    # Normalize density to [0, 1] for a valid alpha range
    density_range = density.max() - density.min()
    density_norm = (density - density.min()) / density_range if density_range > 0 else np.zeros_like(density)

    light_rgb = _lighten_color(team_color)
    full_rgb = tuple(int(team_color.lstrip("#")[i:i+2], 16) / 255 for i in (0, 2, 4))
    cmap = LinearSegmentedColormap.from_list("team_heat", [light_rgb, full_rgb])

    # Raw normalized density used directly as alpha (the original
    # version) was reasonably close already -- the request was for
    # "slightly more opacity" on the real fog, not a different shape
    # entirely. A first attempt at "slightly more" used a sqrt curve,
    # but that changes the shape of the falloff (boosting low-density
    # areas disproportionately more than high-density ones) rather
    # than uniformly scaling it up, and ended up visibly tinting most
    # of the court instead of just the real shot clusters. A flat
    # multiplier on the original values, clipped so the hottest point
    # never exceeds fully opaque, preserves the original contrast
    # between "real shot area" and "essentially no shots" while still
    # making the genuine fog areas modestly more visible.
    density_alpha = np.clip(density_norm * 1.6, 0, 1)

    ax.imshow(
        density_norm.T,
        extent=(-250, 250, -60, 356.7),
        origin="lower",
        cmap=cmap,
        alpha=density_alpha.T,
        aspect="auto",
        zorder=1,
    )

    draw_court(ax, color="white", lw=1.2)

    if return_hotspot_data:
        # The exact density grid just drawn (not a re-computation), so the hover outlines in hotspots.py trace the
        # same fog a person sees.
        return fig, {"xx": xx, "yy": yy, "density": density_norm}
    return fig


def build_hex_shot_chart(
    shots_df, comparison_shots_df, team_color,
    width=6, height=5, xbins=25,
    min_radius=1.5, max_radius=9,
    below_avg_alpha=0.75, above_avg_alpha=1.0,
    efficiency_saturation=0.15,
    below_avg_color="#373737",
    min_zone_fga=0,
    return_hotspot_data=False,
):
    """
    Ports hex_shot_chart.r's core logic exactly: bins both the
    subject's shots and league-wide shots into the SAME hex grid
    (fixed real fix from an earlier version -- using mincnt=0 so both
    datasets produce an identical, deterministic 740-cell grid in the
    same positions every time, rather than mincnt=1's behavior of
    only returning non-empty cells, which produces a DIFFERENT subset
    of grid positions depending on the data and made subject/league
    hexes uncomparable), computes each hex's FG% relative to the
    league average from that same spot, and colors each hex from
    below_avg_color through team_color, sized by shot volume.

    Also ports the real zone-label system: 8 curated zones (matching
    the R version's zone_bucket() grouping of SHOT_ZONE_BASIC /
    SHOT_ZONE_AREA), each showing "makes/attempts\\nsubject% / league%"
    at a fixed position, exactly matching zone_positions in the R file.
    """
    from matplotlib.patches import RegularPolygon
    import matplotlib.patheffects as pe

    fig, ax = new_court_figure(width=width, height=height)

    x = shots_df["LOC_X"].values
    y = shots_df["LOC_Y"].values
    made = shots_df["SHOT_MADE_FLAG"].values

    lx = comparison_shots_df["LOC_X"].values
    ly = comparison_shots_df["LOC_Y"].values
    lmade = comparison_shots_df["SHOT_MADE_FLAG"].values

    extent = (-250, 250, -60, 356.7)

    # mincnt=0 is the real fix -- returns the FULL grid every time,
    # identically positioned regardless of the underlying data, so
    # subject and league hexes at the same index really are the same
    # physical cell. mincnt=1 (the earlier, buggy version) only
    # returns non-empty cells, which differs between datasets.
    subject_counts_hb = ax.hexbin(x, y, gridsize=xbins, extent=extent, mincnt=0, visible=False)
    subject_makes_hb = ax.hexbin(x, y, C=made, reduce_C_function=np.sum, gridsize=xbins, extent=extent, mincnt=0, visible=False)
    league_counts_hb = ax.hexbin(lx, ly, gridsize=xbins, extent=extent, mincnt=0, visible=False)
    league_makes_hb = ax.hexbin(lx, ly, C=lmade, reduce_C_function=np.sum, gridsize=xbins, extent=extent, mincnt=0, visible=False)

    offsets = subject_counts_hb.get_offsets()
    fga = subject_counts_hb.get_array()
    fgm = np.nan_to_num(subject_makes_hb.get_array())
    league_fga = league_counts_hb.get_array()
    league_fgm = np.nan_to_num(league_makes_hb.get_array())

    below_rgb = np.array([int(below_avg_color.lstrip("#")[i:i+2], 16) / 255 for i in (0, 2, 4)])
    team_rgb = np.array([int(team_color.lstrip("#")[i:i+2], 16) / 255 for i in (0, 2, 4)])

    # Matches the R original's percent_rank(fga) exactly: each drawn hex's
    # size is based on its RANK/PERCENTILE among the OTHER drawn hexes,
    # not a raw linear ratio to the single highest-volume hex. Confirmed
    # as a real bug in an earlier version of this port: basketball shot
    # data is heavily skewed (the paint has vastly more attempts per cell
    # than anywhere else), so scaling linearly against that one outlier
    # crushed every other hex down toward min_radius, rendering as
    # near-invisible dots everywhere except the paint. Scoped to only the
    # hexes that will actually be drawn (fga >= the same threshold used
    # below) -- R's hexbin() only ever returns non-empty cells to begin
    # with, unlike this port's deliberate mincnt=0 (needed for a matching
    # subject/league grid), so ranking across the full zero-padded array
    # here would dilute the percentiles of the real, visible hexes.
    draw_threshold = max(2, min_zone_fga)
    drawable = fga >= draw_threshold
    percentile_rank = np.zeros_like(fga, dtype=float)
    if drawable.any():
        percentile_rank[drawable] = pd.Series(fga[drawable]).rank(pct=True).values

    hex_records = []
    for i, (cx, cy) in enumerate(offsets):
        if fga[i] < draw_threshold:
            continue

        fg_pct = fgm[i] / fga[i]
        league_pct = (league_fgm[i] / league_fga[i]) if league_fga[i] > 0 else fg_pct
        diff = fg_pct - league_pct

        t = min(max((diff + efficiency_saturation) / (2 * efficiency_saturation), 0), 1)
        color = tuple(below_rgb + (team_rgb - below_rgb) * t)
        alpha = below_avg_alpha + (above_avg_alpha - below_avg_alpha) * t

        size_factor = percentile_rank[i]
        radius = min_radius + (max_radius - min_radius) * size_factor

        hexagon = RegularPolygon(
            (cx, cy), numVertices=6, radius=radius,
            orientation=0, facecolor=color, alpha=alpha, edgecolor="none",
            zorder=2 + (1 - radius / max_radius),
        )
        ax.add_patch(hexagon)
        # Collected only for the optional interactive-hover overlay
        # (render_interactive_chart in interactive.py) -- doesn't
        # change anything about the hexagon just drawn above.
        if return_hotspot_data:
            hex_records.append({
                "cx": float(cx), "cy": float(cy), "radius": float(radius),
                "fga": int(fga[i]), "fgm": int(fgm[i]),
                "league_fga": int(league_fga[i]), "league_fgm": int(league_fgm[i]),
            })

    draw_court(ax, color="white", lw=1.2)

    # ---------------------------------------------------------- Zone labels
    # Exact zone_bucket() groupings and zone_positions from hex_shot_chart.r
    zone_bucket_map = {
        ("Above the Break 3", "Center(C)"): "top_3",
        ("Above the Break 3", "Left Side Center(LC)"): "left_wing_3",
        ("Above the Break 3", "Right Side Center(RC)"): "right_wing_3",
        ("Left Corner 3", None): "left_corner_3",
        ("Right Corner 3", None): "right_corner_3",
        ("Mid-Range", "Left Side(L)"): "left_mid",
        ("Mid-Range", "Left Side Center(LC)"): "left_mid",
        ("Mid-Range", "Right Side(R)"): "right_mid",
        ("Mid-Range", "Right Side Center(RC)"): "right_mid",
        ("Restricted Area", None): "paint",
        ("In The Paint (Non-RA)", None): "paint",
        ("Mid-Range", "Center(C)"): "paint",
    }

    def bucket(basic, area):
        if (basic, None) in zone_bucket_map:
            return zone_bucket_map[(basic, None)]
        return zone_bucket_map.get((basic, area))

    zone_positions = {
        "top_3": (0, 290, "center"),
        "left_wing_3": (-155, 230, "center"),
        "right_wing_3": (155, 230, "center"),
        "left_mid": (-145, 110, "center"),
        "right_mid": (145, 110, "center"),
        "paint": (0, 40, "center"),
        "left_corner_3": (-240, 15, "left"),
        "right_corner_3": (240, 15, "right"),
    }

    def zone_stats(df):
        zones = {}
        if "SHOT_ZONE_BASIC" not in df.columns or "SHOT_ZONE_AREA" not in df.columns:
            return zones
        for _, row in df.iterrows():
            z = bucket(row["SHOT_ZONE_BASIC"], row["SHOT_ZONE_AREA"])
            if z is None:
                continue
            if z not in zones:
                zones[z] = {"fga": 0, "fgm": 0}
            zones[z]["fga"] += 1
            zones[z]["fgm"] += int(row["SHOT_MADE_FLAG"])
        return zones

    subject_zones = zone_stats(shots_df)
    league_zones = zone_stats(comparison_shots_df)

    for zone, (lx_pos, ly_pos, ha) in zone_positions.items():
        if zone not in subject_zones or subject_zones[zone]["fga"] < min_zone_fga:
            continue
        s = subject_zones[zone]
        l = league_zones.get(zone, {"fga": 0, "fgm": 0})
        fg_pct = s["fgm"] / s["fga"] * 100
        league_pct = (l["fgm"] / l["fga"] * 100) if l["fga"] > 0 else 0

        label = f"{s['fgm']}/{s['fga']}\n{fg_pct:.1f}% / {league_pct:.1f}%"
        ax.text(
            lx_pos, ly_pos, label, color="white", fontweight="bold",
            fontsize=9, ha=ha, va="center", linespacing=0.85, zorder=10,
        )

    # ---------------------------------------------------------- Legend
    # Sits in the gap between the paint and the corner 3 on each side,
    # within the court's own existing bounds -- an earlier version
    # placed this below the court's baseline instead, which required
    # extending the y-axis limits and made the whole image visibly
    # taller than the original reference. Each side is one single
    # horizontal line (down-arrow, three hexagons, up-arrow) -- an
    # earlier version stacked these three elements into separate lines
    # instead, which is the "three lines" bug this replaces. Left
    # side: three hexagons shading from below_avg_color to team_color
    # for the FG% (color) scale. Right side: three hexagons at 25%,
    # 50%, and 75% of the size range for the FGA (size) scale -- an
    # earlier version used 0%/50%/100%, which made the size jump
    # between the smallest and largest hexagon look far more drastic
    # than intended.
    left_x, right_x = -150, 150
    label_y = -30
    # FG% legend: only color varies (below-average to above-average
    # shading), so all 3 hexagons are the same fixed size -- size on
    # the actual chart represents shot volume (FGA), not accuracy, so
    # varying size here would misrepresent what this specific legend
    # encodes. A uniform, smaller size also needs far less horizontal
    # spacing than the varying-size case below.
    fg_pct_offsets = [-11, 0, 11]
    fg_pct_radius = 4.5

    ax.text(left_x - 20, label_y, "\u2193 FG%", color="white", fontsize=7.5, ha="right", va="center")
    for i, off in enumerate(fg_pct_offsets):
        t = i / (len(fg_pct_offsets) - 1)
        color = tuple(below_rgb + (team_rgb - below_rgb) * t)
        hexagon = RegularPolygon((left_x + off, label_y), numVertices=6, radius=fg_pct_radius, orientation=0,
                                  facecolor=color, edgecolor="none")
        ax.add_patch(hexagon)
    ax.text(left_x + 16, label_y, "\u2191 FG%", color="white", fontsize=7.5, ha="left", va="center")

    # FGA legend: size varies (representing shot volume), color is
    # fixed at the team's own color -- accounts for the LARGER of the
    # two hexagons' actual sizes here (min_radius=1.5/max_radius=9
    # means the two largest, at 50%/75% of that range, reach radii
    # 5.25 and 7.125, a combined 12.375 units), confirmed as the actual
    # cause of a previously reported overlap.
    fga_offsets = [-22, -11, 3]

    ax.text(right_x - 29, label_y, "\u2193 FGA", color="white", fontsize=7.5, ha="right", va="center")
    for i, off in enumerate(fga_offsets):
        t = 0.25 + 0.25 * i  # 25%, 50%, 75% of the size range, not 0%/50%/100%
        r = min_radius + (max_radius - min_radius) * t
        hexagon = RegularPolygon((right_x + off, label_y), numVertices=6, radius=r, orientation=0,
                                  facecolor=team_color, edgecolor="none")
        ax.add_patch(hexagon)
    ax.text(right_x + 12, label_y, "\u2191 FGA", color="white", fontsize=7.5, ha="left", va="center")

    if return_hotspot_data:
        return fig, hex_records
    return fig


_IMAGE_CACHE = {}          # url -> (fetched_at, PIL image or None)
_IMAGE_CACHE_MAX = 600
_FAILED_IMAGE_RETRY_SECONDS = 120
_IMAGE_SEP = "||"          # several candidate addresses in one string, best first (see teams.py)
_IMAGE_UA = "BradleyAnalytics/1.0 (NBA analytics dashboard)"
_HOST_FAIL_LIMIT = 3       # consecutive failures before a host is set aside...
_HOST_BLOCK_SECONDS = 600  # ...for this long
_HOST_STATE = {}           # host -> [consecutive_failures, blocked_until]


def _url_host(url):
    from urllib.parse import urlparse
    return urlparse(url).netloc


def _host_is_blocked(host):
    import time
    state = _HOST_STATE.get(host)
    return bool(state and state[1] > time.time())


def _record_host_result(host, ok):
    import time
    state = _HOST_STATE.setdefault(host, [0, 0.0])
    if ok:
        state[0], state[1] = 0, 0.0
        return
    state[0] += 1
    if state[0] >= _HOST_FAIL_LIMIT:
        state[0], state[1] = 0, time.time() + _HOST_BLOCK_SECONDS


_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/124.0.0.0 Safari/537.36")


def _headers_for(url):
    """Headers for an image request. 2kratings.com is asked the way a browser on its own site would ask (a bare script
    user-agent is the usual reason a site refuses an image); every other host keeps the app's own user-agent."""
    if _url_host(url).endswith("2kratings.com"):
        return {"User-Agent": _BROWSER_UA, "Referer": "https://www.2kratings.com/", "Accept-Language": "en-US,en;q=0.9",
                "Accept": "image/svg+xml,image/avif,image/webp,image/png,image/*;q=0.8,*/*;q=0.5"}
    return {"User-Agent": _IMAGE_UA}


def _rasterize_svg(svg_bytes, size=500):
    """SVG -> PNG bytes at `size` px on its long side, keeping the drawing's own shape (needs the system cairo library)."""
    import cairosvg
    from io import BytesIO
    png = cairosvg.svg2png(bytestring=svg_bytes, output_width=size)
    if Image.open(BytesIO(png)).height > size:
        png = cairosvg.svg2png(bytestring=svg_bytes, output_height=size)
    return png


def _download_image(url):
    """
    One address -> a PIL image, or None. A 404 only means "that file isn't there" (e.g. a name spelled differently)
    and does not count against the host; timeouts, connection errors and 403/429/5xx do, so a source that blocks
    servers or is down gets set aside instead of being waited on for every single image.
    """
    import requests
    from io import BytesIO
    host = _url_host(url)
    try:
        response = requests.get(url, timeout=(3, 6), headers=_headers_for(url))
    except Exception:
        _record_host_result(host, False)
        return None
    if response.status_code in (404, 410):
        return None
    if response.status_code != 200:
        _record_host_result(host, False)
        return None
    _record_host_result(host, True)
    content = response.content
    raw_svg = content
    try:
        if url.lower().endswith(".svg") or content.lstrip()[:5] in (b"<?xml", b"<svg ", b"<svg>"):
            import cairosvg     # needs the system cairo library (packages.txt); if it is missing this candidate is skipped
            content = _rasterize_svg(raw_svg)
        img = Image.open(BytesIO(content)).convert("RGBA")
    except Exception:
        return None
    return img if min(img.size) >= 16 else None      # an error page or a 1px placeholder is not a picture


def _fetch_image(url):
    """
    Downloads an image for use in a chart -- returns None on any failure so a missing headshot doesn't crash the
    whole chart. `url` may hold several candidate addresses joined by "||" (best first); the first that loads wins,
    e.g. a 2kratings.com player image with the NBA's official headshot behind it.

    Results are cached in-process (per url string). Streamlit reruns the whole script on every widget interaction and
    the same headshots/logos are requested again each time; a failure is remembered for two minutes so a dead
    address isn't retried (and waited on) repeatedly, while a transient failure still heals itself.
    """
    import time
    if not url or not isinstance(url, str):
        return None
    now = time.time()
    hit = _IMAGE_CACHE.get(url)
    if hit is not None:
        fetched_at, img = hit
        if img is not None or now - fetched_at < _FAILED_IMAGE_RETRY_SECONDS:
            return img
    candidates = [u for u in url.split(_IMAGE_SEP) if u]
    img = None
    for i, candidate in enumerate(candidates):
        is_last = i == len(candidates) - 1
        if _host_is_blocked(_url_host(candidate)) and not is_last:
            continue                      # that source keeps failing -- go straight to the next one
        img = _download_image(candidate)
        if img is not None:
            break
    if len(_IMAGE_CACHE) >= _IMAGE_CACHE_MAX:
        _IMAGE_CACHE.pop(next(iter(_IMAGE_CACHE)))
    _IMAGE_CACHE[url] = (now, img)
    return img


_LOGO_SVG_MAX_BYTES = 90_000


def _safe_svg(content: bytes) -> bool:
    """A real, self-contained SVG: parses as XML, has an <svg> root, and carries nothing executable or external."""
    low = content.lower()
    if b"<svg" not in low[:4000] or b"<script" in low or b"<foreignobject" in low or b"onload=" in low:
        return False
    try:
        import xml.etree.ElementTree as ET
        return ET.fromstring(content).tag.lower().endswith("svg")
    except Exception:
        return False


def fetch_logo_source(url_chain):
    """
    The best available logo from a chain of candidate URLs (best first), as (kind, payload, source_url, index):
      ("svg", <the SVG's own bytes>, ...)  when the SVG is small and safe -- a browser draws it natively, so nothing on the
                                             server has to render it and it looks exactly like the file on the site;
      ("png", <PNG bytes>, ...)            otherwise (a raster logo, or a big SVG rendered with the system cairo library).
    `index` is which candidate won (0 = the preferred source), so a caller can tell a real hit from a fallback. None if no
    candidate works. Each candidate gets one retry for a timeout or server error; a 404 moves straight on.
    """
    import requests
    from io import BytesIO
    candidates = [u for u in str(url_chain or "").split(_IMAGE_SEP) if u]
    for i, url in enumerate(candidates):
        host = _url_host(url)
        if _host_is_blocked(host) and i < len(candidates) - 1:
            continue
        content = None
        for _attempt in (1, 2):
            try:
                r = requests.get(url, timeout=(3, 8), headers=_headers_for(url))
            except Exception:
                _record_host_result(host, False)
                continue
            if r.status_code in (404, 410):
                break
            if r.status_code != 200:
                _record_host_result(host, False)
                continue
            _record_host_result(host, True)
            content = r.content
            break
        if not content:
            continue
        if url.lower().endswith(".svg") or content.lstrip()[:5] in (b"<?xml", b"<svg ", b"<svg>"):
            if not _safe_svg(content):
                continue
            if len(content) <= _LOGO_SVG_MAX_BYTES:
                return ("svg", content, url, i)
            try:
                return ("png", _rasterize_svg(content), url, i)
            except Exception:
                continue
        try:
            img = Image.open(BytesIO(content)).convert("RGBA")
            if min(img.size) < 16:
                continue
            buf = BytesIO()
            img.save(buf, "PNG")
            return ("png", buf.getvalue(), url, i)
        except Exception:
            continue
    return None


def prefetch_images(urls, workers=8):
    """Warm the image cache in parallel -- a lineup chart with dozens of headshots otherwise downloads them one by one."""
    from concurrent.futures import ThreadPoolExecutor
    todo = [u for u in dict.fromkeys(u for u in urls if isinstance(u, str) and u) if u not in _IMAGE_CACHE]
    if len(todo) < 2:
        return
    with ThreadPoolExecutor(max_workers=min(workers, len(todo))) as pool:
        list(pool.map(_fetch_image, todo))


def figure_has_images(fig):
    """True if the chart already draws logos/headshots of its own (so a team badge would be a duplicate)."""
    from matplotlib.offsetbox import OffsetImage
    return bool(fig.images) or bool(fig.findobj(OffsetImage))


def stamp_team_logos(fig, urls, max_logos=2):
    """
    Puts the team logo (two for a two-team chart) directly above the chart's actual content -- measured, not the
    figure's raw edge, so there is no blank band between them. If the figure has no room above the content it grows
    taller; the chart itself is never resized, moved or overlapped. Returns False (and does nothing) if no logo loads.
    """
    imgs = [im for im in (_fetch_image_small(u, 400) for u in list(urls)[:max_logos]) if im is not None]
    if not imgs:
        return False
    w, h = fig.get_size_inches()
    try:
        bb = fig.get_tightbbox(fig.canvas.get_renderer())      # inches, from the bottom-left of the figure
        cx0, cx1, cy1 = float(bb.x0), float(bb.x1), float(bb.y1)
    except Exception:
        cx0, cx1, cy1 = 0.0, float(w), float(h)
    logo_h = float(np.clip(0.12 * max(cx1 - cx0, cy1), 0.55, 1.0))
    gap = 0.08
    new_h = max(float(h), cy1 + gap + logo_h)
    if new_h > h + 1e-9:
        k = h / new_h                       # grow upward: every existing figure-fraction y shrinks by this, so nothing moves
        fig.set_size_inches(w, new_h)
        for ax in list(fig.axes):
            pos = ax.get_position(original=True)
            ax.set_position([pos.x0, pos.y0 * k, pos.width, pos.height * k])
        for t in fig.texts:
            if t.get_transform() == fig.transFigure:
                x, y = t.get_position()
                t.set_position((x, y * k))
    for i, img in enumerate(imgs):
        logo_w = logo_h * img.width / max(img.height, 1)
        left = (cx0 + cx1) / 2 - logo_w / 2 if len(imgs) == 1 else (cx0 if i == 0 else cx1 - logo_w)
        lax = fig.add_axes([left / w, (cy1 + gap) / new_h, logo_w / w, logo_h / new_h])
        lax.imshow(np.array(img))
        lax.axis("off")
    fig._ba_badged = True
    return True


def _fetch_image_small(url, max_px=300):
    """Same as _fetch_image but downscaled (cached) -- for charts that draw many
    small copies of a headshot, where the full 1040x760 original is wasted work."""
    key = (url, max_px)
    hit = _IMAGE_CACHE.get(key)
    if hit is not None:
        return hit[1]
    img = _fetch_image(url)
    if img is not None:
        img = img.copy()
        img.thumbnail((max_px, max_px))
    if len(_IMAGE_CACHE) >= _IMAGE_CACHE_MAX:
        _IMAGE_CACHE.pop(next(iter(_IMAGE_CACHE)))
    import time
    _IMAGE_CACHE[key] = (time.time(), img)
    return img


def build_scatter_plot(
    scatter_df, stat_label_y, stat_label_x,
    image_size=0.2, highlighted_multiplier=1.0,
    width=8, height=8, dot_color=None, return_hotspot_data=False,
):
    """
    Ports scatter_plot.r's core logic: player headshots or team logos
    plotted at (x_value, y_value), with included/highlighted entities
    rendered larger (matching is_included's size-based highlighting --
    the R version's color-based highlighting only applies to the rare
    text-label fallback, which isn't needed here since every entity
    has a real image URL).

    scatter_df needs columns: x_value, y_value, image_url, is_included, name
    """
    prefetch_images(scatter_df["image_url"].tolist() if "image_url" in scatter_df.columns else [])
    from matplotlib.offsetbox import OffsetImage, AnnotationBbox

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    fig.patch.set_edgecolor("none")
    fig.patch.set_linewidth(0)
    ax.set_facecolor("none")

    x_range = scatter_df["x_value"].max() - scatter_df["x_value"].min()
    y_range = scatter_df["y_value"].max() - scatter_df["y_value"].min()
    ax.set_xlim(
        scatter_df["x_value"].min() - x_range * 0.12,
        scatter_df["x_value"].max() + x_range * 0.12,
    )
    ax.set_ylim(
        scatter_df["y_value"].min() - y_range * 0.12,
        scatter_df["y_value"].max() + y_range * 0.12,
    )

    # One record per row, in row order, for the optional hover overlay: which rows really ended up drawn as a
    # headshot/logo (and that artist, so the overlay can use its exact drawn box) versus a plain dot.
    hotspot_records = []
    for _, row in scatter_df.iterrows():
        show_image = bool(row.get("show_image", True))
        img = _fetch_image(row["image_url"]) if show_image and row.get("image_url") else None
        if img is None:
            # A real, explicit dot color (the user's own chosen color)
            # always wins; falling back to the old gold/gray-by-inclusion
            # scheme only when the caller never set one.
            this_dot_color = dot_color or ("#D4AF37" if row.get("is_included", False) else "#B5B5B5")
            ax.scatter(row["x_value"], row["y_value"], color=this_dot_color, s=55, zorder=3)
            hotspot_records.append({"name": row["name"], "x": float(row["x_value"]), "y": float(row["y_value"]),
                                    "artist": None, "image": None, "color": this_dot_color})
            if not show_image:
                continue  # a deliberately-unchecked player stays a plain dot, no name label crowding the plot
            ax.annotate(
                row["name"], (row["x_value"], row["y_value"]),
                fontsize=8, color="white", ha="center", va="bottom", zorder=4
            )
            continue

        size = 0.045 * (highlighted_multiplier if row.get("is_included", False) else 1.0)
        imagebox = OffsetImage(img, zoom=size)
        ab = AnnotationBbox(
            imagebox, (row["x_value"], row["y_value"]),
            frameon=False, zorder=3
        )
        ax.add_artist(ab)
        hotspot_records.append({"name": row["name"], "x": float(row["x_value"]), "y": float(row["y_value"]),
                                "artist": ab, "image": img, "color": None})

    ax.set_xlabel(stat_label_x, color="white", fontsize=12)
    ax.set_ylabel(stat_label_y, color="white", fontsize=12)
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)

    if return_hotspot_data:
        return fig, hotspot_records
    return fig


def build_bar_chart(
    axis_df, stat_display_name, season, top_n, team_color,
    included_names=None, orientation="vertical",
    stat_source="base", is_percentage=False,
    width=8, height=7.5, rank_ascending=False,
):
    """
    Ports bar_chart.r's core logic: bars colored by team accent color
    (or neutral gray for non-included entities), a Y-axis title
    matching the exact "Top N [stat] leaders [season]" phrasing
    (skipping "per game" for bio/bradley_rating stats, same as the R
    version's per_game_phrase logic), and value labels above each bar.

    axis_df needs columns: name, value, is_included, image_url
    (image_url required for headshots/logos to actually render --
    falls back to rotated text names for any row where the image
    fails to load).
    """
    prefetch_images(axis_df["image_url"].tolist() if "image_url" in axis_df.columns else [])
    from matplotlib.offsetbox import OffsetImage, AnnotationBbox

    included_names = included_names or []
    neutral_color = "#B5B5B5"

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    fig.patch.set_edgecolor("none")
    fig.patch.set_linewidth(0)
    ax.set_facecolor("none")

    df = axis_df.sort_values("value", ascending=(orientation == "horizontal")).reset_index(drop=True)
    colors = [team_color if row["is_included"] else neutral_color for _, row in df.iterrows()]

    positions = range(len(df))
    max_val = df["value"].max()

    if orientation == "vertical":
        ax.bar(positions, df["value"], color=colors, edgecolor="white", linewidth=0.4)
    else:
        ax.barh(positions, df["value"], color=colors, edgecolor="white", linewidth=0.4)

    # Value labels above (or right of, for horizontal) each bar -- one decimal for small numbers (steals, net
    # rating, per-game counts under 20), where rounding to a whole number would hide the differences
    small = float(df["value"].abs().max() or 0) < 20
    for i, val in enumerate(df["value"]):
        label = f"{val:.1%}" if is_percentage else (f"{val:,.1f}" if small else f"{val:,.0f}")
        if orientation == "vertical":
            ax.text(i, val + max_val * 0.02, label, ha="center", color="white", fontweight="bold", fontsize=10)
        else:
            ax.text(val + max_val * 0.02, i, label, va="center", color="white", fontweight="bold", fontsize=10)

    # Headshots/logos below (or left of, for horizontal) each bar,
    # falling back to a rotated text name only if the image genuinely
    # fails to load
    has_image_col = "image_url" in df.columns
    for i, row in df.iterrows():
        img = _fetch_image(row["image_url"]) if has_image_col else None

        if img is not None:
            imagebox = OffsetImage(img, zoom=0.045)
            if orientation == "vertical":
                xy, box_alignment = (i, -max_val * 0.06), (0.5, 1)
            else:
                xy, box_alignment = (-max_val * 0.06, i), (1, 0.5)
            ab = AnnotationBbox(
                imagebox, xy, frameon=False, box_alignment=box_alignment,
                annotation_clip=False, zorder=4
            )
            ax.add_artist(ab)
        else:
            if orientation == "vertical":
                ax.text(i, -max_val * 0.04, row["name"], rotation=30, ha="right", va="top", color="white", fontsize=9)
            else:
                ax.text(-max_val * 0.02, i, row["name"], ha="right", va="center", color="white", fontsize=9)

    ax.set_xticks([])
    ax.set_yticks([]) if orientation == "vertical" else None
    if orientation == "horizontal":
        ax.set_xticks([])
        ax.set_yticks([])

    # Exact Y-axis title phrasing from bar_chart.r, including the
    # per-game exception for bio/bradley_rating stats
    per_game_phrase = "" if stat_source in ("bio", "bradley_rating") else " per game"
    rank_word = "Lowest" if rank_ascending else "Top"
    title = f"{rank_word} {top_n} {stat_display_name}{per_game_phrase} leaders {season}"
    if included_names:
        title += f"\n(Includes {', '.join(included_names)})"

    if orientation == "vertical":
        ax.set_ylabel(title, color="white", fontsize=11, fontweight="bold")
    else:
        ax.set_xlabel(title, color="white", fontsize=11, fontweight="bold")

    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)

    return fig


def _bezier_arc(x0, y0, n=15, arc_bow_amount=100):
    """
    Exact port of bezier_arc() from animated_shot_chart.r: a quadratic
    bezier from (x0, y0) to the hoop (0, 0), bowed radially outward
    from the hoop -- corner shots bow the most, shots from straight
    up the middle come in nearly straight.
    """
    x1, y1 = 0, 0
    court_half_width = 250
    bow_amount = arc_bow_amount * (abs(x0) / court_half_width)

    dist_from_hoop = np.sqrt(x0**2 + y0**2)
    out_x = 0 if dist_from_hoop == 0 else x0 / dist_from_hoop
    out_y = 0 if dist_from_hoop == 0 else y0 / dist_from_hoop

    mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2
    ctrl_x = mid_x + out_x * bow_amount
    ctrl_y = mid_y + out_y * bow_amount

    t = np.linspace(0, 1, n)
    x = (1 - t)**2 * x0 + 2 * (1 - t) * t * ctrl_x + t**2 * x1
    y = (1 - t)**2 * y0 + 2 * (1 - t) * t * ctrl_y + t**2 * y1
    return x, y


def build_animated_shot_chart(
    shots_df, team_color,
    fps=12, max_seconds=15, hold_seconds=1.5, frames_per_batch=6,
    arc_points_per_shot=15, arc_bow_amount=100,
    dot_size=1.25, line_max_opacity=0.2,
    missed_dot_color="#373737", background_color="#0D0D0D",
    width=6, height=5,
):
    """
    Exact port of animated_shot_chart.r's chronological reveal logic:
    shots appear in real game order, made shots glow and persist
    forever, missed shots fade after a brief hold. Returns a BytesIO
    buffer containing the finished GIF, ready to hand to
    st.image() directly.
    """
    import io
    from PIL import Image

    shots_df = shots_df.copy()
    shots_df["LOC_X"] = shots_df["LOC_X"].astype(float)
    shots_df["LOC_Y"] = shots_df["LOC_Y"].astype(float)
    shots_df["is_made"] = shots_df["SHOT_MADE_FLAG"] == 1
    shots_df["clock_seconds"] = shots_df["MINUTES_REMAINING"] * 60 + shots_df["SECONDS_REMAINING"]

    shots_df = shots_df[(shots_df["LOC_X"].abs() <= 250) & (shots_df["LOC_Y"] <= 350)]
    shots_df = shots_df.sort_values(
        ["GAME_DATE", "PERIOD", "clock_seconds"], ascending=[True, True, False]
    ).reset_index(drop=True)
    shots_df["shot_index"] = range(1, len(shots_df) + 1)

    if len(shots_df) == 0:
        raise ValueError("No shots remaining after filtering -- check the source data.")

    total_shots = len(shots_df)
    total_frames = round(fps * max_seconds)
    hold_frames = round(fps * hold_seconds)
    reveal_frames = total_frames - hold_frames
    num_batches = max(1, reveal_frames // frames_per_batch)
    shots_per_batch = int(np.ceil(total_shots / num_batches))

    shots_df["batch"] = np.minimum(
        np.ceil(shots_df["shot_index"] / shots_per_batch), num_batches
    ).astype(int)

    arcs = {}
    for _, row in shots_df.iterrows():
        arcs[row["shot_index"]] = _bezier_arc(
            row["LOC_X"], row["LOC_Y"], n=arc_points_per_shot, arc_bow_amount=arc_bow_amount
        )

    frames = []

    for f in range(1, total_frames + 1):
        fig, ax = new_court_figure(width=width, height=height)
        fig.patch.set_alpha(1)
        fig.patch.set_facecolor(background_color)
        ax.set_facecolor(background_color)

        for _, row in shots_df.iterrows():
            batch = row["batch"]
            batch_start = (batch - 1) * frames_per_batch + 1
            batch_end = batch * frames_per_batch
            progress = min(max((f - batch_start + 1) / frames_per_batch, 0), 1)
            fade_end = batch_end + frames_per_batch

            dot_opacity = 1.0 if f >= batch_start else 0.0
            if dot_opacity == 0:
                continue

            if row["is_made"]:
                line_opacity = line_max_opacity * progress
            elif f <= batch_end:
                line_opacity = line_max_opacity * progress
            elif f <= fade_end:
                line_opacity = line_max_opacity * (1 - ((f - batch_end) / frames_per_batch))
            else:
                line_opacity = 0.0

            arc_x, arc_y = arcs[row["shot_index"]]
            n_points_to_show = int(np.ceil(progress * arc_points_per_shot))

            color = team_color if row["is_made"] else missed_dot_color

            if n_points_to_show > 1 and line_opacity > 0:
                ax.plot(
                    arc_x[:n_points_to_show], arc_y[:n_points_to_show],
                    color=color, alpha=line_opacity, linewidth=1, zorder=2
                )

            ax.scatter(
                row["LOC_X"], row["LOC_Y"],
                color=color, s=dot_size * 15, alpha=dot_opacity, zorder=3,
                edgecolors="none"
            )

        draw_court(ax, color="white", lw=1.2)

        fig.canvas.draw()
        buf = np.asarray(fig.canvas.buffer_rgba())
        frames.append(Image.fromarray(buf).convert("RGB"))
        plt.close(fig)

    gif_buffer = io.BytesIO()
    frames[0].save(
        gif_buffer, format="GIF", save_all=True,
        append_images=frames[1:], duration=int(1000 / fps), loop=0
    )
    gif_buffer.seek(0)
    return gif_buffer


def _fetch_headshot(player_id, max_size=150):
    """
    Downloads one player headshot, resized, for embedding into a matplotlib figure -- returns None on any failure
    (network, 404, timeout) so the caller can fall back to text-only rather than crash the whole visualization over
    one missing image. Uses the same source order as everywhere else (2kratings for current players, the NBA's
    official headshot for retired ones, each as the other's fallback).
    """
    try:
        from teams import get_player_headshot_url
        return _fetch_image_small(get_player_headshot_url(player_id), max_size)
    except Exception:
        return None


def build_trade_breakdown_image(team_a_name, team_b_name, sends_a, sends_b,
                                 stats_df, player_ids, salary_data=None):
    """
    A clean, two-column "{Team} Trade:" card rendered as one PNG image
    -- each team's traded players in their own bordered box, with
    headshot, real stat line, and salary/years (from the embedded
    salaries.csv if available) shown directly per player, rather than a
    copyable table of numbers or a separate financial-breakdown section.

    player_ids: dict of {player_name: nba player id}, used to fetch
    headshots -- returns None per-player where a headshot can't be
    fetched, rendering that player's row as text-only instead.
    salary_data: optional DataFrame with PLAYER_NAME/SALARY/
    YEARS_REMAINING columns (the embedded CSV) -- omitted per-player
    where a player isn't in it, rather than showing a fabricated $0.
    """
    n_rows = max(len(sends_a), len(sends_b), 1)
    fig_height = 1.0 + n_rows * 1.5
    fig, ax = plt.subplots(figsize=(11, fig_height))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, fig_height)
    ax.axis("off")
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    box_top = fig_height - 0.15
    box_bottom = 0.15
    ax.plot([0.15, 4.85, 4.85, 0.15, 0.15], [box_top, box_top, box_bottom, box_bottom, box_top], color="#3a3a3a", linewidth=1)
    ax.plot([5.15, 9.85, 9.85, 5.15, 5.15], [box_top, box_top, box_bottom, box_bottom, box_top], color="#3a3a3a", linewidth=1)

    header_y = box_top - 0.35
    ax.text(0.4, header_y, f"{team_a_name} Trade:", fontsize=13, fontweight="bold", color="#f0f0f0", family="serif")
    ax.text(5.4, header_y, f"{team_b_name} Trade:", fontsize=13, fontweight="bold", color="#f0f0f0", family="serif")
    ax.plot([0.3, 4.7], [header_y - 0.25, header_y - 0.25], color="#3a3a3a", linewidth=0.8)
    ax.plot([5.3, 9.7], [header_y - 0.25, header_y - 0.25], color="#3a3a3a", linewidth=0.8)

    def _render_column(names, x_left, start_y):
        y = start_y
        for name in names:
            pid = player_ids.get(name)
            img = _fetch_headshot(pid) if pid else None
            text_x = x_left + 0.9
            if img is not None:
                imagebox = OffsetImage(np.array(img), zoom=0.22)
                ax.add_artist(AnnotationBbox(imagebox, (x_left + 0.4, y), frameon=False, box_alignment=(0.5, 0.5)))
            stat_line = ""
            if stats_df is not None and "PLAYER_NAME" in stats_df.columns:
                row_match = stats_df[stats_df["PLAYER_NAME"] == name]
                if not row_match.empty:
                    r = row_match.iloc[0]
                    bits = [f"{r[f]:.1f} {l}" for f, l in [("PTS", "pts"), ("REB", "reb"), ("AST", "ast")]
                            if f in r.index and pd.notna(r[f])]
                    stat_line = ", ".join(bits)
            salary_line = ""
            if salary_data is not None and "PLAYER_NAME" in salary_data.columns:
                sal_match = salary_data[salary_data["PLAYER_NAME"] == name]
                if not sal_match.empty:
                    sal_row = sal_match.iloc[0]
                    sal = sal_row.get("SALARY")
                    yrs = sal_row.get("YEARS_REMAINING")
                    if pd.notna(sal):
                        salary_line = f"${sal / 1_000_000:.1f}m" + (f", {int(yrs)} yrs" if pd.notna(yrs) else "")
            ax.text(text_x, y + 0.18, name, fontsize=11, color="#f0f0f0", fontweight="bold", va="center")
            if stat_line:
                ax.text(text_x, y - 0.18, stat_line, fontsize=9, color="#9a9a9a", va="center")
            if salary_line:
                ax.text(x_left + 4.5, y, salary_line, fontsize=9, color="#9a9a9a", va="center", ha="right")
            y -= 1.5
        if not names:
            ax.text(x_left + 0.4, y, "(nobody)", fontsize=10, color="#666666", va="center")

    body_start = header_y - 0.7
    _render_column(sends_a, 0.3, body_start)
    _render_column(sends_b, 5.3, body_start)

    return fig


def build_onoff_lineup_image(team_name, rows, player_ids):
    """
    A Databallr-style lineup table rendered as one PNG -- headshots
    beside MIN/PTS/REB/AST/FG% for each row, dark background, gold
    accents, rather than a plain copyable table of numbers.

    rows: list of dicts, each with keys "label" (str), "players" (list
    of player names for headshots, 1-2 of them), "min", "pts", "reb",
    "ast", "fg_pct", "pct_change" (the last one relative to whatever
    baseline the caller computed -- team average or otherwise; None
    entries are rendered as "--" instead of a fabricated 0).
    """
    n_rows = max(len(rows), 1)
    row_height = 1.4
    fig_height = 1.3 + n_rows * row_height
    fig, ax = plt.subplots(figsize=(14, fig_height))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, fig_height)
    ax.axis("off")
    fig.patch.set_facecolor("#0d0d0d")
    ax.set_facecolor("#0d0d0d")

    header_y = fig_height - 0.5
    ax.text(0.3, header_y, team_name, fontsize=15, fontweight="bold", color="#D4AF37", family="serif")
    col_x = {"min": 8.4, "pts": 9.7, "reb": 10.8, "ast": 11.9, "fg": 13.0, "chg": 14.2}
    for key, label in [("min", "MIN"), ("pts", "PTS"), ("reb", "REB"), ("ast", "AST"), ("fg", "FG%"), ("chg", "vs avg")]:
        ax.text(col_x[key], header_y, label, fontsize=10, color="#9a9a9a", ha="center", fontweight="bold")
    ax.plot([0.2, 14.8], [header_y - 0.3, header_y - 0.3], color="#3a3a3a", linewidth=1)

    y = header_y - 0.8
    for row in rows:
        players = row.get("players", [])
        img_x = 0.6
        for name in players:
            pid = player_ids.get(name)
            img = _fetch_headshot(pid, max_size=90) if pid else None
            if img is not None:
                imagebox = OffsetImage(np.array(img), zoom=0.22)
                ax.add_artist(AnnotationBbox(imagebox, (img_x, y), frameon=False, box_alignment=(0.5, 0.5)))
            img_x += 0.9
        ax.text(2.8, y, row.get("label", ""), fontsize=10, color="#f0f0f0", va="center", fontweight="bold")

        def _fmt(key, decimals=1, pct=False):
            v = row.get(key)
            if v is None:
                return "--"
            return f"{v:.1%}" if pct else f"{v:.{decimals}f}"

        ax.text(col_x["min"], y, _fmt("min", 0), fontsize=10, color="#f0f0f0", ha="center", va="center")
        ax.text(col_x["pts"], y, _fmt("pts"), fontsize=10, color="#f0f0f0", ha="center", va="center")
        ax.text(col_x["reb"], y, _fmt("reb"), fontsize=10, color="#f0f0f0", ha="center", va="center")
        ax.text(col_x["ast"], y, _fmt("ast"), fontsize=10, color="#f0f0f0", ha="center", va="center")
        ax.text(col_x["fg"], y, _fmt("fg_pct", pct=True), fontsize=10, color="#f0f0f0", ha="center", va="center")
        pct_change = row.get("pct_change")
        if pct_change is None:
            ax.text(col_x["chg"], y, "--", fontsize=10, color="#9a9a9a", ha="center", va="center")
        else:
            chg_color = "#4caf50" if pct_change >= 0 else "#e05252"
            ax.text(col_x["chg"], y, f"{pct_change:+.1f}%", fontsize=10, color=chg_color, ha="center", va="center", fontweight="bold")
        y -= row_height
        if row is not rows[-1]:
            ax.plot([0.2, 14.8], [y + row_height / 2, y + row_height / 2], color="#232323", linewidth=0.8)

    return fig


def build_onoff_column_image(team_name, columns, player_ids):
    """
    A column-per-scenario on/off table rendered as one PNG -- each of
    the (typically 3) scenarios gets its own column with headshots and
    ON/OFF status at the top, real metric values with % change below,
    rather than a plain copyable table of numbers.

    columns: list of dicts, each with keys "label" (str, e.g. "Together"),
    "players" (list of (name, status) tuples, status being "ON" or
    "OFF"), and "metrics" (list of (metric_label, value, pct_change,
    is_pct) tuples, in the same order for every column so rows line
    up -- None value/pct_change render as "--" instead of a fabricated
    number).
    """
    n_metrics = max(len(columns[0]["metrics"]), 1) if columns else 1
    col_width = 3.2
    n_cols = max(len(columns), 1)
    fig_width = 1.8 + n_cols * col_width
    row_height = 0.55
    fig_height = 1.8 + n_metrics * row_height
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.set_xlim(0, fig_width)
    ax.set_ylim(0, fig_height)
    ax.axis("off")
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    header_y = fig_height - 1.0
    label_x = 0.2
    # Team name sits directly at the same height as the player image
    # row, left-aligned in the same column the "Lineup" label uses
    # below it -- not as a separate row above everything, which is
    # what made it look disproportionately high up before.
    ax.text(label_x, header_y + 0.35, team_name, fontsize=13, fontweight="bold", color="white", family="serif")
    ax.text(label_x, header_y, "Lineup", fontsize=10, color="#9a9a9a", fontweight="bold")

    col_centers = []
    for i, col in enumerate(columns):
        col_center = 1.8 + i * col_width + col_width / 2
        col_centers.append(col_center)
        players = col.get("players", [])
        n_players = max(len(players), 1)
        spacing = 0.9
        start_x = col_center - (n_players - 1) * spacing / 2
        for j, (name, status) in enumerate(players):
            px = start_x + j * spacing
            pid = player_ids.get(name)
            img = _fetch_headshot(pid, max_size=90) if pid else None
            if img is not None:
                imagebox = OffsetImage(np.array(img), zoom=0.34)
                ax.add_artist(AnnotationBbox(imagebox, (px, header_y + 0.5), frameon=False, box_alignment=(0.5, 0.5)))
            status_color = "#4caf50" if status == "ON" else "#666666"
            ax.text(px, header_y, status, fontsize=9, color=status_color, ha="center", fontweight="bold")

    ax.plot([0.1, fig_width - 0.1], [header_y - 0.3, header_y - 0.3], color="#3a3a3a", linewidth=1)

    row_y = header_y - 0.65
    metrics_lists = [col.get("metrics", []) for col in columns]
    for row_idx in range(n_metrics):
        metric_label = metrics_lists[0][row_idx][0] if metrics_lists and len(metrics_lists[0]) > row_idx else ""
        ax.text(label_x, row_y, metric_label, fontsize=9.5, color="#9a9a9a", va="center")
        for col_idx, metrics in enumerate(metrics_lists):
            if row_idx >= len(metrics):
                continue
            _, value, pct_change, is_pct = metrics[row_idx]
            cx = col_centers[col_idx]
            if value is None:
                ax.text(cx - 0.5, row_y, "--", fontsize=9.5, color="#9a9a9a", ha="center", va="center")
            else:
                display = f"{value:.1%}" if is_pct else f"{value:.1f}"
                ax.text(cx - 0.5, row_y, display, fontsize=9.5, color="#f0f0f0", ha="center", va="center", fontweight="bold")
            if pct_change is not None:
                chg_color = "#4caf50" if pct_change >= 0 else "#e05252"
                ax.text(cx + 0.5, row_y, f"{pct_change:+.1f}%", fontsize=9, color=chg_color, ha="center", va="center")
        row_y -= row_height

    return fig


def build_static_stat_table_image(subject_name, table_rows):
    """
    A static, transparent stat table rendered as one PNG -- no
    animation, no dark background fill (blends with the app's own
    gradient background instead), per explicit request to make this
    section stop animating and match the transparent treatment used
    elsewhere in the app.

    table_rows: list of (label, value, is_pct) tuples, same shape the
    caller already builds for the old animated version. None value
    renders as "--" instead of a fabricated number.
    """
    fig_height = 1.0 + len(table_rows) * 0.55
    fig, ax = plt.subplots(figsize=(6, fig_height))
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, fig_height)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    ax.text(0.3, fig_height - 0.4, subject_name, fontsize=13, color="#f0f0f0", fontweight="bold", family="serif")
    y = fig_height - 1.0
    for label, value, is_pct in table_rows:
        display = "--" if value is None else (f"{value:.1%}" if is_pct else f"{value:.1f}")
        ax.text(0.5, y, label, fontsize=10.5, color="#9a9a9a", va="center")
        ax.text(9.5, y, display, fontsize=12, color="#D4AF37", va="center", ha="right", fontweight="bold", family="serif")
        y -= 0.55

    return fig


def build_animated_stat_table_gif(subject_name, table_rows, duration_seconds=2, fps=15, hold_seconds=1.5):
    """
    An animated GIF of a stat table -- every number counts up from 0 to
    its real value over duration_seconds (ease-out, matching the same
    cubic curve used for the dashboard's own JS count-up animation),
    with the text cycling through a few gold shades frame to frame to
    approximate the CSS gradient-shimmer look, since GIFs can't do a
    true animated CSS background-clip gradient the way the live
    dashboard's own metric numbers do.

    table_rows: list of (label, final_value, is_pct) tuples.
    Returns a BytesIO buffer containing the finished GIF.
    """
    n_count_frames = max(1, int(duration_seconds * fps))
    n_hold_frames = max(1, int(hold_seconds * fps))
    gold_shades = ["#8a6410", "#D4AF37", "#F5D370", "#D4AF37"]

    frames = []
    fig_height = 1.0 + len(table_rows) * 0.55
    for frame_idx in range(n_count_frames + n_hold_frames):
        progress = min(1.0, frame_idx / n_count_frames)
        eased = 1 - (1 - progress) ** 3
        shade = gold_shades[frame_idx % len(gold_shades)]

        fig, ax = plt.subplots(figsize=(6, fig_height))
        ax.axis("off")
        ax.set_xlim(0, 10)
        ax.set_ylim(0, fig_height)
        fig.patch.set_facecolor("#0d0d0d")
        ax.set_facecolor("#0d0d0d")

        ax.text(0.3, fig_height - 0.4, subject_name, fontsize=13, color="#f0f0f0", fontweight="bold", family="serif")
        y = fig_height - 1.0
        for label, final_value, is_pct in table_rows:
            current = final_value * eased if final_value is not None else None
            display = "--" if current is None else (f"{current:.1%}" if is_pct else f"{current:.1f}")
            ax.text(0.5, y, label, fontsize=10.5, color="#9a9a9a", va="center")
            ax.text(9.5, y, display, fontsize=12, color=shade, va="center", ha="right", fontweight="bold", family="serif")
            y -= 0.55

        fig.canvas.draw()
        buf = np.asarray(fig.canvas.buffer_rgba())
        frames.append(Image.fromarray(buf).convert("RGB"))
        plt.close(fig)

    gif_buffer = io.BytesIO()
    frames[0].save(
        gif_buffer, format="GIF", save_all=True,
        append_images=frames[1:], duration=int(1000 / fps), loop=0
    )
    gif_buffer.seek(0)
    return gif_buffer






def build_histogram(values, stat_display_name, season, team_color, is_percentage=False,
                     bins=20, width=8, height=7):
    """
    Distribution of one stat across the whole league (or whatever slice
    of players the caller already filtered down to) -- reveals the
    shape of the data (skewed, bimodal, etc.) that a leaderboard alone
    can't show. Same transparent-figure / white-text style as the rest
    of this file's charts.
    """
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    ax.hist(values, bins=bins, color=team_color, edgecolor="white", linewidth=0.6, alpha=0.9)

    mean_val = float(np.mean(values))
    ax.axvline(mean_val, color="white", linestyle="--", linewidth=1.2, alpha=0.8)
    label = f"{mean_val:.0%}" if is_percentage else f"{mean_val:,.1f}"
    ax.text(mean_val, ax.get_ylim()[1] * 0.97, f"  league avg: {label}",
            color="white", fontsize=9, va="top")

    if is_percentage:
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))

    ax.set_xlabel(f"{stat_display_name}, {season}", color="white", fontsize=11, fontweight="bold")
    ax.set_ylabel("Number of Players", color="white", fontsize=11, fontweight="bold")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def build_box_plot(groups, stat_display_name, season, team_color, is_percentage=False,
                    violin=False, width=8, height=7):
    """
    groups: dict of {label: [values]} -- one box (or violin) per group,
    e.g. one per team showing that team's roster's spread on a stat, or
    one per season showing year-to-year consistency for a single
    player. violin=True switches from quartile boxes/whiskers to a
    mirrored density curve for the same comparison.
    """
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    labels = list(groups.keys())
    data = [groups[k] for k in labels]

    if violin:
        parts = ax.violinplot(data, showmeans=True, showextrema=True)
        for body in parts["bodies"]:
            body.set_facecolor(team_color)
            body.set_edgecolor("white")
            body.set_alpha(0.75)
        for key in ("cmeans", "cmaxes", "cmins", "cbars"):
            if key in parts:
                parts[key].set_color("white")
    else:
        bp = ax.boxplot(data, patch_artist=True, medianprops={"color": "white", "linewidth": 1.5},
                         whiskerprops={"color": "white"}, capprops={"color": "white"},
                         flierprops={"markeredgecolor": "white", "markersize": 4})
        for box in bp["boxes"]:
            box.set_facecolor(team_color)
            box.set_edgecolor("white")
            box.set_alpha(0.85)

    ax.set_xticks(range(1, len(labels) + 1))
    ax.set_xticklabels(labels, color="white", fontsize=10, rotation=20 if len(labels) > 6 else 0, ha="right" if len(labels) > 6 else "center")
    if is_percentage:
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
    kind = "Violin" if violin else "Box"
    ax.set_ylabel(f"{stat_display_name}, {season} ({kind} Plot)", color="white", fontsize=11, fontweight="bold")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def build_dot_plot(axis_df, stat_display_name, season, top_n, team_color,
                    included_names=None, stat_source="base", is_percentage=False,
                    width=8, height=7, rank_ascending=False):
    """
    A cleaner alternative to build_bar_chart() for the same ranked
    leaderboard shape -- a single dot per entity along a category axis,
    connected to a baseline stem, instead of a filled bar. Same
    axis_df/columns contract as build_bar_chart (name, value,
    is_included, image_url) so it's a drop-in alternate rendering of
    identical data, not a separate data pipeline -- formatted the same
    way as horizontal Bar Chart, with player images in place of plain
    text names (falling back to a name only if that specific image
    genuinely fails to load).
    """
    included_names = included_names or []
    neutral_color = "#B5B5B5"

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    df = axis_df.sort_values("value", ascending=True).reset_index(drop=True)
    colors = [team_color if row["is_included"] else neutral_color for _, row in df.iterrows()]

    positions = range(len(df))
    max_val = df["value"].max()
    ax.hlines(y=positions, xmin=0, xmax=df["value"], color="#555555", linewidth=1, alpha=0.6)
    ax.scatter(df["value"], positions, color=colors, s=90, zorder=3, edgecolor="white", linewidth=0.8)

    for i, val in enumerate(df["value"]):
        label = f"{val:.0%}" if is_percentage else f"{val:,.0f}"
        ax.text(val + max_val * 0.02, i, label, va="center", color="white", fontsize=9, fontweight="bold")

    has_image_col = "image_url" in df.columns
    for i, row in df.iterrows():
        img = _fetch_image(row["image_url"]) if has_image_col else None
        if img is not None:
            imagebox = OffsetImage(img, zoom=0.08)
            ab = AnnotationBbox(imagebox, (-max_val * 0.14, i), frameon=False,
                                 box_alignment=(1, 0.5), annotation_clip=False, zorder=4)
            ax.add_artist(ab)
        else:
            ax.text(-max_val * 0.02, i, row["name"], ha="right", va="center", color="white", fontsize=9)

    ax.set_xlim(-max_val * 0.28, max_val * 1.15)
    ax.set_yticks([])
    if is_percentage:
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)

    per_game_phrase = "" if stat_source in ("bio", "bradley_rating") else " per game"
    rank_word = "Lowest" if rank_ascending else "Top"
    label = f"{rank_word} {top_n} {stat_display_name}{per_game_phrase} leaders {season} (Dot Plot)"
    if included_names:
        label += f"\n(Includes {', '.join(included_names)})"
    ax.set_xlabel(label, color="white", fontsize=11, fontweight="bold")
    fig.tight_layout()
    return fig


def build_density_plot(values, stat_display_name, season, team_color, is_percentage=False,
                        width=8, height=7):
    """
    A smooth kernel-density estimate of one stat's distribution, without
    binning into discrete buckets the way build_histogram() does --
    reveals the underlying shape more cleanly for a large sample. Same
    values contract as build_histogram (a flat list of numbers).
    """
    from scipy.stats import gaussian_kde

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    values_arr = np.asarray(values, dtype=float)
    values_arr = values_arr[~np.isnan(values_arr)]

    kde = gaussian_kde(values_arr)
    x_grid = np.linspace(values_arr.min(), values_arr.max(), 300)
    density = kde(x_grid)

    ax.fill_between(x_grid, density, color=team_color, alpha=0.55)
    ax.plot(x_grid, density, color=team_color, linewidth=2)

    mean_val = float(values_arr.mean())
    ax.axvline(mean_val, color="white", linestyle="--", linewidth=1.2, alpha=0.8)
    label = f"{mean_val:.0%}" if is_percentage else f"{mean_val:,.1f}"
    ax.text(mean_val, ax.get_ylim()[1] * 0.97, f"  league avg: {label}",
            color="white", fontsize=9, va="top")

    if is_percentage:
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))

    ax.set_yticks([])
    ax.set_xlabel(f"{stat_display_name}, {season}", color="white", fontsize=11, fontweight="bold")
    ax.set_ylabel("Density", color="white", fontsize=11, fontweight="bold")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def build_cumulative_distribution_plot(values, stat_display_name, season, team_color,
                                        is_percentage=False, highlight_value=None,
                                        highlight_name=None, width=8, height=7):
    """
    A rising curve showing what fraction of the league falls at or below
    each value of this stat -- answers "what percentile is X in" at a
    glance. highlight_value/highlight_name optionally mark one specific
    player's spot on the curve with a dot and percentile callout.
    """
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    values_arr = np.sort(np.asarray(values, dtype=float))
    values_arr = values_arr[~np.isnan(values_arr)]
    n = len(values_arr)
    cumulative_pct = np.arange(1, n + 1) / n * 100

    ax.plot(values_arr, cumulative_pct, color=team_color, linewidth=2.5)
    ax.fill_between(values_arr, cumulative_pct, color=team_color, alpha=0.15)

    if highlight_value is not None:
        percentile = float(np.searchsorted(values_arr, highlight_value, side="right") / n * 100)
        ax.scatter([highlight_value], [percentile], color="white", s=90, zorder=5,
                   edgecolor=team_color, linewidth=2)
        label = f"{highlight_value:.0%}" if is_percentage else f"{highlight_value:,.1f}"
        name_part = f"{highlight_name}: " if highlight_name else ""
        ax.annotate(f"{name_part}{label}\n({percentile:.0f}th percentile)",
                    (highlight_value, percentile), textcoords="offset points",
                    xytext=(12, -10), color="white", fontsize=10, fontweight="bold")

    if is_percentage:
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0f}%"))

    ax.set_xlabel(f"{stat_display_name}, {season} (Cumulative Distribution)", color="white", fontsize=11, fontweight="bold")
    ax.set_ylabel("Percentile", color="white", fontsize=11, fontweight="bold")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def build_line_chart(x_labels, values, stat_display_name, subject_name, season, team_color,
                      is_percentage=False, rolling_window=None, cumulative=False,
                      filled=False, width=8, height=7):
    """
    A stat plotted continuously across an ordered axis -- covers the
    core of the spec's "Line / Trend Chart" entry: season trend
    (game-by-game, x_labels are game dates/opponents), rolling average
    (rolling_window > 0 overlays a second smoothed line), and
    cumulative running total (cumulative=True sums values as it goes
    instead of plotting them raw). filled=True shades the area below
    the line instead of a bare line.
    """
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    y = np.asarray(values, dtype=float)
    if cumulative:
        y = np.cumsum(y)

    x = range(len(y))
    if filled:
        ax.fill_between(x, y, color=team_color, alpha=0.25)
    ax.plot(x, y, color=team_color, linewidth=2, marker="o", markersize=4)

    if rolling_window and rolling_window > 1 and not cumulative:
        rolling = pd.Series(y).rolling(rolling_window, min_periods=1).mean()
        ax.plot(x, rolling, color="white", linewidth=1.8, linestyle="--", alpha=0.85,
                label=f"{rolling_window}-game rolling avg")
        ax.legend(facecolor="#1a1a1a", edgecolor="#555555", labelcolor="white", fontsize=9)

    # Thin out x-axis labels so they don't overlap on a long season --
    # shows at most ~15 tick labels regardless of game count.
    step = max(1, len(x_labels) // 15)
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels([x_labels[i] for i in range(0, len(x_labels), step)],
                        color="white", fontsize=8, rotation=45, ha="right")

    if is_percentage:
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    title_stat = f"Cumulative {stat_display_name}" if cumulative else stat_display_name
    ax.set_ylabel(f"{subject_name} -- {title_stat}, {season}", color="white", fontsize=11, fontweight="bold")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def build_slope_chart(entities, before_values, after_values, before_label, after_label,
                       stat_display_name, team_color, is_percentage=False,
                       highlight_names=None, width=8, height=8):
    """
    entities: list of names, before_values/after_values: matching lists
    of the same stat at two points (e.g. two seasons, home vs away).
    One line per entity connecting its "before" dot to its "after" dot
    -- direction and steepness read as improvement/decline at a glance.
    highlight_names get the team color and a bold label; everyone else
    renders muted grey so a handful of highlighted names don't get lost
    in a crowded chart.
    """
    highlight_names = set(highlight_names or [])
    neutral_color = "#555555"

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    for name, before, after in zip(entities, before_values, after_values):
        is_hl = name in highlight_names or not highlight_names
        color = team_color if is_hl else neutral_color
        lw = 2.2 if is_hl else 1
        alpha = 1.0 if is_hl else 0.35
        ax.plot([0, 1], [before, after], color=color, linewidth=lw, alpha=alpha, marker="o", markersize=6 if is_hl else 3)
        if is_hl:
            label = f"{after:.0%}" if is_percentage else f"{after:,.1f}"
            ax.text(1.03, after, f"{name} ({label})", color="white", fontsize=9, va="center", fontweight="bold" if highlight_names else "normal")

    ax.set_xlim(-0.15, 1.6)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([before_label, after_label], color="white", fontsize=12)
    if is_percentage:
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_ylabel(f"{stat_display_name}: {before_label} vs {after_label}", color="white", fontsize=11, fontweight="bold")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def build_waterfall_chart(labels, values, total_label, team_color, pct_labels=None, total_pct_label=None,
                           is_percentage=False, width=8, height=7, image_url=None):
    """
    Sequential bars, each starting where the previous one ended --
    shows how components sum to a total. labels/values are the
    components in order (e.g. ["FT pts", "2PT pts", "3PT pts"] with
    their point contributions); a final bar for the total is appended
    automatically, styled distinctly (full height from zero, a
    different color) as a running-total marker rather than another
    component.

    pct_labels: optional list of short strings (e.g. "83% FT%"), one
    per component, shown as a second line under that bar's points
    number. total_pct_label: same idea for the total bar (e.g. "58% TS%").

    image_url: accepted for backward compatibility with existing
    callers, but no longer drawn -- the player image was explicitly
    removed from this chart's own visualization.
    """
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    running = 0
    positions = list(range(len(values) + 1))
    total = sum(values)
    pct_labels = pct_labels or [None] * len(values)

    for i, (label, val, pct_lbl) in enumerate(zip(labels, values, pct_labels)):
        ax.bar(i, val, bottom=running, color=team_color, edgecolor="white", linewidth=0.6, width=0.6)
        mid = running + val / 2
        label_text = f"{val:.0%}" if is_percentage else f"{val:,.1f}"
        if pct_lbl:
            label_text += f"\n{pct_lbl}"
        ax.text(i, mid, label_text, ha="center", va="center", color="white", fontsize=9, fontweight="bold",
                linespacing=1.6)
        if i > 0:
            ax.plot([i - 1 + 0.3, i - 0.3], [running, running], color="#888888", linewidth=1, linestyle=":")
        running += val

    # Total bar, visually distinct (full height, different shade)
    ax.bar(len(values), total, color="#F5D370", edgecolor="white", linewidth=0.6, width=0.6, alpha=0.9)
    total_label_text = f"{total:.0%}" if is_percentage else f"{total:,.1f}"
    if total_pct_label:
        total_label_text += f"\n{total_pct_label}"
    ax.text(len(values), total / 2, total_label_text, ha="center", va="center", color="#111111", fontsize=10,
             fontweight="bold", linespacing=1.6)

    ax.set_xticks(positions)
    ax.set_xticklabels(list(labels) + [total_label], color="white", fontsize=10, rotation=15 if len(labels) > 4 else 0)
    if is_percentage:
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_ylabel(f"{total_label} Breakdown", color="white", fontsize=11, fontweight="bold")
    fig.tight_layout()
    return fig


def _short_season_label(season):
    """'2024-25' -> \"'24-'25\" for compact axis labels; anything that
    isn't a plain YYYY-YY season string passes through unchanged."""
    s = str(season)
    if len(s) == 7 and s[4] == "-" and s[:4].isdigit() and s[5:].isdigit():
        return f"'{s[2:4]}-'{s[5:]}"
    return s


def build_combo_chart(x_labels, bar_values, line_values, bar_label, line_label,
                       team_color, line_color="white", line_is_percentage=False, width=8, height=7):
    """
    Bars (left axis, bar_label -- typically a volume stat like FGA) and
    a line (right axis, line_label -- typically a rate stat like FG%)
    sharing the same category axis. Two independent y-axes since the
    two stats are rarely on comparable scales. Each has its own
    adjustable color (line_color defaults to white for backward
    compatibility) so the two are easy to tell apart at a glance.
    """
    fig, ax1 = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax1.set_facecolor("none")

    x = range(len(x_labels))
    ax1.bar(x, bar_values, color=team_color, alpha=0.75, width=0.6, label=bar_label)
    ax1.set_ylabel(bar_label, color=team_color, fontsize=11, fontweight="bold")
    ax1.tick_params(axis="y", colors=team_color)

    ax2 = ax1.twinx()
    ax2.plot(x, line_values, color=line_color, linewidth=2.2, marker="o", markersize=5, label=line_label)
    ax2.set_ylabel(line_label, color=line_color, fontsize=11, fontweight="bold")
    ax2.tick_params(axis="y", colors=line_color)
    if line_is_percentage:
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))

    step = max(1, len(x_labels) // 15)
    ax1.set_xticks(list(x)[::step])
    ax1.set_xticklabels([_short_season_label(x_labels[i]) for i in range(0, len(x_labels), step)], color="white", fontsize=8, rotation=45, ha="right")
    ax1.tick_params(axis="x", colors="white")
    for spine in list(ax1.spines.values()) + list(ax2.spines.values()):
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def build_tornado_chart(labels, values, subject_label, team_color, is_percentage=False,
                         center_label="League Average", width=8, height=7.5, image_url=None):
    """
    Diverging bars from a center axis (typically 0, or a stat's league
    average already subtracted out before calling this) -- bars extend
    right for above-center values, left for below, color-coded by
    direction so strengths and weaknesses read apart at a glance.

    image_url: accepted for backward compatibility with existing
    callers, but no longer drawn -- both the player image and the
    title were explicitly removed from this chart's own visualization.
    """
    above_color = team_color
    below_color = "#8B3A3A"

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    positions = range(len(labels))
    colors = [above_color if v >= 0 else below_color for v in values]
    ax.barh(positions, values, color=colors, edgecolor="white", linewidth=0.6, height=0.6)
    ax.axvline(0, color="white", linewidth=1.2)

    for i, v in enumerate(values):
        label_text = f"{v:+.0%}" if is_percentage else f"{v:+,.1f}"
        ax.text(v + (max(abs(x) for x in values) * 0.02 * (1 if v >= 0 else -1)), i, label_text,
                va="center", ha="left" if v >= 0 else "right", color="white", fontsize=9, fontweight="bold")

    ax.set_yticks(list(positions))
    ax.set_yticklabels(labels, color="white", fontsize=10)
    if is_percentage:
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:+.0%}"))
    ax.set_xlabel(f"vs {center_label}", color="white", fontsize=11, fontweight="bold")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def build_radar_chart(stat_labels, player_percentiles, player_name, team_color,
                       second_percentiles=None, second_name=None, second_color="#B5B5B5",
                       width=8, height=8, image_url=None, second_image_url=None):
    """
    Multiple stats as spokes around a circle, forming a shape -- a
    multi-category player profile in one glance (scoring, playmaking,
    rebounding, defense, efficiency, etc). Plots league PERCENTILES
    (0-100) rather than raw values, since stats on wildly different
    scales (points vs assist ratio vs a shooting percentage) can't
    otherwise share one radial axis meaningfully -- 0-100 always works
    regardless of the underlying stat. Optionally overlays a second
    player's shape (a different, muted color, filled less heavily) for
    direct side-by-side comparison.

    image_url/second_image_url: accepted for backward compatibility
    with existing callers, but no longer drawn -- both the player
    image(s) and the title were explicitly removed from this chart's
    own visualization.
    """
    n = len(stat_labels)
    angles = [i / n * 2 * np.pi for i in range(n)]
    angles += angles[:1]  # close the loop

    fig, ax = plt.subplots(figsize=(width, height), subplot_kw=dict(polar=True))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    values = list(player_percentiles) + [player_percentiles[0]]
    ax.plot(angles, values, color=team_color, linewidth=2.2, label=player_name)
    ax.fill(angles, values, color=team_color, alpha=0.35)

    if second_percentiles is not None:
        values2 = list(second_percentiles) + [second_percentiles[0]]
        ax.plot(angles, values2, color=second_color, linewidth=2.2, label=second_name)
        ax.fill(angles, values2, color=second_color, alpha=0.2)
        ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1), facecolor="#1a1a1a",
                  edgecolor="#555555", labelcolor="white", fontsize=10)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(stat_labels, color="white", fontsize=11)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20th", "40th", "60th", "80th", "100th"], color="#888888", fontsize=8)
    ax.spines["polar"].set_visible(False)
    ax.grid(color="#444444", alpha=0.6)

    fig.tight_layout()
    return fig


def build_head_to_head_table(name_a, name_b, table_rows, color_a, color_b="#B5B5B5",
                              image_url_a=None, image_url_b=None):
    """
    A formatted side-by-side comparison of a full stat line for two
    players/teams -- same transparent, static-table aesthetic as
    build_static_stat_table_image() above, but with two value columns
    instead of one. The higher value in each row is bolded/colored in
    that player's color, so the "winner" of each stat reads at a
    glance without needing arrows or extra symbols. table_rows: list
    of (label, value_a, value_b, is_pct) tuples -- either value can be
    None, rendering as "--" and never claiming a winner for that row.

    image_url_a/image_url_b: optional headshot or team-logo URL shown
    above each name -- falls back to just the name (no broken image
    placeholder) if a URL is missing or fails to load.
    """
    fig_height = 1.1 + len(table_rows) * 0.45
    has_images = image_url_a is not None or image_url_b is not None
    if has_images:
        fig_height += 1.2
    fig, ax = plt.subplots(figsize=(3.7, fig_height))
    ax.axis("off")
    ax.set_xlim(0, 4)
    ax.set_ylim(0, fig_height)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    col_a, col_label, col_b = 0.7, 2.0, 3.3

    name_y = fig_height - 0.35
    if has_images:
        image_y = fig_height - 0.75
        img_a = _fetch_image(image_url_a) if image_url_a else None
        if img_a is not None:
            ax.add_artist(AnnotationBbox(OffsetImage(np.array(img_a), zoom=0.075), (col_a, image_y),
                                          frameon=False, box_alignment=(0.5, 0.5)))
        img_b = _fetch_image(image_url_b) if image_url_b else None
        if img_b is not None:
            ax.add_artist(AnnotationBbox(OffsetImage(np.array(img_b), zoom=0.075), (col_b, image_y),
                                          frameon=False, box_alignment=(0.5, 0.5)))
        name_y = fig_height - 1.65

    ax.text(col_a, name_y, name_a, fontsize=11.5, color=color_a, fontweight="bold", family="serif", ha="center")
    ax.text(col_b, name_y, name_b, fontsize=11.5, color=color_b, fontweight="bold", family="serif", ha="center")

    y = name_y - 0.55
    for label, val_a, val_b, is_pct in table_rows:
        def fmt(v):
            return "--" if v is None else (f"{v:.1%}" if is_pct else f"{v:,.1f}")

        a_wins = val_a is not None and val_b is not None and val_a > val_b
        b_wins = val_a is not None and val_b is not None and val_b > val_a

        ax.text(col_a, y, fmt(val_a), fontsize=11, ha="center", va="center",
                color=color_a if a_wins else "#9a9a9a", fontweight="bold" if a_wins else "normal", family="serif")
        ax.text(col_label, y, label, fontsize=9, color="#cccccc", ha="center", va="center")
        ax.text(col_b, y, fmt(val_b), fontsize=11, ha="center", va="center",
                color=color_b if b_wins else "#9a9a9a", fontweight="bold" if b_wins else "normal", family="serif")
        y -= 0.45

    return fig


def build_calendar_heat_map(dates, values, stat_display_name, subject_name, team_color,
                             width=12, height=3.5, image_url=None, return_hotspot_data=False):
    """
    A GitHub-contribution-style grid -- each day's cell shaded by that
    game's stat value, arranged by week (columns) and day-of-week
    (rows) rather than a plain timeline, which is what actually makes
    patterns like "worse on the second night of a back-to-back" or
    "stronger in a particular month" visible at a glance in a way a
    normal line chart over the same games doesn't foreground.

    dates: list of datetime-like game dates. values: matching stat
    values for those games (non-game days are simply blank cells).

    image_url: accepted because the app passes it (as it does for the
    waterfall/tornado/radar charts), but not drawn -- without it in the
    signature the whole Calendar Heat Map page failed with a TypeError.
    return_hotspot_data=True also returns one (week, weekday, date, value)
    per game: the exact cell each game was drawn in, for the hover overlay.
    """
    dates = pd.to_datetime(pd.Series(dates))
    df = pd.DataFrame({"date": dates, "value": values})
    df = df.sort_values("date")

    start = df["date"].min() - pd.Timedelta(days=int(df["date"].min().dayofweek))
    end = df["date"].max()
    n_weeks = int(((end - start).days) / 7) + 2

    grid = np.full((7, n_weeks), np.nan)
    cells = []
    for _, row in df.iterrows():
        days_since_start = (row["date"] - start).days
        week = days_since_start // 7
        weekday = row["date"].dayofweek
        if 0 <= week < n_weeks:
            grid[weekday, week] = row["value"]
            cells.append((int(week), int(weekday), row["date"], row["value"]))

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    cmap = _single_hue_cmap(team_color)
    masked = np.ma.masked_invalid(grid)
    im = ax.imshow(masked, cmap=cmap, aspect="auto")

    ax.set_yticks(range(7))
    ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], color="white", fontsize=9)
    month_positions, month_labels = [], []
    seen_months = set()
    for week in range(n_weeks):
        week_date = start + pd.Timedelta(days=week * 7)
        key = (week_date.year, week_date.month)
        if key not in seen_months:
            seen_months.add(key)
            month_positions.append(week)
            month_labels.append(week_date.strftime("%b"))
    ax.set_xticks(month_positions)
    ax.set_xticklabels(month_labels, color="white", fontsize=9)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    cbar = fig.colorbar(im, ax=ax, orientation="vertical", fraction=0.02, pad=0.02)
    cbar.ax.tick_params(colors="white", labelsize=8)
    cbar.outline.set_visible(False)

    # Short abbreviation only ("PTS", not "PTS (Points)") -- the full
    # spelled-out name is redundant once it's already right there in
    # the abbreviation, and just clutters the axis label.
    short_stat = stat_display_name.split(" (")[0].strip()
    ax.set_ylabel(f"{subject_name} -- {short_stat} by Game Date", color="white", fontsize=11, fontweight="bold")
    fig.tight_layout()
    if return_hotspot_data:
        return fig, cells
    return fig


def _single_hue_cmap(hex_color):
    """Builds a light-to-dark colormap ending at hex_color, for the calendar heat map above."""
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("single_hue", ["#1a1a1a", hex_color])


def build_court_zone_map(shots_df, subject_name, stat_name="FG%", width=8, height=7.5):
    """
    The court divided into its standard shooting zones (restricted
    area, mid-range, corners, above-the-break 3, etc, via
    SHOT_ZONE_BASIC -- a real column on every shot the NBA API
    returns, not an approximation), each shaded by that zone's actual
    FG% for this player/team. Each zone's region is drawn as the
    convex hull of that zone's own real shot locations, rather than
    hardcoded boundary polygons -- lets the real data define the
    zone's shape instead of risking a boundary that's subtly
    mismatched from what the NBA API actually classifies as each zone.

    shots_df needs SHOT_ZONE_BASIC, LOC_X, LOC_Y, SHOT_MADE_FLAG
    columns (the real Shot Chart Detail schema).
    """
    from scipy.spatial import ConvexHull
    from matplotlib.patches import Polygon
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize

    fig, ax = new_court_figure(width=width, height=height)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    draw_court(ax, color="#888888", lw=1.2)

    zone_stats = shots_df.groupby("SHOT_ZONE_BASIC").agg(
        fg_pct=("SHOT_MADE_FLAG", "mean"), attempts=("SHOT_MADE_FLAG", "count"),
    )
    cmap = plt.cm.RdYlGn
    norm = Normalize(vmin=zone_stats["fg_pct"].min(), vmax=zone_stats["fg_pct"].max())

    for zone, group in shots_df.groupby("SHOT_ZONE_BASIC"):
        points = group[["LOC_X", "LOC_Y"]].dropna().values
        if len(points) < 3:
            continue
        try:
            hull = ConvexHull(points)
            hull_points = points[hull.vertices]
        except Exception:
            continue

        fg_pct = zone_stats.loc[zone, "fg_pct"]
        attempts = int(zone_stats.loc[zone, "attempts"])
        color = cmap(norm(fg_pct))
        poly = Polygon(hull_points, closed=True, facecolor=color, edgecolor="white", linewidth=0.8, alpha=0.65)
        ax.add_patch(poly)

        centroid_x, centroid_y = hull_points[:, 0].mean(), hull_points[:, 1].mean()
        ax.text(centroid_x, centroid_y, f"{fg_pct:.0%}\n({attempts})", ha="center", va="center",
                color="white", fontsize=9, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#0d0d0d", alpha=0.6, edgecolor="none"))

    sm = ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, orientation="vertical", fraction=0.04, pad=0.02)
    cbar.set_label(stat_name, color="white", fontsize=10)
    cbar.ax.tick_params(colors="white", labelsize=8)
    cbar.outline.set_visible(False)

    ax.set_xlabel(f"{subject_name} -- Shooting by Zone", color="white", fontsize=11, fontweight="bold")
    fig.tight_layout()
    return fig


def build_small_multiples_shot_charts(players_shots, team_color, n_cols=3, width=12):
    """
    A grid of small, identical shot charts, one per player -- for
    scanning many players' shot profiles at once rather than viewing
    them one at a time. players_shots: list of (player_name, shots_df)
    tuples. Reuses the exact same court-drawing/scatter logic as the
    full-size build_shot_chart(), just at a smaller per-panel size
    with lighter labeling.
    """
    n = len(players_shots)
    n_cols = min(n_cols, n)
    n_rows = (n + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(width, width / n_cols * n_rows * 1.05),
                              subplot_kw=dict(xlim=(-250, 250), ylim=(-60, 356.7)))
    fig.patch.set_alpha(0)
    axes_flat = np.array(axes).reshape(-1) if n > 1 else [axes]

    for i, (name, shots) in enumerate(players_shots):
        ax = axes_flat[i]
        ax.set_facecolor("none")
        draw_court(ax, color="#666666", lw=0.8)
        made = shots[shots["SHOT_MADE_FLAG"] == 1]
        missed = shots[shots["SHOT_MADE_FLAG"] == 0]
        ax.scatter(made["LOC_X"], made["LOC_Y"], c=team_color, s=8, alpha=0.7, marker="o")
        ax.scatter(missed["LOC_X"], missed["LOC_Y"], c="#555555", s=8, alpha=0.5, marker="x")
        ax.set_xlabel(name, color="white", fontsize=10, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")
        for spine in ax.spines.values():
            spine.set_visible(False)

    for j in range(len(players_shots), len(axes_flat)):
        axes_flat[j].axis("off")

    fig.tight_layout()
    return fig


def build_court_radar_hybrid(shots, stat_labels, player_percentiles, player_name, team_color,
                              width=12, height=7.5, image_url=None):
    """
    A shot chart and a percentile radar for the same player, side by
    side in one figure -- pairs "where" (the shot chart) with "what
    kind of player" (the radar profile), rather than making the viewer
    hold two separate images in their head. Reuses the exact same
    court-drawing and radar logic as build_shot_chart() and
    build_radar_chart() individually -- this is genuinely just those
    two placed in one figure, not a new visualization mechanism.

    image_url: optional player headshot or team logo shown centered at
    the top via a separate inset axes, leaving both subplots
    untouched.
    """
    fig = plt.figure(figsize=(width, height))
    fig.patch.set_alpha(0)

    image_added = False
    if image_url:
        img = _fetch_image(image_url)
        if img is not None:
            img_ax = fig.add_axes([0.46, 0.88, 0.08, 0.11])
            img_ax.imshow(np.array(img))
            img_ax.axis("off")
            image_added = True

    ax1 = fig.add_subplot(1, 2, 1, xlim=(-250, 250), ylim=(-60, 356.7))
    ax1.set_facecolor("none")
    draw_court(ax1, color="#888888", lw=1.2)
    made = shots[shots["SHOT_MADE_FLAG"] == 1]
    missed = shots[shots["SHOT_MADE_FLAG"] == 0]
    ax1.scatter(made["LOC_X"], made["LOC_Y"], c=team_color, s=20, alpha=0.75, marker="o", label="Made")
    ax1.scatter(missed["LOC_X"], missed["LOC_Y"], c="#555555", s=20, alpha=0.5, marker="x", label="Missed")
    ax1.set_xticks([])
    ax1.set_yticks([])
    ax1.set_aspect("equal")
    ax1.set_xlabel(f"{player_name} -- Shot Chart", color="white", fontsize=12, fontweight="bold")

    n = len(stat_labels)
    angles = [i / n * 2 * np.pi for i in range(n)]
    angles += angles[:1]
    ax2 = fig.add_subplot(1, 2, 2, projection="polar")
    ax2.set_facecolor("none")
    values = list(player_percentiles) + [player_percentiles[0]]
    ax2.plot(angles, values, color=team_color, linewidth=2.2)
    ax2.fill(angles, values, color=team_color, alpha=0.35)
    ax2.set_xticks(angles[:-1])
    ax2.set_xticklabels(stat_labels, color="white", fontsize=10)
    ax2.set_ylim(0, 100)
    ax2.set_yticks([20, 40, 60, 80, 100])
    ax2.set_yticklabels(["20%", "40%", "60%", "80%", "100%"], color="#888888", fontsize=7)
    ax2.spines["polar"].set_visible(False)
    ax2.grid(color="#444444", alpha=0.6)
    ax2.set_xlabel("Shooting-Tendency Profile", color="white", fontsize=12, fontweight="bold", labelpad=20)

    if not image_added:
        fig.tight_layout()
    return fig


def build_sankey_flow(stage_labels, flows, team_color, width=9, height=8, image_url=None):
    """
    Custom multi-stage flow diagram (matplotlib's own sankey module
    only handles single-node in/out flows, not this kind of
    stage-to-stage structure, so this builds flow bands as filled
    polygons directly). stage_labels: list of lists, one list of node
    names per stage (e.g. [["Restricted Area", "Mid-Range", "3PT"],
    ["Made", "Missed"]]). flows: list of (from_stage_idx, from_node,
    to_node, value) tuples -- from_node/to_node must exist in their
    respective stage_labels lists. Band width is proportional to
    volume; node height is the sum of its own flows.

    image_url: accepted because the app passes it, but not drawn --
    without it in the signature the Shot Flow page failed with a TypeError.
    """
    n_stages = len(stage_labels)
    stage_x = np.linspace(0, 1, n_stages)

    # Compute each node's total volume (max of its outflow/inflow) to
    # size it, then lay nodes out top-to-bottom within their stage
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

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    cmap_colors = [team_color, "#8a6410", "#D4AF37", "#B5B5B5", "#6B6B6B"]
    node_color_map = {}
    for stage_idx, nodes in enumerate(stage_labels):
        for i, node in enumerate(nodes):
            node_color_map[(stage_idx, node)] = cmap_colors[i % len(cmap_colors)]

    # Draw flows as filled polygons (simple straight-sided bands, offset
    # by cumulative position within each node so multiple flows sharing
    # a node stack rather than overlap)
    node_cursor_out = {k: node_positions[k][0] for k in node_positions}
    node_cursor_in = {k: node_positions[k][0] for k in node_positions}
    for from_stage, from_node, to_node, value in flows:
        to_stage = from_stage + 1
        y0_bottom = node_cursor_out[(from_stage, from_node)]
        y0_top = y0_bottom + value
        node_cursor_out[(from_stage, from_node)] = y0_top

        y1_bottom = node_cursor_in[(to_stage, to_node)]
        y1_top = y1_bottom + value
        node_cursor_in[(to_stage, to_node)] = y1_top

        x0, x1 = stage_x[from_stage], stage_x[to_stage]
        xs = np.linspace(x0, x1, 30)
        smooth = 0.5 - 0.5 * np.cos(np.pi * (xs - x0) / (x1 - x0))
        top = y0_top + (y1_top - y0_top) * smooth
        bottom = y0_bottom + (y1_bottom - y0_bottom) * smooth
        ax.fill_between(xs, bottom, top, color=node_color_map[(from_stage, from_node)], alpha=0.45)

    for (stage_idx, node), (y0, y1) in node_positions.items():
        x = stage_x[stage_idx]
        ax.add_patch(plt.Rectangle((x - 0.008, y0), 0.016, y1 - y0, color=node_color_map[(stage_idx, node)]))
        ha = "right" if stage_idx == 0 else ("left" if stage_idx == n_stages - 1 else "center")
        label_x = x - 0.015 if stage_idx == 0 else (x + 0.015 if stage_idx == n_stages - 1 else x)
        ax.text(label_x, (y0 + y1) / 2, f"{node}\n({y1 - y0:.0f})", color="white", fontsize=9,
                ha=ha, va="center", fontweight="bold")

    ax.set_xlim(-0.15, 1.15)
    ax.axis("off")
    fig.tight_layout()
    return fig


def _content_span(fig, axes):
    """(bottom, top) of everything actually drawn in `axes` -- nodes, headshots, names, lines -- as fractions of the figure height,
    so a colour bar can be made exactly as tall as the drawing it explains."""
    from matplotlib.offsetbox import AnnotationBbox
    from matplotlib.text import Text
    renderer = fig.canvas.get_renderer()
    lo, hi = None, None
    for ax in axes:
        for art in ax.get_children():
            try:
                if isinstance(art, Text) and not art.get_text().strip():
                    continue
                if not isinstance(art, (Text, AnnotationBbox)) and art.__class__.__name__ not in ("Line2D", "PathCollection"):
                    continue
                if not art.get_visible():
                    continue
                bb = art.get_window_extent(renderer)
                y0, y1 = fig.transFigure.inverted().transform([(0, bb.y0), (0, bb.y1)])[:, 1]
                if not (np.isfinite(y0) and np.isfinite(y1)):
                    continue
                lo = y0 if lo is None else min(lo, y0)
                hi = y1 if hi is None else max(hi, y1)
            except Exception:
                continue
    return (lo, hi) if lo is not None and hi is not None and hi > lo else None


def _clean_pair_edges(pair_labels, pair_values, pair_minutes=None):
    """
    One value per unordered pair of players, from raw (a, b) labels + values.
    Self-pairs (two teammates sharing the same abbreviated name, e.g. two
    "J. Williams") and non-finite values are dropped, and duplicate pairs
    are averaged instead of being drawn on top of each other. Returns a
    dict {frozenset({a, b}): value}, and, if pair_minutes is given, a
    second dict {frozenset({a, b}): minutes} (summed across duplicates,
    since minutes are additive where a rating is not).
    """
    buckets = {}
    minute_buckets = {}
    pair_minutes = pair_minutes or [None] * len(pair_labels)
    for (a, b), val, mins in zip(pair_labels, pair_values, pair_minutes):
        a, b = str(a).strip(), str(b).strip()
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        if a == b or not np.isfinite(val):
            continue
        key = frozenset((a, b))
        buckets.setdefault(key, []).append(val)
        if mins is not None:
            minute_buckets[key] = minute_buckets.get(key, 0.0) + float(mins)
    edges = {k: sum(v) / len(v) for k, v in buckets.items()}
    if any(pm is not None for pm in pair_minutes):
        return edges, minute_buckets
    return edges, {}


def _name_label(ax, text, xy, below_of_height_pts, *, fontsize=10, above=False, zorder=4):
    """Player name pinned to an exact offset (in POINTS) from (x, y), measured from
    the image's own edge -- data units can't guarantee a gap because the image
    is sized in points, which is why names used to land on top of images."""
    import matplotlib.patheffects as pe
    off = below_of_height_pts / 2 + 3
    label = ax.annotate(text, xy=xy, xytext=(0, off if above else -off), textcoords="offset points",
                        ha="center", va="bottom" if above else "top", color="white",
                        fontsize=fontsize, fontweight="bold", zorder=zorder, annotation_clip=False)
    # Thin dark outline so a name stays legible where a polygon edge passes
    # behind it (e.g. under a triangle's apex, where the two sides converge).
    label.set_path_effects([pe.withStroke(linewidth=2.5, foreground="#0d0d0d")])
    return label


def build_network_diagram(pair_labels, pair_values, player_image_urls=None, value_label="Net Rating",
                           width=12, height=12, return_hotspot_data=False, pair_minutes=None):
    """
    Nodes are players, edges are 2-man lineup pairs weighted/colored by
    how that pairing actually performed together (net rating or a
    similar per-pair stat) -- reveals which combinations of teammates
    work especially well or poorly, which a player-by-player stat line
    can't show on its own. pair_labels: list of (player_a, player_b)
    tuples. pair_values: matching list of that pair's stat value.

    Players sit in a fixed circle rather than a force-directed layout,
    ordered clockwise from 12 o'clock by the average value across each
    player's own 7 strongest connections -- the player with the best
    such average sits at the top, then each successive position going
    clockwise is the next-best, so position around the circle itself
    carries meaning instead of being an arbitrary force-layout
    artifact. Shows real headshot images at each node (falling back to
    a plain circle with initials only if that specific image fails to
    load) rather than a single flat team color, since a lineup network
    inherently involves many different players at once, not one
    consistent "team" to color everything by.

    Nodes, positions and edges all come from ONE cleaned edge table
    (_clean_pair_edges), so an edge can never reference a player that has
    no position -- the source of a reported KeyError at pos[a].
    """
    prefetch_images(list((player_image_urls or {}).values()))
    from matplotlib.colors import Normalize
    from matplotlib.cm import ScalarMappable

    player_image_urls = player_image_urls or {}
    edges, minute_edges = _clean_pair_edges(pair_labels, pair_values, pair_minutes)

    if not edges:
        fig, ax = plt.subplots(figsize=(width, 2))
        fig.patch.set_alpha(0)
        ax.text(0.5, 0.5, "Not enough valid lineup pairs to draw this network.",
                color="white", ha="center", va="center", fontsize=13)
        ax.axis("off")
        if return_hotspot_data:
            return fig, {}, {}, {}
        return fig

    neighbors = {}
    for edge, val in edges.items():
        a, b = tuple(edge)
        neighbors.setdefault(a, []).append(val)
        neighbors.setdefault(b, []).append(val)

    # Each player's own average across their top-7 strongest connections
    # (by value, not absolute value, so being part of a lot of *bad*
    # pairings doesn't count as "strong") -- this average is what
    # determines circle position, not just raw connection count.
    player_avg = {p: sum(sorted(v, reverse=True)[:7]) / len(sorted(v, reverse=True)[:7]) for p, v in neighbors.items()}
    ordered_players = sorted(player_avg, key=lambda n: (-player_avg[n], n))
    n = len(ordered_players)
    pos = {}
    for i, player in enumerate(ordered_players):
        angle = np.pi / 2 - (i / n) * 2 * np.pi  # start at 12 o'clock, go clockwise
        pos[player] = (np.cos(angle), np.sin(angle))

    fig, ax = plt.subplots(figsize=(width, height))
    fig.subplots_adjust(left=0.03, right=0.87, top=0.97, bottom=0.03)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    values = list(edges.values())
    v_min, v_max = min(values), max(values)
    norm = Normalize(vmin=-20, vmax=20, clip=True)
    cmap = plt.cm.RdYlGn

    # Line THICKNESS reflects minutes played together (how much to trust
    # this number), separate from line COLOR, which reflects the rating
    # itself -- a +3 net rating over 500 minutes together is a more
    # reliable read than the same +3 over just 300, and should look it,
    # rather than a same-value pair always drawing identically regardless
    # of sample size. Falls back to rating-based width (the old behavior)
    # when no minutes data is available at all.
    if minute_edges:
        m_vals = list(minute_edges.values())
        m_min, m_max = min(m_vals), max(m_vals)

        def _lw(edge_key, val):
            mins = minute_edges.get(edge_key)
            if mins is None or m_max <= m_min:
                return 1.5 + 5 * (val - v_min) / (v_max - v_min + 1e-9)
            return 1.0 + 6 * (mins - m_min) / (m_max - m_min + 1e-9)
    else:
        def _lw(edge_key, val):
            return 1.5 + 5 * (val - v_min) / (v_max - v_min + 1e-9)

    for edge, val in edges.items():
        a, b = tuple(edge)
        (x0, y0), (x1, y1) = pos[a], pos[b]
        lw = _lw(edge, val)
        edge_color = cmap(norm(val))
        if val > 20 or val < -20:
            # Glowing effect for anything outside the meaningful -20/+20
            # range -- a soft, wider halo in the same color underneath the
            # main line, rather than just clipping color at the extremes.
            for glow_lw, glow_alpha in ((lw + 10, 0.12), (lw + 5, 0.20)):
                ax.plot([x0, x1], [y0, y1], color=edge_color, linewidth=glow_lw, alpha=glow_alpha, zorder=0)
        ax.plot([x0, x1], [y0, y1], color=edge_color, linewidth=lw, alpha=0.75, zorder=1)

    for node in ordered_players:
        x, y = pos[node]
        url = player_image_urls.get(node)
        img = _fetch_image_small(url, 300) if url else None
        last_name = node.split()[-1] if len(node.split()) > 1 else node
        if img is not None:
            zoom = 0.078 * 760 / max(img.height, 1)   # same on-screen size as before, whatever the source size
            imagebox = OffsetImage(np.array(img), zoom=zoom)
            ax.add_artist(AnnotationBbox(imagebox, (x, y), frameon=False, box_alignment=(0.5, 0.5), zorder=3))
            # Above the image for nodes in the top half, below for the
            # bottom half (keeps labels off the edges radiating inward),
            # at an exact point offset from the image's own edge.
            _name_label(ax, last_name, (x, y), img.height * zoom, fontsize=11, above=(y >= 0))
        else:
            # No separate label added here -- this fallback circle's
            # own text already identifies the player.
            ax.scatter([x], [y], s=3000, color="#1a1a1a", edgecolor="#888888", linewidth=2, zorder=2)
            first_name_initial = node.split()[0][0] if node.split() else "?"
            ax.text(x, y, f"{first_name_initial}. {last_name}", color="white", fontsize=8.5,
                    ha="center", va="center", zorder=3, fontweight="bold")

    ax.set_xlim(-1.35, 1.35)
    ax.set_ylim(-1.35, 1.35)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.canvas.draw()       # settle the layout so the drawing's real extent can be measured

    sm = ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    # An explicit figure-relative axes (rather than fig.colorbar(..., ax=ax)'s
    # default sizing): exactly as tall as the network drawing itself (top of the top name to the bottom of the bottom one).
    span = _content_span(fig, [ax])
    y0, y1 = span if span else (0.05, 0.95)
    cbar_ax = fig.add_axes([0.905, max(y0, 0.0), 0.025, min(y1, 1.0) - max(y0, 0.0)])       # exactly as tall as the network drawing
    cbar = fig.colorbar(sm, cax=cbar_ax, orientation="vertical")
    cbar.set_label(value_label, color="white", fontsize=15)
    cbar.ax.tick_params(colors="white", labelsize=13)
    cbar.outline.set_visible(False)

    if return_hotspot_data:
        return fig, pos, edges, minute_edges
    return fig


def build_lineup_shapes_diagram(groups, two_man_lookup, player_image_urls=None,
                                 value_label="Net Rating", width=14, cell_size=3.2, return_hotspot_data=False):
    """
    For 3/4/5-man lineups -- a genuinely different visualization from
    build_network_diagram's single circular pairwise graph, since a
    group of 3+ isn't really one pairwise relationship the way a 2-man
    lineup is: one polygon per qualifying group (triangle for 3-man,
    diamond for 4-man, pentagon for 5-man), laid out in a grid, best net
    rating first. Every qualifying group is drawn, not just a top-N sample.

    groups: list of (tuple_of_N_player_names, group_net_rating) or, to also print the minutes the group played
        together under the rating label, (tuple_of_N_player_names, group_net_rating, minutes).
    two_man_lookup: dict frozenset({playerA, playerB}) -> that pair's own
        2-man rating, used to color each polygon SIDE (the pairwise
        relationship inside the group); the group's own rating is the
        number in the middle.

    Layout is solved in POINTS, not data units. Each panel is a fixed
    physical size, every image is sized in points, and each player's name is
    placed a fixed number of points below the bottom edge of THAT image --
    so a name can never overlap an image, whatever the polygon size. The
    polygon radius is then solved so the polygon plus its images and names
    fill the panel out to its margins (5-man panels included), instead of
    using one hard-coded radius for every lineup size.
    """
    prefetch_images(list((player_image_urls or {}).values()))
    if not groups:
        fig, ax = plt.subplots(figsize=(width, 2))
        fig.patch.set_alpha(0)
        ax.text(0.5, 0.5, "No combinations meet the minimum minutes threshold.",
                color="white", ha="center", va="center", fontsize=13)
        ax.axis("off")
        if return_hotspot_data:
            return fig, []
        return fig

    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from matplotlib.cm import ScalarMappable

    player_image_urls = player_image_urls or {}
    two_man_lookup = two_man_lookup or {}

    # Best-to-worst net rating, so the strongest combinations are the first
    # thing seen. Ties broken by names so the order is stable between reruns.
    groups = sorted(groups, key=lambda g: (-g[1], " | ".join(g[0])))

    cmap = LinearSegmentedColormap.from_list("net_rating", ["#c0392b", "#f1c40f", "#27ae60"])
    norm = Normalize(vmin=-20, vmax=20, clip=True)

    n_groups = len(groups)
    size_n = len(groups[0][0])
    # As square a grid as possible: 9 groups -> 3x3, 5 -> 3 + 2, 10 -> 4 + 4 + 2 -- never a long row of 5 over a row
    # of 4. The last row is centred. (`width` is kept for compatibility; the figure now sizes itself to the grid.)
    full_cols = max(1, math.ceil(math.sqrt(n_groups)))
    n_rows = math.ceil(n_groups / full_cols)
    # Square panels. Few groups -> big panels, so a single 5-man lineup fills the whole image; many groups -> panels
    # shrink to keep the figure's long side near 10in, but never below what an image plus a name need.
    min_cell = 3.0 if size_n >= 5 else 2.6
    cell_in = float(np.clip(10.0 / max(full_cols, n_rows), min_cell, 7.5))
    cell_w_in = cell_h_in = cell_in
    margin_in, cbar_in = 0.15, 1.0
    fig_w = cell_in * full_cols + cbar_in + 2 * margin_in
    fig_h = cell_in * n_rows + 2 * margin_in
    fig = plt.figure(figsize=(fig_w, fig_h))
    fig.patch.set_alpha(0)
    panel_data = []

    cw, ch = cell_w_in * 72, cell_h_in * 72       # panel size in points
    ref = min(cw, ch) / 245.0                     # 1.0 at the reference panel (3.4in)
    # Image heights in points: pentagons get noticeably smaller images than
    # triangles/diamonds (5 of them share the same panel).
    base_h = {3: 38, 4: 36, 5: 24}.get(size_n, 30) * ref
    text_scale = min(1.35, max(1.0, ref))          # a big single panel gets proportionally bigger text
    name_fs = (9 if size_n <= 4 else 8) * text_scale
    gap = 3.0 * text_scale
    label_h = name_fs * 1.25
    pad = 8 + 0.03 * min(cw, ch)

    for idx, grp in enumerate(groups):
        players, group_rating = grp[0], grp[1]
        minutes = grp[2] if len(grp) > 2 else None        # minutes played together, when the caller has them
        row, col = divmod(idx, full_cols)
        in_row = min(full_cols, n_groups - row * full_cols)
        x_in = margin_in + (col + (full_cols - in_row) / 2.0) * cell_w_in
        y_in = fig_h - margin_in - (row + 1) * cell_h_in
        ax = fig.add_axes([x_in / fig_w, y_in / fig_h, cell_w_in / fig_w, cell_h_in / fig_h])
        ax.set_facecolor("none")
        ax.set_xlim(-cw / 2, cw / 2)
        ax.set_ylim(-ch / 2, ch / 2)
        ax.axis("off")

        n = len(players)
        angles = [np.pi / 2 + 2 * np.pi * i / n for i in range(n)]
        unit = [(np.cos(a), np.sin(a)) for a in angles]

        # Per-vertex box (image + gap + name), in points, relative to the vertex.
        boxes = []
        images = []
        for p in players:
            url = player_image_urls.get(p)
            img = _fetch_image_small(url, 300) if url else None
            images.append(img)
            last_name = p.split()[-1] if len(p.split()) > 1 else p
            if img is not None:
                h_pts = base_h
                w_pts = base_h * img.width / max(img.height, 1)
            else:
                h_pts = w_pts = base_h * 0.85
            name_w = 0.62 * name_fs * len(last_name)
            boxes.append((max(w_pts, name_w) / 2, h_pts, last_name))

        def extents(R):
            xs_lo = min(R * ux - hw for (ux, _), (hw, _, _) in zip(unit, boxes))
            xs_hi = max(R * ux + hw for (ux, _), (hw, _, _) in zip(unit, boxes))
            ys_lo = min(R * uy - (h / 2 + gap + label_h) for (_, uy), (_, h, _) in zip(unit, boxes))
            ys_hi = max(R * uy + h / 2 for (_, uy), (_, h, _) in zip(unit, boxes))
            return xs_lo, xs_hi, ys_lo, ys_hi

        R = 20.0
        for cand in np.arange(min(cw, ch), 20, -1.0):
            xl, xh, yl, yh = extents(cand)
            if (xh - xl) <= cw - 2 * pad and (yh - yl) <= ch - 2 * pad:
                R = float(cand)
                break
        xl, xh, yl, yh = extents(R)
        shift_x, shift_y = -(xl + xh) / 2, -(yl + yh) / 2     # centre the whole drawing in the panel
        vertex = {p: (R * ux + shift_x, R * uy + shift_y) for p, (ux, uy) in zip(players, unit)}
        centre = (shift_x, shift_y)

        def _draw_edge(a, b, val):
            color = cmap(norm(val)) if val is not None else "#555555"
            (xa, ya), (xb, yb) = vertex[a], vertex[b]
            if val is not None and (val > 20 or val < -20):
                for glow_lw, glow_alpha in ((10, 0.12), (6, 0.20)):
                    ax.plot([xa, xb], [ya, yb], color=color, linewidth=glow_lw, alpha=glow_alpha, zorder=0)
            ax.plot([xa, xb], [ya, yb], color=color, linewidth=4, zorder=1, solid_capstyle="round")

        for i in range(n):
            a, b = players[i], players[(i + 1) % n]
            _draw_edge(a, b, two_man_lookup.get(frozenset({a, b})))

        for p, img, (_, h_pts, last_name) in zip(players, images, boxes):
            x, y = vertex[p]
            if img is not None:
                zoom = h_pts / max(img.height, 1)              # points = pixels * zoom
                ax.add_artist(AnnotationBbox(OffsetImage(np.array(img), zoom=zoom), (x, y),
                                             frameon=False, box_alignment=(0.5, 0.5), zorder=3))
            else:
                ax.scatter([x], [y], s=(h_pts * 0.95) ** 2, color="#1a1a1a", edgecolor="#888888",
                           linewidth=1.5, zorder=2)
            # Always directly UNDER the image, at a fixed point offset from its bottom edge.
            _name_label(ax, last_name, (x, y), h_pts, fontsize=name_fs)

        ax.text(centre[0], centre[1] + 5, f"{group_rating:+.1f}", color="white", fontsize=17 * min(1.4, ref + 0.1),
                fontweight="bold", ha="center", va="center", zorder=5)
        ax.text(centre[0], centre[1] - 14 * ref, value_label, color="#aaaaaa", fontsize=9 * text_scale,
                ha="center", va="center", zorder=5)
        if minutes is not None and np.isfinite(minutes):
            # the minutes this group played together, directly under the "Net Rating" label
            ax.text(centre[0], centre[1] - 14 * ref - 11.5 * text_scale, f"{minutes:,.0f} min", color="#8f8f8f",
                    fontsize=8.5 * text_scale, ha="center", va="center", zorder=5)
        # Collected only for the optional interactive-hover overlay --
        # doesn't change anything about the panel just drawn above.
        if return_hotspot_data:
            panel_data.append({
                "players": players, "ax": ax, "vertex": dict(vertex), "centre": centre,
                "rating": group_rating, "minutes": minutes,
            })

    sm = ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    # The colorbar spans the WHOLE grid (every row), not just the first few.
    panel_axes = [a_ for a_ in fig.axes]
    span = _content_span(fig, panel_axes)
    y0, y1 = span if span else (margin_in / fig_h, 1 - margin_in / fig_h)
    cbar_ax = fig.add_axes([(fig_w - 0.80) / fig_w, max(y0, 0.0), 0.16 / fig_w, min(y1, 1.0) - max(y0, 0.0)])   # top of the first drawing to the bottom of the last
    cbar = fig.colorbar(sm, cax=cbar_ax, orientation="vertical")
    cbar.set_label(value_label, color="white", fontsize=13)
    cbar.ax.tick_params(colors="white", labelsize=11)
    cbar.outline.set_visible(False)
    if return_hotspot_data:
        return fig, panel_data
    return fig


def build_momentum_chart(x_labels, values, stat_display_name, subject_name, team_color,
                          width=8, height=7):
    """
    A stylized trend chart highlighting scoring runs and momentum
    shifts, rather than just a plain line -- adapted here to game-to-
    game momentum across a season (hot/cold streaks: consecutive games
    above/below the season average) rather than within-game score
    differential, since play-by-play data isn't available from this
    data source to track momentum minute-by-minute inside a single
    game the way the full spec envisions.
    """
    values_arr = np.asarray(values, dtype=float)
    avg = values_arr.mean()
    x = np.arange(len(values_arr))

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    # Shades hot (above-average) and cold (below-average) streak runs
    # as background bands, so runs read as *regions* rather than
    # needing to be inferred from the line's wiggle alone
    above = values_arr >= avg
    run_start = 0
    for i in range(1, len(above) + 1):
        if i == len(above) or above[i] != above[run_start]:
            if i - run_start >= 3:  # only shade runs of 3+ games -- meaningful streaks, not noise
                color = "#2E8B57" if above[run_start] else "#8B3A3A"
                ax.axvspan(run_start - 0.5, i - 0.5, color=color, alpha=0.18, zorder=0)
            run_start = i

    ax.plot(x, values_arr, color=team_color, linewidth=2, zorder=2)
    ax.scatter(x, values_arr, color=team_color, s=25, zorder=3)
    ax.axhline(avg, color="white", linestyle="--", linewidth=1, alpha=0.6, zorder=1)
    ax.text(len(x) - 1, avg, f"  season avg: {avg:.1f}", color="white", fontsize=9, va="center")

    step = max(1, len(x_labels) // 15)
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels([x_labels[i] for i in range(0, len(x_labels), step)],
                        color="white", fontsize=8, rotation=45, ha="right")
    ax.set_ylabel(f"{subject_name} -- {stat_display_name} Momentum (Hot/Cold Streaks)", color="white", fontsize=11, fontweight="bold")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)

    fig.tight_layout()
    return fig


def build_impact_clock(quarter_stats, player_name, team_color, width=8, height=7.5):
    """
    A real clock face representing the 4 quarters of a game -- 12
    o'clock is tip-off, and going clockwise, each 90-degree quadrant is
    one quarter (Q1: 12-3, Q2: 3-6, Q3: 6-9, Q4: 9-12), so position
    around the face directly maps to when in the game that production
    happened, not an arbitrary decoration. The hand points to the
    start of the player's single best-scoring quarter, and that
    quarter's quadrant is shaded in the player's own color, making
    "when this player does their best work" readable at a glance
    before ever looking at the numbers.

    quarter_stats: list of 4 dicts, one per quarter in order (Q1-Q4),
    each with "PTS", "FG_PCT", and "PLUS_MINUS" keys -- per-quarter
    splits from get_player_stats_by_quarter(). "Best" is determined by
    PTS, the most immediately intuitive single measure of scoring
    output, rather than a composite score that would need its own
    explanation to trust.
    """
    fig, ax = plt.subplots(figsize=(width, height), subplot_kw=dict(polar=True))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    ax.set_position([0.12, 0.02, 0.76, 0.90])
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)  # clockwise, matching a real clock face

    # Name sits directly above the clock with no title, subtitle, or
    # verdict line in between -- all of that was deleted per explicit
    # request; the clock face and its own in-quadrant stats now carry
    # the "which quarter is best" information entirely on their own.
    fig.text(0.5, 0.90, player_name, color="white", fontsize=16, fontweight="bold",
              family="serif", ha="center", va="top")

    best_idx = max(range(len(quarter_stats)), key=lambda i: quarter_stats[i]["PTS"])

    # Each quadrant boundary sits at a clean 90-degree mark (Q1 starts
    # at 0=12 o'clock, Q2 at 90=3 o'clock, Q3 at 180=6 o'clock, Q4 at
    # 270=9 o'clock) -- the shaded quadrant is the player's single best
    # quarter, and the hand points exactly to where that quarter
    # begins.
    for q in range(4):
        start_deg = q * 90
        theta_range = np.linspace(np.radians(start_deg), np.radians(start_deg + 90), 50)
        is_best = (q == best_idx)
        ax.fill_between(theta_range, 0, 1, color=team_color if is_best else "#333333",
                         alpha=0.65 if is_best else 0.25)

    for q in range(4):
        angle = np.radians(q * 90)
        ax.plot([angle, angle], [0, 1], color="#555555", linewidth=1)

    hand_angle = np.radians(best_idx * 90)
    ax.plot([hand_angle, hand_angle], [0, 0.92], color="white", linewidth=3, solid_capstyle="round", zorder=5)
    ax.scatter([0], [0], s=120, color="white", zorder=6)

    for q in range(4):
        label_angle = np.radians(q * 90 + 45)
        ax.text(label_angle, 1.15, f"Q{q + 1}", color="white", fontsize=13, fontweight="bold",
                family="serif", ha="center", va="center")

    # Stats live inside each quadrant now, not in a separate list below
    # the clock -- three lines (PTS, FG%, +/-) stacked at decreasing
    # radius within that quadrant's own angular midpoint, all in white
    # regardless of which quadrant is the shaded "best" one, per
    # explicit request.
    for q, stats in enumerate(quarter_stats):
        mid_angle = np.radians(q * 90 + 45)
        # Q2/Q3 sit in the bottom half of the clock, where increasing
        # radius moves a point further down the screen (the opposite
        # of the top half, where increasing radius moves up) -- without
        # flipping the radius order here, PTS/FG%/+/- would read
        # top-to-bottom in Q1/Q4 but bottom-to-top in Q2/Q3, confirmed
        # via direct visual testing showing exactly that inconsistency.
        radii = (0.38, 0.52, 0.68) if q in (1, 2) else (0.68, 0.52, 0.38)
        ax.text(mid_angle, radii[0], f"{stats['PTS']:.1f} pts", color="white", fontsize=10,
                fontweight="bold", family="serif", ha="center", va="center")
        ax.text(mid_angle, radii[1], f"{stats['FG_PCT']:.1%} FG", color="white", fontsize=9,
                family="serif", ha="center", va="center")
        ax.text(mid_angle, radii[2], f"{stats['PLUS_MINUS']:+.1f} +/-", color="white", fontsize=9,
                family="serif", ha="center", va="center")

    ax.set_ylim(0, 1.2)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.spines["polar"].set_visible(False)
    ax.grid(False)

    return fig


def build_bump_chart(seasons, entity_ranks, team_color, highlight_names=None, entity_image_urls=None,
                      width=8, height=8):
    """
    Lines showing each entity's rank position changing over time,
    crossing over each other as ranks shift -- adapted to season-to-
    season league rank (e.g. scoring rank each season) rather than
    week-to-week, since weekly-binned league-wide rank data isn't
    available from this data source without fetching and ranking
    every player's game log individually, which season-level
    get_player_stats() already does in one call per season.

    entity_ranks: dict of {entity_name: [rank_per_season]}, same
    length/order as seasons. Y-axis is inverted so rank 1 sits at the
    top, matching how standings/leaderboards are normally read.

    entity_image_urls: optional dict of {entity_name: image_url} --
    shows a real player headshot or team logo at the end of each
    highlighted line instead of just a colored dot, falling back to
    text-only identification for any entity missing a URL or whose
    image fails to load.
    """
    prefetch_images(list((entity_image_urls or {}).values()))
    highlight_names = set(highlight_names or [])
    entity_image_urls = entity_image_urls or {}
    neutral_color = "#555555"

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    x = range(len(seasons))
    palette = [team_color, "#D4AF37", "#B5B5B5", "#8a6410", "#6B6B6B", "#F5D370"]
    color_idx = 0
    for name, ranks in entity_ranks.items():
        is_hl = name in highlight_names or not highlight_names
        if is_hl:
            color = palette[color_idx % len(palette)]
            color_idx += 1
        else:
            color = neutral_color
        lw = 2.2 if is_hl else 1
        alpha = 1.0 if is_hl else 0.3
        ax.plot(x, ranks, color=color, linewidth=lw, alpha=alpha, marker="o", markersize=6 if is_hl else 3)
        if is_hl:
            end_x, end_y = len(x) - 1, ranks[-1]
            img = _fetch_image(entity_image_urls.get(name)) if entity_image_urls.get(name) else None
            if img is not None:
                imagebox = OffsetImage(np.array(img), zoom=0.045)
                ax.add_artist(AnnotationBbox(imagebox, (end_x + 0.35, end_y), frameon=False,
                                              box_alignment=(0.5, 0.5), annotation_clip=False, zorder=4))
                ax.text(end_x + 0.65, end_y, name, color=color, fontsize=9, va="center", fontweight="bold")
            else:
                ax.text(end_x + 0.1, end_y, name, color=color, fontsize=9, va="center", fontweight="bold")

    ax.invert_yaxis()
    ax.set_xticks(list(x))
    ax.set_xticklabels(seasons, color="white", fontsize=10, rotation=20 if len(seasons) > 6 else 0)
    ax.set_ylabel("League Rank Over Time", color="white", fontsize=11, fontweight="bold")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return fig


# Court areas the Passing Web places receivers in -- the NBA's own shot zones (the ones on every shot chart), split by
# side: the restricted area, the rest of the paint, mid-range (baseline / elbow-wing / straightaway), the two corner 3s,
# the two wing 3s and the top-of-the-key 3. Keys shared with app.py's own per-receiver zone lookup.
PASSING_ZONES = ("ra", "paint", "lmid_base", "lmid_wing", "mid_c", "rmid_wing", "rmid_base",
                 "lc3", "rc3", "lw3", "top3", "rw3")
PASSING_ZONE_NAMES = {
    "ra": "restricted area", "paint": "paint (outside the restricted area)",
    "lmid_base": "left baseline mid-range", "lmid_wing": "left elbow mid-range", "mid_c": "straightaway mid-range",
    "rmid_wing": "right elbow mid-range", "rmid_base": "right baseline mid-range",
    "lc3": "left corner 3", "rc3": "right corner 3", "lw3": "left wing 3", "top3": "top-of-the-key 3",
    "rw3": "right wing 3",
}


def court_zone_key(shot_zone_basic, shot_zone_area, loc_x):
    """
    One shot's Passing Web area, from the NBA's own zone fields. The SIDE always comes from the shot's own LOC_X sign
    (the same coordinate every court chart here plots), never from the "Left"/"Right" wording in the zone names, so a
    receiver lands on the same side of the court that their own Shot Chart shows them shooting from. None for
    backcourt heaves.
    """
    basic = str(shot_zone_basic or "")
    area = str(shot_zone_area or "")
    side = "l" if (loc_x or 0) < 0 else "r"
    if basic == "Restricted Area":
        return "ra"
    if basic == "In The Paint (Non-RA)":
        return "paint"
    if basic == "Mid-Range":
        if area.startswith("Center"):
            return "mid_c"
        return f"{side}mid_wing" if "Center" in area else f"{side}mid_base"
    if "Corner 3" in basic:
        return f"{side}c3"
    if basic == "Above the Break 3":
        return "top3" if area.startswith("Center") else f"{side}w3"
    return None


def court_zone_key_from_xy(x, y):
    """The same areas as court_zone_key(), from a raw court position (for callers that only have coordinates)."""
    side = "l" if x < 0 else "r"
    dist = math.hypot(x, y)
    angle = abs(math.degrees(math.atan2(x, y)))     # 0 = straight out from the basket
    if abs(x) >= 220 and y <= 92.5:
        return f"{side}c3"
    if dist >= 237.5:
        return "top3" if angle < 22.5 else f"{side}w3"
    if dist <= 40:
        return "ra"
    if abs(x) < 80 and y < 142.5:
        return "paint"
    if abs(x) < 80:
        return "mid_c"
    return f"{side}mid_base" if angle > 67.5 else f"{side}mid_wing"


def points_in_areas(x, y, areas):
    """Boolean mask: which (x, y) court points fall inside ANY of the areas (lists of (x, y) outline points)."""
    from matplotlib.path import Path
    pts = np.column_stack([np.asarray(x, dtype=float), np.asarray(y, dtype=float)])
    mask = np.zeros(len(pts), dtype=bool)
    for poly in areas or []:
        if poly is not None and len(poly) >= 3:
            mask |= Path(np.asarray(poly, dtype=float)).contains_points(pts)
    return mask


def build_area_zoom_chart(shots_df, areas, color, width=5.0, pad=24):
    """
    One player's shots, zoomed in on the court area(s) someone circled: the court lines, every shot of his that lands
    in the zoomed window (makes in `color`, misses as grey crosses), the ones outside the circled area faded, and the
    area itself outlined in dashed gold. The figure's shape follows the area (a corner 3 comes out tall, the top of the
    key wide).
    """
    polys = [np.asarray(p, dtype=float) for p in (areas or []) if p is not None and len(p) >= 3]
    allpts = np.vstack(polys) if polys else np.array([[-250, -47.5], [250, 300]])
    x0, y0 = allpts.min(axis=0) - pad
    x1, y1 = allpts.max(axis=0) + pad
    x0, x1 = max(x0, -252), min(x1, 252)
    y0, y1 = max(y0, -52), min(y1, 420)
    if x1 - x0 < 90:                        # never zoom so far in that one shot fills the picture
        cx = (x0 + x1) / 2
        x0, x1 = cx - 45, cx + 45
    if y1 - y0 < 90:
        cy = (y0 + y1) / 2
        y0, y1 = cy - 45, cy + 45
    h = float(np.clip(width * (y1 - y0) / (x1 - x0), 2.4, 6.2))
    fig, ax = plt.subplots(figsize=(width, h))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    draw_court(ax, color="#8a8a8a", lw=1.4)
    for p in polys:
        ax.add_patch(matplotlib.patches.Polygon(p, closed=True, fill=True, facecolor=(0.83, 0.69, 0.22, 0.10),
                                                edgecolor="#D4AF37", linewidth=1.8, linestyle=(0, (5, 4)), zorder=1))
    if shots_df is not None and not shots_df.empty:
        sx = shots_df["LOC_X"].astype(float).to_numpy()
        sy = shots_df["LOC_Y"].astype(float).to_numpy()
        made = shots_df["SHOT_MADE_FLAG"].astype(int).to_numpy() == 1
        inside = points_in_areas(sx, sy, polys)
        view = (sx >= x0) & (sx <= x1) & (sy >= y0) & (sy <= y1)
        for sel, alpha in ((view & ~inside, 0.22), (view & inside, 1.0)):
            ax.scatter(sx[sel & ~made], sy[sel & ~made], marker="x", s=34, linewidths=1.4, color=MISSED_SHOT_COLOR,
                       alpha=alpha * 0.9, zorder=2)
            ax.scatter(sx[sel & made], sy[sel & made], s=44, color=color, edgecolors="#111111", linewidths=0.6,
                       alpha=alpha, zorder=3)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig


_THREE_ZONES = ("lc3", "rc3", "lw3", "rw3", "top3")


def court_zone_key_for_shot(x, y, shot_value=None):
    """
    court_zone_key_from_xy(), made consistent with whether the shot actually counted as a 2 or a 3 -- a location can
    sit a few inches either side of the painted line, and the NBA's own value for the shot decides it.
    """
    zone = court_zone_key_from_xy(x, y)
    side = "l" if x < 0 else "r"
    angle = abs(math.degrees(math.atan2(x, y)))
    if shot_value == 3 and zone not in _THREE_ZONES:
        if abs(x) >= 200 and y <= 92.5:
            return f"{side}c3"
        return "top3" if angle < 22.5 else f"{side}w3"
    if shot_value == 2 and zone in _THREE_ZONES:
        if abs(x) < 80:
            return "mid_c"
        return f"{side}mid_base" if angle > 67.5 else f"{side}mid_wing"
    return zone


# ---------------------------------------------------------------- Passing Web layout
# Where a receiver goes when all that is known is the area's name (no shot positions to average).
_PASS_ANCHORS = {
    "top3": (0, 300), "ra": (0, 10), "paint": (0, 100), "mid_c": (0, 212),
    "lw3": (-175, 222), "rw3": (175, 222), "lc3": (-228, 16), "rc3": (228, 16),
    "lmid_wing": (-128, 150), "rmid_wing": (128, 150), "lmid_base": (-150, 30), "rmid_base": (150, 30),
    # (older keys, in case a caller still passes them)
    "lmid": (-128, 150), "rmid": (128, 150),
}
_PASS_FALLBACK_CYCLE = ["top3", "lw3", "rw3", "lc3", "rc3", "lmid_wing", "rmid_wing", "paint"]


def _zone_keys_array(x, y):
    """court_zone_key_from_xy() for whole arrays of court positions at once (same areas, same boundaries)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    side = np.where(x < 0, "l", "r")
    dist = np.hypot(x, y)
    angle = np.abs(np.degrees(np.arctan2(x, y)))
    conds = [(np.abs(x) >= 220) & (y <= 92.5), (dist >= 237.5) & (angle < 22.5), dist >= 237.5, dist <= 40,
             (np.abs(x) < 80) & (y < 142.5), np.abs(x) < 80, angle > 67.5]
    full = lambda s: np.full(x.shape, s, dtype="<U9")
    choices = [np.char.add(side, "c3"), full("top3"), np.char.add(side, "w3"), full("ra"), full("paint"),
               full("mid_c"), np.char.add(side, "mid_base")]
    return np.select(conds, choices, default=np.char.add(side, "mid_wing"))


def _target_in_zone(zone, xy):
    """
    A receiver's true spot: the average position of his shots in his area, nudged straight out from (or in toward)
    the basket until it sits inside that area -- the average of shots spread around the 3-point arc, for example,
    lands a little inside the arc.
    """
    if xy is None or zone not in _PASS_ANCHORS:
        return _PASS_ANCHORS.get(zone)
    x, y = float(xy[0]), float(xy[1])
    if court_zone_key_from_xy(x, y) == zone:
        return (x, y)
    r0, ang = math.hypot(x, y), math.atan2(x, y)
    radii = np.arange(0, 420, 2.0)
    keys = _zone_keys_array(radii * math.sin(ang), radii * math.cos(ang))
    hits = radii[keys == zone]
    if len(hits):
        r = hits[np.argmin(np.abs(hits - r0))]
        return (r * math.sin(ang), r * math.cos(ang))
    return _PASS_ANCHORS[zone]


def _pack_player_boxes(targets, zones, extents, fixed_boxes, bounds, order, gap=3.0, step=3.0):
    """
    Places every player as close as possible to his true spot while no two players' boxes overlap.

    A player's box is his headshot plus the lines of text under it (extents[i] = how far it reaches left, right, down
    and up from the centre of the picture). Nothing else matters for overlap: connection lines may cross pictures.
    "Close" is measured by the distance to his true spot, with a small extra cost for landing in a different area of
    the same kind (e.g. from a wing 3 into the top-of-the-key 3), a big one for crossing between 2-point and 3-point
    areas, and a little for changing distance from the basket (so a neighbour slides ALONG the arc rather than off it).
    That makes teammates who share an area sit right next to each other: side by side in the paint and at the top of
    the key, next to each other along the arc on a wing, stacked along the sideline in a corner.

    Players are placed biggest connection first (order), each on the best free spot of a fine grid, then everyone is
    re-placed a few times with the others fixed, which tidies up what the first pass left. Boxes stay inside `bounds`
    (the court); only if a player cannot fit there does the area grow (returned as the second value).
    """
    xs = np.arange(bounds[0] - 60, bounds[1] + 60 + step, step)
    ys = np.arange(bounds[2], bounds[3] + 170 + step, step)
    gx, gy = np.meshgrid(xs, ys)
    gx, gy = gx.ravel(), gy.ravel()
    keys = _zone_keys_array(gx, gy)
    is3 = np.isin(keys, list(_THREE_ZONES))
    radius = np.hypot(gx, gy)
    relaxed = (bounds[0] - 60, bounds[1] + 60, bounds[2], bounds[3] + 170)

    costs = {}
    for i in order:
        tx, ty = targets[i]
        c = np.hypot(gx - tx, gy - ty) + 0.5 * np.abs(radius - math.hypot(tx, ty))
        z = zones[i]
        if z:
            c = c + np.where(keys == z, 0.0, 12.0) + np.where(is3 == (z in _THREE_ZONES), 0.0, 60.0)
        costs[i] = c

    def box(i, p):
        l, r, d, u = extents[i]
        return (p[0] - l, p[0] + r, p[1] - d, p[1] + u)

    placed, grew = {}, False

    def best_spot(i):
        nonlocal grew
        others = list(fixed_boxes) + [box(j, placed[j]) for j in placed if j != i]
        l, r, d, u = extents[i]
        for k, (x0, x1, y0, y1) in enumerate((bounds, relaxed)):
            ok = (gx - l >= x0) & (gx + r <= x1) & (gy - d >= y0) & (gy + u <= y1)
            for bx0, bx1, by0, by1 in others:
                ok &= ~((gx - l < bx1 + gap) & (gx + r > bx0 - gap) & (gy - d < by1 + gap) & (gy + u > by0 - gap))
            if ok.any():
                grew = grew or k == 1
                j = int(np.argmin(np.where(ok, costs[i], np.inf)))
                return (float(gx[j]), float(gy[j]))
        return (float(targets[i][0]), float(targets[i][1]))

    for i in order:
        placed[i] = best_spot(i)
    for _ in range(3):
        before = dict(placed)
        grew = False
        for i in order:
            placed[i] = best_spot(i)
        if placed == before:
            break
    return placed, grew


def _receiver_lines(name, val, makes, extra):
    """The text under a receiver's picture: (offset below the picture's centre, text, colour, size, bold)."""
    LINE_H, y0 = 8, 30
    lines = [(y0, name, "white", 7, True), (y0 + LINE_H, "Stats from area:", "#bdbdbd", 5.5, False),
             (y0 + 2 * LINE_H, f"{val:.0f} passes received", "white", 5.5, False)]
    if extra and extra.get("fga", 0) > 0:
        fga = extra["fga"]
        fg3a = extra.get("fg3a", 0)
        lines.append((y0 + 3 * LINE_H, f"{makes:.0f}/{fga:.0f} – {makes / fga * 100:.0f}%", "white", 5.5, False))
        lines.append((y0 + 4 * LINE_H, f"{fg3a / fga * 100:.0f}% 3PA, {(fga - fg3a) / fga * 100:.0f}% 2PA",
                      "white", 5.5, False))
    else:
        lines.append((y0 + 3 * LINE_H, f"{makes:.0f} FGM", "white", 5.5, False))
    return lines


def build_court_connection_map(passer_name, receiver_names, receiver_values, receiver_makes,
                                team_color, passer_image_url=None, receiver_image_urls=None,
                                receiver_extra_stats=None, receiver_positions=None,
                                value_label="Passes", width=6, height=5, return_hotspot_data=False):
    """
    Lines on the court connecting a passer to each teammate he passed to, weighted by pass volume (NBA tracking --
    PlayerDashPtPass -- counts passer-to-receiver passes and the shots that followed, not where each pass travelled).

    Each teammate is drawn where he actually shot right after this passer's passes: receiver_positions has, per
    receiver, either {"zone": area key, "xy": (x, y) average position of those shots}, just an area key from
    PASSING_ZONES (placed at that area's usual spot), or a raw (x, y). The passer stands at the top of the
    free-throw circle.

    Every player is a box -- his headshot plus the text under it (name, passes, FG line, 3PA/2PA split), measured
    from the real rendered sizes -- and boxes never overlap; otherwise each player is as close to his true spot as
    the others allow (see _pack_player_boxes). A headshot that fails to load becomes a plain circle.
    """
    prefetch_images(list(receiver_image_urls or []) + [passer_image_url])
    fig, ax = new_court_figure(width=width, height=height)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    draw_court(ax, color="#888888", lw=1.2)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel(f"{passer_name} -- Passing Connections ({value_label})", color="white", fontsize=11, fontweight="bold")

    n = len(receiver_names)
    passer_pos = (0, 185)  # elevated, central "playmaker" spot at the top of the free-throw circle
    receiver_image_urls = list(receiver_image_urls or []) + [None] * n
    receiver_extra_stats = list(receiver_extra_stats or []) + [None] * n
    receiver_positions = list(receiver_positions or []) + [None] * n
    max_val = max(receiver_values) if receiver_values else 1
    R_ZOOM, R_CIRCLE, P_ZOOM, P_CIRCLE = 0.045, 380, 0.06, 550

    # ------------------------------------------------------------ measure every player's box (in court units)
    fig.tight_layout()
    ax.apply_aspect()
    renderer = fig.canvas.get_renderer()
    ax_px = ax.get_window_extent(renderer)
    x_lo, x_hi = ax.get_xlim()
    pt_per_unit = (ax_px.width * 72.0 / fig.dpi) / (x_hi - x_lo)
    inv = ax.transData.inverted()

    def picture_half(url, zoom, circle_size):
        img = _fetch_image(url) if url else None
        if img is not None:
            arr = np.asarray(img)
            return arr.shape[1] * zoom / 2 / pt_per_unit, arr.shape[0] * zoom / 2 / pt_per_unit
        r = math.sqrt(circle_size / math.pi) / pt_per_unit
        return r, r

    def text_extent(text, size, bold, dy):
        t = ax.text(0, -dy, text, fontsize=size, fontweight="bold" if bold else "normal", ha="center", va="center")
        bb = t.get_window_extent(renderer)
        t.remove()
        (a0, b0), (a1, b1) = inv.transform([(bb.x0, bb.y0), (bb.x1, bb.y1)])
        return min(a0, a1), max(a0, a1), min(b0, b1), max(b0, b1)

    def block_extents(url, zoom, circle_size, lines):
        hw, hh = picture_half(url, zoom, circle_size)
        left, right, down, up = hw, hw, hh, hh
        for dy, text, _c, size, bold in lines:
            a0, a1, b0, b1 = text_extent(text, size, bold, dy)
            left, right = max(left, -a0), max(right, a1)
            down, up = max(down, -b0), max(up, b1)
        return (left, right, down, up)

    def fitted_lines(i):
        # The box should be the picture and the stats under it: a long name ("Kristaps Porzingis") mustn't make it
        # wider than those, or teammates can't stand next to each other. Such a name becomes "K. Porzingis", and
        # only if that is still too wide does its type get (a little) smaller.
        name = receiver_names[i]
        lines = _receiver_lines(name, receiver_values[i], receiver_makes[i], receiver_extra_stats[i])
        hw, _ = picture_half(receiver_image_urls[i], R_ZOOM, R_CIRCLE)
        body = max([2 * hw] + [text_extent(t, sz, b, dy)[1] * 2 for dy, t, _c, sz, b in lines[1:]])

        def width(text, size):
            a0, a1, _b0, _b1 = text_extent(text, size, True, lines[0][0])
            return a1 - a0

        dy, _t, color, size, bold = lines[0]
        parts = name.split()
        short = f"{parts[0][0]}. {' '.join(parts[1:])}" if len(parts) > 1 and parts[0][:1].isalpha() else name
        for text in (name, short):
            if width(text, size) <= body + 4:
                lines[0] = (dy, text, color, size, bold)
                return lines
        w = width(short, size)
        lines[0] = (dy, short, color, max(5.8, round(size * (body + 4) / w, 1)), bold)
        return lines

    receiver_lines = [fitted_lines(i) for i in range(n)]
    extents = [block_extents(receiver_image_urls[i], R_ZOOM, R_CIRCLE, receiver_lines[i]) for i in range(n)]
    pl, pr, pd_, pu = block_extents(passer_image_url, P_ZOOM, P_CIRCLE, [(43, passer_name, "white", 9, True)])
    passer_box = (passer_pos[0] - pl, passer_pos[0] + pr, passer_pos[1] - pd_, passer_pos[1] + pu)

    # ------------------------------------------------------------ each receiver's true spot
    zones, targets = [], []
    for i in range(n):
        spot = receiver_positions[i]
        zone, xy = None, None
        if isinstance(spot, dict):
            zone, xy = spot.get("zone"), spot.get("xy")
        elif isinstance(spot, str):
            zone = spot
        elif isinstance(spot, (tuple, list)) and len(spot) == 2 and all(isinstance(v, (int, float)) for v in spot):
            xy = (float(spot[0]), float(spot[1]))
            zone = court_zone_key_from_xy(*xy)
        if zone not in _PASS_ANCHORS:
            zone = court_zone_key_from_xy(*xy) if xy is not None else _PASS_FALLBACK_CYCLE[i % len(_PASS_FALLBACK_CYCLE)]
        zone = {"lmid": "lmid_wing", "rmid": "rmid_wing"}.get(zone, zone)
        zones.append(zone)
        targets.append(_target_in_zone(zone, xy))

    order = sorted(range(n), key=lambda i: -float(receiver_values[i] or 0))   # biggest connection gets his spot first
    (x_lo, x_hi), (y_lo, y_hi) = ax.get_xlim(), ax.get_ylim()
    final_positions, grew = _pack_player_boxes(targets, zones, extents, [passer_box], (x_lo, x_hi, y_lo, y_hi), order)

    # ------------------------------------------------------------ draw
    def draw_player(pos, name, image_url, image_zoom, circle_size, is_passer=False):
        img = _fetch_image(image_url) if image_url else None
        if img is not None:
            imagebox = OffsetImage(np.array(img), zoom=image_zoom)
            ax.add_artist(AnnotationBbox(imagebox, pos, frameon=False, box_alignment=(0.5, 0.5), zorder=4))
        else:
            ax.scatter([pos[0]], [pos[1]], s=circle_size, color=team_color if is_passer else "#1a1a1a",
                       edgecolor="white" if is_passer else team_color, linewidth=2 if is_passer else 1.5, zorder=4)
            last_name = name.split()[-1] if " " in name else name
            ax.text(pos[0], pos[1], last_name, color="#0d0d0d" if is_passer else "white", fontsize=8 if is_passer else 7,
                    ha="center", va="center", zorder=5, fontweight="bold")

    for i in range(n):
        pos = final_positions[i]
        lw = 1.2 + 6 * (receiver_values[i] / max_val) if max_val else 1.2
        ax.plot([passer_pos[0], pos[0]], [passer_pos[1], pos[1]], color=team_color, linewidth=lw, alpha=0.6, zorder=1)
        draw_player(pos, receiver_names[i], receiver_image_urls[i], R_ZOOM, R_CIRCLE)
        for dy, text, color, size, bold in receiver_lines[i]:
            ax.text(pos[0], pos[1] - dy, text, color=color, fontsize=size, ha="center", va="center", zorder=5,
                    fontweight="bold" if bold else "normal")

    draw_player(passer_pos, passer_name, passer_image_url, P_ZOOM, P_CIRCLE, is_passer=True)
    ax.text(passer_pos[0], passer_pos[1] - 43, passer_name, color="white", fontsize=9, ha="center", va="center",
            zorder=5, fontweight="bold")

    if grew and final_positions:
        # Someone could only fit past the edge of the half court: show that much more floor, and grow the picture by
        # the same amount so every player keeps exactly the size he was measured at.
        boxes = [(p[0] - extents[i][0], p[0] + extents[i][1], p[1] - extents[i][2], p[1] + extents[i][3])
                 for i, p in final_positions.items()]
        nx0, nx1 = min([x_lo] + [b[0] - 4 for b in boxes]), max([x_hi] + [b[1] + 4 for b in boxes])
        ny0, ny1 = min([y_lo] + [b[2] - 4 for b in boxes]), max([y_hi] + [b[3] + 4 for b in boxes])
        w_in, h_in = fig.get_size_inches()
        fig.set_size_inches(w_in * (nx1 - nx0) / (x_hi - x_lo), h_in * (ny1 - ny0) / (y_hi - y_lo))
        ax.set_xlim(nx0, nx1)
        ax.set_ylim(ny0, ny1)
        fig.tight_layout()
    if return_hotspot_data:
        return fig, passer_pos, final_positions
    return fig


# ---------------------------------------------------------------- AI Search: comparison bars + multi-line trends

def _series_palette(main_color, n):
    """The chosen colour first, then clearly different companions for the other subjects."""
    base = [main_color, "#B5B5B5", "#D4AF37", "#5AA9E6", "#E07A5F", "#81B29A", "#C77DFF", "#F2CC8F"]
    out = []
    for c in base:
        if len(out) == n:
            break
        if c.lower() not in [o.lower() for o in out]:
            out.append(c)
    while len(out) < n:
        out.append("#888888")
    return out


def build_comparison_bars(names, stat_labels, values, main_color, is_pct_flags=None, title=None,
                          width=9, height=6.5, return_hotspot_data=False):
    """
    Several players (or teams) side by side on several stats: one group of bars per stat, one bar per subject, each
    labelled with its real value. Stats live on different scales (points vs. steals vs. TS%), so within each group the
    bars are drawn relative to that group's best value -- the tallest bar in every group is the leader on that stat.

    values: values[i][j] = subject i's value on stat j (None if missing).
    Returns fig (and, with return_hotspot_data, the drawn bars: [{"x0","x1","y0","y1","name","stat","value","pct"}]).
    """
    n, m = len(names), len(stat_labels)
    is_pct_flags = is_pct_flags or [False] * m
    colors = _series_palette(main_color, n)
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    group_w = 0.8
    bar_w = group_w / max(1, n)
    records = []
    for j in range(m):
        col = [values[i][j] for i in range(n)]
        present = [abs(float(v)) for v in col if v is not None and not (isinstance(v, float) and np.isnan(v))]
        top = max(present) if present else 1.0
        top = top or 1.0
        for i in range(n):
            v = col[i]
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            h = abs(float(v)) / top
            x0 = j - group_w / 2 + i * bar_w
            ax.bar(x0 + bar_w / 2, h, width=bar_w * 0.92, color=colors[i], edgecolor="white", linewidth=0.4, zorder=2)
            label = f"{float(v):.1%}" if is_pct_flags[j] else (f"{float(v):,.1f}" if abs(float(v)) < 1000 else f"{float(v):,.0f}")
            ax.text(x0 + bar_w / 2, h + 0.02, label, ha="center", va="bottom", color="white",
                    fontsize=8 if n > 3 else 9, fontweight="bold", zorder=3)
            records.append({"x0": x0 + bar_w * 0.04, "x1": x0 + bar_w * 0.96, "y0": 0, "y1": max(h, 0.02),
                            "name": names[i], "stat": stat_labels[j], "value": float(v), "pct": bool(is_pct_flags[j])})
    ax.set_xticks(range(m))
    ax.set_xticklabels(stat_labels, color="white", fontsize=10, fontweight="bold")
    ax.set_yticks([])
    ax.set_ylim(0, 1.18)
    ax.set_xlim(-0.6, m - 0.4)
    for spine in ax.spines.values():
        spine.set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colors]
    ax.legend(handles, names, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=min(n, 4), frameon=False,
              labelcolor="white", fontsize=10)
    if title:
        ax.set_title(title, color="white", fontsize=12, fontweight="bold", pad=12)
    fig.tight_layout()
    if return_hotspot_data:
        return fig, records
    return fig


def build_multi_line_chart(x_labels, series, stat_label, main_color, is_percentage=False, title=None,
                           width=9, height=6.5, return_hotspot_data=False):
    """
    One stat over time for one or more players/teams (a career by season, or a season game by game): one line each,
    a gap wherever a subject has no value. series: [(name, [value or None per x_label]), ...].
    Returns fig (and, with return_hotspot_data, every drawn point: [{"x","y","name","label"}]).
    """
    colors = _series_palette(main_color, len(series))
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    points = []
    xs = list(range(len(x_labels)))
    for (name, vals), color in zip(series, colors):
        y = [float(v) if v is not None and not (isinstance(v, float) and np.isnan(v)) else np.nan for v in vals]
        ax.plot(xs, y, color=color, linewidth=2.2, marker="o", markersize=5, label=name, zorder=3)
        for x, v, lab in zip(xs, y, x_labels):
            if not np.isnan(v):
                points.append({"x": x, "y": v, "name": name, "label": str(lab)})
    step = max(1, len(x_labels) // 15)
    ax.set_xticks(xs[::step])
    ax.set_xticklabels([str(x_labels[i]) for i in range(0, len(x_labels), step)], color="white", fontsize=8,
                       rotation=45 if len(x_labels) > 6 else 0, ha="right" if len(x_labels) > 6 else "center")
    if is_percentage:
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_ylabel(stat_label, color="white", fontsize=11, fontweight="bold")
    ax.tick_params(colors="white")
    ax.grid(axis="y", color="#ffffff", alpha=0.08)
    for spine in ax.spines.values():
        spine.set_visible(False)
    if len(series) > 1:
        ax.legend(facecolor="#1a1a1a", edgecolor="#555555", labelcolor="white", fontsize=9)
    if title:
        ax.set_title(title, color="white", fontsize=12, fontweight="bold", pad=12)
    fig.tight_layout()
    if return_hotspot_data:
        return fig, points
    return fig
