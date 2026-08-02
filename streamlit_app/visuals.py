"""
visuals.py
----------
Builds the Shot Chart and Heat Map figures. Ported from r/shot_chart.r
and r/heat_map.r (which used ggplot2) into matplotlib so everything
can run inside Streamlit Community Cloud without an R runtime.
"""

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, to_rgb

from court import apply_court_limits, draw_court

MISS_COLOR = "#9A9A9A"


def _new_fig(figsize=(6, 5.2)):
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)
    return fig, ax


def build_shot_chart(shots, team_color: str):
    """Plot made/missed shots on a half court, made shots in team color."""
    fig, ax = _new_fig()

    made = shots[shots["SHOT_MADE_FLAG"] == 1]
    missed = shots[shots["SHOT_MADE_FLAG"] == 0]

    ax.scatter(missed["LOC_X"], missed["LOC_Y"], color=MISS_COLOR, alpha=0.75, s=14)
    ax.scatter(made["LOC_X"], made["LOC_Y"], color=team_color, alpha=1.0, s=14)

    draw_court(ax, color="white")
    apply_court_limits(ax)

    fig.tight_layout(pad=0.3)
    return fig


def _lighten_color(hex_color: str, amount: float = 0.15) -> str:
    """Blend a hex color toward white, matching R's lighten_color()."""
    r, g, b = to_rgb(hex_color)
    r = r + (1 - r) * amount
    g = g + (1 - g) * amount
    b = b + (1 - b) * amount
    return (r, g, b)


def build_heat_map(shots, team_color: str):
    """Plot a 2D shot-density heat map, shaded from light to team color."""
    fig, ax = _new_fig()

    cmap = LinearSegmentedColormap.from_list(
        "team_density", [_lighten_color(team_color), team_color]
    )

    x = shots["LOC_X"].to_numpy()
    y = shots["LOC_Y"].to_numpy()

    ax.hexbin(
        x, y,
        gridsize=45,
        cmap=cmap,
        mincnt=1,
        extent=(-250, 250, -60, 356.7),
        linewidths=0,
    )

    draw_court(ax, color="white")
    apply_court_limits(ax)

    fig.tight_layout(pad=0.3)
    return fig


VISUALIZATION_BUILDERS = {
    "Shot Chart": build_shot_chart,
    "Heat Map": build_heat_map,
}
