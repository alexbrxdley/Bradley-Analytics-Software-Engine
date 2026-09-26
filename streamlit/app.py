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
import random
import unicodedata
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
                       get_league_lineup_combos)
from nba_api.stats.static import players, teams
from teams import get_team_color, DEFAULT_COLOR, nearest_color_swatch, get_player_headshot_url, get_team_logo_url, first_working_url
from stats_config import COURT_GRAPHS, AXIS_GRAPHS, ANIMATED_GRAPHS, GAME_LOG_GRAPHS, COMPARISON_GRAPHS, get_stats_for_mode, BRADLEY_RATING_DESCRIPTIONS, ALL_SEASONS, VIZ_CATEGORIES, LOWER_IS_BETTER_STATS
import stats_config as _stats_config
import pickers
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

st.set_page_config(page_title="Bradley Analytics", page_icon=":basketball:", layout="wide", initial_sidebar_state="auto")

# Chart text colour (the White/Black toggle) and team-logo badges are applied by hooks on st.pyplot / st.selectbox /
# st.multiselect. They live in ui_hooks.py and are installed once per server process: wrapping these functions from
# inside this script stacked another layer on every rerun (shared by all visitors) until charts and pickers hit
# Python's recursion limit and failed until the server restarted.
import ui_hooks
import org_sections
from team_grid import team_grid_radio
import team_grid
ui_hooks.install()
ui_hooks.begin_run()

