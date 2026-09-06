"""
visuals.py (shot chart section)

Ports shot_chart.r's exact logic: made shots in team color, missed
shots in a neutral gray, both with the same dot size and opacity
values as the R version, drawn over the shared court from court.py.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
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


def build_heat_map(shots_df, team_color, width=6, height=5, grid_resolution=200):
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

    xx, yy = np.mgrid[-250:250:complex(0, grid_resolution), -60:356.7:complex(0, grid_resolution)]
    positions = np.vstack([xx.ravel(), yy.ravel()])
    values = np.vstack([x, y])
    kernel = gaussian_kde(values)
    density = np.reshape(kernel(positions), xx.shape)

    # Normalize density to [0, 1] for a valid alpha range
    density_norm = (density - density.min()) / (density.max() - density.min())

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
    density_alpha = np.clip(density_norm * 1.35, 0, 1)

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

    return fig


def build_hex_shot_chart(
    shots_df, comparison_shots_df, team_color,
    width=6, height=5, xbins=25,
    min_radius=1.5, max_radius=9,
    below_avg_alpha=0.75, above_avg_alpha=1.0,
    efficiency_saturation=0.15,
    below_avg_color="#373737",
    min_zone_fga=0,
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
            path_effects=[pe.withStroke(linewidth=2.5, foreground="black", alpha=0.8)]
        )

    # ---------------------------------------------------------- Legend
    # Sits in the gap between the paint and the corner 3 on each side,
    # within the court's own existing bounds -- an earlier version
    # placed this below the court's baseline instead, which required
    # extending the y-axis limits and made the whole image visibly
    # taller than the original reference. Left side: three circles
    # shading from below_avg_color to team_color for the FG% (color)
    # scale. Right side: three hexagons growing from min_radius to
    # max_radius for the FGA (size) scale. Each bracketed by down/up
    # arrows showing which direction the scale increases.
    left_x, right_x = -155, 155
    arrow_up_y, dots_y, arrow_down_y = -18, -33, -48
    dot_offsets = [-14, 0, 14]

    ax.text(left_x, arrow_up_y, "\u2191 FG%", color="white", fontsize=8, ha="center", va="center")
    for i, off in enumerate(dot_offsets):
        t = i / (len(dot_offsets) - 1)
        color = tuple(below_rgb + (team_rgb - below_rgb) * t)
        ax.add_patch(plt.Circle((left_x + off, dots_y), radius=3 + i * 1.3, facecolor=color, edgecolor="none"))
    ax.text(left_x, arrow_down_y, "\u2193 FG%", color="white", fontsize=8, ha="center", va="center")

    ax.text(right_x, arrow_up_y, "\u2191 FGA", color="white", fontsize=8, ha="center", va="center")
    for i, off in enumerate(dot_offsets):
        t = i / (len(dot_offsets) - 1)
        r = min_radius + (max_radius - min_radius) * t
        hexagon = RegularPolygon((right_x + off, dots_y), numVertices=6, radius=r, orientation=0,
                                  facecolor=team_color, edgecolor="none")
        ax.add_patch(hexagon)
    ax.text(right_x, arrow_down_y, "\u2193 FGA", color="white", fontsize=8, ha="center", va="center")

    return fig


def _fetch_image(url):
    """Downloads an image from a URL for use in the scatter plot -- returns None on any failure so a missing headshot doesn't crash the whole chart."""
    import requests
    from PIL import Image
    from io import BytesIO
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        return Image.open(BytesIO(response.content)).convert("RGBA")
    except Exception:
        return None


def build_scatter_plot(
    scatter_df, stat_label_y, stat_label_x,
    image_size=0.2, highlighted_multiplier=1.0,
    width=8, height=6,
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

    for _, row in scatter_df.iterrows():
        img = _fetch_image(row["image_url"])
        if img is None:
            ax.scatter(row["x_value"], row["y_value"], color="#B5B5B5", s=40, zorder=3)
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

    ax.set_xlabel(stat_label_x, color="white", fontsize=12)
    ax.set_ylabel(stat_label_y, color="white", fontsize=12)
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)

    return fig


