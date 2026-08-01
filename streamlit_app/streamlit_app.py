"""
Bradley Analytics -- Streamlit Dashboard
------------------------------------------
The live, browser-based version of the Bradley Analytics Software Engine.

Lets a visitor pick any active NBA player, a year, and regular
season/playoffs, then choose a shot chart or shooting heat map --
generated live from the NBA API and rendered as a fully interactive
Plotly chart, right in the browser.

This app is self-contained on purpose: the court geometry and team
colors mirror the R/ggplot2 versions used by the desktop tool, so the
look stays consistent between bradley.bat and this dashboard.
"""

import os
import time
from datetime import datetime

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from nba_api.stats.endpoints import commonplayerinfo, ShotChartDetail
from nba_api.stats.static import players
from scipy.stats import gaussian_kde


# stats.nba.com rejects or hangs on requests that don't look like they
# came from a browser. nba_api ships default headers, but sending a full
# modern browser set (plus the NBA-specific stats tokens) is the standard
# way to make the endpoints respond reliably. Brotli is deliberately left
# out of Accept-Encoding so responses always decode without the optional
# brotli package installed.
NBA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}


def _get_proxy():
    """
    Optional proxy for stats.nba.com traffic. Set an NBA_PROXY value
    (Streamlit secret or environment variable) if you deploy somewhere
    whose outbound IPs stats.nba.com blocks -- Streamlit Community Cloud
    is the common case. Format: "http://user:pass@host:port". Returns
    None (direct connection) when unset, so local runs are unaffected.
    """
    try:
        val = st.secrets.get("NBA_PROXY")
        if val:
            return val
    except Exception:
        pass
    return os.environ.get("NBA_PROXY") or None


NBA_PROXY = _get_proxy()


def fetch_with_retry(endpoint_cls, max_attempts=3, timeout=90, **kwargs):
    """
    Calls an nba_api endpoint with a long timeout, browser-like headers,
    an optional proxy, and retries with exponential backoff.

    stats.nba.com is slow and flaky from many networks (cloud-hosted
    environments especially). This won't defeat a hard IP block -- for
    that, set NBA_PROXY -- but it smooths over ordinary slowness and
    transient failures instead of crashing on the first hiccup.
    """
    if NBA_PROXY:
        kwargs.setdefault("proxy", NBA_PROXY)

    last_exc = None
    for attempt in range(max_attempts):
        try:
            return endpoint_cls(timeout=timeout, headers=NBA_HEADERS, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < max_attempts - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_exc


st.set_page_config(
    page_title="Bradley Analytics",
    layout="centered",
)


# ---------------------------------------------------------------- Theme
# The dark/light contrast for every native widget (dropdowns, buttons,
# checkboxes, etc.) is handled by Streamlit's own theme system via
# .streamlit/config.toml sitting at the project root -- that's far more
# reliable than hand-written CSS, since Streamlit manages correct
# text/background contrast internally. The CSS below only adds the
# font, title styling, and the gradient/grain background flourish on
# top of that.

# Each noise tile is a feTurbulence field passed through a gamma
# feComponentTransfer. The gamma curve crushes the mid-gray values of
# the raw noise down toward black while leaving the brightest pixels
# bright -- so instead of a flat grey haze, what survives is a field of
# crisp, sparse light speckles that reads as real photographic film
# grain when layered over the black gradient below with screen blend.
#
# Three scales are defined and combined in pairs across the two overlay
# layers, which gives the grain depth: large-scale clumping plus fine,
# tight speckle detail on top.

def _noise_svg(base_frequency: float, octaves: int, gamma: float) -> str:
    """Build a URL-encoded turbulence-noise data URI with a gamma boost."""
    return (
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E"
        "%3Cfilter id='n'%3E"
        f"%3CfeTurbulence type='fractalNoise' baseFrequency='{base_frequency}' "
        f"numOctaves='{octaves}' stitchTiles='stitch'/%3E"
        "%3CfeComponentTransfer%3E"
        f"%3CfeFuncR type='gamma' amplitude='1' exponent='{gamma}' offset='0'/%3E"
        f"%3CfeFuncG type='gamma' amplitude='1' exponent='{gamma}' offset='0'/%3E"
        f"%3CfeFuncB type='gamma' amplitude='1' exponent='{gamma}' offset='0'/%3E"
        "%3C/feComponentTransfer%3E"
        "%3C/filter%3E"
        "%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E"
    )


# Coarse grain: larger, softer speckles that give the texture body.
NOISE_SVG = _noise_svg(base_frequency=0.75, octaves=4, gamma=2.4)

# Fine grain: tighter speckles layered in for more visible texture detail.
NOISE_SVG_FINE = _noise_svg(base_frequency=1.6, octaves=3, gamma=2.2)

# Ultra-fine grain: the tightest, sharpest speckle detail on top.
NOISE_SVG_ULTRA_FINE = _noise_svg(base_frequency=2.5, octaves=2, gamma=2.0)

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Kalnia:wght@500&display=swap');

html, body, [class^="st-"], .stMarkdown, h2, h3, h4, p, span, label, button {{
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif !important;
    font-weight: 300 !important;
}}

/* Main title only -- everything else above uses Helvetica Neue Light */
[data-testid="stMarkdownContainer"] h1 {{
    font-family: 'Kalnia', serif !important;
    font-weight: 500 !important;
    font-size: 3.6rem !important;
    color: #FFFFFF !important;
    text-shadow:
        0 0 8px rgba(255, 255, 255, 0.7),
        0 0 20px rgba(255, 255, 255, 0.45),
        0 0 44px rgba(255, 255, 255, 0.25);
}}

.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
    background:
        /* Edge vignette -- darkens the corners for a premium, focused frame */
        radial-gradient(ellipse 120% 90% at 50% 40%,
            rgba(0, 0, 0, 0) 55%, rgba(0, 0, 0, 0.55) 100%),
        /* Soft cool highlight glow, off-center top-left, for depth */
        radial-gradient(circle at 22% 12%,
            rgba(48, 52, 66, 0.55) 0%, rgba(20, 22, 30, 0.18) 32%,
            rgba(0, 0, 0, 0) 60%),
        /* Faint warm counter-glow, lower-right, so the field isn't flat */
        radial-gradient(circle at 82% 88%,
            rgba(40, 30, 30, 0.35) 0%, rgba(0, 0, 0, 0) 50%),
        /* Deep base gradient -- near-black with subtle tonal drift */
        linear-gradient(145deg,
            #000000 0%, #060608 22%, #0a0a0f 45%, #050506 62%,
            #08080a 80%, #000000 100%)
        !important;
    background-attachment: fixed !important;
}}

