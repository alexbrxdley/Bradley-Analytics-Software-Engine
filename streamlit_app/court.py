"""
court.py
--------
Draws an NBA half court on a matplotlib Axes using nba_api shot
coordinates. This is a direct port of r/functions/court.r so the
Streamlit visualizations match the original R-rendered charts.
"""

from matplotlib.patches import Arc, Rectangle


def draw_court(ax, color="white", lw=1.1):
    """Draw the half-court lines used behind shot charts / heat maps."""

    # Hoop
    hoop = Arc((0, 0), 15, 15, theta1=0, theta2=360, linewidth=lw, color=color)

    # Backboard
    backboard = ax.plot([-30, 30], [-7.5, -7.5], color=color, linewidth=lw)

    # Paint (outline only)
    paint = ax.add_patch(
        Rectangle((-80, -47.5), 160, 190, linewidth=lw, edgecolor=color, facecolor="none")
    )

    # Free throw circle: solid top half, dashed bottom half
    ft_top = Arc((0, 142.5), 120, 120, theta1=0, theta2=180, linewidth=lw, color=color)
    ft_bottom = Arc(
        (0, 142.5), 120, 120, theta1=180, theta2=360,
        linewidth=lw, color=color, linestyle="dashed"
    )

    # Restricted area
    restricted = Arc((0, 0), 80, 80, theta1=0, theta2=180, linewidth=lw, color=color)

    # Corner three lines
    corner_left = ax.plot([-220, -220], [-47.5, 92.5], color=color, linewidth=lw)
    corner_right = ax.plot([220, 220], [-47.5, 92.5], color=color, linewidth=lw)

    # Three point arc
    three_arc = Arc(
        (0, 0), 475, 475, theta1=22, theta2=158, linewidth=lw, color=color
    )

    for patch in (hoop, ft_top, ft_bottom, restricted, three_arc):
        ax.add_patch(patch)

    return ax


def apply_court_limits(ax):
    """Match the coordinate limits used in the R visualizations."""
    ax.set_xlim(-250, 250)
    ax.set_ylim(-60, 356.7)
    ax.set_aspect("equal")
    ax.axis("off")