GOLD_GRADIENT = "linear-gradient(135deg, #B8860B, #F5D370, #B8860B)"
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
    "Upload Stats",
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
       blue -- ::selection doesn't reliably support gradient
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
       specifically for digit characters (U+0030-0039) instead -- letters
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

    h1, h2, h3, h4, h5, h6 {{
        font-family: "Playfair Display", serif !important;
        font-weight: 500 !important;
        color: #ffffff;
    }}

    /* Gold-gradient text accent -- the ONLY accent color in this app.
       Numbers/results use bold Times New Roman, never white Arial. Uses the
       more dramatic gradient variant since these are the animated
       (count-up) numbers -- approved in the "example 8" review pass. */
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
       slider, multiselect, etc.) -- confirmed via direct DOM inspection
       that Streamlit renders all of these through the same consistent
       stWidgetLabel structure, so one rule here reaches every label in
       the app instead of needing to hand-edit 25+ individual widget
       calls. Matches the bold-grey "Boston Celtics sends:" style used
       elsewhere, applied consistently everywhere now. */
    [data-testid="stWidgetLabel"] p {{
        color: #888888 !important;
        font-weight: bold !important;
    }}

    /* Sidebar category nav -- text-link style matching the GitHub Pages nav,
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
       different lengths -- a border-top on a shrink-wrapped element is
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
       Scoped to the sidebar specifically -- confirmed as a real bug
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

    /* Divider above the Front Office / Coaching pair -- sandwiches
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
    /* A CSS-drawn triangle (border trick), not a unicode character --
       a device/browser's font not including the right glyph is a real
       cross-platform risk, not a hypothetical one. */
    div[data-testid="stButton"] button p::before, div[data-testid="stFormSubmitButton"] button p::before, div[data-testid="stDownloadButton"] button p::before {{
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
       in a container whose key starts with "no_icon_" -- used for the
       Tableau Dashboard's own utility buttons (+, swap arrows, Remove,
       Reset) and the share-to-community / add-to-dashboard buttons
       under generated charts, none of which are "run" actions the
       triangle icon is meant to signal. */
    div[class*="st-key-no_icon_"] button p::before {{
        display: none;
    }}

    /* Number input +/- steppers: the +/- SYMBOL turns gradient gold on
       hover -- explicitly kill Streamlit's native theme-color hover
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
    /* Number boxes are typed into -- no +/- step buttons anywhere in the app. */
    [data-testid="stNumberInputStepDown"], [data-testid="stNumberInputStepUp"] {{
        display: none !important;
    }}
    /* Multiselect (Add stat filters, Position, etc.) uses a completely
       different structure than selectbox -- confirmed via direct DOM
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
       select box -- confirmed via direct DOM inspection, white/navy by
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
       a trade, etc.) -- confirmed via direct DOM inspection to be
       Streamlit's flat default red (rgb(255,75,75)) with no stable
       class, targeted here structurally via the tags container instead.
       No border here deliberately -- the container itself already has
       a gold border (targeted via stMultiSelectTagsContainer's parent
       above), and each individual chip also having its own border on
       top of that read as a redundant "double border" effect. */
    div[data-testid="stMultiSelectTagsContainer"] span {{
        background: linear-gradient(135deg, #1A1A1A 0%, #050505 100%) !important;
        color: #F5D370 !important;
    }}

    /* Tabs (Roster/Picks, etc.) -- confirmed via direct DOM inspection
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
       -- confirmed via direct DOM inspection of the real structure
       (a react-aria component, not plain HTML): the label itself gets
       data-selected="true" when checked, and its red-filled square is
       specifically the child div wrapping the checkmark svg -- not
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
       target -- see updateSliderGradient() below). This rule's second
       selector actually matches the two handle thumbs themselves
       (confirmed via inspection, not the segment between them), which
       is also the correct place to make them gold. */
    [data-testid="stSlider"] [role="group"] > div > div:first-child {{
        background: #3a3a3a !important;
    }}
    [data-testid="stSlider"] [role="group"] > div > div[style*="left"] {{
        background: {GOLD_GRADIENT} !important;
    }}
    /* The min/max value labels shown above the slider handles --
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

    /* Titled gradient-gold-bordered info card -- replaces st.info()/st.warning()
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
       -- this code does, for network-failure messages specifically,
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
    /* Hide the native "<<" collapse arrow -- our custom glowing icon replaces
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
       pages) to mount instantly -- Streamlit's own native open/close
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
       Stock Market title (a plain span, no such padding) never had --
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
       the first nav item) -- removing the h1's default padding above
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
    /* Embedded in the website the window is sized to the page, so nothing inside it may scroll -- not even by a pixel of
       rounding on a scaled (125%/150%) display. Direct visits (no ?embed=true) keep normal scrolling. */
    html.ba-embed, html.ba-embed body, html.ba-embed [data-testid="stApp"], html.ba-embed [data-testid="stAppViewContainer"],
    html.ba-embed [data-testid="stMain"], html.ba-embed section.main, html.ba-embed [data-testid="stSidebarContent"] {{
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
       the full page height regardless of its own content length --
       confirmed directly (a sidebar with 751px of actual nav content
       was being forced to a full 1400px viewport height). This makes
       it size to its own content instead, so there's a normal margin
       below the last nav item ("Glossary") rather than a large empty
       gap filling out the rest of the page. The main content area's
       own adjustable height (tallest of sidebar vs. current page) is
       untouched by this -- that logic lives in the AI Search
       container fix elsewhere, not in the sidebar's own sizing. */
    section[data-testid="stSidebar"] {{
        height: fit-content !important;
        min-height: 0 !important;
    }}

    /* The fixed bottom bar that holds the chat input has no data-testid of
       its own -- target it via its child instead. Anchored to the viewport
       (background-attachment: fixed) so it shows the correctly-aligned
       continuation of the same gradient as .stApp, instead of each element
       computing its own independent gradient and creating a visible seam. */
    div:has(> div[data-testid="stBottomBlockContainer"]) {{
        background: linear-gradient(135deg, #1A1A1A 0%, #070707 73%) !important;
        background-attachment: fixed !important;
        background-size: 100vw 100vh !important;
    }}

    /* Custom sidebar toggle icon -- glow via pure CSS, no inline JS handlers
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
       dashboard (metric numbers, buttons, links, selected states) --
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

    /* Mobile only: the floating logo + "SIDE BAR" button (shown when the
       sidebar is collapsed, which is the default on mobile) sit at a
       fixed position over the top-left of the page content, covering
       whatever's there -- confirmed via screenshot overlapping the
       banner and page title. Adds clearance above the main content on
       mobile only; desktop already has the expanded sidebar itself
       providing separation, so this would be an unwanted gap there. */
    @media (max-width: 640px) {{
        div[data-testid="stMainBlockContainer"] {{
            padding-top: 52px !important;
        }}
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
       risk -- if the scroll observer ever failed to fire in some
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

    /* #1 / #5: every generated chart (bar, line, radar, etc.) grows in --
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
       opacity transition -- the browser's own rendering engine is what
       carries this through to completion, so it's guaranteed to finish
       and land the overlay at opacity:0 (invisible, non-interactive via
       pointer-events) regardless of whether any JS in the page is still
       around to orchestrate it. That guarantee is the actual point: an
       element that's ended up invisible and inert by the browser's own
       doing is harmless to leave in the DOM indefinitely, which sidesteps
       needing its *removal* (a JS-timer-dependent step) to be reliable
       at all for correctness -- removal is still attempted afterward,
       purely as DOM hygiene, but nothing depends on it succeeding.
       (Direct testing traced the earlier stuck-overlay bug to
       setInterval/setTimeout callbacks silently not firing in this
       nested-iframe context for reasons that didn't turn up under
       inspection -- CSS animations aren't subject to whatever that was,
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

# Custom sidebar toggle: a glowing circular icon replaces Streamlit's default
# arrows. Clicking it spins the icon, then programmatically clicks Streamlit's
# real native collapse/expand button underneath -- so the actual show/hide
# logic is Streamlit's own (guaranteed correct), just with fully custom UI.
components.html(rf"""
<script>
// Player search bars: a typed name matches only players whose FIRST or LAST name (or any later part of the name)
// STARTS with it -- "lebron" finds LeBron James and nobody else. Player pickers are sent with filter_mode="prefix"
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
(function() {{
    const parentDoc = window.parent.document;
    if (parentDoc.__bqSidebarToggleInit) return;
    parentDoc.__bqSidebarToggleInit = true;

    const ICON_SRC = "data:image/png;base64,{TOGGLE_ICON_B64}";

    const fixedIcon = parentDoc.createElement('img');
    fixedIcon.id = 'bq-expand-icon';
    fixedIcon.src = ICON_SRC;
    fixedIcon.title = 'Show sidebar';
    fixedIcon.className = 'bq-toggle-icon';

    // A small labeled button under the floating logo, shown only when the
    // sidebar is closed (same condition, same visibility toggle as the
    // logo itself) -- the logo alone isn't obviously a sidebar toggle to
    // a first-time visitor, so this makes the affordance explicit.
    // Clicking either the logo or this button opens the sidebar; the logo
    // keeps its own spin/breathing animation regardless.
    // The logo and the "SIDE BAR" button are wrapped in one container that
    // acts as a single clickable unit (not just visually adjacent) --
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
        const opts = {{ bubbles: true, cancelable: true, view: window.parent,
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

    // ---- Phones and tablets: smoother dropdowns and text boxes -------------------------------------
    const touchDevice = ('ontouchstart' in window.parent) || (window.parent.navigator.maxTouchPoints || 0) > 0;
    if (touchDevice) {{
        const nav = window.parent.navigator;
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
        // open the list -- the list appearing under the finger swallowed the tap, so the box never got
        // focus -- and a second tap was needed to type.) Focusing inside the touch itself is what lets
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

    // Event delegation on the PARENT document, in the CAPTURE phase --
    // Streamlit's own radio option component calls stopPropagation() on
    // its click handling (confirmed via direct testing: an identical
    // listener in the bubble phase never fires at all for radio label
    // clicks, while the same listener in the capture phase does), so
    // bubble-phase delegation silently misses these clicks entirely.
    parentDoc.addEventListener('click', function(e) {{
        window.parent.__bqTopTrace = window.parent.__bqTopTrace || [];
        window.parent.__bqTopTrace.push({{targetTag: e.target.tagName, targetId: e.target.id}});
        if (e.target && e.target.id === 'bq-collapse-icon') {{
            toggleSidebar(e.target, 'collapse');
        }} else if (e.target && e.target.closest('#bq-toggle-wrapper')) {{
            toggleSidebar(fixedIcon, 'expand');
        }} else if (e.target) {{
            // Mobile only: auto-close the sidebar after selecting a
            // category, so the user doesn't have to manually collapse it
            // every time to see the page they just navigated to.
            const radioLabel = e.target.closest('label[data-testid="stRadioOption"]');
            if (radioLabel && radioLabel.closest('[data-testid="stSidebar"]') && window.parent.innerWidth <= 640) {{
                // Calls Streamlit's native collapse button directly and
                // synchronously, bypassing toggleSidebar() entirely --
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
    // React tree owns and swapped in a bare text node -- from then on React
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
    // handles" element at all -- just a full-width track and two
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
    // Handle positions change continuously while dragging -- listen on
    // the whole document so this fires regardless of which slider (or
    // how many) are on the current page.
    parentDoc.addEventListener('mousemove', () => scanSliders(parentDoc));
    parentDoc.addEventListener('touchmove', () => scanSliders(parentDoc));
    parentDoc.addEventListener('mouseup', () => scanSliders(parentDoc));

    // Checkbox color is handled in pure CSS below (label[data-selected]
    // targeting) -- no JS polling needed for this one.

    // #1/#5/#8/#9: scroll-repeat -- toggles .bq-inview every time the
    // element enters or leaves view, so scrolling away and back replays
    // the animation, instead of the common "only once" pattern.
    // root must be Streamlit's actual scrollable container
    // ([data-testid="stMain"]), not the window -- Streamlit scrolls an
    // inner container, and IntersectionObserver's default root (the
    // viewport) never detects that inner scrolling at all (confirmed
    // via testing).
    function initScrollObserver() {{
        const scrollRoot = parentDoc.querySelector('[data-testid="stMain"]');
        if (!scrollRoot) {{ setTimeout(initScrollObserver, 200); return; }}
        const scrollObserver = new IntersectionObserver((entries) => {{
            entries.forEach((entry) => {{
                entry.target.classList.toggle('bq-inview', entry.isIntersecting);
            }});
        }}, {{ root: scrollRoot, threshold: 0.15 }});
        function watchScrollTargets(root) {{
            const selectors = '[data-testid="stImage"] img';
            root.querySelectorAll(selectors).forEach((el) => scrollObserver.observe(el));
        }}
        watchScrollTargets(parentDoc);
        window.bqScrollObserver = scrollObserver;
        window.bqWatchScrollTargets = watchScrollTargets;
    }}
    initScrollObserver();

    // Reports this page's actual content height to whatever page is
    // embedding it (the GitHub Pages site) via postMessage, so that page
    // can resize its iframe to exactly fit the current section instead
    // of using one fixed height for every page. Sent to window.top so it
    // reaches the outermost page regardless of nesting depth.
    // Streamlit's sidebar is user-resizable by dragging its right edge,
    // and that resized width persists locally for whoever dragged it --
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
    // recreated by a later Streamlit rerun -- every widget interaction
    // triggers one).
    setInterval(lockSidebarWidth, 1000);

    function isPinchZoomed() {{
        // NOTE: only effective when the dashboard is opened directly. When
        // embedded in the GitHub Pages site (a cross-origin iframe),
        // visualViewport.scale stays 1 inside the frame even while the
        // page is pinch-zoomed (confirmed in a real browser), so this
        // returns false there. The embedding page (docs/index.html) holds
        // height updates itself while zoomed, which is what covers that case.
        // window.visualViewport is the real, purpose-built browser API
        // for this distinction -- its scale reflects pinch-zoom level
        // specifically, separate from the page's actual CSS layout
        // size, which getBoundingClientRect() (used by reportHeight
        // below) cannot tell apart on its own. Falls back to "not
        // zoomed" on a browser without this API (very old mobile
        // browsers) rather than blocking height reporting entirely on
        // those.
        const vv = parentDoc.defaultView && parentDoc.defaultView.visualViewport;
        if (!vv) return false;
        return Math.abs(vv.scale - 1) > 0.02;
    }}
    // Reports the exact height this page needs to whatever page embeds it, so the embedding page can size its iframe to
    // fit and the dashboard never needs its own scrollbar. The height is the bottom edge of the last thing actually drawn
    // in the page (zero-height helper elements -- styles, scripts -- are skipped, and Streamlit's own large bottom
    // padding is NOT counted) plus a small fixed margin. On a wide screen it is never less than the sidebar: just past
    // its last item (Glossary). While the sidebar is hidden (phones) only the page content counts.
    // Empty space kept below the last thing on the page (and below Glossary in the sidebar): about one blank line.
    const BOTTOM_MARGIN = 72;
    let lastPostedHeight = -1, lastPostAt = 0;
    function reportHeight() {{
        const container = parentDoc.querySelector('[data-testid="stMainBlockContainer"]');
        if (!container) return;
        // Zooming in must never resize the iframe -- see isPinchZoomed() above.
        if (isPinchZoomed()) return;
        const main = parentDoc.querySelector('[data-testid="stMain"]') || parentDoc.querySelector('section.main');
        const mainTop = main ? main.getBoundingClientRect().top : 0;
        const mainScroll = main ? main.scrollTop : 0;
        const block = container.querySelector('[data-testid="stVerticalBlock"]') || container;
        let contentBottom = 0;
        for (const el of block.children) {{
            const r = el.getBoundingClientRect();
            if (r.height > 3 && r.width > 3) contentBottom = Math.max(contentBottom, r.bottom);
        }}
        if (!contentBottom) return;          // nothing drawn yet: don't announce a height for an empty, still-loading page
        const mainNeeded = Math.ceil(contentBottom - mainTop + mainScroll) + BOTTOM_MARGIN;

        const sidebarSection = parentDoc.querySelector('section[data-testid="stSidebar"]');
        const sbRect = sidebarSection ? sidebarSection.getBoundingClientRect() : null;
        const sidebarShowing = !!(sbRect && sbRect.width > 50);
        let sidebarNeeded = 0;
        if (sidebarShowing) {{
            const items = sidebarSection.querySelectorAll('label[data-testid="stRadioOption"]');
            if (!items.length) return;       // sidebar list not built yet -- wait, so the window doesn't collapse then re-expand on load
            sidebarNeeded = Math.ceil(items[items.length - 1].getBoundingClientRect().bottom - sbRect.top) + BOTTOM_MARGIN;
        }}
        const height = Math.max(mainNeeded, sidebarNeeded);
        // The sidebar background stretches to the full window height, so a tall page never leaves an empty gap below Glossary.
        if (sidebarShowing) sidebarSection.style.setProperty('height', height + 'px', 'important');
        // Only re-send when it changed (or every few seconds, so a reloaded embedding page is never left waiting).
        if (Math.abs(height - lastPostedHeight) < 2 && Date.now() - lastPostAt < 4000) return;
        lastPostedHeight = height;
        lastPostAt = Date.now();
        window.top.postMessage({{ type: 'ba-resize', height: height }}, '*');
    }}
    let reportHeightDebounceTimer = null;
    function debouncedReportHeight() {{
        if (reportHeightDebounceTimer) clearTimeout(reportHeightDebounceTimer);
        reportHeightDebounceTimer = setTimeout(reportHeight, 60);
    }}
    function initHeightReporter() {{
        // Embedded in the website (?embed=true), the window is sized to the page, so the page must never scroll inside it. Mark the
        // document so the CSS can switch the scroll containers off; opening the dashboard on its own keeps normal scrolling.
        try {{
            if (new URLSearchParams(parentDoc.defaultView.location.search).get('embed') === 'true') parentDoc.documentElement.classList.add('ba-embed');
        }} catch (e) {{}}
        const container = parentDoc.querySelector('[data-testid="stMainBlockContainer"]');
        const sidebar = parentDoc.querySelector('section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"]');
        if (!container) {{ setTimeout(initHeightReporter, 200); return; }}
        const resizeObserver = new ResizeObserver(() => debouncedReportHeight());
        resizeObserver.observe(container);
        if (sidebar) resizeObserver.observe(sidebar);
        // Catches back up once the user zooms back out -- reportHeight
        // itself skips while isPinchZoomed() is true, so without this,
        // any real layout change that happened to occur *during* a
        // zoom session (e.g. rotating the phone while zoomed in) would
        // never get reported at all.
        const vv = parentDoc.defaultView && parentDoc.defaultView.visualViewport;
        if (vv) {{
            vv.addEventListener('resize', () => {{ if (!isPinchZoomed()) debouncedReportHeight(); }});
        }}
        reportHeight();
        // Belt and braces. A chart or image can finish loading without this container's own size event firing (and
        // Streamlit may swap the container element), which once left the window shorter than the page and hid the
        // bottom behind an inner scrollbar. So also re-check on any change to the page, on every image that loads,
        // and twice a second -- a re-check is a few cheap measurements, and it only re-sends when the height changed.
        new MutationObserver(() => debouncedReportHeight()).observe(container, {{ childList: true, subtree: true }});
        parentDoc.addEventListener('load', () => debouncedReportHeight(), true);
        setInterval(() => {{ if (!parentDoc.hidden) reportHeight(); }}, 500);
    }}
    initHeightReporter();

    // Category switches (clicking a different sidebar item) re-render the
    // whole main content area over several ticks -- images, fonts, and any
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
            if (text) {{ try {{ window.top.postMessage({{ type: 'ba-page', page: text }}, '*'); }} catch (e) {{}} }}
                [100, 400, 900, 1600].forEach((delay) => setTimeout(reportHeight, delay));

                // Re-plays the page fade-in on every switch, including
                // repeat visits to an already-seen page. Directly setting
                // stMainBlockContainer's own opacity (even via
                // setProperty(..., 'important')) was confirmed, through
                // direct testing, to have no visible effect whatsoever --
                // something about that specific element resists it for
                // reasons that didn't turn up under inspection. This
                // sidesteps that entirely with a same-color overlay laid
                // directly on top of the content, which fades itself out
                // instead, rather than depending on that element's own
                // opacity ever actually changing.
                const freshContainer = parentDoc.querySelector('[data-testid="stMainBlockContainer"]');
                if (freshContainer) {{
                    // Removes any overlay left over from a previous switch
                    // first -- if the component iframe this script itself
                    // runs in gets torn down and recreated by Streamlit's
                    // own re-render (plausible, since this whole script
                    // reruns each time), any setTimeout scheduled by the
                    // *previous* instance to remove its own overlay is
                    // lost with it. The overlay itself survives, though,
                    // since it was appended to the parent document, not
                    // the iframe's own -- so without this cleanup, a
                    // stranded overlay could sit there permanently.
                    parentDoc.querySelectorAll('[data-bq-fade-overlay]').forEach((el) => el.remove());

                    const rect = freshContainer.getBoundingClientRect();
                    const overlay = parentDoc.createElement('div');
                    overlay.setAttribute('data-bq-fade-overlay', '1');
                    overlay.className = 'bq-fade-overlay';
                    // Measured at switch time, before the new page's
                    // content has actually rendered -- so this rect still
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
                    // Best-effort DOM cleanup only -- correctness no
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

            // Idempotent by actual DOM state, not a flag -- a flag set
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
                if (node.matches && node.matches('[data-testid="stImage"] img')) {{
                    if (window.bqScrollObserver) window.bqScrollObserver.observe(node);
                }}
                if (node.querySelectorAll && window.bqWatchScrollTargets) window.bqWatchScrollTargets(node);
                if (node.matches && node.matches('[data-testid="stNumberInput"]')) fixDollarLabels(node.parentElement || parentDoc);
                if (node.querySelectorAll) fixDollarLabels(node);
                if (node.querySelectorAll) fixPercentSuffixes(node);
                if (node.querySelectorAll) addCommaFormattingToAll(node);
            }});
        }}
    }}).observe(parentDoc.body, {{ childList: true, subtree: true, characterData: true }});
}})();
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
<div class="bq-sidebar-header" style="display:flex; align-items:center; gap:10px; margin-bottom:0.1rem;">
  <img id="bq-collapse-icon" src="data:image/png;base64,{TOGGLE_ICON_B64}" title="Hide sidebar"
       class="bq-toggle-icon">
  <span class="bq-sidebar-title" style="font-family:'Playfair Display', serif; font-weight:500; font-size:1.75rem; color:#ffffff; line-height:1.0;">Bradley Analytics</span>
</div>
""", unsafe_allow_html=True)
st.sidebar.markdown(
    '<p style="font-size:0.95rem; font-weight:300; line-height:1.5; color:#9a9a9a; '
    'margin-top:6px; margin-bottom:0.6rem;">NBA shot charts, heat maps, and stat leaderboards</p>',
    unsafe_allow_html=True,
)
# Applies any pending programmatic navigation (from nav_to(), called on
# a later page) before the radio widget instantiates -- confirmed via
# direct testing that Streamlit blocks ANY assignment to a
# widget-backed session_state key once that widget already exists in
# the current run, even immediately followed by st.rerun(). The fix is
# a separate variable, applied here, strictly before instantiation.
if st.session_state.get("pending_nav_target"):
    st.session_state["category_radio"] = st.session_state.pop("pending_nav_target")
elif "category_radio" not in st.session_state and st.query_params.get("page") in CATEGORIES:
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


@st.cache_data
def _load_salary_data():
    """
    An embedded CSV shipped with the app, not a live data source (no
    live browser access at request time) -- sourced from Spotrac,
    which itself compiles publicly reported contract figures (team
    announcements, league filings, reporting from outlets like
    Shams Charania) rather than any proprietary data of its own.
    One row per player per season, so a player's history across
    multiple years can build up over time as more seasons get added.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "data", "salaries.csv")
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=["PLAYER_NAME", "SEASON", "SALARY"])


@st.cache_data
def _load_draft_picks_data():
    """Same approach as salaries -- an embedded, user-fillable template CSV."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "draft_picks.csv")
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=["TEAM", "PICK"])


def fetch_stats_for_source(source: str, season: str, mode: str = "player") -> pd.DataFrame:
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
        per_mode = "Totals" if source in ("bio", "calculated", "bradley_rating") else "PerGame"
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
        marks = {}
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
            funcs, total = [first], len(inspect.getsource(first).splitlines())
            for f in rest:
                if total >= 60:
                    break
                funcs.append(f)
                total += len(inspect.getsource(f).splitlines())
    chunks = []
    for f in funcs:
        try:
            chunks.append(textwrap.dedent(inspect.getsource(f)))
        except (OSError, TypeError):
            continue
    text = "\n\n".join(c.rstrip("\n") for c in chunks).strip("\n")
    lines = text.splitlines()
    if len(lines) > 140:                       # a very long builder: its first 140 lines are plenty to scroll through
        text = "\n".join(lines[:140])
    return text or "import pandas as pd\nimport matplotlib.pyplot as plt"


_LOADING_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;500;600&display=swap');
@property --bq-pct { syntax: '<integer>'; initial-value: 0; inherits: false; }
@keyframes bq-code-scroll { from { transform: translateY(0); } to { transform: translateY(-50%); } }
@keyframes bq-load { 0% { width: 0%; --bq-pct: 0; } 8% { width: 30%; --bq-pct: 30; } 25% { width: 58%; --bq-pct: 58; }
  50% { width: 78%; --bq-pct: 78; } 75% { width: 90%; --bq-pct: 90; } 100% { width: 97%; --bq-pct: 97; } }
.bq-code-loading-box { background: linear-gradient(135deg, #1A1A1A 0%, #050505 100%); border: 1px solid #2a2a2a;
  border-radius: 10px; padding: 12px 14px 12px; margin: 8px 0; font-family: 'Roboto Mono', 'Roboto', monospace; }
.bq-code-loading-label { color: #D4AF37; font-size: 0.82rem; margin-bottom: 8px; font-weight: 500;
  font-family: 'Roboto Mono', 'Roboto', monospace; }
.bq-code-window { position: relative; height: 188px; overflow: hidden;
  -webkit-mask-image: linear-gradient(180deg, transparent 0, #000 14%, #000 86%, transparent 100%);
          mask-image: linear-gradient(180deg, transparent 0, #000 14%, #000 86%, transparent 100%); }
.bq-code-roll { animation: bq-code-scroll var(--bq-dur, 30s) linear infinite; }
.bq-code-roll .cl { margin: 0; padding: 0; font-family: 'Roboto Mono', 'Roboto', monospace; font-size: 0.74rem;
  line-height: 1.55; color: #c9c4b8; white-space: pre; overflow: hidden; text-overflow: clip; }
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
  font-family: 'Roboto Mono', 'Roboto', monospace; font-variant-numeric: tabular-nums; }
.bq-code-pct::after { counter-reset: bqp var(--bq-pct); content: counter(bqp) "%"; animation: bq-load 16s
  cubic-bezier(.25,.8,.3,1) forwards; }
.bq-code-done .bq-code-progress-fill { animation: none; width: 100%; }
.bq-code-done .bq-code-pct::after { animation: none; content: "100%"; }
</style>
"""


@contextlib.contextmanager
def code_loading_animation(label: str = "Generating visualization", code=None):
    """
    A drop-in replacement for `with st.spinner(...):` -- wraps the slow part (a download, or building a chart after
    RUN) and, while it runs, shows the REAL Python behind that step scrolling past (Roboto Mono, coloured like an
    editor) above a gold loading bar that climbs toward 100% and fills to 100% the moment the step finishes; then the
    whole box disappears and the result takes its place. `code`: the function(s) whose source to show (e.g. the chart
    builder); when omitted, one of the app's own chart builders is shown.
    """
    import html as _html
    import time as _time
    lines = _highlight_python(_loading_source(code, label))
    # one element per line (Streamlit's markdown would fold plain line breaks into one paragraph)
    numbered = "".join(f'<div class="cl"><span class="ln">{i}</span>{ln}</div>' for i, ln in enumerate(lines, 1))
    duration = max(12, min(60, len(lines) * 0.42))
    placeholder = st.empty()

    def _box(done=False):
        return (_LOADING_CSS.replace("\n", " ") +
                f'<div class="bq-code-loading-box{" bq-code-done" if done else ""}">'
                f'<div class="bq-code-loading-label">&gt; {_html.escape(label)}...</div>'
                f'<div class="bq-code-window"><div class="bq-code-roll" style="--bq-dur:{duration:.0f}s">'
                f'{numbered}{numbered}</div></div>'
                f'<div class="bq-code-bar-row"><div class="bq-code-progress-track"><div class="bq-code-progress-fill">'
                f'</div></div><div class="bq-code-pct"></div></div></div>')

    placeholder.markdown(_box(), unsafe_allow_html=True)
    started = _time.monotonic()
    try:
        yield
        if _time.monotonic() - started > 0.8:
            # finished: the bar fills to 100% for a moment before the result replaces it
            placeholder.markdown(_box(done=True), unsafe_allow_html=True)
            _time.sleep(0.35)
    finally:
        placeholder.empty()


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


def persistent_run_button(enabled: bool, key: str, show_chart_color: bool = True) -> bool:
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
    if st.button("RUN", use_container_width=True, key=f"run_btn_{key}"):
        st.session_state[state_key] = True
    return enabled and st.session_state.get(state_key, False)


def friendly_error(e):
    """A plain-English reason for a failed NBA data call (the raw text is a wall of connection-pool jargon)."""
    text = f"{type(e).__name__}: {e}"
    low = text.lower()
    if "proxy" in low:
        return ("the proxy this app uses to reach the NBA stats site didn't respond (it closed the connection). "
                "This is usually momentary -- try again in a minute. If it keeps happening, the proxy service set "
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
                st.warning("All 6 Tableau Dashboard slots are full -- remove one first (on the Tableau Dashboard page) to add this.")
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


def render_front_office_roster(team_name):
    """A real roster table: each current player's bio info (position,
    height, weight, age) joined with their actual per-game stats for
    a chosen season -- not a mock-up, genuinely fetched and joined
    the same way the rest of this app already does it. Sorted by PPG
    by default, shown in full (no inner scrollbar) with a transparent
    background rather than Streamlit's usual dataframe panel look."""
    team_id = TEAM_NAME_TO_RECORD[team_name]["id"]
    season = st.selectbox("Season:", ALL_SEASONS, index=0, key=f"fo_roster_season_{team_name}")
    with code_loading_animation(f"Downloading {team_name}'s {season} roster"):
        roster_df = get_team_roster(team_id, season)
        stats_df = get_player_stats(season, per_mode="PerGame")

    if roster_df.empty:
        st.warning(f"No roster found for {team_name} in {season}.")
        return

    roster_cols = [c for c in ["PLAYER_ID", "PLAYER", "POSITION", "HEIGHT", "WEIGHT", "AGE"] if c in roster_df.columns]
    table = roster_df[roster_cols].copy()
    stat_cols = [c for c in ["PLAYER_ID", "PTS", "REB", "AST", "STL", "BLK", "FG_PCT", "FG3_PCT", "MIN"] if c in stats_df.columns]
    if "PLAYER_ID" in table.columns and "PLAYER_ID" in stat_cols:
        table = table.merge(stats_df[stat_cols], on="PLAYER_ID", how="left")
    if "PTS" in table.columns:
        table = table.sort_values("PTS", ascending=False)
    table = table.drop(columns=["PLAYER_ID"], errors="ignore")

    # Real formatting instead of raw floats: age as a plain whole
    # number, ordinary per-game stats to one decimal, and only the
    # actual percentage columns keeping three decimals.
    if "AGE" in table.columns:
        table["AGE"] = table["AGE"].round(0).astype("Int64").astype(str)
    one_decimal_cols = [c for c in ["PTS", "REB", "AST", "STL", "BLK", "MIN"] if c in table.columns]
    for c in one_decimal_cols:
        table[c] = table[c].map(lambda v: f"{v:.1f}" if pd.notna(v) else v)
    pct_cols = [c for c in ["FG_PCT", "FG3_PCT"] if c in table.columns]
    for c in pct_cols:
        table[c] = table[c].map(lambda v: f"{v:.3f}" if pd.notna(v) else v)

    rename = {"PLAYER": "Player", "POSITION": "Pos", "HEIGHT": "Ht", "WEIGHT": "Wt", "AGE": "Age",
              "PTS": "PPG", "REB": "RPG", "AST": "APG", "STL": "SPG", "BLK": "BPG",
              "FG_PCT": "FG%", "FG3_PCT": "3P%", "MIN": "MPG"}
    table = table.rename(columns=rename)

    # st.table renders as plain HTML (unlike st.dataframe's canvas-based
    # grid), which is what makes both "no inner scrollbar" and a real
    # transparent background possible -- it shows every row in full by
    # its own nature, and its background is a normal, CSS-targetable
    # element rather than a canvas Streamlit draws into.
    st.markdown(
        "<style>div[data-testid='stTable'] table, div[data-testid='stTable'] thead, "
        "div[data-testid='stTable'] tbody, div[data-testid='stTable'] th, div[data-testid='stTable'] td "
        "{ background: transparent !important; }</style>",
        unsafe_allow_html=True,
    )
    st.table(table.set_index(table.columns[0]))


def _open_onoff_for_team(team_name):
    """Button callback: jump to the On/Off Lineup Network page with this team already picked. Done in a callback
    (which runs before any widget of the next run exists) -- setting the sidebar's own value from inside the page,
    after the sidebar was already drawn, is what raised the StreamlitAPIException."""
    st.session_state["onoff_team"] = team_name
    st.session_state["category_radio"] = "On/Off Lineup Network"


def render_coaching_player_minutes(team_name):
    """Real per-player minutes for the season, plus a direct link (at the top) into the existing On/Off Lineup Network
    for this same team -- reuses that real, working feature instead of duplicating it."""
    st.button(f"Open On/Off Lineup Network for {team_name}", key=f"co_minutes_link_{team_name}",
              on_click=_open_onoff_for_team, args=(team_name,))
    st.caption(
        "For real lineup combinations and on/off net-rating impact for these minutes, "
        "the On/Off Lineup Network covers this team in full."
    )
    team_id = TEAM_NAME_TO_RECORD[team_name]["id"]
    season = st.selectbox("Season:", ALL_SEASONS, index=0, key=f"co_minutes_season_{team_name}")
    with code_loading_animation(f"Downloading {team_name}'s {season} minutes"):
        stats_df = get_player_stats(season, per_mode="PerGame")
        roster_df = get_team_roster(team_id, season)

    if roster_df.empty:
        st.warning(f"No roster found for {team_name} in {season}.")
        return

    ids = set(roster_df["PLAYER_ID"]) if "PLAYER_ID" in roster_df.columns else set()
    team_stats = stats_df[stats_df["PLAYER_ID"].isin(ids)] if "PLAYER_ID" in stats_df.columns else stats_df.iloc[0:0]
    if team_stats.empty or "MIN" not in team_stats.columns:
        st.warning("Couldn't load minutes data for this team/season.")
    else:
        table = team_stats[["PLAYER_NAME", "MIN", "GP"]].sort_values("MIN", ascending=False)
        table = table.rename(columns={"PLAYER_NAME": "Player", "MIN": "MPG", "GP": "Games"})
        st.dataframe(table, use_container_width=True, hide_index=True)


def render_coaching_player_tendencies(team_name):
    """A real, league-wide play-type tendency table (isolation,
    pick-and-roll, post-up, spot-up, transition, etc) for every NBA
    player that season -- not just this team's roster, matching what
    was actually asked for. Backed by real Synergy play-type data."""
    season = st.selectbox("Season:", ALL_SEASONS, index=0, key=f"co_tendencies_season_{team_name}")
    play_type_options = {
        "All play types": "", "Isolation": "Isolation", "Pick-and-Roll Ball Handler": "PRBallHandler",
        "Pick-and-Roll Roll Man": "PRRollman", "Post-Up": "Postup", "Spot-Up": "Spotup",
        "Hand-Off": "Handoff", "Cut": "Cut", "Transition": "Transition", "Off Screen": "OffScreen",
        "Putback": "OffRebound", "Miscellaneous": "Misc",
    }
    play_type_label = st.selectbox("Play type:", list(play_type_options.keys()), key=f"co_tendencies_type_{team_name}")
    only_this_team = st.checkbox(f"Only show {team_name} players", value=False, key=f"co_tendencies_teamonly_{team_name}")

    with code_loading_animation("Downloading play-type data"):
        try:
            pt_df = get_player_playtype_stats(season, play_type=play_type_options[play_type_label])
        except Exception:
            pt_df = None

    if pt_df is None or pt_df.empty:
        st.warning("Couldn't load play-type data for this season/play type.")
        return

    if only_this_team and "TEAM_ABBREVIATION" in pt_df.columns:
        team_abbrev = TEAM_NAME_TO_RECORD[team_name]["abbreviation"]
        pt_df = pt_df[pt_df["TEAM_ABBREVIATION"] == team_abbrev]

    cols = [c for c in ["PLAYER_NAME", "TEAM_ABBREVIATION", "PLAY_TYPE", "POSS", "PPP", "FREQ", "PERCENTILE"] if c in pt_df.columns]
    table = pt_df[cols].sort_values("PPP", ascending=False) if "PPP" in cols else pt_df[cols]
    rename = {"PLAYER_NAME": "Player", "TEAM_ABBREVIATION": "Team", "PLAY_TYPE": "Play Type",
              "POSS": "Possessions", "PPP": "Pts/Poss", "FREQ": "Frequency", "PERCENTILE": "Percentile"}
    st.dataframe(table.rename(columns=rename), use_container_width=True, hide_index=True)


def render_front_office_cba_guide():
    """For now, just the real CBA document itself as a direct download, titled the way it was asked for. The actual
    analysis-on-the-document version comes later."""
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
        st.error("The CBA document isn't available in this deployment yet.")
        return
    # Just the download: the inline PDF viewer that used to sit under it showed up as a large blank white page
    # (browsers won't render a multi-megabyte data: PDF inside the app's frame), so it is gone.
    st.download_button("Download the full PDF", data=pdf_bytes, file_name="NBA-Collective-Bargaining-Agreement.pdf", mime="application/pdf")


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
    picked_team = team_grid_radio(label, widget_key, default=default_team, extras=["White", "Black", "Gold"], extras_first=True)
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


def render_passing_web(picked_name, player_id, season, top_n=5, rank_ascending=False, color_input=None,
                       key="passing_web", show_explainer=True):
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
            line = (f"**{name}** -- {zone_names[spot]}: {share:.0%} of his shots right after {passer_last}'s passes"
                    f"{runner} (from {n_made} baskets {passer_last} assisted to him)")
        else:
            spot = _catch_spot(r_shots)
            xy = _shots_centroid(r_shots, spot)
            if spot:
                why = ("fewer than 3 of his baskets were assisted by " + passer_last) if rid in source_by_id \
                    else f"{passer_last}'s assists to him couldn't be looked up just now"
                line = (f"**{name}** -- {zone_names.get(spot, spot)}: {why}, so he's placed where he shoots most off "
                        f"a catch")
        placement_lines.append(line or f"**{name}** -- no shot data found, so shown in a general spot")
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
                           receiver_zone_stats=receiver_zone_stats), key)
    title = f"Passing Connections -- {picked_name}"
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
                        f"from his own FG% there -- the NBA only records who passed on made baskets. Areas are the "
                        f"NBA's own shot zones. Each picture sits at the average spot of those shots; players sharing an "
                        f"area stand right next to each other, as close to their real spot as the others allow. "
                        f"Hover a player to see every area.")
        else:
            st.markdown(f"{passer_last}'s assists couldn't be looked up just now (pbpstats.com and the NBA "
                        f"play-by-play were both unreachable), so these players are placed where they shoot most off "
                        f"a catch -- not specifically after {passer_last}'s passes. Run it again in a minute.")
        st.markdown("\n".join(f"- {ln}" for ln in placement_lines))



if category == "Home":
    banner_path = os.path.join(os.path.dirname(__file__), "..", "assets", "banner.png")
    if os.path.exists(banner_path):
        with st.container(key="home_banner"):
            st.image(banner_path, use_container_width=True)
    st.subheader("Bradley Analytics Software Engine")
    st.write(
        "An interactive dashboard covering NBA shot charts, heat maps, stat "
        "leaderboards, criteria-based player search, trade analysis, and "
        "on/off court impact, all built on the same live NBA API data pipeline."
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Visualization Types", "6")
    col2.metric("Dashboard Sections", "10")
    col3.metric("Data Source", "NBA API")
    info_card("Getting Started",
        "Pick a section from the sidebar to get started. Search by Player and "
        "Search by Team generate real shot charts, heat maps, and leaderboards. "
        "Search by Criteria, Trade Machine, On/Off Stats, and Advanced "
        "Stats are all built on the same live data.")
    info_card("A Note on Data",
        "Every chart here uses real, live NBA API data. Salaries and draft picks "
        "are *coming soon* -- there's no free public API for either, so those "
        "will come from a CSV you fill in yourself once that's ready.")
    st.stop()


elif category == "AI Search":
    # The whole page lives in ai_search.py: ask anything -> a written answer plus an interactive chart with its own
    # colour/style/season controls, clarifying questions with one-click answers, and the conversation kept on screen.
    ai_search.render({
        "PLAYER_NAME_TO_RECORD": PLAYER_NAME_TO_RECORD, "TEAM_NAME_TO_RECORD": TEAM_NAME_TO_RECORD,
        "resolve_color_input": resolve_color_input, "DEFAULT_COLOR": DEFAULT_COLOR,
        "default_color_team": _default_color_team, "load_salary_data": _load_salary_data,
        "code_loading_animation": code_loading_animation, "info_card": info_card, "GOLD_GRADIENT": GOLD_GRADIENT,
        "game_lookup": _game_lookup, "friendly_error": friendly_error, "strip_accents": _strip_accents,
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
            })
        st.stop()
    # "Stat mode:" is drawn right above "Add stat filters:" (the stats it changes), but the league's stats have to be
    # downloaded in that mode before any filter is drawn -- so its current choice is read here from its widget key.
    _CRIT_MODES = ["Per Game", "Per 36", "Totals"]
    if st.session_state.get("crit_stat_mode") not in _CRIT_MODES:
        st.session_state["crit_stat_mode"] = "Per Game"
    stat_mode_label = st.session_state["crit_stat_mode"]
    stat_mode_value = {"Totals": "Totals", "Per Game": "PerGame", "Per 36": "Per36"}[stat_mode_label]

    if season:
        st.subheader("Filters")
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

            # Salary -- merged in from the same embedded salaries.csv
            # used everywhere else in the app (Trade Machine, roster
            # display), so as that file gets filled in over time this
            # filter (and every other salary reference in the app)
            # picks it up automatically, no code changes needed later.
            salary_data_criteria = _load_salary_data()
            if not salary_data_criteria.empty and "PLAYER_NAME" in salary_data_criteria.columns and "SEASON" in salary_data_criteria.columns:
                season_salaries_criteria = salary_data_criteria[salary_data_criteria["SEASON"] == season]
                filtered = filtered.merge(
                    season_salaries_criteria[["PLAYER_NAME", "SALARY"]], on="PLAYER_NAME", how="left",
                )
                salary_known = filtered["SALARY"].dropna()
                salary_range = None
                if not salary_known.empty:
                    try:
                        s_sal_min = int(salary_known.min())
                        s_sal_max = int(salary_known.max())
                        if s_sal_min < s_sal_max:
                            salary_range = st.slider(
                                "Salary:", s_sal_min, s_sal_max, (s_sal_min, s_sal_max),
                                format_func=lambda v: f"${v / 1_000_000:.1f}M",
                            )
                        else:
                            salary_range = (s_sal_min, s_sal_max)
                    except Exception:
                        # Whatever the exact cause, this filter is a
                        # narrowing convenience on top of the criteria
                        # search, not the core feature -- if the salary
                        # slider itself can't be built for some reason,
                        # this shows every player instead of crashing
                        # the whole page over one optional filter.
                        salary_range = None
                if salary_range is not None:
                    # Players with no salary on file are left in rather
                    # than dropped -- this filter only narrows among
                    # players salary data actually exists for, instead
                    # of silently hiding everyone else from the whole
                    # page.
                    filtered = filtered[
                        filtered["SALARY"].isna() | filtered["SALARY"].between(salary_range[0], salary_range[1])
                    ]
            else:
                st.markdown("*Salary: Coming soon.*")

            # Stat/rating sliders -- progressive disclosure via
            # multiselect first (30+ possible stats would be an
            # overwhelming wall of sliders shown all at once). AGE and
            # PLAYER_HEIGHT_INCHES are deliberately excluded here since
            # they're both dedicated filters above already -- leaving
            # them in this list too would let someone filter on the
            # same thing twice in two different, redundant widgets.
            player_stats = get_stats_for_mode("player", exclude_bradley_rating=True)
            flat_stats = [
                (field, label) for _, stats in player_stats for field, label, source, modes in stats
                if field not in ("AGE", "PLAYER_HEIGHT_INCHES")
            ]
            stat_labels = [label for field, label in flat_stats]
            label_to_field = {label: field for field, label in flat_stats}

            st.radio("Stat mode:", _CRIT_MODES, horizontal=True, key="crit_stat_mode")
            chosen_stat_labels = st.multiselect("Add stat filters:", stat_labels)
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

            match_count = len(filtered)
            criteria_tools.count_line(f"{match_count} players match these filters.")

            if match_count == 0:
                st.warning("No players match -- loosen a filter.")
            elif match_count > 30:
                st.warning(f"{match_count} players match, narrow the filters to match 30 or fewer players.")
            else:
                st.subheader("Generate scatter plot")
                y_label = st.selectbox("Stat (Y axis):", stat_labels, key="crit_y")
                x_label = st.selectbox("Stat (X axis):", stat_labels, key="crit_x", index=min(1, len(stat_labels) - 1))
                crit_color_input = color_input_with_dropdown(f"crit_color_{season}")
                run_criteria = persistent_run_button(True, key="search_by_criteria")

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

            trade_season = st.selectbox(
                "Season:", ALL_SEASONS,
                index=0, key="trade_season",
            )
            # Two real dropdowns side by side, top-aligned: each opens a 5 x 6 grid of team logos (bigger than
            # these used to be, smaller than Search by Team's full-width grid).
            tcol1, tcol2 = st.columns(2, vertical_alignment="top")
            with tcol1:
                team_a_name = team_grid.team_dropdown("Team 1:", "trade_team_a", logo_px=60)
            with tcol2:
                team_b_name = team_grid.team_dropdown("Team 2:", "trade_team_b", logo_px=60)

            if team_a_name and team_b_name and team_a_name == team_b_name:
                st.warning("Pick two different teams.")
            elif team_a_name and team_b_name:
                with code_loading_animation("Downloading rosters"):
                    try:
                        roster_a = get_team_roster(TEAM_NAME_TO_RECORD[team_a_name]["id"], trade_season)
                        roster_b = get_team_roster(TEAM_NAME_TO_RECORD[team_b_name]["id"], trade_season)
                    except Exception as e:
                        roster_a, roster_b = None, None
                        st.error(f"Couldn't load rosters for {trade_season}: {e}")

                if roster_a is not None and roster_b is not None:
                    names_a = sorted(roster_a["PLAYER"].tolist()) if "PLAYER" in roster_a.columns else []
                    names_b = sorted(roster_b["PLAYER"].tolist()) if "PLAYER" in roster_b.columns else []

                    with code_loading_animation("Downloading player stats for roster display"):
                        try:
                            roster_stats = get_player_stats(trade_season, per_mode="PerGame")
                        except Exception:
                            roster_stats = None

                    salary_data = _load_salary_data()
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
                        with roster_tab:
                            for _, row in roster_df.iterrows():
                                pid = row.get("PLAYER_ID")
                                name = row.get("PLAYER", "Unknown")
                                bio_parts = []
                                for c in ("POSITION", "HEIGHT", "AGE"):
                                    if c in row.index and pd.notna(row[c]):
                                        if c == "AGE":
                                            bio_parts.append(f"{int(row[c])} yo")
                                        else:
                                            bio_parts.append(str(row[c]))
                                bio_line = ", ".join(bio_parts)

                                stat_line = ""
                                if roster_stats is not None and "PLAYER_NAME" in roster_stats.columns:
                                    stat_match = roster_stats[roster_stats["PLAYER_NAME"] == name]
                                    if not stat_match.empty:
                                        sr = stat_match.iloc[0]
                                        bits = [f"{sr[f]:.1f} {l}" for f, l in [("PTS", "pts"), ("REB", "reb"), ("AST", "ast")]
                                                if f in sr.index and pd.notna(sr[f])]
                                        stat_line = ", ".join(bits)

                                salary_line = ""
                                if "PLAYER_NAME" in salary_data.columns and "SEASON" in salary_data.columns:
                                    player_seasons = salary_data[salary_data["PLAYER_NAME"] == name]
                                    sal_match = player_seasons[player_seasons["SEASON"] == trade_season]
                                    if not sal_match.empty:
                                        sal = sal_match.iloc[0].get("SALARY")
                                        # Years remaining computed dynamically
                                        # from how many of this player's rows
                                        # are this season or later, rather than
                                        # stored as a separate field that could
                                        # drift out of sync as more seasons get
                                        # added to the CSV over time.
                                        yrs = (player_seasons["SEASON"] >= trade_season).sum()
                                        if pd.notna(sal):
                                            salary_line = f"${sal / 1_000_000:.1f}m" + (f", {int(yrs)} yrs" if yrs else "")

                                ccol1, ccol2, ccol3 = st.columns([0.4, 0.8, 4])
                                with ccol1:
                                    checked = st.checkbox("Select", key=f"{key_prefix}_{name}", label_visibility="collapsed")
                                with ccol2:
                                    if pid:
                                        # A fixed pixel width, not
                                        # use_container_width -- confirmed as
                                        # the real cause of oversized mobile
                                        # images: Streamlit's columns stack
                                        # vertically on narrow viewports, so a
                                        # container-width image scales up to
                                        # fill the full screen width instead of
                                        # staying a small roster thumbnail.
                                        st.image(first_working_url(get_player_headshot_url(pid)), width=60)
                                with ccol3:
                                    detail_line = " -- ".join(x for x in [bio_line, stat_line, salary_line] if x)
                                    # One markdown block with an explicit <br>
                                    # and tight line-height, rather than
                                    # separate markdown+caption calls -- each
                                    # of those is its own block-level element
                                    # with Streamlit's normal paragraph spacing
                                    # between them, which read as a much bigger
                                    # gap than intended between a player's name
                                    # and their stat line.
                                    st.markdown(
                                        f'<div style="line-height:1.15;"><strong>{name}</strong><br>'
                                        f'<span style="color:#9a9a9a; font-size:0.85rem;">{detail_line}</span></div>',
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
                        st.markdown(f'<p style="color:#888; font-weight:bold; font-size:1.2rem;">{team_a_name}</p>', unsafe_allow_html=True)
                        sent_by_a, picks_sent_by_a = _render_team_roster(roster_a, team_a_name, "a")
                    with rcol2:
                        st.markdown(f'<p style="color:#888; font-weight:bold; font-size:1.2rem;">{team_b_name}</p>', unsafe_allow_html=True)
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

                    # Salary figures come straight from the same embedded
                    # salaries.csv already loaded above for the roster display
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
                                trade_stats = get_player_stats(trade_season, per_mode="PerGame")
                            except Exception as e:
                                trade_stats = None
                                st.error(f"Couldn't load stats: {e}")
                        if trade_stats is not None and "PLAYER_NAME" in trade_stats.columns:
                            player_ids = {name: rec["id"] for name, rec in PLAYER_NAME_TO_RECORD.items()}
                            fig = build_trade_breakdown_image(
                                team_a_name, team_b_name,
                                sends_a=sent_by_a, sends_b=sent_by_b,
                                stats_df=trade_stats, player_ids=player_ids,
                                salary_data=salary_data,
                            )
                            st.pyplot(fig, use_container_width=True)
                            add_to_tableau_dashboard(fig, "Trade Machine", "tableau_trade")
                            offer_share_to_community(fig, "Trade Machine", "share_trade")
                            plt.close(fig)
        elif _fo_tab == "Roster":
            render_front_office_roster(_fo_team)
        elif _fo_tab == "Salary Cap":
            org_sections.coming_soon("Salary Cap", "real contract, cap-hold, and cap-space figures for each team")
        elif _fo_tab == "Draft Scouting":
            org_sections.coming_soon("Draft Scouting", "actual prospect evaluations and projections")
        elif _fo_tab == "CBA Guide":
            render_front_office_cba_guide()
        elif _fo_tab == "Staff":
            org_sections.coming_soon("Staff", "GM history and a real transaction log to analyze")
    st.stop()

elif category == "Coaching":
    _co_tabs = ["Playbook", "Film Room", "Player Tendencies", "Player Minutes", "Staff"]
    _co_team, _co_tab = org_sections.render_section_header(
        "Coaching", _co_tabs, subtitle="Team-level scheme, tendency, and staffing tools.")
    if _co_team:
        if _co_tab == "Player Minutes":
            render_coaching_player_minutes(_co_team)
        elif _co_tab == "Playbook":
            org_sections.coming_soon("Playbook", "real play-diagram and coach-tendency data")
        elif _co_tab == "Film Room":
            org_sections.coming_soon("Film Room", "actual game film/video, which this app has no source for")
        elif _co_tab == "Player Tendencies":
            render_coaching_player_tendencies(_co_team)
        elif _co_tab == "Staff":
            org_sections.coming_soon("Staff", "coaching-staff history and season-by-season records to analyze")
    st.stop()

elif category == "On/Off Lineup Network":
    st.title("On/Off Lineup Network")
    st.caption(
        "Pick a team and two or three teammates, and see how the team's "
        "per-48-minute stats shift with that specific group sharing the "
        "floor, compared to the team's season average."
    )

    onoff_season = st.selectbox(
        "Season:", ALL_SEASONS,
        index=0, key="onoff_season",
    )
    onoff_team_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, key="onoff_team")

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
                            # Solo (group_quantity=1) lineups are only
                            # needed for the exactly-2-player case, to
                            # compute "player1 without player2" via
                            # subtraction (player1's total on-court
                            # stats minus the together stats) --
                            # meaningless for 3 players (which
                            # combination would "without" even mean?),
                            # so skipped entirely for that case.
                            solo_lineups = (
                                get_team_lineup_combos(TEAM_NAME_TO_RECORD[onoff_team_name]["id"], onoff_season, group_quantity=1)
                                if group_size == 2 else None
                            )
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

                            if group_size == 2:
                                if solo_lineups is None:
                                    st.caption(
                                        "Couldn't load individual on-court data for this comparison "
                                        "(the group_quantity=1 lookup failed) -- only the 'together' "
                                        "column above is available this time."
                                    )
                                elif "GROUP_NAME" not in solo_lineups.columns:
                                    st.caption(
                                        "The individual on-court data came back in an unexpected "
                                        "format (no GROUP_NAME column) -- only the 'together' column "
                                        "above is available this time."
                                    )
                                else:
                                    for solo_player, other_player in [(player1, player2), (player2, player1)]:
                                        solo_last = solo_player.split()[-1].lower()
                                        solo_match = solo_lineups[solo_lineups["GROUP_NAME"].str.lower().str.contains(solo_last)]
                                        if solo_match.empty:
                                            st.caption(f"No individual on-court minutes found for {solo_player} this season -- skipping that column.")
                                            continue
                                        solo_row = solo_match.iloc[0]
                                        solo_min = solo_row.get("MIN", 0)
                                        without_min = solo_min - combo_min
                                        if without_min <= 0:
                                            st.caption(
                                                f"{solo_player}'s total on-court minutes ({solo_min:.0f}) aren't "
                                                f"greater than the time with {other_player} together ({combo_min:.0f}) -- "
                                                f"can't isolate a '{solo_player} without {other_player}' column from that."
                                            )
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
                            fig = build_onoff_column_image(onoff_team_name, columns, player_ids_lookup)
                            show_chart(fig, _hover(hover.onoff_column_hotspots, fig.axes[0], columns,
                                                   [c.get("minutes") for c in columns]), "onoff_columns")
                            add_to_tableau_dashboard(fig, "On/Off Stats", "tableau_onoff")
                            offer_share_to_community(fig, "On/Off Stats", "share_onoff")
                            plt.close(fig)

                            if group_size == 2:
                                st.caption(
                                    "The table above is team-level: how the team performs with this "
                                    "specific lineup on the floor. Individual play-by-play data (each "
                                    "player's own scoring split by whether a specific teammate is on "
                                    "or off) isn't exposed by the NBA's public stats API, so it can't "
                                    "be shown here -- what follows instead is each player's own "
                                    "season average, regardless of this specific lineup."
                                )
                                with code_loading_animation("Downloading individual season stats"):
                                    try:
                                        individual_stats = get_player_stats(onoff_season, per_mode="PerGame")
                                    except Exception:
                                        individual_stats = None
                                if individual_stats is not None and "PLAYER_NAME" in individual_stats.columns:
                                    icol1, icol2 = st.columns(2)
                                    for icol, pname in zip([icol1, icol2], [player1, player2]):
                                        with icol:
                                            prow_match = individual_stats[individual_stats["PLAYER_NAME"] == pname]
                                            if not prow_match.empty:
                                                prow = prow_match.iloc[0]
                                                st.markdown(f'<p style="color:#888; font-weight:bold;">{pname} (season avg):</p>', unsafe_allow_html=True)
                                                mc1, mc2, mc3 = st.columns(3)
                                                mc1.metric("PTS", f"{prow['PTS']:.1f}" if "PTS" in prow.index and pd.notna(prow["PTS"]) else "--")
                                                mc2.metric("REB", f"{prow['REB']:.1f}" if "REB" in prow.index and pd.notna(prow["REB"]) else "--")
                                                mc3.metric("AST", f"{prow['AST']:.1f}" if "AST" in prow.index and pd.notna(prow["AST"]) else "--")

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
        "colored by that lineup's net rating -- a wider view than picking one specific "
        "combination above, for spotting which combinations work especially well or poorly at a glance."
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
    net_criteria = st.multiselect("Add criteria:", _net_labels, key="lineup_network_criteria")
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
    net_rank_label = st.selectbox("Rank by:", _net_labels,
                                  index=_net_labels.index("Net Rating") if "Net Rating" in _net_labels else 0,
                                  key="lineup_network_rank")
    if onoff_team_name and persistent_run_button(True, key="onoff_network"):
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
            if "MIN" in all_pairs.columns:
                all_pairs = all_pairs[all_pairs["MIN"] >= min_minutes_together]
            if net_keep_groups is not None:
                all_pairs = all_pairs[all_pairs["GROUP_NAME"].astype(str).isin(net_keep_groups)]
            _rank_field, _rank_low = _net_by_label[net_rank_label]
            if _rank_field in all_pairs.columns:
                # drawn in ranked order: the best lineup by the chosen stat comes first
                all_pairs = (all_pairs.assign(_RANK_V=pd.to_numeric(all_pairs[_rank_field], errors="coerce"))
                             .sort_values("_RANK_V", ascending=_rank_low, na_position="last"))
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

            if value_col is None:
                st.error("Couldn't find a net rating or plus/minus column in the returned lineup data.")
            else:
                import itertools
                pair_labels, pair_values, pair_minutes = [], [], []
                groups_raw, group_ids = [], []
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
                            value_label=net_label, return_hotspot_data=True,
                        )
                        group_ranks = {}
                        for (group_parts, _r, _m), ids in zip(groups_raw, group_ids):
                            if ids and ids in league_rank_by_ids:
                                group_ranks[tuple(resolved_lookup.get(p, p) for p in group_parts)] = league_rank_by_ids[ids]
                        net_hotspots = _hover(hover.lineup_network_group_hotspots, net_panels, two_man_lookup, net_label,
                                              league_ranks=group_ranks)
                    show_chart(fig, net_hotspots, f"lineup_network_{lineup_size}")
                    title = f"Lineup Network -- {onoff_team_name}"
                    add_to_tableau_dashboard(fig, title, "tableau_network")
                    offer_share_to_community(fig, title, "share_network")

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
    for stat_category, stats_in_cat in get_stats_for_mode(formula_mode_key, exclude_bradley_rating=True):
        for field, label, source, modes in stats_in_cat:
            full_label = f"{label} ({stat_category})"
            all_stat_options.append((field, full_label))
            stat_label_to_spec[full_label] = (field, source)

    picked_stat_labels = st.multiselect(
        "Pick stats and advanced stats:", [label for _, label in all_stat_options], key="formula_stats",
    )

    community_formulas = community_storage.load_all_formulas()
    formula_name_to_entry = {f["name"]: f for f in community_formulas}
    picked_formula_names = st.multiselect(
        "Include community-uploaded formulas as components:",
        list(formula_name_to_entry.keys()),
        key="formula_community_picks",
        help="Formulas other people have already built and shared -- pick any to fold into your own as a single weighted component.",
    )

    if not picked_stat_labels and not picked_formula_names:
        st.info("Pick at least one stat or community formula above to start building.")
    else:
        st.markdown("##### Set each component's weight")
        st.caption("Weights always add up to 100% -- moving one slider redistributes the rest automatically.")

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
            if kind == "stat":
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

        st.markdown("##### Apply to a real player or team")
        if formula_mode_key == "player":
            apply_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.", key="formula_apply_player")
        else:
            apply_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.", key="formula_apply_team")
        apply_season = st.selectbox("Season:", ALL_SEASONS, index=0, key="formula_apply_season")

        if apply_name and persistent_run_button(True, key="formula_apply", show_chart_color=False):
            with code_loading_animation("Calculating"):
                try:
                    name_col = "PLAYER_NAME" if formula_mode_key == "player" else "TEAM_NAME"
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
                    }

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
                                dfs_by_mode[key] = get_player_stats(apply_season, per_mode=stat_mode) if formula_mode_key == "player" else get_team_stats(apply_season, per_mode=stat_mode)
                            else:
                                dfs_by_mode[key] = _side_tables[table](apply_season)
                        return dfs_by_mode[key]

                    def subject_rows(df):
                        if formula_mode_key == "player":
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
                                st.warning(f"{comp['label']} isn't available for {apply_name} in {apply_season} -- skipped.")
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
                        st.metric(f"{apply_name} -- {apply_season} formula rating", f"{total:.1f}")
                        st.caption("Rating is a 0-100 scale based on each stat's percentile rank across the full league that season -- 100 means best in the league, 50 means the middle of the pack.")
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
                            return f"{mode_used}" if table == "league" else table.replace("_", " ")
                        sample_note = ", ".join(
                            f"{len(dfs_by_mode[k])} {'players' if formula_mode_key == 'player' else 'teams'} ({_table_label(k)})"
                            for k in dfs_by_mode
                        )
                        gp_note = ""
                        league_keys = [k for k in dfs_by_mode if k[0] == "league"]
                        if league_keys:
                            gp_rows = subject_rows(dfs_by_mode[league_keys[0]])
                            if not gp_rows.empty and "GP" in gp_rows.columns and pd.notna(gp_rows.iloc[0].get("GP")):
                                gp_note = f" -- {apply_name} has played {int(gp_rows.iloc[0]['GP'])} games in {apply_season}"
                        st.caption(f"Computed against: {sample_note}{gp_note}.")
                        with st.expander("Breakdown"):
                            for label, raw_value, pct, weight, contribution in breakdown:
                                if raw_value is None:
                                    st.write(f"{label}: {pct:.1f} percentile x {weight:g} = {contribution:.1f}")
                                else:
                                    st.write(f"{label}: {raw_value:,.2f} ({pct:.1f} percentile) x {weight:g} = {contribution:.1f}")
                except Exception as e:
                    st.error(f"Couldn't calculate this formula: {e}")

        st.markdown("##### Share this formula")
        formula_share_desc = st.text_area("Description:", key="formula_share_desc")
        if st.button("Share to the \"Community Uploads\" page", key="formula_share_btn"):
            if not formula_share_name.strip():
                st.warning("Give your formula a name first.")
            else:
                community_storage.save_formula(formula_share_name.strip(), formula_share_desc.strip(), components)
                st.success("Posted -- also appears on the Community Uploads page.")
                _community_backup_notice()

    st.markdown("---")
    st.markdown("#### Community Formulas")
    st.caption("Every formula shared here so far -- browse for inspiration or to reuse as a component above.")
    gallery_formulas = community_storage.load_all_formulas()
    if not gallery_formulas:
        st.write("No formulas shared yet -- be the first.")
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
        "neighbor -- true mouse drag-and-drop isn't something plain "
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
        st.markdown("Nothing shared yet -- be the first.")
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
    st.caption("Every stat abbreviation used throughout this dashboard, in one place.")
    glossary_terms = [
        ("FGA", "Field Goals Attempted -- total shots taken from the field (not counting free throws)."),
        ("FGM", "Field Goals Made -- shots that went in, from the field."),
        ("FG%", "Field Goal Percentage -- FGM divided by FGA."),
        ("3PA", "3-Point Attempts -- shots taken from beyond the 3-point line."),
        ("3PM", "3-Pointers Made."),
        ("3P%", "3-Point Percentage -- 3PM divided by 3PA."),
        ("PTS", "Points scored."),
        ("REB", "Rebounds -- offensive and defensive combined."),
        ("AST", "Assists."),
        ("STL", "Steals."),
        ("BLK", "Blocks."),
        ("TOV", "Turnovers."),
        ("TS%", "True Shooting Percentage -- shooting efficiency that accounts for the extra value of 3-pointers and free throws, not just field goals."),
        ("USG%", "Usage Rate -- the share of a team's offensive possessions a player uses while on the floor."),
        ("PER", "Player Efficiency Rating -- a single-number summary of a player's per-minute statistical production."),
    ]
    for term, definition in glossary_terms:
        st.markdown(f"**{term}** -- {definition}")
    st.stop()




mode = "player" if category == "Search by Player" else "team"
st.title(category)


# ---------------------------------------------------------------- Step 2: Visualization
# GAME_LOG_GRAPHS and most of COMPARISON_GRAPHS only offered in player
# mode -- get_player_game_log() is player-specific, and Waterfall/
# Combo/Tornado/Radar/Slope are all built around a specific player's
# own numbers, so offering them under Search by Team would be a dead
# end that always errors. Head-to-Head is the one exception: it
# genuinely works for both (its own branch already fetches
# get_team_stats() when mode == "team"), so it's split out into its
# own always-offered list rather than being gated with the rest.
BOTH_MODE_COMPARISON_GRAPHS = [
    'Head-to-Head', 'Waterfall Chart', 'Tornado Chart', 'Radar Chart',
    'Shot Flow (Sankey)', 'Court + Radar Hybrid', 'Small Multiples', 'Bump Chart',
    'Combo Chart', 'Calendar Heat Map', 'Impact Clock',
]
PLAYER_ONLY_COMPARISON_GRAPHS = [g for g in COMPARISON_GRAPHS if g not in BOTH_MODE_COMPARISON_GRAPHS]
# Box Plot shows every team's roster spread on a stat -- shows up only
# under Search by Team, since "every team" doesn't have an equivalent
# meaning for a single selected player.
TEAM_ONLY_AXIS_GRAPHS = ['Box Plot']
all_visualizations_unfiltered = (
    COURT_GRAPHS + AXIS_GRAPHS + ANIMATED_GRAPHS + BOTH_MODE_COMPARISON_GRAPHS
    + (GAME_LOG_GRAPHS + PLAYER_ONLY_COMPARISON_GRAPHS if mode == "player" else TEAM_ONLY_AXIS_GRAPHS)
)

# Dot Plot and Density Plot are internal display modes of Bar Chart and
# Histogram now, not their own selectable entries -- excluded from the
# mode-filtered list above before it's split into the 3 top-level
# categories below, so they never show up as their own option anywhere.
all_visualizations_unfiltered = [v for v in all_visualizations_unfiltered if v not in ("Dot Plot", "Density Plot", "Momentum Chart")]

viz_category_labels = [
    ("Team Comparison" if mode == "team" and cat == "Player Comparison" else cat)
    for cat in VIZ_CATEGORIES.keys()
] + ["Lineup Network"]
viz_category_display = st.radio(
    "Visualization Category:",
    viz_category_labels,
    horizontal=True,
    key="viz_category",
)
if viz_category_display == "Lineup Network":
    # Not a real category with its own visualizations -- a shortcut
    # that jumps to the actual Two-Man Lineup Network section, which
    # lives on the On/Off Stats page, explicitly requested rather than
    # duplicating that section's own logic here. Uses del (not
    # assignment) to reset this widget's own already-instantiated
    # state, and the existing nav_to() helper (not a direct assignment
    # to category_radio, also already instantiated) for the same
    # confirmed reason: Streamlit blocks direct assignment to a
    # widget-backed session_state key once that widget already exists
    # in the current run, but both deletion and nav_to()'s own
    # pending-flag-plus-rerun pattern are exceptions to that.
    del st.session_state["viz_category"]
    st.session_state["_scroll_to_lineup_network"] = True
    nav_to("On/Off Lineup Network")
# Translates the (possibly renamed) displayed label back to the
# original VIZ_CATEGORIES key -- "Team Comparison" only exists as a
# display-time relabeling of "Player Comparison" for team mode, not a
# separate category with its own contents.
viz_category = "Player Comparison" if viz_category_display == "Team Comparison" else viz_category_display
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
    "Small Multiples": "Shot Chart Comparison",
    "Bump Chart": "Multi-Season Bump Chart",
    "Slope Chart": "Multi-Season Slope Chart",
    "Histogram": "League Average Histogram",
    "Cumulative Distribution Plot": "Cumulative Percentile Plot",
}

visualization = st.selectbox(
    "Visualization:",
    all_visualizations,
    index=None,
    placeholder="Choose visualization.",
    format_func=lambda v: VIZ_DISPLAY_NAMES.get(v, v),
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
is_head_to_head = visualization == "Head-to-Head"
is_calendar_heat_map = visualization == "Calendar Heat Map"
is_small_multiples = visualization == "Small Multiples"
is_court_radar_hybrid = visualization == "Court + Radar Hybrid"
is_sankey_flow = visualization == "Shot Flow (Sankey)"
is_impact_clock = visualization == "Impact Clock"
is_bump_chart = visualization == "Bump Chart"
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
if _needs_stat_mode:
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
                st.caption("Couldn't load this player's exact career span -- showing recent seasons instead.")

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
                    st.warning("This player's career ended before shot-location data was tracked (1996-97) -- no court visualization is possible for them.")

            season = st.selectbox(
                "Season:", real_seasons,
                index=0,
            )
        else:
            season = None

    else:
        team_query = st.selectbox(
            "Team:", ALL_TEAM_NAMES, index=None,
            placeholder="Enter team name.",
        )
        if team_query:
            season = st.selectbox(
                "Season:", ALL_SEASONS,
                index=0,
            )
        else:
            season = None
        player_id = None

    if season:
        if not is_scatter_plot:
            subject_name = picked_name if mode == "player" else team_query
            default_team = _default_color_team(mode, subject_name, season)
            color_input = color_input_with_dropdown(f"court_color_box_{mode}_{subject_name}_{season}", default_team)
        else:
            color_input = None
    else:
        color_input = None

    ready_to_run = bool(season) and (is_scatter_plot or bool(color_input))

    if ready_to_run:
        run = persistent_run_button(True, key=visualization)
    else:
        run = False

    if run:
        if mode == "player" and player_id:
            with code_loading_animation("Downloading shot data"):
                shots = get_player_shots(player_id, season)

            team_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR

            if visualization == "Shot Chart":
                fig = build_shot_chart(shots, team_color)
                show_chart(fig, _hover(hover.shot_chart_hotspots, fig.axes[0], shots,
                                       _game_lookup("player", player_id, season), False), "shot_chart")
                add_to_tableau_dashboard(fig, f"Search by {mode.capitalize()} -- Shot Chart", "tableau_shot_chart")
                offer_share_to_community(fig, f"Search by {mode.capitalize()} -- Shot Chart", "share_shot_chart")
            elif visualization == "Heat Map":
                fig = build_heat_map(shots, team_color)
                show_chart(fig, _hover(hover.heat_map_hotspots, fig.axes[0], shots,
                                       get_zone_league_averages(season, player_id=player_id),
                                       _last_name(picked_name)), "heat_map")
                add_to_tableau_dashboard(fig, f"Search by {mode.capitalize()} -- Heat Map", "tableau_heat_map")
                offer_share_to_community(fig, f"Search by {mode.capitalize()} -- Heat Map", "share_heat_map")
            elif visualization == "Hex Shot Chart":
                with code_loading_animation("Downloading league-wide comparison data"):
                    league_shots = get_league_shots(season)
                fig, hex_records = build_hex_shot_chart(shots, league_shots, team_color, return_hotspot_data=True)
                show_chart(fig, _hover(hover.hex_chart_hotspots, fig.axes[0], hex_records, _last_name(picked_name)),
                           "hex_chart")
                add_to_tableau_dashboard(fig, f"Search by {mode.capitalize()} -- Hex Shot Chart", "tableau_hex_chart")
                offer_share_to_community(fig, f"Search by {mode.capitalize()} -- Hex Shot Chart", "share_hex_chart")
            elif visualization == "Animated Shot Chart":
                with code_loading_animation("Building animation -- this takes a little longer"):
                    gif_buffer = build_animated_shot_chart(shots, team_color)
                st.image(gif_buffer)
                add_to_tableau_dashboard(gif_buffer, f"Search by {mode.capitalize()} -- Animated Shot Chart", "tableau_animated_chart")
                offer_share_to_community(gif_buffer, f"Search by {mode.capitalize()} -- Animated Shot Chart", "share_animated_chart")
            elif visualization == "Court Zone Map":
                fig = build_court_zone_map(shots, picked_name)
                st.pyplot(fig)
                add_to_tableau_dashboard(fig, f"Search by {mode.capitalize()} -- Court Zone Map", "tableau_zone_map")
                offer_share_to_community(fig, f"Search by {mode.capitalize()} -- Court Zone Map", "share_zone_map")
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
                add_to_tableau_dashboard(fig, "Search by Team -- Shot Chart", "tableau_team_shot_chart")
                offer_share_to_community(fig, "Search by Team -- Shot Chart", "share_team_shot_chart")
            elif visualization == "Heat Map":
                fig = build_heat_map(shots, team_color)
                show_chart(fig, _hover(hover.heat_map_hotspots, fig.axes[0], shots,
                                       get_zone_league_averages(season, team_id=_team_id), _team_short),
                           "team_heat_map")
                add_to_tableau_dashboard(fig, "Search by Team -- Heat Map", "tableau_team_heat_map")
                offer_share_to_community(fig, "Search by Team -- Heat Map", "share_team_heat_map")
            elif visualization == "Hex Shot Chart":
                with code_loading_animation("Downloading league-wide comparison data"):
                    league_shots = get_league_shots(season)
                fig, hex_records = build_hex_shot_chart(shots, league_shots, team_color, return_hotspot_data=True)
                show_chart(fig, _hover(hover.hex_chart_hotspots, fig.axes[0], hex_records, _team_short), "team_hex_chart")
                add_to_tableau_dashboard(fig, "Search by Team -- Hex Shot Chart", "tableau_team_hex_chart")
                offer_share_to_community(fig, "Search by Team -- Hex Shot Chart", "share_team_hex_chart")
            elif visualization == "Animated Shot Chart":
                with code_loading_animation("Building animation -- this takes a little longer"):
                    gif_buffer = build_animated_shot_chart(shots, team_color)
                st.image(gif_buffer)
                add_to_tableau_dashboard(gif_buffer, "Search by Team -- Animated Shot Chart", "tableau_team_animated_chart")
                offer_share_to_community(gif_buffer, "Search by Team -- Animated Shot Chart", "share_team_animated_chart")
            elif visualization == "Court Zone Map":
                fig = build_court_zone_map(shots, f"{team_query}")
                st.pyplot(fig)
                add_to_tableau_dashboard(fig, "Search by Team -- Court Zone Map", "tableau_team_zone_map")
                offer_share_to_community(fig, "Search by Team -- Court Zone Map", "share_team_zone_map")
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

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    chosen_category = st.selectbox("Stat category:", category_names)

    stats_in_category = dict(categories)[chosen_category]
    stat_labels = [label for _, label, _, _ in stats_in_category]
    chosen_stat_label = st.selectbox("Stat:", stat_labels)

    chosen_stat = next(s for s in stats_in_category if s[1] == chosen_stat_label)
    stat_field = chosen_stat[0]

    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)

    view_mode = st.radio("View:", ["Game-by-game", "Cumulative running total", "Momentum (hot/cold streaks)"], horizontal=True)
    rolling_window = 0
    filled = False
    if view_mode == "Game-by-game":
        rolling_window = st.number_input("Rolling average window (0 = off):", min_value=0, max_value=20, value=5)
    elif view_mode == "Cumulative running total":
        filled = st.checkbox("Fill area below the line", value=True)
    else:
        st.caption(
            "Adapted to game-to-game momentum across a season (hot/cold streaks), since play-by-play "
            "data isn't available from this data source to track momentum minute-by-minute within a "
            "single game."
        )

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
                "(bradley_ratings.py), which isn't ported to the dashboard yet -- "
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
                    "season-level only) -- try a base counting stat like Points, Rebounds, or Assists."
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
                add_to_tableau_dashboard(fig, f"Line Chart -- {picked_name}", "tableau_line_chart")
                offer_share_to_community(fig, f"Line Chart -- {picked_name}", "share_line_chart")


elif is_waterfall_chart:

    if mode == "player":
        picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    else:
        picked_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.")
    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
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
                                   [ftm * 1, fg2m * 2, fg3m * 3], [ftm, fg2m, fg3m], [_fta, _fga - _fg3a, _fg3a]),
                       "waterfall")
            add_to_tableau_dashboard(fig, f"Waterfall -- {picked_name}", "tableau_waterfall")
            offer_share_to_community(fig, f"Waterfall -- {picked_name}", "share_waterfall")


# ---------------------------------------------------------------- Branch: Combo Chart
elif is_combo_chart:

    if mode == "player":
        picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
        subject_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    else:
        picked_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.")
        subject_id = TEAM_NAME_TO_RECORD[picked_name]["id"] if picked_name else None

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    bar_category = st.selectbox("Bar stat category (volume stat):", category_names, key="combo_bar_cat")
    bar_stats_in_cat = dict(categories)[bar_category]
    bar_label_choice = st.selectbox("Bar stat:", [label for _, label, _, _ in bar_stats_in_cat], key="combo_bar_stat")

    # The bar color auto-follows the current Chart Color (White/Black)
    # setting -- white by default, automatically switching to black if
    # Chart Color is Black -- but only while the user hasn't manually
    # picked a bar color themselves. A tracking flag (the last
    # auto-assigned value) distinguishes "still on the auto default"
    # from "user deliberately chose this," since once someone picks a
    # color it should stay exactly as they set it regardless of
    # Chart Color.
    bar_color_key = f"combo_color_box_{mode}"
    chart_color_widget_key = f"combo_chart_color_{mode}"
    if bar_color_key not in st.session_state:
        st.session_state[f"{bar_color_key}_auto_value"] = "White"
    current_chart_color_default = st.session_state.get(f"{bar_color_key}_auto_value", "White")
    color_input = color_input_with_dropdown(bar_color_key, default_team=current_chart_color_default, show_text_color_toggle=False, label="Bar Color:")

    line_category = st.selectbox("Line stat category (rate stat):", category_names, key="combo_line_cat")
    line_stats_in_cat = dict(categories)[line_category]
    line_label_choice = st.selectbox("Line stat:", [label for _, label, _, _ in line_stats_in_cat], key="combo_line_stat")
    line_color_input = color_input_with_dropdown(f"combo_line_color_box_{mode}", default_team="Gold", show_text_color_toggle=False, label="Line Color:")

    # Chart Color comes last, after both color pickers, matching the
    # exact requested header order -- each color_input_with_dropdown()
    # call would otherwise render its own copy of this toggle
    # immediately after itself, attaching it to the first color picker
    # instead of standing alone at the end.
    def _on_chart_color_change(mode_for_callback, bar_key):
        new_default = "Black" if st.session_state[f"combo_chart_color_{mode_for_callback}"] == "Black" else "White"
        last_auto = st.session_state.get(f"{bar_key}_auto_value", "White")
        if st.session_state.get(bar_key) == last_auto:
            # Still on the auto-assigned default (untouched by the
            # user) -- safe to follow Chart Color. If the user has
            # picked something else, leave it alone entirely.
            st.session_state[bar_key] = new_default
        st.session_state[f"{bar_key}_auto_value"] = new_default

    combo_text_color_choice = st.radio(
        "Chart Color:", ["White", "Black"], key=f"combo_chart_color_{mode}", horizontal=True,
        on_change=_on_chart_color_change, args=(mode, bar_color_key),
    )
    st.session_state["_global_chart_text_color"] = "black" if combo_text_color_choice == "Black" else "white"

    run = persistent_run_button(bool(picked_name), key=visualization, show_chart_color=False)

    if run:
        bar_stat = next(s for s in bar_stats_in_cat if s[1] == bar_label_choice)
        line_stat = next(s for s in line_stats_in_cat if s[1] == line_label_choice)

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
                seasons = ALL_SEASONS[:15]

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
                    add_to_tableau_dashboard(fig, f"Combo Chart -- {picked_name}", "tableau_combo")
                    offer_share_to_community(fig, f"Combo Chart -- {picked_name}", "share_combo")


# ---------------------------------------------------------------- Branch: Tornado Chart
elif is_tornado_chart:

    if mode == "player":
        picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    else:
        picked_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.")

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    chosen_category = st.selectbox("Stat category:", category_names)
    stats_in_category = dict(categories)[chosen_category]
    chosen_labels = st.multiselect(
        "Stats to compare against league average:", [label for _, label, _, _ in stats_in_category],
        default=[label for _, label, _, _ in stats_in_category][:5],
    )
    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
    default_team = _default_color_team(mode, picked_name, season)
    color_input = color_input_with_dropdown(f"tornado_color_box_{mode}_{picked_name}_{season}", default_team)

    run = persistent_run_button((season and picked_name and chosen_labels), key=visualization)

    if run:
        chosen_stats = [s for s in stats_in_category if s[1] in chosen_labels]
        eligible = [s for s in chosen_stats if s[2] in ("base", "advanced", "calculated")]
        skipped = [s[1] for s in chosen_stats if s not in eligible]
        if skipped:
            st.caption(f"Skipped (not available for direct league-average comparison): {', '.join(skipped)}")

        if not eligible:
            st.warning("None of the selected stats can be compared this way -- pick base/advanced/calculated stats.")
        else:
            with code_loading_animation("Downloading stats"):
                stats_df = get_player_stats(season, per_mode=shared_per_mode) if mode == "player" else get_team_stats(season, per_mode=shared_per_mode)

            name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
            subject_row = stats_df[stats_df[name_col] == picked_name]
            if subject_row.empty:
                st.error(f"No stats found for {picked_name} in {season}.")
            else:
                labels, diffs, any_pct = [], [], False
                subject_vals, league_avgs, pct_flags = [], [], []
                for field, label, _, _ in eligible:
                    if field in stats_df.columns:
                        league_avg = stats_df[field].mean()
                        subject_val = float(subject_row.iloc[0][field])
                        labels.append(label.split(" (")[0])
                        diffs.append(subject_val - league_avg)
                        subject_vals.append(subject_val)
                        league_avgs.append(float(league_avg))
                        pct_flags.append(field.endswith("_PCT"))
                        if field.endswith("_PCT"):
                            any_pct = True

                tornado_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                fig = build_tornado_chart(labels, diffs, picked_name, tornado_color, is_percentage=False,
                                           image_url=_subject_image_url(mode, picked_name))
                show_chart(fig, _hover(hover.tornado_hotspots, fig.axes[0], labels, subject_vals, league_avgs,
                                       pct_flags), "tornado")
                add_to_tableau_dashboard(fig, f"Tornado -- {picked_name}", "tableau_tornado")
                offer_share_to_community(fig, f"Tornado -- {picked_name}", "share_tornado")


# ---------------------------------------------------------------- Branch: Slope Chart
elif is_slope_chart:

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    chosen_category = st.selectbox("Stat category:", category_names)
    stats_in_category = dict(categories)[chosen_category]
    chosen_stat_label = st.selectbox("Stat:", [label for _, label, _, _ in stats_in_category])
    chosen_stat = next(s for s in stats_in_category if s[1] == chosen_stat_label)

    col1, col2 = st.columns(2)
    with col1:
        before_season = st.selectbox("Before Season:", ALL_SEASONS, index=0, key="slope_before_season")
    with col2:
        after_season = st.selectbox("After Season:", ALL_SEASONS, index=0, key="slope_after_season")

    included_input = st.text_input(
        f"Enter {'player' if mode == 'player' else 'team'}(s) to compare (comma separated):"
    )
    top_n = st.number_input("Or show top __ by the after-season value (used if no names entered):", min_value=1, max_value=30, value=8)
    slope_rank_ascending = rank_direction_control(chosen_stat[0], "slope")
    color_input = color_input_with_dropdown("slope_color_box")

    run = persistent_run_button((before_season and after_season), key=visualization)

    if run:
        stat_field = chosen_stat[0]
        if chosen_stat[2] == "bradley_rating":
            st.warning("Bradley Rating stats aren't available for this comparison yet.")
        else:
            with code_loading_animation("Downloading both seasons"):
                if mode == "player":
                    before_df = get_player_stats(before_season, per_mode=shared_per_mode)
                    after_df = get_player_stats(after_season, per_mode=shared_per_mode)
                else:
                    before_df = get_team_stats(before_season, per_mode=shared_per_mode)
                    after_df = get_team_stats(after_season, per_mode=shared_per_mode)

            name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
            if stat_field not in before_df.columns or stat_field not in after_df.columns:
                st.error(f"Couldn't find {chosen_stat_label} in the returned stats.")
            else:
                merged = before_df[[name_col, stat_field]].merge(
                    after_df[[name_col, stat_field]], on=name_col, suffixes=("_before", "_after"),
                )
                merged[f"{stat_field}_after"] = pd.to_numeric(merged[f"{stat_field}_after"], errors="coerce")
                merged[f"{stat_field}_before"] = pd.to_numeric(merged[f"{stat_field}_before"], errors="coerce")
                merged = merged.dropna(subset=[f"{stat_field}_after", f"{stat_field}_before"])
                included_names = [n.strip() for n in included_input.split(",") if n.strip()] if included_input else []
                if included_names:
                    merged = merged[merged[name_col].isin(included_names)]
                else:
                    merged = (merged.nsmallest(int(top_n), f"{stat_field}_after") if slope_rank_ascending
                              else merged.nlargest(int(top_n), f"{stat_field}_after"))

                if merged.empty:
                    st.warning("No matching entries found across both seasons.")
                else:
                    is_pct = stat_field.endswith("_PCT")
                    slope_color = resolve_color_input(color_input) or DEFAULT_COLOR
                    fig = build_slope_chart(
                        merged[name_col].tolist(), merged[f"{stat_field}_before"].tolist(),
                        merged[f"{stat_field}_after"].tolist(), before_season, after_season,
                        chosen_stat_label, slope_color, is_percentage=is_pct,
                        highlight_names=included_names,
                    )
                    st.pyplot(fig)
                    add_to_tableau_dashboard(fig, "Slope Chart", "tableau_slope")
                    offer_share_to_community(fig, "Slope Chart", "share_slope")



# ---------------------------------------------------------------- Branch: Bar Chart
# ---------------------------------------------------------------- Branch: Radar Chart
elif is_radar_chart:

    names_list = ALL_PLAYER_NAMES if mode == "player" else ALL_TEAM_NAMES
    picked_name = st.selectbox(
        f"{'Player' if mode == 'player' else 'Team'}:", names_list, index=None, placeholder="Enter name.",
    )

    compare_toggle = st.checkbox(f"Compare against a second {'player' if mode == 'player' else 'team'}")
    second_name = None
    if compare_toggle:
        second_name = st.selectbox(
            f"Second {'player' if mode == 'player' else 'team'}:", names_list, index=None,
            placeholder="Enter name.", key="radar_p2",
        )

    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
    default_team = _default_color_team(mode, picked_name, season)
    color_input = color_input_with_dropdown(f"radar_color_box_{mode}_{picked_name}_{season}", default_team)

    run = persistent_run_button((season and picked_name and (not compare_toggle or second_name)), key=visualization)

    if run:
        with code_loading_animation("Downloading stats"):
            stats_df = get_player_stats(season, per_mode=shared_per_mode) if mode == "player" else get_team_stats(season, per_mode=shared_per_mode)

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
        if not required_cols.issubset(stats_df.columns):
            st.error("Couldn't find all the stats this profile needs in the returned data.")
        else:
            stats_df = stats_df.copy()
            stats_df["_DEFENSE_COMBO"] = stats_df["STL"] + stats_df["BLK"]

            def subject_percentiles(name):
                row = stats_df[stats_df[name_col] == name]
                if row.empty:
                    return None
                percentiles = []
                for _, field in radar_categories:
                    col = "_DEFENSE_COMBO" if field is None else field
                    pct_rank = float((stats_df[col] < row.iloc[0][col]).mean() * 100)
                    percentiles.append(pct_rank)
                return percentiles

            p1_percentiles = subject_percentiles(picked_name)
            if p1_percentiles is None:
                st.error(f"No stats found for {picked_name} in {season}.")
            else:
                p2_percentiles = subject_percentiles(second_name) if second_name else None
                if second_name and p2_percentiles is None:
                    st.warning(f"No stats found for {second_name} in {season} -- showing {picked_name} alone.")

                radar_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                fig = build_radar_chart(
                    [c for c, _ in radar_categories], p1_percentiles, picked_name, radar_color,
                    second_percentiles=p2_percentiles, second_name=second_name,
                    image_url=_subject_image_url(mode, picked_name),
                    second_image_url=_subject_image_url(mode, second_name) if p2_percentiles else None,
                )
                _r = stats_df[stats_df[name_col] == picked_name].iloc[0]
                _radar_lines = [
                    [f"{_r['PTS']:.1f} PTS"], [f"{_r['AST']:.1f} AST"], [f"{_r['REB']:.1f} REB"],
                    [f"{_r['STL']:.1f} STL + {_r['BLK']:.1f} BLK"], [f"{_r['TS_PCT']:.1%} TS%"],
                ]
                show_chart(fig, _hover(hover.radar_hotspots, fig.axes[0], [c for c, _ in radar_categories],
                                       p1_percentiles, _radar_lines), "radar")
                title = f"Radar -- {picked_name}" + (f" vs {second_name}" if p2_percentiles else "")
                add_to_tableau_dashboard(fig, title, "tableau_radar")
                offer_share_to_community(fig, title, "share_radar")



# ---------------------------------------------------------------- Branch: Bar Chart
# ---------------------------------------------------------------- Branch: Head-to-Head
elif is_head_to_head:

    picked_name = st.selectbox(
        f"{'Player' if mode == 'player' else 'Team'} A:", ALL_PLAYER_NAMES if mode == "player" else ALL_TEAM_NAMES,
        index=None, placeholder="Enter name.",
    )
    second_name = st.selectbox(
        f"{'Player' if mode == 'player' else 'Team'} B:", ALL_PLAYER_NAMES if mode == "player" else ALL_TEAM_NAMES,
        index=None, placeholder="Enter name.", key="h2h_second",
    )
    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
    default_team_a = _default_color_team(mode, picked_name, season)
    default_team_b = _default_color_team(mode, second_name, season)
    color_input_a = color_input_with_dropdown(f"h2h_color_a_{mode}_{picked_name}_{season}", default_team_a, show_text_color_toggle=False)
    color_input_b = color_input_with_dropdown(f"h2h_color_b_{mode}_{second_name}_{season}", default_team_b)

    run = persistent_run_button((season and picked_name and second_name), key=visualization)

    if run:
        with code_loading_animation("Downloading stats"):
            stats_df = get_player_stats(season, per_mode=shared_per_mode) if mode == "player" else get_team_stats(season, per_mode=shared_per_mode)

        name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
        row_a = stats_df[stats_df[name_col] == picked_name]
        row_b = stats_df[stats_df[name_col] == second_name]

        if row_a.empty or row_b.empty:
            st.error("Couldn't find stats for one or both -- try a different season.")
        else:
            row_a, row_b = row_a.iloc[0], row_b.iloc[0]
            # A standard full box-score comparison -- matches the spec's
            # own framing ("full box score comparison, advanced stat
            # comparison") rather than a single custom-picked stat.
            h2h_stats = [
                ("PTS", "PTS", False), ("REB", "REB", False), ("AST", "AST", False),
                ("STL", "STL", False), ("BLK", "BLK", False), ("TOV", "TOV", False),
                ("FG%", "FG_PCT", True), ("3P%", "FG3_PCT", True), ("FT%", "FT_PCT", True),
                ("TS%", "TS_PCT", True), ("USG%", "USG_PCT", True), ("PLUS_MINUS", "PLUS_MINUS", False),
            ]
            table_rows = []
            for label, field, is_pct in h2h_stats:
                val_a = float(row_a[field]) if field in row_a.index and pd.notna(row_a[field]) else None
                val_b = float(row_b[field]) if field in row_b.index and pd.notna(row_b[field]) else None
                if val_a is not None or val_b is not None:
                    table_rows.append((label, val_a, val_b, is_pct))

            color_a = resolve_color_input(color_input_a) or DEFAULT_COLOR
            color_b = resolve_color_input(color_input_b) or "#B5B5B5"
            if mode == "player":
                image_url_a = get_player_headshot_url(PLAYER_NAME_TO_RECORD[picked_name]["id"])
                image_url_b = get_player_headshot_url(PLAYER_NAME_TO_RECORD[second_name]["id"])
            else:
                image_url_a = get_team_logo_url(TEAM_NAME_TO_RECORD[picked_name]["id"])
                image_url_b = get_team_logo_url(TEAM_NAME_TO_RECORD[second_name]["id"])
            fig = build_head_to_head_table(picked_name, second_name, table_rows, color_a, color_b,
                                            image_url_a=image_url_a, image_url_b=image_url_b)
            st.pyplot(fig)
            title = f"Head-to-Head -- {picked_name} vs {second_name}"
            add_to_tableau_dashboard(fig, title, "tableau_h2h")
            offer_share_to_community(fig, title, "share_h2h")



# ---------------------------------------------------------------- Branch: Bar Chart
# ---------------------------------------------------------------- Branch: Calendar Heat Map
elif is_calendar_heat_map:

    if mode == "player":
        picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
        subject_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    else:
        picked_name = st.selectbox("Team:", ALL_TEAM_NAMES, index=None, placeholder="Enter team name.")
        subject_id = TEAM_NAME_TO_RECORD[picked_name]["id"] if picked_name else None

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    chosen_category = st.selectbox("Stat category:", category_names)
    stats_in_category = dict(categories)[chosen_category]
    chosen_stat_label = st.selectbox("Stat:", [label for _, label, _, _ in stats_in_category])
    chosen_stat = next(s for s in stats_in_category if s[1] == chosen_stat_label)

    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
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
                    "season-level only) -- try a base counting stat like Points, Rebounds, or Assists."
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
                add_to_tableau_dashboard(fig, f"Calendar -- {picked_name}", "tableau_calendar")
                offer_share_to_community(fig, f"Calendar -- {picked_name}", "share_calendar")


# ---------------------------------------------------------------- Branch: Small Multiples
elif is_small_multiples:

    if mode == "player":
        picked_names = st.multiselect("Players (up to 9):", ALL_PLAYER_NAMES, max_selections=9)
    else:
        picked_names = st.multiselect("Teams (up to 9):", ALL_TEAM_NAMES, max_selections=9)
    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    color_input = color_input_with_dropdown(f"smallmult_color_box_{mode}")

    run = persistent_run_button((season and len(picked_names) >= 2), key=visualization)

    if run:
        subjects_shots = []
        noun = "players" if mode == "player" else "teams"
        with code_loading_animation(f"Downloading shots for {len(picked_names)} {noun}"):
            for name in picked_names:
                if mode == "player":
                    subject_id = PLAYER_NAME_TO_RECORD[name]["id"]
                    shots = get_player_shots(subject_id, season)
                else:
                    subject_id = TEAM_NAME_TO_RECORD[name]["id"]
                    shots = get_team_shots(subject_id, season)
                if not shots.empty:
                    subjects_shots.append((name, shots))

        if not subjects_shots:
            st.error(f"No shot data found for any of the selected {noun} in that season.")
        else:
            sm_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
            fig = build_small_multiples_shot_charts(subjects_shots, sm_color)
            st.pyplot(fig)
            title = f"Small Multiples -- {len(subjects_shots)} {noun.capitalize()}"
            add_to_tableau_dashboard(fig, title, "tableau_small_multiples")
            offer_share_to_community(fig, title, "share_small_multiples")


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
            title = f"Court + Radar Hybrid -- {picked_name}"
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
    default_team = _default_color_team(mode, picked_name, season)
    color_input = color_input_with_dropdown(f"sankey_color_box_{mode}_{picked_name}_{season}", default_team)
    st.caption(
        "Shows how shot attempts split by zone, then by outcome -- a scoped-down version of "
        "the fuller \"possession -> play type -> shot type -> outcome\" flow, since play-type-level "
        "possession data isn't available from this data source; zone-to-outcome is."
    )

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
            title = f"Shot Flow -- {picked_name}"
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
    default_team = _default_color_team(mode, picked_name, season)
    color_input = color_input_with_dropdown(f"impactclock_color_box_{mode}_{picked_name}_{season}", default_team)
    st.caption(
        f"Shows which quarter of the game this {'player' if mode == 'player' else 'team'} is most productive in this "
        "season, using each quarter's own per-game stat splits."
    )

    run = persistent_run_button((season and picked_name), key=visualization)

    if run:
        with code_loading_animation("Downloading quarter-by-quarter stats"):
            by_quarter = (get_player_stats_by_quarter(subject_id, season) if mode == "player"
                          else get_team_stats_by_quarter(subject_id, season))

        if by_quarter.empty or len(by_quarter) < 4:
            st.error(
                f"Couldn't load complete quarter-by-quarter data for {picked_name} in {season} "
                "-- this needs all 4 quarters' splits to be available."
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
            title = f"Impact Clock -- {picked_name}"
            add_to_tableau_dashboard(fig, title, f"tableau_impact_clock_{mode}")
            offer_share_to_community(fig, title, f"share_impact_clock_{mode}")


# ---------------------------------------------------------------- Branch: Bump Chart
elif is_bump_chart:

    names_list = ALL_PLAYER_NAMES if mode == "player" else ALL_TEAM_NAMES
    picked_names = st.multiselect(
        f"{'Players' if mode == 'player' else 'Teams'} to track (2-6):", names_list, max_selections=6,
    )

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    chosen_category = st.selectbox("Stat category:", category_names)
    stats_in_category = dict(categories)[chosen_category]
    chosen_stat_label = st.selectbox("Stat:", [label for _, label, _, _ in stats_in_category])
    chosen_stat = next(s for s in stats_in_category if s[1] == chosen_stat_label)

    c1, c2 = st.columns(2)
    most_recent_season = c1.selectbox("Most Recent Season:", ALL_SEASONS, index=0, key="bump_most_recent_season")
    n_seasons = c2.number_input("Number of seasons back:", min_value=2, max_value=10, value=5)
    st.caption(
        "Adapted to season-to-season league rank, since weekly-binned league-wide rank data isn't "
        "available from this data source the way single-season snapshots are."
    )
    color_input = color_input_with_dropdown(f"bump_color_box_{mode}")

    run = persistent_run_button((most_recent_season and len(picked_names) >= 2), key=visualization)

    if run:
        stat_field = chosen_stat[0]
        if chosen_stat[2] == "bradley_rating":
            st.warning("Bradley Rating stats aren't available for this comparison yet.")
        else:
            try:
                start_year = int(most_recent_season.split("-")[0])
            except (ValueError, IndexError):
                start_year = None

            if start_year is None:
                st.error("Couldn't parse that season -- use the YYYY-YY format, e.g. 2025-26.")
            else:
                season_list = [f"{start_year - i}-{str((start_year - i + 1))[-2:]}" for i in range(int(n_seasons))]
                season_list = season_list[::-1]  # oldest first, for a left-to-right chart

                entity_ranks = {name: [] for name in picked_names}
                name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
                any_missing = False
                with code_loading_animation(f"Downloading {len(season_list)} seasons of league-wide stats"):
                    for s in season_list:
                        s_df = get_player_stats(s, per_mode=shared_per_mode) if mode == "player" else get_team_stats(s, per_mode=shared_per_mode)
                        if stat_field not in s_df.columns:
                            any_missing = True
                            continue
                        s_df = s_df.sort_values(stat_field, ascending=False).reset_index(drop=True)
                        s_df["_rank"] = s_df.index + 1
                        for name in picked_names:
                            match = s_df[s_df[name_col] == name]
                            entity_ranks[name].append(int(match.iloc[0]["_rank"]) if not match.empty else None)

                if any_missing:
                    st.warning(f"{chosen_stat_label} wasn't available for at least one season -- showing what's available.")

                complete_ranks = {name: ranks for name, ranks in entity_ranks.items() if None not in ranks}
                if len(complete_ranks) < 2:
                    st.error(f"Not enough complete data across those seasons for at least 2 of the selected {'players' if mode == 'player' else 'teams'}.")
                else:
                    bump_color = resolve_color_input(color_input) or DEFAULT_COLOR
                    entity_image_urls = {}
                    for name in complete_ranks:
                        if mode == "player":
                            record = PLAYER_NAME_TO_RECORD.get(name)
                            if record:
                                entity_image_urls[name] = get_player_headshot_url(record["id"])
                        else:
                            record = TEAM_NAME_TO_RECORD.get(name)
                            if record:
                                entity_image_urls[name] = get_team_logo_url(record["id"])
                    fig = build_bump_chart(season_list, complete_ranks, bump_color, entity_image_urls=entity_image_urls)
                    st.pyplot(fig)
                    title = f"Bump Chart -- {chosen_stat_label} Rank"
                    add_to_tableau_dashboard(fig, title, "tableau_bump")
                    offer_share_to_community(fig, title, "share_bump")


# ---------------------------------------------------------------- Branch: Passing Connections
elif is_court_connection:

    picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    player_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    season = st.selectbox("Season:", _seasons_for_dropdown(mode, picked_name), index=0)
    top_n = st.number_input("Show top __ passing connections:", min_value=3, max_value=10, value=5)
    passing_rank_ascending = rank_direction_control("PASS", "passing")
    default_team = _default_color_team("player", picked_name, season)
    color_input = color_input_with_dropdown(f"connection_color_box_{picked_name}_{season}", default_team)
    st.caption(
        "Each teammate is placed in the court area he took the most shots from right after this player's passes: "
        "every basket this player assisted to him, with its exact court location, plus his misses in each area "
        "estimated from his own FG% there (the NBA only records the passer on made baskets). Teammates who share "
        "an area sit right next to each other. Hover a teammate to see every area."
    )

    run = persistent_run_button((season and picked_name), key=visualization)

    if run:
        render_passing_web(picked_name, player_id, season, top_n=top_n, rank_ascending=passing_rank_ascending,
                           color_input=color_input, key="passing_web")


elif is_bar_chart:

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    chosen_category = st.selectbox("Stat category:", category_names)

    stats_in_category = dict(categories)[chosen_category]
    stat_labels = [label for _, label, _, _ in stats_in_category]
    chosen_stat_label = st.selectbox("Stat:", stat_labels)

    chosen_stat = next(s for s in stats_in_category if s[1] == chosen_stat_label)
    stat_field = chosen_stat[0]

    if stat_field in BRADLEY_RATING_DESCRIPTIONS:
        st.caption(BRADLEY_RATING_DESCRIPTIONS[stat_field])

    top_n = st.number_input("Display the top __:", min_value=1, max_value=499, value=10)
    rank_ascending = rank_direction_control(stat_field, "bar_chart")

    included_input = st.text_input(
        f"Enter {'player' if mode == 'player' else 'team'}(s) to include (comma separated, optional):"
    )

    season = st.selectbox("Season:", ALL_SEASONS, index=0)

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
                "(bradley_ratings.py), which isn't ported to the dashboard yet -- "
                "base and advanced stats work now."
            )
        elif not season:
            st.warning("Enter a season first.")
        else:
            with code_loading_animation("Downloading stats"):
                stats_df = fetch_stats_for_source(stat_source, season, mode)

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
                leaderboard = (stats_df.nsmallest(int(top_n), stat_field) if rank_ascending else stats_df.nlargest(int(top_n), stat_field))[[name_col, id_col, stat_field]]
                leaderboard.columns = ["name", "player_id", "value"]
                if mode == "player":
                    leaderboard["image_url"] = leaderboard["player_id"].apply(get_player_headshot_url)
                else:
                    leaderboard["image_url"] = leaderboard["player_id"].apply(get_team_logo_url)

                included_names = [n.strip() for n in included_input.split(",") if n.strip()] if included_input else []
                leaderboard["is_included"] = leaderboard["name"].isin(included_names) if included_names else True

                is_pct = stat_field.endswith("_PCT")
                bar_team_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR

                if display_as == "Dot Plot":
                    fig = build_dot_plot(
                        leaderboard, stat_display_name=chosen_stat_label, season=season,
                        top_n=int(top_n), team_color=bar_team_color, included_names=included_names,
                        stat_source=stat_source, is_percentage=is_pct, rank_ascending=rank_ascending,
                    )
                else:
                    fig = build_bar_chart(
                        leaderboard, stat_display_name=chosen_stat_label, season=season,
                        top_n=int(top_n), team_color=bar_team_color, included_names=included_names,
                        orientation="vertical" if display_as == "Vertical Bar" else "horizontal",
                        stat_source=stat_source, is_percentage=is_pct, rank_ascending=rank_ascending,
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

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    chosen_category = st.selectbox("Stat category:", category_names)

    stats_in_category = dict(categories)[chosen_category]
    stat_labels = [label for _, label, _, _ in stats_in_category]
    chosen_stat_label = st.selectbox("Stat:", stat_labels)

    chosen_stat = next(s for s in stats_in_category if s[1] == chosen_stat_label)
    stat_field = chosen_stat[0]

    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    display_as = st.radio("Display As:", ["Histogram", "Density Plot"], horizontal=True)
    bins = st.number_input("Number of bins:", min_value=5, max_value=60, value=20, disabled=(display_as == "Density Plot"))
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
                "(bradley_ratings.py), which isn't ported to the dashboard yet -- "
                "base and advanced stats work now."
            )
        else:
            with code_loading_animation("Downloading stats"):
                stats_df = fetch_stats_for_source(stat_source, season, mode)

            if stat_field not in stats_df.columns:
                st.error(f"Couldn't find {stat_field} in the returned stats.")
            elif display_as == "Density Plot" and pd.to_numeric(stats_df[stat_field], errors="coerce").dropna().shape[0] < 5:
                st.warning("Not enough players with this stat to estimate a density curve.")
            else:
                is_pct = stat_field.endswith("_PCT")
                hist_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                values = pd.to_numeric(stats_df[stat_field], errors="coerce").dropna().tolist()
                if display_as == "Density Plot":
                    fig = build_density_plot(
                        values, stat_display_name=chosen_stat_label,
                        season=season, team_color=hist_color, is_percentage=is_pct,
                    )
                else:
                    fig = build_histogram(
                        values, stat_display_name=chosen_stat_label,
                        season=season, team_color=hist_color, is_percentage=is_pct, bins=int(bins),
                    )
                st.pyplot(fig)
                add_to_tableau_dashboard(fig, "Histogram", "tableau_histogram")
                offer_share_to_community(fig, "Histogram", "share_histogram")


# ---------------------------------------------------------------- Branch: Cumulative Distribution Plot
elif is_cumdist_plot:

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    chosen_category = st.selectbox("Stat category:", category_names)

    stats_in_category = dict(categories)[chosen_category]
    stat_labels = [label for _, label, _, _ in stats_in_category]
    chosen_stat_label = st.selectbox("Stat:", stat_labels)

    chosen_stat = next(s for s in stats_in_category if s[1] == chosen_stat_label)
    stat_field = chosen_stat[0]

    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    highlight_input = st.selectbox(
        f"Highlight a specific {'player' if mode == 'player' else 'team'} on the curve (optional):",
        ALL_PLAYER_NAMES if mode == "player" else ALL_TEAM_NAMES, index=None,
        placeholder="None -- just show the curve",
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
                "(bradley_ratings.py), which isn't ported to the dashboard yet -- "
                "base and advanced stats work now."
            )
        else:
            with code_loading_animation("Downloading stats"):
                stats_df = fetch_stats_for_source(stat_source, season, mode)

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
                        st.warning(f"No {stat_field} value found for {highlight_input} this season -- showing the curve without a highlight.")

                fig = build_cumulative_distribution_plot(
                    pd.to_numeric(stats_df[stat_field], errors="coerce").dropna().tolist(), stat_display_name=chosen_stat_label,
                    season=season, team_color=cumdist_color, is_percentage=is_pct,
                    highlight_value=highlight_value, highlight_name=highlight_input,
                )
                st.pyplot(fig)
                add_to_tableau_dashboard(fig, "Cumulative Distribution Plot", "tableau_cumdist")
                offer_share_to_community(fig, "Cumulative Distribution Plot", "share_cumdist")


# ---------------------------------------------------------------- Branch: Scatter Plot
# ---------------------------------------------------------------- Branch: Box Plot
elif is_box_plot:

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    chosen_category = st.selectbox("Stat category:", category_names)

    stats_in_category = dict(categories)[chosen_category]
    stat_labels = [label for _, label, _, _ in stats_in_category]
    chosen_stat_label = st.selectbox("Stat:", stat_labels)

    chosen_stat = next(s for s in stats_in_category if s[1] == chosen_stat_label)
    stat_field = chosen_stat[0]

    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    team_filter_input = st.text_input(
        "Limit to these teams (comma-separated abbreviations, e.g. BOS, LAL -- optional, defaults to all 30):"
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
                "(bradley_ratings.py), which isn't ported to the dashboard yet -- "
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
                    st.warning("Not enough players per team to plot a spread -- try lowering the minimum games played.")
                else:
                    is_pct = stat_field.endswith("_PCT")
                    box_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                    fig = build_box_plot(
                        groups, stat_display_name=chosen_stat_label, season=season,
                        team_color=box_color, is_percentage=is_pct, violin=(plot_style == "Violin"),
                    )
                    _labels = list(groups.keys())
                    _names = [group_names.get(t) or [None] * len(groups[t]) for t in _labels]
                    show_chart(fig, _hover(hover.box_plot_hotspots, fig.axes[0], _labels, [groups[t] for t in _labels],
                                           names_data=_names), "box_plot")
                    add_to_tableau_dashboard(fig, "Box Plot", "tableau_box_plot")
                    offer_share_to_community(fig, "Box Plot", "share_box_plot")


# ---------------------------------------------------------------- Branch: Scatter Plot
elif is_scatter_plot:

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]

    st.markdown("**First stat measurement (Y axis):**")
    y_category = st.selectbox("Category (Y):", category_names, key="y_cat")
    y_stats = dict(categories)[y_category]
    y_label = st.selectbox("Stat (Y):", [label for _, label, _, _ in y_stats], key="y_stat")
    y_field = next(s for s in y_stats if s[1] == y_label)[0]

    st.markdown("**Second stat measurement (X axis):**")
    x_category = st.selectbox("Category (X):", category_names, key="x_cat")
    x_stats = dict(categories)[x_category]
    x_label = st.selectbox("Stat (X):", [label for _, label, _, _ in x_stats], key="x_stat")

    top_n = st.number_input("Display the top __ (ranked by Y axis):", min_value=1, max_value=499, value=10)
    rank_ascending = rank_direction_control(y_field, "scatter")

    included_input = st.text_input(
        f"Enter {'player' if mode == 'player' else 'team'}(s) to include (comma separated, optional):"
    )

    season = st.selectbox("Season:", ALL_SEASONS, index=0)

    # No color prompt -- Scatter Plot shows only player headshots or
    # team logos, matching bradley_analytics.py's is_scatter_plot
    # branch exactly.

    run = persistent_run_button(season, key=visualization)

    if run:
        y_stat = next(s for s in y_stats if s[1] == y_label)
        x_stat = next(s for s in x_stats if s[1] == x_label)

        if y_stat[2] == "bradley_rating" or x_stat[2] == "bradley_rating":
            st.warning(
                "Bradley Rating stats require the full multi-season rating model "
                "(bradley_ratings.py), which isn't ported to the dashboard yet -- "
                "base and advanced stats work now."
            )
        elif not season:
            st.warning("Enter a season first.")
        else:
            with code_loading_animation("Downloading stats"):
                y_source, x_source = y_stat[2], x_stat[2]
                id_col = "PLAYER_ID" if mode == "player" else "TEAM_ID"
                if y_source == x_source:
                    # Common case: both axes pull from the same source
                    # (e.g. both "base"/"advanced"/etc, which all live in
                    # the one combined get_player_stats() table anyway) --
                    # a single fetch already has both columns.
                    stats_df = fetch_stats_for_source(y_source, season, mode)
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
                    y_df = fetch_stats_for_source(y_source, season, mode)
                    x_df = fetch_stats_for_source(x_source, season, mode)
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
                leaderboard = (stats_df.nsmallest(int(top_n), y_field) if rank_ascending else stats_df.nlargest(int(top_n), y_field))[[name_col, id_col, y_field, x_field]]
                leaderboard.columns = ["name", "player_id", "y_value", "x_value"]
                if mode == "player":
                    leaderboard["image_url"] = leaderboard["player_id"].apply(get_player_headshot_url)
                else:
                    leaderboard["image_url"] = leaderboard["player_id"].apply(get_team_logo_url)

                included_names = [n.strip() for n in included_input.split(",") if n.strip()] if included_input else []
                leaderboard["is_included"] = leaderboard["name"].isin(included_names) if included_names else False
                # "Show pictures for": which players/teams are drawn as their picture (the rest as dots)
                pics = pickers.picture_picker(leaderboard["name"].tolist(), key=f"scatter_pics_{mode}_{season}",
                                              noun="players" if mode == "player" else "teams")
                leaderboard["show_image"] = leaderboard["name"].astype(str).isin(pics)

                fig, scatter_records = build_scatter_plot(leaderboard, stat_label_y=y_label, stat_label_x=x_label,
                                                          return_hotspot_data=True)
                # The same interactive effects as Search by Criteria's scatter: diagonal bands (best corner = high
                # in both stats, or low for a lower-is-better one), hovered player/band grows, nobody ever darkens.
                show_chart(fig, _hover(hover.criteria_scatter_hotspots, fig.axes[0], scatter_records, x_label, y_label,
                                       noun="player" if mode == "player" else "team",
                                       x_higher_better=x_field not in LOWER_IS_BETTER_STATS,
                                       y_higher_better=not rank_ascending),
                           "scatter_plot")
                add_to_tableau_dashboard(fig, "Scatter Plot", "tableau_scatter_plot")
                offer_share_to_community(fig, "Scatter Plot", "share_scatter_plot")

