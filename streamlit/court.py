"""
court.py

Draws the NBA half court in matplotlib, matching the exact geometry
of r/functions/court.r line for line. Coordinates are in the same
units as NBA API shot chart data (LOC_X / LOC_Y), so shots plot
directly onto this court with no additional scaling.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Arc


def draw_court(ax, color="white", lw=1.2):
    """
    Draws the NBA half court onto the given matplotlib Axes.
    Mirrors court.r's draw_court() exactly:
      - Hoop: circle, radius 7.5, centered at (0, 0)
      - Backboard: horizontal segment at y=-7.5, x from -30 to 30
      - Paint: rectangle, x -80 to 80, y -47.5 to 142.5
      - Free throw circle: radius 60 centered at (0, 142.5),
        solid on the near (bottom) half, dashed on the far half
      - Restricted area: arc, radius 40, centered at (0, 0), 0-180 deg
      - Corner three lines: vertical segments at x=-220 and x=220,
        y from -47.5 to 92.5
      - Three point arc: radius 237.5, centered at (0, 0), 22-158 deg
    """

    # Hoop
    hoop = plt.Circle((0, 0), radius=7.5, linewidth=lw, color=color, fill=False)
    ax.add_patch(hoop)

    # Backboard
    ax.plot([-30, 30], [-7.5, -7.5], color=color, linewidth=lw)

    # Paint (outer rectangle only, matching court.r -- no separate
    # inner/outer box, since court.r only draws one rect)
    paint = Rectangle(
        (-80, -47.5), 160, 190,
        linewidth=lw, edgecolor=color, facecolor="none"
    )
    ax.add_patch(paint)

    # Free throw circle -- solid near half (0-180), dashed far half (180-360)
    ft_circle_near = Arc(
        (0, 142.5), 120, 120, angle=0, theta1=0, theta2=180,
        linewidth=lw, color=color
    )
    ax.add_patch(ft_circle_near)

    ft_circle_far = Arc(
        (0, 142.5), 120, 120, angle=0, theta1=180, theta2=360,
        linewidth=lw, color=color, linestyle="dashed"
    )
    ax.add_patch(ft_circle_far)

    # Restricted area
    restricted = Arc(
        (0, 0), 80, 80, angle=0, theta1=0, theta2=180,
        linewidth=lw, color=color
    )
    ax.add_patch(restricted)

    # Corner three lines
    ax.plot([-220, -220], [-47.5, 92.5], color=color, linewidth=lw)
    ax.plot([220, 220], [-47.5, 92.5], color=color, linewidth=lw)

    # Three point arc
    three_arc = Arc(
        (0, 0), 475, 475, angle=0, theta1=22, theta2=158,
        linewidth=lw, color=color
    )
    ax.add_patch(three_arc)


def new_court_figure(width=6, height=5, xlim=(-250, 250), ylim=(-60, 356.7)):
    """
    Creates a new matplotlib figure/axes sized and limited to match
    shot_chart.r's exact plot bounds (scale_x_continuous limits =
    c(-250, 250), scale_y_continuous limits = c(-60, 356.7)),
    with a fully transparent background matching
    bradley_transparent_theme() in save_plot.r.
    """
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax
