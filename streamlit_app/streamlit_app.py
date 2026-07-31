"""
Bradley Analytics -- Streamlit Dashboard
------------------------------------------
The live, browser-based version of the Bradley Analytics Software Engine.

Lets a visitor pick any active NBA player, a season, and a visualization
type, and generates a fully interactive shot chart or shooting heat map
right in the browser using Plotly -- no install required.

This app is self-contained on purpose: the court geometry and team
colors mirror the R/ggplot2 versions used by the desktop tool, so the
look stays consistent between bradley.bat and this dashboard.
"""

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from nba_api.stats.endpoints import commonplayerinfo, ShotChartDetail
from nba_api.stats.static import players
from scipy.stats import gaussian_kde


st.set_page_config(
    page_title="Bradley Analytics",
    layout="centered",
)


# ---------------------------------------------------------------- Theme
# The dark/light contrast for every native widget (dropdowns, buttons,
# checkboxes, etc.) is handled by Streamlit's own theme system via
# .streamlit/config.toml sitting alongside this project -- that's far
# more reliable than hand-written CSS, since Streamlit manages correct
# text/background contrast internally. The CSS below only adds the
# font and the gradient/grain background flourish on top of that.

NOISE_SVG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E"
    "%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' "
    "baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E"
    "%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E"
)

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Kalnia:wght@600&family=Playfair+Display:wght@400;600&display=swap');

html, body, [class^="st-"], .stMarkdown, h2, h3, h4, p, span, label, button {{
    font-family: 'Playfair Display', serif !important;
}}

/* Main title only -- everything else above uses Playfair Display */
[data-testid="stMarkdownContainer"] h1 {{
    font-family: 'Kalnia', serif !important;
}}

.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
    background: linear-gradient(135deg, #000000 0%, #0d0d0d 35%, #1a1a1a 65%, #000000 100%) !important;
}}

.stApp::before {{
    content: "";
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background-image: url("{NOISE_SVG}");
    opacity: 0.16;
    pointer-events: none;
    z-index: 9999;
    mix-blend-mode: overlay;
}}

header[data-testid="stHeader"] {{
    background: transparent !important;
}}

#MainMenu {{
    visibility: hidden !important;
}}

h1, h2, h3 {{
    font-weight: 600 !important;
    letter-spacing: 0.03em;
}}

hr {{
    border-color: #333333 !important;
}}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# NBA team colors, keyed by full official team name so this can drive
# the team dropdown directly
TEAM_COLORS = {
    "Atlanta Hawks": "#E03A3E",
    "Boston Celtics": "#007A33",
    "Brooklyn Nets": "#000000",
    "Charlotte Hornets": "#1D1160",
    "Chicago Bulls": "#CE1141",
    "Cleveland Cavaliers": "#860038",
    "Dallas Mavericks": "#00538C",
    "Denver Nuggets": "#0E2240",
    "Detroit Pistons": "#C8102E",
    "Golden State Warriors": "#1D428A",
    "Houston Rockets": "#CE1141",
    "Indiana Pacers": "#002D62",
    "LA Clippers": "#C8102E",
    "Los Angeles Lakers": "#552583",
    "Memphis Grizzlies": "#5D76A9",
    "Miami Heat": "#98002E",
    "Milwaukee Bucks": "#00471B",
    "Minnesota Timberwolves": "#0C2340",
    "New Orleans Pelicans": "#0C2340",
    "New York Knicks": "#006BB6",
    "Oklahoma City Thunder": "#007AC1",
    "Orlando Magic": "#0077C0",
    "Philadelphia 76ers": "#006BB6",
    "Phoenix Suns": "#1D1160",
    "Portland Trail Blazers": "#E03A3E",
    "Sacramento Kings": "#5A2D81",
    "San Antonio Spurs": "#C4CED4",
    "Toronto Raptors": "#CE1141",
    "Utah Jazz": "#002B5C",
    "Washington Wizards": "#002B5C",
}


def find_matching_team(team_name: str) -> str:
    """
    Find the closest matching team name in TEAM_COLORS, used to
    pre-select a player's own team in the dropdown. Tries an exact
    match first (what the NBA API's TEAM_NAME field returns), then a
    partial match in case of slight naming differences.
    """
    if team_name in TEAM_COLORS:
        return team_name

    team_lower = team_name.lower().strip()

    for name in TEAM_COLORS:
        if name.lower() in team_lower or team_lower in name.lower():
            return name

    return next(iter(TEAM_COLORS))