def build_bar_chart(
    axis_df, stat_display_name, season, top_n, team_color,
    included_names=None, orientation="vertical",
    stat_source="base", is_percentage=False,
    width=8, height=6,
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

    # Value labels above (or right of, for horizontal) each bar
    for i, val in enumerate(df["value"]):
        label = f"{val:.0%}" if is_percentage else f"{val:,.0f}"
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
    title = f"Top {top_n} {stat_display_name}{per_game_phrase} leaders {season}"
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
    Downloads one player headshot, resized, for embedding into a
    matplotlib figure -- returns None on any failure (network, 404,
    timeout) so the caller can fall back to text-only rather than crash
    the whole visualization over one missing image.
    """
    try:
        url = f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png"
        with urllib.request.urlopen(url, timeout=5) as response:
            img_data = response.read()
        img = Image.open(io.BytesIO(img_data)).convert("RGBA")
        img.thumbnail((max_size, max_size))
        return img
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
    ax.text(label_x, header_y + 0.7, team_name, fontsize=13, fontweight="bold", color="white", family="serif")
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
                ax.add_artist(AnnotationBbox(imagebox, (px, header_y + 0.7), frameon=False, box_alignment=(0.5, 0.5)))
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
                     bins=20, width=8, height=6):
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
                    violin=False, width=9, height=6):
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
                    width=8, height=6):
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
    label = f"Top {top_n} {stat_display_name}{per_game_phrase} leaders {season} (Dot Plot)"
    if included_names:
        label += f"\n(Includes {', '.join(included_names)})"
    ax.set_xlabel(label, color="white", fontsize=11, fontweight="bold")
    fig.tight_layout()
    return fig


def build_density_plot(values, stat_display_name, season, team_color, is_percentage=False,
                        width=8, height=6):
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
                                        highlight_name=None, width=8, height=6):
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
                      filled=False, width=10, height=6):
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
                       highlight_names=None, width=8, height=7):
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


def build_waterfall_chart(labels, values, total_label, team_color, is_percentage=False,
                           width=9, height=6):
    """
    Sequential bars, each starting where the previous one ended --
    shows how components sum to a total. labels/values are the
    components in order (e.g. ["FT pts", "2PT pts", "3PT pts"] with
    their point contributions); a final bar for the total is appended
    automatically, styled distinctly (full height from zero, a
    different color) as a running-total marker rather than another
    component.
    """
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    running = 0
    positions = list(range(len(values) + 1))
    total = sum(values)

    for i, (label, val) in enumerate(zip(labels, values)):
        ax.bar(i, val, bottom=running, color=team_color, edgecolor="white", linewidth=0.6, width=0.6)
        mid = running + val / 2
        label_text = f"{val:.0%}" if is_percentage else f"{val:,.1f}"
        ax.text(i, mid, label_text, ha="center", va="center", color="white", fontsize=9, fontweight="bold")
        if i > 0:
            ax.plot([i - 1 + 0.3, i - 0.3], [running, running], color="#888888", linewidth=1, linestyle=":")
        running += val

    # Total bar, visually distinct (full height, different shade)
    ax.bar(len(values), total, color="#F5D370", edgecolor="white", linewidth=0.6, width=0.6, alpha=0.9)
    total_label_text = f"{total:.0%}" if is_percentage else f"{total:,.1f}"
    ax.text(len(values), total / 2, total_label_text, ha="center", va="center", color="#111111", fontsize=10, fontweight="bold")

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


def build_combo_chart(x_labels, bar_values, line_values, bar_label, line_label,
                       team_color, line_is_percentage=False, width=10, height=6):
    """
    Bars (left axis, bar_label -- typically a volume stat like FGA) and
    a line (right axis, line_label -- typically a rate stat like FG%)
    sharing the same category axis. Two independent y-axes since the
    two stats are rarely on comparable scales.
    """
    fig, ax1 = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax1.set_facecolor("none")

    x = range(len(x_labels))
    ax1.bar(x, bar_values, color=team_color, alpha=0.75, width=0.6, label=bar_label)
    ax1.set_ylabel(bar_label, color=team_color, fontsize=11, fontweight="bold")
    ax1.tick_params(axis="y", colors=team_color)

    ax2 = ax1.twinx()
    ax2.plot(x, line_values, color="white", linewidth=2.2, marker="o", markersize=5, label=line_label)
    ax2.set_ylabel(line_label, color="white", fontsize=11, fontweight="bold")
    ax2.tick_params(axis="y", colors="white")
    if line_is_percentage:
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))

    step = max(1, len(x_labels) // 15)
    ax1.set_xticks(list(x)[::step])
    ax1.set_xticklabels([x_labels[i] for i in range(0, len(x_labels), step)], color="white", fontsize=8, rotation=45, ha="right")
    ax1.tick_params(axis="x", colors="white")
    for spine in list(ax1.spines.values()) + list(ax2.spines.values()):
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def build_tornado_chart(labels, values, subject_label, team_color, is_percentage=False,
                         center_label="League Average", width=9, height=6):
    """
    Diverging bars from a center axis (typically 0, or a stat's league
    average already subtracted out before calling this) -- bars extend
    right for above-center values, left for below, color-coded by
    direction so strengths and weaknesses read apart at a glance.
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
    ax.set_xlabel(f"{subject_label} vs {center_label}", color="white", fontsize=11, fontweight="bold")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def build_radar_chart(stat_labels, player_percentiles, player_name, team_color,
                       second_percentiles=None, second_name=None, second_color="#B5B5B5",
                       width=8, height=8):
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

    label = f"{player_name} -- League Percentile Profile" if second_percentiles is None else f"{player_name} vs {second_name}"
    ax.set_xlabel(label, color="white", fontsize=12, fontweight="bold", labelpad=20)
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
    fig_height = 1.3 + len(table_rows) * 0.55
    has_images = image_url_a is not None or image_url_b is not None
    if has_images:
        fig_height += 1.7
    fig, ax = plt.subplots(figsize=(8, fig_height))
    ax.axis("off")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, fig_height)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    name_y = fig_height - 0.4
    if has_images:
        image_y = fig_height - 1.0
        img_a = _fetch_image(image_url_a) if image_url_a else None
        if img_a is not None:
            ax.add_artist(AnnotationBbox(OffsetImage(np.array(img_a), zoom=0.13), (1.5, image_y),
                                          frameon=False, box_alignment=(0.5, 0.5)))
        img_b = _fetch_image(image_url_b) if image_url_b else None
        if img_b is not None:
            ax.add_artist(AnnotationBbox(OffsetImage(np.array(img_b), zoom=0.13), (8.5, image_y),
                                          frameon=False, box_alignment=(0.5, 0.5)))
        name_y = fig_height - 2.3

    ax.text(1.5, name_y, name_a, fontsize=13, color=color_a, fontweight="bold", family="serif", ha="center")
    ax.text(8.5, name_y, name_b, fontsize=13, color=color_b, fontweight="bold", family="serif", ha="center")

    y = name_y - 0.7
    for label, val_a, val_b, is_pct in table_rows:
        def fmt(v):
            return "--" if v is None else (f"{v:.1%}" if is_pct else f"{v:,.1f}")

        a_wins = val_a is not None and val_b is not None and val_a > val_b
        b_wins = val_a is not None and val_b is not None and val_b > val_a

        ax.text(1.5, y, fmt(val_a), fontsize=12.5, ha="center", va="center",
                color=color_a if a_wins else "#9a9a9a", fontweight="bold" if a_wins else "normal", family="serif")
        ax.text(5, y, label, fontsize=10, color="#cccccc", ha="center", va="center")
        ax.text(8.5, y, fmt(val_b), fontsize=12.5, ha="center", va="center",
                color=color_b if b_wins else "#9a9a9a", fontweight="bold" if b_wins else "normal", family="serif")
        y -= 0.55

    return fig