/* Static aesthetic grain -- two fixed noise layers at different
   scales for texture depth. No animation/movement.
   Important: opacity here must stay LOW (well under 0.15). Noise from
   feTurbulence averages out to roughly mid-gray, so at higher opacity
   with mix-blend-mode: screen, the noise's average brightness washes
   the entire background toward flat grey instead of staying black
   with visible light speckles on top. Low opacity keeps only the
   brightest noise pixels visible as grain. */
.stApp::before {{
    content: "";
    position: fixed;
    top: -50%; left: -50%; right: -50%; bottom: -50%;
    width: 200%; height: 200%;
    background-image: url("{NOISE_SVG}"), url("{NOISE_SVG_ULTRA_FINE}");
    background-size: 260px 260px, 38px 38px;
    opacity: 0.13;
    pointer-events: none;
    z-index: 9999;
    mix-blend-mode: screen;
}}

.stApp::after {{
    content: "";
    position: fixed;
    top: -50%; left: -50%; right: -50%; bottom: -50%;
    width: 200%; height: 200%;
    background-image: url("{NOISE_SVG_FINE}"), url("{NOISE_SVG_ULTRA_FINE}");
    background-size: 96px 96px, 24px 24px;
    opacity: 0.08;
    pointer-events: none;
    z-index: 9998;
    mix-blend-mode: screen;
}}

header[data-testid="stHeader"] {{
    background: transparent !important;
}}

#MainMenu {{
    visibility: hidden !important;
}}

hr {{
    border-color: #333333 !important;
}}

[data-testid="baseButton-primary"], button[kind="primary"] {{
    background-color: transparent !important;
    border: 1px solid #FFFFFF !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    font-size: 1.15rem !important;
}}