def hex_to_rgb(hex_color: str):
    """Convert '#RRGGBB' to an (r, g, b) integer tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------- Court

def arc_points(cx: float, cy: float, radius: float, start_deg: float, end_deg: float, n: int = 100):
    """Generate x, y points along a circular arc, mirroring court.r."""
    angles = np.radians(np.linspace(start_deg, end_deg, n))
    return cx + radius * np.cos(angles), cy + radius * np.sin(angles)


def court_lines():
    """
    Every line that makes up the half court, as (x, y, dash) tuples.
    Coordinates match the NBA API's shot chart units and the same
    dimensions used in r/functions/court.r.
    """
    lines = []

    # Hoop
    x, y = arc_points(0, 0, 7.5, 0, 360)
    lines.append((x, y, "solid"))

    # Backboard
    lines.append(([-30, 30], [-7.5, -7.5], "solid"))

    # Paint
    lines.append((
        [-80, 80, 80, -80, -80],
        [-47.5, -47.5, 142.5, 142.5, -47.5],
        "solid",
    ))

    # Free throw circle (top half, solid)
    x, y = arc_points(0, 142.5, 60, 0, 180)
    lines.append((x, y, "solid"))

    # Free throw circle (bottom half, dashed)
    x, y = arc_points(0, 142.5, 60, 180, 360)
    lines.append((x, y, "dash"))

    # Restricted area
    x, y = arc_points(0, 0, 40, 0, 180)
    lines.append((x, y, "solid"))

    # Corner three lines
    lines.append(([-220, -220], [-47.5, 92.5], "solid"))
    lines.append(([220, 220], [-47.5, 92.5], "solid"))

    # Three point arc
    x, y = arc_points(0, 0, 237.5, 22, 158)
    lines.append((x, y, "solid"))

    return lines


def add_court(fig: go.Figure, color: str = "white") -> go.Figure:
    """Draw the half court on top of a figure."""
    for x, y, dash in court_lines():
        fig.add_trace(
            go.Scatter(
                x=x, y=y,
                mode="lines",
                line=dict(color=color, width=1.5, dash=dash),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    return fig


def base_layout(fig: go.Figure) -> go.Figure:
    """Apply the shared axis range, aspect ratio, and transparent background."""
    fig.update_layout(
        xaxis=dict(range=[-250, 250], visible=False),
        yaxis=dict(range=[-60, 356.7], visible=False, scaleanchor="x", scaleratio=1),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10),
        height=600,
        font=dict(color="#FFFFFF"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


# ---------------------------------------------------------------- Charts

def shot_chart_figure(shots, color: str) -> go.Figure:
    made = shots[shots["SHOT_MADE_FLAG"] == 1]
    missed = shots[shots["SHOT_MADE_FLAG"] == 0]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=missed["LOC_X"], y=missed["LOC_Y"],
        mode="markers",
        marker=dict(color="#B5B5B5", size=6, opacity=0.75),
        name="Missed",
        hovertemplate="Missed<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=made["LOC_X"], y=made["LOC_Y"],
        mode="markers",
        marker=dict(color=color, size=6, opacity=1),
        name="Made",
        hovertemplate="Made<extra></extra>",
    ))

    add_court(fig, color="white")
    base_layout(fig)

    return fig


def heat_map_figure(shots, color: str) -> go.Figure:
    """
    Uses a smooth 2D kernel density estimate over a 200x200 grid, the
    same approach as heat_map.r's stat_density_2d(n = 200) -- rather
    than binning shots into a coarse grid, which looks blocky/pixelated
    by comparison.
    """
    x = shots["LOC_X"].to_numpy(dtype=float)
    y = shots["LOC_Y"].to_numpy(dtype=float)

    if len(x) < 2:
        fig = go.Figure()
        add_court(fig, color="white")
        base_layout(fig)
        return fig

    x_grid = np.linspace(-250, 250, 200)
    y_grid = np.linspace(-60, 356.7, 200)
    xx, yy = np.meshgrid(x_grid, y_grid)

    kde = gaussian_kde(np.vstack([x, y]))
    zz = kde(np.vstack([xx.ravel(), yy.ravel()])).reshape(xx.shape)
    zz = zz / zz.max()

    # Fade very low density to fully transparent, matching the way
    # alpha = density tapers off smoothly in the R version, instead of
    # a flat wash of color covering the whole court.
    zz = np.where(zz < 0.03, np.nan, zz)

    r, g, b = hex_to_rgb(color)
    colorscale = [
        [0.0, f"rgba({r},{g},{b},0)"],
        [0.25, f"rgba({r},{g},{b},0.25)"],
        [0.55, f"rgba({r},{g},{b},0.6)"],
        [1.0, f"rgba({r},{g},{b},1)"],
    ]

    fig = go.Figure()

    fig.add_trace(go.Heatmap(
        x=x_grid, y=y_grid, z=zz,
        colorscale=colorscale,
        zsmooth="best",
        showscale=False,
        hoverinfo="skip",
    ))

    add_court(fig, color="white")
    base_layout(fig)

    return fig


# ---------------------------------------------------------------- Data

@st.cache_data(show_spinner=False)
def get_active_players():
    return sorted(players.get_active_players(), key=lambda p: p["full_name"])


@st.cache_data(show_spinner=False)
def get_player_seasons(player_id: int):
    info = commonplayerinfo.CommonPlayerInfo(player_id=player_id)
    career = info.get_data_frames()[0]

    first_year = int(career["FROM_YEAR"][0])
    last_year = int(career["TO_YEAR"][0])
    team = career["TEAM_NAME"][0]

    seasons = [f"{y}-{str(y + 1)[2:]}" for y in range(first_year, last_year + 1)]

    return seasons, team


@st.cache_data(show_spinner=False)
def get_shot_data(player_id: int, season: str):
    response = ShotChartDetail(
        team_id=0,
        player_id=player_id,
        season_nullable=season,
        context_measure_simple="FGA",
    )
    return response.get_data_frames()[0]


# ---------------------------------------------------------------- UI

st.title("BRADLEY ANALYTICS")
st.caption(
    "Live NBA shot charts and shooting heat maps, generated in real time "
    "from the NBA API. Hover, zoom, and pan the chart below."
)

active_players = get_active_players()
player_names = [p["full_name"] for p in active_players]

col1, col2 = st.columns(2)

with col1:
    selected_name = st.selectbox(
        "Player",
        player_names,
        index=None,
        placeholder="Select a player",
    )

selected_season = None
player_team = None

if selected_name:
    selected_player = next(p for p in active_players if p["full_name"] == selected_name)

    with st.spinner("Loading seasons..."):
        seasons, player_team = get_player_seasons(selected_player["id"])

    with col2:
        selected_season = st.selectbox(
            "Season",
            list(reversed(seasons)),
            index=None,
            placeholder="Select a season",
        )

if selected_name and selected_season:
    viz_type = st.radio("Visualization", ["Shot Chart", "Heat Map"], horizontal=True)

    team_options = list(TEAM_COLORS.keys())
    default_team_index = team_options.index(find_matching_team(player_team))

    swatch_col, dropdown_col = st.columns([1, 6])

    with dropdown_col:
        selected_team = st.selectbox(
            "Team Color",
            team_options,
            index=default_team_index,
        )

    color = TEAM_COLORS[selected_team]

    with swatch_col:
        st.markdown(
            f'<div style="width: 34px; height: 34px; border-radius: 4px; '
            f'background-color: {color}; border: 1px solid #333333; '
            f'margin-top: 28px;"></div>',
            unsafe_allow_html=True,
        )

    generate = st.button("Generate", type="primary")
else:
    generate = False

if generate:
    with st.spinner(f"Pulling shot data for {selected_name} ({selected_season})..."):
        shots = get_shot_data(selected_player["id"], selected_season)

    if shots.empty:
        st.error(f"No shot data found for {selected_name} during {selected_season}.")
    else:
        if viz_type == "Shot Chart":
            fig = shot_chart_figure(shots, color)
        else:
            fig = heat_map_figure(shots, color)

        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
        st.caption(f"{len(shots):,} field goal attempts • {selected_name} • {selected_season}")

st.divider()
st.caption(
    "Built by Alex Bradley. See the full project, including the downloadable "
    "desktop tool, on [GitHub](https://github.com/alexbrxdley/Bradley-Analytics-Software-Engine)."
)