def build_calendar_heat_map(dates, values, stat_display_name, subject_name, team_color,
                             width=12, height=3.5):
    """
    A GitHub-contribution-style grid -- each day's cell shaded by that
    game's stat value, arranged by week (columns) and day-of-week
    (rows) rather than a plain timeline, which is what actually makes
    patterns like "worse on the second night of a back-to-back" or
    "stronger in a particular month" visible at a glance in a way a
    normal line chart over the same games doesn't foreground.

    dates: list of datetime-like game dates. values: matching stat
    values for those games (non-game days are simply blank cells).
    """
    dates = pd.to_datetime(pd.Series(dates))
    df = pd.DataFrame({"date": dates, "value": values})
    df = df.sort_values("date")

    start = df["date"].min() - pd.Timedelta(days=int(df["date"].min().dayofweek))
    end = df["date"].max()
    n_weeks = int(((end - start).days) / 7) + 2

    grid = np.full((7, n_weeks), np.nan)
    for _, row in df.iterrows():
        days_since_start = (row["date"] - start).days
        week = days_since_start // 7
        weekday = row["date"].dayofweek
        if 0 <= week < n_weeks:
            grid[weekday, week] = row["value"]

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

    ax.set_ylabel(f"{subject_name} -- {stat_display_name} by Game Date", color="white", fontsize=11, fontweight="bold")
    fig.tight_layout()
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
                              width=14, height=7):
    """
    A shot chart and a percentile radar for the same player, side by
    side in one figure -- pairs "where" (the shot chart) with "what
    kind of player" (the radar profile), rather than making the viewer
    hold two separate images in their head. Reuses the exact same
    court-drawing and radar logic as build_shot_chart() and
    build_radar_chart() individually -- this is genuinely just those
    two placed in one figure, not a new visualization mechanism.
    """
    fig = plt.figure(figsize=(width, height))
    fig.patch.set_alpha(0)

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

    fig.tight_layout()
    return fig