[data-testid="baseButton-primary"]:hover, button[kind="primary"]:hover {{
    background-color: rgba(255, 255, 255, 0.1) !important;
    border-color: #FFFFFF !important;
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
    if not team_name:
        return next(iter(TEAM_COLORS))

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
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            font=dict(size=18),
        ),
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


# NBA shot-chart data (ShotChartDetail) only exists from the 1996-97
# season onward, so that's the earliest year worth ever offering.
FIRST_SHOTCHART_SEASON = 1996


def current_season_start_year() -> int:
    """
    Starting year of the most recent NBA season that could have data.
    NBA seasons run October -> June, so before October the latest
    playable season started in the previous calendar year.
    """
    now = datetime.now()
    return now.year if now.month >= 10 else now.year - 1


def season_range(first_year: int, last_year: int):
    """Build a list like ['1996-97', '1997-98', ...] from start years."""
    return [f"{y}-{str(y + 1)[2:]}" for y in range(first_year, last_year + 1)]


@st.cache_data(show_spinner=False)
def get_player_seasons(player_id: int):
    """
    Return (seasons, team) for a player.

    First tries the live CommonPlayerInfo endpoint to get the player's
    exact career span and current team. That call hits stats.nba.com,
    which is frequently slow, rate-limited, or outright blocked from
    cloud hosts (Streamlit Community Cloud especially) and can be flaky
    even locally.

    If it fails -- or returns unusable data -- we fall back to the full
    range of seasons that have shot-chart data (1996-97 through the
    current season) with no team pre-selected. This guarantees the Year
    dropdown always populates instead of dead-ending on an error, which
    was the previous behavior when this single call failed.
    """
    latest = current_season_start_year()
    fallback = (season_range(FIRST_SHOTCHART_SEASON, latest), None)

    try:
        info = fetch_with_retry(commonplayerinfo.CommonPlayerInfo, player_id=player_id)
        career = info.get_data_frames()[0]

        if career.empty:
            return fallback

        first_year = int(career["FROM_YEAR"].iloc[0])
        last_year = int(career["TO_YEAR"].iloc[0])
        team = career["TEAM_NAME"].iloc[0] or None

        # Clamp to sane bounds so we never build an empty or pre-1996 list.
        first_year = max(first_year, FIRST_SHOTCHART_SEASON)
        last_year = max(last_year, first_year)

        return season_range(first_year, last_year), team
    except Exception:
        return fallback


@st.cache_data(show_spinner=False)
def get_shot_data(player_id: int, season: str, season_type: str):
    response = fetch_with_retry(
        ShotChartDetail,
        team_id=0,
        player_id=player_id,
        season_nullable=season,
        season_type_all_star=season_type,
        context_measure_simple="FGA",
    )
    return response.get_data_frames()[0]


# ---------------------------------------------------------------- UI

st.title("BRADLEY ANALYTICS")
st.caption("Live, interactive NBA shot charts and shooting heat maps.")

active_players = get_active_players()
player_names = [p["full_name"] for p in active_players]

selected_name = st.selectbox(
    "Player",
    player_names,
    index=None,
    placeholder="Enter player name",
    label_visibility="collapsed",
)

selected_season = None
selected_season_type = None
player_team = None

if selected_name:
    selected_player = next(p for p in active_players if p["full_name"] == selected_name)

    with st.spinner("Loading seasons..."):
        seasons, player_team = get_player_seasons(selected_player["id"])

    col1, col2 = st.columns(2)

    with col1:
        selected_season = st.selectbox(
            "Year",
            list(reversed(seasons)),
            index=None,
            placeholder="Select a year",
        )

    with col2:
        selected_season_type = st.selectbox(
            "Season Type",
            ["Regular Season", "Playoffs"],
            index=0,
        )

if selected_name and selected_season and selected_season_type:
    viz_type = st.radio("Visualization", ["Shot Chart", "Heat Map"], horizontal=True)

    team_options = list(TEAM_COLORS.keys())
    default_team_index = team_options.index(find_matching_team(player_team))

    swatch_col, dropdown_col = st.columns([1, 7], gap="small")

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

    st.write("")
    st.write("")
    button_left, button_center, button_right = st.columns([2, 1, 2])
    with button_center:
        generate = st.button("► Run", type="primary", use_container_width=True)
else:
    generate = False

if generate:
    try:
        with st.spinner(f"Pulling shot data for {selected_name} ({selected_season}, {selected_season_type})..."):
            shots = get_shot_data(selected_player["id"], selected_season, selected_season_type)
    except Exception:
        st.error(
            "Couldn't reach stats.nba.com to pull shot data. This API is "
            "occasionally slow or unreliable when hosted in the cloud -- "
            "try again in a moment."
        )
        st.stop()

    if shots.empty:
        st.error(
            f"No shot data found for {selected_name} during {selected_season} "
            f"({selected_season_type})."
        )
    else:
        if viz_type == "Shot Chart":
            fig = shot_chart_figure(shots, color)
        else:
            fig = heat_map_figure(shots, color)

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"displaylogo": False, "displayModeBar": False},
        )
        st.caption(
            f"{len(shots):,} field goal attempts • {selected_name} • "
            f"{selected_season} • {selected_season_type}"
        )

st.divider()
st.caption(
    "Built by Alex Bradley. See the full project, including the downloadable "
    "desktop tool, on [GitHub](https://github.com/alexbrxdley/Bradley-Analytics-Software-Engine)."
)
