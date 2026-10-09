"""
Bradley Analytics -- Interactive Streamlit Dashboard.

Run locally with:  streamlit run streamlit/app.py
Deploy for free at: https://streamlit.io/cloud (connects directly to this GitHub repo)

Built directly from Bradley Quant's own app.py as the starting point,
with the finance-specific content replaced by NBA content -- guarantees
identical structure/styling/animation infrastructure by construction,
rather than porting individual pieces across and risking missing one.
"""
import os
import re
import math
import io
import uuid
import contextlib
import json
import time
import random
import unicodedata
import hashlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import matplotlib.pyplot as plt

from nba_data import (get_player_shots, get_team_shots, get_league_shots, get_player_stats,
                       get_team_stats, get_player_bio_stats, get_player_career_seasons,
                       get_team_roster, get_team_lineup_combos, get_player_game_log,
                       get_player_defense_stats, get_player_hustle_stats, get_player_clutch_stats,
                       get_player_passes, get_player_team_for_season, get_player_current_team,
                       get_team_game_log, get_player_stats_by_quarter,
                       get_player_vs_player, get_player_playtype_stats,
                       get_team_stats_by_quarter, get_quarter_game_logs, get_zone_league_averages,
                       get_game_context_lookup, get_passer_assisted_shots, get_passer_assisted_shots_v3,
                       get_assisted_shots_for_receivers, get_team_assist_network, get_league_assist_networks,
                       get_league_lineup_combos, get_current_player_teams, get_team_player_on_court)
from nba_api.stats.static import players, teams
from teams import get_team_color, DEFAULT_COLOR, nearest_color_swatch, get_player_headshot_url, get_team_logo_url, first_working_url
from stats_config import COURT_GRAPHS, AXIS_GRAPHS, ANIMATED_GRAPHS, GAME_LOG_GRAPHS, COMPARISON_GRAPHS, get_stats_for_mode, BRADLEY_RATING_DESCRIPTIONS, ALL_SEASONS, VIZ_CATEGORIES, LOWER_IS_BETTER_STATS
import stats_config as _stats_config
import pickers
import stat_menus
import ai_search
import criteria_tools
_stats_config.refresh_seasons()   # the default season moves on by itself the day after each season opens
import community_storage
from visuals import (build_shot_chart, build_heat_map, build_hex_shot_chart, build_bar_chart,
                      build_scatter_plot, build_animated_shot_chart, build_trade_breakdown_image,
                      build_onoff_column_image, build_static_stat_table_image,
                      build_histogram, build_box_plot, build_dot_plot,
                      build_density_plot, build_cumulative_distribution_plot, build_line_chart,
                      build_slope_chart, build_waterfall_chart, build_combo_chart, build_tornado_chart,
                      build_radar_chart, build_head_to_head_table, build_calendar_heat_map,
                      build_court_zone_map, build_small_multiples_shot_charts, build_court_radar_hybrid,
                      build_sankey_flow, build_network_diagram, build_lineup_shapes_diagram, build_momentum_chart,
                      build_impact_clock, build_bump_chart, build_court_connection_map,
                      recolor_white_text, court_zone_key, court_zone_key_from_xy, court_zone_key_for_shot,
                      PASSING_ZONE_NAMES)
import interactive
import hotspots as hover

st.set_page_config(page_title="Bradley Analytics", page_icon=os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png"), layout="wide", initial_sidebar_state="auto")


# ---------------------------------------------------------------- lineup numbers for the website
# The website's Lineup Network window (docs/assets/live-strip.js, "Season Net Ratings") gets its numbers from this
# dashboard: it opens it, hidden, as ?lineups=SAS&season=2025-26 and this answers with that team's season lineups --
# every 2-, 3-, 4- and 5-man group with its net rating, minutes and games together, exactly what the On/Off Lineup
# Network page shows for that team and season with a minimum of 0 minutes (the same calls: _team_lineup_frame) --
# sent back to the website with postMessage. Nothing else of the dashboard is drawn for such a visit.
def _website_lineups(tri, season):
    team = next((t for t in teams.get_teams() if t["abbreviation"] == tri), None)
    if team is None:
        raise ValueError(f"unknown team {tri}")
    team_id = team["id"]
    names = {}
    try:                                                   # full names first (the website matches players by name)
        roster = get_team_roster(team_id, season)
        for pid, nm in zip(roster["PLAYER_ID"], roster["PLAYER"]):
            names[str(int(pid))] = str(nm)
    except Exception:  # noqa: BLE001
        pass

    def id_list(group_id):
        return [int(x) for x in str(group_id or "").strip("-").split("-") if x.strip().isdigit()]

    groups = {}
    for size in (2, 3, 4, 5):
        adv = get_team_lineup_combos(team_id, season, group_quantity=size, measure_type="Advanced")
        minutes = {}
        try:
            base = get_team_lineup_combos(team_id, season, group_quantity=size, measure_type="Base")
            for gid, m in zip(base["GROUP_ID"], base["MIN"]):
                minutes[tuple(sorted(id_list(gid)))] = float(m)
        except Exception:  # noqa: BLE001 -- the Advanced numbers' own minutes then
            pass
        out = {}
        gnames = adv["GROUP_NAME"] if "GROUP_NAME" in adv.columns else [None] * len(adv)
        gps = adv["GP"] if "GP" in adv.columns else [0] * len(adv)
        mins_adv = adv["MIN"] if "MIN" in adv.columns else [0] * len(adv)
        for gid, gname, net, gp, m_adv in zip(adv["GROUP_ID"], gnames, adv["NET_RATING"], gps, mins_adv):
            ids = id_list(gid)
            try:
                net = float(net)
            except (TypeError, ValueError):
                continue
            if len(ids) != size or net != net:
                continue
            # a player not on the season's roster (traded away): the lineup's own "J. Tatum" names
            for pid, short in zip(ids, str(gname or "").split(" - ")):
                names.setdefault(str(pid), short.strip())
            key = tuple(sorted(ids))
            m = minutes.get(key, m_adv)
            out["-".join(str(i) for i in key)] = [round(net, 1), round(float(m or 0), 1), int(gp or 0)]
        groups[str(size)] = out
    for pid in list(names):                               # a short name -> the full one when nba_api knows it
        if "." in names[pid]:
            info = players.find_player_by_id(int(pid))
            if info and info.get("full_name"):
                names[pid] = info["full_name"]
    return {"season": season, "team": tri, "players": names, "groups": groups}


_lineups_team = str(st.query_params.get("lineups") or "").upper()
if _lineups_team:
    _lineups_season = str(st.query_params.get("season") or "")
    _answer = {"type": "ba-lineups", "team": _lineups_team, "season": _lineups_season}
    if re.fullmatch(r"[A-Z]{2,3}", _lineups_team) and re.fullmatch(r"\d{4}-\d{2}", _lineups_season):
        try:
            _answer["data"] = _website_lineups(_lineups_team, _lineups_season)
        except Exception as _e:  # noqa: BLE001
            _answer["error"] = str(_e)[:200]
    else:
        _answer["error"] = "bad request"
    components.html("<script>try { window.top.postMessage(" +
                    json.dumps(_answer, separators=(",", ":")).replace("</", "<\\/") +
                    ", '*'); } catch (e) {}</script>", height=0)
    st.stop()

# Chart text colour (the White/Black toggle) and team-logo badges are applied by hooks on st.pyplot / st.selectbox /
# st.multiselect. They live in ui_hooks.py and are installed once per server process: wrapping these functions from
# inside this script stacked another layer on every rerun (shared by all visitors) until charts and pickers hit
# Python's recursion limit and failed until the server restarted.
import ui_hooks
import org_sections
import salary_table
import ratings_data
import visuals
from html import escape as html_escape
from team_grid import team_grid_radio
import team_grid
ui_hooks.install()
ui_hooks.begin_run()

GOLD_GRADIENT = "linear-gradient(135deg, #B8860B, #F5D370, #B8860B)"
# the desktop sidebar's width: 30px margin + logo (34) + gap (10) + "Analytics" in Playfair Display 28px (116) + 30px margin
SIDEBAR_WIDTH_PX = 222
# A more dramatic variant for animated/counting numbers specifically -- darker
# dark end, paired with a soft glow, so short numeric strings read as a real
# gradient instead of looking flat (approved in the "example 8" review pass).
GOLD_GRADIENT_DRAMATIC = "linear-gradient(135deg, #8a6508, #F5D370, #8a6508)"
# A horizontal, seamlessly-repeating pattern (unlike the two above, which are
# only ever meant to span exactly one element edge-to-edge) for text that
# should shimmer -- paired with background-repeat:repeat-x and a fixed-pixel
# background-size, matching the same technique already proven on the
# website's own animated gold text, so panning it never shows a visible
# reset/jump the way panning a plain 3-stop gradient would.
GOLD_SHIMMER = ("linear-gradient(90deg, #8a6410 0%, #D4AF37 18%, #FFF0B8 34%, "
                 "#F5D370 50%, #D4AF37 66%, #B8860B 82%, #8a6410 100%)")
# Same repeating-tile shimmer technique, but built from GOLD_GRADIENT_DRAMATIC's
# darker stops specifically, so the animated count-up numbers keep their
# distinctive darker "dramatic" look (already approved in the "example 8"
# review pass) while also gaining the shimmer motion.
GOLD_SHIMMER_DRAMATIC = ("linear-gradient(90deg, #5c4207 0%, #8a6508 18%, #F5D370 34%, "
                          "#FFF0B8 50%, #F5D370 66%, #8a6508 82%, #5c4207 100%)")

# Load the circular toggle icon once, base64-encoded for inline embedding in custom HTML/JS
import base64
_icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "toggle_icon.png")
with open(_icon_path, "rb") as _f:
    TOGGLE_ICON_B64 = base64.b64encode(_f.read()).decode()

# SVG gradient definition merged into the same markdown call as the main
# CSS block -- each separate st.markdown() call, even one producing zero
# visible height, still consumes a full 16px flexbox gap in the main
# content area, which was pushing every page's title down well below
# where the sidebar's own content starts.
# Sidebar order. Defined here, ahead of the sidebar CSS, because the two gold
# divider lines in that CSS are positioned from this list (see below) rather
# than from hardcoded nth-of-type numbers that silently pointed at the wrong
# item whenever a category was added or moved.
CATEGORIES = [
    "Home",
    "AI Search",
    "Search by Player",
    "Search by Team",
    "Search by Criteria",
    "On/Off Lineup Network",
    "Stat Formula Creator",
    "Front Office",
    "Coaching",
    "Tableau Dashboard",
    "Community Uploads",
    "Glossary",
    "Upload Stats",
]
_DIVIDER_ABOVE_TOOLS = CATEGORIES.index("Search by Player") + 1    # 1-based nth-of-type
_DIVIDER_ABOVE_ORG = CATEGORIES.index("Front Office") + 1
_DIVIDER_ABOVE_EXTRAS = CATEGORIES.index("Tableau Dashboard") + 1

st.markdown(f"""
<svg width="0" height="0" style="position:absolute">
  <defs>
    <linearGradient id="goldIconGradient" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#B8860B" />
      <stop offset="50%" stop-color="#F5D370" />
      <stop offset="100%" stop-color="#B8860B" />
    </linearGradient>
  </defs>
</svg>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500&display=swap" rel="stylesheet">
<style>
    /* Gold text-selection highlight, replacing the browser/OS default
       blue - ::selection doesn't reliably support gradient
       backgrounds across browsers, so this uses a solid gold matching
       the app's own accent color instead, which is the closest
       consistently-achievable version of the request. */
    ::selection {{
        background: #D4AF37;
        color: #0d0d0d;
    }}

    /* Playfair Display renders every character EXCEPT digits (the Google
       Fonts <link> above provides it). This extra @font-face, under the
       SAME family name, tells the browser to use Times New Roman
       specifically for digit characters (U+0030-0039) instead - letters
       stay Playfair Display, numbers render in Times New Roman. */
    @font-face {{
        font-family: "Playfair Display";
        src: local("Times New Roman");
        unicode-range: U+0030-0039;
        font-weight: 500;
    }}

    .stApp {{
        background: linear-gradient(135deg, #1A1A1A 0%, #070707 73%);
        background-attachment: fixed;
        background-size: 100vw 100vh;
        font-family: Arial, sans-serif;
    }}
    section[data-testid="stSidebar"] {{
        background: linear-gradient(135deg, #1A1A1A 0%, #070707 73%);
        border-right: 1px solid #2a2a2a;
    }}
    /* Desktop: the sidebar only as wide as its widest line needs - the two-line "Bradley / Analytics" title beside
       its logo (the nav items are narrower) - plus the same margin on the right as on the left. */
    @media (min-width: 641px) {{
        section[data-testid="stSidebar"][aria-expanded="true"] {{
            width: {SIDEBAR_WIDTH_PX}px !important; min-width: {SIDEBAR_WIDTH_PX}px !important; max-width: {SIDEBAR_WIDTH_PX}px !important;
        }}
    }}

    h1, h2, h3, h4, h5, h6 {{
        font-family: "Playfair Display", serif !important;
        font-weight: 500 !important;
        color: #ffffff;
    }}

    /* Gold-gradient text accent - the ONLY accent color in this app.
       Numbers/results use bold Times New Roman, never white Arial. Uses the
       more dramatic gradient variant since these are the animated
       (count-up) numbers - approved in the "example 8" review pass. */
    div[data-testid="stMetricValue"] {{
        background: {GOLD_SHIMMER_DRAMATIC};
        background-size: 320px 100%;
        background-repeat: repeat-x;
        animation: bqGoldTextShimmer 5s linear infinite;
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        font-family: "Times New Roman", serif;
        font-weight: bold;
        filter: drop-shadow(0 0 8px rgba(245, 211, 112, 0.35));
    }}
    div[data-testid="stMetricLabel"] {{ color: #c9c9c9; }}
    /* Every widget's own label (the text above a text box, selectbox,
       slider, multiselect, etc.) - confirmed via direct DOM inspection
       that Streamlit renders all of these through the same consistent
       stWidgetLabel structure, so one rule here reaches every label in
       the app instead of needing to hand-edit 25+ individual widget
       calls. Matches the bold-grey "Boston Celtics sends:" style used
       elsewhere, applied consistently everywhere now. */
    [data-testid="stWidgetLabel"] p {{
        color: #888888 !important;
        font-weight: bold !important;
    }}

    /* Sidebar category nav - text-link style matching the GitHub Pages nav,
       no bubble/dot indicator. Selected = gold gradient text. Hover on an
       unselected item = lighter gold. */
    label[data-testid="stRadioOption"] > div > div > div:first-child {{
        display: none !important;
    }}
    label[data-testid="stRadioOption"] {{
        position: relative;
        padding: 6px 4px;
        border-radius: 4px;
        cursor: pointer;
    }}
    /* Sidebar radio options shrink-to-fit their own text by default,
       which is exactly why the two gold dividers below could end up
       different lengths - a border-top on a shrink-wrapped element is
       only as wide as that element's own content, so a divider sitting
       before a short label naturally comes out shorter than one before
       a long label. Scoped to the sidebar specifically so other
       st.radio() widgets elsewhere in the app aren't forced full-width too. */
    section[data-testid="stSidebar"] label[data-testid="stRadioOption"] {{
        display: block;
        width: 100%;
    }}
    label[data-testid="stRadioOption"]::after {{
        content: "";
        position: absolute;
        left: 4px;
        right: 4px;
        bottom: 2px;
        height: 2px;
        background: {GOLD_GRADIENT};
        transform: scaleX(0);
        transform-origin: left;
        transition: transform 0.3s ease;
    }}
    label[data-testid="stRadioOption"]:hover::after {{
        transform: scaleX(1);
    }}
    label[data-testid="stRadioOption"] p {{
        color: #c9c9c9;
        font-family: Arial, sans-serif;
        transition: color 0.15s ease;
        margin: 0;
    }}
    label[data-testid="stRadioOption"]:hover p {{
        color: #F5D370;
    }}
    label[data-testid="stRadioOption"][data-selected="true"] p {{
        background: {GOLD_SHIMMER};
        background-size: 320px 100%;
        background-repeat: repeat-x;
        animation: bqGoldTextShimmer 5s linear infinite;
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        font-weight: bold;
    }}

    /* Divider between Home/AI Search and the main tools group.
       Scoped to the sidebar specifically - confirmed as a real bug
       without this scoping: it was applying to every st.radio() in the
       app (e.g. Search by Criteria's "Stat mode" picker), putting a
       stray divider line above whichever option happened to be 3rd or
       9th in that unrelated group. The positions come from CATEGORIES
       (_DIVIDER_ABOVE_TOOLS / _DIVIDER_ABOVE_EXTRAS), so adding a
       category can no longer leave a divider on the wrong item. */
    section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:nth-of-type({_DIVIDER_ABOVE_TOOLS}) {{
        border-top: 1px solid transparent;
        border-image: {GOLD_GRADIENT} 1;
        margin-top: 10px;
        padding-top: 16px;
    }}

    /* Divider between the main tools group and the Tableau Dashboard / Community Uploads / Glossary group */
    section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:nth-of-type({_DIVIDER_ABOVE_EXTRAS}) {{
        border-top: 1px solid transparent;
        border-image: {GOLD_GRADIENT} 1;
        margin-top: 10px;
        padding-top: 16px;
    }}

    /* Divider above the Front Office / Coaching pair - sandwiches
       that pair between two gold lines, the way every other grouping
       in this sidebar is set off. */
    section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:nth-of-type({_DIVIDER_ABOVE_ORG}) {{
        border-top: 1px solid transparent;
        border-image: {GOLD_GRADIENT} 1;
        margin-top: 10px;
        padding-top: 16px;
    }}

    /* Buttons: full width, gradient-gold border AND text, glow on hover
       (not a solid fill) */
    div[data-testid="stElementContainer"]:has(div[data-testid="stButton"], div[data-testid="stFormSubmitButton"], div[data-testid="stDownloadButton"]) {{
        width: 100% !important;
    }}
    div[data-testid="stButton"], div[data-testid="stFormSubmitButton"], div[data-testid="stDownloadButton"] {{
        width: 100% !important;
    }}
    div[data-testid="stButton"] button, div[data-testid="stFormSubmitButton"] button, div[data-testid="stDownloadButton"] button {{
        width: 100% !important;
        background: linear-gradient(135deg, #1A1A1A 0%, #050505 100%) !important;
        border: none;
        border-radius: 10px;
        position: relative;
        font-family: Arial, sans-serif;
        transition: box-shadow 0.2s ease;
    }}
    div[data-testid="stButton"] button::before, div[data-testid="stFormSubmitButton"] button::before, div[data-testid="stDownloadButton"] button::before {{
        content: "";
        position: absolute;
        inset: 0;
        border-radius: 10px;
        padding: 2px;
        background: {GOLD_GRADIENT};
        -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
        -webkit-mask-composite: xor;
        mask-composite: exclude;
        pointer-events: none;
    }}
    div[data-testid="stButton"] button p, div[data-testid="stFormSubmitButton"] button p, div[data-testid="stDownloadButton"] button p {{
        background: {GOLD_SHIMMER};
        background-size: 320px 100%;
        background-repeat: repeat-x;
        animation: bqGoldTextShimmer 5s linear infinite;
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        font-weight: bold;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
    }}
    /* The play triangle is ONLY on the RUN buttons (persistent_run_button's st.button keyed "run_btn_..."); no other
       button has it. A CSS-drawn triangle (border trick), not a unicode character - a device/browser's font not
       including the right glyph is a real cross-platform risk, not a hypothetical one. */
    div[data-testid="stButton"] button p::before, div[data-testid="stFormSubmitButton"] button p::before, div[data-testid="stDownloadButton"] button p::before {{
        display: none;
    }}
    div[class*="st-key-run_btn_"] div[data-testid="stButton"] button p::before {{
        display: block;
        content: "";
        width: 0;
        height: 0;
        border-top: 7px solid transparent;
        border-bottom: 7px solid transparent;
        border-left: 11px solid #D4AF37;
        flex-shrink: 0;
    }}
    div[data-testid="stButton"] button:hover, div[data-testid="stFormSubmitButton"] button:hover, div[data-testid="stDownloadButton"] button:hover {{
        box-shadow: 0 0 14px 2px rgba(212, 175, 55, 0.55);
    }}

    /* Interactive (hover) charts are an iframe; as an inline element it sat on a text baseline and left ~9px of
       empty space under it, so the gap below a chart didn't match the gap between the buttons under it. */
    iframe[srcdoc*="ic-wrap"] {{
        display: block;
    }}

    /* Removes the play-triangle icon specifically from buttons wrapped
       in a container whose key starts with "no_icon_" - used for the
       Tableau Dashboard's own utility buttons (+, swap arrows, Remove,
       Reset) and the share-to-community / add-to-dashboard buttons
       under generated charts, none of which are "run" actions the
       triangle icon is meant to signal. */
    div[class*="st-key-no_icon_"] button p::before {{
        display: none;
    }}

    /* Number input +/- steppers: the +/- SYMBOL turns gradient gold on
       hover - explicitly kill Streamlit's native theme-color hover
       background first, since it would otherwise show through as a flat fill */
    button[data-testid="stNumberInputStepUp"]:hover,
    button[data-testid="stNumberInputStepDown"]:hover {{
        background: transparent !important;
    }}
    button[data-testid="stNumberInputStepUp"]:hover svg,
    button[data-testid="stNumberInputStepDown"]:hover svg {{
        fill: url(#goldIconGradient) !important;
    }}

    /* Inputs, selects: neutral dark, no navy */
    input, textarea, select,
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"],
    div[data-testid="stNumberInputContainer"],
    div[data-testid="stSelectbox"] div[role="group"],
    div[data-testid="stTextInputRootElement"],
    div[data-testid="stTextAreaRootElement"] {{
        background-color: rgba(255, 255, 255, 0.04) !important;
        border-color: #2a2a2a !important;
        color: #f0f0f0 !important;
    }}
    /* Number boxes are typed into - no +/- step buttons anywhere in the app. */
    [data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"] {{
        display: none !important;
    }}
    /* Multiselect (Add stat filters, Position, etc.) uses a completely
       different structure than selectbox - confirmed via direct DOM
       inspection that its actual white background lives on an unnamed
       parent div one level above stMultiSelectTagsContainer, not on
       any element the rule above can reach. */
    div[data-testid="stMultiSelect"] div:has(> div[data-testid="stMultiSelectTagsContainer"]) {{
        background-color: rgba(255, 255, 255, 0.04) !important;
        border-color: #2a2a2a !important;
    }}
    div[data-testid="stMultiSelectTagsContainer"] {{
        color: #f0f0f0 !important;
    }}
    /* The dropdown popup itself (the options list that appears when you
       click) renders in a separate portal, not nested under the visible
       select box - confirmed via direct DOM inspection, white/navy by
       default regardless of the closed-state styling above. */
    div[data-testid="stSelectboxVirtualDropdown"],
    div[data-testid="stMultiSelectDropdown"] {{
        background: linear-gradient(135deg, #1A1A1A 0%, #050505 100%) !important;
        border: 1px solid #5c4608 !important;
    }}
    div[data-testid="stSelectboxVirtualDropdown"] [role="option"],
    div[data-testid="stMultiSelectDropdown"] [role="option"] {{
        color: #f0f0f0 !important;
        background: transparent !important;
    }}
    div[data-testid="stSelectboxVirtualDropdown"] [role="option"]:hover,
    div[data-testid="stMultiSelectDropdown"] [role="option"]:hover,
    div[data-testid="stSelectboxVirtualDropdown"] [aria-selected="true"],
    div[data-testid="stMultiSelectDropdown"] [aria-selected="true"] {{
        background: rgba(212, 175, 55, 0.15) !important;
        color: #F5D370 !important;
    }}
    /* Selected multiselect chips (Add stat filters, players chosen for
       a trade, etc.) - confirmed via direct DOM inspection to be
       Streamlit's flat default red (rgb(255,75,75)) with no stable
       class, targeted here structurally via the tags container instead.
       No border here deliberately - the container itself already has
       a gold border (targeted via stMultiSelectTagsContainer's parent
       above), and each individual chip also having its own border on
       top of that read as a redundant "double border" effect. */
    div[data-testid="stMultiSelectTagsContainer"] span {{
        background: linear-gradient(135deg, #1A1A1A 0%, #050505 100%) !important;
        color: #F5D370 !important;
    }}

    /* Tabs (Roster/Picks, etc.) - confirmed via direct DOM inspection
       that the active tab's text/border AND a separate selection-
       indicator bar element (a stable react-aria class, not a
       Streamlit testid) both default to Streamlit's red/orange. */
    [data-testid="stTab"][aria-selected="true"] {{
        color: #D4AF37 !important;
    }}
    [data-testid="stTab"][aria-selected="true"] p {{
        color: #D4AF37 !important;
    }}
    .react-aria-SelectionIndicator {{
        background: {GOLD_GRADIENT} !important;
    }}

    /* Checked checkboxes (roster player selection, draft picks, etc.)
       - confirmed via direct DOM inspection of the real structure
       (a react-aria component, not plain HTML): the label itself gets
       data-selected="true" when checked, and its red-filled square is
       specifically the child div wrapping the checkmark svg - not
       :first-child, since the input's wrapping span is actually first.
       This is a pure CSS fix (no JS/polling needed), reliable and
       instant on click rather than dependent on timing. */
    [data-testid="stCheckbox"] label[data-selected="true"] > div:has(svg) {{
        background: {GOLD_GRADIENT} !important;
    }}

    /* AI chat input: gradient-black fill, gradient-gold border */
    div[data-testid="stChatInput"] {{
        background: transparent !important;
        border: none !important;
    }}
    textarea[data-testid="stChatInputTextArea"] {{
        background: linear-gradient(135deg, #1A1A1A 0%, #070707 73%) !important;
        color: #999999 !important;
    }}
    textarea[data-testid="stChatInputTextArea"]::placeholder {{
        color: #888888 !important;
        opacity: 1 !important;
    }}
    div[data-testid="stChatInput"] > div {{
        background: linear-gradient(135deg, #1A1A1A 0%, #070707 73%) !important;
        border: none !important;
        border-radius: 24px !important;
        position: relative !important;
    }}
    div[data-testid="stChatInput"] > div::before {{
        content: "";
        position: absolute;
        inset: 0;
        border-radius: 24px;
        padding: 2px;
        background: {GOLD_GRADIENT};
        -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
        -webkit-mask-composite: xor;
        mask-composite: exclude;
        pointer-events: none;
    }}
    /* Sliders: dark grey track as a fallback/initial state (the real
       grey-to-gold-to-grey gradient between the two handles is computed
       live in JS instead, since direct DOM inspection confirmed BaseWeb
       has no separate "filled segment" element a static CSS rule could
       target - see updateSliderGradient() below). This rule's second
       selector actually matches the two handle thumbs themselves
       (confirmed via inspection, not the segment between them), which
       is also the correct place to make them gold. */
    [data-testid="stSlider"] [role="group"] > div > div:first-child {{
        background: #3a3a3a !important;
    }}
    [data-testid="stSlider"] [role="group"] > div > div[style*="left"] {{
        background: {GOLD_GRADIENT} !important;
    }}
    /* The min/max value labels shown above the slider handles -
       confirmed via direct DOM inspection to be plain <p> tags with no
       stable class, using Streamlit's default red by default. Scoped
       to [role="group"] specifically (not the whole stSlider
       container), since the wider selector was confirmed to also catch
       the widget's own title label (e.g. "Age:"), turning it white
       instead of the intended grey from the global stWidgetLabel rule. */
    [data-testid="stSlider"] [role="group"] p {{
        color: #ffffff !important;
    }}

    /* Submit (send) button: transparent fill, gradient-gold rounded border,
       gradient-gold icon (matching the "Calculate" button style) */
    button[data-testid="stChatInputSubmitButton"] {{
        background: transparent !important;
        border: none !important;
        border-radius: 8px !important;
        position: relative !important;
    }}
    button[data-testid="stChatInputSubmitButton"]::before {{
        content: "";
        position: absolute;
        inset: 0;
        border-radius: 8px;
        padding: 1.5px;
        background: {GOLD_GRADIENT};
        -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
        -webkit-mask-composite: xor;
        mask-composite: exclude;
        pointer-events: none;
    }}
    button[data-testid="stChatInputSubmitButton"] svg {{
        fill: url(#goldIconGradient) !important;
    }}

    /* Titled gradient-gold-bordered info card - replaces st.info()/st.warning()
       everywhere, matching the feature-card style used on the GitHub Pages site */
    .bq-info-card {{
        position: relative;
        border-radius: 10px;
        padding: 16px 20px;
        margin: 12px 0;
        background: linear-gradient(135deg, #1A1A1A 0%, #070707 73%);
    }}
    .bq-info-card::before {{
        content: "";
        position: absolute;
        inset: 0;
        border-radius: 10px;
        padding: 1.5px;
        background: {GOLD_GRADIENT};
        -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
        -webkit-mask-composite: xor;
        mask-composite: exclude;
        pointer-events: none;
    }}
    .bq-info-card-title {{
        display: inline-block;
        font-family: "Playfair Display", serif;
        font-weight: 500;
        font-size: 1.1rem;
        background: {GOLD_SHIMMER};
        background-size: 320px 100%;
        background-repeat: repeat-x;
        animation: bqGoldTextShimmer 5s linear infinite;
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        margin-bottom: 6px;
    }}
    .bq-info-card-body {{
        color: #c9c9c9;
        text-align: left;
        font-family: Arial, sans-serif;
        font-size: 0.95rem;
        line-height: 1.5;
    }}

    /* Chat messages: no avatar icons, user right-aligned, assistant left-aligned */
    div[data-testid="stChatMessage"] {{
        background: transparent !important;
    }}
    div[data-testid^="stChatMessageAvatar"] {{
        display: none !important;
    }}
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {{
        flex-direction: row-reverse;
    }}
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"])
        div[data-testid="stChatMessageContent"] {{
        text-align: right;
        margin-left: auto !important;
        margin-right: 0 !important;
        max-width: 75%;
        flex-grow: 0 !important;
    }}
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarAssistant"])
        div[data-testid="stChatMessageContent"] {{
        text-align: left;
        margin-left: 0 !important;
        margin-right: auto !important;
        max-width: 75%;
        flex-grow: 0 !important;
    }}

    /* Selectbox dropdown popup: gradient black background, gold-gradient
       text on the selected option, lighter gold on hover */
    div[data-testid="stSelectboxVirtualDropdown"] {{
        background: linear-gradient(135deg, #1A1A1A 0%, #070707 73%) !important;
    }}
    div[role="listbox"] [role="option"] {{
        background: transparent !important;
        color: #c9c9c9;
    }}
    div[role="listbox"] [role="option"]:hover {{
        background: transparent !important;
        color: #F5D370 !important;
    }}
    div[role="listbox"] [role="option"][aria-selected="true"] {{
        background: transparent !important;
    }}
    div[role="listbox"] [role="option"][aria-selected="true"] div {{
        background: {GOLD_SHIMMER};
        background-size: 320px 100%;
        background-repeat: repeat-x;
        animation: bqGoldTextShimmer 5s linear infinite;
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        font-weight: bold;
    }}

    /* Alert boxes: dark, gold-outlined instead of colored fills.
       Bradley Quant's own version of this rule never needed to
       override the text color since it almost never uses st.error()
       - this code does, for network-failure messages specifically,
       so the default Streamlit red was left showing through until
       this fix (confirmed via direct screenshot, not assumed). */
    div[data-testid="stAlertContainer"] {{
        background: rgba(255, 255, 255, 0.04) !important;
        border: 1px solid #5c4608 !important;
    }}
    div[data-testid="stAlertContainer"] p {{
        color: #e8e8e8 !important;
    }}
    div[data-testid="stAlertContainer"] svg {{
        fill: #D4AF37 !important;
    }}

    a {{
        background: {GOLD_SHIMMER};
        background-size: 320px 100%;
        background-repeat: repeat-x;
        animation: bqGoldTextShimmer 5s linear infinite;
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
    }}

    /* Hide the default top toolbar (Deploy button, hamburger menu) */
    header[data-testid="stHeader"] {{
        display: none !important;
    }}
    div[data-testid="stToolbar"] {{
        display: none !important;
    }}
    /* Hide the native "<<" collapse arrow - our custom glowing icon replaces
       it. Uses opacity/position rather than display:none, since display:none
       breaks our JS-triggered .click() on this element. */
    div[data-testid="stSidebarCollapseButton"] {{
        opacity: 0 !important;
        pointer-events: none !important;
        position: absolute !important;
        width: 1px !important;
        height: 1px !important;
        overflow: hidden !important;
    }}

    /* Force expanders (used heavily on the Guide page, uniquely among all
       pages) to mount instantly - Streamlit's own native open/close
       transition applies on initial mount too, and with many expanders
       rendering at once this reads as "the whole page is animated"
       specifically on this page, unlike everywhere else. Scoped to the
       expander's own container only, not its descendants, so button
       hover effects inside expanders still work normally. */
    div[data-testid="stExpander"] {{
        transition: none !important;
        animation: none !important;
    }}
    div[data-testid="stExpander"] > details {{
        transition: none !important;
        animation: none !important;
    }}

    /* Reclaim the vertical space that was reserved for the now-hidden header.
       Also compensates for invisible zero-height elements (the merged
       CSS/SVG markdown block, the components.html JS injection) that
       each still consume a full 16px flexbox gap in the main content
       area, even though they render nothing. */
    div[data-testid="stMainBlockContainer"] {{
        padding-top: 0.1rem !important;
        margin-top: -32px !important;
    }}

    /* Every real st.title() page had ~20px of Streamlit's own default
       padding-top baked into the h1 element itself, which the custom
       Stock Market title (a plain span, no such padding) never had -
       confirmed via direct measurement: identical container top
       position (1.59375px) on every page, but the h1's own text sat
       visibly lower due to this padding, while its line-height also
       differed (52.8px vs the span's 50.6px). Removing the padding and
       matching the line-height makes every title's spacing consistent
       with Stock Market's. */
    div[data-testid="stMainBlockContainer"] h1 {{
        padding-top: 0 !important;
        line-height: 1.15 !important;
    }}
    /* Desktop only: nudges every page title down to sit level with the
       sidebar's own "Bradley Quant" header text specifically (not just
       the first nav item) - removing the h1's default padding above
       fixed spacing consistency between titles, but also shifted every
       title up relative to the sidebar header by that same amount
       (confirmed via direct measurement: 24px). Scoped to desktop only
       so mobile's already-correct spacing is untouched. */
    @media (min-width: 641px) {{
        div[data-testid="stMainBlockContainer"] h1 {{
            margin-top: 24px !important;
        }}
        .bq-stock-header-row {{
            margin-top: 24px !important;
        }}
    }}
    /* Every hand-built field label (the Color: / Team: pickers) sits exactly as far from its control as Streamlit's own
       labels do (Season:, Player: ...): the same 24px label line and 29px from the label's top to the control's top,
       and the same gap above it as between any two fields. */
    div[data-testid="stElementContainer"]:has(.ba-dd-label) {{ margin-bottom: 0 !important; }}
    /* A block that only carries styling (st.markdown("<style>...")) takes no room: without this each one added a
       second 16px gap between the two fields around it, so some fields sat twice as far apart as the rest. */
    div[data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:only-child) {{
        display: none !important;
    }}
    /* Embedded in the website the window is sized to the page, so nothing inside it may scroll - not even by a pixel of
       rounding on a scaled (125%/150%) display. Direct visits (no ?embed=true) keep normal scrolling. */
    html.ba-embed, html.ba-embed body, html.ba-embed [data-testid="stApp"], html.ba-embed [data-testid="stAppViewContainer"],
    html.ba-embed [data-testid="stMain"], html.ba-embed section.main, html.ba-embed [data-testid="stSidebarContent"],
    html.ba-embed [data-testid="stAppScrollToBottomContainer"] {{
        overflow-y: hidden !important;
    }}
    section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"] {{
        padding-top: 0.1rem !important;
        /* Streamlit reserves ~6rem of padding under the sidebar content. That made the sidebar's own content taller than
           the window we size to "just past Glossary", so it grew an inner scrollbar. Only a small margin is kept. */
        padding-bottom: 0.4rem !important;
    }}
    /* The real source of the big sidebar gap: stSidebarHeader (60px) and its
       stLogoSpacer child (32px) reserve space above the content regardless of
       the padding fix above. Shrink both instead of hiding the header
       entirely, since the (invisible) native collapse button lives inside it
       and display:none on an ancestor would break our JS click-forwarding. */
    div[data-testid="stSidebarHeader"] {{
        height: auto !important;
        min-height: 0 !important;
        padding: 4px 0 !important;
    }}
    div[data-testid="stLogoSpacer"] {{
        height: 0 !important;
        min-height: 0 !important;
        width: 0 !important;
    }}

    /* Streamlit's own default layout stretches the sidebar to match
       the full page height regardless of its own content length -
       confirmed directly (a sidebar with 751px of actual nav content
       was being forced to a full 1400px viewport height). This makes
       it size to its own content instead, so there's a normal margin
       below the last nav item ("Glossary") rather than a large empty
       gap filling out the rest of the page. The main content area's
       own adjustable height (tallest of sidebar vs. current page) is
       untouched by this - that logic lives in the AI Search
       container fix elsewhere, not in the sidebar's own sizing. */
    section[data-testid="stSidebar"] {{
        height: fit-content !important;
        min-height: 0 !important;
    }}

    /* The fixed bottom bar that holds the chat input has no data-testid of
       its own - target it via its child instead. Anchored to the viewport
       (background-attachment: fixed) so it shows the correctly-aligned
       continuation of the same gradient as .stApp, instead of each element
       computing its own independent gradient and creating a visible seam. */
    div:has(> div[data-testid="stBottomBlockContainer"]) {{
        background: linear-gradient(135deg, #1A1A1A 0%, #070707 73%) !important;
        background-attachment: fixed !important;
        background-size: 100vw 100vh !important;
    }}

    /* Custom sidebar toggle icon - glow via pure CSS, no inline JS handlers
       (inline onclick/onmouseover HTML attributes crash Streamlit's React
       renderer with a fatal error, so all interactivity here is done via
       addEventListener in the script block below instead) */
    .bq-toggle-icon, #bq-expand-icon {{
        width: 34px;
        height: 34px;
        border-radius: 50%;
        cursor: pointer;
        flex-shrink: 0;
        animation: bqLogoBreathe 2.6s ease-in-out infinite;
        transition: transform 0.5s ease;
    }}
    @keyframes bqLogoBreathe {{
        0%, 100% {{ filter: drop-shadow(0 0 2px rgba(212, 175, 55, 0.35)); }}
        50% {{ filter: drop-shadow(0 0 7px rgba(245, 211, 112, 0.75)); }}
    }}

    /* Shared shimmer for every gradient-gold TEXT element in the
       dashboard (metric numbers, buttons, links, selected states) -
       background-size wider than the text plus a panning
       background-position is what makes a gradient text-fill actually
       move, rather than sitting static. */
    @keyframes bqGoldTextShimmer {{
        from {{ background-position: 0px 0; }}
        to {{ background-position: -320px 0; }}
    }}

    /* Mobile: logo stacks above the "Bradley Quant" title in the sidebar's
       own header, top-left, instead of sitting inline beside it. */
    @media (max-width: 640px) {{
        .bq-sidebar-header {{
            flex-direction: column !important;
            align-items: flex-start !important;
            gap: 4px !important;
        }}
    }}
    /* The title is always two lines, "Bradley" over "Analytics" (desktop and phone). */
    .bq-sidebar-title > span {{ display: block; }}
    /* Every gold line in the sidebar is the same length: the one under the title is as long as the ones between the
       groups of pages, which are as wide as the widest page name (--ba-nav-w, measured by the page; the names never
       wrap, so that width never depends on the sidebar's). Same spacing above and below it as theirs, too. */
    section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(> [data-testid="stRadio"]) {{
        width: max-content !important; max-width: none !important;
    }}
    section[data-testid="stSidebar"] label[data-testid="stRadioOption"] p {{ white-space: nowrap; }}
    .bq-sidebar-rule {{ width: var(--ba-nav-w, 150px); }}
    /* Phones: the open sidebar is only as wide as its widest line (the page names and those gold lines) plus the same
       margin on the right as on the left. */
    @media (max-width: 640px) {{
        section[data-testid="stSidebar"][aria-expanded="true"] {{
            width: calc(var(--ba-nav-w, 150px) + 41px) !important;
            min-width: calc(var(--ba-nav-w, 150px) + 41px) !important;
            max-width: calc(var(--ba-nav-w, 150px) + 41px) !important;
        }}
    }}

    /* Mobile only: the floating logo + "SIDE BAR" button (shown when the
       sidebar is collapsed, which is the default on mobile) sit at a
       fixed position over the top-left of the page content, covering
       whatever's there - confirmed via screenshot overlapping the
       banner and page title. Adds clearance above the main content on
       mobile only; desktop already has the expanded sidebar itself
       providing separation, so this would be an unwanted gap there. */
    @media (max-width: 640px) {{
        div[data-testid="stMainBlockContainer"] {{
            padding-top: 52px !important;
        }}
    }}

    /* Home, phones only: "<- OPEN SIDE BAR TO GET STARTED!" in the strip above the banner, right of the SIDE BAR button */
    .ba-sb-hint {{ display: none; }}
    @media (max-width: 640px) {{
        div[data-testid="stElementContainer"]:has(.ba-sb-hint) {{ margin: 0 !important; }}
        .ba-sb-hint {{
            display: flex; align-items: center; justify-content: center; text-align: center;
            height: 40px; margin: -46px 0 6px 44px; cursor: pointer; -webkit-tap-highlight-color: transparent;
            font-family: Arial, sans-serif; font-weight: bold; font-size: min(1rem, 4.05vw); color: #ffffff;
            letter-spacing: 0.02em; white-space: nowrap;
            animation: baHintBreathe 2.4s ease-in-out infinite;
        }}
        /* the long arrow is drawn (Arial has no long arrow, and the fallback font's sat low): centred on the text */
        .ba-sb-hint .ba-sb-arrow {{ flex: none; width: 2.2em; height: 0.8em; margin-right: 0.45em; overflow: visible;
            animation: baHintArrow 2.4s ease-in-out infinite; }}
        .ba-sb-hint span {{ line-height: 1; }}
    }}
    @keyframes baHintArrow {{
        0%, 100% {{ filter: drop-shadow(0 0 2px rgba(255,255,255,0.25)); }}
        50% {{ filter: drop-shadow(0 0 4px rgba(255,255,255,0.85)) drop-shadow(0 0 9px rgba(255,255,255,0.45)); }}
    }}
    @keyframes baHintBreathe {{
        0%, 100% {{ opacity: 0.72; text-shadow: 0 0 4px rgba(255,255,255,0.25), 0 0 10px rgba(255,255,255,0.12); }}
        50% {{ opacity: 1; text-shadow: 0 0 8px rgba(255,255,255,0.85), 0 0 20px rgba(255,255,255,0.45); }}
    }}

    /* ===== Animations ===== */

    /* #3: verdict badge fades into its color */
    .bq-verdict-badge {{
        display: inline-block;
        animation: bqFadeIn 1.7s ease forwards;
    }}
    @keyframes bqFadeIn {{
        from {{ opacity: 0; }}
        to {{ opacity: 1; }}
    }}

    /* #6: gold shimmer sweeps across the button border on hover */
    div[data-testid="stButton"] button::before, div[data-testid="stFormSubmitButton"] button::before, div[data-testid="stDownloadButton"] button::before {{
        background-size: 200% 100%;
        background-position: 0% 0;
        transition: background-position 1s ease;
    }}
    div[data-testid="stButton"] button:hover::before, div[data-testid="stFormSubmitButton"] button:hover::before, div[data-testid="stDownloadButton"] button:hover::before {{
        background-position: 100% 0;
    }}

    /* #7: metric cards lift on hover */
    div[data-testid="stMetric"] {{
        border-radius: 8px;
        padding: 6px 10px !important;
        transition: transform 0.25s ease, box-shadow 0.25s ease;
    }}
    div[data-testid="stMetric"]:hover {{
        transform: translateY(-4px);
        box-shadow: 0 8px 20px rgba(184, 134, 11, 0.3);
    }}


    /* #8 and #9 were removed: gating the entire main content panel and the
       info card border/title behind opacity:0-until-observed was a real
       risk - if the scroll observer ever failed to fire in some
       rendering context (confirmed happening: a real screenshot showed
       the sidebar rendering fine while the whole main content panel and
       the AI disclaimer's border/title stayed completely invisible),
       there was no fallback. Both are always visible now. */

    /* #10: custom gold-gradient thinking spinner, replacing Streamlit's default */
    div[data-testid="stSpinner"] > div:first-child {{
        border-color: #2a2a2a !important;
        border-top-color: #F5D370 !important;
    }}

    /* #11: chat bubbles slide in from their own side */
    div[data-testid="stChatMessage"] {{
        animation: bqFadeIn 0.4s ease;
    }}
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {{
        animation: bqSlideRight 0.4s ease;
    }}
    div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarAssistant"]) {{
        animation: bqSlideLeft 0.4s ease;
    }}
    @keyframes bqSlideRight {{
        from {{ transform: translateX(30px); opacity: 0; }}
        to {{ transform: translateX(0); opacity: 1; }}
    }}
    @keyframes bqSlideLeft {{
        from {{ transform: translateX(-30px); opacity: 0; }}
        to {{ transform: translateX(0); opacity: 1; }}
    }}

    /* #12: the most extreme verdicts pulse; a plain Hold/middling verdict stays still */
    @keyframes bqPulse {{
        0%, 100% {{ box-shadow: 0 0 0 0 rgba(0, 200, 5, 0.5); }}
        50% {{ box-shadow: 0 0 0 10px rgba(0, 200, 5, 0); }}
    }}
    @keyframes bqPulseRed {{
        0%, 100% {{ box-shadow: 0 0 0 0 rgba(255, 80, 0, 0.5); }}
        50% {{ box-shadow: 0 0 0 10px rgba(255, 80, 0, 0); }}
    }}
    .bq-pulse-buy {{ animation: bqFadeIn 1.7s ease forwards, bqPulse 1.8s ease-in-out infinite 1.7s; }}
    .bq-pulse-sell {{ animation: bqFadeIn 1.7s ease forwards, bqPulseRed 1.8s ease-in-out infinite 1.7s; }}

    /* #1 / #5: every generated chart (bar, line, radar, etc.) grows in -
       scroll-repeat via .bq-inview. Opacity + transform only, never
       clip-path (see #9 note above for why). Excludes the home banner
       (.st-key-home_banner), which should never animate. */
    div[data-testid="stImage"] img {{
        opacity: 0;
        transform: scaleY(0.4);
        transform-origin: bottom center;
        transition: opacity 0.7s cubic-bezier(.2,.8,.3,1), transform 0.7s cubic-bezier(.2,.8,.3,1);
    }}
    div[data-testid="stImage"] img.bq-inview {{
        opacity: 1;
        transform: scaleY(1);
    }}
    .st-key-home_banner img {{
        opacity: 1 !important;
        transform: none !important;
        transition: none !important;
    }}

    /* #6: page-fade overlay fade-out, defined as a pure CSS animation
       (animation-fill-mode: forwards) rather than driven by a JS-toggled
       opacity transition - the browser's own rendering engine is what
       carries this through to completion, so it's guaranteed to finish
       and land the overlay at opacity:0 (invisible, non-interactive via
       pointer-events) regardless of whether any JS in the page is still
       around to orchestrate it. That guarantee is the actual point: an
       element that's ended up invisible and inert by the browser's own
       doing is harmless to leave in the DOM indefinitely, which sidesteps
       needing its *removal* (a JS-timer-dependent step) to be reliable
       at all for correctness - removal is still attempted afterward,
       purely as DOM hygiene, but nothing depends on it succeeding.
       (Direct testing traced the earlier stuck-overlay bug to
       setInterval/setTimeout callbacks silently not firing in this
       nested-iframe context for reasons that didn't turn up under
       inspection - CSS animations aren't subject to whatever that was,
       since the browser's compositor drives them independent of any
       particular JS execution context remaining alive.) */
    @keyframes bqFadeOverlayOut {{
        0% {{ opacity: 1; }}
        55% {{ opacity: 1; }}
        100% {{ opacity: 0; }}
    }}
    .bq-fade-overlay {{
        animation: bqFadeOverlayOut 1.1s ease forwards;
        pointer-events: none;
    }}

    /* #4: sidebar collapses/expands with a smooth slide instead of an
       instant cut. Streamlit's real collapse mechanism changes transform
       (translateX) together with width/max-width, not just width alone. */
    section[data-testid="stSidebar"] {{
        transition: transform 0.35s cubic-bezier(.2,.8,.3,1),
                    width 0.35s cubic-bezier(.2,.8,.3,1),
                    max-width 0.35s cubic-bezier(.2,.8,.3,1),
                    min-width 0.35s cubic-bezier(.2,.8,.3,1) !important;
    }}

    /* #14: current price flashes green on an uptick, red on a downtick */
    @keyframes bqFlashUp {{
        0% {{ color: #00C805; -webkit-text-fill-color: #00C805; }}
        100% {{ color: #F5D370; -webkit-text-fill-color: #F5D370; }}
    }}
    @keyframes bqFlashDown {{
        0% {{ color: #FF5000; -webkit-text-fill-color: #FF5000; }}
        100% {{ color: #F5D370; -webkit-text-fill-color: #F5D370; }}
    }}
    .bq-flash-up {{ animation: bqFlashUp 1.2s ease forwards; }}
    .bq-flash-down {{ animation: bqFlashDown 1.2s ease forwards; }}
</style>
""", unsafe_allow_html=True)

# Also run inside the dashboard page itself (not the page script's little frame, which Streamlit sometimes redraws --
# anything that frame set up then stops working): every chart picture fades/grows in as it scrolls into view
# (.bq-inview), and the code window under RUN waits for the chart's picture to finish loading before it fades in.
_PAGE_WATCH_JS = r"""
(function () {
  if (document.__bqWatch) return;
  document.__bqWatch = true;
  var observers = new WeakMap();
  function observerFor(el) {
    // Streamlit scrolls an inner container: stMain, or stAppScrollToBottomContainer on a page with a chat box
    var root = el.closest('[data-testid="stMain"], [data-testid="stAppScrollToBottomContainer"]');
    if (!root) return null;
    var ob = observers.get(root);
    if (!ob) {
      ob = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { e.target.classList.toggle('bq-inview', e.isIntersecting); });
      }, { root: root, threshold: 0.15 });
      observers.set(root, ob);
    }
    return ob;
  }
  function watchImage(img) {
    var ob = observerFor(img);
    if (ob) ob.observe(img); else img.classList.add('bq-inview');
  }
  function holdCodeWindow(d) {
    if (d.__bqHeld) return;
    d.__bqHeld = true;
    setTimeout(function () {
      var main = document.querySelector('[data-testid="stMain"]') || document;
      var pending = Array.prototype.filter.call(main.querySelectorAll('[data-testid="stImage"] img'), function (im) { return !im.complete; });
      if (!pending.length) return;
      d.classList.add('bq-wait');
      var left = pending.length;
      function done() { left--; if (left <= 0) d.classList.remove('bq-wait'); }
      pending.forEach(function (im) { im.addEventListener('load', done, { once: true }); im.addEventListener('error', done, { once: true }); });
      setTimeout(function () { d.classList.remove('bq-wait'); }, 8000);
    }, 120);
  }
  function scan(root) {
    if (root.matches) {
      if (root.matches('[data-testid="stImage"] img')) watchImage(root);
      if (root.matches('details.bq-codewin')) holdCodeWindow(root);
    }
    root.querySelectorAll('[data-testid="stImage"] img').forEach(watchImage);
    root.querySelectorAll('details.bq-codewin').forEach(holdCodeWindow);
  }
  scan(document);
  new MutationObserver(function (ms) {
    ms.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1) scan(n); }); });
  }).observe(document.body, { childList: true, subtree: true });

  // Stat menus (stat_menus.py): an entry whose text starts with two invisible characters is a section heading -
  // OFFENSE, PLAYMAKING, REBOUNDING, DEFENSE, OVERALL - drawn in bold grey Arial with a thin grey line above it
  // (except the first), and it can't be clicked.
  var HEAD = '\u2063\u2063';
  var css = document.createElement('style');
  css.textContent =
    '[role="option"].ba-opt-head { pointer-events: none !important; cursor: default !important; background: transparent !important;' +
    ' border-top: 1px solid #3a3a3a !important; }' +
    '[role="option"].ba-opt-head.ba-opt-first { border-top-color: transparent !important; }' +
    '[role="option"].ba-opt-head, [role="option"].ba-opt-head * { font-family: Arial, Helvetica, sans-serif !important;' +
    ' font-weight: 700 !important; font-size: 11.5px !important; letter-spacing: .08em !important; color: #8f8f8f !important;' +
    ' -webkit-text-fill-color: #8f8f8f !important; text-transform: uppercase !important; }' +
    '[data-baseweb="tag"]:has(> span[title^="' + HEAD + '"]) { display: none !important; }';
  document.head.appendChild(css);
  var headPending = 0;
  function markHeads() {
    headPending = 0;
    var opts = document.querySelectorAll('[role="option"]');
    for (var i = 0; i < opts.length; i++) {
      var o = opts[i], isHead = (o.textContent || '').indexOf(HEAD) === 0;
      if (isHead !== o.classList.contains('ba-opt-head')) o.classList.toggle('ba-opt-head', isHead);
      if (isHead) {
        o.setAttribute('aria-disabled', 'true');
        var box = o.closest('[role="listbox"]') || o.parentElement;
        var first = !o.previousElementSibling && (!box || box.scrollTop < 4);
        if (first !== o.classList.contains('ba-opt-first')) o.classList.toggle('ba-opt-first', first);
      }
    }
  }
  new MutationObserver(function () {
    if (!headPending) headPending = requestAnimationFrame(markHeads);
  }).observe(document.body, { childList: true, subtree: true, characterData: true });

  // Clicking a table's column header sorts the table by that column: numbers largest to smallest (a second click:
  // smallest to largest), words A to Z. Empty / N/A cells always go last; a Total or End of Bench row keeps its place.
  if (!window.__baThSort) {
    window.__baThSort = true;
    var sortCss = document.createElement('style');
    sortCss.textContent =
      '.ba-roster thead th, .ba-cap thead th, .crit-table thead th, [data-testid="stMarkdownContainer"] table:not(.cba-t) thead th' +
      ' { cursor: pointer; user-select: none; -webkit-user-select: none; }' +
      'th.ba-sort-desc::after { content: " ▾"; } th.ba-sort-asc::after { content: " ▴"; }';
    document.head.appendChild(sortCss);
    var GRADES = { 'A+': 97, 'A': 93, 'A-': 90, 'B+': 87, 'B': 83, 'B-': 80, 'C+': 77, 'C': 73, 'C-': 70,
                   'D+': 67, 'D': 63, 'D-': 60, 'F': 50 };
    var cellValue = function (td) {
      var t = (td ? td.innerText || td.textContent || '' : '').replace(/\s+/g, ' ').trim();
      if (!t || /^(n\/a|-|–|—)$/i.test(t)) return null;
      var m = t.match(/^(\d+)-(\d{1,2})$/);                       // a height, 6-7
      if (m) return +m[1] * 12 + +m[2];
      if (GRADES.hasOwnProperty(t)) return GRADES[t];             // a Potential grade
      m = t.replace(/[$,%\s]/g, '').match(/^([-+]?\d*\.?\d+)([kmb])?$/i);
      if (m) return parseFloat(m[1]) * ({ k: 1e3, m: 1e6, b: 1e9 }[(m[2] || '').toLowerCase()] || 1);
      return t.toLowerCase();
    };
    var colOf = function (row, idx) {                            // the cell under header column idx (colspans counted)
      var x = 0;
      for (var i = 0; i < row.cells.length; i++) {
        var span = row.cells[i].colSpan || 1;
        if (idx < x + span) return span > 1 ? null : row.cells[i];
        x += span;
      }
      return null;
    };
    document.addEventListener('click', function (e) {
      var th = e.target && e.target.closest ? e.target.closest('thead th') : null;
      if (!th) return;
      var table = th.closest('table');
      if (!table || table.classList.contains('cba-t') || !table.tBodies.length) return;
      if (!table.matches('.ba-roster, .ba-cap, .crit-table table, [data-testid="stMarkdownContainer"] table')) return;
      if (!(th.innerText || '').trim()) return;                   // the picture column
      var idx = 0, c = th;
      while ((c = c.previousElementSibling)) idx += c.colSpan || 1;
      // The table on the page belongs to Streamlit (React): moving its rows would get them mixed up the next time it
      // updates the table. So a sorted copy is shown in its place, and the moment Streamlit changes the original (a
      // new season, another display) the copy goes away and the original is back.
      if (!table.__baOrig) {
        var orig = table, copy = orig.cloneNode(true);
        copy.__baOrig = orig;
        orig.style.display = 'none';
        orig.parentNode.insertBefore(copy, orig.nextSibling);
        var holder = orig.parentNode;
        var mo = new MutationObserver(function (recs) {
          var changed = recs.some(function (r) { return r.target !== holder || !orig.isConnected || orig.parentNode !== holder; });
          if (!changed) return;
          mo.disconnect();
          if (copy.parentNode) copy.parentNode.removeChild(copy);
          orig.style.display = '';
        });
        mo.observe(orig, { childList: true, subtree: true, characterData: true });
        mo.observe(holder, { childList: true });                  // (the table itself replaced)
        table = copy;
        th = copy.querySelectorAll('thead th')[Array.prototype.indexOf.call(orig.querySelectorAll('thead th'), th)];
      }
      var body = table.tBodies[0], all = Array.prototype.slice.call(body.rows);
      var pinned = function (r) { return r.classList.contains('tot') || r.classList.contains('eob') || r.querySelector('td[colspan]'); };
      var data = all.filter(function (r) { return !pinned(r); });
      var vals = data.map(function (r) { return cellValue(colOf(r, idx)); });
      var nums = vals.every(function (v) { return v === null || typeof v === 'number'; });
      var asc = nums ? th.classList.contains('ba-sort-desc') : !th.classList.contains('ba-sort-asc');
      var order = data.map(function (r, i) { return i; }).sort(function (a, b) {
        var va = vals[a], vb = vals[b];
        if (va === null || vb === null) return (va === null) - (vb === null) || a - b;
        if (typeof va !== typeof vb) return typeof va === 'number' ? -1 : 1;
        var d = typeof va === 'number' ? va - vb : va.localeCompare(vb);
        return (asc ? d : -d) || a - b;
      });
      // the pinned rows stay where they are; the others fill the remaining places in the new order
      var k = 0;
      var next = all.map(function (r) { return pinned(r) ? r : data[order[k++]]; });
      next.forEach(function (r) { body.appendChild(r); });
      Array.prototype.forEach.call(table.querySelectorAll('thead th'), function (h) { h.classList.remove('ba-sort-asc', 'ba-sort-desc'); });
      th.classList.add(asc ? 'ba-sort-asc' : 'ba-sort-desc');
    }, true);
  }

  // The sidebar's page names are as wide as the widest of them: that width (--ba-nav-w) sizes the gold line under the
  // title and, on a phone, the open sidebar itself.
  function navWidth() {
    var g = document.querySelector('section[data-testid="stSidebar"] [data-testid="stRadio"]');
    if (!g) return;
    var w = g.getBoundingClientRect().width;
    if (w < 60) return;
    var v = w.toFixed(2) + 'px';
    if (document.documentElement.style.getPropertyValue('--ba-nav-w') !== v) document.documentElement.style.setProperty('--ba-nav-w', v);
  }
  var navPending = 0;
  new MutationObserver(function () { if (!navPending) navPending = requestAnimationFrame(function () { navPending = 0; navWidth(); }); })
    .observe(document.body, { childList: true, subtree: true });
  window.addEventListener('resize', navWidth);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(navWidth);
  navWidth();

  // Charts drawn as SVG that should be pictures (the CBA Guide's charts of the chosen team, marked data-ba-img): the page
  // draws each one into a see-through PNG at the size it is shown (so it looks exactly the same, with the reader's own
  // fonts), shows that picture in its place -- it can be saved, dragged or copied like any image -- and puts a
  // "Download .png" button under it. The SVG stays in the page, hidden, so Streamlit can still update it; when it
  // changes (another team), the picture is drawn again.
  var imgCss = document.createElement('style');
  imgCss.textContent =
    'svg.ba-svg-done { display: none !important; }' +
    '.ba-svg-pic img { display: block; width: 100%; height: auto; -webkit-user-drag: element; }' +
    '@keyframes baSvgShimmer { from { background-position: 0px 0; } to { background-position: -320px 0; } }' +
    '.ba-svg-dl { position: relative; display: flex; align-items: center; justify-content: center; width: 100%;' +
    ' box-sizing: border-box; min-height: 2.5rem; margin-top: 14px; padding: .25rem .75rem; border-radius: 10px;' +
    ' background: linear-gradient(135deg,#1A1A1A 0%,#050505 100%); text-decoration: none !important; cursor: pointer;' +
    ' transition: box-shadow .2s ease; animation: none; -webkit-background-clip: border-box; background-clip: border-box; }' +
    '.ba-svg-dl::before { content: ""; position: absolute; inset: 0; border-radius: 10px; padding: 2px;' +
    ' background: linear-gradient(135deg,#B8860B,#F5D370,#B8860B); background-size: 200% 100%; background-position: 0% 0;' +
    ' transition: background-position 1s ease; -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);' +
    ' -webkit-mask-composite: xor; mask-composite: exclude; pointer-events: none; }' +
    '.ba-svg-dl:hover { box-shadow: 0 0 14px 2px rgba(212,175,55,.55); }' +
    '.ba-svg-dl:hover::before { background-position: 100% 0; }' +
    '.ba-svg-dl span { font-family: "Source Sans", "Source Sans Pro", sans-serif; font-size: .875rem; line-height: 1.6;' +
    ' font-weight: bold; background: linear-gradient(90deg,#8a6410 0%,#D4AF37 18%,#FFF0B8 34%,#F5D370 50%,#D4AF37 66%,' +
    '#B8860B 82%,#8a6410 100%); background-size: 320px 100%; background-repeat: repeat-x;' +
    ' animation: baSvgShimmer 5s linear infinite; -webkit-background-clip: text; background-clip: text; color: transparent; }';
  document.head.appendChild(imgCss);
  function svgSig(svg) {
    var t = svg.getAttribute('viewBox') + '|' + svg.innerHTML, h = 5381;
    for (var i = 0; i < t.length; i++) h = ((h << 5) + h + t.charCodeAt(i)) | 0;
    return t.length + ':' + h;
  }
  function drawSvgPicture(svg) {
    var sig = svgSig(svg);
    var pic = svg.nextElementSibling && svg.nextElementSibling.classList &&
              svg.nextElementSibling.classList.contains('ba-svg-pic') ? svg.nextElementSibling : null;
    if (pic && pic.__baSig === sig) return;
    var vb = (svg.getAttribute('viewBox') || '').trim().split(/[\s,]+/).map(Number);
    var vw = vb[2] || 960, vh = vb[3] || 400;
    var shown = (pic && pic.querySelector('img') && pic.querySelector('img').getBoundingClientRect().width) ||
                svg.getBoundingClientRect().width;
    var dispW = shown > 20 ? shown : vw;          // (the hidden phone/desktop copy: its own size)
    var scale = Math.max(2, window.devicePixelRatio || 1);
    var outW = Math.round(dispW * scale), outH = Math.round(dispW * scale * vh / vw);
    var clone = svg.cloneNode(true);
    clone.removeAttribute('class');
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.setAttribute('width', outW);
    clone.setAttribute('height', outH);
    // lines drawn at a fixed on-screen width keep that width in the picture
    clone.querySelectorAll('[vector-effect="non-scaling-stroke"]').forEach(function (el) {
      el.setAttribute('stroke-width', (parseFloat(el.getAttribute('stroke-width') || '1') * scale).toFixed(2));
    });
    var svgUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(clone));
    var name = svg.getAttribute('data-ba-img') || 'bradley-analytics-chart.png';
    var src = new Image();
    src.onload = function () {
      var c = document.createElement('canvas');
      c.width = outW; c.height = outH;
      c.getContext('2d').drawImage(src, 0, 0, outW, outH);
      var url;
      try { url = c.toDataURL('image/png'); } catch (e) { url = svgUrl; }
      if (!svg.isConnected) return;
      var p = svg.nextElementSibling && svg.nextElementSibling.classList &&
              svg.nextElementSibling.classList.contains('ba-svg-pic') ? svg.nextElementSibling : null;
      if (!p) {
        p = document.createElement('div');
        p.className = 'ba-svg-pic';
        p.innerHTML = '<img alt=""><a class="ba-svg-dl"><span>Download .png</span></a>';
        svg.parentNode.insertBefore(p, svg.nextSibling);
      }
      var im = p.querySelector('img');
      im.src = url;
      im.alt = svg.getAttribute('aria-label') || '';
      im.title = svg.getAttribute('aria-label') || '';
      var a = p.querySelector('a');
      a.href = url;
      a.setAttribute('download', url === svgUrl ? name.replace(/\.png$/, '.svg') : name);
      p.__baSig = sig;
      svg.classList.add('ba-svg-done');
    };
    src.src = svgUrl;
  }
  var svgPending = 0;
  function checkSvgPictures() {
    svgPending = 0;
    document.querySelectorAll('svg[data-ba-img]').forEach(drawSvgPicture);
    // a picture whose chart is gone goes too
    document.querySelectorAll('.ba-svg-pic').forEach(function (p) {
      var prev = p.previousElementSibling;
      if (!prev || prev.tagName.toLowerCase() !== 'svg' || !prev.hasAttribute('data-ba-img')) p.remove();
    });
  }
  new MutationObserver(function (ms) {
    for (var i = 0; i < ms.length; i++) {
      var t = ms[i].target;
      if (t && t.closest && t.closest('.ba-svg-pic')) continue;       // (its own picture changing)
      if (!svgPending) svgPending = requestAnimationFrame(checkSvgPictures);
      break;
    }
  }).observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true,
                                attributeFilter: ['d', 'x', 'y', 'cx', 'cy', 'width', 'height', 'fill', 'viewBox', 'points',
                                                  'x1', 'x2', 'y1', 'y2', 'data-ba-img'] });
  checkSvgPictures();

  // Links to a spot further down the same page (e.g. the CBA Guide's list of sections). Inside the website the
  // dashboard never scrolls itself (its window is as tall as the page), so the website is asked to scroll to that spot
  // ("ba-scroll-to", in pixels from the top of the dashboard); opened on its own, the dashboard scrolls to it.
  document.addEventListener('click', function (e) {
    // AI Search's links to a place in the dashboard ("#ba-nav-<button key>"): they press that place's button under the answer
    var nav = e.target.closest && e.target.closest('a[href^="#ba-nav-"]');
    if (nav) {
      e.preventDefault();
      var btn = document.querySelector('.st-key-' + CSS.escape(nav.getAttribute('href').slice(8)) + ' button');
      if (btn) btn.click();
      return;
    }
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (!a || a.getAttribute('href').length < 2) return;
    var spot = document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1)));
    if (!spot) return;
    e.preventDefault();
    if (document.documentElement.classList.contains('ba-embed') && window.top !== window) {
      // (a spot that is itself nudged up above its heading, e.g. top:-70px for the dashboard's own top bar: its heading)
      var y = spot.getBoundingClientRect().top - Math.min(0, parseFloat(spot.style.top) || 0) - document.documentElement.getBoundingClientRect().top;
      try { window.top.postMessage({ type: 'ba-scroll-to', y: Math.max(0, Math.round(y)) }, '*'); } catch (err) {}
    } else {
      spot.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, true);
})();
"""
_PAGE_WATCH_JSON = json.dumps(_PAGE_WATCH_JS).replace("</", "<\\/")

# The website's window around the dashboard is sized to the dashboard's height, which this reports (postMessage
# "ba-resize") whenever anything on the page changes -- also run inside the dashboard page itself, for the same reason.
_HEIGHT_JS = r"""
(function () {
  if (document.__bqHeight) return;
  document.__bqHeight = true;
  function isPinchZoomed() {
      // NOTE: only effective when the dashboard is opened directly. When
      // embedded in the GitHub Pages site (a cross-origin iframe),
      // visualViewport.scale stays 1 inside the frame even while the
      // page is pinch-zoomed (confirmed in a real browser), so this
      // returns false there. The embedding page (docs/index.html) holds
      // height updates itself while zoomed, which is what covers that case.
      // window.visualViewport is the real, purpose-built browser API
      // for this distinction - its scale reflects pinch-zoom level
      // specifically, separate from the page's actual CSS layout
      // size, which getBoundingClientRect() (used by reportHeight
      // below) cannot tell apart on its own. Falls back to "not
      // zoomed" on a browser without this API (very old mobile
      // browsers) rather than blocking height reporting entirely on
      // those.
      const vv = window && window.visualViewport;
      if (!vv) return false;
      return Math.abs(vv.scale - 1) > 0.02;
  }
  // Reports the exact height this page needs to whatever page embeds it, so the embedding page can size its iframe to
  // fit and the dashboard never needs its own scrollbar. The height is the bottom edge of the last thing actually drawn
  // in the page (zero-height helper elements - styles, scripts - are skipped, and Streamlit's own large bottom
  // padding is NOT counted) plus a small fixed margin. On a wide screen it is never less than the sidebar: just past
  // its last item (Glossary). While the sidebar is hidden (phones) only the page content counts.
  // Empty space kept below the last thing on the page (and below Glossary in the sidebar): about one blank line.
  const BOTTOM_MARGIN = 72;
  let lastPostedHeight = -1, lastPostAt = 0;
  function reportHeight() {
      const container = document.querySelector('[data-testid="stMainBlockContainer"]');
      if (!container) return;
      // Zooming in must never resize the iframe - see isPinchZoomed() above.
      if (isPinchZoomed()) return;
      // A page with a chat box (AI Search) scrolls stAppScrollToBottomContainer instead of stMain, and keeps the chat
      // box in a bar stuck to the bottom of the window (stBottom): the page needs room for all of its content AND that bar.
      const main = document.querySelector('[data-testid="stAppScrollToBottomContainer"]') ||
                   document.querySelector('[data-testid="stMain"]') || document.querySelector('section.main');
      const mainTop = main ? main.getBoundingClientRect().top : 0;
      const mainScroll = main ? main.scrollTop : 0;
      const bottomBar = document.querySelector('[data-testid="stBottom"]');
      const bottomBarH = bottomBar ? Math.ceil(bottomBar.getBoundingClientRect().height) : 0;
      const block = container.querySelector('[data-testid="stVerticalBlock"]') || container;
      let contentBottom = 0;
      for (const el of block.children) {
          const r = el.getBoundingClientRect();
          if (r.height > 3 && r.width > 3) contentBottom = Math.max(contentBottom, r.bottom);
      }
      if (!contentBottom) return;          // nothing drawn yet: don't announce a height for an empty, still-loading page
      const mainNeeded = Math.ceil(contentBottom - mainTop + mainScroll) + (bottomBarH ? bottomBarH + 16 : BOTTOM_MARGIN);

      const sidebarSection = document.querySelector('section[data-testid="stSidebar"]');
      const sbRect = sidebarSection ? sidebarSection.getBoundingClientRect() : null;
      const sidebarShowing = !!(sbRect && sbRect.width > 50);
      let sidebarNeeded = 0;
      if (sidebarShowing) {
          const items = sidebarSection.querySelectorAll('label[data-testid="stRadioOption"]');
          if (!items.length) return;       // sidebar list not built yet - wait, so the window doesn't collapse then re-expand on load
          sidebarNeeded = Math.ceil(items[items.length - 1].getBoundingClientRect().bottom - sbRect.top) + BOTTOM_MARGIN;
      }
      const height = Math.max(mainNeeded, sidebarNeeded);
      // The sidebar background stretches to the full window height, so a tall page never leaves an empty gap below Glossary.
      if (sidebarShowing) sidebarSection.style.setProperty('height', height + 'px', 'important');
      // Only re-send when it changed (or every few seconds, so a reloaded embedding page is never left waiting).
      if (Math.abs(height - lastPostedHeight) < 2 && Date.now() - lastPostAt < 4000) return;
      lastPostedHeight = height;
      lastPostAt = Date.now();
      window.top.postMessage({ type: 'ba-resize', height: height }, '*');
  }
  let reportHeightDebounceTimer = null;
  function debouncedReportHeight() {
      if (reportHeightDebounceTimer) clearTimeout(reportHeightDebounceTimer);
      reportHeightDebounceTimer = setTimeout(reportHeight, 60);
  }
  function initHeightReporter() {
      // Embedded in the website (?embed=true), the window is sized to the page, so the page must never scroll inside it. Mark the
      // document so the CSS can switch the scroll containers off; opening the dashboard on its own keeps normal scrolling.
      try {
          if (new URLSearchParams(window.location.search).get('embed') === 'true') document.documentElement.classList.add('ba-embed');
      } catch (e) {}
      // AI Search's chat container keeps itself scrolled to the bottom. Embedded, the window is already sized to the whole
      // page and can't be scrolled by the user, so that pushed the top of the page (its title) up out of sight / under
      // the sidebar button. Resetting it afterwards made the page shake on every click, so embedded, these containers
      // simply can't be scrolled at all: their scroll position is always 0 and scrolling them does nothing.
      if (!window.__baNoInnerScroll && document.documentElement.classList.contains('ba-embed')) {
          window.__baNoInnerScroll = true;
          const freeze = (el) => {
              if (!el || el.__baFrozen) return;
              el.__baFrozen = true;
              try {
                  Object.defineProperty(el, 'scrollTop', { configurable: true, get: () => 0, set: () => {} });
                  Object.defineProperty(el, 'scrollLeft', { configurable: true, get: () => 0, set: () => {} });
                  el.scrollTo = el.scroll = el.scrollBy = function () {};
              } catch (e) {}
              // (anything already scrolled before this ran)
              try { Object.getOwnPropertyDescriptor(Element.prototype, 'scrollTop').set.call(el, 0); } catch (e) {}
          };
          const SEL = '[data-testid="stAppScrollToBottomContainer"], [data-testid="stMain"]';
          let freezePending = 0;
          const freezeAll = () => { freezePending = 0; document.querySelectorAll(SEL).forEach(freeze); };
          freezeAll();
          new MutationObserver(() => { if (!freezePending) freezePending = requestAnimationFrame(freezeAll); })
              .observe(document.body, { childList: true, subtree: true });
          // the browser's own scrolling (e.g. bringing a focused box into view) goes around the above: undone at once
          const nativeTop = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollTop');
          document.addEventListener('scroll', (e) => {
              const t = e.target;
              if (t && t.matches && t.matches(SEL) && nativeTop.get.call(t)) nativeTop.set.call(t, 0);
          }, true);
      }
      const container = document.querySelector('[data-testid="stMainBlockContainer"]');
      const sidebar = document.querySelector('section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"]');
      if (!container) { setTimeout(initHeightReporter, 200); return; }
      const resizeObserver = new ResizeObserver(() => debouncedReportHeight());
      resizeObserver.observe(container);
      if (sidebar) resizeObserver.observe(sidebar);
      // Catches back up once the user zooms back out - reportHeight
      // itself skips while isPinchZoomed() is true, so without this,
      // any real layout change that happened to occur *during* a
      // zoom session (e.g. rotating the phone while zoomed in) would
      // never get reported at all.
      const vv = window && window.visualViewport;
      if (vv) {
          vv.addEventListener('resize', () => { if (!isPinchZoomed()) debouncedReportHeight(); });
      }
      reportHeight();
      // Belt and braces. A chart or image can finish loading without this container's own size event firing (and
      // Streamlit may swap the container element), which once left the window shorter than the page and hid the
      // bottom behind an inner scrollbar. So also re-check on any change to the page, on every image that loads,
      // and twice a second - a re-check is a few cheap measurements, and it only re-sends when the height changed.
      new MutationObserver(() => debouncedReportHeight()).observe(container, { childList: true, subtree: true });
      document.addEventListener('load', () => debouncedReportHeight(), true);
      setInterval(() => { if (!document.hidden) reportHeight(); }, 500);
  }
  initHeightReporter();

  window.__bqReportHeight = reportHeight;
  // which page of the dashboard is showing, for the website (it reopens that page only when the browser reloads it)
  var lastPage = null;
  setInterval(function () {
    var sel = document.querySelector('section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] p');
    var text = sel ? sel.textContent : null;
    if (text && text !== lastPage) {
      lastPage = text;
      try { window.top.postMessage({ type: 'ba-page', page: text }, '*'); } catch (e) {}
      [100, 400, 900, 1600].forEach(function (d) { setTimeout(reportHeight, d); });
    }
  }, 300);
})();
"""
_HEIGHT_JSON = json.dumps(_HEIGHT_JS).replace("</", "<\\/")

# Custom sidebar toggle: a glowing circular icon replaces Streamlit's default
# arrows. Clicking it spins the icon, then programmatically clicks Streamlit's
# real native collapse/expand button underneath -- so the actual show/hide
# logic is Streamlit's own (guaranteed correct), just with fully custom UI.
components.html(rf"""
<script>
// Player search bars: a typed name matches only players whose FIRST or LAST name (or any later part of the name)
// STARTS with it - "lebron" finds LeBron James and nobody else. Player pickers are sent with filter_mode="prefix"
// and an invisible marker (U+2063) on every option label (ui_hooks.py); Streamlit's prefix filter calls
// label.startsWith(typed), so for a MARKED label only, startsWith answers "does any word of the name start with
// this" (accents, periods and apostrophes ignored). Every other string in the page behaves exactly as before.
(function() {{
    try {{
        const SP = window.parent.String.prototype;
        if (SP.startsWith.__baWordPrefix) return;
        const orig = SP.startsWith;
        const MARK = "\u2063";
        const norm = (t) => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
                              .split(MARK).join("").replace(/[.'\u2019`]/g, "");
        const patched = function(search, pos) {{
            const str = String(this);
            if (pos === undefined && typeof search === "string" && str.indexOf(MARK) !== -1) {{
                const hay = norm(str), q = norm(search).replace(/^\s+/, "");
                if (!q) return true;
                if (orig.call(hay, q)) return true;
                for (let i = 1; i < hay.length; i++) {{
                    const c = hay.charAt(i - 1);
                    if ((c === " " || c === "-") && orig.call(hay, q, i)) return true;
                }}
                return false;
            }}
            return orig.apply(this, arguments);
        }};
        patched.__baWordPrefix = true;
        SP.startsWith = patched;
    }} catch (e) {{}}
}})();
// Everything below runs in the app's OWN page (injected there once), not in this little frame: Streamlit remounts
// this frame whenever the page's layout changes (AI Search's chat layout, for one), and the old frame's click handlers
// and timers die with it -- which left the SIDE BAR button and the rest of these helpers dead after visiting AI Search.
(function() {{
    const parentDoc = window.parent.document;
    if (parentDoc.__bqSidebarToggleInit) return;
    parentDoc.__bqSidebarToggleInit = true;
    const s = parentDoc.createElement('script');
    s.textContent = '(' + bqMain.toString() + ')(window);';
    parentDoc.head.appendChild(s);
}})();
function bqMain(PW) {{
    const parentDoc = PW.document;

    try {{
        if (!parentDoc.__bqHeight) {{                    // the website's window: always as tall as the dashboard
            const hs = parentDoc.createElement('script');
            hs.textContent = {_HEIGHT_JSON};
            parentDoc.head.appendChild(hs);
        }}
    }} catch (e) {{}}
    try {{
        if (!parentDoc.__bqWatch) {{                     // charts scrolling into view, the code window's timing
            const ws = parentDoc.createElement('script');
            ws.textContent = {_PAGE_WATCH_JSON};
            parentDoc.head.appendChild(ws);
        }}
    }} catch (e) {{}}

    const ICON_SRC = "data:image/png;base64,{TOGGLE_ICON_B64}";

    const fixedIcon = parentDoc.createElement('img');
    fixedIcon.id = 'bq-expand-icon';
    fixedIcon.src = ICON_SRC;
    fixedIcon.title = 'Show sidebar';
    fixedIcon.className = 'bq-toggle-icon';

    // A small labeled button under the floating logo, shown only when the
    // sidebar is closed (same condition, same visibility toggle as the
    // logo itself) - the logo alone isn't obviously a sidebar toggle to
    // a first-time visitor, so this makes the affordance explicit.
    // Clicking either the logo or this button opens the sidebar; the logo
    // keeps its own spin/breathing animation regardless.
    // The logo and the "SIDE BAR" button are wrapped in one container that
    // acts as a single clickable unit (not just visually adjacent) -
    // clicking anywhere in the wrapper, icon or button, triggers the same
    // expand action. Only one click listener is needed on the wrapper
    // itself rather than checking multiple separate element IDs.
    const toggleWrapper = parentDoc.createElement('div');
    toggleWrapper.id = 'bq-toggle-wrapper';
    toggleWrapper.style.cssText = 'position: fixed; top: 8px; left: 8px; z-index: 999999; display: none; ' +
        'flex-direction: column; align-items: center; gap: 3px; cursor: pointer;';
    toggleWrapper.appendChild(fixedIcon);
    fixedIcon.style.cssText = 'display: block;';

    const sidebarBtn = parentDoc.createElement('div');
    sidebarBtn.id = 'bq-sidebar-btn';
    sidebarBtn.textContent = 'SIDE BAR';
    sidebarBtn.style.cssText = 'margin-top: -9px; padding: 1px 6px; border-radius: 999px; border: 1px solid transparent; ' +
        'background: linear-gradient(135deg, #1a1a1a, #050505) padding-box, ' +
        'linear-gradient(135deg, #B8860B, #F5D370, #B8860B) border-box; ' +
        'color: #ffffff; font-family: Arial, sans-serif; font-weight: bold; font-size: 6px; ' +
        'white-space: nowrap; text-align: center; position: relative; z-index: 1;';
    toggleWrapper.appendChild(sidebarBtn);
    parentDoc.body.appendChild(toggleWrapper);

    function simulateRealClick(el) {{
        const rect = el.getBoundingClientRect();
        const opts = {{ bubbles: true, cancelable: true, view: PW,
                        clientX: rect.x + rect.width / 2, clientY: rect.y + rect.height / 2 }};
        el.dispatchEvent(new PointerEvent('pointerdown', opts));
        el.dispatchEvent(new MouseEvent('mousedown', opts));
        el.dispatchEvent(new PointerEvent('pointerup', opts));
        el.dispatchEvent(new MouseEvent('mouseup', opts));
        el.dispatchEvent(new MouseEvent('click', opts));
    }}

    // ---- Team dropdowns (Front Office/Coaching switcher, Trade Machine teams): an open panel
    // "ba_dd_panel_<id>" closes when someone clicks/taps anywhere outside it (other than its own
    // "ba_dd_toggle_<id>" button, which already toggles it), or clicks the team that's already chosen.
    parentDoc.addEventListener('click', function(e) {{
        if (!e.target || !e.target.closest) return;
        parentDoc.querySelectorAll('[class*="st-key-ba_dd_panel_"]').forEach(function(panel) {{
            const cls = [...panel.classList].find(c => c.indexOf('st-key-ba_dd_panel_') === 0);
            if (!cls) return;
            const id = cls.slice('st-key-ba_dd_panel_'.length);
            const wrap = parentDoc.querySelector('.st-key-ba_dd_toggle_' + CSS.escape(id));
            const btn = wrap && wrap.querySelector('button');
            if (!btn || wrap.contains(e.target)) return;
            const inside = panel.contains(e.target);
            const onCurrent = inside && e.target.closest('label[data-testid="stRadioOption"][data-selected="true"]');
            if (!inside || onCurrent) simulateRealClick(btn);
        }});
    }}, true);

    // ---- The code window under a RUN button: once opened, it closes again when someone clicks (or taps)
    // anywhere outside it. A tap is a touch that barely moved - starting a scroll outside it doesn't close it.
    function closeCodeWindows(target) {{
        if (!target || !target.closest) return;
        parentDoc.querySelectorAll('details.bq-codewin[open]').forEach(function(d) {{
            if (!d.contains(target)) d.open = false;
        }});
    }}
    parentDoc.addEventListener('click', function(e) {{ closeCodeWindows(e.target); }}, true);
    let codeTap = null;
    parentDoc.addEventListener('touchstart', function(e) {{
        const t = e.touches && e.touches[0];
        codeTap = t ? {{ x: t.clientX, y: t.clientY }} : null;
    }}, {{ capture: true, passive: true }});
    parentDoc.addEventListener('touchend', function(e) {{
        const t = e.changedTouches && e.changedTouches[0];
        if (codeTap && t && Math.abs(t.clientX - codeTap.x) < 10 && Math.abs(t.clientY - codeTap.y) < 10) closeCodeWindows(e.target);
        codeTap = null;
    }}, {{ capture: true, passive: true }});

    // ---- Phones and tablets: smoother dropdowns and text boxes -------------------------------------
    const touchDevice = ('ontouchstart' in PW) || (PW.navigator.maxTouchPoints || 0) > 0;
    if (touchDevice) {{
        const nav = PW.navigator;
        // iPhone/iPad zoom the page in whenever a text box smaller than 16px gets focus (the "semi-zoom"
        // on every dropdown tap). Text boxes are 16px here on touch screens, and on iOS the page is
        // also told not to auto-zoom (pinch-to-zoom still works there).
        const mobileCss = parentDoc.createElement('style');
        mobileCss.textContent =
            '@media (pointer: coarse) {{' +
            '  [data-testid="stSelectbox"] input, [data-testid="stMultiSelect"] input, [data-testid="stTextInput"] input,' +
            '  [data-testid="stNumberInput"] input, [data-testid="stTextArea"] textarea, [data-testid="stChatInput"] textarea' +
            '  {{ font-size: 16px !important; }}' +
            '  button, label, a, [role="option"], [role="combobox"], [data-testid="stSelectbox"], [data-testid="stMultiSelect"]' +
            '  {{ touch-action: manipulation; }}' +
            '}}';
        parentDoc.head.appendChild(mobileCss);
        const isIOS = /iPad|iPhone|iPod/.test(nav.userAgent) || (nav.platform === 'MacIntel' && nav.maxTouchPoints > 1);
        if (isIOS) {{
            let vp = parentDoc.querySelector('meta[name="viewport"]');
            if (!vp) {{ vp = parentDoc.createElement('meta'); vp.name = 'viewport'; parentDoc.head.appendChild(vp); }}
            vp.content = 'width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover';
        }}

        const BOX = '[data-testid="stSelectbox"], [data-testid="stMultiSelect"]';
        const MENU = '[data-testid="stSelectboxVirtualDropdown"], [data-testid="stMultiSelectDropdown"], [role="listbox"]';
        const typeable = (el) => el && el.tagName === 'INPUT' && !el.readOnly && el.getAttribute('inputmode') !== 'none';

        // One tap on a search box opens the list AND the keyboard. (On a phone the first tap used to only
        // open the list - the list appearing under the finger swallowed the tap, so the box never got
        // focus - and a second tap was needed to type.) Focusing inside the touch itself is what lets
        // the phone raise its keyboard.
        parentDoc.addEventListener('touchend', function(e) {{
            const box = e.target && e.target.closest && e.target.closest(BOX);
            if (!box) return;
            const input = box.querySelector('input');
            if (typeable(input) && parentDoc.activeElement !== input && !e.target.closest('[aria-label="Clear value"]')) {{
                input.focus({{ preventScroll: true }});
            }}
        }}, {{ capture: true, passive: true }});

        // Tapping anywhere outside an open dropdown (or its text box) closes it and puts the keyboard away.
        parentDoc.addEventListener('touchstart', function(e) {{
            const t = e.target;
            if (!t || !t.closest) return;
            const active = parentDoc.activeElement;
            const inBox = active && active.closest && active.closest(BOX);
            const textBox = active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA');
            if (!inBox && !textBox) return;
            if (t.closest(BOX) || t.closest(MENU) || t === active) return;
            active.blur();
        }}, {{ capture: true, passive: true }});

        // Picking an option (tap, or typing a name and pressing Enter/Go) closes the list and the keyboard.
        const closeAfterPick = function() {{
            setTimeout(function() {{
                const a = parentDoc.activeElement;
                if (a && a.closest && a.closest(BOX)) a.blur();
            }}, 60);
        }};
        parentDoc.addEventListener('click', function(e) {{
            if (e.target && e.target.closest && e.target.closest('[role="option"]')) closeAfterPick();
        }}, true);
        parentDoc.addEventListener('keydown', function(e) {{
            if (e.key === 'Enter' && e.target && e.target.closest && e.target.closest(BOX)) closeAfterPick();
        }}, true);
    }}

    function toggleSidebar(iconEl, action) {{
        if (action === 'collapse') {{
            // Position the fixed icon exactly where the sidebar icon
            // currently sits, so it visually "stays put" as the sidebar
            // disappears rather than jumping to a different spot.
            const rect = iconEl.getBoundingClientRect();
            fixedIcon.style.top = rect.top + 'px';
            fixedIcon.style.left = rect.left + 'px';
        }}
        iconEl.style.transform = action === 'collapse' ? 'rotate(-360deg)' : 'rotate(360deg)';
        setTimeout(() => {{
            iconEl.style.transform = 'rotate(0deg)';
            const selector = action === 'collapse'
                ? '[data-testid="stSidebarCollapseButton"] button'
                : '[data-testid="stExpandSidebarButton"]';
            const btn = parentDoc.querySelector(selector);
            if (btn) simulateRealClick(btn);
        }}, 350);
    }}

    // Event delegation on the PARENT document, in the CAPTURE phase -
    // Streamlit's own radio option component calls stopPropagation() on
    // its click handling (confirmed via direct testing: an identical
    // listener in the bubble phase never fires at all for radio label
    // clicks, while the same listener in the capture phase does), so
    // bubble-phase delegation silently misses these clicks entirely.
    parentDoc.addEventListener('click', function(e) {{
        PW.__bqTopTrace = PW.__bqTopTrace || [];
        PW.__bqTopTrace.push({{targetTag: e.target.tagName, targetId: e.target.id}});
        if (e.target && e.target.id === 'bq-collapse-icon') {{
            toggleSidebar(e.target, 'collapse');
        }} else if (e.target && (e.target.closest('#bq-toggle-wrapper') || e.target.closest('.ba-sb-hint'))) {{
            toggleSidebar(fixedIcon, 'expand');
        }} else if (e.target) {{
            // Mobile only: auto-close the sidebar after selecting a
            // category, so the user doesn't have to manually collapse it
            // every time to see the page they just navigated to.
            const radioLabel = e.target.closest('label[data-testid="stRadioOption"]');
            if (radioLabel && radioLabel.closest('[data-testid="stSidebar"]') && PW.innerWidth <= 640) {{
                // Calls Streamlit's native collapse button directly and
                // synchronously, bypassing toggleSidebar() entirely -
                // that helper has its own internal 350ms delay for a
                // rotation animation that isn't even visible here anyway
                // (the icon is hidden while the sidebar is open), and
                // confirmed via tracing that ANY delay here, whether
                // from this code or from toggleSidebar's own internal
                // timer, never fires: the radio click immediately
                // triggers a Streamlit rerun that recreates this iframe,
                // destroying pending timers before they can run. A
                // synchronous, same-tick call has no such window.
                const nativeBtn = parentDoc.querySelector('[data-testid="stSidebarCollapseButton"] button');
                if (nativeBtn) simulateRealClick(nativeBtn);
            }}
        }}
    }}, true);

    function watchSidebar() {{
        const sidebar = parentDoc.querySelector('[data-testid="stSidebar"]');
        if (!sidebar) {{ setTimeout(watchSidebar, 300); return; }}
        const update = () => {{
            const expanded = sidebar.getAttribute('aria-expanded') === 'true';
            toggleWrapper.style.display = expanded ? 'none' : 'flex';
        }};
        update();
        new MutationObserver(update).observe(sidebar, {{ attributes: true, attributeFilter: ['aria-expanded'] }});
    }}
    watchSidebar();

    // Finds the actual text node holding a metric's number. The animation
    // below edits THAT node's nodeValue in place and never replaces any
    // element or node: an earlier version assigned el.textContent on the
    // stMetricValue wrapper, which deleted the child element Streamlit's
    // React tree owns and swapped in a bare text node - from then on React
    // updated the detached original, so a metric that changed value (e.g.
    // Stat Formula Creator's rating after picking a different season or
    // player) kept showing its first number while everything around it
    // updated. Editing the node React already holds keeps its later
    // updates visible.
    function metricTextNode(el) {{
        const walker = parentDoc.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        let n;
        while ((n = walker.nextNode())) {{
            if (n.nodeValue && n.nodeValue.trim()) return n;
        }}
        return null;
    }}

    // #2: animate a metric counting up from 0 to its real value,
    // preserving whatever prefix/suffix formatting Streamlit gave it
    // ($, %, commas, decimals). Called for a metric when it first appears
    // AND whenever React later changes its text, so a new value counts up
    // too. Text this function wrote itself is remembered (el.__bqWritten)
    // and skipped, so the mutation observer below never re-triggers on our
    // own frames.
    function animateMetric(el) {{
        const node = metricTextNode(el);
        if (!node) return;
        const raw = node.nodeValue;
        if (el.__bqWritten === raw) return;
        const match = raw.match(/-?[\d,]+\.?\d*/);
        const target = match ? parseFloat(match[0].replace(/,/g, '')) : NaN;
        if (!match || isNaN(target)) {{ el.__bqWritten = raw; return; }}
        const prefix = raw.slice(0, match.index);
        const suffix = raw.slice(match.index + match[0].length);
        const decimals = (match[0].split('.')[1] || '').length;
        const hasComma = match[0].includes(',');
        const token = (el.__bqToken = (el.__bqToken || 0) + 1);
        const start = performance.now();
        const duration = 2000;
        let last = raw;
        function write(text) {{
            last = text;
            el.__bqWritten = text;
            node.nodeValue = text;
        }}
        function frame(now) {{
            // A newer value took over, or React changed the text under us
            // (the observer restarts the animation for that new value).
            if (el.__bqToken !== token || node.nodeValue !== last) return;
            const p = Math.min(1, (now - start) / duration);
            const eased = 1 - Math.pow(1 - p, 3);
            const val = target * eased;
            const formatted = hasComma
                ? val.toLocaleString(undefined, {{ minimumFractionDigits: decimals, maximumFractionDigits: decimals }})
                : val.toFixed(decimals);
            if (p < 1) {{
                write(prefix + formatted + suffix);
                requestAnimationFrame(frame);
            }} else {{
                write(raw);
            }}
        }}
        requestAnimationFrame(frame);
        // Guarantees the exact correct final text even if the last RAF
        // frame gets skipped or delayed for any reason (confirmed
        // happening: settled value was off by one, e.g. "24+" instead of
        // "25+"). Only acts if this animation is still the current one and
        // nobody else has changed the text since.
        setTimeout(() => {{
            if (el.__bqToken === token && node.nodeValue === last && last !== raw) write(raw);
        }}, duration + 50);
    }}
    function scanMetrics(root) {{
        root.querySelectorAll('[data-testid="stMetricValue"]').forEach(animateMetric);
    }}
    scanMetrics(parentDoc);

    // Range slider fill: confirmed via direct DOM inspection that
    // BaseWeb's slider has no separate "filled segment between the two
    // handles" element at all - just a full-width track and two
    // independently-positioned handles. A static CSS selector can't
    // express "gold between two dynamic positions, grey outside them",
    // so this computes the gradient in JS from the handles' own live
    // left% and applies it directly to the track background.
    function updateSliderGradient(sliderEl) {{
        const track = sliderEl.querySelector('[role="group"] > div > div:first-child');
        const handles = sliderEl.querySelectorAll('[role="group"] > div > div[style*="left"]');
        if (!track || handles.length < 2) return;
        const positions = Array.from(handles).map(h => parseFloat(h.style.left)).filter(n => !isNaN(n));
        if (positions.length < 2) return;
        const lo = Math.min(...positions);
        const hi = Math.max(...positions);
        track.style.setProperty('background',
            `linear-gradient(to right, #3a3a3a 0%, #3a3a3a ${{lo}}%, #B8860B ${{lo}}%, #F5D370 ${{(lo+hi)/2}}%, #B8860B ${{hi}}%, #3a3a3a ${{hi}}%, #3a3a3a 100%)`,
            'important');
    }}
    function scanSliders(root) {{
        root.querySelectorAll('[data-testid="stSlider"]').forEach(updateSliderGradient);
    }}
    scanSliders(parentDoc);
    // Handle positions change continuously while dragging - listen on
    // the whole document so this fires regardless of which slider (or
    // how many) are on the current page.
    parentDoc.addEventListener('mousemove', () => scanSliders(parentDoc));
    parentDoc.addEventListener('touchmove', () => scanSliders(parentDoc));
    parentDoc.addEventListener('mouseup', () => scanSliders(parentDoc));

    // Checkbox color is handled in pure CSS below (label[data-selected]
    // targeting) - no JS polling needed for this one.

    // #1/#5/#8/#9: scroll-repeat - charts toggle .bq-inview every time they enter or leave view, so scrolling away
    // and back replays the animation. That watcher runs in the dashboard page itself (_PAGE_WATCH_JS, added above).

    // Reports this page's actual content height to whatever page is
    // embedding it (the GitHub Pages site) via postMessage, so that page
    // can resize its iframe to exactly fit the current section instead
    // of using one fixed height for every page. Sent to window.top so it
    // reaches the outermost page regardless of nesting depth.
    // Streamlit's sidebar is user-resizable by dragging its right edge,
    // and that resized width persists locally for whoever dragged it -
    // this locks it so the width in the CSS above (matching Bradley
    // Quant's own default) can never be changed by anyone, confirmed
    // via a real drag-and-release test that this actually prevents the
    // resize rather than just hiding a cursor hint.
    function lockSidebarWidth() {{
        const sidebar = parentDoc.querySelector('section[data-testid="stSidebar"]');
        if (!sidebar) return;
        sidebar.querySelectorAll('*').forEach((el) => {{
            if (getComputedStyle(el).cursor === 'col-resize') {{
                el.style.setProperty('pointer-events', 'none', 'important');
                el.style.setProperty('cursor', 'default', 'important');
            }}
        }});
    }}
    lockSidebarWidth();
    // A separate, permanent interval (not subject to the 300-tick
    // limit below, which is fine for cosmetic fixes but would let this
    // lock lapse after ~2 minutes if the resize handle element gets
    // recreated by a later Streamlit rerun - every widget interaction
    // triggers one).
    setInterval(lockSidebarWidth, 1000);

    // (The height reporter - which keeps the website's window exactly as tall as the dashboard - runs in the dashboard
    // page itself: _HEIGHT_JS, added above. Run from this little frame it stopped whenever Streamlit redrew the frame,
    // and the window's height froze.)

    // Category switches (clicking a different sidebar item) re-render the
    // whole main content area over several ticks - images, fonts, and any
    // freshly-generated chart can each settle a little after the initial
    // DOM swap. ResizeObserver alone can catch most of that, but a
    // switch-triggered burst of re-checks (rather than relying only on
    // whatever resize events happen to fire) makes sure the iframe never
    // gets stuck reporting an in-between height from mid-render. Watches
    // the same radio group's selected option instead of aria-expanded,
    // since that's what actually changes on a category switch.
    function watchCategorySwitch() {{
        const sidebar = parentDoc.querySelector('section[data-testid="stSidebar"]');
        if (!sidebar) {{ setTimeout(watchCategorySwitch, 300); return; }}
        let lastSelected = null;
        const checkSwitch = () => {{
            const selected = sidebar.querySelector('label[data-testid="stRadioOption"][data-selected="true"] p');
            const text = selected ? selected.textContent : null;
            if (text !== lastSelected) {{
                lastSelected = text;

                // Re-plays the page fade-in on every switch, including
                // repeat visits to an already-seen page. Directly setting
                // stMainBlockContainer's own opacity (even via
                // setProperty(..., 'important')) was confirmed, through
                // direct testing, to have no visible effect whatsoever -
                // something about that specific element resists it for
                // reasons that didn't turn up under inspection. This
                // sidesteps that entirely with a same-color overlay laid
                // directly on top of the content, which fades itself out
                // instead, rather than depending on that element's own
                // opacity ever actually changing.
                const freshContainer = parentDoc.querySelector('[data-testid="stMainBlockContainer"]');
                if (freshContainer) {{
                    // Removes any overlay left over from a previous switch
                    // first - if the component iframe this script itself
                    // runs in gets torn down and recreated by Streamlit's
                    // own re-render (plausible, since this whole script
                    // reruns each time), any setTimeout scheduled by the
                    // *previous* instance to remove its own overlay is
                    // lost with it. The overlay itself survives, though,
                    // since it was appended to the parent document, not
                    // the iframe's own - so without this cleanup, a
                    // stranded overlay could sit there permanently.
                    parentDoc.querySelectorAll('[data-bq-fade-overlay]').forEach((el) => el.remove());

                    const rect = freshContainer.getBoundingClientRect();
                    const overlay = parentDoc.createElement('div');
                    overlay.setAttribute('data-bq-fade-overlay', '1');
                    overlay.className = 'bq-fade-overlay';
                    // Measured at switch time, before the new page's
                    // content has actually rendered - so this rect still
                    // reflects the *previous* page's height. Padded
                    // generously below (extra 800px) since a taller new
                    // page is the only direction this can go wrong in.
                    // Opacity/animation itself comes from the
                    // .bq-fade-overlay CSS class (see the stylesheet
                    // above) rather than being toggled here in JS.
                    overlay.style.cssText = `
                        position: fixed; left: ${{rect.left}}px; top: ${{rect.top}}px;
                        width: ${{rect.width}}px; height: ${{rect.height + 800}}px;
                        background: #0d0d0d; z-index: 9999;
                    `;
                    parentDoc.body.appendChild(overlay);
                    // Best-effort DOM cleanup only - correctness no
                    // longer depends on this actually firing, since the
                    // CSS animation above already guarantees the overlay
                    // lands at opacity:0 (invisible, inert) on its own.
                    parentDoc.defaultView.setTimeout(() => overlay.remove(), 1150);
                }}
            }}
        }};
        new MutationObserver(checkSwitch).observe(sidebar, {{ subtree: true, attributes: true, attributeFilter: ['data-selected'] }});
    }}
    watchCategorySwitch();

    // Dollar-amount fields: strip "$" out of the label text and show it as
    // a real prefix INSIDE the left edge of the box instead.
    function fixDollarLabels(root) {{
        root.querySelectorAll('[data-testid="stNumberInput"]').forEach((widget) => {{
            const labelP = widget.querySelector('[data-testid="stWidgetLabel"] p');
            const inputContainer = widget.querySelector('[data-testid="stNumberInputContainer"]');
            const input = widget.querySelector('[data-testid="stNumberInputField"]');
            if (!labelP || !inputContainer || !input) return;

            const hasDollarInLabel = labelP.textContent.includes('$');
            const wasMarkedDollar = widget.dataset.bqIsDollarField === '1';
            if (!hasDollarInLabel && !wasMarkedDollar) return;

            if (hasDollarInLabel) {{
                widget.dataset.bqIsDollarField = '1';
                labelP.textContent = labelP.textContent
                    .replace(/\s*\([^)]*\$[^)]*\)/g, '')
                    .replace(/\$/g, '')
                    .trim();
            }}

            // Idempotent by actual DOM state, not a flag - a flag set
            // before confirming the append actually succeeded permanently
            // blocked every retry on a silent failure (Streamlit briefly
            // replacing the container mid-operation, confirmed happening).
            if (inputContainer.querySelector('.bq-dollar-prefix')) return;
            inputContainer.style.position = 'relative';
            input.style.paddingLeft = '24px';
            const dollarSpan = parentDoc.createElement('span');
            dollarSpan.className = 'bq-dollar-prefix';
            dollarSpan.textContent = '$';
            dollarSpan.style.cssText = 'position:absolute; left:12px; top:50%; ' +
                'transform:translateY(calc(-50% - 1.5px)); color:#f0f0f0; font:14px "Source Sans", sans-serif; ' +
                'pointer-events:none; z-index:2;';
            inputContainer.appendChild(dollarSpan);
        }});
    }}
    fixDollarLabels(parentDoc);

    // Percent fields: position "%" right after the digits, measuring the
    // actual rendered text width (fixed positions don't work since values
    // like "6.00" and "100.00" have very different widths).
    const bqMeasureCanvas = parentDoc.createElement('canvas');
    const bqMeasureCtx = bqMeasureCanvas.getContext('2d');
    function measureTextWidth(text, font) {{
        bqMeasureCtx.font = font;
        return bqMeasureCtx.measureText(text).width;
    }}
    function positionPercentSuffix(input, suffixSpan) {{
        const font = getComputedStyle(input).font || '16px sans-serif';
        const width = measureTextWidth(input.value || '0', font);
        const inputPaddingLeft = parseFloat(getComputedStyle(input).paddingLeft) || 12;
        suffixSpan.style.left = (inputPaddingLeft + width + 3) + 'px';
    }}
    function fixPercentSuffixes(root) {{
        root.querySelectorAll('.bq-pct-marker').forEach((marker) => {{
            const key = marker.getAttribute('data-target-key');
            const container = parentDoc.querySelector('.st-key-' + key);
            if (!container) return;
            const input = container.querySelector('[data-testid="stNumberInputField"]');
            const numInputContainer = container.querySelector('[data-testid="stNumberInputContainer"]');
            if (!input || !numInputContainer) return;
            if (numInputContainer.querySelector('.bq-pct-suffix')) return;
            input.style.paddingRight = '30px';
            const suffixSpan = parentDoc.createElement('span');
            suffixSpan.className = 'bq-pct-suffix';
            suffixSpan.textContent = '%';
            suffixSpan.style.cssText = 'position:absolute; top:50%; transform:translateY(calc(-50% - 1.5px)); ' +
                'color:#f0f0f0; font:14px "Source Sans", sans-serif; pointer-events:none; z-index:2;';
            numInputContainer.style.position = 'relative';
            numInputContainer.appendChild(suffixSpan);
            positionPercentSuffix(input, suffixSpan);
            if (!input.dataset.bqPctListenerAttached) {{
                input.dataset.bqPctListenerAttached = '1';
                input.addEventListener('input', () => positionPercentSuffix(input, suffixSpan));
            }}
        }});
    }}
    fixPercentSuffixes(parentDoc);

    // Thousands-separator commas ($7000.00 -> $7,000.00). native
    // type="number" inputs reject any value containing commas outright,
    // so commas can never be written into the real input directly. Uses a
    // display-only overlay showing the comma-formatted text instead: the
    // real input's own text is made transparent while the overlay shows
    // on top; focusing the field swaps back to the real, plain-digit text
    // so editing is never disrupted by commas appearing mid-edit.
    function formatWithCommas(value) {{
        const parts = value.split('.');
        parts[0] = parts[0].replace(/\B(?=(\d{{3}})+(?!\d))/g, ',');
        return parts.join('.');
    }}
    function addCommaFormatting(input) {{
        if (input.dataset.bqCommaSetup) return;
        input.dataset.bqCommaSetup = '1';
        const overlay = parentDoc.createElement('div');
        overlay.className = 'bq-comma-overlay';
        const cs = getComputedStyle(input);
        overlay.style.cssText = 'position:absolute; top:0; left:0; width:100%; height:100%; ' +
            'pointer-events:none; color:' + cs.color + '; font:' + cs.font + '; ' +
            'padding-top:' + cs.paddingTop + '; padding-right:' + cs.paddingRight + '; ' +
            'padding-bottom:' + cs.paddingBottom + '; padding-left:' + cs.paddingLeft + '; ' +
            'box-sizing:' + cs.boxSizing + '; line-height:' + cs.lineHeight + '; ' +
            'display:block; white-space:nowrap; text-align:' + cs.textAlign + '; z-index:1;';
        const parent = input.parentElement;
        if (getComputedStyle(parent).position === 'static') parent.style.position = 'relative';
        parent.insertBefore(overlay, input);
        function showFormatted() {{
            overlay.textContent = formatWithCommas(input.value || '0');
            overlay.style.visibility = 'visible';
            input.style.setProperty('color', 'transparent', 'important');
        }}
        function showRaw() {{
            overlay.style.visibility = 'hidden';
            input.style.removeProperty('color');
        }}
        input.addEventListener('focus', showRaw);
        input.addEventListener('blur', showFormatted);
        if (parentDoc.activeElement !== input) showFormatted();
        else showRaw();
    }}
    function addCommaFormattingToAll(root) {{
        root.querySelectorAll('[data-testid="stNumberInputField"]').forEach(addCommaFormatting);
    }}
    addCommaFormattingToAll(parentDoc);

    let bqScanCount = 0;
    const bqScanInterval = setInterval(() => {{
        fixDollarLabels(parentDoc);
        fixPercentSuffixes(parentDoc);
        addCommaFormattingToAll(parentDoc);
        scanSliders(parentDoc);
        bqScanCount++;
        if (bqScanCount > 300) clearInterval(bqScanInterval);
    }}, 400);

    new MutationObserver((mutations) => {{
        for (const m of mutations) {{
            // React updating a metric's number in place (same element, new
            // text): a characterData change on its text node, or a swapped
            // text node inside it. Re-animate for the new value.
            if (m.type === 'characterData') {{
                const host = m.target.parentElement && m.target.parentElement.closest('[data-testid="stMetricValue"]');
                if (host) animateMetric(host);
                continue;
            }}
            m.addedNodes.forEach((node) => {{
                if (node.nodeType === 3) {{
                    const host = node.parentElement && node.parentElement.closest('[data-testid="stMetricValue"]');
                    if (host) animateMetric(host);
                    return;
                }}
                if (node.nodeType !== 1) return;
                if (node.matches && node.matches('[data-testid="stMetricValue"]')) animateMetric(node);
                if (node.querySelectorAll) scanMetrics(node);
                if (node.matches && node.matches('[data-testid="stSlider"]')) updateSliderGradient(node);
                if (node.querySelectorAll) scanSliders(node);
                if (node.matches && node.matches('[data-testid="stNumberInput"]')) fixDollarLabels(node.parentElement || parentDoc);
                if (node.querySelectorAll) fixDollarLabels(node);
                if (node.querySelectorAll) fixPercentSuffixes(node);
                if (node.querySelectorAll) addCommaFormattingToAll(node);
            }});
        }}
    }}).observe(parentDoc.body, {{ childList: true, subtree: true, characterData: true }});
}}
</script>
""", height=0)



def info_card(title: str, body: str):
    """
    Replaces st.info()/st.warning() with a titled, gradient-gold-bordered
    card matching the site's feature-card style, instead of Streamlit's
    default flat blue/olive fill boxes.
    """
    body_clean = " ".join(body.split())  # collapse newlines/indentation into flowing text
    st.markdown(f"""
    <div class="bq-info-card">
      <div class="bq-info-card-title">{title}</div>
      <div class="bq-info-card-body">{body_clean}</div>
    </div>
""", unsafe_allow_html=True)


@st.cache_data
def _strip_accents(s):
    """
    Strips diacritics (accents) from a string -- shared by
    _load_all_players (so typing "jokic" matches "Nikola Jokić" in the
    player search) and the Passing Connections receiver-name lookup
    (so a reformatted "Nikola Jokić" still matches the now-accent-
    stripped PLAYER_NAME_TO_RECORD keys).
    """
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _fold_accents(s):
    """Uncached accent-stripper for bulk use (whole DataFrame columns)."""
    return "".join(c for c in unicodedata.normalize("NFD", str(s)) if unicodedata.category(c) != "Mn")


def _rows_for_player(df, picked_name, name_col="PLAYER_NAME"):
    """
    Rows of an NBA stats table belonging to a player picked from
    ALL_PLAYER_NAMES. Those names have accents stripped (so typing
    "jokic" finds Jokić), but the API's own PLAYER_NAME column keeps
    them ("Nikola Jokić") -- a plain == therefore never matched any of
    the ~24 active players with an accented name, and the Stat Formula
    Creator / Advanced Stats reported "No data found" for them.
    """
    if df is None or name_col not in df.columns:
        return df.iloc[0:0] if df is not None else pd.DataFrame()
    return df[df[name_col].map(_fold_accents) == picked_name]


def _load_all_players():
    """
    Every player, once, cached -- rebuilding this 5,103-entry list and
    lookup dict from scratch on every single script rerun (Streamlit
    reruns the whole script on every widget interaction) would be
    wasteful; this only actually runs once per session.

    Names are stripped of diacritics (accents) here -- confirmed via
    direct testing that Streamlit's selectbox search filters against
    the actual displayed option text, not a separate raw value, so a
    format_func showing the accented name while keeping an unaccented
    raw value doesn't help: searching "jokic" still returns no
    results against a displayed "Nikola Jokić". Verified this
    introduces zero new name collisions beyond the ones that already
    exist in the raw NBA data (e.g. two different real players both
    named "Dee Brown").
    """
    all_players = players.get_players()
    names = sorted(_strip_accents(p["full_name"]) for p in all_players)
    by_name = {_strip_accents(p["full_name"]): p for p in all_players}
    return names, by_name


ALL_PLAYER_NAMES, PLAYER_NAME_TO_RECORD = _load_all_players()


@st.cache_data
def _load_all_teams():
    all_teams = teams.get_teams()
    # Sorted by the team's actual name (nickname, e.g. "Celtics",
    # "Lakers"), not the city it's prefixed with in full_name --
    # explicitly requested, since sorting by full_name alphabetizes by
    # city first.
    names = [t["full_name"] for t in sorted(all_teams, key=lambda t: t["nickname"])]
    by_name = {t["full_name"]: t for t in all_teams}
    return names, by_name


ALL_TEAM_NAMES, TEAM_NAME_TO_RECORD = _load_all_teams()
# Reverse lookup (e.g. "BOS" -> "Boston Celtics") -- needed to convert
# PlayerCareerStats' TEAM_ABBREVIATION into the full team name the
# color dropdown's own options are keyed by.
TEAM_ABBREVIATION_TO_NAME = {t["abbreviation"]: t["full_name"] for t in teams.get_teams()}


st.sidebar.markdown(f"""
<div class="bq-sidebar-header" style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
  <img id="bq-collapse-icon" src="data:image/png;base64,{TOGGLE_ICON_B64}" title="Hide sidebar"
       class="bq-toggle-icon">
  <span class="bq-sidebar-title" style="font-family:'Playfair Display', serif; font-weight:500; font-size:1.75rem; color:#ffffff; line-height:1.0;"><span>Bradley</span> <span>Analytics</span></span>
</div>
<div class="bq-sidebar-rule" style="height:1px; background:{GOLD_GRADIENT}; margin:0 0 11px;"></div>
""", unsafe_allow_html=True)
# Applies any pending programmatic navigation (from nav_to(), called on
# a later page) before the radio widget instantiates -- confirmed via
# direct testing that Streamlit blocks ANY assignment to a
# widget-backed session_state key once that widget already exists in
# the current run, even immediately followed by st.rerun(). The fix is
# a separate variable, applied here, strictly before instantiation.
# Every visit starts on Home: a brand-new session ignores the ?page= in its URL. (The page writes the open section
# into its own URL, and a browser can bring that URL back -- going back to the website, reopening a tab, a phone
# restoring a page -- which used to reopen the dashboard wherever it was left instead of on Home.)
_fresh_session = "_ba_session" not in st.session_state
st.session_state["_ba_session"] = True
if _fresh_session:
    st.session_state.pop("category_radio", None)
if st.session_state.get("pending_nav_target"):
    st.session_state["category_radio"] = st.session_state.pop("pending_nav_target")
elif "category_radio" not in st.session_state and not _fresh_session and st.query_params.get("page") in CATEGORIES:
    # Mitigates a documented, currently-open Streamlit framework bug
    # (github.com/streamlit/streamlit/issues/12016): any resize event,
    # including pinch-zoom on mobile, can reset the sidebar radio's own
    # session_state back to its default (the first category, "Home"),
    # which looks exactly like the app redirecting to the home page
    # while someone is just trying to zoom in on a chart. A URL query
    # param survives that reset (it lives in the URL, not component
    # state), so it's used here to restore the actual current page
    # instead of silently falling back to Home.
    st.session_state["category_radio"] = st.query_params["page"]
category = st.sidebar.radio("Category", CATEGORIES, label_visibility="collapsed", key="category_radio")
if st.query_params.get("page") != category:
    st.query_params["page"] = category


def nav_to(target_category: str):
    st.session_state["pending_nav_target"] = target_category
    # Streamlit doesn't allow modifying a widget's session_state value
    # after that widget has already been instantiated in the same
    # script run (confirmed via direct testing -- the sidebar radio is
    # instantiated near the top of this file, so calling nav_to() from
    # any page below it needs a rerun to actually take effect, rather
    # than raising StreamlitAPIException).
    st.rerun()


def nav_to_id(nav_id: str):
    """Looks up a short nav id and jumps there -- kept for interface
    parity with Bradley Quant, unused here since this project has no
    Guide/glossary-link-to-tool feature yet."""
    nav_to(nav_id)


def _salary_files_stamp():
    """When data/salary_table.xlsx and data/salaries.csv last changed -- part of the cache key below, so uploading a
    new spreadsheet to GitHub shows up on the site as soon as the new file lands, without waiting for a restart."""
    stamp = []
    for p in (salary_table.XLSX, salary_table.CSV):
        try:
            stamp.append((os.path.getmtime(p), os.path.getsize(p)))
        except OSError:
            stamp.append(None)
    return tuple(stamp)


@st.cache_data(show_spinner=False)
def _salary_tables(stamp):
    """(every filled-in cell of the salary spreadsheet, the app-wide per-player-per-season salary table)."""
    table = salary_table.read_table()
    return table, salary_table.to_salary_data(table)


def _load_salary_data():
    """
    Salaries for every page (Trade Machine, Search by Criteria's Salary filter, AI Search trades): read from
    data/salary_table.xlsx, the spreadsheet filled in by hand (one row per player, one column per season, plus a status
    column per season). Columns: PLAYER_NAME, SEASON, SALARY, STATUS, TEAM, PLAYER_ID, YEARS_REMAINING -- one row per
    player per season, under each spelling of his name (the sheet's, the NBA's accented one, an accent-free one) so
    exact-name lookups find him. data/salaries.csv fills in anything the sheet doesn't have yet.
    """
    try:
        return _salary_tables(_salary_files_stamp())[1].copy()
    except Exception:
        return pd.DataFrame(columns=salary_table.DATA_COLUMNS)


def _load_salary_table():
    """Every filled-in salary/status cell of data/salary_table.xlsx (for Front Office > Salary Cap)."""
    try:
        return _salary_tables(_salary_files_stamp())[0].copy()
    except Exception:
        return pd.DataFrame(columns=salary_table.TABLE_COLUMNS)


@st.cache_data
def _load_draft_picks_data():
    """Same approach as salaries -- an embedded, user-fillable template CSV."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "draft_picks.csv")
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=["TEAM", "PICK"])


def _salary_season_for(season):
    """The season whose salaries go with `season`'s stats: that season -- except that from July 1 (the new league
    year) the latest season's stats are paired with the new season's contracts, which are the current ones."""
    cap = _cap_season()
    # (once the new season is in the dropdowns itself, each season simply goes with its own contracts)
    return cap if season == _stats_config.default_season() and cap > season and cap not in ALL_SEASONS else season


def _stats_with_salary(season, mode="player"):
    """
    The season stats table plus SALARY in $ millions: a player's cap hit for the salary season (see
    _salary_season_for), or a team's payroll -- every cap hit on its roster (including $0 camp deals) plus its dead
    money. Rosters are the NBA's current ones for the current league year, else who played for the team that season.
    """
    sal_season = _salary_season_for(season)
    base = get_team_stats(season, per_mode="Totals") if mode == "team" else get_player_stats(season, per_mode="Totals")
    base = base.copy()
    table = _load_salary_table()
    t = table[(table["SEASON"] == sal_season) & table["SALARY"].notna()] if not table.empty else table
    if mode != "team":
        data = _load_salary_data()
        d = data[data["SEASON"] == sal_season] if not data.empty else data
        by_id = {int(i): v for i, v in zip(d["PLAYER_ID"], d["SALARY"]) if pd.notna(i)}
        by_name = dict(zip(d["PLAYER_NAME"], d["SALARY"]))
        vals = []
        for pid, nm in zip(base.get("PLAYER_ID", pd.Series([None] * len(base))),
                           base.get("PLAYER_NAME", pd.Series([None] * len(base)))):
            v = by_id.get(int(pid)) if pd.notna(pid) else None
            if v is None:
                v = by_name.get(nm)
            vals.append(v / 1_000_000 if v is not None else None)
        base["SALARY"] = vals
        return base
    # team payroll
    team_of = {}
    if sal_season == _cap_season():
        try:
            team_of = get_current_player_teams()
        except Exception:
            team_of = {}
    if not team_of:
        try:
            ps = get_player_stats(season, per_mode="Totals")
            team_of = {int(p): int(tm) for p, tm in zip(ps["PLAYER_ID"], ps["TEAM_ID"]) if pd.notna(p) and pd.notna(tm)}
        except Exception:
            team_of = {}
    abbr_to_id = {rec["abbreviation"]: rec["id"] for rec in TEAM_NAME_TO_RECORD.values()}
    name_to_id = {}
    for rec in PLAYER_NAME_TO_RECORD.values():
        name_to_id[salary_table.name_key(rec["full_name"])] = rec["id"]
    payroll = {}
    for x in t.itertuples(index=False):
        amount = float(x.SALARY)
        if x.STATUS == "Dead money":
            tid = abbr_to_id.get(str(x.TEAM or "").upper())
        else:
            pid = salary_table._player_id(x.PLAYER_ID) or name_to_id.get(salary_table.name_key(x.PLAYER))
            tid = team_of.get(int(pid)) if pid else None
        if tid:
            payroll[int(tid)] = payroll.get(int(tid), 0.0) + amount
    base["SALARY"] = [payroll[int(tid)] / 1_000_000 if pd.notna(tid) and int(tid) in payroll else None
                      for tid in base.get("TEAM_ID", pd.Series([None] * len(base)))]
    return base


def _player_image_url(pid, name=None):
    """A player's picture addresses by id -- or, for a player nba_api doesn't know yet (a new rookie in the Bradley
    Ratings), 2kratings' picture by his name."""
    if pid is not None and pd.notna(pid):
        return get_player_headshot_url(int(pid))
    from teams import twok_headshot_urls, IMAGE_SEP
    return IMAGE_SEP.join(twok_headshot_urls(str(name))) if name else None


def _ratings_stat(kind, column):
    """A Bradley Ratings / Tendencies column as the dashboard's (field, label, source, modes) stat tuple."""
    return (column, column, ratings_data.SOURCE_OF[kind], ("player",))


def _ratings_season_ok(stats, season):
    """False (after a short note) when a Bradley rating / tendency is asked for in a season they don't cover."""
    if any(s and ratings_data.is_source(s[2]) for s in stats) and not ratings_data.available(season):
        st.warning(f"Bradley Ratings and Tendencies are for {' and '.join(sorted(ratings_data.SEASONS))} - pick one "
                   "of those seasons.")
        return False
    return True


def measurement_picker(key, mode, title="Measurement:", include_salary=True, value_field=None, stat_label="Stat:"):
    """Search by Player's "Measurement:" -- one of a stat, a Bradley rating or a tendency, picked from three menus on
    one line ("Stat:", "Bradley rating:", "Tendency:", a third of the width each on a computer; stacked on a phone).
    Picking in one empties the other two. Returns the pick as a (field, label, source, modes) stat tuple. In Search by
    Team it is just the "Stat:" menu, as before."""
    items, by_label = stat_menus.stat_items(mode, include_salary=include_salary)
    start = next((lbl for lbl, s in by_label.items() if s[0] == value_field), None) if value_field else None
    start = start or next((v for v, _sec in items), None)
    if mode != "player":
        return by_label.get(stat_menus.select(stat_label, items, key=f"{key}_{mode}", value=start))
    keys = {"stat": f"{key}_{mode}", "rating": f"{key}_br_{mode}", "tend": f"{key}_td_{mode}"}

    def only(which):
        def cb():
            if st.session_state.get(keys[which]) is None:
                return
            for other, k in keys.items():
                if other != which:
                    st.session_state[k] = None
        return cb

    # "Measurement:" in the same grey bold label style as "Stat:" under it
    st.markdown(f'<div class="ba-measure-label" style="font-size:0.875rem; font-weight:bold; color:#888888; '
                f'line-height:1.6; margin:0 0 -2px 0;">{html_escape(title)}</div>', unsafe_allow_html=True)
    with st.container(key=f"ba_measure_{key}"):
        c1, c2, c3 = st.columns(3, gap="small")
        with c1:
            stat_lbl = stat_menus.select_optional(stat_label, items, keys["stat"], value=start, placeholder="Choose a stat",
                                                  on_change=only("stat"))
        with c2:
            br = stat_menus.select_optional("Bradley rating:", [(c, None) for c in ratings_data.columns(ratings_data.RATINGS)],
                                            keys["rating"], placeholder="Choose a rating", on_change=only("rating"))
        with c3:
            td = stat_menus.select_optional("Tendency:", [(c, None) for c in ratings_data.columns(ratings_data.TENDENCIES)],
                                            keys["tend"], placeholder="Choose a tendency", on_change=only("tend"))
    if br:
        return _ratings_stat(ratings_data.RATINGS, br)
    if td:
        return _ratings_stat(ratings_data.TENDENCIES, td)
    return by_label.get(stat_lbl) or by_label.get(start)


def fetch_stats_for_source(source: str, season: str, mode: str = "player", per_mode: str = None) -> pd.DataFrame:
    """
    Every axis-graph chart branch (Bar Chart, Histogram, Density Plot,
    etc.) needs to fetch the right underlying stats table before it can
    look up a specific stat_field in it -- base/advanced/bio/calculated
    stats all live together in get_player_stats()'s one combined table,
    but defense/hustle/clutch stats come from separate NBA endpoints
    entirely (see nba_data.py). Centralizing that dispatch here once,
    rather than repeating the same if/elif in all 7 branches, is what
    keeps them from silently drifting out of sync with each other as
    new stat sources get added.

    mode="team" switches base/advanced/calculated stats over to
    get_team_stats() instead -- these charts previously always called
    get_player_stats() regardless of mode, meaning Search by Team's
    Bar Chart, Scatter Plot, Histogram, and the rest of this family
    were silently showing player data even when the user had picked
    Team mode. defense_tracking/hustle/clutch have no team-level
    equivalent in this app (stats_config.py already marks them
    player-only), so those are unaffected by mode either way.
    """
    if ratings_data.is_source(source):
        # the Bradley Ratings / Tendencies spreadsheets (players only; 2025-26 and 2026-27)
        if mode != "player" or not ratings_data.available(season):
            return pd.DataFrame(columns=["PLAYER_ID", "PLAYER_NAME"])
        return ratings_data.league_frame(ratings_data.kind_of_source(source))
    if source == "salary":
        return _stats_with_salary(season, mode)
    if source == "defense_tracking":
        return get_player_defense_stats(season)
    elif source == "hustle":
        return get_player_hustle_stats(season)
    elif source == "clutch":
        return get_player_clutch_stats(season)
    else:
        # get_player_stats() defaults to per_mode="Totals" -- Trade
        # Machine and On/Off Stats already explicitly override this to
        # "PerGame" at their own call sites, but this central dispatch
        # never did, meaning every chart that goes through it (Bar
        # Chart, Histogram, Scatter Plot, Box Plot, and the rest of the
        # axis-graph family) was silently showing season totals the
        # whole time, despite Bar Chart's own UI labeling them "per
        # game". "calculated" stats (PPS, FT_RATE, FG3A_RATE) are
        # ratios of two raw counts, so per-game scaling cancels out of
        # them mathematically either way -- kept on Totals since bio
        # and bradley_rating genuinely aren't per-game numbers
        # (height, draft position, a composite rating).
        # (the page's Per Game / Per 36 / Totals choice, when given, for every stat it applies to)
        per_mode = "Totals" if source in ("bio", "calculated", "bradley_rating") else (per_mode or "PerGame")
        if mode == "team":
            return get_team_stats(season, per_mode=per_mode)
        return get_player_stats(season, per_mode=per_mode)


def _community_backup_notice():
    """After a share is posted: say plainly if it will NOT survive the app sleeping or rebooting."""
    err = community_storage.last_push_error()
    if err:
        st.warning(f"Posted, but it could not be backed up to GitHub ({err}), so it will be lost the next time the app sleeps or reboots.")
    elif community_storage.github_persistence_status().startswith("Not permanent"):
        st.caption("Note: shares are not permanent yet (no GitHub backup is set up), so this will disappear when the app sleeps or reboots.")


def offer_share_to_community(fig, source_section: str, widget_key: str):
    """
    A button (same style as RUN) that reveals a name/description form
    on click, then publishes to Community Uploads on submit -- replaces
    an earlier always-open expander design. One reusable function so
    every chart-generating section gets identical behavior.
    """
    show_key = f"{widget_key}_show_form"
    with st.container(key=f"no_icon_{widget_key}_share"):
        share_clicked = st.button("Share to the \"Community Uploads\" page", key=f"{widget_key}_share_btn", use_container_width=True)
    if share_clicked:
        st.session_state[show_key] = True

    if st.session_state.get(show_key):
        share_name = st.text_input("Your name:", key=f"{widget_key}_share_name")
        share_desc = st.text_area("Description:", key=f"{widget_key}_share_desc")
        if st.button("Post", key=f"{widget_key}_post_btn"):
            if not share_name.strip():
                st.warning("Enter your name first.")
            else:
                community_storage.save_visualization(fig, share_name.strip(), share_desc.strip(), source_section)
                st.success("Posted to Community Uploads.")
                _community_backup_notice()
                st.session_state[show_key] = False


_CODE_KEYWORDS = {"def", "return", "if", "elif", "else", "for", "in", "not", "and", "or", "is", "None", "True", "False",
                  "with", "as", "try", "except", "finally", "import", "from", "lambda", "while", "break", "continue",
                  "yield", "raise", "class", "pass", "global", "nonlocal", "assert", "del"}


def _highlight_python(source):
    """Real source code as HTML lines, coloured like an editor (gold keywords, warm strings, grey comments)."""
    import io as _io
    import keyword
    import tokenize
    import html as _html
    lines = source.splitlines()
    marks = {}
    try:
        prev_def = False
        for tok in tokenize.generate_tokens(_io.StringIO(source).readline):
            kind, text, (r0, c0), (r1, c1) = tok.type, tok.string, tok.start, tok.end
            cls = None
            if kind == tokenize.NAME and (keyword.iskeyword(text) or text in _CODE_KEYWORDS):
                cls = "k"
            elif kind == tokenize.NAME and prev_def:
                cls = "f"
            elif kind == tokenize.STRING:
                cls = "s"
            elif kind == tokenize.COMMENT:
                cls = "c"
            elif kind == tokenize.NUMBER:
                cls = "n"
            if kind == tokenize.NAME:
                prev_def = text in ("def", "class")
            if cls:
                for r in range(r0, r1 + 1):
                    start = c0 if r == r0 else 0
                    end = c1 if r == r1 else len(lines[r - 1]) if r - 1 < len(lines) else 0
                    marks.setdefault(r, []).append((start, end, cls))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # (a snippet cut off mid-statement can't be tokenized: colour it line by line instead)
        marks = {}
        pat = re.compile(r"(#.*$)|(\"[^\"]*\"|'[^']*')|\b(\d+(?:\.\d+)?)\b|\b([A-Za-z_]\w*)\b")
        for i, line in enumerate(lines, 1):
            prev_def = False
            for m in pat.finditer(line):
                cls = None
                if m.group(1):
                    cls = "c"
                elif m.group(2):
                    cls = "s"
                elif m.group(3):
                    cls = "n"
                elif m.group(4) in _CODE_KEYWORDS or keyword.iskeyword(m.group(4) or ""):
                    cls = "k"
                elif prev_def:
                    cls = "f"
                prev_def = m.group(4) in ("def", "class")
                if cls:
                    marks.setdefault(i, []).append((m.start(), m.end(), cls))
    out = []
    for i, line in enumerate(lines, 1):
        spans = sorted(marks.get(i, []))
        pos, parts = 0, []
        for start, end, cls in spans:
            if start < pos:
                continue
            parts.append(_html.escape(line[pos:start]))
            parts.append(f'<span class="{cls}">{_html.escape(line[start:end])}</span>')
            pos = end
        parts.append(_html.escape(line[pos:]))
        out.append("".join(parts) or "&nbsp;")
    return out


def _has_source(f):
    import inspect
    try:
        inspect.getsource(f)
        return True
    except (OSError, TypeError):
        return False


# What the loading box types out: just the code -- docstrings and the code's own comments are taken out -- with a short
# "# ..." note here and there saying what the next few lines do.
_TYPING_NOTES = [
    (r"plt\.subplots|new_court_figure|plt\.figure\(|^fig\s*=", "set up the figure"),
    (r"requests\.get|read_csv|read_excel|\.get_data_frames\(|_fetch_[a-z_]*\(|"
     r"\bget_(player|team|league|shot|shots|game|season|lineup|play|box|assist|draft|schedule|hustle|clutch)[a-z_]*\(",
     "load the data"),
    (r"\.merge\(|pd\.concat\(", "combine the tables"),
    (r"\.groupby\(|\.agg\(|\.pivot_table\(|\.value_counts\(", "add up the numbers"),
    (r"\.sort_values\(|\.nlargest\(|\.nsmallest\(|\bsorted\(", "sort"),
    (r"draw_court\(", "draw the court"),
    (r"\bax\.(bar|barh|scatter|plot|hexbin|fill|fill_between|hist|boxplot|violinplot|pie|imshow|contourf?)\(", "draw the data"),
    (r"OffsetImage\(|AnnotationBbox\(", "add the pictures"),
    (r"\bax\.(text|annotate)\(", "label the chart"),
    (r"set_xlabel\(|set_ylabel\(|set_title\(|suptitle\(", "axis titles"),
    (r"\.spines|tick_params\(|set_xticks\(|set_yticks\(|\.axis\(", "clean up the axes"),
    (r"^for\s", "go through each one"),
    (r"^return\b", "hand back the result"),
]


def _code_for_typing(source):
    """`source` without its docstrings or comments, plus an occasional short "# ..." note above a section (each note at
    most once per function, never two within four lines of each other). Falls back to the plain source if it can't be
    parsed."""
    import ast
    import io as _io
    import tokenize
    import textwrap
    src = textwrap.dedent(source)
    lines = src.splitlines()
    drop = set()
    try:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and node.body:
                first = node.body[0]
                if (isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant)
                        and isinstance(first.value.value, str)):
                    drop.update(range(first.lineno - 1, (first.end_lineno or first.lineno)))
        cut = {}
        for tok in tokenize.generate_tokens(_io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                cut[tok.start[0] - 1] = min(cut.get(tok.start[0] - 1, 10 ** 6), tok.start[1])
    except (SyntaxError, tokenize.TokenError, IndentationError, ValueError):
        return src
    kept = []
    for i, ln in enumerate(lines):
        if i in drop:
            continue
        if i in cut:
            ln = ln[:cut[i]].rstrip()
            if not ln.strip():
                continue
        if not ln.strip() and (not kept or not kept[-1].strip()):
            continue                                   # no double blank lines
        kept.append(ln.rstrip())
    while kept and not kept[-1].strip():
        kept.pop()
    # which kept lines start a statement (a note never goes in the middle of one)
    text = "\n".join(kept)
    starts = set()
    try:
        prev_end = None
        for tok in tokenize.generate_tokens(_io.StringIO(text + "\n").readline):
            if tok.type in (tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING):
                continue
            if tok.type == tokenize.NEWLINE:
                prev_end = tok.start[0]
                continue
            if prev_end is None or tok.start[0] > prev_end:
                starts.add(tok.start[0] - 1)
                prev_end = 10 ** 9
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text
    out, used, last_note = [], set(), -10
    for i, ln in enumerate(kept):
        body = ln.strip()
        if i in starts and body and not body.startswith(("def ", "async def ", "class ", "@")) and i - last_note >= 4:
            for pattern, note in _TYPING_NOTES:
                if note not in used and re.search(pattern, body):
                    out.append(ln[:len(ln) - len(ln.lstrip())] + "# " + note)
                    used.add(note)
                    last_note = i
                    break
        out.append(ln)
        if body.startswith(("def ", "async def ")):
            used = set()                                # each function gets its own notes
    return "\n".join(out)


def _loading_source(code, label):
    """The real Python behind this step: the given function(s), else one of the app's own chart builders."""
    import inspect
    import textwrap
    import visuals as _visuals
    funcs = [c for c in (code if isinstance(code, (list, tuple)) else [code]) if c is not None] if code else []
    funcs = [getattr(f, "__wrapped__", f) for f in funcs]
    funcs = [f for f in funcs if _has_source(f)]
    if not funcs:
        # the app's own function that best matches what this step says it is doing ("Downloading every shot in the
        # league" -> get_league_shots), from its data loaders and chart builders
        import nba_data as _nba_data
        pool = [f for mod, prefix in ((_nba_data, "get_"), (_visuals, "build_"))
                for n, f in inspect.getmembers(mod, inspect.isfunction)
                if n.startswith(prefix) and f.__module__ == mod.__name__]
        pool.sort(key=lambda f: f.__name__)
        words = {w.rstrip("s") for w in re.findall(r"[a-z]+", label.lower()) if len(w) > 3}
        words -= {"downloading", "download", "every", "this", "season", "with", "from", "data", "drawing", "league"}

        def score(f):
            parts = {p.rstrip("s") for p in f.__name__.lower().split("_")}
            return len(words & parts)
        if pool:
            best = max(score(f) for f in pool)
            fits = [f for f in pool if score(f) == best] if best > 0 else [f for f in pool if f.__name__.startswith("build_")]
            first = fits[sum(map(ord, label)) % len(fits)]
            # enough code to scroll through: the best match, then the next-best ones, until there are ~60 lines
            rest = sorted((f for f in pool if f is not first), key=lambda f: (-score(f), f.__name__.startswith("get_"),
                                                                              (sum(map(ord, f.__name__ + label)) % 97)))
            funcs, total = [first], len(_code_for_typing(inspect.getsource(first)).splitlines())
            for f in rest:
                if total >= 60:
                    break
                funcs.append(f)
                total += len(_code_for_typing(inspect.getsource(f)).splitlines())
    chunks = []
    for f in funcs:
        try:
            chunks.append(_code_for_typing(textwrap.dedent(inspect.getsource(f))))
        except (OSError, TypeError):
            continue
    text = "\n\n".join(c.rstrip("\n") for c in chunks if c.strip()).strip("\n")
    lines = text.splitlines()
    if len(lines) > 140:                       # a very long builder: its first 140 lines are plenty to scroll through
        text = "\n".join(lines[:140])
    return text or "import pandas as pd\nimport matplotlib.pyplot as plt"


_LOADING_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
@property --bq-pct { syntax: '<integer>'; initial-value: 0; inherits: false; }
@keyframes bq-code-scroll { from { transform: translateY(0); } to { transform: translateY(-50%); } }
@keyframes bq-load { 0% { width: 0%; --bq-pct: 0; } 8% { width: 30%; --bq-pct: 30; } 25% { width: 58%; --bq-pct: 58; }
  50% { width: 78%; --bq-pct: 78; } 75% { width: 90%; --bq-pct: 90; } 100% { width: 97%; --bq-pct: 97; } }
.bq-code-loading-box { background: linear-gradient(135deg, #1A1A1A 0%, #050505 100%); border: 1px solid #2a2a2a;
  border-radius: 10px; padding: 12px 14px 12px; margin: 8px 0; font-family: 'Roboto', Arial, sans-serif; }
/* a finished box waiting for its chart goes away with it; should nothing follow, it folds away by itself */
.bq-code-loading-box.bq-code-done { animation: bqLoaderGone .3s ease 6s forwards; }
@keyframes bqLoaderGone { to { opacity: 0; max-height: 0; margin: 0; padding: 0; border-width: 0; overflow: hidden; } }
.bq-code-loading-label { color: #D4AF37; font-size: 0.82rem; margin-bottom: 8px; font-weight: 500;
  font-family: 'Roboto', Arial, sans-serif; }
.bq-code-window { position: relative; height: 188px; overflow: hidden;
  -webkit-mask-image: linear-gradient(180deg, transparent 0, #000 14%, #000 86%, transparent 100%);
          mask-image: linear-gradient(180deg, transparent 0, #000 14%, #000 86%, transparent 100%); }
.bq-code-roll { font-size: 0.74rem; line-height: 1.55; will-change: transform; }
.bq-code-roll .cl { margin: 0; padding: 0; font-family: 'Roboto', Arial, sans-serif; font-size: 1em;
  line-height: 1.55; height: 1.55em; color: #c9c4b8; white-space: pre; overflow: hidden; text-overflow: clip; }
.bq-code-roll .ct { display: inline-block; vertical-align: top; clip-path: inset(0 100% 0 0); }
.bq-code-roll .cw { position: relative; display: inline-block; vertical-align: top; }
.bq-code-roll .cu { position: absolute; top: 0.12em; left: 0; width: 0; height: 1.3em; opacity: 0; pointer-events: none; }
.bq-code-roll .cu::after { content: ""; position: absolute; left: 1px; top: 0; width: 2px; height: 100%; background: #F5D370;
  box-shadow: 0 0 6px rgba(245, 211, 112, 0.7); animation: bq-caret-blink 0.9s steps(1, end) infinite; }
@keyframes bq-caret-blink { 0% { opacity: 1; } 50% { opacity: 0; } 100% { opacity: 1; } }
.bq-code-done .cu { display: none; }
.bq-code-roll .ln { display: inline-block; width: 2.6em; color: #4d4a42; text-align: right; margin-right: 1.1em;
  user-select: none; }
.bq-code-roll .k { color: #D4AF37; font-weight: 600; }
.bq-code-roll .f { color: #F5D370; }
.bq-code-roll .s { color: #d9c9a0; }
.bq-code-roll .c { color: #6f6a62; font-style: italic; }
.bq-code-roll .n { color: #e8c77a; }
.bq-code-bar-row { display: flex; align-items: center; gap: 10px; margin-top: 10px; }
.bq-code-progress-track { flex: 1; height: 6px; border-radius: 3px; background: #2a2a2a; overflow: hidden; }
.bq-code-progress-fill { height: 100%; width: 0%; border-radius: 3px;
  background: linear-gradient(90deg, #8a6410 0%, #D4AF37 30%, #FFF0B8 55%, #F5D370 75%, #B8860B 100%);
  animation: bq-load 16s cubic-bezier(.25,.8,.3,1) forwards; }
.bq-code-pct { min-width: 3.2em; text-align: right; color: #F5D370; font-size: 0.78rem; font-weight: 600;
  font-family: 'Roboto', Arial, sans-serif; font-variant-numeric: tabular-nums; }
.bq-code-pct::after { counter-reset: bqp var(--bq-pct); content: counter(bqp) "%"; animation: bq-load 16s
  cubic-bezier(.25,.8,.3,1) forwards; }
.bq-code-done .bq-code-progress-fill { animation: none; width: 100%; }
.bq-code-done .bq-code-pct::after { animation: none; content: "100%"; }
</style>
"""


def _typing_animation_css(plain_lines, chars_per_sec=42.0, keep_row=7):
    """
    CSS that types the loading box's code out rapidly, one line after another (each line revealed character by
    character with a stepped clip), while the code window scrolls so the line being typed stays in view. The whole
    sequence loops if the step is still running when the last line is done. Pure CSS -- Streamlit's markdown can't run
    scripts. Returns (the <style> block, the inline style for the scrolling roll, the id its rules use).
    """
    import uuid as _uuid
    uid = _uuid.uuid4().hex[:8]
    n = max(len(plain_lines), 1)
    total_chars = sum(len(ln.rstrip()) for ln in plain_lines)
    cps = max(chars_per_sec, total_chars / 90.0)              # the whole thing types in at most ~90 s
    starts, durs, t = [], [], 0.0
    for ln in plain_lines:
        d = max(0.05, len(ln.rstrip()) / cps)
        starts.append(t)
        durs.append(d)
        t += d
    period = t + 1.2                                          # a short pause on the finished code before it loops
    pct = lambda x: f"{100.0 * x / period:.3f}%"              # noqa: E731
    rules = []
    for i, (st0, d, ln) in enumerate(zip(starts, durs, plain_lines), 1):
        steps = max(1, len(ln.rstrip())) + 4                   # + the line number, revealed first
        rules.append(f"@keyframes bqt{uid}_{i}{{0%,{pct(st0)}{{clip-path:inset(0 100% 0 0);"
                     f"animation-timing-function:steps({steps},end)}}{pct(st0 + d)},100%{{clip-path:inset(0 0 0 0)}}}}"
                     f".bqr{uid} .t{i}{{animation:bqt{uid}_{i} {period:.2f}s infinite}}")
        # the blinking "|" rides along the line as it's typed (same steps as the reveal), then moves to the next line;
        # after the last line it stays there, blinking, until the code starts over
        last = i == len(plain_lines)
        before = max(0.0, st0 - 0.001)
        rules.append(f"@keyframes bqu{uid}_{i}{{0%,{pct(before)}{{left:0;opacity:0}}"
                     f"{pct(st0)}{{left:0;opacity:1;animation-timing-function:steps({steps},end)}}"
                     f"{pct(st0 + d)}{{left:100%;opacity:1}}"
                     + ("100%{left:100%;opacity:1}}" if last else
                        f"{pct(min(period, st0 + d + 0.001))},100%{{left:100%;opacity:0}}}}") +
                     f".bqr{uid} .u{i}{{animation:bqu{uid}_{i} {period:.2f}s infinite}}")
    stops = ["0%{transform:translateY(0)}"]
    for i, (st0, d) in enumerate(zip(starts, durs)):
        off = max(0, i - keep_row)
        if off:
            stops.append(f"{pct(st0)}{{transform:translateY(-{(off - 1) * 1.55:.2f}em)}}"
                         f"{pct(st0 + d)}{{transform:translateY(-{off * 1.55:.2f}em)}}")
    stops.append(f"100%{{transform:translateY(-{max(0, n - 1 - keep_row) * 1.55:.2f}em)}}")
    rules.append(f"@keyframes bqs{uid}{{{''.join(stops)}}}")
    css = "<style>" + "".join(rules) + ".bq-code-done .ct{clip-path:none!important;animation:none!important}</style>"
    return css, f"animation: bqs{uid} {period:.2f}s linear infinite;", uid


@contextlib.contextmanager
def code_loading_animation(label: str = "Generating visualization", code=None, record=True, min_seconds=None):
    """
    A drop-in replacement for `with st.spinner(...):` -- wraps the slow part (a download, or building a chart after
    RUN) and, while it runs, shows the REAL Python behind that step scrolling past (Roboto Mono, coloured like an
    editor) above a gold loading bar that climbs toward 100% and fills to 100% the moment the step finishes; then the
    whole box disappears and the result takes its place. `code`: the function(s) whose source to show (e.g. the chart
    builder); when omitted, one of the app's own chart builders is shown.
    """
    import html as _html
    import time as _time
    source = _loading_source(code, label)
    lines = _highlight_python(source)
    typing_css, roll_style, typing_uid = _typing_animation_css(source.splitlines()[:len(lines)])
    # one element per line (Streamlit's markdown would fold plain line breaks into one paragraph); each line's text
    # is typed out (revealed character by character) in turn while the window scrolls to keep up with it
    numbered = "".join(f'<div class="cl"><span class="cw"><span class="ct t{i}"><span class="ln">{i}</span>{ln}</span>'
                       f'<span class="cu u{i}"></span></span></div>'
                       for i, ln in enumerate(lines, 1))
    placeholder = st.empty()

    def _box(done=False):
        return (_LOADING_CSS.replace("\n", " ") + typing_css +
                f'<div class="bq-code-loading-box{" bq-code-done" if done else ""}">'
                f'<div class="bq-code-loading-label">&gt; {_html.escape(label)}...</div>'
                f'<div class="bq-code-window"><div class="bq-code-roll bqr{typing_uid}" style="{roll_style}">'
                f'{numbered}</div></div>'
                f'<div class="bq-code-bar-row"><div class="bq-code-progress-track"><div class="bq-code-progress-fill">'
                f'</div></div><div class="bq-code-pct"></div></div></div>')

    placeholder.markdown(_box(), unsafe_allow_html=True)
    started = _time.monotonic()
    _LOADER_DEPTH[0] += 1
    keep_until_shown = False
    try:
        yield
        if record:
            _note_run_code(source=source)
        clicked = _RUN_CODE.get("clicked_at")
        built_here = _RUN_CODE.get("built_in_box") and _LOADER_DEPTH[0] == 1
        if clicked is not None and (min_seconds or built_here):
            # right after RUN: the box that draws the chart stays up (typing) for at least 3 s
            wait = started + (min_seconds or _MIN_TYPING_SECONDS) - _time.monotonic()
            if wait > 0:
                _time.sleep(wait)
            _RUN_CODE["clicked_at"] = None               # only the first drawing after a RUN waits
            keep_until_shown = True
        if _time.monotonic() - started > 0.8:
            # finished: the bar fills to 100% for a moment before the result replaces it
            placeholder.markdown(_box(done=True), unsafe_allow_html=True)
            _time.sleep(0.35)
    finally:
        _LOADER_DEPTH[0] = max(0, _LOADER_DEPTH[0] - 1)
        if keep_until_shown:
            # the chart is put on screen right after this (turning a figure into a picture can take a second): the
            # full box stays until it's there, so there's never a blank gap between the code and the visualization
            _PENDING_LOADERS.append(placeholder)
        else:
            placeholder.empty()


_LOADER_DEPTH = [0]        # >0 while a loading box is already on screen (no box inside a box)
_PENDING_LOADERS = []      # finished boxes still on screen until their chart is shown (see _flush_run_code)
_DRAWING_NAMES = {"court_connection_map": "passing web", "impact_clock": "impact clock",
                  "onoff_column_image": "on/off columns", "trade_breakdown_image": "trade breakdown",
                  "static_stat_table_image": "stat table", "sankey_flow": "shot flow",
                  "head_to_head_table": "head-to-head", "network_diagram": "lineup network",
                  "lineup_shapes_diagram": "lineup network"}


def _drawing_with_loader(builder):
    """A chart builder that shows the loading box (its own real source code scrolling, the bar filling to 100%)
    while it draws -- so after RUN the box stays up until the visualization itself appears, not only while the data
    downloads. Inside another loading box it just draws."""
    import functools
    short = builder.__name__[len("build_"):]
    label = f"Drawing the {_DRAWING_NAMES.get(short, short.replace('_', ' '))}"

    @functools.wraps(builder)
    def run(*args, **kwargs):
        if _LOADER_DEPTH[0] > 0:
            out = builder(*args, **kwargs)
        else:
            animated = "animated" in builder.__name__
            with code_loading_animation(label, code=builder, record=False, min_seconds=None if animated else _MIN_TYPING_SECONDS):
                out = builder(*args, **kwargs)
        _note_run_code(func=builder)          # this chart's own code goes in the window under its RUN button
        return out
    return run


for _name, _fn in list(globals().items()):
    if _name.startswith("build_") and callable(_fn) and getattr(_fn, "__module__", "") == "visuals":
        globals()[_name] = _drawing_with_loader(_fn)


# ---- The code window under a RUN button: once a visualization has been generated, a small window right under its
# RUN button shows the start of the real Python that drew it; clicking the window opens it to the full code (clicking
# again closes it). The drawing functions (visuals.build_*) that made it are what's shown; a RUN that draws nothing
# (e.g. Stat Formula Creator's calculation) gets no window.
_RUN_CODE = {"slot": None, "draw": [], "steps": [], "clicked_at": None, "pending": False, "built_in_box": False}
_MIN_TYPING_SECONDS = 3.0           # after RUN: this long of code typing, then the visualization

_CODE_WINDOW_CSS = """<style>
.bq-codewin { margin: 6px 0 12px; border: 1px solid #2a2a2a; border-radius: 10px; overflow: hidden;
  background: linear-gradient(135deg, #1A1A1A 0%, #050505 100%); font-family: 'Roboto', Arial, sans-serif; }
.bq-codewin > summary { list-style: none; cursor: pointer; display: block; padding: 8px 12px 0; }
.bq-codewin > summary::-webkit-details-marker { display: none; }
.bq-codewin > summary::marker { content: ""; }
.bq-codewin .hd { display: flex; align-items: center; justify-content: space-between; gap: 10px; color: #D4AF37;
  font-size: 0.78rem; font-weight: 500; margin-bottom: 6px; }
.bq-codewin .hd .tg { color: #9a9a9a; font-weight: 400; white-space: nowrap; }
.bq-codewin[open] .hd .more, .bq-codewin:not([open]) .hd .less { display: none; }
.bq-codewin:hover { border-color: #D4AF37; }
.bq-codewin { animation: bqCodeIn .45s ease .4s both; }            /* it comes in just after the chart */
.bq-codewin.bq-wait { visibility: hidden; animation: none; }        /* a picture is still loading: wait for it */
@keyframes bqCodeIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
.bq-codewin .code { font-size: 0.72rem; line-height: 1.5; color: #c9c4b8; overflow-x: auto; padding: 0 12px 10px 0; }
.bq-codewin .peek { max-height: 6.2em; overflow: hidden; padding-bottom: 8px;
  -webkit-mask-image: linear-gradient(180deg, #000 55%, transparent 100%); mask-image: linear-gradient(180deg, #000 55%, transparent 100%); }
.bq-codewin[open] .peek { display: none; }
.bq-codewin .code .cl { white-space: pre; margin: 0; min-height: 1.5em; }
.bq-codewin .code .ln { display: inline-block; width: 2.6em; color: #4d4a42; text-align: right; margin-right: 1.1em; user-select: none; }
.bq-codewin .code .k { color: #D4AF37; font-weight: 600; }
.bq-codewin .code .f { color: #F5D370; }
.bq-codewin .code .s { color: #d9c9a0; }
.bq-codewin .code .c { color: #6f6a62; font-style: italic; }
.bq-codewin .code .n { color: #e8c77a; }
</style>"""


def _full_source(func):
    import inspect
    import textwrap
    try:
        return textwrap.dedent(inspect.getsource(getattr(func, "__wrapped__", func))).rstrip("\n")
    except (OSError, TypeError):
        return ""


def _note_run_code(func=None, source=None):
    """Record a finished step's code for the window under the current RUN button (and redraw that window)."""
    if _RUN_CODE["slot"] is None:
        return
    if func is not None:
        text = _code_for_typing(_full_source(func))
        bucket = _RUN_CODE["draw"]
    else:
        text = source or ""
        bucket = _RUN_CODE["steps"]
    if not text.strip() or text in bucket:
        return
    bucket.append(text)
    if _RUN_CODE["draw"]:
        _RUN_CODE["pending"] = True           # shown once the chart itself is on the page (see _flush_run_code)
        if _LOADER_DEPTH[0] > 0:
            _RUN_CODE["built_in_box"] = True


def _flush_run_code():
    """Put the code window under the RUN button -- called right after a chart has been shown, so the window appears
    with (never before) the visualization it belongs to. The finished loading box goes away here too."""
    while _PENDING_LOADERS:
        try:
            _PENDING_LOADERS.pop().empty()
        except Exception:
            pass
    if _RUN_CODE.get("slot") is None or not _RUN_CODE.get("pending") or not _RUN_CODE["draw"]:
        return
    _RUN_CODE["pending"] = False
    shown = "\n\n".join(_RUN_CODE["draw"])
    lines = _highlight_python(shown)
    n = len(lines)
    rows = [f'<div class="cl"><span class="ln">{i}</span>{ln}</div>' for i, ln in enumerate(lines, 1)]
    html = (_CODE_WINDOW_CSS.replace("\n", " ") +
            '<details class="bq-codewin"><summary><div class="hd"><span>&lt;/&gt; The code that made this visualization</span>'
            f'<span class="tg"><span class="more">Click to see all {n} lines &#9662;</span>'
            '<span class="less">Click to close &#9652;</span></span></div>'
            f'<div class="code peek">{"".join(rows[:6])}</div></summary>'
            f'<div class="code">{"".join(rows)}</div></details>')
    try:
        _RUN_CODE["slot"].markdown(html, unsafe_allow_html=True)
    except Exception:
        pass


def _code_window_here():
    """Moves the code window's place to right here on the page -- for a page with more controls between its RUN
    button and its charts (Search by Criteria's "Shots by area": the window goes under "Players to show:" and the
    pop-up hint, right above the charts). Filled in by _flush_run_code once the charts are drawn."""
    if _RUN_CODE.get("slot") is not None:
        _RUN_CODE["slot"] = st.empty()


# charts drawn by the other modules (Search by Criteria's tools, Upload Stats, ...) call visuals.build_* directly --
# visuals reports each finished drawing to this hook too
visuals.set_build_hook(lambda f: _note_run_code(func=f))
ui_hooks.set_after_chart(_flush_run_code)            # a chart shown with st.pyplot


def _show_animated_shot_chart(gif_buffer):
    """The animated shot chart at the same width as the other court charts (the page's full width) -- its frames are
    cropped the same way as theirs, so the court is exactly the same size as in the shot chart, heat map and hex
    chart."""
    st.markdown(
        "<style>.st-key-ba_anim_shot { align-items: stretch !important; }"
        ".st-key-ba_anim_shot [data-testid='stElementContainer'], .st-key-ba_anim_shot [data-testid='stFullScreenFrame'],"
        ".st-key-ba_anim_shot [data-testid='stFullScreenFrame'] > div, .st-key-ba_anim_shot [data-testid='stImage'],"
        ".st-key-ba_anim_shot [data-testid='stImageContainer'] { width: 100% !important; max-width: 100% !important; }"
        ".st-key-ba_anim_shot img { width: 100% !important; height: auto !important; }</style>",
        unsafe_allow_html=True)
    with st.container(key="ba_anim_shot"):
        try:
            st.image(gif_buffer, width="stretch")
        except (TypeError, Exception):                   # a Streamlit without width="stretch"
            st.image(gif_buffer, use_container_width=True)
    _download_gif_button(gif_buffer, "animated_shot_chart")
    _flush_run_code()


def _download_gif_button(gif_buffer, widget_key, file_name="bradley-analytics-animated-shot-chart.gif"):
    """ "Download GIF" under an animated visualization (same look as the "Download .png" button under the others)."""
    try:
        gif_buffer.seek(0)
        data = gif_buffer.read()
        gif_buffer.seek(0)
        with st.container(key=f"no_icon_{widget_key}_gif_download"):
            st.download_button("Download GIF", data=data, file_name=file_name, mime="image/gif",
                               key=f"{widget_key}_gif_download_btn", use_container_width=True)
    except Exception:
        pass


def rank_direction_control(stat_field: str, key_prefix: str) -> bool:
    """
    Renders a "Highest / Lowest" radio for ranking direction --
    explicitly requested to work like the color picker's own
    pick-or-type pattern, except here it's picking which end of the
    ranking to show (e.g. "top 10" Defensive Rating should mean the
    10 *lowest* values, since fewer points allowed is better defense,
    not the 10 highest).

    Keyed to the stat field itself (not a fixed key), so switching to
    a different stat gives a fresh widget with a fresh smart default
    based on LOWER_IS_BETTER_STATS, while staying on the same stat
    preserves whatever direction the user manually picked for it --
    changing stats shouldn't silently discard a manual override on an
    unrelated stat, but it also shouldn't carry the WRONG stat's
    manual choice onto a new one that has its own correct default.

    Returns True if "Lowest" (ascending) is selected.
    """
    default_lowest = stat_field in LOWER_IS_BETTER_STATS
    choice = st.radio(
        "Rank by:", ["Highest", "Lowest"],
        index=1 if default_lowest else 0,
        horizontal=True, key=f"{key_prefix}_direction_{stat_field}",
    )
    return choice == "Lowest"


def persistent_run_button(enabled: bool, key: str, show_chart_color: bool = True, not_ready: str = None) -> bool:
    """
    Fixes a real, widespread bug: every visualization branch's chart
    (and its own "Add to Tableau Dashboard" button) sits inside
    `if run:`, where run was a bare st.button() return value -- true
    only on the exact rerun where RUN itself was clicked, false on
    every other rerun including the one immediately triggered by
    clicking "Add to Tableau Dashboard" (nested inside that same `if
    run:` block). That inner click's own handling code never got a
    chance to execute at all, since Streamlit had already re-decided
    `if run:` was false before reaching it -- confirmed directly with
    a minimal reproduction, not assumed, and it explains "the button
    to add it to the dashboard... it never appears" exactly: the whole
    chart+button block silently disappeared on that very click.

    Persisting "has been run" in session_state (keyed uniquely per
    visualization via `key`) instead of relying on the transient
    button-click return value fixes this: once true, it stays true
    across every subsequent rerun this visualization is showing,
    including whichever button inside its own output block gets
    clicked next. `enabled` still gates it exactly like the original
    "if (season and picked_name) else False" conditions did -- if the
    person clears a required input, the persisted true is masked back
    to false rather than showing a stale chart for now-invalid inputs.

    Also renders "Chart Color" immediately before the RUN button
    itself -- explicitly requested to be the one single, consistent
    place this ever appears, replacing several previous attempts that
    each put it in a different spot relative to the RUN button
    depending on where a given visualization's own color picker
    happened to sit in its own flow. Since every visualization's run
    button already calls this one shared function, this is the only
    place this needs to be added for it to be correct everywhere at
    once. show_chart_color=False opts out for the handful of run
    buttons that don't produce an actual chart at all (e.g. Stat
    Formula Creator's rating calculation), where the toggle isn't
    relevant.
    """
    if show_chart_color:
        chart_color_label = st.radio(
            "Chart Color:", ["White", "Black"], horizontal=True, key=f"chart_color_{key}",
        )
        st.session_state["_global_chart_text_color"] = "black" if chart_color_label == "Black" else "white"
    state_key = f"run_state_{key}"
    clicked_now = st.button("RUN", use_container_width=True, key=f"run_btn_{key}")
    if clicked_now and not enabled:
        # every section shows all of its fields from the start, so RUN can be pressed before they're filled in
        st.warning(not_ready or "Fill in the fields above first (a player or team name, for example).")
        clicked_now = False
    if clicked_now:
        st.session_state[state_key] = True
    active = bool(enabled and st.session_state.get(state_key, False))
    # the code window's place: right under this RUN button, filled in once the visualization has been drawn
    _RUN_CODE.update(slot=st.empty() if active else None, draw=[], steps=[], pending=False, built_in_box=False)
    # RUN was just clicked: the drawing's loading box stays up (code typing) until ~3 s after the click
    _RUN_CODE["clicked_at"] = time.monotonic() if (active and clicked_now) else None
    return active


def friendly_error(e):
    """A plain-English reason for a failed NBA data call (the raw text is a wall of connection-pool jargon)."""
    text = f"{type(e).__name__}: {e}"
    low = text.lower()
    if "proxy" in low:
        return ("the proxy this app uses to reach the NBA stats site didn't respond (it closed the connection). "
                "This is usually momentary - try again in a minute. If it keeps happening, the proxy service set "
                "in NBA_PROXY_URL may be down or out of data.")
    if "timed out" in low or "timeout" in low:
        return "the NBA stats site took too long to answer. Try again in a minute."
    if "connection" in low or "max retries" in low:
        return "couldn't connect to the NBA stats site. Try again in a minute."
    return str(e)


def _hover(builder, *args, **kwargs):
    """Builds one chart's hover regions; a hover problem must never cost anyone the chart itself, so any failure here
    just means that chart shows without pop-ups."""
    try:
        return builder(*args, **kwargs) or []
    except Exception:
        return []


def _last_name(full_name):
    """'Jaren Jackson Jr.' -> 'Jackson' (a generational suffix is never the name a pop-up should show)."""
    parts = [p for p in str(full_name).split() if p.lower().rstrip(".") not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    return parts[-1] if parts else str(full_name)


def _game_lookup(mode, subject_id, season):
    """Real per-game result/score/opponent for hover pop-ups ({} if it can't be loaded)."""
    try:
        return get_game_context_lookup(mode, subject_id, season) or {}
    except Exception:
        return {}


def show_chart(fig, hotspot_list, key, file_name=None):
    """
    Shows a generated chart with its interactive hover pop-ups (desktop) and the "Download .png" button under it --
    in place of st.pyplot for every chart that has hover regions. Applies exactly what the st.pyplot hook applies
    (team-logo strip, White/Black chart text, the glow for black text) first, so the chart looks the same either way.
    Falls back to a plain st.pyplot image if the interactive layer can't be built.
    """
    ui_hooks.prepare_figure(fig)
    glow = st.session_state.get("_global_chart_text_color") == "black"
    name = file_name or f"bradley-analytics-{re.sub(r'[^a-z0-9]+', '-', str(key).lower()).strip('-')}.png"
    try:
        interactive.render_interactive_chart(fig, hotspot_list or [], key, glow=glow, file_name=name)
        fig._ba_interactive = True
    except Exception:
        st.pyplot(fig)
    _flush_run_code()


def _download_png_button(fig, widget_key):
    """The "Download .png" button (same look as the Tableau/Community buttons under it) for a chart shown as a plain
    image. Interactive charts draw this same button themselves, directly under the picture, so it can include any
    pinned pop-ups."""
    if getattr(fig, "_ba_interactive", False) or not hasattr(fig, "savefig"):
        return
    try:
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", transparent=True)
        with st.container(key=f"no_icon_{widget_key}_download"):
            st.download_button("Download .png", data=buf.getvalue(), file_name=f"bradley-analytics-{widget_key}.png",
                               mime="image/png", key=f"{widget_key}_download_btn", use_container_width=True)
    except Exception:
        pass


def add_to_tableau_dashboard(fig, source_label: str, widget_key: str):
    """
    A button that saves this chart into the Tableau Dashboard collage --
    either a specific slot (if the person arrived here via the '+'
    button on an empty slot, which remembers which one to fill) or the
    first open slot otherwise. Handles a GIF buffer the same way
    save_visualization() does (duck-typed on savefig()) -- the final
    collage PNG is a static composite regardless, so an animated
    visualization contributes its first frame, same as it would if
    someone screenshotted it.
    """
    _flush_run_code()                      # (the chart is already on the page above this button)
    if "tableau_slots" not in st.session_state:
        st.session_state.tableau_slots = [None] * 6

    # "Download .png" always sits directly above the Tableau button, in the same button style.
    _download_png_button(fig, widget_key)

    added_key = f"{widget_key}_added"
    if st.session_state.get(added_key):
        st.markdown(
            """
            <style>
            @keyframes bq-check-pop {
                0% { transform: scale(0); opacity: 0; }
                60% { transform: scale(1.3); opacity: 1; }
                100% { transform: scale(1); opacity: 1; }
            }
            .bq-added-check {
                display: inline-block;
                animation: bq-check-pop 0.4s ease-out;
                color: #4caf50;
                font-weight: bold;
                margin-right: 6px;
            }
            </style>
            <div style="border: 1px solid #3a3a3a; border-radius: 6px; padding: 8px 16px;
                        text-align: center; color: #4caf50; font-weight: bold;">
              <span class="bq-added-check">&#10003;</span>ADDED TO TABLEAU DASHBOARD!
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    with st.container(key=f"no_icon_{widget_key}_tableau"):
        clicked = st.button("Add to Tableau Dashboard", key=f"{widget_key}_tableau_btn", use_container_width=True)
    if clicked:
        if hasattr(fig, "savefig"):
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", transparent=True)
            buf.seek(0)
            image_bytes = buf.read()
        else:
            fig.seek(0)
            image_bytes = fig.read()

        target_slot = st.session_state.get("tableau_target_slot")
        if target_slot is not None and st.session_state.tableau_slots[target_slot] is None:
            slot_idx = target_slot
        else:
            empty_slots = [i for i, s in enumerate(st.session_state.tableau_slots) if s is None]
            if not empty_slots:
                st.warning("All 6 Tableau Dashboard slots are full - remove one first (on the Tableau Dashboard page) to add this.")
                return
            slot_idx = empty_slots[0]

        st.session_state.tableau_slots[slot_idx] = {"image_bytes": image_bytes, "source": source_label}
        st.session_state["tableau_target_slot"] = None
        st.session_state[added_key] = True
        st.rerun()


# =============================================================================
# HOME
# =============================================================================
def resolve_color_input(color_input: str) -> str:
    """Mirrors resolve_color() -- accepts a raw hex code or a team name."""
    special = {"white": "#FFFFFF", "black": "#000000", "gold": "#D4AF37"}
    if color_input.strip().lower() in special:
        return special[color_input.strip().lower()]
    hex_candidate = color_input.strip().lstrip("#")
    is_hex = len(hex_candidate) == 6 and all(c in "0123456789abcdefABCDEF" for c in hex_candidate)
    if is_hex:
        return f"#{hex_candidate.upper()}"
    return get_team_color(color_input)


def _team_text_color(team_name):
    """The team's colour for words on the dashboard's black background: the colour itself, or -- for a very dark one
    (e.g. the Nuggets' navy) -- a lighter shade of it, so it can still be read."""
    col = get_team_color(team_name) or "#D4AF37"
    try:
        r, g, b = (int(col.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return "#D4AF37"
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum >= 60:
        return col
    mix = min(0.65, (60 - lum) / 90 + 0.25)
    r, g, b = (round(v + (255 - v) * mix) for v in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def _team_fill_colors(team_name):
    """(fill, words) for a box filled with the team's colour: black or white words, whichever reads better on it."""
    fill = get_team_color(team_name) or "#D4AF37"
    try:
        r, g, b = (int(fill.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        return fill, ("#111111" if (0.299 * r + 0.587 * g + 0.114 * b) > 160 else "#ffffff")
    except Exception:
        return "#D4AF37", "#111111"


ROSTER_DISPLAYS = ["Stats", "Bradley Ratings", "Tendencies"]


def _safe_key(s):
    """Any text as a widget-key-safe slug."""
    return re.sub(r"[^A-Za-z0-9_]", "_", str(s))


def _roster_frame(team_name, season):
    """(roster, picture urls) for a team's season: PLAYER_ID, PLAYER, POSITION, AGE, HEIGHT (+ TEAM_NAME)."""
    team_id = TEAM_NAME_TO_RECORD[team_name]["id"]
    roster_df = get_team_roster(team_id, season)
    urls = {}
    if roster_df is not None and not roster_df.empty and "PLAYER_ID" in roster_df.columns:
        urls = {int(p): get_player_headshot_url(int(p)) for p in roster_df["PLAYER_ID"].dropna()}
        visuals.prefetch_images(list(urls.values()))
    if roster_df is None or roster_df.empty:
        return pd.DataFrame(), urls
    table = roster_df[[c for c in ["PLAYER_ID", "PLAYER", "POSITION", "AGE", "HEIGHT"] if c in roster_df.columns]].copy()
    table["TEAM_NAME"] = team_name
    return table, urls


def _sort_by_rating_then_points(table, season, pts=None):
    """Every player list's order (Roster, Player Tendencies, Trade Machine): highest Player Rating first; players
    without one -- no row yet, or a season the ratings don't cover -- after them by points per game, then by name.
    pts: points per game per row (defaults to the table's PTS column, else this season's per-game stats)."""
    t = table.copy()
    rating = pd.Series(float("nan"), index=t.index)
    if ratings_data.available(season) and not t.empty:
        for kind in (ratings_data.RATINGS, ratings_data.TENDENCIES):
            found = ratings_data.lookup(kind, t)
            for i in t.index:
                hit = found.get(i)
                if pd.isna(rating[i]) and hit is not None and "Player Rating" in hit.index:
                    rating[i] = pd.to_numeric(hit["Player Rating"], errors="coerce")
    if pts is None:
        if "PTS" in t.columns:
            pts = t["PTS"]
        else:
            ppg = {}
            try:
                # (a season without games yet: the latest one that has them)
                sdf = get_player_stats(min(str(season), _stats_config.default_season()), per_mode="PerGame")
                if sdf is not None and {"PLAYER_ID", "PTS"} <= set(sdf.columns):
                    ppg = dict(zip(sdf["PLAYER_ID"].astype(int), sdf["PTS"]))
            except Exception:
                pass
            pids = t["PLAYER_ID"] if "PLAYER_ID" in t.columns else pd.Series([None] * len(t), index=t.index)
            pts = [ppg.get(int(p)) if pd.notna(p) else None for p in pids]
    t["_SORT_R"] = pd.to_numeric(rating, errors="coerce")
    t["_SORT_NOR"] = t["_SORT_R"].isna()
    t["_SORT_P"] = pd.to_numeric(pd.Series(list(pts), index=t.index), errors="coerce")
    by = ["_SORT_NOR", "_SORT_R", "_SORT_P"] + (["PLAYER"] if "PLAYER" in t.columns else [])
    return t.sort_values(by, ascending=[True, False, False, True][:len(by)], na_position="last")


def _rating_columns_for(table, kind, season):
    """Adds the Bradley Ratings (kind=ratings) or Tendencies of each roster player to `table` (NaN = N/A, also for
    every player in a season they don't cover), sorted by Player Rating, players without numbers last. Returns
    (table, the columns' [(label, key, fmt)])."""
    import html as _html
    cols = ratings_data.columns(kind)
    found = ratings_data.lookup(kind, table) if ratings_data.available(season) else {}
    for c in cols + ["Player Rating"]:
        vals = []
        for i in table.index:
            hit = found.get(i)
            vals.append(hit[c] if hit is not None and c in hit.index else float("nan"))
        table[f"_R_{c}"] = pd.to_numeric(pd.Series(vals, index=table.index), errors="coerce")
    table = _sort_by_rating_then_points(table, season)
    spec = [(_html.escape(ratings_data.short_label(c)), f"_R_{c}",
             (lambda col: (lambda v: ratings_data.display(v, col)))(c)) for c in cols]
    return table, spec


def _roster_table_html(team_name, table, urls, cols, wide=False):
    """The roster table every roster-style page shares: picture, Player, Pos, Age, Ht, then `cols`
    ([(header, column, formatter)]). wide=True (dozens of rating / tendency columns): headers wrap onto two lines
    and the picture and name stay in place while the numbers scroll sideways."""
    import html as _html
    base = [("Pos", "POSITION", lambda v: _html.escape(str(v)) if pd.notna(v) else ""),
            ("Age", "AGE", lambda v: str(int(round(float(v)))) if pd.notna(v) else ""),
            ("Ht", "HEIGHT", lambda v: _html.escape(str(v)) if pd.notna(v) else "")]
    cols = [c for c in base if c[1] in table.columns] + [c for c in cols if c[1] in table.columns]
    rows = []
    for _, r in table.iterrows():
        pid = r.get("PLAYER_ID")
        uri = visuals.picture_data_uri(urls.get(int(pid))) if pd.notna(pid) and int(pid) in urls else None
        pic = (f'<img src="{uri}" alt="">' if uri else '<span class="noimg"></span>')
        name = str(r.get("PLAYER") or "")
        first, _, rest = name.partition(" ")
        who = (f'<span class="fn">{_html.escape(first)}</span> <span class="ln">{_html.escape(rest)}</span>' if rest
               else _html.escape(name))
        cells = []
        for _lbl, key, fmt in cols:
            txt = fmt(r.get(key))
            cells.append(f'<td{" class=na" if txt == "N/A" else ""}>{txt}</td>')
        rows.append(f'<tr><td class="pic">{pic}</td><td class="pl">{who}</td>' + "".join(cells) + "</tr>")
    head = "".join(f"<th>{lbl}</th>" for lbl, _k, _f in cols)
    head_color = _team_text_color(team_name)
    wide_css = """
.ba-roster.wide th { vertical-align: bottom; }
.ba-roster.wide th:nth-child(n+6) { white-space: nowrap; line-height: 1.2; text-align: center; font-size: 0.8rem; }
.ba-roster.wide td:nth-child(n+6) { text-align: center; }
.ba-roster.wide th:nth-child(-n+5), .ba-roster.wide td:nth-child(-n+5) { text-align: left; }
.ba-roster.wide td.pic, .ba-roster.wide th:first-child { position: sticky; left: 0; z-index: 2; background: #0e0e0e; }
.ba-roster.wide td.pl, .ba-roster.wide th:nth-child(2) { position: sticky; left: 50px; z-index: 2; background: #0e0e0e;
                                                         box-shadow: 1px 0 0 #242424; }
.ba-roster td.na { color: #6f6f6f; }
@media (max-width: 640px) { .ba-roster.wide td.pl, .ba-roster.wide th:nth-child(2) { left: 42px; } }
""" if wide else ".ba-roster td.na { color: #6f6f6f; }"
    st.markdown(f"""
<style>
.ba-roster-wrap {{ overflow-x: auto; margin: 4px 0 10px; }}
.ba-roster {{ border-collapse: collapse; font-family: Arial, sans-serif; font-size: 0.88rem; width: 100%; }}
.ba-roster th {{ color: {head_color}; font-weight: 700; padding: 7px 8px; text-align: right; border-bottom: 1px solid #3a3730;
                white-space: nowrap; background: transparent; }}
.ba-roster th:nth-child(-n+3), .ba-roster td:nth-child(-n+3) {{ text-align: left; }}
.ba-roster td {{ padding: 4px 8px; text-align: right; color: #e6e6e6; border-bottom: 1px solid #242424; white-space: nowrap;
                vertical-align: middle; }}
.ba-roster td.pic {{ width: 50px; min-width: 50px; padding: 3px 4px 3px 2px; }}
.ba-roster td.pic img, .ba-roster td.pic .noimg {{ display: block; width: 46px; min-width: 46px; max-width: none; height: 34px; }}
.ba-roster td.pl {{ color: #f0f0f0; font-weight: 600; }}
{wide_css}
@media (max-width: 640px) {{
  .ba-roster {{ font-size: 0.8rem; width: max-content; min-width: 100%; }}
  .ba-roster th, .ba-roster td {{ padding-left: 5px; padding-right: 5px; }}
  .ba-roster td.pl {{ white-space: normal; line-height: 1.2; min-width: 5.5em; }}
  .ba-roster td.pl .fn, .ba-roster td.pl .ln {{ display: block; white-space: nowrap; }}
  .ba-roster td.pic {{ width: 42px; min-width: 42px; }}
  .ba-roster td.pic img, .ba-roster td.pic .noimg {{ width: 38px; min-width: 38px; height: 28px; }}
}}
</style>
<div class="ba-roster-wrap"><table class="ba-roster{' wide' if wide else ''}">
<thead><tr><th></th><th>Player</th>{head}</tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
""", unsafe_allow_html=True)


def _display_roster_picker(key):
    """"Display roster:" -- Stats / Bradley Ratings / Tendencies, in the same gold-when-picked text style as the
    section tabs above it (a small grey bold Arial label over it)."""
    st.markdown(
        f"<style>.st-key-{key}_wrap [data-testid='stWidgetLabel'] p {{ font-family: Arial, sans-serif !important; "
        "font-size: 0.8rem !important; }}"
        f".st-key-{key}_wrap [data-testid='stRadio'] {{ margin-top: -4px; }}</style>", unsafe_allow_html=True)
    with st.container(key=f"{key}_wrap"):
        return st.radio("Display roster:", ROSTER_DISPLAYS, index=0, horizontal=True, key=key)


def _ratings_season_note(season, what):
    if not ratings_data.available(season):
        st.caption(f"{what} are for {' and '.join(sorted(ratings_data.SEASONS))} only, so every player shows N/A "
                   f"for {season}.")


def render_front_office_roster(team_name):
    """The team's roster for a chosen season: each player's picture, bio (position, age, height) and -- picked under
    "Display roster:" -- his per-game stats (games played, points, rebounds, ...), his Bradley Ratings, or his
    Tendencies. Every display lists the highest Player Rating first; players without one (no numbers yet, or a season
    the ratings don't cover) come after them by points per game. Clicking a column's header sorts by it.
    Drawn as a plain HTML table: on a wide screen every name and height stays on one line; on a phone a name can wrap
    to two lines (first name over last name) and the table scrolls sideways if it has to."""
    season = st.selectbox("Season:", ALL_SEASONS, index=0, key=f"fo_roster_season_{team_name}")
    display = _display_roster_picker(f"fo_roster_display_{_safe_key(team_name)}")
    with code_loading_animation(f"Downloading {team_name}'s {season} roster"):
        table, urls = _roster_frame(team_name, season)
        stats_df = get_player_stats(season, per_mode="PerGame") if display == "Stats" else None

    if table.empty:
        st.warning(f"No roster found for {team_name} in {season}.")
        return

    if display == "Stats":
        stat_cols = [c for c in ["PLAYER_ID", "GP", "PTS", "REB", "AST", "STL", "BLK", "FG_PCT", "FG3_PCT", "MIN"]
                     if stats_df is not None and c in stats_df.columns]
        if "PLAYER_ID" in table.columns and "PLAYER_ID" in stat_cols:
            table = table.merge(stats_df[stat_cols], on="PLAYER_ID", how="left")

        # highest Player Rating first; players without one after them by points per game
        table = _sort_by_rating_then_points(table, season)

        def one(v):
            return f"{v:.1f}" if pd.notna(v) else ""

        def pct(v):
            return f"{v:.3f}" if pd.notna(v) else ""

        cols = [("GP", "GP", lambda v: str(int(v)) if pd.notna(v) else ""),
                ("PPG", "PTS", one), ("RPG", "REB", one), ("APG", "AST", one), ("SPG", "STL", one), ("BPG", "BLK", one),
                ("FG%", "FG_PCT", pct), ("3P%", "FG3_PCT", pct), ("MPG", "MIN", one)]
        _roster_table_html(team_name, table, urls, cols)
        return
    kind = ratings_data.RATINGS if display == "Bradley Ratings" else ratings_data.TENDENCIES
    _ratings_season_note(season, display)
    table, cols = _rating_columns_for(table, kind, season)
    _roster_table_html(team_name, table, urls, cols, wide=True)


def render_coaching_player_tendencies(team_name):
    """Coaching > Player Tendencies: the Roster table (picture, name, position, age, height) with each player's
    Tendencies where the stats start -- N/A for a player we don't have them for yet."""
    season = st.selectbox("Season:", ALL_SEASONS, index=0, key=f"co_tend_season_{team_name}")
    with code_loading_animation(f"Downloading {team_name}'s {season} roster"):
        table, urls = _roster_frame(team_name, season)
    if table.empty:
        st.warning(f"No roster found for {team_name} in {season}.")
        return
    _ratings_season_note(season, "Tendencies")
    table, cols = _rating_columns_for(table, ratings_data.TENDENCIES, season)
    _roster_table_html(team_name, table, urls, cols, wide=True)


def _cap_year_start(today=None):
    """The league (cap) year starts July 1, so from July on the upcoming season's contracts are the current ones."""
    today = today or _stats_config._today_eastern()
    return today.year if today.month >= 7 else today.year - 1


def _cap_season(today=None):
    """The current league year as a season label, e.g. "2026-27" from July 1, 2026."""
    y = _cap_year_start(today)
    return f"{y}-{str(y + 1)[-2:]}"


def render_front_office_salary_cap(team_name):
    """Each contract on this team's books, by season, straight from the salary spreadsheet (data/salary_table.xlsx):
    salary per season coloured by its status (player option, team option, non-guaranteed, ...), UFA/RFA years, dead
    money from waivers and buyouts, and each season's total. Who's on the team comes from its NBA roster for that
    season (the spreadsheet has no team column); dead money comes from the spreadsheet's Dead money sheet.

    Above it, four windows: the season's total salary and the team's space under the cap, the 1st apron and the 2nd
    apron (official figures in salary_table.CAP_FIGURES). The table lists name, age, and the current league year plus
    the five after it (an earlier season: just that season), biggest current salary first."""
    import html as _html
    team_id = TEAM_NAME_TO_RECORD[team_name]["id"]
    abbr = TEAM_NAME_TO_RECORD[team_name]["abbreviation"]
    y0 = _cap_year_start()
    cap_seasons = [f"{y}-{str(y + 1)[-2:]}" for y in range(y0, 1995, -1)]
    season = st.selectbox("Season:", cap_seasons, index=0, key=f"fo_cap_season_{team_name}")
    current = season == cap_seasons[0]
    roster = None
    with code_loading_animation(f"Downloading {team_name}'s {season} roster"):
        # before opening night the new season's roster can still be empty -- fall back to the latest one
        for s in dict.fromkeys([season, _stats_config.default_season()] if current else [season]):
            try:
                roster = get_team_roster(team_id, s)
            except Exception:
                roster = None
            if roster is not None and not roster.empty:
                break
    ids = roster["PLAYER_ID"].tolist() if roster is not None and "PLAYER_ID" in roster.columns else []
    names = roster["PLAYER"].tolist() if roster is not None and "PLAYER" in roster.columns else []
    ages = {}
    if roster is not None and "AGE" in roster.columns:
        for pid, nm, age in zip(roster.get("PLAYER_ID", [None] * len(roster)), roster.get("PLAYER", [""] * len(roster)),
                                roster["AGE"]):
            if pd.notna(age):
                ages[("id", int(pid)) if pd.notna(pid) else ("name", nm)] = int(age)
                ages[("name", salary_table.name_key(nm))] = int(age)
    if not ids and not names:
        st.warning(f"Couldn't load {team_name}'s {season} roster, so only its dead money can be shown.")
    table = _load_salary_table()
    # the current league year and the 5 after it (an earlier season: just that season)
    seasons = ([f"{y}-{str(y + 1)[-2:]}" for y in range(y0, min(y0 + 5, 2033) + 1)] if current else [season])
    rows, totals = salary_table.team_contracts(table, abbr, seasons, ids, names)

    # the four windows: this season's total, and how far under (or over) the cap and both aprons it leaves the team
    figs = salary_table.CAP_FIGURES.get(season, {})
    total = totals.get(season, 0) if rows else 0

    def _money(v):
        return f"${v:,.0f}" if v is not None else "—"
    windows = [("Total Salary:", _money(total)),
               ("Cap Space:", _money(figs["cap"] - total) if "cap" in figs else "—"),
               ("1st Apron Space:", _money(figs["apron1"] - total) if "apron1" in figs else "—"),
               ("2nd Apron Space:", _money(figs["apron2"] - total) if "apron2" in figs else "—")]
    # the season on the first line and what the window shows on the second, on the team's own colour; the number
    # under it on a black gradient
    head_bg = get_team_color(team_name)
    try:
        _r, _g, _b = (int(head_bg.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        head_fg = "#111111" if (0.299 * _r + 0.587 * _g + 0.114 * _b) > 160 else "#ffffff"
    except Exception:
        head_bg, head_fg = "#D4AF37", "#111111"
    st.markdown(
        '<style>'
        '.ba-cap-cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 22px; margin: 6px 0 16px; }'
        '@media (max-width: 760px) { .ba-cap-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; } }'
        '.ba-cap-card { border: 1px solid #2c2c2c; border-radius: 6px; overflow: hidden; '
        'background: linear-gradient(135deg, #1A1A1A 0%, #070707 73%); }'
        f'.ba-cap-card .h {{ background: {head_bg}; color: {head_fg}; font: 700 0.8rem Roboto, Arial, sans-serif; '
        'text-align: center; padding: 6px 6px 7px; letter-spacing: 0.02em; line-height: 1.3; }'
        '.ba-cap-card .h span { display: block; }'
        '.ba-cap-card .v { color: #ffffff; font: 400 1.25rem Roboto, Arial, sans-serif; text-align: center; '
        'padding: 13px 6px 14px; white-space: nowrap; }'
        '@media (max-width: 760px) { .ba-cap-card .v { font-size: 1.05rem; } }'
        '</style><div class="ba-cap-cards">' +
        "".join(f'<div class="ba-cap-card"><div class="h"><span>{_html.escape(season)}</span>'
                f'<span>{_html.escape(h)}</span></div><div class="v">{v}</div></div>'
                for h, v in windows) + '</div>', unsafe_allow_html=True)

    if not rows:
        st.info(f"No {team_name} contracts have been entered for {season}{' onward' if current else ''} yet.")
        return

    def _cell(salary, status):
        if salary is not None:
            text = f"${salary:,.0f}"
        elif status in ("UFA", "RFA", "Two-way"):
            text = _html.escape("Two-Way" if status == "Two-way" else status)
        else:
            text = ""
        style = ""
        if status in salary_table.STATUS_COLORS:
            bg, fg = salary_table.STATUS_COLORS[status]
            style = f' style="background:{bg};color:{fg};font-weight:700;"'
        title = f' title="{_html.escape(status)}"' if status else ""
        return f"<td{style}{title}>{text}</td>"

    def _age(r):
        if r["dead"]:
            return ""
        a = ages.get(("id", r["player_id"])) if r.get("player_id") else None
        if a is None:
            a = ages.get(("name", salary_table.name_key(r["player"])))
        return "" if a is None else str(a)

    head = "".join(f'<th class="{"cur" if i == 0 else ""}">{s}</th>' for i, s in enumerate(seasons))

    # each player's picture, in front of his name (the same picture as the Roster table's)
    def _pid_of(r):
        if r.get("player_id"):
            return int(r["player_id"])
        rec = PLAYER_NAME_TO_RECORD.get(_strip_accents(str(r["player"])))
        return int(rec["id"]) if rec else None
    _pic_urls = {i: get_player_headshot_url(i) for i in (_pid_of(r) for r in rows) if i}
    visuals.prefetch_images(list(_pic_urls.values()))

    def _pic(r):
        i = _pid_of(r)
        uri = visuals.picture_data_uri(_pic_urls[i]) if i in _pic_urls else None
        return f'<td class="pic">{f"<img src={chr(34)}{uri}{chr(34)} alt={chr(34)}{chr(34)}>" if uri else "<span class=noimg></span>"}</td>'
    body = []
    for r in rows:
        who = _html.escape(r["player"]) + (' <span class="dm">(dead money)</span>' if r["dead"] else "")
        body.append(f'<tr>{_pic(r)}<td class="pl">{who}</td><td class="age">{_age(r)}</td>' +
                    "".join(_cell(*r["cells"][s]) for s in seasons) + "</tr>")
    body.append('<tr class="tot"><td class="pic"></td><td class="pl">Total</td><td class="age"></td>' +
                "".join(f"<td>{'$' + format(totals[s], ',.0f') if totals[s] else '-'}</td>" for s in seasons) + "</tr>")
    used = [s for s in salary_table.STATUS_COLORS if any(c[1] == s for r in rows for c in r["cells"].values())]
    legend = "".join(
        f'<span class="chip" style="background:{salary_table.STATUS_COLORS[s][0]};'
        f'color:{salary_table.STATUS_COLORS[s][1]};">{s}</span>' for s in used)
    th_color = _team_text_color(team_name)
    cur_bg, cur_fg = _team_fill_colors(team_name)
    st.markdown(f"""
<style>
.ba-cap-wrap {{ overflow-x: auto; margin: 4px 0 10px; }}
.ba-cap {{ border-collapse: collapse; font-family: Arial, sans-serif; font-size: 0.86rem; min-width: 100%; }}
.ba-cap th {{ background: #111111; color: {th_color}; font-weight: 700; padding: 7px 10px; text-align: right;
             border-bottom: 1px solid #3a3730; white-space: nowrap; }}
.ba-cap th.cur {{ background: {cur_bg}; color: {cur_fg}; }}
.ba-cap th:first-child, .ba-cap th:nth-child(2) {{ text-align: left; }}
.ba-cap td.pic {{ width: 50px; min-width: 50px; padding: 3px 4px 3px 2px; }}
.ba-cap td.pic img, .ba-cap td.pic .noimg {{ display: block; width: 46px; min-width: 46px; max-width: none; height: 34px; }}
@media (max-width: 640px) {{
  .ba-cap td.pic {{ width: 42px; min-width: 42px; }}
  .ba-cap td.pic img, .ba-cap td.pic .noimg {{ width: 38px; min-width: 38px; height: 28px; }}
}}
.ba-cap th.age, .ba-cap td.age {{ text-align: center; }}
.ba-cap td {{ padding: 6px 10px; text-align: right; color: #e6e6e6; border-bottom: 1px solid #242424;
             white-space: nowrap; }}
.ba-cap td.pl {{ text-align: left; color: #f0f0f0; font-weight: 600; }}
.ba-cap td.age {{ color: #bdbdbd; }}
.ba-cap .dm {{ color: #9d9d9d; font-weight: 400; font-style: italic; }}
.ba-cap tr.tot td {{ border-top: 1px solid #D4AF37; border-bottom: none; color: #F5D370; font-weight: 700; }}
.ba-cap-legend {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 2px 0 8px; }}
.ba-cap-legend .chip {{ font: 700 0.75rem Arial, sans-serif; padding: 3px 8px; border-radius: 4px; }}
</style>
<div class="ba-cap-legend">{legend}</div>
<div class="ba-cap-wrap"><table class="ba-cap">
<thead><tr><th></th><th>Name</th><th class="age">Age</th>{head}</tr></thead>
<tbody>{''.join(body)}</tbody></table></div>
""", unsafe_allow_html=True)
    st.caption("Cap hit per season. Totals include dead money and leave out two-way contracts, which don't count "
               "against the cap. Cap space here is the cap minus these contracts (it doesn't count cap holds for "
               "unsigned free agents).")


def _open_onoff_for_team(team_name):
    """Button callback: jump to the On/Off Lineup Network page with this team already picked. Done in a callback
    (which runs before any widget of the next run exists) -- setting the sidebar's own value from inside the page,
    after the sidebar was already drawn, is what raised the StreamlitAPIException."""
    st.session_state["onoff_team"] = team_name
    st.session_state["category_radio"] = "On/Off Lineup Network"


def render_coaching_player_minutes(team_name):
    """Plan the rotation: the team's roster laid out like Front Office's Roster table (picture, name, position), but in
    place of the stats a 0-48 minute slider for each player, the minutes that slider gives him (MIN), then the minutes
    he really averages (MPG, darker). In the header row, centred over the sliders on the same line as MIN and MPG:
    TOTAL MINUTES x/240 -- the minutes handed out so far, green at exactly 240 (a full game: 5 players x 48 minutes),
    red under or over it. The sliders start at each player's real average, rounded; everything updates as a slider
    moves (all in the page, no reloading).

    Each row has a grip at its left: drag it to move the player anywhere in the order (the starting five on top, say).
    Every player on 0 minutes sits at the bottom, under a grey "End of Bench" line -- a slider taken down to 0 sends
    its player there, and one raised from 0 brings him back up to the end of the rotation. At exactly 240/240 a
    "Download .png" button appears above the table: a picture of the rotation in its current order (the End of Bench
    players are left out of it)."""
    import html as _html
    st.button(f"Open On/Off Lineup Network for {team_name}", key=f"co_minutes_link_{team_name}",
              on_click=_open_onoff_for_team, args=(team_name,))
    team_id = TEAM_NAME_TO_RECORD[team_name]["id"]
    season = st.selectbox("Season:", ALL_SEASONS, index=0, key=f"co_minutes_season_{team_name}")
    with code_loading_animation(f"Downloading {team_name}'s {season} minutes"):
        roster_df = get_team_roster(team_id, season)
        stats_df = get_player_stats(season, per_mode="PerGame")
        urls = {}
        if not roster_df.empty and "PLAYER_ID" in roster_df.columns:
            urls = {int(p): get_player_headshot_url(int(p)) for p in roster_df["PLAYER_ID"].dropna()}
            visuals.prefetch_images(list(urls.values()))
    if roster_df.empty:
        st.warning(f"No roster found for {team_name} in {season}.")
        return

    table = roster_df[[c for c in ["PLAYER_ID", "PLAYER", "POSITION"] if c in roster_df.columns]].copy()
    if "PLAYER_ID" in table.columns and "PLAYER_ID" in stats_df.columns and "MIN" in stats_df.columns:
        table = table.merge(stats_df[["PLAYER_ID", "MIN"]], on="PLAYER_ID", how="left")
    else:
        table["MIN"] = float("nan")
    table["_MPG"] = pd.to_numeric(table["MIN"], errors="coerce")
    table = table.sort_values(["_MPG", "PLAYER"], ascending=[False, True], na_position="last")

    playing, bench = [], []
    for _, r in table.iterrows():
        pid = r.get("PLAYER_ID")
        uri = visuals.picture_data_uri(urls.get(int(pid))) if pd.notna(pid) and int(pid) in urls else None
        pic = f'<img src="{uri}" alt="">' if uri else '<span class="noimg"></span>'
        name = str(r.get("PLAYER") or "")
        first, _, rest = name.partition(" ")
        who = (f'<span class="fn">{_html.escape(first)}</span> <span class="ln">{_html.escape(rest)}</span>' if rest
               else _html.escape(name))
        mpg = r["_MPG"]
        start = int(round(mpg)) if pd.notna(mpg) else 0
        pos = _html.escape(str(r.get("POSITION"))) if pd.notna(r.get("POSITION")) else ""
        row = (f'<tr class="p" data-name="{_html.escape(name)}" data-pos="{pos}" '
               f'data-mpg="{f"{mpg:.1f}" if pd.notna(mpg) else "-"}">'
               f'<td class="grip" title="Drag to move {_html.escape(name)}"><span></span></td>'
               f'<td class="pic">{pic}</td><td class="pl">{who}</td><td class="pos">{pos}</td>'
               f'<td class="sl"><input type="range" min="0" max="48" step="1" value="{start}" '
               f'aria-label="Minutes for {_html.escape(name)}"></td>'
               f'<td class="min">{start}</td><td class="mpg">{f"{mpg:.1f}" if pd.notna(mpg) else "-"}</td></tr>')
        (playing if start > 0 else bench).append(row)

    head_color = _team_text_color(team_name)
    fill = get_team_color(team_name) or "#D4AF37"
    fill_text = _team_text_color(team_name)
    height = 46 + 46 * (len(playing) + len(bench)) + 40
    file_name = f"bradley-analytics-{re.sub(r'[^a-z0-9]+', '-', team_name.lower()).strip('-')}-{season}-rotation.png"
    _doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; padding: 0; background: transparent; }}
body {{ font-family: Arial, sans-serif; color: #e6e6e6; }}
.wrap {{ overflow-x: auto; }}
table {{ border-collapse: collapse; font-size: 14px; width: 100%; }}
th {{ color: {head_color}; font-weight: 700; padding: 7px 8px; text-align: right; border-bottom: 1px solid #3a3730;
     white-space: nowrap; }}
th.l {{ text-align: left; }}
th.tm {{ text-align: center; font-size: 13px; letter-spacing: .04em; }}
th.tm span {{ color: #bdbdbd; }}
th.tm b {{ font-size: 14px; }}
th.tm .ok {{ color: #2ECC71; }}
th.tm .bad {{ color: #FF4D4D; }}
td {{ padding: 4px 8px; color: #e6e6e6; border-bottom: 1px solid #242424; white-space: nowrap; vertical-align: middle;
     height: 37px; }}
td.grip {{ width: 14px; padding: 4px 2px 4px 0; cursor: grab; touch-action: none; user-select: none; -webkit-user-select: none; }}
td.grip span {{ display: block; width: 10px; height: 16px; margin: 0 auto; opacity: .55;
  background-image: radial-gradient(circle, #bdbdbd 1.3px, transparent 1.6px); background-size: 5px 5.4px; }}
td.grip:hover span, tr.dragging td.grip span {{ opacity: 1; }}
tr.dragging td {{ background: rgba(212, 175, 55, .08); }}
tr.dragging td.grip {{ cursor: grabbing; }}
td.pic {{ width: 50px; min-width: 50px; padding: 3px 4px 3px 2px; }}
td.pic img, td.pic .noimg {{ display: block; width: 46px; height: 34px; object-fit: cover; object-position: top; }}
td.pl {{ color: #f0f0f0; font-weight: 600; }}
td.pos {{ color: #e6e6e6; }}
td.sl {{ width: 60%; min-width: 110px; padding-left: 14px; padding-right: 14px; }}
td.min {{ text-align: right; font-weight: 700; color: #ffffff; min-width: 2.2em; }}
td.mpg {{ text-align: right; color: #7d7d7d; min-width: 2.6em; }}
tr.eob td {{ height: auto; padding: 14px 0 3px; border-bottom: none; border-top: 1px solid #5a5a5a; color: #9a9a9a;
  font: 700 12.5px Arial, sans-serif; letter-spacing: .02em; }}
tr.eob.empty {{ display: none; }}
input[type=range] {{ -webkit-appearance: none; appearance: none; width: 100%; height: 6px; border-radius: 3px; margin: 0;
  background: linear-gradient(to right, {fill} 0%, {fill} var(--p, 0%), #2a2a2a var(--p, 0%), #2a2a2a 100%); outline: none;
  cursor: pointer; }}
input[type=range]::-webkit-slider-thumb {{ -webkit-appearance: none; appearance: none; width: 16px; height: 16px;
  border-radius: 50%; background: #ffffff; border: 2px solid {fill_text}; box-shadow: 0 0 0 2px #0d0d0d; }}
input[type=range]::-moz-range-thumb {{ width: 14px; height: 14px; border-radius: 50%; background: #ffffff;
  border: 2px solid {fill_text}; }}
input[type=range]::-moz-range-track {{ background: transparent; }}
/* "Download .png" -- the same button as everywhere else in the dashboard; only there at exactly 240/240 */
@keyframes bqGoldTextShimmer {{ from {{ background-position: 0px 0; }} to {{ background-position: -320px 0; }} }}
.dl-row {{ display: none; margin: 0 0 12px; }}
.dl-row.on {{ display: block; }}
.dl {{ position: relative; width: 100%; min-height: 2.5rem; padding: .25rem .75rem; border: none; border-radius: 10px;
  background: linear-gradient(135deg, #1A1A1A 0%, #050505 100%); cursor: pointer; display: flex; align-items: center;
  justify-content: center; transition: box-shadow .2s ease; }}
.dl::before {{ content: ""; position: absolute; inset: 0; border-radius: 10px; padding: 2px;
  background: linear-gradient(135deg, #B8860B, #F5D370, #B8860B); background-size: 200% 100%; background-position: 0% 0;
  transition: background-position 1s ease; -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor; mask-composite: exclude; pointer-events: none; }}
.dl:hover {{ box-shadow: 0 0 14px 2px rgba(212, 175, 55, .55); }}
.dl:hover::before {{ background-position: 100% 0; }}
.dl span {{ font-family: "Source Sans", "Source Sans Pro", sans-serif; font-size: .875rem; line-height: 1.6; font-weight: bold;
  background: linear-gradient(90deg, #8a6410 0%, #D4AF37 18%, #FFF0B8 34%, #F5D370 50%, #D4AF37 66%, #B8860B 82%, #8a6410 100%);
  background-size: 320px 100%; background-repeat: repeat-x; animation: bqGoldTextShimmer 5s linear infinite;
  -webkit-background-clip: text; background-clip: text; color: transparent; }}
@media (max-width: 600px) {{
  table {{ font-size: 12.8px; }}
  th, td {{ padding-left: 5px; padding-right: 5px; }}
  td.grip {{ padding-left: 0; padding-right: 0; width: 12px; }}
  td.pl {{ white-space: normal; line-height: 1.2; min-width: 5.2em; }}
  td.pl .fn, td.pl .ln {{ display: block; white-space: nowrap; }}
  td.pic {{ width: 42px; min-width: 42px; }}
  td.pic img, td.pic .noimg {{ width: 38px; height: 28px; }}
  td.sl {{ min-width: 84px; padding-left: 8px; padding-right: 8px; }}
  th.tm {{ white-space: normal; font-size: 11.5px; line-height: 1.25; }}
  th.tm b {{ font-size: 12.5px; }}
}}
</style></head><body>
<div class="dl-row"><button class="dl" type="button"><span>Download .png</span></button></div>
<div class="wrap"><table>
<thead>
<tr><th></th><th></th><th class="l">Player</th><th class="l">Pos</th><th class="tm"><span>TOTAL MINUTES: <b class="tot">0</b>/240</span></th><th>MIN</th><th>MPG</th></tr>
</thead>
<tbody>{''.join(playing)}<tr class="eob"><td colspan="7">End of Bench</td></tr>{''.join(bench)}</tbody></table></div>
<script>
(function () {{
  var TEAM = {json.dumps(team_name)}, SEASON = {json.dumps(season)}, FILE = {json.dumps(file_name)};
  var FILL = {json.dumps(fill)}, HEAD = {json.dumps(head_color)};
  var tbody = document.querySelector('tbody'), eob = tbody.querySelector('tr.eob'), tot = document.querySelector('.tot');
  var dlRow = document.querySelector('.dl-row');
  // "Download .png" is set in Streamlit's own bundled font ("Source Sans"), copied in from the app (same origin) --
  // without it this frame falls back to a wider font and the button looks bigger than every other button.
  (function copyButtonFont() {{
    try {{
      // the button is sized in rem, like Streamlit's own buttons: this frame takes the app's root font size (its
      // baseFontSize), so "Download .png" is exactly as big as every other button on any setup
      var rootPx = parseFloat(window.parent.getComputedStyle(window.parent.document.documentElement).fontSize);
      if (rootPx) document.documentElement.style.fontSize = rootPx + 'px';
    }} catch (e) {{}}
    try {{
      var pd = window.parent.document, css = '';
      for (var i = 0; i < pd.styleSheets.length; i++) {{
        var sheet = pd.styleSheets[i], rules;
        try {{ rules = sheet.cssRules; }} catch (e) {{ continue; }}
        for (var j = 0; j < rules.length; j++) {{
          var rule = rules[j];
          if (rule.type === 5 && /Source Sans/i.test(rule.style.getPropertyValue('font-family'))) {{
            var base = sheet.href || pd.baseURI;
            css += rule.cssText.replace(/url\\((["']?)([^"')]+)\\1\\)/g, function (m, q, u) {{
              try {{ return 'url("' + new URL(u, base).href + '")'; }} catch (e) {{ return m; }}
            }}) + '\\n';
          }}
        }}
      }}
      if (css) {{ var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st); }}
    }} catch (e) {{}}
  }})();
  function rows() {{ return Array.prototype.slice.call(tbody.querySelectorAll('tr.p')); }}
  function above(tr) {{ return !!(tr.compareDocumentPosition(eob) & Node.DOCUMENT_POSITION_FOLLOWING); }}
  function mins(tr) {{ return +tr.querySelector('input').value; }}
  function paint(inp) {{
    inp.style.setProperty('--p', (100 * inp.value / 48) + '%');
    inp.closest('tr').querySelector('td.min').textContent = inp.value;
  }}
  // 0 minutes = End of Bench: below the grey line; a player given minutes again goes back to the end of the rotation
  function place(tr) {{
    if (mins(tr) === 0 && above(tr)) tbody.insertBefore(tr, eob.nextSibling);
    else if (mins(tr) > 0 && !above(tr)) tbody.insertBefore(tr, eob);
  }}
  function total() {{
    var t = 0;
    rows().forEach(function (r) {{ t += mins(r); }});
    tot.textContent = t;
    tot.parentNode.className = t === 240 ? 'ok' : 'bad';   // the span around TOTAL MINUTES
    dlRow.className = 'dl-row' + (t === 240 ? ' on' : '');
    eob.className = 'eob' + (rows().some(function (r) {{ return !above(r); }}) ? '' : ' empty');
  }}
  rows().forEach(function (r) {{
    var i = r.querySelector('input');
    paint(i);
    i.addEventListener('input', function () {{ paint(i); total(); }});
    i.addEventListener('change', function () {{ place(r); total(); }});
  }});
  total();

  // drag a row by its grip to move the player (mouse, pen or finger)
  tbody.addEventListener('pointerdown', function (e) {{
    var grip = e.target.closest('td.grip');
    if (!grip) return;
    e.preventDefault();
    var tr = grip.closest('tr'), id = e.pointerId;
    tr.classList.add('dragging');
    // (listened for on the whole document: moving the row in the table would drop a pointer capture on the grip)
    function move(ev) {{
      if (ev.pointerId !== id) return;
      ev.preventDefault();
      var y = ev.clientY, target = null, list = Array.prototype.slice.call(tbody.children);
      for (var k = 0; k < list.length; k++) {{
        var r = list[k];
        if (r === tr) continue;
        var b = r.getBoundingClientRect();
        if (y < b.top + b.height / 2) {{ target = r; break; }}
      }}
      if (target !== tr.nextSibling && target !== tr) tbody.insertBefore(tr, target);
    }}
    function up(ev) {{
      if (ev.pointerId !== id) return;
      tr.classList.remove('dragging');
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', up);
      document.removeEventListener('pointercancel', up);
      place(tr);
      total();
    }}
    document.addEventListener('pointermove', move, {{ passive: false }});
    document.addEventListener('pointerup', up);
    document.addEventListener('pointercancel', up);
  }});

  // the picture: the rotation in its current order, End of Bench left out; see-through background like every other
  // download in the dashboard
  function drawPicture() {{
    var act = rows().filter(function (r) {{ return above(r) && mins(r) > 0; }});
    var S = 2, W = 820, rowH = 48, top = 96, H = top + act.length * rowH + 14;
    var c = document.createElement('canvas');
    c.width = W * S; c.height = H * S;
    var g = c.getContext('2d');
    g.scale(S, S);
    g.textBaseline = 'middle';
    g.fillStyle = '#ffffff'; g.font = '700 24px Arial, sans-serif'; g.textAlign = 'left';
    g.fillText(TEAM + ' Rotation', 0, 22);
    g.fillStyle = '#9a9a9a'; g.font = '400 14px Arial, sans-serif';
    g.fillText(SEASON, 0, 48);
    var X = {{ pic: 0, name: 60, pos: 300, bar: 350, barW: 330, min: 740, mpg: W }};
    var hy = 78;
    // "TOTAL MINUTES: 240/240" above the bars, as on the page
    g.textAlign = 'center'; g.font = '700 13px Arial, sans-serif'; g.fillStyle = '#2ECC71';
    g.fillText('TOTAL MINUTES: 240/240', X.bar + X.barW / 2, hy);
    g.fillStyle = HEAD; g.font = '700 13px Arial, sans-serif'; g.textAlign = 'left';
    g.fillText('Player', X.name, hy); g.fillText('Pos', X.pos, hy);
    g.textAlign = 'right'; g.fillText('MIN', X.min, hy); g.fillText('MPG', X.mpg, hy);
    g.fillStyle = '#3a3730'; g.fillRect(0, top - 6, W, 1);
    act.forEach(function (r, k) {{
      var y = top + k * rowH, cy = y + rowH / 2 - 3;
      var img = r.querySelector('td.pic img');
      if (img && img.complete && img.naturalWidth) {{
        var bw = 50, bh = 37, s = Math.max(bw / img.naturalWidth, bh / img.naturalHeight);
        var sw = bw / s, sh = bh / s;
        g.drawImage(img, (img.naturalWidth - sw) / 2, 0, sw, sh, X.pic, cy - bh / 2, bw, bh);
      }}
      g.textAlign = 'left'; g.fillStyle = '#f0f0f0'; g.font = '700 16px Arial, sans-serif';
      g.fillText(r.getAttribute('data-name'), X.name, cy);
      g.fillStyle = '#e6e6e6'; g.font = '400 15px Arial, sans-serif';
      g.fillText(r.getAttribute('data-pos'), X.pos, cy);
      var m = mins(r);
      g.fillStyle = '#2a2a2a'; g.fillRect(X.bar, cy - 4, X.barW, 8);
      g.fillStyle = FILL; g.fillRect(X.bar, cy - 4, X.barW * m / 48, 8);
      g.textAlign = 'right'; g.fillStyle = '#ffffff'; g.font = '700 16px Arial, sans-serif';
      g.fillText(String(m), X.min, cy);
      g.fillStyle = '#7d7d7d'; g.font = '400 15px Arial, sans-serif';
      g.fillText(r.getAttribute('data-mpg'), X.mpg, cy);
      g.fillStyle = '#242424'; g.fillRect(0, y + rowH - 4, W, 1);
    }});
    return c;
  }}
  document.querySelector('.dl').addEventListener('click', function () {{
    var c = drawPicture();
    function save(url) {{
      var a = document.createElement('a');
      a.href = url; a.download = FILE;
      document.body.appendChild(a); a.click(); a.remove();
    }}
    if (c.toBlob) c.toBlob(function (b) {{ save(URL.createObjectURL(b)); }}, 'image/png');
    else save(c.toDataURL('image/png'));
  }});
  window.__baRotationPicture = drawPicture;                 // (for checking the picture)
}})();
</script></body></html>"""
    # sized to its real content (no empty space under the table, on a phone or a desktop)
    try:
        st.iframe(_doc, height="content")
    except Exception:
        components.html(_doc, height=height, scrolling=False)


def _team_payrolls(team_name):
    """{season: committed salary} for this team, the current league year and the five after it (the Salary Cap tab's
    totals, including dead money) -- {} if it can't be worked out."""
    try:
        team_id = TEAM_NAME_TO_RECORD[team_name]["id"]
        abbr = TEAM_NAME_TO_RECORD[team_name]["abbreviation"]
        y0 = _cap_year_start()
        seasons = [f"{y}-{str(y + 1)[-2:]}" for y in range(y0, min(y0 + 5, 2033) + 1)]
        roster = None
        for s_ in dict.fromkeys([seasons[0], _stats_config.default_season()]):
            try:
                roster = get_team_roster(team_id, s_)
            except Exception:
                roster = None
            if roster is not None and not roster.empty:
                break
        ids = roster["PLAYER_ID"].tolist() if roster is not None and "PLAYER_ID" in roster.columns else []
        names = roster["PLAYER"].tolist() if roster is not None and "PLAYER" in roster.columns else []
        rows, totals = salary_table.team_contracts(_load_salary_table(), abbr, seasons, ids, names)
        return {s_: totals[s_] for s_ in seasons if rows and totals.get(s_)}
    except Exception:
        return {}


def _include_picker(mode, key, label=None):
    """"Enter player(s) to include (optional):" -- a menu of every player (or team) that narrows as you type; each
    one picked becomes a chip, like picking several stats. Teams are listed by name in a menu here, not the logo grid
    the app's other team pickers use (their ids are the menu's values, so ui_hooks leaves it a plain menu)."""
    noun = "player" if mode == "player" else "team"
    label = label or f"Enter {noun}(s) to include (optional):"
    if mode == "player":
        return st.multiselect(label, ALL_PLAYER_NAMES, key=key)
    id_to_name = {TEAM_NAME_TO_RECORD[n]["id"]: n for n in ALL_TEAM_NAMES}
    picked = st.multiselect(label, list(id_to_name), format_func=lambda i: id_to_name.get(i, str(i)), key=key)
    return [id_to_name[i] for i in picked if i in id_to_name]


def _rows_named(df, names, name_col):
    """The rows of `df` for these players/teams (accents and case ignored), in the order given."""
    if df is None or df.empty or not names or name_col not in df.columns:
        return df.iloc[0:0] if df is not None else pd.DataFrame()
    folded = df[name_col].astype(str).map(lambda n: _fold_accents(n).lower())
    keep = []
    for n in names:
        hit = df.index[folded == _fold_accents(str(n)).lower()]
        if len(hit):
            keep.append(hit[0])
    return df.loc[keep]


def _formula_scores(components, community_formulas, kind, season):
    """Every player (or team) of the season with this formula's rating: the same 0-100 number the single-subject
    version gives -- each stat's percentile rank across the league, times its weight, added up (a community formula's
    own stats one level deep). Returns (DataFrame [id, name, GP, rating], note) -- players are kept only with at least
    40% of the most games anyone played, so a handful of minutes can't top the list."""
    name_col = "PLAYER_NAME" if kind == "player" else "TEAM_NAME"
    id_col = "PLAYER_ID" if kind == "player" else "TEAM_ID"
    tables = {}
    side = {"bio": get_player_bio_stats, "defense_tracking": get_player_defense_stats,
            "hustle": get_player_hustle_stats, "clutch": get_player_clutch_stats}

    def table(stat_mode, source):
        if source == "salary" or ratings_data.is_source(source):
            key = (source, None)
            if key not in tables:
                tables[key] = fetch_stats_for_source(source, season, kind)
        elif source in side:
            key = (source, None)
            if key not in tables:
                tables[key] = side[source](season) if kind == "player" else None
        else:
            key = ("league", stat_mode)
            if key not in tables:
                tables[key] = (get_player_stats(season, per_mode=stat_mode) if kind == "player"
                               else get_team_stats(season, per_mode=stat_mode))
        return tables[key]

    league = table("PerGame", "base")
    if league is None or league.empty or name_col not in league.columns:
        return pd.DataFrame(), ""
    cols = [c for c in (id_col, name_col, "GP") if c in league.columns]
    out = league[cols].drop_duplicates(subset=[id_col] if id_col in cols else [name_col]).reset_index(drop=True)
    out["rating"] = 0.0

    def pct_for(df, field):
        """Each subject's percentile for `field` in `df`, lined up with `out` (NaN where missing)."""
        if df is None or df.empty or field not in df.columns:
            return pd.Series([float("nan")] * len(out))
        vals = pd.to_numeric(df[field], errors="coerce")
        ranks = vals.rank(pct=True) * 100
        if id_col in df.columns and id_col in out.columns:
            m = dict(zip(pd.to_numeric(df[id_col], errors="coerce"), ranks))
            return pd.to_numeric(out[id_col], errors="coerce").map(m)
        m = dict(zip(df[name_col].map(_fold_accents), ranks)) if name_col in df.columns else {}
        return out[name_col].map(_fold_accents).map(m)

    for comp in components:
        if comp["kind"] == "stat":
            p = pct_for(table(comp.get("stat_mode", "PerGame"), comp.get("source", "base")), comp["field"])
            out["rating"] += p.fillna(0) * comp["weight"]
        else:
            sub = next((f for f in community_formulas if f["id"] == comp.get("formula_id")), None)
            if not sub:
                continue
            sub_total = pd.Series([0.0] * len(out))
            for sc in sub.get("formula_data", []):
                if sc.get("kind") != "stat":
                    continue
                p = pct_for(table(sc.get("stat_mode", "PerGame"), sc.get("source", "base")), sc["field"])
                sub_total += p.fillna(0) * sc["weight"]
            out["rating"] += sub_total * comp["weight"]
    note = ""
    if kind == "player" and "GP" in out.columns:
        gp = pd.to_numeric(out["GP"], errors="coerce")
        need = max(1, int(round(0.4 * (gp.max() or 0))))
        out = out[gp >= need]
        note = f"Players with {need}+ games in {season}."
    return out.reset_index(drop=True), note


def _formula_best_chart(components, community_formulas, kind, season, top_n, stat_name):
    """The top players (or teams) of a season by this formula, as a bar chart."""
    if not components:
        return
    with code_loading_animation("Calculating every " + ("player" if kind == "player" else "team")):
        try:
            scores, note = _formula_scores(components, community_formulas, kind, season)
        except Exception as e:
            st.error(f"Couldn't calculate this formula: {friendly_error(e)}")
            return
    if scores.empty:
        st.error(f"No {season} data found.")
        return
    name_col = "PLAYER_NAME" if kind == "player" else "TEAM_NAME"
    id_col = "PLAYER_ID" if kind == "player" else "TEAM_ID"
    top = scores.nlargest(int(top_n), "rating")
    board = pd.DataFrame({"name": top[name_col].values, "player_id": top[id_col].values, "value": top["rating"].values})
    board["image_url"] = board["player_id"].apply(get_player_headshot_url if kind == "player" else get_team_logo_url)
    board["is_included"] = True
    fig = build_bar_chart(board, stat_display_name=stat_name, season=season, top_n=int(top_n), team_color="#D4AF37",
                          stat_source="formula", decimals=1)
    drawn = board.sort_values("value", ascending=False).reset_index(drop=True)
    show_chart(fig, _hover(hover.bar_chart_hotspots, fig.axes[0], drawn["name"].tolist(), drawn["value"].tolist(),
                           stat_name), "formula_best")
    if note:
        st.caption(note)
    add_to_tableau_dashboard(fig, "Stat Formula Creator", "tableau_formula_best")
    plt.close(fig)


def render_front_office_cba_guide(team_name):
    """The CBA itself as a download, then the whole guide to it (cba_guide.py): every salary-cap rule, with charts, and
    where this team stands."""
    import cba_guide
    st.markdown("### NBA Collective Bargaining Agreement")
    st.markdown(
        "<span style=\"font-family:Arial, sans-serif; color:#999999; font-size:0.9rem;\">CBA 2023 \u2013 2029</span>",
        unsafe_allow_html=True,
    )
    pdf_path = os.path.join(os.path.dirname(__file__), "assets", "NBA-Collective-Bargaining-Agreement.pdf")
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
    except FileNotFoundError:
        pdf_bytes = None
    if pdf_bytes:
        st.download_button("Download the full PDF", data=pdf_bytes, file_name="NBA-Collective-Bargaining-Agreement.pdf",
                           mime="application/pdf")
    with code_loading_animation(f"Downloading {team_name}'s contracts"):
        payrolls = _team_payrolls(team_name)
    cba_guide.render(team_name, get_team_color(team_name), payrolls)


def color_input_with_dropdown(widget_key: str, default_team: str = None, show_text_color_toggle: bool = True, label: str = "Color:") -> str:
    """
    The visualization colour picker: a grid of all 30 team logos (alphabetical by team name, each in a ring of that
    team's own colour -- see team_grid.py) plus White / Black / Gold swatches, and a field for an exact hex code, which
    wins if filled in. Returns a team's full name, "White", "Black", "Gold" or the typed code ("" if nothing chosen).

    default_team: pre-selects this team (e.g. the subject player's
    actual team for the selected season, or the subject team itself)
    instead of leaving the dropdown empty. The caller's widget_key
    must vary with whatever determines default_team (player+season,
    or team) -- Streamlit widgets keep whatever the user last picked
    in session_state once a key has been used once, so a fixed key
    would keep showing a stale team from a previous player/season
    instead of ever re-applying a new default.
    """
    # White/Black/Gold as special options at the top of every color
    # dropdown, explicitly requested -- resolved directly by
    # resolve_color_input() above, bypassing the team-name lookup
    # entirely since none of these are real teams.
    # A grid of every team's logo (each in a ring of that team's own colour) with White / Black / Gold swatches on a line of their own above them, instead of a
    # dropdown of team names. Returns the same values the dropdown did: a team's full name, "White", "Black" or "Gold".
    # A dropdown like the Trade Machine's team boxes: closed, it shows the chosen logo (in a ring of its team's colour)
    # and name; open, White / Black / Gold on the first line and the 30 teams under them (10 across, 5 on a phone).
    # On a computer the two share one line, half the width each (the box's open logo panel goes full width under
    # them); on a phone (where Streamlit stacks columns) the code field sits just under the box, as before.
    row_key = "ba_color_row_" + re.sub(r"[^A-Za-z0-9_]", "_", str(widget_key))
    # (the code field as tall as the box beside it)
    st.markdown(f"<style>.st-key-{row_key} [data-testid='stTextInputRootElement'] {{ height: 2.6rem; min-height: 2.6rem; }}"
                "</style>", unsafe_allow_html=True)
    with st.container(key=row_key):
        c_dd, c_hex = st.columns(2, vertical_alignment="bottom", gap="small")
    panel_slot = st.container()
    with c_dd:
        picked_team = team_grid.color_dropdown(label, widget_key, default=default_team, panel_container=panel_slot)
    with c_hex:
        hex_typed = st.text_input(
            "Or enter a color code instead:", key=widget_key + "_hex",
            placeholder="...or enter a color code instead.", label_visibility="collapsed",
        )
    # Each call site gets its own uniquely-keyed widget (required --
    # Head-to-Head calls this function twice per render, once per
    # subject, and a fixed shared key would raise a DuplicateWidgetID
    # error), but every instance funnels its value into one shared
    # session_state variable, which is what the st.pyplot monkey-patch
    # actually reads. Effectively one preference across the whole app,
    # not per-chart, even though each widget instance is technically
    # independent.
    if hex_typed:
        return hex_typed
    if picked_team:
        return picked_team
    return ""


def _subject_image_url(mode, subject_name):
    """
    A player's headshot or a team's logo, by mode -- shared by every
    single-subject chart that shows an optional image_url header
    (Waterfall, Tornado, and others), rather than repeating the same
    mode-branch and dict lookup at each call site individually.
    Returns None if the subject can't be resolved, so the caller can
    omit the image entirely rather than pass a broken URL.
    """
    if not subject_name:
        return None
    if mode == "player":
        record = PLAYER_NAME_TO_RECORD.get(subject_name)
        return get_player_headshot_url(record["id"]) if record else None
    record = TEAM_NAME_TO_RECORD.get(subject_name)
    return get_team_logo_url(record["id"]) if record else None


def _seasons_for_dropdown(mode, subject_name):
    """
    The season list a "Season:" dropdown should actually offer --
    limited to a specific player's real career span in player mode
    (so someone can't pick a season before they entered the league or
    after they left it), or the full league-wide ALL_SEASONS in team
    mode (teams don't have the same "career span" concept a player
    does) or if the per-player lookup fails for any reason.
    """
    if mode == "player" and subject_name:
        player_id = PLAYER_NAME_TO_RECORD.get(subject_name, {}).get("id")
        if player_id:
            real_seasons = get_player_career_seasons(player_id)
            if real_seasons:
                # a player still in the league also gets the upcoming season (listed from July 1, before its games)
                real_seasons = list(real_seasons)
                newest = ALL_SEASONS[0] if ALL_SEASONS else None
                if (newest and newest not in real_seasons and _stats_config.default_season() in real_seasons
                        and PLAYER_NAME_TO_RECORD.get(subject_name, {}).get("is_active")):
                    real_seasons = [newest] + real_seasons
                return real_seasons
    return ALL_SEASONS


def _default_color_team(mode, subject_name, season=None):
    """
    Which team should pre-fill the color dropdown for a given
    player/team + season combination -- the subject team itself in
    team mode, or the player's actual team for that specific season in
    player mode (not just their current team, since a player may have
    since been traded). Returns None (leaving the dropdown empty) on
    any lookup failure rather than guessing, and requires a season in
    player mode since "which team did they finish with" isn't
    meaningful without one.
    """
    if not subject_name:
        return None
    if mode == "team":
        return subject_name
    if not season:
        return None
    player_id = PLAYER_NAME_TO_RECORD.get(subject_name, {}).get("id")
    if not player_id:
        return None
    abbrev = get_player_team_for_season(player_id, season)
    if not abbrev:
        # No season-ending row exists yet -- either the season hasn't
        # started at all (nothing to look up), or some other lookup
        # failure. Either way, "the team he's currently on" is a
        # better default than leaving the dropdown empty. (An
        # in-progress season doesn't need this fallback at all:
        # PlayerCareerStats already has a row reflecting the player's
        # standing so far, which get_player_team_for_season() would
        # have already returned above.)
        abbrev = get_player_current_team(player_id)
    return TEAM_ABBREVIATION_TO_NAME.get(abbrev) if abbrev else None


# ---------------------------------------------------------------- Lineups: league-wide ranks
def _lineup_id_set(group_id):
    """NBA lineup GROUP_ID ("-1628369-1627759-") -> frozenset of player ids (None if it can't be read)."""
    ids = []
    for part in str(group_id or "").strip("-").split("-"):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return frozenset(ids) if ids else None


def _league_lineups(season, size):
    """Every lineup of this size in the league this season: Advanced ratings with minutes (MIN) and plus-minus
    merged in from the Base call when the Advanced one lacks them. Empty DataFrame if it can't be loaded."""
    try:
        lg = get_league_lineup_combos(season, group_quantity=size, measure_type="Advanced")
    except Exception:
        return pd.DataFrame()
    if lg is None or lg.empty or "GROUP_ID" not in lg.columns:
        return pd.DataFrame()
    lg = lg.copy()
    missing = [c for c in ("MIN", "PLUS_MINUS") if c not in lg.columns]
    if missing:
        try:
            base = get_league_lineup_combos(season, group_quantity=size, measure_type="Base")
            keys = ["GROUP_ID"] + (["TEAM_ID"] if "TEAM_ID" in lg.columns and "TEAM_ID" in base.columns else [])
            have = [c for c in missing if c in base.columns]
            if have:
                lg = lg.merge(base[keys + have].drop_duplicates(keys), on=keys, how="left")
        except Exception:
            pass
    return lg


def _team_lineup_frame(team_id, season, size):
    """One team's every N-man lineup: Advanced ratings, with minutes together (MIN) taken from the Base numbers."""
    frame = get_team_lineup_combos(team_id, season, group_quantity=size, measure_type="Advanced")
    try:
        base = get_team_lineup_combos(team_id, season, group_quantity=size, measure_type="Base")
        if "MIN" in base.columns and "GROUP_NAME" in base.columns:
            frame = frame.drop(columns=["MIN"], errors="ignore").merge(base[["GROUP_NAME", "MIN"]], on="GROUP_NAME",
                                                                       how="left")
    except Exception:  # noqa: BLE001
        pass
    for f, _lbl, _low in criteria_tools.LINEUP_STATS:
        if f in frame.columns:
            frame[f] = pd.to_numeric(frame[f], errors="coerce")
    return frame


def _lineup_league_ranks(season, size, min_minutes, value_col):
    """
    {frozenset(player ids): (rank, pool size)} -- each lineup's rank by value_col (higher is better) among every
    lineup of this size in the league that played at least min_minutes together this season. {} if the league-wide
    lineup data can't be loaded (the pop-ups then just don't show a league rank).
    """
    lg = _league_lineups(season, size)
    if lg.empty or value_col not in lg.columns:
        return {}
    lg = lg[pd.to_numeric(lg[value_col], errors="coerce").notna()].copy()
    if "MIN" in lg.columns:
        lg = lg[pd.to_numeric(lg["MIN"], errors="coerce").fillna(0) >= float(min_minutes or 0)]
    if lg.empty:
        return {}
    ranks = pd.to_numeric(lg[value_col], errors="coerce").rank(ascending=False, method="min")
    pool = len(lg)
    out = {}
    names = lg["GROUP_NAME"] if "GROUP_NAME" in lg.columns else [None] * len(lg)
    team_ids = lg["TEAM_ID"] if "TEAM_ID" in lg.columns else [None] * len(lg)
    for gid, gname, tid, rank in zip(lg["GROUP_ID"], names, team_ids, ranks):
        ids = _lineup_id_set(gid)
        if ids and ids not in out:
            out[ids] = (int(rank), pool)
        # also by team + the abbreviated names, for a team table that comes back without GROUP_ID
        if gname is not None and tid is not None and pd.notna(tid):
            key = (int(tid), frozenset(p.strip() for p in str(gname).split(" - ")))
            out.setdefault(key, (int(rank), pool))
    return out


# ---------------------------------------------------------------- Passing Web (shared by its own page and Search by Criteria)
# League-typical FG% per area -- only used to steady a receiver's own FG% where he took few shots, or in place of it
# when his shot chart can't be loaded.
_PASS_ZONE_REF_FG = {"ra": 0.64, "paint": 0.44, "lmid_base": 0.41, "rmid_base": 0.41, "lmid_wing": 0.41,
                     "rmid_wing": 0.41, "mid_c": 0.42, "lc3": 0.39, "rc3": 0.39, "lw3": 0.36, "rw3": 0.36, "top3": 0.35}
_PASS_SELF_CREATED = ("pullup", "pull-up", "pull up", "step back", "step-back", "driving", "fadeaway", "turnaround",
                      "floating", "putback", "tip ", "tip shot", "tip dunk", "tip layup")


def _reformat_last_first(name):
    """PlayerDashPtPass names receivers "Last, First" -> "First Last", accent-stripped like PLAYER_NAME_TO_RECORD."""
    name = str(name)
    if "," in name:
        last, first = (p.strip() for p in name.split(",", 1))
        name = f"{first} {last}"
    return _strip_accents(name)


def _pbp_assisted_xy(assisted, rid, r_shots):
    """
    The baskets a passer assisted to one receiver, from the NBA's play-by-play rows (get_passer_assisted_shots*), as a
    DataFrame of X / Y / SHOT_VALUE / ZONE in shot-chart coordinates. Each basket is pinned to the receiver's own
    shot-chart row (same game, period and clock) so its area is the NBA's own zone; baskets that can't be pinned use
    the play-by-play's coordinates, turned the same way as the ones that could. None if there's nothing to go on.
    """
    if assisted is None:
        return None
    if assisted.empty:
        return pd.DataFrame(columns=["X", "Y", "SHOT_VALUE", "ZONE"])
    if "PLAYER_ID" not in assisted.columns:
        return None
    mine = assisted[assisted["PLAYER_ID"] == rid]
    if mine.empty:
        return pd.DataFrame(columns=["X", "Y", "SHOT_VALUE", "ZONE"])
    have_cols = r_shots is not None and {"SHOT_ZONE_BASIC", "SHOT_ZONE_AREA", "LOC_X", "LOC_Y", "GAME_ID", "PERIOD",
                                         "MINUTES_REMAINING", "SECONDS_REMAINING"}.issubset(r_shots.columns)
    made_rows = {}
    if have_cols:
        made = r_shots[r_shots["SHOT_MADE_FLAG"] == 1] if "SHOT_MADE_FLAG" in r_shots.columns else r_shots
        for rec in made.to_dict("records"):
            made_rows.setdefault((str(rec["GAME_ID"]), int(rec["PERIOD"])), []).append(rec)
    out, loose, same_side, flipped = [], [], 0, 0
    for a in mine.to_dict("records"):
        x, y = a.get("X_LEGACY"), a.get("Y_LEGACY")
        x = None if x is None or pd.isna(x) else float(x)
        y = None if y is None or pd.isna(y) else float(y)
        value = int(a.get("SHOT_VALUE") or 2)
        clock = a.get("CLOCK_SEC")
        best = None
        if clock is not None and not pd.isna(clock):
            cands = [r for r in made_rows.get((str(a["GAME_ID"]), int(a["PERIOD"])), []) if not r.get("_used") and
                     abs(int(r["MINUTES_REMAINING"]) * 60 + int(r["SECONDS_REMAINING"]) - int(clock)) <= 1]
            if cands and x is not None and y is not None:
                best = min(cands, key=lambda r: min(math.hypot(r["LOC_X"] - x, r["LOC_Y"] - y),
                                                    math.hypot(r["LOC_X"] + x, r["LOC_Y"] - y)))
            elif len(cands) == 1:
                best = cands[0]
        if best is not None:
            best["_used"] = True
            out.append({"X": float(best["LOC_X"]), "Y": float(best["LOC_Y"]), "SHOT_VALUE": value,
                        "ZONE": court_zone_key(best["SHOT_ZONE_BASIC"], best["SHOT_ZONE_AREA"], best["LOC_X"])})
            if x is not None and abs(x) >= 20 and abs(best["LOC_X"]) >= 20:
                if (x < 0) == (best["LOC_X"] < 0):
                    same_side += 1
                else:
                    flipped += 1
        elif x is not None and y is not None:
            loose.append((x, y, value))
    sign = -1 if flipped > same_side else 1
    for x, y, value in loose:
        out.append({"X": sign * x, "Y": y, "SHOT_VALUE": value, "ZONE": None})
    return pd.DataFrame(out, columns=["X", "Y", "SHOT_VALUE", "ZONE"])


def _passing_zone_stats(made_xy, r_shots):
    """
    Where one receiver shot right after a passer's passes: (top area, {area: {"made", "att", "share"}}, baskets used),
    or None if fewer than 3 baskets. Made baskets are counted by area, then turned into attempts with his own FG% in
    each area (steadied toward league-typical where he took few shots) -- the NBA only names the passer on made
    baskets, so misses after a pass can only be estimated. The area with the most estimated attempts is his spot.
    """
    if made_xy is None or len(made_xy) < 3:
        return None
    zones = []
    for rec in made_xy.to_dict("records"):
        z = rec.get("ZONE")
        if not (isinstance(z, str) and z):      # (pandas 3 turns a missing zone into NaN, which is "truthy")
            z = court_zone_key_for_shot(float(rec["X"]), float(rec["Y"]), rec.get("SHOT_VALUE"))
        if z:
            zones.append(z)
    made_by_zone = pd.Series(zones).value_counts() if zones else pd.Series(dtype=int)
    if made_by_zone.empty:
        return None
    fg = {}
    if r_shots is not None and {"SHOT_ZONE_BASIC", "SHOT_ZONE_AREA", "LOC_X", "SHOT_MADE_FLAG"}.issubset(r_shots.columns):
        keys = [court_zone_key(b, ar, lx) for b, ar, lx in
                zip(r_shots["SHOT_ZONE_BASIC"], r_shots["SHOT_ZONE_AREA"], r_shots["LOC_X"])]
        tally = pd.DataFrame({"z": keys, "m": r_shots["SHOT_MADE_FLAG"].astype(float)}).dropna()
        for z, g in tally.groupby("z"):
            fg[z] = (g["m"].sum() + 8 * _PASS_ZONE_REF_FG.get(z, 0.45)) / (len(g) + 8)
    attempts = {z: n / max(0.15, fg.get(z, _PASS_ZONE_REF_FG.get(z, 0.45))) for z, n in made_by_zone.items()}
    total = sum(attempts.values())
    stats = {z: {"made": int(made_by_zone[z]), "att": attempts[z], "share": attempts[z] / total} for z in attempts}
    top = max(attempts, key=lambda z: (attempts[z], made_by_zone[z]))
    return top, stats, int(made_by_zone.sum())


def _zone_centroid(made_xy, zone):
    """Average court position of the baskets (X / Y / SHOT_VALUE / ZONE rows) that fall in one area, or None."""
    if made_xy is None or len(made_xy) == 0 or not zone:
        return None
    xs, ys = [], []
    for rec in made_xy.to_dict("records"):
        z = rec.get("ZONE")
        if not (isinstance(z, str) and z):
            z = court_zone_key_for_shot(float(rec["X"]), float(rec["Y"]), rec.get("SHOT_VALUE"))
        if z == zone:
            xs.append(float(rec["X"]))
            ys.append(float(rec["Y"]))
    return (sum(xs) / len(xs), sum(ys) / len(ys)) if xs else None


def _shots_centroid(r_shots, zone):
    """Average court position of a player's own shot-chart shots in one area (the catch-spot fallback), or None."""
    if r_shots is None or r_shots.empty or not zone or \
            not {"SHOT_ZONE_BASIC", "SHOT_ZONE_AREA", "LOC_X", "LOC_Y"}.issubset(r_shots.columns):
        return None
    keys = [court_zone_key(b, a, x) for b, a, x in
            zip(r_shots["SHOT_ZONE_BASIC"], r_shots["SHOT_ZONE_AREA"], r_shots["LOC_X"])]
    sel = r_shots[[k == zone for k in keys]]
    if sel.empty:
        return None
    return float(sel["LOC_X"].astype(float).mean()), float(sel["LOC_Y"].astype(float).mean())


def _catch_spot(r_shots):
    """Fallback spot: the area a receiver shoots from most off a catch (his own shots minus self-created ones)."""
    if r_shots is None or r_shots.empty or not {"SHOT_ZONE_BASIC", "SHOT_ZONE_AREA", "LOC_X"}.issubset(r_shots.columns):
        return None
    df = r_shots
    if "ACTION_TYPE" in df.columns:
        kinds = df["ACTION_TYPE"].astype(str).str.lower()
        caught = df[~kinds.apply(lambda t: any(k in t for k in _PASS_SELF_CREATED))]
        if len(caught) >= 10:
            df = caught
    spots = pd.Series([sp for sp in (court_zone_key(b, a, x) for b, a, x in
                       zip(df["SHOT_ZONE_BASIC"], df["SHOT_ZONE_AREA"], df["LOC_X"])) if sp])
    return spots.value_counts().idxmax() if not spots.empty else None


def _own_zone_stats(r_shots):
    """A receiver's own shots by Passing Web area -- the ones he took off a catch (his shot chart minus self-created
    shots) when there are enough of them, else all of them: {area: {"made", "att", "share"}}, or {} with no shots.
    The pop-up's court for a teammate whose assisted baskets from this passer couldn't be counted."""
    if r_shots is None or r_shots.empty or not {"SHOT_ZONE_BASIC", "SHOT_ZONE_AREA", "LOC_X"}.issubset(r_shots.columns):
        return {}
    df = r_shots
    if "ACTION_TYPE" in df.columns:
        kinds = df["ACTION_TYPE"].astype(str).str.lower()
        caught = df[~kinds.apply(lambda t: any(k in t for k in _PASS_SELF_CREATED))]
        if len(caught) >= 10:
            df = caught
    keys = [court_zone_key(b, a, x) for b, a, x in zip(df["SHOT_ZONE_BASIC"], df["SHOT_ZONE_AREA"], df["LOC_X"])]
    made = df["SHOT_MADE_FLAG"].astype(float).tolist() if "SHOT_MADE_FLAG" in df.columns else [0.0] * len(keys)
    tally = {}
    for z, m in zip(keys, made):
        if z:
            t = tally.setdefault(z, [0, 0.0])
            t[0] += 1
            t[1] += m
    total = sum(t[0] for t in tally.values())
    if not total:
        return {}
    return {z: {"made": int(t[1]), "att": float(t[0]), "share": t[0] / total} for z, t in tally.items()}


def render_passing_web(picked_name, player_id, season, top_n=5, rank_ascending=False, color_input=None,
                       key="passing_web", show_explainer=True, only_receiver=None):
    """
    The whole Passing Web for one passer: his top passing connections (NBA tracking), each teammate placed in the court
    area where he took the most shots right after this passer's passes, the chart with its hover pop-ups (a mini court
    of where each teammate's shots came from), and the "How each player was placed" box.

    Where each teammate shot off this passer's passes comes from pbpstats.com's shot log (every basket the passer
    assisted to him, with its exact court position -- one small request per teammate, reachable from the cloud). Any
    teammate it can't answer for falls back to the NBA's own play-by-play, then to where he shoots most off a catch.
    """
    with code_loading_animation("Downloading passing data"):
        try:
            passes_df = get_player_passes(player_id, season)
        except Exception as e:
            st.error(f"Couldn't load passing data for {picked_name} in {season}: {friendly_error(e)}")
            return
    if passes_df is None or passes_df.empty or "PASS_TO" not in passes_df.columns:
        st.error(f"No passing data found for {picked_name} in {season}.")
        return
    passes_df = passes_df.copy()
    passes_df["PASS"] = pd.to_numeric(passes_df["PASS"], errors="coerce")
    passes_df = passes_df.dropna(subset=["PASS"])
    if only_receiver:
        # just this passer -> this teammate (Search by Team's optional "Receiver")
        want = _strip_accents(str(only_receiver)).lower().strip()
        passes_df = passes_df[passes_df["PASS_TO"].map(lambda n: _strip_accents(_reformat_last_first(n)).lower().strip() == want)]
        if passes_df.empty:
            st.warning(f"No passes from {picked_name} to {only_receiver} in {season} in the NBA's tracking data.")
            return
    top_passes = passes_df.nsmallest(int(top_n), "PASS") if rank_ascending else passes_df.nlargest(int(top_n), "PASS")

    # PlayerDashPtPass names receivers "Last, First"; the rest of the app is keyed by accent-stripped "First Last".
    receiver_names = [_reformat_last_first(n) for n in top_passes["PASS_TO"].tolist()]
    receiver_values = top_passes["PASS"].tolist()
    receiver_makes = top_passes["FGM"].tolist() if "FGM" in top_passes.columns else [0] * len(receiver_names)
    if "FGA" in top_passes.columns and "FG3A" in top_passes.columns:
        receiver_extra_stats = [{"fga": float(row["FGA"]), "fg3a": float(row["FG3A"])} for _, row in top_passes.iterrows()]
    else:
        receiver_extra_stats = [None] * len(receiver_names)
    passer_image_url = get_player_headshot_url(player_id)
    receiver_image_urls = []
    raw_ids = (top_passes["PASS_TEAMMATE_PLAYER_ID"].tolist() if "PASS_TEAMMATE_PLAYER_ID" in top_passes.columns
               else [None] * len(receiver_names))
    receiver_ids = []
    for name, rid in zip(receiver_names, raw_ids):
        record = PLAYER_NAME_TO_RECORD.get(name)
        receiver_image_urls.append(get_player_headshot_url(record["id"]) if record else None)
        try:
            rid = int(rid) if rid is not None and pd.notna(rid) else (record["id"] if record else None)
        except (TypeError, ValueError):
            rid = record["id"] if record else None
        receiver_ids.append(rid)
    passer_last = _last_name(picked_name)

    # 1) every basket this passer assisted to each teammate, with its court position (pbpstats.com)
    with code_loading_animation(f"Finding where {passer_last}'s assists to each teammate were shot"):
        try:
            assisted = get_assisted_shots_for_receivers(int(player_id), tuple(r for r in receiver_ids if r), season) or {}
        except Exception:
            assisted = {}
        # each teammate's own shot chart: his FG% in every area (turns made baskets into attempts), and the fallback
        r_shots_by_id = {}
        for rid in receiver_ids:
            if rid:
                try:
                    r_shots_by_id[rid] = get_player_shots(rid, season)
                except Exception:
                    r_shots_by_id[rid] = None
    # A season pbpstats hasn't loaded comes back empty rather than as an error: a teammate the NBA's tracking credits
    # with 3+ assisted baskets from this passer but who has (almost) none in pbpstats is treated as not answered, so
    # the NBA play-by-play below is used for him instead.
    ast_by_id = {}
    if "AST" in top_passes.columns:
        for rid, a in zip(receiver_ids, pd.to_numeric(top_passes["AST"], errors="coerce").tolist()):
            ast_by_id[rid] = a
    for rid, df in list(assisted.items()):
        if df is not None and len(df) < 3 and (ast_by_id.get(rid) or 0) >= 3:
            assisted[rid] = None
    source_by_id = {rid: "pbpstats" for rid, df in assisted.items() if df is not None}

    # 2) teammates pbpstats couldn't answer for: the NBA's own play-by-play (live feed first, then the stats site)
    missing = [rid for rid in receiver_ids if rid and assisted.get(rid) is None]
    pbp_label = None
    if missing:
        try:
            passer_shots = get_player_shots(player_id, season)
            passer_games = tuple(sorted(set(passer_shots["GAME_ID"]))) if "GAME_ID" in passer_shots.columns else ()
        except Exception:
            passer_games = ()
        pbp_rows = None
        if passer_games:
            with code_loading_animation("Reading every game's play-by-play"):
                try:
                    pbp_rows = get_passer_assisted_shots(int(player_id), season, passer_games, passer_last)
                    pbp_label = "the NBA's live play-by-play"
                except Exception:
                    try:
                        pbp_rows = get_passer_assisted_shots_v3(int(player_id), season, passer_games, passer_last)
                        pbp_label = "the NBA stats site's play-by-play"
                    except Exception:
                        pbp_rows = None
        for rid in missing:
            xy = _pbp_assisted_xy(pbp_rows, rid, r_shots_by_id.get(rid))
            if xy is not None:
                assisted[rid] = xy
                source_by_id[rid] = "pbp"

    zone_names = PASSING_ZONE_NAMES
    receiver_positions, receiver_spot_notes, receiver_zone_stats, placement_lines = [], [], [], []
    for name, rid in zip(receiver_names, receiver_ids):
        spot, note, line, zstats = None, None, None, None
        r_shots = r_shots_by_id.get(rid) if rid else None
        found = _passing_zone_stats(assisted.get(rid), r_shots) if rid else None
        xy = None
        if found:
            spot, zstats, n_made = found
            xy = _zone_centroid(assisted.get(rid), spot)
            ranked = sorted(zstats, key=lambda z: zstats[z]["share"], reverse=True)
            share = zstats[spot]["share"]
            note = f"Most shots off {passer_last}'s passes: {zone_names[spot]} (~{share:.0%})"
            runner = (f"; next: {zone_names[ranked[1]]} {zstats[ranked[1]]['share']:.0%}" if len(ranked) > 1 else "")
            line = (f"**{name}** - {zone_names[spot]}: {share:.0%} of his shots right after {passer_last}'s passes"
                    f"{runner} (from {n_made} baskets {passer_last} assisted to him)")
        else:
            spot = _catch_spot(r_shots)
            xy = _shots_centroid(r_shots, spot)
            # the pop-up still shows his court: where he shoots off a catch (his own shots), in the chart's colour
            zstats = _own_zone_stats(r_shots)
            if spot and zstats.get(spot):
                note = f"Where he shoots most off a catch: {zone_names.get(spot, spot)} (~{zstats[spot]['share']:.0%})"
            if spot:
                why = ("fewer than 3 of his baskets were assisted by " + passer_last) if rid in source_by_id \
                    else f"{passer_last}'s assists to him couldn't be looked up just now"
                line = (f"**{name}** - {zone_names.get(spot, spot)}: {why}, so he's placed where he shoots most off "
                        f"a catch")
        placement_lines.append(line or f"**{name}** - no shot data found, so shown in a general spot")
        # where he goes on the court: the average position of those shots, inside that area
        receiver_positions.append({"zone": spot, "xy": xy} if spot else None)
        receiver_spot_notes.append(note)
        receiver_zone_stats.append(zstats)

    connection_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
    fig, passer_pos, receiver_final_positions = build_court_connection_map(
        picked_name, receiver_names, receiver_values, receiver_makes, connection_color,
        passer_image_url=passer_image_url, receiver_image_urls=receiver_image_urls,
        receiver_extra_stats=receiver_extra_stats, receiver_positions=receiver_positions,
        return_hotspot_data=True,
    )
    show_chart(fig, _hover(hover.passing_web_hotspots, fig.axes[0], passer_pos, receiver_final_positions,
                           receiver_names, receiver_values, receiver_makes, receiver_extra_stats,
                           passer_name=picked_name, receiver_spot_notes=receiver_spot_notes,
                           receiver_zone_stats=receiver_zone_stats, color=connection_color), key)
    title = f"Passing Connections - {picked_name}"
    add_to_tableau_dashboard(fig, title, f"tableau_{key}")
    offer_share_to_community(fig, title, f"share_{key}")
    plt.close(fig)
    if not show_explainer:
        return
    # Exactly how each player got his spot, with the numbers -- so the placement can be checked.
    with st.expander("How each player was placed", expanded=True):
        used = set(source_by_id.values())
        sources = []
        if "pbpstats" in used:
            sources.append("pbpstats.com's shot log, which is built from the NBA's own play-by-play and shot charts")
        if "pbp" in used and pbp_label:
            sources.append(pbp_label)
        if sources:
            st.markdown(f"Each player stands in the court area where he took the most shots right after "
                        f"{passer_last}'s passes in {season}. That's every basket {passer_last} assisted to him, with "
                        f"its exact court location from {' and '.join(sources)}, and his misses in each area estimated "
                        f"from his own FG% there - the NBA only records who passed on made baskets. Areas are the "
                        f"NBA's own shot zones. Each picture sits at the average spot of those shots; players sharing an "
                        f"area stand right next to each other, as close to their real spot as the others allow. "
                        f"Hover a player to see every area.")
        else:
            st.markdown(f"{passer_last}'s assists couldn't be looked up just now (pbpstats.com and the NBA "
                        f"play-by-play were both unreachable), so these players are placed where they shoot most off "
                        f"a catch - not specifically after {passer_last}'s passes. Run it again in a minute.")
        st.markdown("\n".join(f"- {ln}" for ln in placement_lines))



if category == "Home":
    # Phones only: a breathing hint in the empty strip above the banner, beside the SIDE BAR button (tapping it opens
    # the sidebar, the same as the button)
    st.markdown('<div class="ba-sb-hint" role="button"><svg class="ba-sb-arrow" viewBox="0 0 44 14" aria-hidden="true">'
                '<path d="M43 7H2.5M9 1.2 2 7l7 5.8" fill="none" stroke="currentColor" stroke-width="2.4" '
                'stroke-linecap="round" stroke-linejoin="round"/></svg><span>OPEN SIDE BAR TO GET STARTED!</span></div>',
                unsafe_allow_html=True)
    banner_path = os.path.join(os.path.dirname(__file__), "..", "assets", "banner.png")
    if os.path.exists(banner_path):
        with st.container(key="home_banner"):
            st.image(banner_path, use_container_width=True)
    st.subheader("Bradley Analytics Software Engine")
    st.write(
        "One dashboard for the whole NBA: shot charts and heat maps, advanced player and team charts, a league-wide "
        "criteria search, lineup networks, front office and coaching tools, and an AI assistant - all running on "
        "live NBA data."
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Visualization Types", "6")
    col2.metric("Dashboard Sections", "10")
    col3.metric("Data Source", "NBA API")
    info_card("Getting Started",
        "Open the sidebar and pick a section. Search by Player and Search by Team build court charts, advanced "
        "charts and league comparisons for anyone; Search by Criteria filters the whole league; the On/Off Lineup "
        "Network maps how every lineup performs; Front Office and Coaching cover rosters, salaries, trades and "
        "minutes; and AI Search answers questions with a link straight to the right chart.")
    info_card("A Note on Data",
        "Stats, shots and lineups come straight from the NBA's own data, updated as games are played. Salaries and "
        "contracts come from a separately maintained salary sheet, so they can trail the latest signings and trades "
        "by a little.")
    st.stop()


elif category == "AI Search":
    def _ai_navigate(nav):
        """AI Search's links: open a place in the dashboard -- a page, and on it the tab, chart category and chart,
        Criteria tool or glossary term the link names (button callback: runs before the next run draws anything)."""
        page = (nav or {}).get("page")
        if page not in CATEGORIES:
            return
        st.session_state["pending_nav_target"] = page
        if page in ("Search by Player", "Search by Team") and nav.get("viz_category") in VIZ_CATEGORIES:
            st.session_state["viz_category"] = nav["viz_category"]
            if nav.get("visualization") in VIZ_CATEGORIES[nav["viz_category"]]:
                st.session_state["viz_select"] = nav["visualization"]
            else:
                st.session_state.pop("viz_select", None)
        if page in ("Front Office", "Coaching") and nav.get("tab"):
            st.session_state.setdefault("_org_pending_tab", {})[page] = nav["tab"]
        if page == "Search by Criteria" and nav.get("tool") in criteria_tools.TOOLS:
            st.session_state["crit_tool"] = nav["tool"]
        if page == "Glossary" and nav.get("term"):
            st.session_state["glossary_search"] = nav["term"]

    # The whole page lives in ai_search.py: ask anything -> a written answer plus an interactive chart with its own
    # colour/style/season controls, clarifying questions with one-click answers, and the conversation kept on screen.
    ai_search.render({
        "PLAYER_NAME_TO_RECORD": PLAYER_NAME_TO_RECORD, "TEAM_NAME_TO_RECORD": TEAM_NAME_TO_RECORD,
        "resolve_color_input": resolve_color_input, "DEFAULT_COLOR": DEFAULT_COLOR,
        "default_color_team": _default_color_team, "load_salary_data": _load_salary_data,
        "code_loading_animation": code_loading_animation, "info_card": info_card, "GOLD_GRADIENT": GOLD_GRADIENT,
        "game_lookup": _game_lookup, "friendly_error": friendly_error, "strip_accents": _strip_accents,
        "navigate": _ai_navigate,
    })
    st.stop()

elif category == "Search by Criteria":
    st.title("Search by Criteria")
    # Which kind of search: the original stats search (scatter plot) first and picked by default, then lineups,
    # shots from a circled area of the court, and passing -- each ending in its own visualization.
    crit_tool = st.selectbox("Criteria Tool:", criteria_tools.TOOLS, index=0, key="crit_tool")
    st.caption(criteria_tools.CAPTIONS[crit_tool])
    criteria_tools.inject_css()

    season = st.selectbox(
        "Season:", ALL_SEASONS,
        index=0,
    )
    if crit_tool != criteria_tools.TOOLS[0]:
        if season:
            criteria_tools.render(crit_tool, season, {
                "code_loading_animation": code_loading_animation, "persistent_run_button": persistent_run_button,
                "show_chart": show_chart, "hover": _hover, "add_to_tableau_dashboard": add_to_tableau_dashboard,
                "offer_share_to_community": offer_share_to_community, "friendly_error": friendly_error,
                "player_name_by_id": {rec["id"]: name for name, rec in PLAYER_NAME_TO_RECORD.items()},
                "league_lineups": _league_lineups, "ALL_TEAM_NAMES": ALL_TEAM_NAMES,
                "render_passing_web": render_passing_web, "color_input_with_dropdown": color_input_with_dropdown,
                "resolve_color_input": resolve_color_input, "strip_accents": _strip_accents,
                "code_window_here": _code_window_here, "show_code_window": _flush_run_code,
            })
        st.stop()
    # "Stat mode:" is drawn right above "Add stat filters:" (the stats it changes), but the league's stats have to be
    # downloaded in that mode before any filter is drawn -- so its current choice is read here from its widget key.
    _CRIT_MODES = ["Per Game", "Per 36", "Totals"]
    # (the last choice is also kept separately: Streamlit can forget -- or stop showing -- a radio's value while it
    # isn't drawn, e.g. while another Criteria Tool is open; the radio below always starts on this choice)
    stat_mode_label = st.session_state.get("crit_stat_mode")
    if stat_mode_label not in _CRIT_MODES:
        stat_mode_label = st.session_state.get("_crit_stat_mode_keep", "Per Game")
    stat_mode_value = {"Totals": "Totals", "Per Game": "PerGame", "Per 36": "Per36"}[stat_mode_label]

    if season:
        st.subheader("Filters:")
        with code_loading_animation("Downloading league-wide stats and bio data"):
            try:
                stats_df = get_player_stats(season, per_mode=stat_mode_value)
                bio_df = get_player_bio_stats(season)
            except Exception as e:
                stats_df, bio_df = None, None
                st.error(f"Couldn't load league data for {season}: {e}")

        if stats_df is not None and bio_df is not None:
            # Merge stats + bio on player id so every filter (stat-based
            # or bio-based) operates on one combined table.
            bio_position_col = next(
                (c for c in ("PLAYER_POSITION", "POSITION") if c in bio_df.columns), None,
            )
            bio_cols = ["PLAYER_ID", "PLAYER_HEIGHT_INCHES", "PLAYER_WEIGHT"]
            if "AGE" in bio_df.columns:
                bio_cols.append("AGE")
            if bio_position_col:
                bio_cols.append(bio_position_col)
            merged = stats_df.merge(
                bio_df[bio_cols], on="PLAYER_ID", how="inner", suffixes=("", "_bio"),
            )

            filtered = merged.copy()

            # Position -- checks every column name variant the bio
            # endpoint has been observed to use across different nba_api
            # versions/seasons, rather than assuming one exact name and
            # silently disappearing if that guess is wrong (confirmed as
            # a real risk, not hypothetical, since this can't be tested
            # against a live response from this sandbox).
            position_col = next(
                (c for c in ("PLAYER_POSITION", "POSITION") if c in merged.columns), None,
            )
            if position_col:
                all_positions = sorted(merged[position_col].dropna().unique().tolist())
                picked_positions = st.multiselect("Position:", all_positions)
                if picked_positions:
                    filtered = filtered[filtered[position_col].isin(picked_positions)]

            # Age -- a dedicated, always-visible filter matching
            # Height's treatment, rather than requiring it to be dug out
            # of the generic "Add stat filters" multiselect below.
            if "AGE" in merged.columns and merged["AGE"].notna().any():
                a_min = int(merged["AGE"].min())
                a_max = int(merged["AGE"].max())
                if a_min < a_max:
                    age_range = st.slider("Age:", a_min, a_max, (a_min, a_max))
                    filtered = filtered[filtered["AGE"].between(age_range[0], age_range[1])]

            # Height -- select_slider (not a plain slider) so the
            # handles themselves can show real "5'11"" labels, since
            # st.slider()'s format parameter only does number formatting
            # (decimal places), not a genuine unit conversion.
            if "PLAYER_HEIGHT_INCHES" in merged.columns and merged["PLAYER_HEIGHT_INCHES"].notna().any():
                h_min = int(merged["PLAYER_HEIGHT_INCHES"].min())
                h_max = int(merged["PLAYER_HEIGHT_INCHES"].max())
                if h_min < h_max:
                    def _inches_to_feet(inches):
                        return f"{inches // 12}'{inches % 12}"
                    height_options = list(range(h_min, h_max + 1))
                    height_labels = {h: _inches_to_feet(h) for h in height_options}
                    height_range = st.select_slider(
                        "Height:", options=height_options,
                        value=(h_min, h_max), format_func=lambda h: height_labels[h],
                    )
                    filtered = filtered[
                        filtered["PLAYER_HEIGHT_INCHES"].between(height_range[0], height_range[1])
                    ]

            # Salary -- merged in from the same salary spreadsheet
            # (data/salary_table.xlsx) used everywhere else in the app
            # (Trade Machine, Salary Cap, AI Search), so as that file
            # gets filled in over time this filter picks it up
            # automatically, no code changes needed later.
            salary_data_criteria = _load_salary_data()
            if not salary_data_criteria.empty and "PLAYER_NAME" in salary_data_criteria.columns and "SEASON" in salary_data_criteria.columns:
                # the season's salaries (from July 1, the new league year's -- see _salary_season_for)
                season_salaries_criteria = salary_data_criteria[
                    salary_data_criteria["SEASON"] == _salary_season_for(season)]
                filtered = filtered.merge(
                    season_salaries_criteria[["PLAYER_NAME", "SALARY"]].drop_duplicates("PLAYER_NAME"),
                    on="PLAYER_NAME", how="left",
                )
                salary_range = None
                league_salaries = season_salaries_criteria["SALARY"].dropna()
                if not league_salaries.empty:
                    try:
                        # $0 up to the league's top salary rounded up ($62.6m -> $64m), in $1m steps
                        hi_m = int(visuals.money_top((league_salaries / 1_000_000).tolist()))
                        pick_m = st.slider("Salary:", 0, hi_m, (0, hi_m), step=1, format="$%dm",
                                           key="crit_salary")
                        salary_range = (pick_m[0] * 1_000_000 - 1, pick_m[1] * 1_000_000 + 1)
                        salary_narrowed = tuple(pick_m) != (0, hi_m)
                    except Exception:
                        # Whatever the exact cause, this filter is a
                        # narrowing convenience on top of the criteria
                        # search, not the core feature -- if the salary
                        # slider itself can't be built for some reason,
                        # this shows every player instead of crashing
                        # the whole page over one optional filter.
                        salary_range = None
                if salary_range is not None:
                    # At the full $0-top range nobody is dropped (players with no salary on file stay in); once the
                    # range is narrowed, only players whose salary is inside it remain.
                    in_range = filtered["SALARY"].between(salary_range[0], salary_range[1])
                    filtered = filtered[in_range if salary_narrowed else (in_range | filtered["SALARY"].isna())]
            else:
                st.markdown("*Salary: Coming soon.*")

            # Stat/rating sliders -- progressive disclosure via
            # multiselect first (30+ possible stats would be an
            # overwhelming wall of sliders shown all at once). AGE and
            # PLAYER_HEIGHT_INCHES are deliberately excluded here since
            # they're both dedicated filters above already -- leaving
            # them in this list too would let someone filter on the
            # same thing twice in two different, redundant widgets.
            crit_items, crit_by_label = stat_menus.stat_items("player", exclude_fields=("AGE", "PLAYER_HEIGHT_INCHES"))
            label_to_field = {label: spec[0] for label, spec in crit_by_label.items()}

            st.radio("Stat mode:", _CRIT_MODES, index=_CRIT_MODES.index(stat_mode_label), horizontal=True,
                     key="crit_stat_mode",
                     on_change=lambda: st.session_state.update(_crit_stat_mode_keep=st.session_state["crit_stat_mode"]))
            chosen_stat_labels = stat_menus.multiselect("Add stat filters:", crit_items, key="crit_stat_filters")
            # the Bradley Ratings and Tendencies as filters too: picked here, their sliders come after the stats' below
            chosen_rating_filters = st.multiselect("Add Bradley rating filters:", ratings_data.columns(ratings_data.RATINGS),
                                                   key="crit_rating_filters")
            chosen_tend_filters = st.multiselect("Add tendency filters:", ratings_data.columns(ratings_data.TENDENCIES),
                                                 key="crit_tendency_filters")
            for label in chosen_stat_labels:
                field = label_to_field[label]
                if field not in filtered.columns or not filtered[field].notna().any():
                    st.caption(f"({label} isn't available in this season's data)")
                    continue
                is_pct = field.endswith("_PCT")
                # Percentage stats are stored as 0-1 fractions (0.37)
                # but should read as whole percent points on the slider
                # (37) -- scale up for display, scale back down before
                # applying the filter to the real 0-1 values.
                scale = 100 if is_pct else 1
                s_min = float(filtered[field].min()) * scale
                s_max = float(filtered[field].max()) * scale
                if s_min >= s_max:
                    continue
                # Whole-number steps once a stat's real range crosses 10
                # (points, rebounds, etc.), decimals for smaller
                # counting stats (steals, blocks) where a whole step
                # would be too coarse to be useful. Rounding the bounds
                # themselves (not just the step) matters here -- a
                # fractional min/max like 2.345-35.678 with step=1
                # would still produce fractional slider positions
                # (2.345, 3.345...), not the clean whole numbers wanted.
                if is_pct:
                    step = 1
                    s_min, s_max = round(s_min), round(s_max)
                elif s_max > 10:
                    step = 1
                    s_min, s_max = int(s_min), int(s_max) + 1
                else:
                    step = 0.1
                    s_min, s_max = round(s_min, 1), round(s_max, 1)
                chosen_range = st.slider(
                    label, s_min, s_max, (s_min, s_max), step=step, key=f"crit_{field}",
                    format="%d%%" if is_pct else None,
                )
                real_lo = chosen_range[0] / scale
                real_hi = chosen_range[1] / scale
                filtered = filtered[filtered[field].between(real_lo, real_hi)]

            # Bradley rating / tendency sliders (2025-26 and 2026-27; a player without the numbers drops out once one
            # of these filters is set)
            rating_filter_picks = ([(ratings_data.RATINGS, c) for c in chosen_rating_filters] +
                                   [(ratings_data.TENDENCIES, c) for c in chosen_tend_filters])
            if rating_filter_picks and not ratings_data.available(season):
                st.caption(f"(Bradley Ratings and Tendencies are for {' and '.join(sorted(ratings_data.SEASONS))} only)")
                rating_filter_picks = []
            for kind, col in rating_filter_picks:
                league = ratings_data.league_frame(kind)
                vals = dict(zip(pd.to_numeric(league["PLAYER_ID"], errors="coerce"), pd.to_numeric(league[col], errors="coerce")))
                tag = "BR" if kind == ratings_data.RATINGS else "TD"
                fkey = f"_{tag}_{col}"
                filtered = filtered.copy()
                filtered[fkey] = pd.to_numeric(filtered["PLAYER_ID"], errors="coerce").map(vals)
                known = pd.to_numeric(league[col], errors="coerce").dropna()
                if known.empty:
                    continue
                slider_key = f"crit_{tag.lower()}_{_safe_key(col)}"
                if col == "Potential":
                    grades = sorted({g for g in league.get("POTENTIAL_GRADE", pd.Series(dtype=str)).dropna()
                                     if g in ratings_data.GRADE_POINTS}, key=lambda g: ratings_data.GRADE_POINTS[g])
                    if len(grades) < 2:
                        continue
                    lo_g, hi_g = st.select_slider(col, options=grades, value=(grades[0], grades[-1]), key=slider_key)
                    lo, hi = ratings_data.GRADE_POINTS[lo_g], ratings_data.GRADE_POINTS[hi_g]
                else:
                    r_min, r_max = int(known.min()), int(known.max())
                    if r_min >= r_max:
                        continue
                    lo, hi = st.slider(col, r_min, r_max, (r_min, r_max), step=1, key=slider_key)
                filtered = filtered[filtered[fkey].between(lo, hi)]

            match_count = len(filtered)
            criteria_tools.count_line(f"{match_count} players match these filters.")

            if match_count == 0:
                st.warning("No players match - loosen a filter.")
            elif match_count > 30:
                st.warning(f"{match_count} players match, narrow the filters to match 30 or fewer players.")
            st.subheader("Generate scatter plot")
            y_label = stat_menus.select("Stat (Y axis):", crit_items, key="crit_y_sec")
            x_label = stat_menus.select("Stat (X axis):", crit_items, key="crit_x_sec", value="OFF RTG (Offensive Rating)")
            crit_color_input = color_input_with_dropdown(f"crit_color_{season}")
            # (shown from the start; RUN draws once 1 to 30 players match)
            run_criteria = persistent_run_button(0 < match_count <= 30, key="search_by_criteria",
                                                 not_ready="Narrow the filters to 1-30 matching players first.")

            if run_criteria:
                y_field = label_to_field[y_label]
                x_field = label_to_field[x_label]
                if y_field not in filtered.columns or x_field not in filtered.columns:
                    st.error("One of the chosen stats isn't available in this season's data.")
                else:
                    scatter_df = filtered[["PLAYER_NAME", "PLAYER_ID", y_field, x_field]].copy()
                    scatter_df.columns = ["name", "player_id", "y_value", "x_value"]
                    scatter_df["image_url"] = scatter_df["player_id"].apply(
                        lambda pid: get_player_headshot_url(pid)
                    )
                    scatter_df["is_included"] = True
                    # "Show pictures for": which players are drawn as their headshot (the rest as dots)
                    pics = pickers.picture_picker(scatter_df["name"].tolist(), key=f"crit_pics_{season}")
                    scatter_df["show_image"] = scatter_df["name"].astype(str).isin(pics)
                    crit_color = resolve_color_input(crit_color_input) if crit_color_input else DEFAULT_COLOR
                    fig, crit_records = build_scatter_plot(scatter_df, y_label, x_label, dot_color=crit_color,
                                                           return_hotspot_data=True)
                    show_chart(fig, _hover(hover.criteria_scatter_hotspots, fig.axes[0], crit_records, x_label,
                                           y_label, stripe_color=crit_color), "criteria_scatter")
                    add_to_tableau_dashboard(fig, "Search by Criteria", "tableau_criteria")
                    offer_share_to_community(fig, "Search by Criteria", "share_criteria")
                    plt.close(fig)
    st.stop()

elif category == "Front Office":
    _fo_tabs = ["Roster", "Salary Cap", "Trade Machine", "Draft Scouting", "CBA Guide", "Staff"]
    _fo_team, _fo_tab = org_sections.render_section_header(
        "Front Office", _fo_tabs, subtitle="Team-level roster, cap, draft, and front-office tools.")
    if _fo_team:
        if _fo_tab == "Trade Machine":
            st.caption("Pick two teams and swap players between their real rosters.")

            # From July 1 the new league year's contracts and rosters are the current ones, so that season comes first
            # (its stats don't exist yet -- ordering by points uses the latest season that has them)
            _cap_now = _cap_season()
            trade_seasons = ([_cap_now] if _cap_now not in ALL_SEASONS else []) + list(ALL_SEASONS)
            trade_season = st.selectbox(
                "Season:", trade_seasons,
                index=0, key="trade_season",
            )
            # (a season that hasn't had a game yet has no stats: the latest one that has stands in)
            stats_season = min(trade_season, _stats_config.default_season())
            # Two real dropdowns side by side, top-aligned: each opens a 5 x 6 grid of team logos (bigger than
            # these used to be, smaller than Search by Team's full-width grid).
            # Team 1 starts as the team picked at the top of Front Office (and follows it when that team changes);
            # it can still be changed here
            if st.session_state.get("_trade_team_a_follows") != _fo_team:
                st.session_state["_trade_team_a_follows"] = _fo_team
                st.session_state["trade_team_a"] = _fo_team
                if st.session_state.get("trade_team_b") == _fo_team:
                    st.session_state["trade_team_b"] = None
            tcol1, tcol2 = st.columns(2, vertical_alignment="top")
            with tcol1:
                team_a_name = team_grid.team_dropdown("Team 1:", "trade_team_a", logo_px=60)
            with tcol2:
                team_b_name = team_grid.team_dropdown("Team 2:", "trade_team_b", logo_px=60)

            if team_a_name and team_b_name and team_a_name == team_b_name:
                st.warning("Pick two different teams.")
            elif team_a_name and team_b_name:
                def _trade_roster(team_name):
                    team_id = TEAM_NAME_TO_RECORD[team_name]["id"]
                    try:
                        r = get_team_roster(team_id, trade_season)
                    except Exception:
                        r = None
                    if (r is None or r.empty) and trade_season != stats_season:
                        r = get_team_roster(team_id, stats_season)       # the new season's roster isn't posted yet
                    return r

                with code_loading_animation("Downloading rosters"):
                    try:
                        roster_a = _trade_roster(team_a_name)
                        roster_b = _trade_roster(team_b_name)
                    except Exception as e:
                        roster_a, roster_b = None, None
                        st.error(f"Couldn't load rosters for {trade_season}: {e}")

                if roster_a is not None and roster_b is not None:
                    names_a = sorted(roster_a["PLAYER"].tolist()) if "PLAYER" in roster_a.columns else []
                    names_b = sorted(roster_b["PLAYER"].tolist()) if "PLAYER" in roster_b.columns else []

                    with code_loading_animation("Downloading player stats for roster display"):
                        try:
                            roster_stats = get_player_stats(stats_season, per_mode="PerGame")
                        except Exception:
                            roster_stats = None
                        # every roster headshot at once (the server downloads them, with retries, and hands the page
                        # the pictures -- so they show even when a source blocks the browser's own request)
                        _headshot_urls = {int(p): get_player_headshot_url(int(p))
                                          for r in (roster_a, roster_b) if "PLAYER_ID" in r.columns
                                          for p in r["PLAYER_ID"].dropna()}
                        visuals.prefetch_small_images(_headshot_urls.values(), max_px=160)

                    salary_data = _load_salary_data()
                    contracts = salary_table.contract_index(_load_salary_table())
                    picks_data = _load_draft_picks_data()
                    if salary_data.empty or picks_data.empty:
                        st.markdown("*Salaries and draft picks: Coming soon.*")

                    def _render_team_roster(roster_df, team_name, key_prefix):
                        """
                        A live, checkbox-driven roster -- checking a player here
                        IS the selection (no separate multiselect dropdown
                        disconnected from the roster view). Returns the names/
                        picks actually checked.
                        """
                        names = sorted(roster_df["PLAYER"].tolist()) if "PLAYER" in roster_df.columns else []
                        team_picks = picks_data[picks_data["TEAM"] == team_name]["PICK"].tolist() if "TEAM" in picks_data.columns else []

                        roster_tab, picks_tab = st.tabs([f"Roster ({len(names)})", f"Picks ({len(team_picks)})"])
                        selected_players = []
                        # ordered by points per game (not shown); players without stats go last, by name
                        ppg = {}
                        if roster_stats is not None and {"PLAYER_ID", "PTS"} <= set(roster_stats.columns):
                            ppg = dict(zip(roster_stats["PLAYER_ID"].astype(int), roster_stats["PTS"]))
                        ordered = roster_df.copy()
                        _pids = ordered.get("PLAYER_ID", pd.Series([None] * len(ordered)))
                        ordered["_PPG"] = [ppg.get(int(p)) if pd.notna(p) else None for p in _pids]
                        # highest Player Rating first; players without one after them by points per game
                        ordered = _sort_by_rating_then_points(ordered, trade_season, pts=ordered["_PPG"])
                        with roster_tab:
                            for _, row in ordered.iterrows():
                                pid = row.get("PLAYER_ID")
                                name = row.get("PLAYER", "Unknown")
                                bio_parts = []
                                for c in ("POSITION", "AGE", "HEIGHT"):          # (position, age, height -- every table's order)
                                    if c in row.index and pd.notna(row[c]) and str(row[c]).strip():
                                        if c == "AGE":
                                            bio_parts.append(f"{int(row[c])} yo")
                                        else:
                                            bio_parts.append(str(row[c]))
                                bio_line = ", ".join(bio_parts)
                                # "$58.4m, 4 yrs PO": this season's salary, the years left counting this one, and
                                # PO / TO / MO when the last of them is a player / team / mutual option
                                salary_line = salary_table.format_contract(salary_table.contract_summary(
                                    contracts, trade_season, pid if pd.notna(pid) else None, name))

                                ccol1, ccol2, ccol3 = st.columns([0.4, 0.8, 4])
                                with ccol1:
                                    checked = st.checkbox("Select", key=f"{key_prefix}_{name}", label_visibility="collapsed")
                                with ccol2:
                                    pic = (visuals.image_png_bytes(_headshot_urls.get(int(pid)), max_px=160)
                                           if pd.notna(pid) and int(pid) in _headshot_urls else None)
                                    if pic:
                                        # a fixed pixel width (a container-width image would fill the whole screen
                                        # on a phone, where Streamlit stacks these columns)
                                        st.image(pic, width=60)
                                with ccol3:
                                    lines_html = "".join(f'<br><span style="color:#9a9a9a; font-size:0.85rem;">'
                                                         f'{html_escape(x)}</span>' for x in (bio_line, salary_line) if x)
                                    # one markdown block with explicit <br>s and a tight line-height (separate
                                    # markdown calls each get a paragraph's spacing)
                                    st.markdown(
                                        f'<div style="line-height:1.15;"><strong>{html_escape(name)}</strong>{lines_html}</div>',
                                        unsafe_allow_html=True,
                                    )
                                if checked:
                                    selected_players.append(name)

                        selected_picks = []
                        with picks_tab:
                            if team_picks:
                                for pick in team_picks:
                                    if st.checkbox(pick, key=f"{key_prefix}_pick_{pick}"):
                                        selected_picks.append(pick)
                            else:
                                st.markdown("*Coming soon.*")

                        return selected_players, selected_picks

                    rcol1, rcol2 = st.columns(2)
                    with rcol1:
                        sent_by_a, picks_sent_by_a = _render_team_roster(roster_a, team_a_name, "a")
                    with rcol2:
                        sent_by_b, picks_sent_by_b = _render_team_roster(roster_b, team_b_name, "b")

                    def _render_trade_chips(team_name, players, picks):
                        st.markdown(f'<p style="color:#888; font-weight:bold;">{team_name} Trade:</p>', unsafe_allow_html=True)
                        items = players + picks
                        if not items:
                            st.caption("(nothing selected yet)")
                            return
                        chips = "".join(
                            f'<span style="display:inline-block; margin:2px 4px 2px 0; padding:4px 10px; '
                            f'border-radius:6px; border:1px solid #D4AF37; color:#F5D370; '
                            f'font-family:Arial, sans-serif; font-size:0.9rem;">{item} &times;</span>'
                            for item in items
                        )
                        st.markdown(chips, unsafe_allow_html=True)

                    tcol1, tcol2 = st.columns(2)
                    with tcol1:
                        _render_trade_chips(team_a_name, sent_by_a, picks_sent_by_a)
                    with tcol2:
                        _render_trade_chips(team_b_name, sent_by_b, picks_sent_by_b)

                    # Salary figures come straight from the same salary
                    # spreadsheet already loaded above for the roster display
                    # -- no separate checkbox or upload step needed. Filtered
                    # to the specific season being traded in, since a player
                    # can now have multiple season rows.
                    salaries = {}
                    if "PLAYER_NAME" in salary_data.columns and "SEASON" in salary_data.columns:
                        season_salaries = salary_data[salary_data["SEASON"] == trade_season]
                        salary_lookup = dict(zip(season_salaries["PLAYER_NAME"], season_salaries["SALARY"]))
                        for p in sent_by_a + sent_by_b:
                            salaries[p] = salary_lookup.get(p, 0)

                    new_roster_a = [n for n in names_a if n not in sent_by_a] + sent_by_b
                    new_roster_b = [n for n in names_b if n not in sent_by_b] + sent_by_a

                    if salaries:
                        salary_out_a = sum(salaries.get(p, 0) for p in sent_by_a)
                        salary_in_a = sum(salaries.get(p, 0) for p in sent_by_b)
                        salary_out_b = sum(salaries.get(p, 0) for p in sent_by_b)
                        salary_in_b = sum(salaries.get(p, 0) for p in sent_by_a)
                        scol1, scol2 = st.columns(2)
                        with scol1:
                            st.metric(f"{team_a_name} salary change", f"${salary_in_a - salary_out_a:,.0f}")
                        with scol2:
                            st.metric(f"{team_b_name} salary change", f"${salary_in_b - salary_out_b:,.0f}")

                    if st.button("Compare stat impact", use_container_width=True):
                        with code_loading_animation("Downloading player stats"):
                            try:
                                trade_stats = get_player_stats(stats_season, per_mode="PerGame")
                            except Exception as e:
                                trade_stats = None
                                st.error(f"Couldn't load stats: {e}")
                        if trade_stats is not None and "PLAYER_NAME" in trade_stats.columns:
                            player_ids = {name: rec["id"] for name, rec in PLAYER_NAME_TO_RECORD.items()}
                            fig = build_trade_breakdown_image(
                                team_a_name, team_b_name,
                                sends_a=sent_by_a, sends_b=sent_by_b,
                                stats_df=trade_stats, player_ids=player_ids,
                                salary_data=salary_data, season=trade_season,
                            )
                            st.pyplot(fig, use_container_width=True)
                            add_to_tableau_dashboard(fig, "Trade Machine", "tableau_trade")
                            offer_share_to_community(fig, "Trade Machine", "share_trade")
                            plt.close(fig)
        elif _fo_tab == "Roster":
            render_front_office_roster(_fo_team)
        elif _fo_tab == "Salary Cap":
            render_front_office_salary_cap(_fo_team)
        elif _fo_tab == "Draft Scouting":
            org_sections.coming_soon("Draft Scouting")
        elif _fo_tab == "CBA Guide":
            render_front_office_cba_guide(_fo_team)
        elif _fo_tab == "Staff":
            org_sections.coming_soon("Staff")
    st.stop()

elif category == "Coaching":
    _co_tabs = ["Player Minutes", "Playbook", "Player Tendencies", "Film Room", "Staff"]
    _co_team, _co_tab = org_sections.render_section_header(
        "Coaching", _co_tabs, subtitle="Team-level scheme, minutes, and staffing tools.")
    if _co_team:
        if _co_tab == "Player Minutes":
            render_coaching_player_minutes(_co_team)
        elif _co_tab == "Playbook":
            org_sections.coming_soon("Playbook")
        elif _co_tab == "Film Room":
            org_sections.coming_soon("Film Room")
        elif _co_tab == "Player Tendencies":
            render_coaching_player_tendencies(_co_team)
        elif _co_tab == "Staff":
            org_sections.coming_soon("Staff")
    st.stop()

elif category == "On/Off Lineup Network":
    st.title("On/Off Lineup Network")

    onoff_season = st.selectbox(
        "Season:", ALL_SEASONS,
        index=0, key="onoff_season",
    )
    onoff_team_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, key="onoff_team")

    st.markdown("---")
    st.markdown("#### Lineup Network")
    if st.session_state.pop("_scroll_to_lineup_network", False):
        components.html(
            """
            <script>
            (function() {
                const parentDoc = window.parent.document;
                const headings = parentDoc.querySelectorAll('h4');
                for (const h of headings) {
                    if (h.textContent.trim() === 'Lineup Network') {
                        h.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        break;
                    }
                }
            })();
            </script>
            """,
            height=0,
        )
    st.caption(
        "Every combination of teammates who shared the court together this season, connected and "
        "colored by that lineup's net rating - a wider view than picking one specific "
        "combination in On/Off Stats below, for spotting which combinations work especially well or poorly at a glance."
    )
    lineup_size_label = st.radio(
        "Lineup size:", ["Two-Man Lineup", "Three-Man Lineup", "Four-Man Lineup", "Five-Man Lineup"],
        horizontal=True, key="lineup_network_size",
    )
    lineup_size = {"Two-Man Lineup": 2, "Three-Man Lineup": 3, "Four-Man Lineup": 4, "Five-Man Lineup": 5}[lineup_size_label]
    min_minutes_together = st.number_input(
        "Minimum minutes played together:", min_value=0, max_value=3000, value=20, step=5,
        help="Filters out pairings with too small a sample to be meaningful.",
    )
    # "Add criteria:" -- a range slider per chosen lineup stat (same as Search by Criteria's Lineups tool), and
    # "Rank by:" -- the order the lineups are drawn in (best first)
    _net_by_label = {lbl: (f, low) for f, lbl, low in criteria_tools.LINEUP_STATS if f != "PLUS_MINUS"}
    _net_labels = list(_net_by_label)
    # (no "Minutes Together" here: the minimum-minutes box above already filters on it)
    _net_items = stat_menus.lineup_items([(f, lbl, low) for lbl, (f, low) in _net_by_label.items() if f != "MIN"])
    net_criteria = stat_menus.multiselect("Add criteria:", _net_items, key="lineup_network_criteria")
    net_keep_groups = None
    if net_criteria and onoff_team_name:
        with code_loading_animation(f"Downloading every {lineup_size}-man lineup combination",
                                    code=get_team_lineup_combos):
            try:
                _pre = _team_lineup_frame(TEAM_NAME_TO_RECORD[onoff_team_name]["id"], onoff_season, lineup_size)
            except Exception as e:  # noqa: BLE001
                _pre = None
                st.error(f"Couldn't load lineup data for {onoff_season}: {friendly_error(e)}")
        if _pre is not None and "GROUP_NAME" in _pre.columns:
            if "MIN" in _pre.columns:
                _pre = _pre[pd.to_numeric(_pre["MIN"], errors="coerce").fillna(0) >= min_minutes_together]
            _missing = [c for c in net_criteria if _net_by_label[c][0] not in _pre.columns]
            if _missing:
                st.caption(f"Not in this team's lineup data: {', '.join(_missing)}.")
            _kept = criteria_tools.range_filters(_pre, [(_net_by_label[c][0], c) for c in net_criteria
                                                        if c not in _missing], f"lineup_network_{lineup_size}")
            net_keep_groups = set(_kept["GROUP_NAME"].astype(str))
            criteria_tools.inject_css()
            criteria_tools.count_line(f"{len(_kept)} of {len(_pre)} lineups meet these criteria.")
    net_rank_label = stat_menus.select("Rank by:", _net_items, value="Net Rating",
                                  key="lineup_network_rank")
    _run_network = persistent_run_button(bool(onoff_team_name), key="onoff_network",   # (shown from the start)
                                         not_ready="Pick a team first.")
    if onoff_team_name and _run_network:
        with code_loading_animation(f"Downloading every {lineup_size}-man lineup combination"):
            try:
                all_pairs = get_team_lineup_combos(
                    TEAM_NAME_TO_RECORD[onoff_team_name]["id"], onoff_season,
                    group_quantity=lineup_size, measure_type="Advanced",
                )
                # MIN (minutes played together) isn't reliably present
                # in the Advanced measure_type response (that call is
                # focused on rating-type columns) -- fetched
                # separately from Base rather than assuming Advanced
                # happens to include it too.
                try:
                    all_pairs_minutes = get_team_lineup_combos(
                        TEAM_NAME_TO_RECORD[onoff_team_name]["id"], onoff_season,
                        group_quantity=lineup_size, measure_type="Base",
                    )
                    if "MIN" in all_pairs_minutes.columns and "GROUP_NAME" in all_pairs_minutes.columns:
                        # If all_pairs already has its own "MIN" column
                        # (the "Advanced" measure_type response isn't
                        # guaranteed not to include one, despite usually
                        # not), merging in a second "MIN" column would
                        # otherwise make pandas silently rename BOTH to
                        # "MIN_x"/"MIN_y" to avoid the collision --
                        # confirmed directly with a minimal reproduction
                        # -- leaving no column literally named "MIN" at
                        # all, and the filter below would then silently
                        # never apply. Dropped first so the merge always
                        # produces one unambiguous "MIN" column from
                        # this Base call, which is the authoritative
                        # source for it here anyway.
                        all_pairs = all_pairs.drop(columns=["MIN"], errors="ignore")
                        all_pairs = all_pairs.merge(
                            all_pairs_minutes[["GROUP_NAME", "MIN"]], on="GROUP_NAME", how="left",
                        )
                except Exception:
                    pass
            except Exception as e:
                all_pairs = None
                st.error(f"Couldn't load lineup data for {onoff_season}: {e}")

        if all_pairs is not None and "GROUP_NAME" in all_pairs.columns:
            value_col = "NET_RATING" if "NET_RATING" in all_pairs.columns else None
            if value_col is None:
                # "Advanced" measure type is expected to include NET_RATING,
                # but nba_api's static docs for this endpoint have proven
                # unreliable before (see stats_config.py's note on Synergy
                # Play Types) -- falls back to PLUS_MINUS from a second,
                # "Base" measure_type call rather than assuming.
                try:
                    all_pairs_base = get_team_lineup_combos(
                        TEAM_NAME_TO_RECORD[onoff_team_name]["id"], onoff_season,
                        group_quantity=lineup_size, measure_type="Base",
                    )
                    if "PLUS_MINUS" in all_pairs_base.columns:
                        all_pairs = all_pairs_base
                        value_col = "PLUS_MINUS"
                except Exception:
                    pass

            if value_col is not None:
                # minimum minutes, "Add criteria:" and "Rank by:" -- applied to whichever data is drawn
                if "MIN" in all_pairs.columns:
                    all_pairs = all_pairs[pd.to_numeric(all_pairs["MIN"], errors="coerce").fillna(0) >= min_minutes_together]
                if net_keep_groups is not None:
                    all_pairs = all_pairs[all_pairs["GROUP_NAME"].astype(str).isin(net_keep_groups)]
                _rank_field, _rank_low = _net_by_label[net_rank_label]
                if _rank_field not in all_pairs.columns:
                    _rank_field, _rank_low = value_col, False
                # ranked: the best lineup by the chosen stat comes first (in the diagram and the list under it)
                all_pairs = (all_pairs.assign(_RANK_V=pd.to_numeric(all_pairs[_rank_field], errors="coerce"))
                             .sort_values("_RANK_V", ascending=_rank_low, na_position="last"))
            if value_col is None:
                st.error("Couldn't find a net rating or plus/minus column in the returned lineup data.")
            else:
                import itertools
                pair_labels, pair_values, pair_minutes = [], [], []
                groups_raw, group_ids, group_rank_vals = [], [], []
                for _, row in all_pairs.iterrows():
                    # GROUP_NAME's exact separator isn't pinned down by this
                    # app's own existing GROUP_NAME handling elsewhere
                    # (which only ever checks substring containment, never
                    # splits it) -- tries the standard " - " NBA API
                    # convention and skips any row that doesn't split
                    # cleanly into exactly lineup_size names, rather than
                    # guessing. For a 3+ man lineup, this decomposes the
                    # single N-man rating into every pairwise combination
                    # within that lineup (e.g. a 3-man group of A, B, C
                    # becomes edges A-B, A-C, B-C, all carrying that same
                    # lineup's rating) -- the network diagram itself is
                    # inherently a pairwise (node-edge) visualization, so
                    # this is the most direct way to show a larger lineup
                    # on the same node-link graph without inventing a
                    # different chart type just for group sizes above 2.
                    parts = [p.strip() for p in str(row["GROUP_NAME"]).split(" - ")]
                    if len(parts) == lineup_size and pd.notna(row[value_col]):
                        # minutes played together travel with the group so the 3/4/5-man diagrams can print them
                        _mins = row["MIN"] if "MIN" in all_pairs.columns and pd.notna(row["MIN"]) else None
                        groups_raw.append((tuple(parts), float(row[value_col]), float(_mins) if _mins is not None else None))
                        group_rank_vals.append(row.get("_RANK_V"))
                        group_ids.append(_lineup_id_set(row.get("GROUP_ID"))
                                         or (int(TEAM_NAME_TO_RECORD[onoff_team_name]["id"]), frozenset(parts)))
                        for a, b in itertools.combinations(parts, 2):
                            pair_labels.append((a, b))
                            pair_values.append(float(row[value_col]))
                            # minutes together travel with each 2-man pair, so the diagram's line thickness and the
                            # pop-up's "N min together" line both have them
                            pair_minutes.append(float(_mins) if _mins is not None and lineup_size == 2 else None)

                if len(pair_labels) < 2:
                    st.warning("Not enough valid lineup combinations found to build this diagram.")
                else:
                    # GROUP_NAME returns each player abbreviated as
                    # "T. Craig", not the full "Trendon Craig" --
                    # confirmed directly from a real screenshot of this
                    # exact chart, where every single node fell back to
                    # its plain-circle text (which is built from
                    # whatever name string it's given), and that
                    # fallback text read "T. Craig" -- meaning the
                    # lookup below was being handed an already-
                    # abbreviated name and unsurprisingly never
                    # matching it against PLAYER_NAME_TO_RECORD's full
                    # names. An abbreviated name has no reliable way to
                    # resolve against the entire league on its own
                    # (multiple "T. Craig"-shaped matches could exist
                    # league-wide), but matching it against this
                    # specific team's own roster this same season
                    # resolves it unambiguously.
                    try:
                        with code_loading_animation("Downloading the team's roster", code=get_team_roster):
                            roster = get_team_roster(TEAM_NAME_TO_RECORD[onoff_team_name]["id"], onoff_season)
                    except Exception:
                        roster = pd.DataFrame()

                    def _resolve_abbreviated_name(abbrev_name):
                        parts = abbrev_name.replace(".", "").split()
                        if len(parts) < 2 or roster.empty or "PLAYER" not in roster.columns:
                            return None
                        first_initial, last_token = parts[0][0].lower(), parts[-1].lower()
                        suffixes = {"jr", "sr", "ii", "iii", "iv", "v"}

                        candidates = []
                        for _, r_row in roster.iterrows():
                            full_name = str(r_row["PLAYER"])
                            full_parts = full_name.split()
                            if len(full_parts) < 2 or full_parts[0][0].lower() != first_initial:
                                continue
                            candidates.append((full_name, full_parts, int(r_row["PLAYER_ID"])))

                        # Strategy 1: exact last-token match -- covers
                        # the ordinary case where GROUP_NAME's
                        # abbreviation and the roster's own PLAYER
                        # column both end on the same word.
                        for full_name, full_parts, pid in candidates:
                            if full_parts[-1].lower().rstrip(".") == last_token.rstrip("."):
                                return full_name, pid

                        # Strategy 2: suffix-aware -- NBA's own
                        # GROUP_NAME abbreviation logic appears to drop
                        # generational suffixes (Jr/Sr/II/III/IV) when
                        # forming "First_Initial. Last_Name", while the
                        # roster's own PLAYER column can still include
                        # one (e.g. "Scotty Pippen Jr." abbreviates to
                        # "S. Pippen", not "S. Jr."). If the roster
                        # entry's own last token is a suffix, the real
                        # match is the token just before it.
                        for full_name, full_parts, pid in candidates:
                            if full_parts[-1].lower().rstrip(".") in suffixes and len(full_parts) >= 3:
                                real_surname = full_parts[-2]
                                if real_surname.lower().rstrip(".") == last_token.rstrip("."):
                                    return full_name, pid

                        # Strategy 3: last resort -- the abbreviated
                        # last-name token appears anywhere among the
                        # full name's own tokens (catches hyphenated or
                        # multi-word surnames formatted inconsistently
                        # between the two sources).
                        for full_name, full_parts, pid in candidates:
                            if any(p.lower().rstrip(".") == last_token.rstrip(".") for p in full_parts):
                                return full_name, pid

                        # Strategy 4: the team roster snapshot itself
                        # can be incomplete for this purpose -- it
                        # reflects the CURRENT roster, so a player
                        # traded away mid-season won't appear on it for
                        # a season they actually played with this team
                        # earlier. Falls back to the app's own global
                        # all-players database (not scoped to any one
                        # team) using the same first-initial + last-name
                        # matching as the strategies above.
                        for full_name, record in PLAYER_NAME_TO_RECORD.items():
                            full_parts = full_name.split()
                            if len(full_parts) < 2 or full_parts[0][0].lower() != first_initial:
                                continue
                            if full_parts[-1].lower().rstrip(".") == last_token.rstrip("."):
                                return full_name, record["id"]

                        return None

                    unique_players = {name for pair in pair_labels for name in pair}
                    resolved_lookup = {}
                    player_image_urls = {}
                    for name in unique_players:
                        resolved = _resolve_abbreviated_name(name)
                        if resolved:
                            resolved_full_name, resolved_id = resolved
                            resolved_lookup[name] = resolved_full_name
                            player_image_urls[name] = get_player_headshot_url(resolved_id)

                    net_label = value_col.replace("_", " ").title()
                    # Where each of these lineups ranks among EVERY lineup of this size in the league that played at
                    # least as many minutes together -- the "#7 best duo in the league" line at the bottom of each
                    # pop-up. One league-wide call; any lineup it can't be matched to just has no rank line.
                    with code_loading_animation(f"Ranking every {lineup_size}-man lineup in the league",
                                                code=get_league_lineup_combos):
                        league_rank_by_ids = _lineup_league_ranks(onoff_season, lineup_size, min_minutes_together, value_col)
                    if lineup_size == 2:
                        fig, net_pos, net_edges, net_minutes = build_network_diagram(
                            pair_labels, pair_values, player_image_urls=player_image_urls,
                            value_label=net_label, return_hotspot_data=True,
                            pair_minutes=pair_minutes if any(m is not None for m in pair_minutes) else None,
                        )
                        duo_ranks = {}
                        for (group_parts, _r, _m), ids in zip(groups_raw, group_ids):
                            if ids and ids in league_rank_by_ids and group_parts[0] != group_parts[1]:
                                duo_ranks[frozenset(group_parts)] = league_rank_by_ids[ids]
                        net_hotspots = _hover(hover.lineup_network_2man_hotspots, fig.axes[0], net_pos, net_edges,
                                              net_label, minute_edges=net_minutes, league_ranks=duo_ranks)
                    else:
                        # The N-man shapes each need the *pairwise* 2-man
                        # net rating for their edges (not the N-man
                        # group's own rating, which is reserved for the
                        # center label) -- fetched as a second, separate
                        # call, since the N-man endpoint itself only
                        # ever returns the whole group's combined rating.
                        try:
                            with code_loading_animation("Downloading every two-man pairing", code=get_team_lineup_combos):
                                two_man_raw = get_team_lineup_combos(
                                    TEAM_NAME_TO_RECORD[onoff_team_name]["id"], onoff_season,
                                    group_quantity=2, measure_type="Advanced",
                                )
                        except Exception:
                            two_man_raw = pd.DataFrame()
                        two_man_lookup = {}
                        if not two_man_raw.empty and "GROUP_NAME" in two_man_raw.columns and value_col in two_man_raw.columns:
                            for _, tm_row in two_man_raw.iterrows():
                                tm_parts = [p.strip() for p in str(tm_row["GROUP_NAME"]).split(" - ")]
                                if len(tm_parts) == 2 and pd.notna(tm_row[value_col]):
                                    a_full = resolved_lookup.get(tm_parts[0], tm_parts[0])
                                    b_full = resolved_lookup.get(tm_parts[1], tm_parts[1])
                                    two_man_lookup[frozenset({a_full, b_full})] = float(tm_row[value_col])

                        groups = [
                            (tuple(resolved_lookup.get(p, p) for p in group_parts), rating, mins)
                            for group_parts, rating, mins in groups_raw
                        ]
                        full_name_image_urls = {resolved_lookup.get(k, k): v for k, v in player_image_urls.items()}
                        fig, net_panels = build_lineup_shapes_diagram(
                            groups, two_man_lookup, player_image_urls=full_name_image_urls,
                            value_label=net_label, return_hotspot_data=True, keep_order=True,
                        )
                        group_ranks = {}
                        for (group_parts, _r, _m), ids in zip(groups_raw, group_ids):
                            if ids and ids in league_rank_by_ids:
                                group_ranks[tuple(resolved_lookup.get(p, p) for p in group_parts)] = league_rank_by_ids[ids]
                        net_hotspots = _hover(hover.lineup_network_group_hotspots, net_panels, two_man_lookup, net_label,
                                              league_ranks=group_ranks)
                    show_chart(fig, net_hotspots, f"lineup_network_{lineup_size}")
                    # the lineups in "Rank by:" order, best first
                    _ranked = pd.DataFrame({
                        "#": list(range(1, len(groups_raw) + 1)),
                        "Lineup": [", ".join(resolved_lookup.get(p, p) for p in g[0]) for g in groups_raw],
                        "Min": [int(round(g[2])) if g[2] is not None else None for g in groups_raw],
                        (net_rank_label if _rank_field != value_col else net_label):
                            pd.to_numeric(pd.Series(group_rank_vals, dtype="object"), errors="coerce").tolist(),
                        net_label: [g[1] for g in groups_raw],
                    })
                    _ranked = _ranked.loc[:, ~_ranked.columns.duplicated()]
                    criteria_tools.inject_css()
                    criteria_tools.count_line(f"Ranked by {net_rank_label}")
                    criteria_tools.html_table(_ranked, max_height=360)
                    title = f"Lineup Network - {onoff_team_name}"
                    add_to_tableau_dashboard(fig, title, "tableau_network")
                    offer_share_to_community(fig, title, "share_network")

    st.markdown("---")
    st.markdown("#### On/Off Stats")
    st.caption(
        "Pick a team and two or three teammates, and see how the team's "
        "per-48-minute stats shift with that specific group sharing the "
        "floor, compared to the team's season average."
    )
    if not onoff_team_name:
        # every picker shows from the start: the players open once a team is picked above
        _pc1, _pc2, _pc3 = st.columns(3)
        _pc1.selectbox("Player 1:", [], index=None, placeholder="Pick a team first.", disabled=True, key="onoff_p1_wait")
        _pc2.selectbox("Player 2:", [], index=None, placeholder="Pick a team first.", disabled=True, key="onoff_p2_wait")
        _pc3.selectbox("Player 3 (optional):", [], index=None, placeholder="Pick a team first.", disabled=True, key="onoff_p3_wait")
    onoff_roster = None
    if onoff_team_name:
        with code_loading_animation("Downloading roster"):
            try:
                onoff_roster = get_team_roster(TEAM_NAME_TO_RECORD[onoff_team_name]["id"], onoff_season)
            except Exception as e:
                onoff_roster = None
                st.error(f"Couldn't load the roster for {onoff_season}: {e}")

        if onoff_roster is not None and "PLAYER" in onoff_roster.columns:
            roster_names = sorted(onoff_roster["PLAYER"].tolist())
            pc1, pc2, pc3 = st.columns(3)
            with pc1:
                player1 = st.selectbox("Player 1:", roster_names, index=None, key="onoff_p1")
            with pc2:
                remaining2 = [p for p in roster_names if p != player1]
                player2 = st.selectbox("Player 2:", remaining2, index=None, key="onoff_p2")
            with pc3:
                remaining3 = [p for p in roster_names if p not in (player1, player2)]
                player3 = st.selectbox("Player 3 (optional):", remaining3, index=None, key="onoff_p3")

            if player1 and player2:
                chosen = [player1, player2] + ([player3] if player3 else [])
                group_size = len(chosen)

                if st.button("Look up this combination", use_container_width=True):
                    with code_loading_animation("Downloading lineup combination data"):
                        try:
                            combos = get_team_lineup_combos(
                                TEAM_NAME_TO_RECORD[onoff_team_name]["id"], onoff_season, group_quantity=group_size,
                            )
                            team_baseline = get_team_stats(onoff_season)
                            # Each player's own on-court totals are only needed for the exactly-2-player case, to
                            # work out "player1 without player2" by subtraction (his on-court totals minus the
                            # together totals) -- meaningless for 3 players, so skipped for that case. They come from
                            # the team's player on/off totals (the lineups endpoint has no one-player groups).
                            solo_lineups = None
                            if group_size == 2:
                                try:
                                    solo_lineups = get_team_player_on_court(TEAM_NAME_TO_RECORD[onoff_team_name]["id"], onoff_season)
                                except Exception:
                                    solo_lineups = None
                        except Exception as e:
                            combos, team_baseline, solo_lineups = None, None, None
                            st.error(f"Couldn't load lineup data: {e}")

                    if combos is not None and "GROUP_NAME" in combos.columns:
                        # Robust match: every chosen player's last name
                        # must appear in GROUP_NAME, regardless of the
                        # endpoint's exact "Last, First - Last, First"
                        # formatting.
                        last_names = [p.split()[-1].lower() for p in chosen]

                        def _matches(group_name):
                            gn = str(group_name).lower()
                            return all(ln in gn for ln in last_names)

                        match_rows = combos[combos["GROUP_NAME"].apply(_matches)]

                        if match_rows.empty:
                            st.warning(
                                f"No minutes found with exactly {', '.join(chosen)} on the "
                                "court together this season for this team."
                            )
                        else:
                            combo_row = match_rows.iloc[0]
                            combo_min = combo_row.get("MIN", 0)

                            team_row_match = team_baseline[team_baseline["TEAM_NAME"] == onoff_team_name] if team_baseline is not None else None
                            team_gp = team_row_match.iloc[0].get("GP", 0) if team_row_match is not None and not team_row_match.empty else 0
                            team_row = team_row_match.iloc[0] if team_row_match is not None and not team_row_match.empty else None

                            # Advanced measure type (Off/Def Rating) for
                            # the together lineup specifically -- a
                            # second, separate API call, same pattern as
                            # get_player_stats fetching Base + Advanced
                            # separately.
                            combo_row_adv = None
                            if group_size == 2:
                                try:
                                    combos_adv = get_team_lineup_combos(
                                        TEAM_NAME_TO_RECORD[onoff_team_name]["id"], onoff_season,
                                        group_quantity=group_size, measure_type="Advanced",
                                    )
                                    adv_match = combos_adv[combos_adv["GROUP_NAME"].apply(_matches)] if "GROUP_NAME" in combos_adv.columns else pd.DataFrame()
                                    if not adv_match.empty:
                                        combo_row_adv = adv_match.iloc[0]
                                except Exception:
                                    combo_row_adv = None

                            def _per48(row, field, minutes):
                                if row is None or field not in row.index or minutes <= 0 or pd.isna(row[field]):
                                    return None
                                return (row[field] / minutes) * 48

                            def _pct_change(value, field, skip_gp_division=False):
                                if value is None or team_row is None or team_gp <= 0 or field not in team_row.index:
                                    return None
                                team_val = team_row[field] if skip_gp_division else team_row[field] / team_gp
                                if not team_val:
                                    return None
                                return (value - team_val) / team_val * 100

                            def _metric_row(label, value, field, skip_gp_division=False, is_pct=False):
                                return (label, value, _pct_change(value, field, skip_gp_division), is_pct)

                            together_metrics = [
                                _metric_row("Off Rating", combo_row_adv.get("OFF_RATING") if combo_row_adv is not None else None, "OFF_RATING", skip_gp_division=True),
                                _metric_row("Def Rating", combo_row_adv.get("DEF_RATING") if combo_row_adv is not None else None, "DEF_RATING", skip_gp_division=True),
                                _metric_row("PTS", _per48(combo_row, "PTS", combo_min), "PTS"),
                                _metric_row("REB", _per48(combo_row, "REB", combo_min), "REB"),
                                _metric_row("AST", _per48(combo_row, "AST", combo_min), "AST"),
                            ]
                            columns = [{
                                "label": " + ".join(chosen),
                                "players": [(p, "ON") for p in chosen],
                                "metrics": together_metrics,
                                "minutes": combo_min,
                            }]

                            if group_size == 2 and solo_lineups is not None and not solo_lineups.empty:
                                _roster_ids = {}
                                if onoff_roster is not None and {"PLAYER", "PLAYER_ID"} <= set(onoff_roster.columns):
                                    _roster_ids = dict(zip(onoff_roster["PLAYER"], onoff_roster["PLAYER_ID"]))

                                def _norm(v):
                                    return re.sub(r"[^a-z]", "", _fold_accents(v).lower())

                                def _solo_rows(name):
                                    """This player's on-court row: by his player id, else by his name ("Last, First")."""
                                    pid = _roster_ids.get(name) or (PLAYER_NAME_TO_RECORD.get(name) or {}).get("id")
                                    if pid is not None and "VS_PLAYER_ID" in solo_lineups.columns:
                                        hit = solo_lineups[pd.to_numeric(solo_lineups["VS_PLAYER_ID"], errors="coerce") == int(pid)]
                                        if not hit.empty:
                                            return hit
                                    for col in ("VS_PLAYER_NAME", "GROUP_NAME", "PLAYER_NAME"):
                                        if col in solo_lineups.columns:
                                            want = _norm(name)
                                            names = solo_lineups[col].astype(str).map(
                                                lambda v: _norm(" ".join(reversed([x.strip() for x in v.split(",", 1)])) if "," in v else v))
                                            hit = solo_lineups[names == want]
                                            if not hit.empty:
                                                return hit
                                    return solo_lineups.iloc[0:0]

                                for solo_player, other_player in [(player1, player2), (player2, player1)]:
                                        solo_match = _solo_rows(solo_player)
                                        if solo_match.empty:
                                            continue
                                        solo_row = solo_match.iloc[0]
                                        solo_min = solo_row.get("MIN", 0)
                                        without_min = solo_min - combo_min
                                        if without_min <= 0:        # never on the court without him: no such column
                                            continue

                                        # Subtraction: this player's stats
                                        # WITHOUT the other = their total
                                        # on-court total minus the together
                                        # total, confirmed as mathematically
                                        # valid for counting stats (totals
                                        # subtract cleanly). Off/Def Rating
                                        # are NOT included here deliberately
                                        # -- ratings aren't simple counting
                                        # stats, so subtracting two
                                        # already-computed rate values
                                        # wouldn't be valid the way it is
                                        # for PTS/REB/AST; showing "--" is
                                        # honest, a fabricated derived
                                        # rating would not be.
                                        without_pts = solo_row.get("PTS", 0) - combo_row.get("PTS", 0) if "PTS" in solo_row.index and "PTS" in combo_row.index else None
                                        without_reb = solo_row.get("REB", 0) - combo_row.get("REB", 0) if "REB" in solo_row.index and "REB" in combo_row.index else None
                                        without_ast = solo_row.get("AST", 0) - combo_row.get("AST", 0) if "AST" in solo_row.index and "AST" in combo_row.index else None

                                        without_pts_per48 = (without_pts / without_min) * 48 if without_pts is not None else None
                                        without_reb_per48 = (without_reb / without_min) * 48 if without_reb is not None else None
                                        without_ast_per48 = (without_ast / without_min) * 48 if without_ast is not None else None
                                        columns.append({
                                            "label": f"{solo_player} without {other_player}",
                                            "minutes": without_min,
                                            "players": [(solo_player, "ON"), (other_player, "OFF")],
                                            "metrics": [
                                                ("Off Rating", None, None, False),
                                                ("Def Rating", None, None, False),
                                                _metric_row("PTS", without_pts_per48, "PTS"),
                                                _metric_row("REB", without_reb_per48, "REB"),
                                                _metric_row("AST", without_ast_per48, "AST"),
                                            ],
                                        })



                            player_ids_lookup = {name: rec["id"] for name, rec in PLAYER_NAME_TO_RECORD.items()}
                            fig = build_onoff_column_image(
                                onoff_team_name, columns, player_ids_lookup,
                                team_logo_url=get_team_logo_url(TEAM_NAME_TO_RECORD[onoff_team_name]["id"]))
                            show_chart(fig, _hover(hover.onoff_column_hotspots, fig.axes[0], columns,
                                                   [c.get("minutes") for c in columns]), "onoff_columns")
                            add_to_tableau_dashboard(fig, "On/Off Stats", "tableau_onoff")
                            offer_share_to_community(fig, "On/Off Stats", "share_onoff")
                            plt.close(fig)


    st.stop()

elif category == "Stat Formula Creator":
    st.title("Stat Formula Creator")
    st.caption(
        "Name a custom stat, build it from any weighted combination of base stats, advanced "
        "stats, and other formulas the community has already shared, then apply it to a real "
        "player or team. Share it here and it also appears on the Community Uploads page."
    )

    formula_share_name = st.text_input("Name your stat:", key="formula_share_name")

    formula_mode = st.radio("Formula for:", ["Player", "Team"], horizontal=True, key="formula_mode")
    formula_mode_key = formula_mode.lower()

    all_stat_options = []  # list of (field, label) across every category, base+advanced together
    # label -> (field, source). The source matters: "CLUTCH PTS" and "PTS"
    # share the field name "PTS" but live in different NBA tables, and
    # looking up only the field silently used the regular-season number for
    # a clutch stat (and skipped hustle/defense/bio/calculated stats
    # entirely, since those columns aren't in the season-stats table).
    stat_label_to_spec = {}
    formula_items, formula_show = [], {}
    for stat_category, stats_in_cat in get_stats_for_mode(formula_mode_key, exclude_bradley_rating=True,
                                                          include_salary=True):
        for field, label, source, modes in stats_in_cat:
            full_label = f"{label} ({stat_category})"      # the name a saved formula refers to it by
            all_stat_options.append((field, full_label))
            stat_label_to_spec[full_label] = (field, source)
            formula_items.append((full_label, _stats_config.stat_section(field, source)))
            formula_show[full_label] = label
    _formula_order = {lbl: i for i, (lbl, _sec) in enumerate(stat_menus.stat_items(formula_mode_key, include_salary=True)[0])}
    formula_items.sort(key=lambda it: _formula_order.get(formula_show[it[0]], 999))

    # A player's formula: one "Stat mode:" for every stat in it, then "Stats:", "Bradley ratings:" and "Tendencies:"
    # (a formula can mix all three), then the community formulas -- every pick gets its weight slider below
    is_player_formula = formula_mode_key == "player"
    formula_global_mode = "PerGame"
    if is_player_formula:
        _fm_label = st.radio("Stat mode:", ["Per Game", "Per 36", "Totals"], horizontal=True, key="formula_stat_mode_all")
        formula_global_mode = {"Totals": "Totals", "Per Game": "PerGame", "Per 36": "Per36"}[_fm_label]
    picked_stat_labels = stat_menus.multiselect(
        "Stats:" if is_player_formula else "Pick stats and advanced stats:", formula_items, key="formula_stats",
        format_func=lambda v: formula_show.get(v, v),
    )
    if is_player_formula:
        picked_rating_cols = st.multiselect("Bradley ratings:", ratings_data.columns(ratings_data.RATINGS),
                                            key="formula_ratings")
        picked_tend_cols = st.multiselect("Tendencies:", ratings_data.columns(ratings_data.TENDENCIES),
                                          key="formula_tendencies")
        for _c in picked_rating_cols:
            _lbl = f"{_c} (Bradley Rating)"
            stat_label_to_spec[_lbl] = (_c, ratings_data.SOURCE_OF[ratings_data.RATINGS])
            picked_stat_labels = picked_stat_labels + [_lbl]
        for _c in picked_tend_cols:
            stat_label_to_spec[_c] = (_c, ratings_data.SOURCE_OF[ratings_data.TENDENCIES])
            picked_stat_labels = picked_stat_labels + [_c]

    community_formulas = community_storage.load_all_formulas()
    formula_name_to_entry = {f["name"]: f for f in community_formulas}
    picked_formula_names = st.multiselect(
        "Include community-uploaded formulas as components:",
        list(formula_name_to_entry.keys()),
        key="formula_community_picks",
        help="Formulas other people have already built and shared - pick any to fold into your own as a single weighted component.",
    )

    components = []
    if not picked_stat_labels and not picked_formula_names:
        st.info("Pick at least one stat or community formula above to start building.")
    else:
        st.markdown("##### Set each component's weight")
        st.caption("Weights always add up to 100% - moving one slider redistributes the rest automatically.")

        # A stable, order-preserving identity for each currently-picked
        # component, used both as each slider's own widget key suffix
        # and to detect when the picked set itself changes (a stat or
        # formula added/removed), which requires re-splitting 100%
        # across the new set from scratch.
        component_ids = [("stat", label) for label in picked_stat_labels] + [("formula", fname) for fname in picked_formula_names]
        weight_key = lambda cid: f"formula_weight_{cid[0]}_{cid[1]}"
        settled_key = lambda cid: f"{weight_key(cid)}_settled"

        prev_component_ids = st.session_state.get("_formula_component_ids")
        if prev_component_ids != component_ids:
            # The picked set changed -- re-split 100% evenly across the
            # new set (remainder to the first few, e.g. 3 components ->
            # 34/33/33) rather than trying to preserve old weights that
            # no longer correspond to the same set of components.
            n = len(component_ids)
            base = 100 // n
            remainder = 100 - base * n
            for i, cid in enumerate(component_ids):
                value = base + (1 if i < remainder else 0)
                st.session_state[weight_key(cid)] = float(value)
                st.session_state[settled_key(cid)] = float(value)
            st.session_state["_formula_component_ids"] = component_ids
        else:
            # Applies a pending redistribution (computed at the end of
            # the previous run, after detecting which slider the user
            # actually moved) before the sliders below are
            # instantiated -- confirmed elsewhere in this app that
            # Streamlit blocks direct assignment to a slider's
            # session_state once it already exists in the current run,
            # so this has to happen strictly before that point, with
            # the actual redistribution math done post-instantiation on
            # the prior run instead.
            pending = st.session_state.pop("_formula_pending_weights", None)
            if pending:
                for cid, value in pending.items():
                    st.session_state[weight_key(cid)] = value
                    st.session_state[settled_key(cid)] = value

        components = []
        current_weights = {}
        component_stat_modes = {}
        for cid in component_ids:
            kind, name = cid
            label_text = f"Weight for {name}:" if kind == "stat" else f"Weight for formula \"{name}\":"
            if kind == "stat" and is_player_formula:
                component_stat_modes[cid] = formula_global_mode         # (the one "Stat mode:" above the stats)
            elif kind == "stat":
                per_stat_mode_label = st.radio(
                    "Stat mode:", ["Per Game", "Per 36", "Totals"], horizontal=True,
                    key=f"formula_stat_mode_{name}", label_visibility="collapsed",
                )
                component_stat_modes[cid] = {"Totals": "Totals", "Per Game": "PerGame", "Per 36": "Per36"}[per_stat_mode_label]
            safe_weight_key = "".join(c if c.isalnum() else "_" for c in weight_key(cid))
            with st.container(key=f"formula_slider_wrap_{safe_weight_key}"):
                weight = st.slider(label_text, 0.0, 100.0, step=1.0, format="%.0f%%", key=weight_key(cid))
            # A per-slider, value-dependent two-stop gradient (gold up
            # to the current weight, grey after it) -- confirmed via
            # direct DOM inspection that a single-value slider has no
            # separate "filled segment" element the way a range slider
            # does, so a single generic rule can only color the whole
            # track one color, not represent the actual value. Scoped
            # to this slider's own wrapping container's key (which I
            # generate and sanitize myself) so each one reflects its
            # own weight independently.
            st.markdown(
                f"""
                <style>
                .st-key-formula_slider_wrap_{safe_weight_key} [role="group"] > div > div:first-child {{
                    background: linear-gradient(90deg, #D4AF37 0%, #D4AF37 {weight}%, #3a3a3a {weight}%, #3a3a3a 100%) !important;
                }}
                </style>
                """,
                unsafe_allow_html=True,
            )
            current_weights[cid] = weight
            if kind == "stat":
                comp_field, comp_source = stat_label_to_spec[name]
                components.append({"kind": "stat", "field": comp_field, "source": comp_source, "label": name, "weight": weight / 100, "stat_mode": component_stat_modes[cid]})
            else:
                components.append({"kind": "formula", "formula_id": formula_name_to_entry[name]["id"], "label": name, "weight": weight / 100})

        # Detects which single slider the user actually moved by
        # comparing every slider's current value to its own last-known
        # "settled" value (updated only once a redistribution is
        # applied, never on every render) -- redistributes the exact
        # opposite delta across every other component, proportional to
        # their own current weights (falling back to an even split only
        # if every other component is currently at 0), so the total
        # stays exactly 100 regardless of which slider moved or by how
        # much.
        moved_cid = None
        for cid in component_ids:
            if abs(current_weights[cid] - st.session_state.get(settled_key(cid), current_weights[cid])) > 1e-9:
                moved_cid = cid
                break
        if moved_cid is not None and len(component_ids) > 1:
            others = [cid for cid in component_ids if cid != moved_cid]
            delta = current_weights[moved_cid] - st.session_state[settled_key(moved_cid)]
            others_total = sum(current_weights[cid] for cid in others)
            new_weights = {moved_cid: current_weights[moved_cid]}
            if others_total > 1e-9:
                for cid in others:
                    share = current_weights[cid] / others_total
                    new_weights[cid] = max(0.0, current_weights[cid] - delta * share)
            else:
                even_share = max(0.0, 100.0 - current_weights[moved_cid]) / len(others)
                for cid in others:
                    new_weights[cid] = even_share
            # Rounds everything to whole percentage points, then nudges
            # the largest "other" component by whatever rounding
            # leftover remains so the total lands on exactly 100, not
            # 99 or 101 -- rounding each share independently doesn't
            # guarantee the sum comes out even.
            rounded = {cid: round(w) for cid, w in new_weights.items()}
            leftover = 100 - sum(rounded.values())
            if leftover != 0 and others:
                biggest = max(others, key=lambda cid: rounded[cid])
                rounded[biggest] += leftover
            st.session_state["_formula_pending_weights"] = {cid: float(rounded[cid]) for cid in component_ids}
            st.rerun()

        st.markdown("##### Apply to a player/team, or see the best players/teams with your stat")
        apply_how = st.radio(
            "Apply to:", ["Search by player", "Search by team", "Search by best players", "Search by best teams"],
            horizontal=True, key="formula_apply_how", label_visibility="collapsed",
        )
        apply_kind = "team" if apply_how.endswith(("team", "teams")) else "player"
        apply_best = "best" in apply_how
        apply_name = None
        if not apply_best:
            if apply_kind == "player":
                apply_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.", key="formula_apply_player")
            else:
                apply_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.", key="formula_apply_team")
        apply_season = st.selectbox("Season:", ALL_SEASONS, index=0, key="formula_apply_season")
        if apply_best:
            best_n = st.number_input("Display the top __:", min_value=3, max_value=30, value=10, key="formula_best_n")
            if persistent_run_button(True, key="formula_best", show_chart_color=False):
                _formula_best_chart(components, community_formulas, apply_kind, apply_season, int(best_n),
                                    formula_share_name.strip() or "custom stat")

        if apply_name and persistent_run_button(True, key="formula_apply", show_chart_color=False):
            with code_loading_animation("Calculating"):
                try:
                    name_col = "PLAYER_NAME" if apply_kind == "player" else "TEAM_NAME"
                    # Fetches the full league's stats separately per
                    # unique stat mode actually used by any component
                    # (not just one fixed mode for the whole formula),
                    # since each stat can now independently be Per
                    # Game/Per 36/Totals -- cached per mode so the same
                    # mode isn't fetched twice across multiple
                    # components that happen to share it. Keeps the
                    # full dataframe, not just the one player's row,
                    # since a percentile rank needs the whole league to
                    # compare against.
                    dfs_by_mode = {}
                    _side_tables = {
                        "bio": get_player_bio_stats, "defense_tracking": get_player_defense_stats,
                        "hustle": get_player_hustle_stats, "clutch": get_player_clutch_stats,
                        "salary": lambda s: fetch_stats_for_source("salary", s, apply_kind),
                        # the Bradley Ratings / Tendencies: ranked among every player who has them
                        ratings_data.SOURCE_OF[ratings_data.RATINGS]:
                            lambda s: fetch_stats_for_source(ratings_data.SOURCE_OF[ratings_data.RATINGS], s, apply_kind),
                        ratings_data.SOURCE_OF[ratings_data.TENDENCIES]:
                            lambda s: fetch_stats_for_source(ratings_data.SOURCE_OF[ratings_data.TENDENCIES], s, apply_kind),
                    }
                    if any(ratings_data.is_source(c.get("source")) for c in components) and not ratings_data.available(apply_season):
                        st.warning(f"Bradley Ratings and Tendencies are for {' and '.join(sorted(ratings_data.SEASONS))} "
                                   "only - they're left out for this season.")

                    def get_df(stat_mode, source="base"):
                        # Season stats (base/advanced/calculated) come in
                        # the per-mode league table; bio/defense/hustle/
                        # clutch each have their own table, so each
                        # component is ranked against the table its stat
                        # actually lives in. Components saved before
                        # "source" existed default to the season table.
                        table = source if source in _side_tables else "league"
                        key = (table, stat_mode if table == "league" else None)
                        if key not in dfs_by_mode:
                            if table == "league":
                                dfs_by_mode[key] = get_player_stats(apply_season, per_mode=stat_mode) if apply_kind == "player" else get_team_stats(apply_season, per_mode=stat_mode)
                            else:
                                dfs_by_mode[key] = _side_tables[table](apply_season)
                        return dfs_by_mode[key]

                    def subject_rows(df):
                        if apply_kind == "player":
                            return _rows_for_player(df, apply_name, name_col)
                        return df[df[name_col] == apply_name] if name_col in df.columns else df.iloc[0:0]

                    def percentile_rank(df, field, value):
                        # Percentage of the league this value is equal
                        # to or better than -- pandas' own rank(pct=True)
                        # gives exactly this in one step: 100 means this
                        # value ties or beats everyone in the league for
                        # this stat and season, 50 means the middle of
                        # the pack.
                        ranks = df[field].rank(pct=True)
                        row_match = df.index[df[field] == value]
                        if len(row_match) == 0:
                            return None
                        return float(ranks.loc[row_match[0]]) * 100

                    total = 0.0
                    breakdown = []
                    any_row_found = False
                    # Resolves a community formula's own components
                    # one level deep only (not fully recursive) --
                    # a deliberate, simple safeguard against a
                    # formula that includes itself, or a long
                    # chain of formulas including each other,
                    # rather than needing cycle-detection logic
                    # for a feature this new.
                    for comp in components:
                        if comp["kind"] == "stat":
                            df = get_df(comp.get("stat_mode", "PerGame"), comp.get("source", "base"))
                            match = subject_rows(df)
                            if match.empty:
                                continue
                            row = match.iloc[0]
                            any_row_found = True
                            if comp["field"] not in row.index or pd.isna(row[comp["field"]]):
                                st.warning(f"{comp['label']} isn't available for {apply_name} in {apply_season} - skipped.")
                                continue
                            raw_value = float(row[comp["field"]])
                            pct = percentile_rank(df, comp["field"], raw_value)
                            if pct is None:
                                continue
                            contribution = pct * comp["weight"]
                            total += contribution
                            breakdown.append((comp["label"], raw_value, pct, comp["weight"], contribution))
                        else:
                            sub_entry = next((f for f in community_formulas if f["id"] == comp["formula_id"]), None)
                            if not sub_entry:
                                continue
                            sub_total = 0.0
                            for sub_comp in sub_entry["formula_data"]:
                                if sub_comp.get("kind") != "stat":
                                    continue  # one level deep only
                                sub_df = get_df(sub_comp.get("stat_mode", "PerGame"), sub_comp.get("source", "base"))
                                sub_match = subject_rows(sub_df)
                                if sub_match.empty:
                                    continue
                                sub_row = sub_match.iloc[0]
                                any_row_found = True
                                if sub_comp["field"] not in sub_row.index or pd.isna(sub_row[sub_comp["field"]]):
                                    continue
                                sub_value = float(sub_row[sub_comp["field"]])
                                sub_pct = percentile_rank(sub_df, sub_comp["field"], sub_value)
                                if sub_pct is None:
                                    continue
                                sub_total += sub_pct * sub_comp["weight"]
                            contribution = sub_total * comp["weight"]
                            total += contribution
                            breakdown.append((f"{comp['label']} (formula)", None, sub_total, comp["weight"], contribution))

                    if not any_row_found:
                        st.error(f"No {apply_season} data found for {apply_name}.")
                    else:
                        st.metric(f"{apply_name} - {apply_season} formula rating", f"{total:.1f}")
                        st.caption("Rating is a 0-100 scale based on each stat's percentile rank across the full league that season - 100 means best in the league, 50 means the middle of the pack.")
                        # Surfaces the actual inputs behind this specific
                        # result -- how many players/teams the
                        # percentile was computed against, and the
                        # subject's own games-played count if available
                        # -- so a result from a small early-season
                        # sample (2025-26 is the current, still-in-
                        # progress season) is checkable rather than a
                        # black box that could look "stuck" the same
                        # way a real staleness bug would.
                        def _table_label(key):
                            table, mode_used = key
                            nice = {ratings_data.SOURCE_OF[ratings_data.RATINGS]: "Bradley Ratings",
                                    ratings_data.SOURCE_OF[ratings_data.TENDENCIES]: "Tendencies"}
                            return f"{mode_used}" if table == "league" else nice.get(table, table.replace("_", " "))
                        sample_note = ", ".join(
                            f"{len(dfs_by_mode[k])} {'players' if apply_kind == 'player' else 'teams'} ({_table_label(k)})"
                            for k in dfs_by_mode
                        )
                        gp_note = ""
                        league_keys = [k for k in dfs_by_mode if k[0] == "league"]
                        if league_keys:
                            gp_rows = subject_rows(dfs_by_mode[league_keys[0]])
                            if not gp_rows.empty and "GP" in gp_rows.columns and pd.notna(gp_rows.iloc[0].get("GP")):
                                gp_note = f" - {apply_name} has played {int(gp_rows.iloc[0]['GP'])} games in {apply_season}"
                        st.caption(f"Computed against: {sample_note}{gp_note}.")
                        with st.expander("Breakdown"):
                            for label, raw_value, pct, weight, contribution in breakdown:
                                if raw_value is None:
                                    st.write(f"{label}: {pct:.1f} percentile x {weight:g} = {contribution:.1f}")
                                else:
                                    st.write(f"{label}: {raw_value:,.2f} ({pct:.1f} percentile) x {weight:g} = {contribution:.1f}")
                except Exception as e:
                    st.error(f"Couldn't calculate this formula: {e}")

    st.markdown("---")
    if components:
        st.markdown("##### Share this formula")
        formula_share_desc = st.text_area("Description:", key="formula_share_desc")
        if st.button("Share to the \"Community Uploads\" page", key="formula_share_btn"):
            if not formula_share_name.strip():
                st.warning("Give your formula a name first.")
            else:
                community_storage.save_formula(formula_share_name.strip(), formula_share_desc.strip(), components)
                st.success("Posted - also appears on the Community Uploads page.")
                _community_backup_notice()

    st.markdown("#### Community Formulas")
    st.caption("Every formula shared here so far - browse for inspiration or to reuse as a component above.")
    gallery_formulas = community_storage.load_all_formulas()
    if not gallery_formulas:
        st.write("No formulas shared yet - be the first.")
    else:
        gallery_cols = st.columns(3)
        for i, entry in enumerate(gallery_formulas):
            with gallery_cols[i % 3]:
                image_path = community_storage.get_image_path(entry["image_filename"])
                if os.path.exists(image_path):
                    st.image(image_path, use_container_width=True)
                st.markdown(f"**{entry['name']}**")
                if entry.get("description"):
                    st.caption(entry["description"])
                component_summary = ", ".join(f"{c['label']} (x{c['weight']:g})" for c in entry["formula_data"])
                st.caption(component_summary)
    st.stop()

elif category == "Tableau Dashboard":
    st.title("Tableau Dashboard")
    st.caption(
        "Build a custom collage from up to 6 charts. Click the + on an "
        "empty slot to jump to a page, generate any chart the regular "
        "way, then use its \"Add to Tableau Dashboard\" button. Use the "
        "arrow buttons under a slot to swap its position with a "
        "neighbor - true mouse drag-and-drop isn't something plain "
        "Streamlit can reliably support without a custom component "
        "package, so this is the direct-manipulation alternative."
    )

    # Tightens the grid so slots sit closer together, more like an
    # actual collage, than Streamlit's own default column gap gives --
    # targets Streamlit's own column-gap CSS variable rather than
    # individual elements, so it applies consistently regardless of
    # exactly what's inside each column.
    st.markdown(
        """
        <style>
        div[data-testid="stHorizontalBlock"] { gap: 0.5rem !important; }
        div[data-testid="column"] { padding: 0 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "tableau_slots" not in st.session_state:
        st.session_state.tableau_slots = [None] * 6

    def _swap_slots(a, b):
        st.session_state.tableau_slots[a], st.session_state.tableau_slots[b] = (
            st.session_state.tableau_slots[b], st.session_state.tableau_slots[a],
        )
        st.rerun()

    def _render_tableau_slot(idx):
        slot = st.session_state.tableau_slots[idx]
        if slot is None:
            st.markdown(
                f"""
                <style>
                .st-key-no_icon_tableau_plus_wrap_{idx} button {{
                    height: 200px !important;
                    background: #1a1a1a !important;
                }}
                .st-key-no_icon_tableau_plus_wrap_{idx} button p {{
                    font-size: 60px !important;
                }}
                </style>
                """,
                unsafe_allow_html=True,
            )
            with st.container(key=f"no_icon_tableau_plus_wrap_{idx}"):
                if st.button("+", key=f"tableau_plus_{idx}", use_container_width=True):
                    st.session_state["tableau_target_slot"] = idx
                    nav_to("Search by Player")
        else:
            st.image(slot["image_bytes"], use_container_width=True, caption=slot["source"])
            row, col = divmod(idx, 3)
            # Only the directions actually valid for THIS slot -- a
            # fixed 4-column grid left 2 columns empty for every corner
            # slot (6 of the 8 possible slots), which is exactly why
            # the buttons looked small and didn't fill the row: they
            # were confined to half the available columns instead of
            # the row's full width.
            directions = []
            if col > 0:
                directions.append(("left", idx - 1))
            if col < 2:
                directions.append(("right", idx + 1))
            if row > 0:
                directions.append(("up", idx - 3))
            if row < 1:
                directions.append(("down", idx + 3))

            # Genuine arrow shapes (a shaft plus an arrowhead, via
            # clip-path polygons) directly on each button's own text --
            # a plain triangle (the border-trick this used previously)
            # isn't what "arrow" means, confirmed directly against an
            # isolated rendered test before applying this shape here.
            # Not Unicode arrow emoji either, since a device/browser's
            # font not including the arrow glyphs is a real cross-
            # platform risk, confirmed directly: that's exactly what
            # produced plain squares instead of arrows originally.
            arrow_svg_paths = {
                "left": "M7.5 2.5L4 6L7.5 9.5",
                "right": "M4.5 2.5L8 6L4.5 9.5",
                "up": "M2.5 7.5L6 4L9.5 7.5",
                "down": "M2.5 4.5L6 8L9.5 4.5",
            }
            css_rules = "".join(
                f"""
                .st-key-bq_arrow_wrap_{direction}_{idx} button {{
                    height: 46px !important;
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                }}
                .st-key-bq_arrow_wrap_{direction}_{idx} button > div {{
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    height: 100% !important;
                    width: 100% !important;
                }}
                .st-key-bq_arrow_wrap_{direction}_{idx} button span {{
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                }}
                .st-key-bq_arrow_wrap_{direction}_{idx} button div[data-testid="stMarkdownContainer"] {{
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                }}
                .st-key-bq_arrow_wrap_{direction}_{idx} button p {{
                    font-size: 0 !important;
                    display: inline-block !important;
                    width: 14px !important;
                    height: 14px !important;
                    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none'%3E%3Cpath d='{svg_path}' stroke='%23D4AF37' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") !important;
                    background-repeat: no-repeat !important;
                    background-position: center !important;
                    -webkit-background-clip: border-box !important;
                    background-clip: border-box !important;
                }}
                .st-key-bq_arrow_wrap_{direction}_{idx} button p::before {{
                    content: none !important;
                }}
                """
                for direction, svg_path in arrow_svg_paths.items()
            )
            st.markdown(f"<style>{css_rules}</style>", unsafe_allow_html=True)
            with st.container(key=f"no_icon_tableau_arrows_{idx}"):
                arrow_cols = st.columns(len(directions))
                labels = {"left": "Left", "right": "Right", "up": "Up", "down": "Down"}
                for i, (direction, target_idx) in enumerate(directions):
                    with arrow_cols[i]:
                        with st.container(key=f"bq_arrow_wrap_{direction}_{idx}"):
                            if st.button(labels[direction], key=f"tableau_{direction}_{idx}", use_container_width=True,
                                         help=f"Swap with the slot to the {direction}" if direction in ("left", "right") else f"Swap with the slot {direction}"):
                                _swap_slots(idx, target_idx)
            with st.container(key=f"no_icon_tableau_remove_{idx}"):
                if st.button("Remove", key=f"tableau_remove_{idx}", use_container_width=True):
                    st.session_state.tableau_slots[idx] = None
                    st.rerun()

    st.markdown(
        """
        <style>
        .st-key-tableau_grid > div[data-testid="stLayoutWrapper"]:first-child {
            margin-bottom: -20px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="tableau_grid"):
        row1 = st.columns(3)
        for i in range(3):
            with row1[i]:
                _render_tableau_slot(i)
        row2 = st.columns(3)
        for i in range(3, 6):
            with row2[i - 3]:
                _render_tableau_slot(i)

    st.markdown("---")

    if any(s is not None for s in st.session_state.tableau_slots):
        with st.container(key="no_icon_tableau_reset"):
            if st.button("Reset Dashboard", use_container_width=True, key="tableau_reset"):
                st.session_state.tableau_slots = [None] * 6
                st.rerun()

        from PIL import Image as _PILImage

        cell_w, cell_h = 500, 400
        collage = _PILImage.new("RGBA", (cell_w * 3, cell_h * 2), (13, 13, 13, 255))
        for i, slot in enumerate(st.session_state.tableau_slots):
            if slot is None:
                continue
            row_i, col_i = divmod(i, 3)
            img = _PILImage.open(io.BytesIO(slot["image_bytes"])).convert("RGBA")
            img.thumbnail((cell_w - 20, cell_h - 20))
            x = col_i * cell_w + (cell_w - img.width) // 2
            y = row_i * cell_h + (cell_h - img.height) // 2
            collage.paste(img, (x, y), img)
        out_buf = io.BytesIO()
        collage.save(out_buf, format="PNG")
        st.download_button(
            "Download Collage as PNG", data=out_buf.getvalue(),
            file_name="tableau_dashboard.png", mime="image/png", use_container_width=True,
        )
    else:
        st.caption("No charts added yet.")
    st.stop()

elif category == "Upload Stats":
    import types
    import upload_stats

    @st.cache_data(show_spinner=False)
    def _upload_league_shots(season):
        # NBA reference data only (never anything the person uploaded) -- safe to share across sessions.
        return get_league_shots(season)

    upload_stats.render_upload_stats_page(types.SimpleNamespace(
        run_button=persistent_run_button,
        loading=code_loading_animation,
        tableau=add_to_tableau_dashboard,
        info_card=info_card,
        color_picker=lambda key: color_input_with_dropdown(key, default_team="Gold"),
        resolve_color=resolve_color_input,
        league_shots=_upload_league_shots,
        seasons=ALL_SEASONS,
    ))
    st.stop()

elif category == "Community Uploads":
    st.title("Community Uploads")
    st.caption(
        "Charts shared by anyone using this app. Generate a chart in "
        "Search by Player, Search by Team, Search by Criteria, or Trade "
        "Machine, then use the \"Share to Community Uploads\" "
        "option underneath it to publish here."
    )
    st.caption(community_storage.github_persistence_status())

    shared_items = community_storage.load_all()
    if not shared_items:
        st.markdown("Nothing shared yet - be the first.")
    else:
        for item in shared_items:
            img_path = community_storage.get_image_path(item["image_filename"])
            if os.path.exists(img_path):
                cols = st.columns([1, 2])
                with cols[0]:
                    st.image(img_path, use_container_width=True)
                with cols[1]:
                    st.markdown(f"**{item['name']}**")
                    if item.get("description"):
                        st.markdown(item["description"])
                    st.caption(f"From {item['source_section']}")
            st.markdown("---")
    st.stop()

# =============================================================================
# GLOSSARY
# =============================================================================
elif category == "Glossary":
    st.title("Glossary")
    st.caption("Every stat and chart in this dashboard - and the live windows on bradley-analytics.com - in one place. "
               "The stats are grouped the same way as every stat menu: Offense, Playmaking, Rebounding, Defense, Overall.")
    GLOSSARY = [
        ("Offense", [
            ("PTS", "Points scored."),
            ("OFF RTG", "Offensive Rating - points scored per 100 possessions. For a player: his team's points per 100 "
                        "possessions while he's on the floor."),
            ("TS%", "True Shooting Percentage - PTS / (2 x (FGA + 0.44 x FTA)): scoring efficiency that counts the extra "
                    "value of 3-pointers and free throws, not just field goals."),
            ("EFG%", "Effective Field Goal Percentage - (FGM + 0.5 x 3PM) / FGA: field-goal percentage with a made 3 "
                     "worth 1.5 times a made 2."),
            ("USG%", "Usage Rate - the share of his team's plays (shots, free throws, turnovers) a player finishes while "
                     "he's on the floor."),
            ("FGM / FGA / FG%", "Field goals made, attempted, and made per attempt (everything but free throws)."),
            ("3PM / 3PA / 3P%", "3-pointers made, attempted, and made per attempt."),
            ("FTM / FTA / FT%", "Free throws made, attempted, and made per attempt."),
            ("PPS", "Points Per Shot - points scored per field-goal attempt."),
            ("FT RATE", "Free Throw Rate - free-throw attempts per field-goal attempt: how often a player gets to the line."),
            ("3PA RATE", "3-Point Attempt Rate - the share of field-goal attempts that are 3-pointers."),
            ("BRADLEY 3PT RATING", BRADLEY_RATING_DESCRIPTIONS.get("BRADLEY_3PT_RATING", "Bradley Analytics' own "
                                   "3-point shooting rating.")),
            ("PFD", "Personal Fouls Drawn - fouls committed against the player."),
            ("BLKA", "Blocked Attempts - the player's own shots that got blocked."),
            ("CLUTCH PTS / FG% / 3P%", "Scoring and shooting in clutch time: the last 5 minutes of a game within 5 points."),
        ]),
        ("Playmaking", [
            ("AST", "Assists - passes that lead directly to a teammate's made basket."),
            ("TOV", "Turnovers - possessions lost to the other team (lower is better)."),
            ("AST%", "Assist Percentage - the share of his teammates' made baskets a player assisted while on the floor."),
            ("AST/TO", "Assist-to-Turnover Ratio - assists per turnover."),
            ("AST RATIO", "Assist Ratio - assists per 100 of the player's own possessions."),
            ("TOV%", "Turnover Percentage - turnovers per 100 plays (lower is better)."),
            ("SCREEN ASSISTS", "Screens that directly freed a teammate for a made basket."),
            ("CLUTCH AST", "Assists in clutch time (the last 5 minutes of a game within 5 points)."),
        ]),
        ("Rebounding", [
            ("REB", "Rebounds - offensive and defensive combined."),
            ("OREB / DREB", "Offensive rebounds (off his own team's misses) and defensive rebounds (off the other team's)."),
            ("REB% / OREB% / DREB%", "The share of the available rebounds a player grabbed while on the floor - all of "
                                    "them, offensive only, defensive only."),
            ("BOX OUTS", "Times a player boxed out an opponent on a shot."),
            ("CLUTCH REB", "Rebounds in clutch time (the last 5 minutes of a game within 5 points)."),
        ]),
        ("Defense", [
            ("DEF RTG", "Defensive Rating - points allowed per 100 possessions (lower is better). For a player: while he's "
                        "on the floor."),
            ("STL", "Steals."),
            ("BLK", "Blocks."),
            ("PF", "Personal Fouls committed (lower is better)."),
            ("OPP FG%", "Opponents' field-goal percentage on the shots this player defended (the NBA's player tracking)."),
            ("LEAGUE AVG FG%", "What the whole league shoots on those same shots."),
            ("DEF IMPACT", "OPP FG% minus the league average on the same shots, in percentage points - below zero means "
                           "opponents shoot worse than usual against him."),
            ("DEF FGA", "Shots defended."),
            ("CONTESTED SHOTS / DEFLECTIONS / CHARGES DRAWN / LOOSE BALLS RECOVERED",
             "Effort (\"hustle\") stats: shots contested, passes and dribbles deflected, offensive fouls drawn, and loose "
             "balls recovered."),
        ]),
        ("Overall", [
            ("NET RTG", "Net Rating - OFF RTG minus DEF RTG: points scored minus points allowed per 100 possessions."),
            ("PIE", "Player Impact Estimate - the share of everything that happens in his games (points, rebounds, "
                    "assists, steals...) a player accounts for."),
            ("+/-", "Plus/Minus - the score difference while the player (or lineup) is on the floor."),
            ("MIN / GP", "Minutes played and games played."),
            ("PACE", "Possessions per 48 minutes - how fast a team (or a player's minutes) plays."),
            ("DD2 / TD3", "Double-doubles and triple-doubles (10+ in two or three of points, rebounds, assists, steals, "
                          "blocks)."),
            ("W / L / W%", "Wins, losses and winning percentage."),
            ("SALARY", "The season's salary (cap hit) in $ millions - a team's: its whole payroll."),
            ("AGE / HEIGHT / WEIGHT", "Age during the season, height in inches, weight in pounds."),
            ("DRAFT YR / RD / PICK", "The year, round and pick number a player was drafted with."),
            ("CLUTCH +/-", "Plus/Minus in clutch time (the last 5 minutes of a game within 5 points)."),
            ("Per Game / Per 36 / Totals", "How a stat is counted: per game played, per 36 minutes on the floor, or the "
                                           "season total."),
        ]),
        ("Lineups", [
            ("Lineup Network", "Every combination of teammates who shared the court (2, 3, 4 or 5 of them), connected and "
                               "colored by how that group played together."),
            ("Lineup Net Rating", "A group's points scored minus allowed per 100 possessions with exactly those players on "
                                  "the floor together."),
            ("Minutes / Games Together", "How long, and in how many games, a group has played together."),
            ("On/Off Stats", "How a team's per-48-minute numbers change with two or three chosen teammates on the floor "
                             "together, compared with the team's season average."),
        ]),
        ("Charts", [
            ("Shot Chart", "Every shot on the court, made and missed."),
            ("Heat Map", "Where on the court shots come from, shaded by how often."),
            ("Hex Shot Chart", "The court in hexagons: size for how often, color for how well compared with the league."),
            ("Animated Shot Chart", "Every shot of the season appearing in order (downloadable as a GIF)."),
            ("Passing Web", "A passer's favorite targets, each placed where he shoots most after the passer's passes - "
                            "by player, or by team with a chosen passer (and receiver)."),
            ("Season Trend Chart", "A stat game by game through a season (or its running total, or hot and cold streaks)."),
            ("Archetype Radar Chart", "A player's or team's profile across several stats at once, against the league."),
            ("Clutch Impact Clock", "How a player or team does in each part of the game clock."),
            ("Career Combo Chart", "A volume stat as bars and a rate stat as a line, season by season."),
            ("Scoring Splits Waterfall Chart", "Points split into free throws, 2-pointers and 3-pointers."),
            ("League Comparing Tornado Chart", "Several stats against the league average side by side."),
            ("Calendar Heat Map", "A stat for every game day of a season, laid out like a calendar."),
            ("Shot Flow (Sankey)", "How shots flow from where they're taken to made or missed."),
            ("Multi-Season Slope Chart", "How a stat changed from one season to another."),
            ("Bar Chart / Scatter Plot", "The league's leaders in a stat, or every player plotted by two stats."),
            ("League Average Histogram / Box Plot / Cumulative Percentile Plot",
             "How a stat is spread across the league, where a player or team sits in it, and what percentile they're in."),
            ("Stat Formula Creator", "Build your own rating by weighting any stats together."),
        ]),
        ("Live games on bradley-analytics.com", [
            ("Win Probability", "Each team's chance to win after every score, from the margin, the time and possessions "
                                "left, home court, and how the fives on the floor have played together."),
            ("Lead changes / Times tied", "How often the lead switched teams, and how often the score was level."),
            ("Lead time", "How long each team was ahead during the game."),
            ("Hot Hand", "A player with 3+ made shots in a row, or 60%+ shooting on 8+ shots, in that game."),
            ("Momentum Run", "A team with 3+ wins in a row, or 8 of its last 10, going into that game."),
            ("Season / Live Game Net Ratings", "The Lineup Network window's two views: the five's net ratings together this "
                                               "season (from this dashboard), or so far in this game."),
            ("Timeouts / BONUS", "Timeouts a team has left, and when the other team is in the bonus (every foul means "
                                 "free throws)."),
        ]),
    ]
    # The search box is a menu of every term that narrows as you type -- to the terms that START with what's typed
    # ("Shot" -> Shot Chart, Shot Flow (Sankey)). Pick one to see just it.
    _all_terms = [t for _sec, terms in GLOSSARY for t, _d in terms]
    picked = st.selectbox("Search the glossary:", _all_terms, index=None, placeholder="", key="glossary_search",
                          filter_mode="prefix")
    query = str(picked or "").strip().lower()
    exact = picked in _all_terms
    shown = 0
    for section, terms in GLOSSARY:
        hits = [(t, d) for t, d in terms
                if not query or (t == picked if exact else (query in t.lower() or query in d.lower()))]
        if not hits:
            continue
        shown += len(hits)
        st.markdown(f'<div class="ba-gloss-head">{html_escape(section)}</div>', unsafe_allow_html=True)
        st.markdown("".join(f'<div class="ba-gloss-row"><b>{html_escape(t)}</b> - {html_escape(d)}</div>' for t, d in hits),
                    unsafe_allow_html=True)
    if not shown:
        st.caption("Nothing matches that - try another word.")
    st.markdown("<style>.ba-gloss-head { font-family: Arial, Helvetica, sans-serif; font-weight: 700; color: #8f8f8f; "
                "letter-spacing: .08em; text-transform: uppercase; font-size: 0.8rem; border-top: 1px solid #3a3a3a; "
                "padding-top: 12px; margin: 18px 0 8px; } .ba-gloss-row { margin: 0 0 8px; line-height: 1.5; }</style>",
                unsafe_allow_html=True)
    st.stop()




mode = "player" if category == "Search by Player" else "team"
st.title(category)


# ---------------------------------------------------------------- Step 2: Visualization
# GAME_LOG_GRAPHS and most of COMPARISON_GRAPHS only offered in player
# mode -- get_player_game_log() is player-specific, and Waterfall/
# Combo/Tornado/Radar/Slope are all built around a specific player's
# own numbers, so offering them under Search by Team would be a dead
# end that always errors; the charts below work for both modes.
BOTH_MODE_COMPARISON_GRAPHS = [
    'Waterfall Chart', 'Tornado Chart', 'Radar Chart',
    'Shot Flow (Sankey)', 'Court + Radar Hybrid',
    'Combo Chart', 'Calendar Heat Map', 'Impact Clock',
    'Passing Connections',        # under Search by Team: pick the team, then its passer (and a receiver, if wanted)
    'Line / Trend Chart',         # Season Trend Chart: a team's game log (get_team_game_log) works the same way
]
PLAYER_ONLY_COMPARISON_GRAPHS = [g for g in COMPARISON_GRAPHS if g not in BOTH_MODE_COMPARISON_GRAPHS]
# Box Plot shows every team's roster spread on a stat -- shows up only
# under Search by Team, since "every team" doesn't have an equivalent
# meaning for a single selected player.
TEAM_ONLY_AXIS_GRAPHS = ['Box Plot']
all_visualizations_unfiltered = (
    COURT_GRAPHS + AXIS_GRAPHS + ANIMATED_GRAPHS + BOTH_MODE_COMPARISON_GRAPHS
    + ([g for g in GAME_LOG_GRAPHS if g not in BOTH_MODE_COMPARISON_GRAPHS] + PLAYER_ONLY_COMPARISON_GRAPHS
       if mode == "player" else TEAM_ONLY_AXIS_GRAPHS)
)
# (each chart once, in the order VIZ_CATEGORIES lists them)
all_visualizations_unfiltered = list(dict.fromkeys(all_visualizations_unfiltered))

# Dot Plot and Density Plot are internal display modes of Bar Chart and
# Histogram now, not their own selectable entries -- excluded from the
# mode-filtered list above before it's split into the 3 top-level
# categories below, so they never show up as their own option anywhere.
all_visualizations_unfiltered = [v for v in all_visualizations_unfiltered if v not in ("Dot Plot", "Density Plot", "Momentum Chart")]

viz_category = st.radio(
    "Visualization Category:",
    list(VIZ_CATEGORIES.keys()),
    horizontal=True,
    key="viz_category",
)
all_visualizations = [v for v in VIZ_CATEGORIES[viz_category] if v in all_visualizations_unfiltered]

# Display-only renames -- the selectbox's actual return value (used
# by every is_xxx flag below and throughout the rest of this branch)
# stays the original internal name; only the label shown to the
# person changes. Keeping the stored value unchanged is deliberately
# the lowest-risk way to rename these across a codebase with many
# string comparisons against the original names, rather than renaming
# the names themselves everywhere they're used.
VIZ_DISPLAY_NAMES = {
    "Passing Connections": "Passing Web",
    "Line / Trend Chart": "Season Trend Chart",
    "Radar Chart": "Archetype Radar Chart",
    "Impact Clock": "Clutch Impact Clock",
    "Combo Chart": "Career Combo Chart",
    "Waterfall Chart": "Scoring Splits Waterfall Chart",
    "Tornado Chart": "League Comparing Tornado Chart",
    "Slope Chart": "Multi-Season Slope Chart",
    "Histogram": "League Average Histogram",
    "Cumulative Distribution Plot": "Cumulative Percentile Plot",
}

# (keyed, so an AI Search link can open a chart; a choice this category doesn't have starts over on its first chart)
if all_visualizations and st.session_state.get("viz_select") not in all_visualizations:
    st.session_state["viz_select"] = all_visualizations[0]
visualization = st.selectbox(
    "Visualization:",
    all_visualizations,
    index=0,                      # the first chart of the category (Shot Chart first), so all of its fields show at once
    format_func=lambda v: VIZ_DISPLAY_NAMES.get(v, v),
    key="viz_select",
)

if visualization is None:
    st.stop()

is_axis_graph = visualization in AXIS_GRAPHS
is_scatter_plot = visualization == "Scatter Plot"
is_bar_chart = visualization == "Bar Chart"
is_line_chart = visualization == "Line / Trend Chart"
is_slope_chart = visualization == "Slope Chart"
is_waterfall_chart = visualization == "Waterfall Chart"
is_combo_chart = visualization == "Combo Chart"
is_tornado_chart = visualization == "Tornado Chart"
is_radar_chart = visualization == "Radar Chart"
is_calendar_heat_map = visualization == "Calendar Heat Map"
is_court_radar_hybrid = visualization == "Court + Radar Hybrid"
is_sankey_flow = visualization == "Shot Flow (Sankey)"
is_impact_clock = visualization == "Impact Clock"
is_court_connection = visualization == "Passing Connections"
is_histogram = visualization == "Histogram"
is_box_plot = visualization == "Box Plot"
is_cumdist_plot = visualization == "Cumulative Distribution Plot"
is_court_graph = visualization in COURT_GRAPHS
is_animated = visualization in ANIMATED_GRAPHS

# A single, shared Per Game/Per 36/Totals selector appearing before
# any visualization-specific stat selection, explicitly requested on
# every visualization section here -- matches Search by Criteria's own
# "Stat mode:" radio exactly (same label, same three options, same
# per_mode value mapping) rather than each of the 15+ branches below
# needing its own separate copy.
# Per Game/Per 36/Totals is meaningless for visualizations built from
# raw shot-level or pass-level data rather than aggregated stats --
# explicitly requested to hide it there rather than showing an option
# that changes nothing.
_needs_stat_mode = not (is_court_graph or is_animated or is_court_connection)
# Search by Player's Tornado Chart draws its "Stat mode:" itself, right above the stats it applies to
_stat_mode_inline = is_tornado_chart and mode == "player"


def _shared_stat_mode_radio():
    label = st.radio("Stat mode:", ["Per Game", "Per 36", "Totals"], horizontal=True, key="shared_stat_mode")
    return {"Totals": "Totals", "Per Game": "PerGame", "Per 36": "Per36"}[label]


# These charts draw "Stat mode:" themselves, under the player/team and season it applies to. The value it holds is
# already in session state before the script runs, so it can be read up here.
_STAT_MODE_BELOW_SUBJECT = {"Line / Trend Chart", "Waterfall Chart", "Combo Chart", "Tornado Chart", "Slope Chart",
                            "Radar Chart", "Calendar Heat Map", "Shot Flow (Sankey)", "Impact Clock", "Bar Chart",
                            "Histogram", "Cumulative Distribution Plot", "Scatter Plot"}
if _needs_stat_mode and (_stat_mode_inline or visualization in _STAT_MODE_BELOW_SUBJECT):
    shared_per_mode = {"Totals": "Totals", "Per Game": "PerGame", "Per 36": "Per36"}.get(
        st.session_state.get("shared_stat_mode", "Per Game"), "PerGame")
elif _needs_stat_mode:
    shared_stat_mode_label = st.radio(
        "Stat mode:", ["Per Game", "Per 36", "Totals"], horizontal=True, key="shared_stat_mode",
    )
    shared_per_mode = {"Totals": "Totals", "Per Game": "PerGame", "Per 36": "Per36"}[shared_stat_mode_label]
else:
    shared_per_mode = "PerGame"


# ---------------------------------------------------------------- Branch: Court Graphs / Animated
if is_court_graph or is_animated:

    if mode == "player":
        # A single native selectbox populated with every player, rather
        # than a text field that only shows a dropdown after pressing
        # Enter -- Streamlit's own selectbox has a real, live, type-as-
        # you-go search built in (confirmed directly: typing "Tatum"
        # alone correctly surfaces "Jayson Tatum" instantly, no separate
        # submit step), so this gets genuine live filtering by first OR
        # last name for free, with no custom JS required.
        picked_name = st.selectbox(
            "Player:",
            ALL_PLAYER_NAMES,
            index=None,
            placeholder="Enter player name.",
        )

        player_id = None
        season = None

        if picked_name:
            player = PLAYER_NAME_TO_RECORD[picked_name]
            player_id = player["id"]
            st.success(f"Found: {player['full_name']}")

            with code_loading_animation("Looking up available seasons"):
                real_seasons = get_player_career_seasons(player_id)

            if real_seasons is None:
                # Fallback if the career-span lookup fails for any
                # reason (network issue, proxy problem, etc.) --
                # a reasonable recent-seasons range rather than a
                # hard crash.
                current_season_start_year = _stats_config.current_season_start_year()
                real_seasons = [f"{y}-{str(y+1)[2:]}" for y in range(current_season_start_year, current_season_start_year - 10, -1)]
                st.caption("Couldn't load this player's exact career span - showing recent seasons instead.")

            # Court graphs (Shot Chart, Heat Map, Hex Shot Chart,
            # Animated Shot Chart) all depend on LOC_X/LOC_Y
            # shot-location data, which the NBA didn't track
            # before the 1996-97 season -- confirmed directly
            # (1996-97 shot charts generate real data, 1995-96
            # returns nothing). Seasons before that are removed
            # from this dropdown specifically, since no court
            # graph could ever produce real output for them.
            if is_court_graph or is_animated:
                real_seasons = [s for s in real_seasons if int(s[:4]) >= 1996]
                if not real_seasons:
                    st.warning("This player's career ended before shot-location data was tracked (1996-97) - no court visualization is possible for them.")

            season = st.selectbox(
                "Season:", real_seasons,
                index=0,
            )
        else:
            # every field shows from the start: until a player is picked, every season with shot locations
            season = st.selectbox("Season:", [s for s in ALL_SEASONS if int(s[:4]) >= 1996], index=0)

    else:
        team_query = st.selectbox(
            "Team:", ALL_TEAM_NAMES, index=None,
            placeholder="Enter team name.",
        )
        season = st.selectbox(
            "Season:", [s for s in ALL_SEASONS if int(s[:4]) >= 1996],
            index=0,
        )
        player_id = None

    subject_name = picked_name if mode == "player" else team_query
    if not is_scatter_plot:
        default_team = _default_color_team(mode, subject_name, season) if subject_name else None
        color_input = color_input_with_dropdown(f"court_color_box_{mode}_{subject_name}_{season}", default_team)
    else:
        color_input = None

    ready_to_run = bool(season) and bool(subject_name) and (is_scatter_plot or bool(color_input))
    run = persistent_run_button(ready_to_run, key=visualization)

    if run:
        if mode == "player" and player_id:
            with code_loading_animation("Downloading shot data"):
                shots = get_player_shots(player_id, season)

            team_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR

            if visualization == "Shot Chart":
                fig = build_shot_chart(shots, team_color)
                show_chart(fig, _hover(hover.shot_chart_hotspots, fig.axes[0], shots,
                                       _game_lookup("player", player_id, season), False), "shot_chart")
                add_to_tableau_dashboard(fig, f"Search by {mode.capitalize()} - Shot Chart", "tableau_shot_chart")
                offer_share_to_community(fig, f"Search by {mode.capitalize()} - Shot Chart", "share_shot_chart")
            elif visualization == "Heat Map":
                fig = build_heat_map(shots, team_color)
                show_chart(fig, _hover(hover.heat_map_hotspots, fig.axes[0], shots,
                                       get_zone_league_averages(season, player_id=player_id),
                                       _last_name(picked_name), color=team_color), "heat_map")
                add_to_tableau_dashboard(fig, f"Search by {mode.capitalize()} - Heat Map", "tableau_heat_map")
                offer_share_to_community(fig, f"Search by {mode.capitalize()} - Heat Map", "share_heat_map")
            elif visualization == "Hex Shot Chart":
                with code_loading_animation("Downloading league-wide comparison data"):
                    league_shots = get_league_shots(season)
                fig, hex_records = build_hex_shot_chart(shots, league_shots, team_color, return_hotspot_data=True)
                show_chart(fig, _hover(hover.hex_chart_hotspots, fig.axes[0], hex_records, _last_name(picked_name),
                                       color=team_color), "hex_chart")
                add_to_tableau_dashboard(fig, f"Search by {mode.capitalize()} - Hex Shot Chart", "tableau_hex_chart")
                offer_share_to_community(fig, f"Search by {mode.capitalize()} - Hex Shot Chart", "share_hex_chart")
            elif visualization == "Animated Shot Chart":
                with code_loading_animation("Building animation - this takes a little longer", code=build_animated_shot_chart):
                    gif_buffer = build_animated_shot_chart(shots, team_color)
                _show_animated_shot_chart(gif_buffer)
                add_to_tableau_dashboard(gif_buffer, f"Search by {mode.capitalize()} - Animated Shot Chart", "tableau_animated_chart")
                offer_share_to_community(gif_buffer, f"Search by {mode.capitalize()} - Animated Shot Chart", "share_animated_chart")
            elif visualization == "Court Zone Map":
                fig = build_court_zone_map(shots, picked_name)
                st.pyplot(fig)
                add_to_tableau_dashboard(fig, f"Search by {mode.capitalize()} - Court Zone Map", "tableau_zone_map")
                offer_share_to_community(fig, f"Search by {mode.capitalize()} - Court Zone Map", "share_zone_map")
            else:
                st.info(f"{visualization} is being built next.")
        elif mode == "team" and team_query:
            with code_loading_animation("Downloading shot data"):
                shots = get_team_shots(TEAM_NAME_TO_RECORD[team_query]["id"], season)

            team_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR

            _team_id = TEAM_NAME_TO_RECORD[team_query]["id"]
            _team_short = TEAM_NAME_TO_RECORD[team_query].get("nickname") or team_query
            if visualization == "Shot Chart":
                fig = build_shot_chart(shots, team_color)
                show_chart(fig, _hover(hover.shot_chart_hotspots, fig.axes[0], shots,
                                       _game_lookup("team", _team_id, season), True), "team_shot_chart")
                add_to_tableau_dashboard(fig, "Search by Team - Shot Chart", "tableau_team_shot_chart")
                offer_share_to_community(fig, "Search by Team - Shot Chart", "share_team_shot_chart")
            elif visualization == "Heat Map":
                fig = build_heat_map(shots, team_color)
                show_chart(fig, _hover(hover.heat_map_hotspots, fig.axes[0], shots,
                                       get_zone_league_averages(season, team_id=_team_id), _team_short,
                                       color=team_color), "team_heat_map")
                add_to_tableau_dashboard(fig, "Search by Team - Heat Map", "tableau_team_heat_map")
                offer_share_to_community(fig, "Search by Team - Heat Map", "share_team_heat_map")
            elif visualization == "Hex Shot Chart":
                with code_loading_animation("Downloading league-wide comparison data"):
                    league_shots = get_league_shots(season)
                fig, hex_records = build_hex_shot_chart(shots, league_shots, team_color, return_hotspot_data=True)
                show_chart(fig, _hover(hover.hex_chart_hotspots, fig.axes[0], hex_records, _team_short, color=team_color),
                           "team_hex_chart")
                add_to_tableau_dashboard(fig, "Search by Team - Hex Shot Chart", "tableau_team_hex_chart")
                offer_share_to_community(fig, "Search by Team - Hex Shot Chart", "share_team_hex_chart")
            elif visualization == "Animated Shot Chart":
                with code_loading_animation("Building animation - this takes a little longer", code=build_animated_shot_chart):
                    gif_buffer = build_animated_shot_chart(shots, team_color)
                _show_animated_shot_chart(gif_buffer)
                add_to_tableau_dashboard(gif_buffer, "Search by Team - Animated Shot Chart", "tableau_team_animated_chart")
                offer_share_to_community(gif_buffer, "Search by Team - Animated Shot Chart", "share_team_animated_chart")
            elif visualization == "Court Zone Map":
                fig = build_court_zone_map(shots, f"{team_query}")
                st.pyplot(fig)
                add_to_tableau_dashboard(fig, "Search by Team - Court Zone Map", "tableau_team_zone_map")
                offer_share_to_community(fig, "Search by Team - Court Zone Map", "share_team_zone_map")
            else:
                st.info(f"{visualization} is being built next.")
        else:
            st.warning("Enter a valid player or team name first.")


# ---------------------------------------------------------------- Branch: Bar Chart
# ---------------------------------------------------------------- Branch: Line / Trend Chart
elif is_line_chart:

    # Its own player/team picker -- this branch is a sibling of the
    # court-graphs block above, not nested inside it, so
    # player_id/picked_name aren't set by that block's own selectbox
    # for this branch.
    if mode == "player":
        picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
        subject_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    else:
        picked_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.")
        subject_id = TEAM_NAME_TO_RECORD[picked_name]["id"] if picked_name else None

    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
    shared_per_mode = _shared_stat_mode_radio()

    chosen_stat = stat_menus.stat_select("Stat:", mode, key="line_stat")
    chosen_stat_label = chosen_stat[1]
    stat_field = chosen_stat[0]

    view_mode = st.radio("View:", ["Game-by-game", "Cumulative running total", "Momentum (hot/cold streaks)"], horizontal=True)
    rolling_window = 0
    filled = False
    if view_mode == "Game-by-game":
        rolling_window = st.number_input("Rolling average window (0 = off):", min_value=0, max_value=20, value=5)
    elif view_mode == "Cumulative running total":
        filled = st.checkbox("Fill area below the line", value=True)

    default_team = _default_color_team(mode, picked_name, season)
    color_input = color_input_with_dropdown(f"line_color_box_{mode}_{picked_name}_{season}", default_team)

    if season:
        run = persistent_run_button(True, key=visualization)
    else:
        run = False

    if run:
        stat_source = chosen_stat[2]
        if stat_source == "bradley_rating":
            st.warning(
                "Bradley Rating stats require the full multi-season rating model "
                "(bradley_ratings.py), which isn't ported to the dashboard yet - "
                "base and advanced stats work now."
            )
        elif not subject_id:
            st.warning(f"Pick a {'player' if mode == 'player' else 'team'} first.")
        else:
            with code_loading_animation("Downloading game log"):
                game_log = get_player_game_log(subject_id, season) if mode == "player" else get_team_game_log(subject_id, season)

            # PlayerGameLog/TeamGameLog's raw stat abbreviations (PTS,
            # AST, REB, ...) match this app's own base stat_field names
            # directly for counting stats, but advanced/bio fields (TS%,
            # USG%, etc.) aren't in a single game's box score at all --
            # confirmed via the endpoints' own documented columns, not
            # assumed.
            if stat_field not in game_log.columns:
                st.error(
                    f"{chosen_stat_label} isn't available on a per-game basis (advanced/bio stats are "
                    "season-level only) - try a base counting stat like Points, Rebounds, or Assists."
                )
            elif game_log.empty:
                st.warning(f"No games found for {picked_name} in {season}.")
            elif view_mode == "Momentum (hot/cold streaks)" and len(game_log) < 6:
                st.warning(f"Not enough games found for {picked_name} in {season} to show meaningful streaks.")
            else:
                game_log_sorted = game_log.iloc[::-1].reset_index(drop=True)  # API returns newest-first
                is_pct = stat_field.endswith("_PCT")
                line_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                if view_mode == "Momentum (hot/cold streaks)":
                    fig = build_momentum_chart(
                        game_log_sorted["GAME_DATE"].tolist(), game_log_sorted[stat_field].tolist(),
                        chosen_stat_label, picked_name, line_color,
                    )
                else:
                    fig = build_line_chart(
                        game_log_sorted["GAME_DATE"].tolist(), game_log_sorted[stat_field].tolist(),
                        stat_display_name=chosen_stat_label, subject_name=picked_name, season=season,
                        team_color=line_color, is_percentage=is_pct,
                        rolling_window=int(rolling_window) if view_mode == "Game-by-game" else None,
                        cumulative=(view_mode == "Cumulative running total"), filled=filled,
                    )
                _raw = pd.to_numeric(game_log_sorted[stat_field], errors="coerce").fillna(0).tolist()
                _plot = pd.Series(_raw).cumsum().tolist() if view_mode == "Cumulative running total" else _raw
                show_chart(fig, _hover(hover.season_trend_hotspots, fig.axes[0], list(range(len(_raw))),
                                       game_log_sorted["GAME_DATE"].tolist(), _plot, chosen_stat_label,
                                       _game_lookup(mode, subject_id, season), display_values=_raw, is_pct=is_pct),
                           "line_chart")
                add_to_tableau_dashboard(fig, f"Line Chart - {picked_name}", "tableau_line_chart")
                offer_share_to_community(fig, f"Line Chart - {picked_name}", "share_line_chart")


elif is_waterfall_chart:

    if mode == "player":
        picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    else:
        picked_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.")
    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
    shared_per_mode = _shared_stat_mode_radio()
    default_team = _default_color_team(mode, picked_name, season)
    color_input = color_input_with_dropdown(f"waterfall_color_box_{mode}_{picked_name}_{season}", default_team)

    run = persistent_run_button((season and picked_name), key=visualization)

    if run:
        with code_loading_animation("Downloading stats"):
            stats_df = get_player_stats(season, per_mode=shared_per_mode) if mode == "player" else get_team_stats(season, per_mode=shared_per_mode)

        name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
        subject_row = stats_df[stats_df[name_col] == picked_name]
        if subject_row.empty:
            st.error(f"No stats found for {picked_name} in {season}.")
        else:
            row = subject_row.iloc[0]
            ftm, fg3m, fgm = float(row["FTM"]), float(row["FG3M"]), float(row["FGM"])
            fg2m = fgm - fg3m
            wf_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
            fig = build_waterfall_chart(
                ["FT pts", "2PT pts", "3PT pts"], [ftm * 1, fg2m * 2, fg3m * 3],
                "Total PTS", wf_color, image_url=_subject_image_url(mode, picked_name),
            )
            _fta, _fga, _fg3a = (float(row.get(c, 0) or 0) for c in ("FTA", "FGA", "FG3A"))
            show_chart(fig, _hover(hover.waterfall_hotspots, fig.axes[0], ["Free throws", "2-pointers", "3-pointers"],
                                   [ftm * 1, fg2m * 2, fg3m * 3], [ftm, fg2m, fg3m], [_fta, _fga - _fg3a, _fg3a],
                                   per_mode=shared_per_mode),
                       "waterfall")
            add_to_tableau_dashboard(fig, f"Waterfall - {picked_name}", "tableau_waterfall")
            offer_share_to_community(fig, f"Waterfall - {picked_name}", "share_waterfall")


# ---------------------------------------------------------------- Branch: Combo Chart
elif is_combo_chart:

    if mode == "player":
        picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
        subject_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    else:
        picked_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.")
        subject_id = TEAM_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    shared_per_mode = _shared_stat_mode_radio()

    bar_stat = stat_menus.stat_select("Bar stat (a volume stat):", mode, key="combo_bar_stat")
    bar_label_choice = bar_stat[1]

    # The bar color starts on the player's / team's own color (their current team for a player - the chart covers a
    # whole career), and follows the subject when another one is picked. Before anyone is picked it shows White.
    _combo_team = _default_color_team(mode, picked_name, _stats_config.default_season()) if picked_name else None
    bar_color_key = f"combo_color_box_{mode}_{picked_name}"
    current_chart_color_default = _combo_team or "White"
    color_input = color_input_with_dropdown(bar_color_key, default_team=current_chart_color_default, show_text_color_toggle=False, label="Bar Color:")

    line_stat = stat_menus.stat_select("Line stat (a rate stat):", mode, key="combo_line_stat", value_field="FG_PCT")
    line_label_choice = line_stat[1]
    line_color_input = color_input_with_dropdown(f"combo_line_color_box_{mode}", default_team="Gold", show_text_color_toggle=False, label="Line Color:")

    # Chart Color comes last, after both color pickers, matching the
    # exact requested header order -- each color_input_with_dropdown()
    # call would otherwise render its own copy of this toggle
    # immediately after itself, attaching it to the first color picker
    # instead of standing alone at the end.
    combo_text_color_choice = st.radio(
        "Chart Color:", ["White", "Black"], key=f"combo_chart_color_{mode}", horizontal=True,
    )
    st.session_state["_global_chart_text_color"] = "black" if combo_text_color_choice == "Black" else "white"

    run = persistent_run_button(bool(picked_name), key=visualization, show_chart_color=False)

    if run:

        if bar_stat[2] == "bradley_rating" or line_stat[2] == "bradley_rating" or bar_stat[2] not in ("base", "advanced", "calculated") or line_stat[2] not in ("base", "advanced", "calculated"):
            st.warning(
                "Combo Chart's trend view currently supports base/advanced/calculated stats "
                "only (the season-by-season table it's built on doesn't include defense-tracking, "
                "hustle, or clutch endpoints)."
            )
        else:
            name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
            if mode == "player":
                with code_loading_animation("Looking up career seasons"):
                    seasons = get_player_career_seasons(subject_id)
                if not seasons:
                    st.error(f"Couldn't determine {picked_name}'s career span.")
            else:
                # Teams don't have a "career span" lookup the way
                # players do -- a franchise's own history (including
                # relocations and renames) is a substantially different,
                # messier problem than a single player's career, so
                # this uses a reasonable recent range instead of trying
                # to solve that.
                seasons = ALL_SEASONS[_stats_config.default_season_index(ALL_SEASONS):][:15]

            if not seasons:
                pass
            else:
                bar_values, line_values, valid_seasons = [], [], []
                with code_loading_animation(f"Downloading {len(seasons)} seasons of stats"):
                    for s in reversed(seasons):  # oldest first, for a left-to-right trend
                        s_df = get_player_stats(s, per_mode=shared_per_mode) if mode == "player" else get_team_stats(s, per_mode=shared_per_mode)
                        s_row = s_df[s_df[name_col] == picked_name]
                        if not s_row.empty and bar_stat[0] in s_row.columns and line_stat[0] in s_row.columns:
                            bar_values.append(float(s_row.iloc[0][bar_stat[0]]))
                            line_values.append(float(s_row.iloc[0][line_stat[0]]))
                            valid_seasons.append(s)

                if not valid_seasons:
                    st.error(f"No matching seasons of data found for {picked_name}.")
                else:
                    line_is_pct = line_stat[0].endswith("_PCT")
                    combo_color = resolve_color_input(color_input) or DEFAULT_COLOR
                    line_color = resolve_color_input(line_color_input) if line_color_input else "white"
                    fig = build_combo_chart(
                        valid_seasons, bar_values, line_values, bar_label_choice, line_label_choice,
                        combo_color, line_color=line_color, line_is_percentage=line_is_pct,
                    )
                    show_chart(fig, _hover(hover.combo_chart_hotspots, fig.axes[0], valid_seasons, bar_values,
                                           line_values, bar_label_choice, line_label_choice), "combo")
                    add_to_tableau_dashboard(fig, f"Combo Chart - {picked_name}", "tableau_combo")
                    offer_share_to_community(fig, f"Combo Chart - {picked_name}", "share_combo")


# ---------------------------------------------------------------- Branch: Tornado Chart
elif is_tornado_chart:

    if mode == "player":
        picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    else:
        picked_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.")
    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
    shared_per_mode = _shared_stat_mode_radio()

    tornado_stats = stat_menus.stat_multiselect("Stats to compare against league average:", mode, key="tornado_stats",
                                                default_n=5)
    tornado_ratings, tornado_tends = [], []
    if mode == "player":
        # the Bradley Ratings and Tendencies, compared with the average of every player who has them
        tornado_ratings = st.multiselect("Bradley ratings to compare against league average:",
                                         ratings_data.columns(ratings_data.RATINGS), key="tornado_ratings")
        tornado_tends = st.multiselect("Tendencies to compare against league average:",
                                       ratings_data.columns(ratings_data.TENDENCIES), key="tornado_tendencies")
    chosen_labels = [s_[1] for s_ in tornado_stats] + list(tornado_ratings) + list(tornado_tends)
    default_team = _default_color_team(mode, picked_name, season)
    color_input = color_input_with_dropdown(f"tornado_color_box_{mode}_{picked_name}_{season}", default_team)

    run = persistent_run_button((season and picked_name and chosen_labels), key=visualization)

    if run:
        chosen_stats = tornado_stats
        eligible = [s for s in chosen_stats if s[2] in ("base", "advanced", "calculated")]
        skipped = [s[1] for s in chosen_stats if s not in eligible]
        rating_picks = ([(ratings_data.RATINGS, c) for c in tornado_ratings] +
                        [(ratings_data.TENDENCIES, c) for c in tornado_tends])
        if rating_picks and not ratings_data.available(season):
            skipped += [c for _k, c in rating_picks]
            st.caption(f"Bradley Ratings and Tendencies are for {' and '.join(sorted(ratings_data.SEASONS))} only.")
            rating_picks = []
        if skipped:
            st.caption(f"Skipped (not available for direct league-average comparison): {', '.join(skipped)}")

        if not eligible and not rating_picks:
            st.warning("None of the selected stats can be compared this way - pick base/advanced/calculated stats, "
                       "Bradley ratings or tendencies.")
        else:
            labels, diffs = [], []
            subject_vals, league_avgs, pct_flags = [], [], []
            found_any = False
            if eligible:
                with code_loading_animation("Downloading stats"):
                    stats_df = get_player_stats(season, per_mode=shared_per_mode) if mode == "player" else get_team_stats(season, per_mode=shared_per_mode)
                name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
                subject_row = stats_df[stats_df[name_col].map(_fold_accents) == _fold_accents(picked_name)] \
                    if name_col in stats_df.columns else stats_df.iloc[0:0]
                if subject_row.empty:
                    st.warning(f"No stats found for {picked_name} in {season}.")
                else:
                    found_any = True
                    for field, label, _, _ in eligible:
                        if field in stats_df.columns:
                            league_avg = pd.to_numeric(stats_df[field], errors="coerce").mean()
                            subject_val = float(subject_row.iloc[0][field])
                            labels.append(label.split(" (")[0])
                            diffs.append(subject_val - league_avg)
                            subject_vals.append(subject_val)
                            league_avgs.append(float(league_avg))
                            pct_flags.append(field.endswith("_PCT"))
            if rating_picks:
                rec = PLAYER_NAME_TO_RECORD.get(picked_name, {})
                who = pd.DataFrame([{"PLAYER": rec.get("full_name", picked_name), "PLAYER_ID": rec.get("id")}])
                for kind in (ratings_data.RATINGS, ratings_data.TENDENCIES):
                    cols = [c for k, c in rating_picks if k == kind]
                    if not cols:
                        continue
                    hit = ratings_data.lookup(kind, who).get(0)
                    if hit is None:
                        st.warning(f"No {'Bradley Ratings' if kind == ratings_data.RATINGS else 'Tendencies'} for "
                                   f"{picked_name} yet.")
                        continue
                    league = ratings_data.league_frame(kind)
                    for c in cols:
                        val = pd.to_numeric(pd.Series([hit[c]]), errors="coerce").iloc[0]
                        if pd.isna(val):
                            continue
                        avg = float(pd.to_numeric(league[c], errors="coerce").mean())
                        found_any = True
                        labels.append(c)
                        diffs.append(float(val) - avg)
                        subject_vals.append(float(val))
                        league_avgs.append(avg)
                        pct_flags.append(False)
            if found_any and labels:
                tornado_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                fig = build_tornado_chart(labels, diffs, picked_name, tornado_color, is_percentage=False,
                                           image_url=_subject_image_url(mode, picked_name))
                show_chart(fig, _hover(hover.tornado_hotspots, fig.axes[0], labels, subject_vals, league_avgs,
                                       pct_flags), "tornado")
                add_to_tableau_dashboard(fig, f"Tornado - {picked_name}", "tableau_tornado")
                offer_share_to_community(fig, f"Tornado - {picked_name}", "share_tornado")
            elif not found_any:
                st.error(f"No data found for {picked_name} in {season}.")


# ---------------------------------------------------------------- Branch: Slope Chart
elif is_slope_chart:

    chosen_stat = stat_menus.stat_select("Stat:", mode, key="slope_stat")
    chosen_stat_label = chosen_stat[1]

    included_names = _include_picker(mode, f"slope_include_{mode}")
    # One slider for the seasons compared (like Search by Criteria's): from the earliest season there is data for --
    # or, with players picked, the earliest season any of them played -- to the latest season with a game played.
    _chrono = list(reversed(ALL_SEASONS))
    _first = _chrono[0]
    if mode == "player" and included_names:
        _starts = []
        for _n in included_names:
            _pid = PLAYER_NAME_TO_RECORD.get(_n, {}).get("id")
            _cs = get_player_career_seasons(_pid) if _pid else None
            if _cs:
                _starts.append(min(_cs))
        if _starts:
            _first = max(_chrono[0], min(_starts))
    _options = [x for x in _chrono if x >= _first]
    # the slider reaches the upcoming season too, but starts at the latest season that has had games
    _last = _stats_config.default_season() if _stats_config.default_season() in _options else _options[-1]
    _li = _options.index(_last)
    _default = (_options[0], _last) if (mode == "player" and included_names) else (_options[_li - 1] if _li > 0 else _options[0], _last)
    slope_range = st.select_slider(
        "Seasons:", options=_options, value=_default,
        key=f"slope_range_{mode}_{_options[0]}_{hashlib.md5('|'.join(sorted(included_names)).encode()).hexdigest()[:8]}",
    )
    before_season, after_season = slope_range
    shared_per_mode = _shared_stat_mode_radio()
    top_n = st.number_input("Or show top __ by the after-season value (used if no names entered):", min_value=1, max_value=30, value=8)
    slope_rank_ascending = rank_direction_control(chosen_stat[0], "slope")
    color_input = color_input_with_dropdown("slope_color_box")

    run = persistent_run_button((before_season and after_season and before_season < after_season), key=visualization,
                                not_ready="Pick two different seasons on the slider first.")

    if run:
        stat_field = chosen_stat[0]
        if chosen_stat[2] == "bradley_rating":
            st.warning("Bradley Rating stats aren't available for this comparison yet.")
        else:
            id_col = "PLAYER_ID" if mode == "player" else "TEAM_ID"
            name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
            in_range = [x for x in _chrono if before_season <= x <= after_season]
            # the seasons shown as bars in each pop-up: every season of the range, or 12 spread across a long one
            if len(in_range) > 12:
                _idx = sorted({round(k * (len(in_range) - 1) / 11) for k in range(12)})
                bar_seasons = [in_range[k] for k in _idx]
            else:
                bar_seasons = list(in_range)
            tables = {}

            def _table(season_):
                if season_ not in tables:
                    try:
                        df_ = fetch_stats_for_source(chosen_stat[2], season_, mode, per_mode=shared_per_mode)
                    except Exception:
                        df_ = pd.DataFrame()
                    if df_ is not None and not df_.empty and stat_field in df_.columns and id_col in df_.columns:
                        df_ = df_.copy()
                        df_[stat_field] = pd.to_numeric(df_[stat_field], errors="coerce")
                        df_ = df_.dropna(subset=[stat_field]).drop_duplicates(subset=[id_col])
                    else:
                        df_ = pd.DataFrame()
                    tables[season_] = df_
                return tables[season_]

            with code_loading_animation("Downloading every season in the range"):
                before_df, after_df = _table(before_season), _table(after_season)
                for x in bar_seasons:
                    _table(x)

            if before_df.empty or after_df.empty:
                st.error(f"Couldn't find {chosen_stat_label} in the returned stats.")
            else:
                # who: the players/teams picked, or the top N of the later season
                if included_names:
                    if mode == "player":
                        ids = [PLAYER_NAME_TO_RECORD[n]["id"] for n in included_names if n in PLAYER_NAME_TO_RECORD]
                    else:
                        ids = [TEAM_NAME_TO_RECORD[n]["id"] for n in included_names if n in TEAM_NAME_TO_RECORD]
                else:
                    pool = after_df
                    pool = pool.nsmallest(int(top_n), stat_field) if slope_rank_ascending else pool.nlargest(int(top_n), stat_field)
                    ids = pool[id_col].tolist()

                def _value(season_, ent_id):
                    df_ = _table(season_)
                    if df_.empty:
                        return None
                    hit = df_[df_[id_col] == ent_id]
                    return float(hit.iloc[0][stat_field]) if not hit.empty else None

                # each one's first and last season of the range he played in (a player who started later, or
                # stopped earlier, still gets his line)
                rows = []
                for ent_id in ids:
                    seasons_played = None
                    if mode == "player":
                        _cs = get_player_career_seasons(ent_id)
                        seasons_played = [x for x in (_cs or []) if before_season <= x <= after_season]
                    first_s = min(seasons_played) if seasons_played else before_season
                    last_s = max(seasons_played) if seasons_played else after_season
                    b_val, a_val = _value(first_s, ent_id), _value(last_s, ent_id)
                    if b_val is None or a_val is None or first_s == last_s:
                        continue
                    name = (next((n for n, r in PLAYER_NAME_TO_RECORD.items() if r["id"] == ent_id), None) if mode == "player"
                            else next((n for n, r in TEAM_NAME_TO_RECORD.items() if r["id"] == ent_id), None))
                    if not name:
                        _row = _table(last_s)
                        name = str(_row[_row[id_col] == ent_id].iloc[0][name_col]) if name_col in _row.columns else str(ent_id)
                    rows.append((ent_id, name, first_s, last_s, b_val, a_val))

                if not rows:
                    st.warning("No matching entries found across both seasons.")
                else:
                    # how big each change is next to everyone who played both seasons of the range
                    both = before_df[[id_col, stat_field]].merge(after_df[[id_col, stat_field]], on=id_col, suffixes=("_b", "_a"))
                    deltas = (both[f"{stat_field}_a"] - both[f"{stat_field}_b"]).tolist()
                    is_pct = stat_field.endswith("_PCT")
                    noun = "player" if mode == "player" else "team"

                    def _ordinal(k):
                        return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"

                    notes, bars = {}, {}
                    for i, (ent_id, name, first_s, last_s, b_val, a_val) in enumerate(rows):
                        d = a_val - b_val
                        d_txt = f"{d * 100:+.1f} pts" if is_pct else f"{d:+.1f}"
                        if first_s == before_season and last_s == after_season and deltas:
                            if d >= 0:
                                k = 1 + sum(1 for x in deltas if x > d)
                                notes[i] = f"{d_txt}, the league's {'biggest' if k == 1 else _ordinal(k) + '-biggest'} jump"
                            else:
                                k = 1 + sum(1 for x in deltas if x < d)
                                notes[i] = f"{d_txt}, the league's {'biggest' if k == 1 else _ordinal(k) + '-biggest'} drop"
                        else:
                            notes[i] = f"{d_txt} from {first_s} to {last_s}"
                        show = [x for x in bar_seasons if first_s <= x <= last_s]
                        for x in (first_s, last_s):
                            if x not in show:
                                show.append(x)
                        show.sort()
                        bars[i] = ([f"{x[2:4]}-{x[5:]}" for x in show], [_value(x, ent_id) for x in show],
                                   {f"{first_s[2:4]}-{first_s[5:]}", f"{last_s[2:4]}-{last_s[5:]}"})

                    slope_color = resolve_color_input(color_input) or DEFAULT_COLOR
                    names = [r[1] for r in rows]
                    image_urls = [get_player_headshot_url(r[0]) if mode == "player" else get_team_logo_url(r[0]) for r in rows]
                    fig, slope_pics = build_slope_chart(
                        names, [r[4] for r in rows], [r[5] for r in rows], before_season, after_season,
                        chosen_stat_label, slope_color, is_percentage=is_pct,
                        highlight_names=included_names, image_urls=image_urls, return_hotspot_data=True,
                    )
                    show_chart(fig, _hover(hover.slope_hotspots, fig.axes[0], slope_pics, names, [r[4] for r in rows],
                                           [r[5] for r in rows], chosen_stat_label, [r[2] for r in rows],
                                           [r[3] for r in rows], bars=bars, notes=notes, color=slope_color,
                                           is_pct=is_pct), "slope_chart")
                    add_to_tableau_dashboard(fig, "Slope Chart", "tableau_slope")
                    offer_share_to_community(fig, "Slope Chart", "share_slope")



# ---------------------------------------------------------------- Branch: Bar Chart
# ---------------------------------------------------------------- Branch: Radar Chart
elif is_radar_chart:

    names_list = ALL_PLAYER_NAMES if mode == "player" else ALL_TEAM_NAMES
    _noun = "player" if mode == "player" else "team"
    picked_name = st.selectbox(
        f"{'Player' if mode == 'player' else 'Team'}:", names_list, index=None, placeholder="Enter name.",
    )

    compare_toggle = st.checkbox(f"Compare against a second {_noun}")
    second_name = None
    if compare_toggle:
        second_name = st.selectbox(
            f"Second {_noun}:", names_list, index=None,
            placeholder="Enter name.", key="radar_p2",
        )

    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
    # the second player can be from any season of his own
    second_season = season
    if compare_toggle:
        _s2_options = _seasons_for_dropdown(mode, second_name) if second_name else ALL_SEASONS
        second_season = st.selectbox(f"Second {_noun} season:", _s2_options,
                                     index=_s2_options.index(season) if season in _s2_options else 0,
                                     key=f"radar_p2_season_{mode}_{second_name}")
    shared_per_mode = _shared_stat_mode_radio()
    default_team = _default_color_team(mode, picked_name, season)
    color_input = color_input_with_dropdown(f"radar_color_box_{mode}_{picked_name}_{season}", default_team)
    second_color_input = None
    if compare_toggle:
        second_color_input = color_input_with_dropdown(
            f"radar_color2_box_{mode}_{second_name}_{second_season}",
            _default_color_team(mode, second_name, second_season) if second_name else None,
            show_text_color_toggle=False, label=f"Second {_noun} color:")

    run = persistent_run_button((season and picked_name and (not compare_toggle or second_name)), key=visualization)

    if run:
        with code_loading_animation("Downloading stats"):
            _fetch = (lambda s_: get_player_stats(s_, per_mode=shared_per_mode)) if mode == "player" else \
                (lambda s_: get_team_stats(s_, per_mode=shared_per_mode))
            stats_df = _fetch(season)
            stats_df2 = _fetch(second_season) if (second_name and second_season != season) else stats_df

        # 5 categories, each backed by one representative stat already
        # present in get_player_stats()'s/get_team_stats()'s combined
        # base+advanced table -- Defense combines steals and blocks
        # into one simple sum rather than picking just one, since
        # neither alone captures "defense" well on its own.
        radar_categories = [
            ("Scoring", "PTS"), ("Playmaking", "AST"), ("Rebounding", "REB"),
            ("Defense", None), ("Efficiency", "TS_PCT"),
        ]
        name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
        required_cols = {"PTS", "AST", "REB", "STL", "BLK", "TS_PCT", name_col}
        if not required_cols.issubset(stats_df.columns) or not required_cols.issubset(stats_df2.columns):
            st.error("Couldn't find all the stats this profile needs in the returned data.")
        else:
            stats_df = stats_df.copy()
            stats_df["_DEFENSE_COMBO"] = stats_df["STL"] + stats_df["BLK"]
            stats_df2 = stats_df2.copy()
            stats_df2["_DEFENSE_COMBO"] = stats_df2["STL"] + stats_df2["BLK"]

            def subject_percentiles(name, df):
                row = df[df[name_col] == name]
                if row.empty:
                    return None
                percentiles = []
                for _, field in radar_categories:
                    col = "_DEFENSE_COMBO" if field is None else field
                    pct_rank = float((df[col] < row.iloc[0][col]).mean() * 100)
                    percentiles.append(pct_rank)
                return percentiles

            p1_percentiles = subject_percentiles(picked_name, stats_df)
            if p1_percentiles is None:
                st.error(f"No stats found for {picked_name} in {season}.")
            else:
                p2_percentiles = subject_percentiles(second_name, stats_df2) if second_name else None
                if second_name and p2_percentiles is None:
                    st.warning(f"No stats found for {second_name} in {second_season} - showing {picked_name} alone.")

                radar_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                radar_color2 = (resolve_color_input(second_color_input) if second_color_input else None) or "#B5B5B5"
                if str(radar_color2).lower() == str(radar_color).lower():      # (two players of the same team: grey)
                    radar_color2 = "#B5B5B5"
                _same_name = bool(second_name) and second_name == picked_name
                _label1 = picked_name + (f" ({season})" if p2_percentiles and (second_season != season) else "")
                _label2 = (second_name + (f" ({second_season})" if second_season != season or _same_name else "")
                           if second_name else None)
                fig = build_radar_chart(
                    [c for c, _ in radar_categories], p1_percentiles, _label1, radar_color,
                    second_percentiles=p2_percentiles, second_name=_label2, second_color=radar_color2,
                    image_url=_subject_image_url(mode, picked_name),
                    second_image_url=_subject_image_url(mode, second_name) if p2_percentiles else None,
                )
                _r = stats_df[stats_df[name_col] == picked_name].iloc[0]
                _r2 = stats_df2[stats_df2[name_col] == second_name].iloc[0] if p2_percentiles else None
                _radar_lines = [
                    [f"{_r['PTS']:.1f} PTS"], [f"{_r['AST']:.1f} AST"], [f"{_r['REB']:.1f} REB"],
                    [f"{_r['STL']:.1f} STL + {_r['BLK']:.1f} BLK"], [f"{_r['TS_PCT']:.1%} TS%"],
                ]
                _strips = []
                for _cat, _field in radar_categories:
                    _col = "_DEFENSE_COMBO" if _field is None else _field
                    _is_pct = _col == "TS_PCT"
                    _scale = 100.0 if _is_pct else 1.0
                    _vals = (pd.to_numeric(stats_df[_col], errors="coerce").dropna() * _scale).tolist()
                    _strips.append({"values": _vals, "subject": float(_r[_col]) * _scale,
                                    "second": float(_r2[_col]) * _scale if _r2 is not None else None,
                                    "fmt": "{:.1f}%" if _is_pct else "{:.1f}", "noun": _noun})
                show_chart(fig, _hover(hover.radar_hotspots, fig.axes[0], [c for c, _ in radar_categories],
                                       p1_percentiles, _radar_lines,
                                       shapes=[p1_percentiles] + ([p2_percentiles] if p2_percentiles else []),
                                       strips=_strips, color=radar_color, second_color=radar_color2), "radar")
                title = f"Radar - {picked_name}" + (f" vs {second_name}" if p2_percentiles else "")
                add_to_tableau_dashboard(fig, title, "tableau_radar")
                offer_share_to_community(fig, title, "share_radar")



# ---------------------------------------------------------------- Branch: Bar Chart
# ---------------------------------------------------------------- Branch: Bar Chart
# ---------------------------------------------------------------- Branch: Calendar Heat Map
elif is_calendar_heat_map:

    if mode == "player":
        picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
        subject_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    else:
        picked_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.")
        subject_id = TEAM_NAME_TO_RECORD[picked_name]["id"] if picked_name else None

    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
    shared_per_mode = _shared_stat_mode_radio()

    chosen_stat = stat_menus.stat_select("Stat:", mode, key="calendar_stat")
    chosen_stat_label = chosen_stat[1]
    default_team = _default_color_team(mode, picked_name, season)
    color_input = color_input_with_dropdown(f"calendar_color_box_{mode}_{picked_name}_{season}", default_team)

    run = persistent_run_button((season and picked_name), key=visualization)

    if run:
        stat_field = chosen_stat[0]
        if chosen_stat[2] == "bradley_rating":
            st.warning("Bradley Rating stats aren't available on a per-game basis.")
        elif not subject_id:
            st.warning(f"Pick a {'player' if mode == 'player' else 'team'} first.")
        else:
            with code_loading_animation("Downloading game log"):
                game_log = get_player_game_log(subject_id, season) if mode == "player" else get_team_game_log(subject_id, season)

            if stat_field not in game_log.columns:
                st.error(
                    f"{chosen_stat_label} isn't available on a per-game basis (advanced/bio stats are "
                    "season-level only) - try a base counting stat like Points, Rebounds, or Assists."
                )
            elif game_log.empty:
                st.warning(f"No games found for {picked_name} in {season}.")
            else:
                cal_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                fig, cal_cells = build_calendar_heat_map(
                    game_log["GAME_DATE"].tolist(), game_log[stat_field].tolist(),
                    chosen_stat_label, picked_name, cal_color,
                    image_url=_subject_image_url(mode, picked_name), return_hotspot_data=True,
                )
                _by_date = {pd.to_datetime(r["GAME_DATE"]).normalize(): r for _, r in game_log.iterrows()}
                _cal_rows = [_by_date.get(pd.Timestamp(d).normalize()) for _, _, d, _ in cal_cells]
                show_chart(fig, _hover(
                    hover.calendar_heat_map_hotspots, fig.axes[0], [(w, wd) for w, wd, _, _ in cal_cells],
                    [d for _, _, d, _ in cal_cells], [float(v) for _, _, _, v in cal_cells], chosen_stat_label,
                    _game_lookup(mode, subject_id, season), is_pct=stat_field.endswith("_PCT"),
                    pts=[float(r["PTS"]) if r is not None and "PTS" in r else None for r in _cal_rows],
                    reb=[float(r["REB"]) if r is not None and "REB" in r else None for r in _cal_rows],
                    ast=[float(r["AST"]) if r is not None and "AST" in r else None for r in _cal_rows],
                ), "calendar")
                add_to_tableau_dashboard(fig, f"Calendar - {picked_name}", "tableau_calendar")
                offer_share_to_community(fig, f"Calendar - {picked_name}", "share_calendar")


# ---------------------------------------------------------------- Branch: Court + Radar Hybrid
elif is_court_radar_hybrid:

    if mode == "player":
        picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
        subject_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    else:
        picked_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.")
        subject_id = TEAM_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
    default_team = _default_color_team(mode, picked_name, season)
    color_input = color_input_with_dropdown(f"hybrid_color_box_{mode}_{picked_name}_{season}", default_team)

    run = persistent_run_button((season and picked_name), key=visualization)

    if run:
        with code_loading_animation("Downloading shots"):
            shots = get_player_shots(subject_id, season) if mode == "player" else get_team_shots(subject_id, season)

        if shots.empty or "SHOT_ZONE_BASIC" not in shots.columns:
            st.error(f"No shot data found for {picked_name} in {season}.")
        else:
            total = len(shots)
            zone_counts = shots["SHOT_ZONE_BASIC"].value_counts()
            rim_rate = zone_counts.get("Restricted Area", 0) / total * 100
            midrange_rate = zone_counts.get("Mid-Range", 0) / total * 100
            three_zones = ["Left Corner 3", "Right Corner 3", "Above the Break 3"]
            three_rate = sum(zone_counts.get(z, 0) for z in three_zones) / total * 100
            fg_pct = float(shots["SHOT_MADE_FLAG"].mean()) * 100
            paint_rate = zone_counts.get("In The Paint (Non-RA)", 0) / total * 100

            labels = ["Rim Rate", "Paint Rate", "Mid-Range Rate", "3PT Rate", "Overall FG%"]
            values = [rim_rate, paint_rate, midrange_rate, three_rate, fg_pct]

            hybrid_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
            fig = build_court_radar_hybrid(shots, labels, values, picked_name, hybrid_color,
                                            image_url=_subject_image_url(mode, picked_name))
            st.pyplot(fig)
            title = f"Court + Radar Hybrid - {picked_name}"
            add_to_tableau_dashboard(fig, title, "tableau_hybrid")
            offer_share_to_community(fig, title, "share_hybrid")


# ---------------------------------------------------------------- Branch: Shot Flow (Sankey)
elif is_sankey_flow:

    if mode == "player":
        picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
        subject_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    else:
        picked_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.")
        subject_id = TEAM_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
    shared_per_mode = _shared_stat_mode_radio()
    default_team = _default_color_team(mode, picked_name, season)
    color_input = color_input_with_dropdown(f"sankey_color_box_{mode}_{picked_name}_{season}", default_team)

    run = persistent_run_button((season and picked_name), key=visualization)

    if run:
        with code_loading_animation("Downloading shots"):
            shots = get_player_shots(subject_id, season) if mode == "player" else get_team_shots(subject_id, season)

        if shots.empty or "SHOT_ZONE_BASIC" not in shots.columns:
            st.error(f"No shot data found for {picked_name} in {season}.")
        else:
            zone_order = shots["SHOT_ZONE_BASIC"].value_counts().index.tolist()
            stage_labels = [zone_order, ["Made", "Missed"]]
            flows = []
            for zone, group in shots.groupby("SHOT_ZONE_BASIC"):
                made = int(group["SHOT_MADE_FLAG"].sum())
                missed = len(group) - made
                if made > 0:
                    flows.append((0, zone, "Made", made))
                if missed > 0:
                    flows.append((0, zone, "Missed", missed))

            sankey_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
            fig = build_sankey_flow(stage_labels, flows, sankey_color, image_url=_subject_image_url(mode, picked_name))
            show_chart(fig, _hover(hover.sankey_hotspots, fig.axes[0], stage_labels, flows), "sankey")
            title = f"Shot Flow - {picked_name}"
            add_to_tableau_dashboard(fig, title, "tableau_sankey")
            offer_share_to_community(fig, title, "share_sankey")


# ---------------------------------------------------------------- Branch: Impact Clock
elif is_impact_clock:

    if mode == "player":
        picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
        subject_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    else:
        picked_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.")
        subject_id = TEAM_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    player_id = subject_id if mode == "player" else None
    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
    shared_per_mode = _shared_stat_mode_radio()
    default_team = _default_color_team(mode, picked_name, season)
    color_input = color_input_with_dropdown(f"impactclock_color_box_{mode}_{picked_name}_{season}", default_team)

    run = persistent_run_button((season and picked_name), key=visualization)

    if run:
        with code_loading_animation("Downloading quarter-by-quarter stats"):
            by_quarter = (get_player_stats_by_quarter(subject_id, season) if mode == "player"
                          else get_team_stats_by_quarter(subject_id, season))

        if by_quarter.empty or len(by_quarter) < 4:
            st.error(
                f"Couldn't load complete quarter-by-quarter data for {picked_name} in {season} "
                "- this needs all 4 quarters' splits to be available."
            )
        elif not {"PTS", "FG_PCT", "PLUS_MINUS"}.issubset(by_quarter.columns):
            st.error("The quarter-split data returned is missing one of the stats this chart needs.")
        else:
            by_quarter_sorted = by_quarter.sort_values("QUARTER")
            quarter_stats = [
                {"PTS": float(row["PTS"]), "FG_PCT": float(row["FG_PCT"]), "PLUS_MINUS": float(row["PLUS_MINUS"])}
                for _, row in by_quarter_sorted.iterrows()
            ]

            clock_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
            fig = build_impact_clock(quarter_stats, picked_name, clock_color)
            # Each quarter's pop-up ends with a small season-trend line: points in that quarter, game by game.
            with code_loading_animation("Downloading game-by-game quarter scoring"):
                try:
                    quarter_logs = get_quarter_game_logs(mode, subject_id, season)
                except Exception:
                    quarter_logs = {}
            show_chart(fig, _hover(hover.clutch_clock_hotspots, fig.axes[0], quarter_stats, quarter_logs,
                                   color=clock_color), f"impact_clock_{mode}")
            title = f"Impact Clock - {picked_name}"
            add_to_tableau_dashboard(fig, title, f"tableau_impact_clock_{mode}")
            offer_share_to_community(fig, title, f"share_impact_clock_{mode}")


# ---------------------------------------------------------------- Branch: Passing Connections
elif is_court_connection and mode == "team":
    # A team's passing web: the team, then which of its players is the passer -- and, if wanted, one receiver only
    pass_team = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.", key="team_pass_team")
    season = st.selectbox("Season:", ALL_SEASONS, index=0, key="team_pass_season")
    pass_roster = {}
    if pass_team and season:
        with code_loading_animation("Downloading roster"):
            try:
                _r = get_team_roster(TEAM_NAME_TO_RECORD[pass_team]["id"], season)
                pass_roster = {str(n): int(i) for n, i in zip(_r["PLAYER"], _r["PLAYER_ID"])}
            except Exception as e:  # noqa: BLE001
                st.error(f"Couldn't load the {season} roster: {friendly_error(e)}")
    _roster_names = sorted(pass_roster)
    passer = st.selectbox("Passer:", _roster_names, index=None,
                          placeholder="Choose the passer." if _roster_names else "Pick a team first.",
                          disabled=not _roster_names, key=f"team_pass_passer_{pass_team}_{season}")
    receiver = st.selectbox("Receiver (optional):", [n for n in _roster_names if n != passer], index=None,
                            placeholder="Every teammate he passes to", disabled=not _roster_names,
                            key=f"team_pass_receiver_{pass_team}_{season}")
    top_n = st.number_input("Show top __ passing connections:", min_value=3, max_value=10, value=5, disabled=bool(receiver),
                            key="team_pass_top_n")
    passing_rank_ascending = rank_direction_control("PASS", "team_passing")
    color_input = color_input_with_dropdown(f"team_connection_color_box_{pass_team}_{season}", pass_team)
    run = persistent_run_button(bool(season and pass_team and passer), key=visualization + "_team")
    if run and passer:
        render_passing_web(passer, pass_roster[passer], season, top_n=top_n, rank_ascending=passing_rank_ascending,
                           color_input=color_input, key="team_passing_web", only_receiver=receiver)


elif is_court_connection:

    picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    player_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
    top_n = st.number_input("Show top __ passing connections:", min_value=3, max_value=10, value=5)
    passing_rank_ascending = rank_direction_control("PASS", "passing")
    default_team = _default_color_team("player", picked_name, season)
    color_input = color_input_with_dropdown(f"connection_color_box_{picked_name}_{season}", default_team)

    run = persistent_run_button((season and picked_name), key=visualization)

    if run:
        render_passing_web(picked_name, player_id, season, top_n=top_n, rank_ascending=passing_rank_ascending,
                           color_input=color_input, key="passing_web")


elif is_bar_chart:

    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    shared_per_mode = _shared_stat_mode_radio()

    chosen_stat = measurement_picker("bar_stat", mode)
    chosen_stat_label = chosen_stat[1]
    stat_field = chosen_stat[0]

    if stat_field in BRADLEY_RATING_DESCRIPTIONS:
        st.caption(BRADLEY_RATING_DESCRIPTIONS[stat_field])

    top_n = st.number_input("Display the top __:", min_value=1, max_value=499, value=10)
    rank_ascending = rank_direction_control(stat_field, "bar_chart")

    included_names = _include_picker(mode, f"bar_include_{mode}")

    display_as = st.radio("Display As:", ["Vertical Bar", "Horizontal Bar", "Dot Plot"], horizontal=True)

    color_input = color_input_with_dropdown("bar_color_box")

    if season:
        run = persistent_run_button(True, key=visualization)
    else:
        run = False

    if run:
        stat_source = chosen_stat[2]

        if stat_source == "bradley_rating":
            st.warning(
                "Bradley Rating stats require the full multi-season rating model "
                "(bradley_ratings.py), which isn't ported to the dashboard yet - "
                "base and advanced stats work now."
            )
        elif not season:
            st.warning("Enter a season first.")
        elif not _ratings_season_ok([chosen_stat], season):
            pass
        else:
            with code_loading_animation("Downloading stats"):
                stats_df = fetch_stats_for_source(stat_source, season, mode, per_mode=shared_per_mode)

            if stat_field not in stats_df.columns:
                st.error(f"Couldn't find {stat_field} in the returned stats.")
            else:
                # pandas' nlargest() raises TypeError outright on a
                # column with dtype "object", which real stat columns
                # often end up as when some rows are None (e.g. a
                # shooting percentage for a player/team with zero
                # attempts that season) -- coercing to numeric first
                # (turning anything unparseable into NaN, then
                # dropping those rows) guarantees a clean float column
                # to rank, rather than assuming the API always returns
                # one.
                stats_df = stats_df.copy()
                stats_df[stat_field] = pd.to_numeric(stats_df[stat_field], errors="coerce")
                stats_df = stats_df.dropna(subset=[stat_field])

                name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
                id_col = "PLAYER_ID" if mode == "player" else "TEAM_ID"
                top_rows = stats_df.nsmallest(int(top_n), stat_field) if rank_ascending else stats_df.nlargest(int(top_n), stat_field)
                # the players/teams asked for are always in the chart -- added after the top N when they aren't in it
                extra_rows = _rows_named(stats_df, included_names, name_col)
                extra_rows = extra_rows[~extra_rows.index.isin(top_rows.index)]
                leaderboard = pd.concat([top_rows, extra_rows])[[name_col, id_col, stat_field]]
                leaderboard.columns = ["name", "player_id", "value"]
                if mode == "player":
                    leaderboard["image_url"] = [_player_image_url(p, n) for p, n in zip(leaderboard["player_id"], leaderboard["name"])]
                else:
                    leaderboard["image_url"] = leaderboard["player_id"].apply(get_team_logo_url)

                _inc_folded = {_fold_accents(n).lower() for n in included_names}
                leaderboard["is_included"] = (leaderboard["name"].map(lambda n: _fold_accents(str(n)).lower() in _inc_folded)
                                              if included_names else True)
                included_names = leaderboard.loc[leaderboard["is_included"] == True, "name"].tolist() if included_names else []

                is_pct = stat_field.endswith("_PCT")
                bar_team_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                # salaries are the season they're paid in (from July 1, the new league year's)
                shown_season = _salary_season_for(season) if stat_source == "salary" else season

                if display_as == "Dot Plot":
                    fig = build_dot_plot(
                        leaderboard, stat_display_name=chosen_stat_label, season=shown_season,
                        top_n=int(top_n), team_color=bar_team_color, included_names=included_names,
                        stat_source=stat_source, is_percentage=is_pct, rank_ascending=rank_ascending,
                        decimals=(None if stat_source in ("salary", "bio", "bradley_rating")
                                  else 0 if ratings_data.is_source(stat_source)
                                  else 0 if shared_per_mode == "Totals" and stat_source != "calculated" else 1),
                    )
                else:
                    fig = build_bar_chart(
                        leaderboard, stat_display_name=chosen_stat_label, season=shown_season,
                        top_n=int(top_n), team_color=bar_team_color, included_names=included_names,
                        orientation="vertical" if display_as == "Vertical Bar" else "horizontal",
                        stat_source=stat_source, is_percentage=is_pct, rank_ascending=rank_ascending,
                        # per game / per 36 numbers with one decimal (34.3, not 34); season totals, ratings and
                        # tendencies whole numbers
                        decimals=(None if stat_source in ("salary", "bio", "bradley_rating")
                                  else 0 if ratings_data.is_source(stat_source)
                                  else 0 if shared_per_mode == "Totals" and stat_source != "calculated" else 1),
                        per_mode=shared_per_mode,
                    )
                if display_as == "Dot Plot":
                    st.pyplot(fig)
                else:
                    _orient = "vertical" if display_as == "Vertical Bar" else "horizontal"
                    _drawn = leaderboard.sort_values("value", ascending=(_orient == "horizontal")).reset_index(drop=True)
                    show_chart(fig, _hover(hover.bar_chart_hotspots, fig.axes[0], _drawn["name"].tolist(),
                                           _drawn["value"].tolist(), chosen_stat_label, orientation=_orient,
                                           rank_ascending=rank_ascending, is_pct=is_pct), "bar_chart")
                add_to_tableau_dashboard(fig, "Bar Chart", "tableau_bar_chart")
                offer_share_to_community(fig, "Bar Chart", "share_bar_chart")


# ---------------------------------------------------------------- Branch: Histogram
elif is_histogram:

    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    shared_per_mode = _shared_stat_mode_radio()

    chosen_stat = measurement_picker("hist_stat", mode)
    chosen_stat_label = chosen_stat[1]
    stat_field = chosen_stat[0]
    display_as = st.radio("Display As:", ["Histogram", "Density Plot"], horizontal=True)
    bins = st.number_input("Number of bars:", min_value=5, max_value=60, value=7, disabled=(display_as == "Density Plot"))
    color_input = color_input_with_dropdown("hist_color_box")

    if season:
        run = persistent_run_button(True, key=visualization)
    else:
        run = False

    if run:
        stat_source = chosen_stat[2]
        if stat_source == "bradley_rating":
            st.warning(
                "Bradley Rating stats require the full multi-season rating model "
                "(bradley_ratings.py), which isn't ported to the dashboard yet - "
                "base and advanced stats work now."
            )
        elif not _ratings_season_ok([chosen_stat], season):
            pass
        else:
            with code_loading_animation("Downloading stats"):
                stats_df = fetch_stats_for_source(stat_source, season, mode, per_mode=shared_per_mode)

            if stat_field not in stats_df.columns:
                st.error(f"Couldn't find {stat_field} in the returned stats.")
            elif display_as == "Density Plot" and pd.to_numeric(stats_df[stat_field], errors="coerce").dropna().shape[0] < 5:
                st.warning("Not enough players with this stat to estimate a density curve.")
            else:
                is_pct = stat_field.endswith("_PCT")
                hist_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                values = pd.to_numeric(stats_df[stat_field], errors="coerce").dropna().tolist()
                shown_season = _salary_season_for(season) if stat_source == "salary" else season
                if display_as == "Density Plot":
                    fig = build_density_plot(
                        values, stat_display_name=chosen_stat_label,
                        season=shown_season, team_color=hist_color, is_percentage=is_pct,
                    )
                else:
                    fig = build_histogram(
                        values, stat_display_name=chosen_stat_label,
                        season=shown_season, team_color=hist_color, is_percentage=is_pct, bins=int(bins),
                    )
                if stat_source == "salary":
                    visuals.money_axis(fig.axes[0], "x", values)
                if display_as == "Density Plot":
                    st.pyplot(fig)
                else:
                    # the pop-up: the pictures of who is in each bar (the best of them first, up to 10, kept small so
                    # the chart's page stays light enough to load)
                    _name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
                    _id_col = "PLAYER_ID" if mode == "player" else "TEAM_ID"
                    _hd = stats_df[[c for c in (_name_col, _id_col, stat_field) if c in stats_df.columns]].copy()
                    _hd[stat_field] = pd.to_numeric(_hd[stat_field], errors="coerce")
                    _hd = _hd.dropna(subset=[stat_field])
                    _patches = list(fig.axes[0].patches)
                    _bars = []
                    for _k, _p in enumerate(_patches):
                        _lo, _hi = _p.get_x(), _p.get_x() + _p.get_width()
                        _in = _hd[(_hd[stat_field] >= _lo) & ((_hd[stat_field] < _hi) if _k < len(_patches) - 1 else (_hd[stat_field] <= _hi))]
                        _in = _in.sort_values(stat_field, ascending=False)
                        _bars.append((_lo, _hi, [(str(r[_name_col]), r.get(_id_col)) for _, r in _in.iterrows()]))
                    _urls = {}
                    if _id_col in _hd.columns:
                        _want = [pid for _lo, _hi, _ppl in _bars for _nm, pid in _ppl[:10] if pd.notna(pid)]
                        _src = {int(pid): (get_player_headshot_url(int(pid)) if mode == "player" else get_team_logo_url(int(pid)))
                                for pid in _want}
                        visuals.prefetch_small_images(list(_src.values()), max_px=48)
                        _urls = {pid: visuals.image_tiny_data_uri(u, max_px=48) for pid, u in _src.items()}
                    _bars = [(_lo, _hi, [(nm, _urls.get(int(pid)) if pd.notna(pid) else None) for nm, pid in _ppl])
                             for _lo, _hi, _ppl in _bars]
                    show_chart(fig, _hover(hover.histogram_hotspots, fig.axes[0], _patches, _bars, chosen_stat_label,
                                           is_pct=is_pct, noun="players" if mode == "player" else "teams"), "histogram")
                add_to_tableau_dashboard(fig, "Histogram", "tableau_histogram")
                offer_share_to_community(fig, "Histogram", "share_histogram")


# ---------------------------------------------------------------- Branch: Cumulative Distribution Plot
elif is_cumdist_plot:

    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    shared_per_mode = _shared_stat_mode_radio()

    chosen_stat = stat_menus.stat_select("Stat:", mode, key="cumdist_stat", include_salary=True)
    chosen_stat_label = chosen_stat[1]
    stat_field = chosen_stat[0]
    highlight_input = st.selectbox(
        f"Highlight a specific {'player' if mode == 'player' else 'team'} on the curve (optional):",
        ALL_PLAYER_NAMES if mode == "player" else ALL_TEAM_NAMES, index=None,
        placeholder="",
    )
    color_input = color_input_with_dropdown("cumdist_color_box")

    if season:
        run = persistent_run_button(True, key=visualization)
    else:
        run = False

    if run:
        stat_source = chosen_stat[2]
        if stat_source == "bradley_rating":
            st.warning(
                "Bradley Rating stats require the full multi-season rating model "
                "(bradley_ratings.py), which isn't ported to the dashboard yet - "
                "base and advanced stats work now."
            )
        else:
            with code_loading_animation("Downloading stats"):
                stats_df = fetch_stats_for_source(stat_source, season, mode, per_mode=shared_per_mode)

            if stat_field not in stats_df.columns:
                st.error(f"Couldn't find {stat_field} in the returned stats.")
            elif stats_df[stat_field].dropna().shape[0] < 5:
                st.warning("Not enough players with this stat to plot a distribution.")
            else:
                is_pct = stat_field.endswith("_PCT")
                cumdist_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR

                highlight_value = None
                if highlight_input:
                    name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
                    match = stats_df[stats_df[name_col] == highlight_input] if name_col in stats_df.columns else None
                    if match is not None and not match.empty and pd.notna(match.iloc[0][stat_field]):
                        highlight_value = float(match.iloc[0][stat_field])
                    else:
                        st.warning(f"No {stat_field} value found for {highlight_input} this season - showing the curve without a highlight.")

                _vals = pd.to_numeric(stats_df[stat_field], errors="coerce").dropna().tolist()
                fig = build_cumulative_distribution_plot(
                    _vals, stat_display_name=chosen_stat_label,
                    season=_salary_season_for(season) if stat_source == "salary" else season,
                    team_color=cumdist_color, is_percentage=is_pct,
                    highlight_value=highlight_value, highlight_name=highlight_input,
                )
                if stat_source == "salary":
                    visuals.money_axis(fig.axes[0], "x", _vals)
                # the pop-up: whoever sits at that spot of the curve, his number and percentile
                _name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
                _cd = stats_df[[_name_col, stat_field]].copy() if _name_col in stats_df.columns else None
                _pts = []
                if _cd is not None:
                    _cd[stat_field] = pd.to_numeric(_cd[stat_field], errors="coerce")
                    _cd = _cd.dropna(subset=[stat_field]).sort_values(stat_field, kind="mergesort").reset_index(drop=True)
                    _n = len(_cd)
                    _pts = [(float(v), (k + 1) / _n * 100, str(nm)) for k, (nm, v) in enumerate(zip(_cd[_name_col], _cd[stat_field]))]
                show_chart(fig, _hover(hover.cumdist_hotspots, fig.axes[0], _pts, chosen_stat_label, is_pct=is_pct,
                                       noun="player" if mode == "player" else "team", color=cumdist_color), "cumdist")
                add_to_tableau_dashboard(fig, "Cumulative Distribution Plot", "tableau_cumdist")
                offer_share_to_community(fig, "Cumulative Distribution Plot", "share_cumdist")


# ---------------------------------------------------------------- Branch: Scatter Plot
# ---------------------------------------------------------------- Branch: Box Plot
elif is_box_plot:

    chosen_stat = stat_menus.stat_select("Stat:", mode, key="box_stat", include_salary=True)
    chosen_stat_label = chosen_stat[1]
    stat_field = chosen_stat[0]

    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    team_filter_input = st.text_input(
        "Limit to these teams (comma-separated abbreviations, e.g. BOS, LAL - optional, defaults to all 30):"
    )
    plot_style = st.radio("Style:", ["Box", "Violin"], horizontal=True)
    min_games = st.number_input("Minimum games played (filters out small samples):", min_value=0, max_value=82, value=10)
    color_input = color_input_with_dropdown("box_color_box")

    if season:
        run = persistent_run_button(True, key=visualization)
    else:
        run = False

    if run:
        stat_source = chosen_stat[2]
        if stat_source == "bradley_rating":
            st.warning(
                "Bradley Rating stats require the full multi-season rating model "
                "(bradley_ratings.py), which isn't ported to the dashboard yet - "
                "base and advanced stats work now."
            )
        else:
            with code_loading_animation("Downloading stats"):
                # Deliberately always player-level data here (not
                # gated by mode the way the other axis-graph branches
                # now are) -- Box Plot's whole purpose is showing the
                # spread of a stat across each team's own players, which
                # needs multiple player rows per team to group; team-
                # level data (get_team_stats(), one row per team) would
                # leave nothing to form a spread from at all.
                stats_df = fetch_stats_for_source(stat_source, season, "player")

            if stat_field not in stats_df.columns or "TEAM_ABBREVIATION" not in stats_df.columns:
                st.error(f"Couldn't find {stat_field} in the returned stats.")
            else:
                filtered = stats_df[stats_df["GP"] >= min_games] if "GP" in stats_df.columns else stats_df
                if team_filter_input:
                    wanted_teams = [t.strip().upper() for t in team_filter_input.split(",") if t.strip()]
                    filtered = filtered[filtered["TEAM_ABBREVIATION"].isin(wanted_teams)]
                filtered = filtered.copy()
                filtered[stat_field] = pd.to_numeric(filtered[stat_field], errors="coerce")

                groups = {
                    team: sub[stat_field].dropna().tolist()
                    for team, sub in filtered.groupby("TEAM_ABBREVIATION")
                    if len(sub[stat_field].dropna()) >= 2
                }
                group_names = {
                    team: sub.dropna(subset=[stat_field])["PLAYER_NAME"].tolist() if "PLAYER_NAME" in sub.columns else None
                    for team, sub in filtered.groupby("TEAM_ABBREVIATION")
                    if len(sub[stat_field].dropna()) >= 2
                }
                if not groups:
                    st.warning("Not enough players per team to plot a spread - try lowering the minimum games played.")
                else:
                    is_pct = stat_field.endswith("_PCT")
                    box_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                    fig = build_box_plot(
                        groups, stat_display_name=chosen_stat_label,
                        season=_salary_season_for(season) if stat_source == "salary" else season,
                        team_color=box_color, is_percentage=is_pct, violin=(plot_style == "Violin"),
                    )
                    if stat_source == "salary":
                        visuals.money_axis(fig.axes[0], "y", [v for g in groups.values() for v in g])
                    _labels = list(groups.keys())
                    _names = [group_names.get(t) or [None] * len(groups[t]) for t in _labels]
                    show_chart(fig, _hover(hover.box_plot_hotspots, fig.axes[0], _labels, [groups[t] for t in _labels],
                                           names_data=_names), "box_plot")
                    add_to_tableau_dashboard(fig, "Box Plot", "tableau_box_plot")
                    offer_share_to_community(fig, "Box Plot", "share_box_plot")


# ---------------------------------------------------------------- Branch: Scatter Plot
elif is_scatter_plot:

    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    shared_per_mode = _shared_stat_mode_radio()

    if mode == "player":
        y_stat = measurement_picker("scatter_y_stat", mode, title="Measurement (Y axis):")
        x_stat = measurement_picker("scatter_x_stat", mode, title="Measurement (X axis):", value_field="FG_PCT")
    else:
        y_stat = stat_menus.stat_select("Stat (Y axis):", mode, key="scatter_y_stat", include_salary=True)
        x_stat = stat_menus.stat_select("Stat (X axis):", mode, key="scatter_x_stat", include_salary=True, value_field="FG_PCT")
    y_label, y_field = y_stat[1], y_stat[0]
    x_label = x_stat[1]

    top_n = st.number_input("Display the top __ (ranked by Y axis):", min_value=1, max_value=499, value=10)
    rank_ascending = rank_direction_control(y_field, "scatter")

    included_names = _include_picker(mode, f"scatter_include_{mode}")

    # No color prompt -- Scatter Plot shows only player headshots or
    # team logos, matching bradley_analytics.py's is_scatter_plot
    # branch exactly.

    run = persistent_run_button(season, key=visualization)

    if run:

        if y_stat[2] == "bradley_rating" or x_stat[2] == "bradley_rating":
            st.warning(
                "Bradley Rating stats require the full multi-season rating model "
                "(bradley_ratings.py), which isn't ported to the dashboard yet - "
                "base and advanced stats work now."
            )
        elif not season:
            st.warning("Enter a season first.")
        elif not _ratings_season_ok([y_stat, x_stat], season):
            pass
        else:
            with code_loading_animation("Downloading stats"):
                y_source, x_source = y_stat[2], x_stat[2]
                id_col = "PLAYER_ID" if mode == "player" else "TEAM_ID"
                if y_source == x_source:
                    # Common case: both axes pull from the same source
                    # (e.g. both "base"/"advanced"/etc, which all live in
                    # the one combined get_player_stats() table anyway) --
                    # a single fetch already has both columns.
                    stats_df = fetch_stats_for_source(y_source, season, mode, per_mode=shared_per_mode)
                else:
                    # X and Y come from genuinely different tables (e.g.
                    # Clutch PTS vs Usage%) -- fetch each separately and
                    # merge on PLAYER_ID, since nlargest()[[...]] below
                    # needs both stat columns present in one dataframe.
                    # x_field and y_field can share the same literal
                    # column name across two different sources (e.g.
                    # Clutch's "PTS" vs base "PTS") -- any pre-existing
                    # same-named column is dropped from y_df first, so
                    # the merged frame's "PTS" is unambiguously the one
                    # actually selected for the X axis, not silently left
                    # pointing at Y's version of a same-named stat.
                    y_df = fetch_stats_for_source(y_source, season, mode, per_mode=shared_per_mode)
                    x_df = fetch_stats_for_source(x_source, season, mode, per_mode=shared_per_mode)
                    if id_col in y_df.columns and id_col in x_df.columns and x_stat[0] in x_df.columns:
                        y_df_deduped = y_df.drop(columns=[x_stat[0]], errors="ignore")
                        x_slice = x_df[[id_col, x_stat[0]]]
                        stats_df = y_df_deduped.merge(x_slice, on=id_col, how="inner")
                    else:
                        stats_df = pd.DataFrame()  # missing join key -- caught by the columns check below

            y_field, x_field = y_stat[0], x_stat[0]

            if y_field not in stats_df.columns or x_field not in stats_df.columns:
                st.error("Couldn't find one of the selected stats in the returned data.")
            else:
                stats_df = stats_df.copy()
                stats_df[y_field] = pd.to_numeric(stats_df[y_field], errors="coerce")
                stats_df[x_field] = pd.to_numeric(stats_df[x_field], errors="coerce")
                stats_df = stats_df.dropna(subset=[y_field, x_field])

                name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
                top_rows = stats_df.nsmallest(int(top_n), y_field) if rank_ascending else stats_df.nlargest(int(top_n), y_field)
                # the players/teams asked for are always plotted -- added when they aren't in the top N
                extra_rows = _rows_named(stats_df, included_names, name_col)
                extra_rows = extra_rows[~extra_rows.index.isin(top_rows.index)]
                leaderboard = pd.concat([top_rows, extra_rows])[[name_col, id_col, y_field, x_field]]
                leaderboard.columns = ["name", "player_id", "y_value", "x_value"]
                if mode == "player":
                    leaderboard["image_url"] = [_player_image_url(p, n) for p, n in zip(leaderboard["player_id"], leaderboard["name"])]
                else:
                    leaderboard["image_url"] = leaderboard["player_id"].apply(get_team_logo_url)

                _inc_folded = {_fold_accents(n).lower() for n in included_names}
                leaderboard["is_included"] = leaderboard["name"].map(lambda n: _fold_accents(str(n)).lower() in _inc_folded)
                # "Show pictures for": which players/teams are drawn as their picture (the rest as dots)
                pics = pickers.picture_picker(leaderboard["name"].tolist(), key=f"scatter_pics_{mode}_{season}",
                                              noun="players" if mode == "player" else "teams")
                leaderboard["show_image"] = leaderboard["name"].astype(str).isin(pics)

                fig, scatter_records = build_scatter_plot(leaderboard, stat_label_y=y_label, stat_label_x=x_label,
                                                          return_hotspot_data=True)
                if y_stat[2] == "salary":
                    visuals.money_axis(fig.axes[0], "y", leaderboard["y_value"].tolist())
                if x_stat[2] == "salary":
                    visuals.money_axis(fig.axes[0], "x", leaderboard["x_value"].tolist())
                if "salary" in (y_stat[2], x_stat[2]) and _salary_season_for(season) != season:
                    st.caption(f"Salaries are {_salary_season_for(season)}'s (the current league year).")
                # The same interactive effects as Search by Criteria's scatter: diagonal bands (best corner = high
                # in both stats, or low for a lower-is-better one), hovered player/band grows, nobody ever darkens.
                show_chart(fig, _hover(hover.criteria_scatter_hotspots, fig.axes[0], scatter_records, x_label, y_label,
                                       noun="player" if mode == "player" else "team",
                                       x_higher_better=x_field not in LOWER_IS_BETTER_STATS,
                                       y_higher_better=not rank_ascending),
                           "scatter_plot")
                add_to_tableau_dashboard(fig, "Scatter Plot", "tableau_scatter_plot")
                offer_share_to_community(fig, "Scatter Plot", "share_scatter_plot")