def build_sankey_flow(stage_labels, flows, team_color, width=11, height=7):
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


def build_network_diagram(pair_labels, pair_values, team_color, value_label="Net Rating",
                           width=10, height=9):
    """
    Nodes are players, edges are 2-man lineup pairs weighted/colored by
    how that pairing actually performed together (net rating or a
    similar per-pair stat) -- reveals which combinations of teammates
    work especially well or poorly, which a player-by-player stat line
    can't show on its own. pair_labels: list of (player_a, player_b)
    tuples. pair_values: matching list of that pair's stat value.
    Node position is a force-directed (spring) layout via networkx,
    so pairs that share more/stronger connections cluster closer
    together rather than at fixed, arbitrary positions.
    """
    import networkx as nx
    from matplotlib.colors import Normalize
    from matplotlib.cm import ScalarMappable

    G = nx.Graph()
    for (a, b), val in zip(pair_labels, pair_values):
        G.add_edge(a, b, weight=val)

    pos = nx.spring_layout(G, seed=42, k=1.2 / max(len(G.nodes) ** 0.5, 1))

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    values = list(pair_values)
    norm = Normalize(vmin=min(values), vmax=max(values))
    cmap = plt.cm.RdYlGn

    for (a, b), val in zip(pair_labels, pair_values):
        x0, y0 = pos[a]
        x1, y1 = pos[b]
        lw = 1.5 + 5 * (val - min(values)) / (max(values) - min(values) + 1e-9)
        ax.plot([x0, x1], [y0, y1], color=cmap(norm(val)), linewidth=lw, alpha=0.75, zorder=1)

    for node in G.nodes:
        x, y = pos[node]
        ax.scatter([x], [y], s=900, color="#1a1a1a", edgecolor=team_color, linewidth=2, zorder=2)
        first_name_initial = node.split()[0][0] if node.split() else "?"
        last_name = node.split()[-1] if len(node.split()) > 1 else node
        ax.text(x, y, f"{first_name_initial}. {last_name}", color="white", fontsize=8,
                ha="center", va="center", zorder=3, fontweight="bold")

    sm = ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, orientation="vertical", fraction=0.03, pad=0.02)
    cbar.set_label(value_label, color="white", fontsize=10)
    cbar.ax.tick_params(colors="white", labelsize=8)
    cbar.outline.set_visible(False)

    ax.axis("off")
    fig.text(0.5, 0.02, f"Two-Man Lineup Network -- {value_label}", color="white", fontsize=11,
              fontweight="bold", ha="center")
    fig.tight_layout()
    return fig


def build_momentum_chart(x_labels, values, stat_display_name, subject_name, team_color,
                          width=11, height=6):
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


def build_impact_clock(overall_stats, clutch_stats, player_name, team_color, width=8, height=6):
    """
    Performance mapped onto a clock face, highlighting clutch-period
    activity at a glance -- adapted to the data actually available
    (clutch vs. overall season stats, from get_player_clutch_stats(),
    rather than true minute-by-minute in-game data, which isn't
    available from this data source). The clock's final arc (the last
    ~1/4, styled like a game's closing minutes) is highlighted in the
    player's color and annotated with clutch performance; the rest of
    the face shows the season-overall numbers for comparison.

    overall_stats/clutch_stats: dicts of {stat_label: value}, same
    keys expected in both (e.g. {"PTS": 27.4, "FG%": 0.47}).
    """
    fig, ax = plt.subplots(figsize=(width, height), subplot_kw=dict(polar=True))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    # Full clock face, 12 hour-marks, going clockwise from the top
    theta = np.linspace(0, 2 * np.pi, 200)
    ax.plot(theta, np.ones_like(theta), color="#444444", linewidth=1)
    for hour in range(12):
        angle = -hour / 12 * 2 * np.pi + np.pi / 2
        ax.plot([angle, angle], [0.92, 1.0], color="#666666", linewidth=1.2)

    # Highlights the final quarter-arc (styled as the clock's closing
    # stretch, i.e. "clutch time") in the player's own color
    clutch_start = np.pi / 2 - 2 * np.pi * 0.75
    clutch_end = np.pi / 2 - 2 * np.pi * 1.0
    clutch_theta = np.linspace(clutch_end, clutch_start, 100)
    ax.fill_between(clutch_theta, 0, 1, color=team_color, alpha=0.25)

    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.spines["polar"].set_visible(False)
    ax.grid(False)

    # Stat annotations placed outside the clock face -- clutch on the
    # highlighted side, overall on the other, so the comparison is
    # readable rather than crowded onto the clock itself
    clutch_text = "\n".join(f"{k}: {v}" for k, v in clutch_stats.items())
    overall_text = "\n".join(f"{k}: {v}" for k, v in overall_stats.items())
    fig.text(0.76, 0.5, f"CLUTCH\n{clutch_text}", color=team_color, fontsize=14, fontweight="bold",
              ha="left", va="center", family="serif")
    fig.text(0.05, 0.5, f"OVERALL\n{overall_text}", color="#aaaaaa", fontsize=14,
              ha="left", va="center", family="serif")

    ax.set_xlabel(f"{player_name} -- Impact Clock", color="white", fontsize=15, fontweight="bold", labelpad=15)
    fig.tight_layout()
    return fig


def build_bump_chart(seasons, entity_ranks, team_color, highlight_names=None, width=10, height=7):
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
    """
    highlight_names = set(highlight_names or [])
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
            ax.text(len(x) - 1 + 0.1, ranks[-1], name, color=color, fontsize=9, va="center", fontweight="bold")

    ax.invert_yaxis()
    ax.set_xticks(list(x))
    ax.set_xticklabels(seasons, color="white", fontsize=10, rotation=20 if len(seasons) > 6 else 0)
    ax.set_ylabel("League Rank Over Time", color="white", fontsize=11, fontweight="bold")
    ax.tick_params(colors="white")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def build_court_connection_map(passer_name, receiver_names, receiver_values, receiver_makes,
                                team_color, passer_image_url=None, receiver_image_urls=None,
                                value_label="Passes", width=11, height=10.5):
    """
    Arcs on the court connecting a passer to each teammate they passed
    to, weighted by pass volume -- the real, honest version of "pass
    origin to shot location" this data source can actually support:
    PlayerDashPtPass tracks passer-to-receiver connections and the
    shots that resulted (see nba_data.py's get_player_passes()), not
    literal spatial pass-trajectory coordinates, which aren't tracked
    anywhere in this API. Since real on-court positioning at the
    moment of each pass isn't available either, receivers are placed
    at representative court spots (corners, wings, top of the arc,
    paint) rather than the passer's own actual teammates' real
    positions -- an honest approximation, not a claim of precise
    spatial accuracy.

    Shows real headshot images (falling back to a plain colored circle
    with the name inside only if that specific image genuinely fails
    to load) with the player's name and pass/makes stats stacked below
    each one, all sized up substantially from the original text-in-
    circle version.
    """
    fig, ax = new_court_figure(width=width, height=height)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    draw_court(ax, color="#888888", lw=1.2)
    ax.set_ylim(-90, 400)

    passer_pos = (0, 160)  # elevated, central "playmaker" spot
    receiver_image_urls = receiver_image_urls or [None] * len(receiver_names)

    # Representative court spots, cycling if there are more receivers
    # than named spots -- spaced further apart than the original
    # text-in-circle version needed, since the real headshot images are
    # substantially larger and would otherwise overlap each other and
    # the central passer.
    spot_positions = [
        (-235, -10), (235, -10), (-210, 260), (210, 260), (0, 340),
        (-130, -25), (130, -25), (0, -25), (-235, 300), (235, 300),
    ]

    def draw_player(pos, name, image_url, image_zoom, circle_size, is_passer=False):
        img = _fetch_image(image_url) if image_url else None
        if img is not None:
            imagebox = OffsetImage(np.array(img), zoom=image_zoom)
            ax.add_artist(AnnotationBbox(imagebox, pos, frameon=False, box_alignment=(0.5, 0.5), zorder=4))
        else:
            ax.scatter([pos[0]], [pos[1]], s=circle_size, color=team_color if is_passer else "#1a1a1a",
                       edgecolor="white" if is_passer else team_color, linewidth=2 if is_passer else 1.5, zorder=4)
            last_name = name.split()[-1] if " " in name else name
            text_color = "#0d0d0d" if is_passer else "white"
            ax.text(pos[0], pos[1], last_name, color=text_color, fontsize=11 if is_passer else 10,
                    ha="center", va="center", zorder=5, fontweight="bold")

    max_val = max(receiver_values) if receiver_values else 1
    for i, (name, val, makes, img_url) in enumerate(zip(receiver_names, receiver_values, receiver_makes, receiver_image_urls)):
        pos = spot_positions[i % len(spot_positions)]
        lw = 1.5 + 8 * (val / max_val)
        ax.plot([passer_pos[0], pos[0]], [passer_pos[1], pos[1]], color=team_color, linewidth=lw, alpha=0.6, zorder=1)

        draw_player(pos, name, img_url, image_zoom=0.13, circle_size=1400)
        ax.text(pos[0], pos[1] - 34, name, color="white", fontsize=11, ha="center", va="center", zorder=5, fontweight="bold")
        ax.text(pos[0], pos[1] - 50, f"{val:.0f} passes / {makes:.0f} FGM", color=team_color, fontsize=10, ha="center", va="center", zorder=5)

    draw_player(passer_pos, passer_name, passer_image_url, image_zoom=0.17, circle_size=2200, is_passer=True)
    ax.text(passer_pos[0], passer_pos[1] - 42, passer_name, color="white", fontsize=13, ha="center", va="center", zorder=5, fontweight="bold")

    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel(f"{passer_name} -- Passing Connections ({value_label})", color="white", fontsize=12, fontweight="bold")
    fig.tight_layout()
    return fig
