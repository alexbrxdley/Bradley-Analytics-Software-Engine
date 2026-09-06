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
                       get_player_passes, get_player_team_for_season)
from nba_api.stats.static import players, teams
from teams import get_team_color, DEFAULT_COLOR, nearest_color_swatch, get_player_headshot_url, get_team_logo_url
from stats_config import COURT_GRAPHS, AXIS_GRAPHS, ANIMATED_GRAPHS, GAME_LOG_GRAPHS, COMPARISON_GRAPHS, get_stats_for_mode, BRADLEY_RATING_DESCRIPTIONS, ALL_SEASONS, VIZ_CATEGORIES
import community_storage
from visuals import (build_shot_chart, build_heat_map, build_hex_shot_chart, build_bar_chart,
                      build_scatter_plot, build_animated_shot_chart, build_trade_breakdown_image,
                      build_onoff_column_image, build_static_stat_table_image,
                      build_histogram, build_box_plot, build_dot_plot,
                      build_density_plot, build_cumulative_distribution_plot, build_line_chart,
                      build_slope_chart, build_waterfall_chart, build_combo_chart, build_tornado_chart,
                      build_radar_chart, build_head_to_head_table, build_calendar_heat_map,
                      build_court_zone_map, build_small_multiples_shot_charts, build_court_radar_hybrid,
                      build_sankey_flow, build_network_diagram, build_momentum_chart,
                      build_impact_clock, build_bump_chart, build_court_connection_map)

st.set_page_config(page_title="Bradley Analytics", page_icon=":basketball:", layout="wide", initial_sidebar_state="auto")

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
        background-attachment: fixed;
        background-size: 100vw 100vh;
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
       9th in that unrelated group. */
    section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:nth-of-type(3) {{
        border-top: 1px solid transparent;
        border-image: {GOLD_GRADIENT} 1;
        margin-top: 10px;
        padding-top: 16px;
    }}

    /* Divider between the main tools group and Community Uploads/Glossary */
    section[data-testid="stSidebar"] label[data-testid="stRadioOption"]:nth-of-type(10) {{
        border-top: 1px solid transparent;
        border-image: {GOLD_GRADIENT} 1;
        margin-top: 10px;
        padding-top: 16px;
    }}

    /* Buttons: full width, gradient-gold border AND text, glow on hover
       (not a solid fill) */
    div[data-testid="stElementContainer"]:has(div[data-testid="stButton"]) {{
        width: 100% !important;
    }}
    div[data-testid="stButton"] {{
        width: 100% !important;
    }}
    div[data-testid="stButton"] button {{
        width: 100% !important;
        background: linear-gradient(135deg, #1A1A1A 0%, #050505 100%) !important;
        border: none;
        border-radius: 10px;
        position: relative;
        font-family: Arial, sans-serif;
        transition: box-shadow 0.2s ease;
    }}
    div[data-testid="stButton"] button::before {{
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
    div[data-testid="stButton"] button p {{
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
    div[data-testid="stButton"] button p::before {{
        content: "";
        width: 0;
        height: 0;
        border-top: 7px solid transparent;
        border-bottom: 7px solid transparent;
        border-left: 11px solid #D4AF37;
        flex-shrink: 0;
    }}
    div[data-testid="stButton"] button:hover {{
        box-shadow: 0 0 14px 2px rgba(212, 175, 55, 0.55);
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
    div[data-testid="stTextInputRootElement"] {{
        background-color: rgba(255, 255, 255, 0.04) !important;
        border-color: #2a2a2a !important;
        color: #f0f0f0 !important;
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
    section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"] {{
        padding-top: 0.1rem !important;
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
    div[data-testid="stButton"] button::before {{
        background-size: 200% 100%;
        background-position: 0% 0;
        transition: background-position 1s ease;
    }}
    div[data-testid="stButton"] button:hover::before {{
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
        from {{ opacity: 1; }}
        to {{ opacity: 0; }}
    }}
    .bq-fade-overlay {{
        animation: bqFadeOverlayOut 0.5s ease forwards;
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

    // #2: animate every metric value counting up from 0 to its real value,
    // preserving whatever prefix/suffix formatting Streamlit gave it
    // ($, %, commas, decimals).
    function animateMetric(el) {{
        if (el.dataset.bqAnimated) return;
        el.dataset.bqAnimated = '1';
        const raw = el.textContent;
        const match = raw.match(/-?[\d,]+\.?\d*/);
        if (!match) return;
        const target = parseFloat(match[0].replace(/,/g, ''));
        if (isNaN(target)) return;
        const prefix = raw.slice(0, match.index);
        const suffix = raw.slice(match.index + match[0].length);
        const decimals = (match[0].split('.')[1] || '').length;
        const hasComma = match[0].includes(',');
        const start = performance.now();
        const duration = 2000;
        function frame(now) {{
            const p = Math.min(1, (now - start) / duration);
            const eased = 1 - Math.pow(1 - p, 3);
            const val = target * eased;
            const formatted = hasComma
                ? val.toLocaleString(undefined, {{ minimumFractionDigits: decimals, maximumFractionDigits: decimals }})
                : val.toFixed(decimals);
            el.textContent = prefix + formatted + suffix;
            if (p < 1) requestAnimationFrame(frame);
            else el.textContent = raw;
        }}
        requestAnimationFrame(frame);
        // Guarantees the exact correct final text even if the last RAF
        // frame gets skipped or delayed for any reason (confirmed
        // happening: settled value was off by one, e.g. "24+" instead of
        // "25+", with the animated flag still set -- meaning the loop had
        // started but its completing frame never fired).
        setTimeout(() => {{ el.textContent = raw; }}, duration + 50);
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

    function reportHeight() {{
        const container = parentDoc.querySelector('[data-testid="stMainBlockContainer"]');
        const sidebar = parentDoc.querySelector('section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"]');
        if (!container) return;
        const mainHeight = Math.ceil(container.getBoundingClientRect().height) + 60;
        // A generated visualization (chart, image, GIF) can make the
        // main content taller than the sidebar, but the sidebar's own
        // 10-item category list is a fixed height regardless of which
        // page is showing -- using whichever is actually taller means
        // the iframe never clips either one, on any page.
        //
        // The sidebar's width is checked first -- confirmed via direct
        // measurement that a collapsed/hidden sidebar (mobile default)
        // isn't display:none, it's squeezed to ~0px width while still
        // laid out, which wraps every word onto its own line and
        // inflates its content height to 4000+px. Without this check,
        // a hidden sidebar was making the whole page report as far
        // taller than either its visible content or the sidebar
        // actually is.
        const sidebarRect = sidebar ? sidebar.getBoundingClientRect() : null;
        const sidebarHeight = (sidebarRect && sidebarRect.width > 50) ? Math.ceil(sidebarRect.height) + 100 : 0;
        const height = Math.max(mainHeight, sidebarHeight);
        window.top.postMessage({{ type: 'ba-resize', height: height }}, '*');
    }}
    function initHeightReporter() {{
        const container = parentDoc.querySelector('[data-testid="stMainBlockContainer"]');
        const sidebar = parentDoc.querySelector('section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"]');
        if (!container) {{ setTimeout(initHeightReporter, 200); return; }}
        const resizeObserver = new ResizeObserver(() => reportHeight());
        resizeObserver.observe(container);
        if (sidebar) resizeObserver.observe(sidebar);
        reportHeight();
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
                    parentDoc.defaultView.setTimeout(() => overlay.remove(), 650);
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
            m.addedNodes.forEach((node) => {{
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
    }}).observe(parentDoc.body, {{ childList: true, subtree: true }});
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
    names = sorted(t["full_name"] for t in all_teams)
    by_name = {t["full_name"]: t for t in all_teams}
    return names, by_name


ALL_TEAM_NAMES, TEAM_NAME_TO_RECORD = _load_all_teams()
# Reverse lookup (e.g. "BOS" -> "Boston Celtics") -- needed to convert
# PlayerCareerStats' TEAM_ABBREVIATION into the full team name the
# color dropdown's own options are keyed by.
TEAM_ABBREVIATION_TO_NAME = {t["abbreviation"]: t["full_name"] for t in teams.get_teams()}


CATEGORIES = [
    "Home",
    "AI Search",
    "Search by Player",
    "Search by Team",
    "Search by Criteria",
    "Trade Machine",
    "On/Off Stats",
    "Advanced Stats",
    "Tableau Dashboard",
    "Community Uploads",
    "Glossary",
]

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
category = st.sidebar.radio("Category", CATEGORIES, label_visibility="collapsed", key="category_radio")


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


def offer_share_to_community(fig, source_section: str, widget_key: str):
    """
    A button (same style as RUN) that reveals a name/description form
    on click, then publishes to Community Uploads on submit -- replaces
    an earlier always-open expander design. One reusable function so
    every chart-generating section gets identical behavior.
    """
    show_key = f"{widget_key}_show_form"
    if st.button("Share to the \"Community Uploads\" page", key=f"{widget_key}_share_btn", use_container_width=True):
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
                st.session_state[show_key] = False


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

    if st.button("Add to Tableau Dashboard", key=f"{widget_key}_tableau_btn", use_container_width=True):
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
        st.success(f"Added to Tableau Dashboard, slot {slot_idx + 1}.")


# =============================================================================
# HOME
# =============================================================================
def resolve_color_input(color_input: str) -> str:
    """Mirrors resolve_color() -- accepts a raw hex code or a team name."""
    hex_candidate = color_input.strip().lstrip("#")
    is_hex = len(hex_candidate) == 6 and all(c in "0123456789abcdefABCDEF" for c in hex_candidate)
    if is_hex:
        return f"#{hex_candidate.upper()}"
    return get_team_color(color_input)


def color_input_with_dropdown(widget_key: str, default_team: str = None) -> str:
    """
    A real, live, type-as-you-go searchable dropdown of all 30 teams
    (the same native Streamlit selectbox search behavior used for player
    search above), plus a separate hex code field for anyone who wants an
    exact custom color instead of a team's -- a selectbox can only ever
    return one of its own listed options, so it can't also accept an
    arbitrary typed hex value the way a single combined field would need
    to; two clearly-labeled fields is the correct shape for "pick a team
    OR type an exact color", not a limitation to hide.

    default_team: pre-selects this team (e.g. the subject player's
    actual team for the selected season, or the subject team itself)
    instead of leaving the dropdown empty. The caller's widget_key
    must vary with whatever determines default_team (player+season,
    or team) -- Streamlit widgets keep whatever the user last picked
    in session_state once a key has been used once, so a fixed key
    would keep showing a stale team from a previous player/season
    instead of ever re-applying a new default.
    """
    default_index = ALL_TEAM_NAMES.index(default_team) if default_team in ALL_TEAM_NAMES else None
    picked_team = st.selectbox(
        "Color:",
        ALL_TEAM_NAMES,
        index=default_index,
        placeholder="Choose a team...",
        key=widget_key,
        format_func=lambda name: f"{nearest_color_swatch(get_team_color(name))} {name}",
    )
    hex_typed = st.text_input(
        "Or enter a color code instead:", key=widget_key + "_hex",
        placeholder="...or enter a color code instead.", label_visibility="collapsed",
    )
    if hex_typed:
        return hex_typed
    if picked_team:
        return picked_team
    return ""


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
    return TEAM_ABBREVIATION_TO_NAME.get(abbrev) if abbrev else None




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
    st.title("AI Search")
    st.caption("Ask for a chart, leaderboard, filtered player search, or stat lookup in plain language.")
    info_card("Disclaimer",
        "Bradley is an AI assistant built on real, live NBA API data -- but like any AI, it can "
        "occasionally misread a request, pick the wrong player/season, or make a mistake summarizing "
        "a result. The underlying charts and numbers come straight from the NBA API, but double-check "
        "anything that matters against the raw data (Search by Player/Team/Criteria) before relying on it.")

    import json as _json_module
    import uuid as _uuid_module

    _ai_dir = os.path.join(os.path.dirname(__file__), "..", "ai_assistant")
    with open(os.path.join(_ai_dir, "tools_schema.json")) as _f:
        _tools_schema = _json_module.load(_f)["tools"]
    api_tools = [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in _tools_schema
    ]
    with open(os.path.join(_ai_dir, "system_prompt.md")) as _f:
        SYSTEM_PROMPT = _f.read()

    try:
        api_key = st.secrets.get("GROQ_API_KEY", None)
    except Exception:
        api_key = None
    if not api_key:
        api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        st.markdown(f"""
        <div class="bq-info-card">
          <div class="bq-info-card-title">AI Setup Required</div>
          <div class="bq-info-card-body">
            Bradley isn't live yet -- no Groq API key configured. Groq is free -- get a key at
            <a href="https://console.groq.com/keys" target="_blank">console.groq.com</a>,
            no credit card required:
            <ul style="margin: 8px 0 0 0; padding-left: 20px;">
              <li><strong>Local run:</strong> create <code>.streamlit/secrets.toml</code> in the
                  project root with <code>GROQ_API_KEY = "your-key-here"</code></li>
              <li><strong>Streamlit Community Cloud:</strong> add <code>GROQ_API_KEY</code>
                  under your deployed app's Settings -> Secrets</li>
            </ul>
          </div>
        </div>
        """, unsafe_allow_html=True)

    def dispatch_ai_tool_call(tool_name: str, tool_input: dict):
        """Maps each AI tool name to a real call into this project's own nba_data/visuals functions."""
        try:
            if tool_name == "generate_court_visualization":
                subject_type = tool_input["subject_type"]
                subject_name = tool_input["subject_name"]
                season = tool_input["season"]
                chart_type = tool_input["chart_type"]

                if subject_type == "player":
                    record = PLAYER_NAME_TO_RECORD.get(subject_name)
                    if not record:
                        return {"error": f"No player found matching '{subject_name}'. Ask the person to confirm the spelling."}
                    shots = get_player_shots(record["id"], season)
                else:
                    record = TEAM_NAME_TO_RECORD.get(subject_name)
                    if not record:
                        return {"error": f"No team found matching '{subject_name}'."}
                    shots = get_team_shots(record["id"], season)

                if shots is None or shots.empty:
                    return {"error": f"No shot data found for {subject_name} in {season} -- they may not have played that season, or it's outside the 1996-97+ range shot data is tracked for."}

                color_input = tool_input.get("color")
                team_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR

                if chart_type == "shot_chart":
                    fig = build_shot_chart(shots, team_color)
                elif chart_type == "heat_map":
                    fig = build_heat_map(shots, team_color)
                elif chart_type == "hex_shot_chart":
                    league_shots = get_league_shots(season)
                    fig = build_hex_shot_chart(shots, league_shots, team_color)
                elif chart_type == "animated_shot_chart":
                    gif_buffer = build_animated_shot_chart(shots, team_color)
                    path = f"/tmp/ai_chart_{_uuid_module.uuid4().hex}.gif"
                    with open(path, "wb") as fh:
                        fh.write(gif_buffer.read())
                    return {"chart_path": path, "note": "Animated GIF generated."}
                else:
                    return {"error": f"Unknown chart_type: {chart_type}"}

                path = f"/tmp/ai_chart_{_uuid_module.uuid4().hex}.png"
                fig.savefig(path, dpi=120, bbox_inches="tight", transparent=True)
                plt.close(fig)
                return {"chart_path": path}

            if tool_name == "search_by_criteria":
                season = tool_input["season"]
                per_mode = tool_input.get("per_mode", "PerGame")
                stats_df = get_player_stats(season, per_mode=per_mode)
                bio_df = get_player_bio_stats(season)
                if stats_df is None or bio_df is None:
                    return {"error": f"Couldn't load league data for {season}."}

                bio_position_col = next((c for c in ("PLAYER_POSITION", "POSITION") if c in bio_df.columns), None)
                bio_cols = ["PLAYER_ID", "PLAYER_HEIGHT_INCHES", "PLAYER_WEIGHT"]
                if "AGE" in bio_df.columns:
                    bio_cols.append("AGE")
                if bio_position_col:
                    bio_cols.append(bio_position_col)
                merged = stats_df.merge(bio_df[bio_cols], on="PLAYER_ID", how="inner", suffixes=("", "_bio"))
                filtered = merged.copy()

                if tool_input.get("position") and bio_position_col:
                    filtered = filtered[filtered[bio_position_col].astype(str).str.contains(tool_input["position"], case=False, na=False)]
                if tool_input.get("min_age") is not None and "AGE" in filtered.columns:
                    filtered = filtered[filtered["AGE"] >= tool_input["min_age"]]
                if tool_input.get("max_age") is not None and "AGE" in filtered.columns:
                    filtered = filtered[filtered["AGE"] <= tool_input["max_age"]]
                if tool_input.get("min_height_inches") is not None:
                    filtered = filtered[filtered["PLAYER_HEIGHT_INCHES"] >= tool_input["min_height_inches"]]
                if tool_input.get("max_height_inches") is not None:
                    filtered = filtered[filtered["PLAYER_HEIGHT_INCHES"] <= tool_input["max_height_inches"]]

                for sf in tool_input.get("stat_filters", []):
                    stat = sf.get("stat")
                    if stat not in filtered.columns:
                        continue
                    if "min" in sf and sf["min"] is not None:
                        filtered = filtered[filtered[stat] >= sf["min"]]
                    if "max" in sf and sf["max"] is not None:
                        filtered = filtered[filtered[stat] <= sf["max"]]

                sort_by = tool_input.get("sort_by")
                if sort_by and sort_by in filtered.columns:
                    filtered = filtered.sort_values(sort_by, ascending=False)

                top_n = min(tool_input.get("top_n", 10), 30)
                filtered = filtered.head(top_n)

                if filtered.empty:
                    return {"error": "No players matched every one of those filters -- try loosening one of them.", "players": []}

                result_cols = ["PLAYER_NAME"] + ([bio_position_col] if bio_position_col else []) + (["AGE"] if "AGE" in filtered.columns else [])
                stat_names_wanted = list({sf["stat"] for sf in tool_input.get("stat_filters", [])} | ({sort_by} if sort_by else set()))
                result_cols += [s for s in stat_names_wanted if s in filtered.columns and s not in result_cols]

                players_out = filtered[result_cols].round(3).to_dict(orient="records")
                return {"players": players_out, "count": len(players_out)}

            if tool_name == "generate_leaderboard":
                season = tool_input["season"]
                per_mode = tool_input.get("per_mode", "PerGame")
                subject_type = tool_input["subject_type"]
                stat_field = tool_input["stat"]
                top_n = min(tool_input.get("top_n", 10), 30)
                ascending = tool_input.get("ascending", False)

                stats_df = get_player_stats(season, per_mode=per_mode) if subject_type == "player" else get_team_stats(season)
                id_col = "PLAYER_ID" if subject_type == "player" else "TEAM_ID"
                name_col = "PLAYER_NAME" if subject_type == "player" else "TEAM_NAME"
                if stat_field not in stats_df.columns:
                    return {"error": f"'{stat_field}' isn't a valid stat field for {season}. Check the exact field name and try again."}

                ranked = stats_df.nsmallest(top_n, stat_field) if ascending else stats_df.nlargest(top_n, stat_field)
                leaderboard = ranked[[name_col, id_col, stat_field]].copy()
                leaderboard.columns = ["name", "player_id" if subject_type == "player" else "team_id", "value"]
                if subject_type == "player":
                    leaderboard["image_url"] = leaderboard["player_id"].apply(
                        lambda pid: f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png"
                    )
                else:
                    leaderboard["image_url"] = ""
                leaderboard["is_included"] = True

                is_pct = stat_field.endswith("_PCT")
                fig = build_bar_chart(
                    leaderboard, stat_display_name=stat_field, season=season,
                    top_n=top_n, team_color=DEFAULT_COLOR, included_names=[],
                    orientation="vertical", stat_source="base",
                    is_percentage=is_pct,
                )
                path = f"/tmp/ai_chart_{_uuid_module.uuid4().hex}.png"
                fig.savefig(path, dpi=120, bbox_inches="tight", transparent=True)
                plt.close(fig)
                return {"chart_path": path, "top_result": leaderboard.iloc[0]["name"] if not leaderboard.empty else None}

            if tool_name == "generate_scatter_plot":
                season = tool_input["season"]
                per_mode = tool_input.get("per_mode", "PerGame")
                subject_type = tool_input["subject_type"]
                x_field = tool_input["x_stat"]
                y_field = tool_input["y_stat"]
                highlight_names = tool_input.get("highlight_names", [])

                stats_df = get_player_stats(season, per_mode=per_mode) if subject_type == "player" else get_team_stats(season)
                id_col = "PLAYER_ID" if subject_type == "player" else "TEAM_ID"
                name_col = "PLAYER_NAME" if subject_type == "player" else "TEAM_NAME"
                if x_field not in stats_df.columns or y_field not in stats_df.columns:
                    return {"error": f"Couldn't find '{x_field}' or '{y_field}' in the {season} data. Check the exact field names."}

                scatter_df = stats_df.nlargest(50, y_field)[[name_col, id_col, y_field, x_field]].copy()
                scatter_df.columns = ["name", "player_id", "y_value", "x_value"]
                scatter_df["image_url"] = scatter_df["player_id"].apply(
                    lambda pid: f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png"
                ) if subject_type == "player" else ""
                scatter_df["is_included"] = scatter_df["name"].isin(highlight_names) if highlight_names else False

                fig = build_scatter_plot(scatter_df, stat_label_y=y_field, stat_label_x=x_field)
                path = f"/tmp/ai_chart_{_uuid_module.uuid4().hex}.png"
                fig.savefig(path, dpi=120, bbox_inches="tight", transparent=True)
                plt.close(fig)
                return {"chart_path": path}

            if tool_name == "trade_machine":
                season = tool_input["season"]
                team_1 = tool_input["team_1"]
                team_2 = tool_input["team_2"]
                team_1_sends = tool_input["team_1_sends"]
                team_2_sends = tool_input["team_2_sends"]

                if team_1 not in TEAM_NAME_TO_RECORD or team_2 not in TEAM_NAME_TO_RECORD:
                    return {"error": "One of those team names wasn't recognized. Check the exact full team name."}

                trade_stats = get_player_stats(season, per_mode="PerGame")
                if trade_stats is None or "PLAYER_NAME" not in trade_stats.columns:
                    return {"error": f"Couldn't load player stats for {season}."}

                player_ids = {name: rec["id"] for name, rec in PLAYER_NAME_TO_RECORD.items()}
                salary_data = _load_salary_data()

                fig = build_trade_breakdown_image(
                    team_1, team_2,
                    sends_a=team_1_sends, sends_b=team_2_sends,
                    stats_df=trade_stats, player_ids=player_ids,
                    salary_data=salary_data,
                )
                path = f"/tmp/ai_chart_{_uuid_module.uuid4().hex}.png"
                fig.savefig(path, dpi=120, bbox_inches="tight", transparent=True)
                plt.close(fig)
                return {"chart_path": path}

            if tool_name == "advanced_stats":
                subject_type = tool_input["subject_type"]
                subject_name = tool_input["subject_name"]
                season = tool_input["season"]

                stats_df = get_player_stats(season, per_mode="PerGame") if subject_type == "player" else get_team_stats(season)
                name_col = "PLAYER_NAME" if subject_type == "player" else "TEAM_NAME"
                if stats_df is None or name_col not in stats_df.columns:
                    return {"error": f"Couldn't load {subject_type} stats for {season}."}

                row_match = stats_df[stats_df[name_col] == subject_name]
                if row_match.empty:
                    return {"error": f"No {subject_type} found matching '{subject_name}' in {season}."}
                row = row_match.iloc[0]

                all_fields = [
                    ("TS_PCT", "TS%", True), ("EFG_PCT", "EFG%", True),
                    ("FG_PCT", "FG%", True), ("FG3_PCT", "3P%", True),
                    ("AST_PCT", "AST%", True), ("AST_TOV", "AST/TOV", False),
                    ("AST_RATIO", "AST Ratio", False), ("TM_TOV_PCT", "TOV%", True),
                    ("OREB_PCT", "OREB%", True), ("DREB_PCT", "DREB%", True),
                    ("REB_PCT", "REB%", True),
                    ("OFF_RATING", "Off Rating", False), ("DEF_RATING", "Def Rating", False),
                    ("NET_RATING", "Net Rating", False), ("PACE", "Pace", False),
                    ("PIE", "PIE", False),
                ]
                all_fields.append(("USG_PCT", "USG%", True) if subject_type == "player" else ("W_PCT", "Win%", True))

                result = {}
                for field, label, is_pct in all_fields:
                    if field in row.index and pd.notna(row[field]):
                        result[label] = round(float(row[field]), 3)
                return {"stats": result}

            if tool_name == "on_off_stats":
                team = tool_input["team"]
                player_1 = tool_input["player_1"]
                player_2 = tool_input["player_2"]
                season = tool_input["season"]

                if team not in TEAM_NAME_TO_RECORD:
                    return {"error": f"No team found matching '{team}'."}
                team_id = TEAM_NAME_TO_RECORD[team]["id"]
                chosen = [player_1, player_2]

                combos = get_team_lineup_combos(team_id, season, group_quantity=2)
                team_baseline = get_team_stats(season)
                solo_lineups = get_team_lineup_combos(team_id, season, group_quantity=1)

                if combos is None or "GROUP_NAME" not in combos.columns:
                    return {"error": "Couldn't load lineup combination data for this team/season."}

                last_names = [p.split()[-1].lower() for p in chosen]

                def _matches(group_name):
                    gn = str(group_name).lower()
                    return all(ln in gn for ln in last_names)

                match_rows = combos[combos["GROUP_NAME"].apply(_matches)]
                if match_rows.empty:
                    return {"error": f"No minutes found with both {player_1} and {player_2} on the court together this season for {team}."}

                combo_row = match_rows.iloc[0]
                combo_min = combo_row.get("MIN", 0)

                team_row_match = team_baseline[team_baseline["TEAM_NAME"] == team] if team_baseline is not None else None
                team_gp = team_row_match.iloc[0].get("GP", 0) if team_row_match is not None and not team_row_match.empty else 0
                team_row = team_row_match.iloc[0] if team_row_match is not None and not team_row_match.empty else None

                combo_row_adv = None
                try:
                    combos_adv = get_team_lineup_combos(team_id, season, group_quantity=2, measure_type="Advanced")
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

                result = {
                    "together": {
                        "off_rating": combo_row_adv.get("OFF_RATING") if combo_row_adv is not None else None,
                        "def_rating": combo_row_adv.get("DEF_RATING") if combo_row_adv is not None else None,
                        "pts_per48": _per48(combo_row, "PTS", combo_min),
                        "reb_per48": _per48(combo_row, "REB", combo_min),
                        "ast_per48": _per48(combo_row, "AST", combo_min),
                    }
                }

                if solo_lineups is not None and "GROUP_NAME" in solo_lineups.columns:
                    for solo_player, other_player in [(player_1, player_2), (player_2, player_1)]:
                        solo_last = solo_player.split()[-1].lower()
                        solo_match = solo_lineups[solo_lineups["GROUP_NAME"].str.lower().str.contains(solo_last)]
                        if solo_match.empty:
                            continue
                        solo_row = solo_match.iloc[0]
                        solo_min = solo_row.get("MIN", 0)
                        without_min = solo_min - combo_min
                        if without_min <= 0:
                            continue
                        without_pts = solo_row.get("PTS", 0) - combo_row.get("PTS", 0) if "PTS" in solo_row.index and "PTS" in combo_row.index else None
                        without_reb = solo_row.get("REB", 0) - combo_row.get("REB", 0) if "REB" in solo_row.index and "REB" in combo_row.index else None
                        without_ast = solo_row.get("AST", 0) - combo_row.get("AST", 0) if "AST" in solo_row.index and "AST" in combo_row.index else None
                        result[f"{solo_player}_without_{other_player}"] = {
                            "pts_per48": (without_pts / without_min) * 48 if without_pts is not None else None,
                            "reb_per48": (without_reb / without_min) * 48 if without_reb is not None else None,
                            "ast_per48": (without_ast / without_min) * 48 if without_ast is not None else None,
                            "note": "Off/Def Rating aren't included here -- they can't be validly derived via subtraction the way counting stats can.",
                        }

                return {"on_off_data": result}

        except Exception as e:
            return {"error": f"Something went wrong running {tool_name}: {e}"}

        return {"error": f"Tool '{tool_name}' is not recognized."}

    if "ai_search_messages" not in st.session_state:
        st.session_state.ai_search_messages = []

    for msg in st.session_state.ai_search_messages:
        if msg["role"] in ("user", "assistant") and isinstance(msg["content"], str):
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

    user_input = st.chat_input("Ask Bradley about any player, team, or stat")
    if user_input:
        st.session_state.ai_search_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        with st.chat_message("assistant"):
            if not api_key:
                st.write("I'm Bradley, but I can't run live yet -- no Groq API key is configured. See the note above this chat for how to add one (it's free).")
            else:
                from groq import Groq
                import groq as groq_module

                MODEL = "openai/gpt-oss-120b"
                client = Groq(api_key=api_key)

                with st.spinner("Thinking..."):
                    history = [m for m in st.session_state.ai_search_messages if isinstance(m["content"], str)][-10:]
                    conversation = [{"role": "system", "content": SYSTEM_PROMPT}] + history
                    final_text = ""
                    generated_charts = []
                    generated_data = []
                    api_error = None

                    try:
                        for _ in range(6):
                            response = client.chat.completions.create(
                                model=MODEL, max_tokens=3000, messages=conversation, tools=api_tools,
                            )
                            choice_msg = response.choices[0].message
                            if choice_msg.content:
                                final_text = choice_msg.content
                            if not choice_msg.tool_calls:
                                break
                            conversation.append({
                                "role": "assistant", "content": choice_msg.content,
                                "tool_calls": [tc.model_dump() for tc in choice_msg.tool_calls],
                            })
                            for tool_call in choice_msg.tool_calls:
                                tool_args = _json_module.loads(tool_call.function.arguments)
                                result = dispatch_ai_tool_call(tool_call.function.name, tool_args)
                                if isinstance(result, dict) and "chart_path" in result and os.path.exists(result["chart_path"]):
                                    generated_charts.append(result["chart_path"])
                                if isinstance(result, dict) and "players" in result:
                                    generated_data.append(result["players"])
                                conversation.append({
                                    "role": "tool", "tool_call_id": tool_call.id,
                                    "content": _json_module.dumps(result, default=str),
                                })
                    except groq_module.NotFoundError:
                        api_error = (
                            f"Groq says the model `{MODEL}` doesn't exist or isn't available anymore. Check "
                            "[console.groq.com/docs/models](https://console.groq.com/docs/models) for a "
                            "current model that supports tool calling, then update the `MODEL` variable "
                            "in `streamlit/app.py`."
                        )
                    except groq_module.AuthenticationError:
                        api_error = "Groq rejected the API key -- double check `GROQ_API_KEY` is set correctly."
                    except groq_module.RateLimitError:
                        api_error = "Hit Groq's rate limit -- wait a moment and try again."
                    except groq_module.BadRequestError as e:
                        api_error = f"Groq rejected the request: {e}"

                    if api_error:
                        st.write(api_error)
                        final_text = api_error
                    else:
                        if final_text:
                            st.write(final_text)
                        for chart_path in generated_charts:
                            if chart_path.endswith(".gif"):
                                st.image(chart_path)
                            else:
                                st.image(chart_path)

                    st.session_state.ai_search_messages.append({"role": "assistant", "content": final_text or "(no response)"})
    st.stop()

elif category == "Search by Criteria":
    st.title("Search by Criteria")
    st.caption(
        "Filter the whole league by position, height, and any combination of "
        "stats, then generate a scatter plot of the players left standing."
    )

    season = st.selectbox(
        "Season:", ALL_SEASONS,
        index=0,
    )
    stat_mode_label = st.radio(
        "Stat mode:", ["Per Game", "Per 36", "Totals"], horizontal=True,
    )
    stat_mode_value = {"Totals": "Totals", "Per Game": "PerGame", "Per 36": "Per36"}[stat_mode_label]

    if season:
        st.subheader("Filters")
        with st.spinner("Downloading league-wide stats and bio data..."):
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
                if not salary_known.empty and salary_known.min() < salary_known.max():
                    s_sal_min = int(salary_known.min())
                    s_sal_max = int(salary_known.max())
                    salary_range = st.slider(
                        "Salary:", s_sal_min, s_sal_max, (s_sal_min, s_sal_max),
                        format_func=lambda v: f"${v / 1_000_000:.1f}M",
                    )
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
            st.markdown(f"**{match_count} players match these filters.**")

            if match_count == 0:
                st.warning("No players match -- loosen a filter.")
            elif match_count > 30:
                st.warning(
                    f"{match_count} players match -- narrow the filters to 30 or "
                    "fewer before generating a scatter plot (matches the same "
                    "cap already used for leaderboards elsewhere in this app, "
                    "so headshots stay legible instead of overlapping)."
                )
            else:
                st.subheader("Generate scatter plot")
                y_label = st.selectbox("Stat (Y axis):", stat_labels, key="crit_y")
                x_label = st.selectbox("Stat (X axis):", stat_labels, key="crit_x", index=min(1, len(stat_labels) - 1))
                run_criteria = st.button("RUN", use_container_width=True, key="crit_run")

                if run_criteria:
                    y_field = label_to_field[y_label]
                    x_field = label_to_field[x_label]
                    if y_field not in filtered.columns or x_field not in filtered.columns:
                        st.error("One of the chosen stats isn't available in this season's data.")
                    else:
                        scatter_df = filtered[["PLAYER_NAME", "PLAYER_ID", y_field, x_field]].copy()
                        scatter_df.columns = ["name", "player_id", "y_value", "x_value"]
                        scatter_df["image_url"] = scatter_df["player_id"].apply(
                            lambda pid: f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png"
                        )
                        scatter_df["is_included"] = True
                        fig = build_scatter_plot(scatter_df, y_label, x_label)
                        st.pyplot(fig, use_container_width=True)
                        offer_share_to_community(fig, "Search by Criteria", "share_criteria")
                        add_to_tableau_dashboard(fig, "Search by Criteria", "tableau_criteria")
                        plt.close(fig)
    st.stop()

elif category == "Trade Machine":
    st.title("Trade Machine")
    st.caption("Pick two teams and swap players between their real rosters.")

    trade_season = st.selectbox(
        "Season:", ALL_SEASONS,
        index=0, key="trade_season",
    )
    tcol1, tcol2 = st.columns(2)
    with tcol1:
        team_a_name = st.selectbox("Team 1:", ALL_TEAM_NAMES, index=None, key="trade_team_a")
    with tcol2:
        team_b_name = st.selectbox("Team 2:", ALL_TEAM_NAMES, index=None, key="trade_team_b")

    if team_a_name and team_b_name and team_a_name == team_b_name:
        st.warning("Pick two different teams.")
    elif team_a_name and team_b_name:
        with st.spinner("Downloading rosters..."):
            try:
                roster_a = get_team_roster(TEAM_NAME_TO_RECORD[team_a_name]["id"], trade_season)
                roster_b = get_team_roster(TEAM_NAME_TO_RECORD[team_b_name]["id"], trade_season)
            except Exception as e:
                roster_a, roster_b = None, None
                st.error(f"Couldn't load rosters for {trade_season}: {e}")

        if roster_a is not None and roster_b is not None:
            names_a = sorted(roster_a["PLAYER"].tolist()) if "PLAYER" in roster_a.columns else []
            names_b = sorted(roster_b["PLAYER"].tolist()) if "PLAYER" in roster_b.columns else []

            with st.spinner("Downloading player stats for roster display..."):
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
                                st.image(f"https://cdn.nba.com/headshots/nba/latest/1040x760/{pid}.png", width=60)
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
                with st.spinner("Downloading player stats..."):
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
                    offer_share_to_community(fig, "Trade Machine", "share_trade")
                    add_to_tableau_dashboard(fig, "Trade Machine", "tableau_trade")
                    plt.close(fig)
    st.stop()

elif category == "On/Off Stats":
    st.title("On/Off Stats")
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
        with st.spinner("Downloading roster..."):
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
                    with st.spinner("Downloading lineup combination data..."):
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
                            st.pyplot(fig, use_container_width=True)
                            offer_share_to_community(fig, "On/Off Stats", "share_onoff")
                            add_to_tableau_dashboard(fig, "On/Off Stats", "tableau_onoff")
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
                                with st.spinner("Downloading individual season stats..."):
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
    st.markdown("#### Two-Man Lineup Network")
    st.caption(
        "Every pair of teammates who shared the court together this season, connected and "
        "colored by that pairing's net rating -- a wider view than picking one specific "
        "combination above, for spotting which pairings work especially well or poorly at a glance."
    )
    if onoff_team_name and st.button("Build Network", key="onoff_network"):
        with st.spinner("Downloading every 2-man lineup combination..."):
            try:
                all_pairs = get_team_lineup_combos(
                    TEAM_NAME_TO_RECORD[onoff_team_name]["id"], onoff_season,
                    group_quantity=2, measure_type="Advanced",
                )
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
                        group_quantity=2, measure_type="Base",
                    )
                    if "PLUS_MINUS" in all_pairs_base.columns:
                        all_pairs = all_pairs_base
                        value_col = "PLUS_MINUS"
                except Exception:
                    pass

            if value_col is None:
                st.error("Couldn't find a net rating or plus/minus column in the returned lineup data.")
            else:
                pair_labels, pair_values = [], []
                for _, row in all_pairs.iterrows():
                    # GROUP_NAME's exact separator isn't pinned down by this
                    # app's own existing GROUP_NAME handling elsewhere
                    # (which only ever checks substring containment, never
                    # splits it) -- tries the standard " - " NBA API
                    # convention and skips any row that doesn't split
                    # cleanly into exactly two names, rather than guessing.
                    parts = [p.strip() for p in str(row["GROUP_NAME"]).split(" - ")]
                    if len(parts) == 2 and pd.notna(row[value_col]):
                        pair_labels.append((parts[0], parts[1]))
                        pair_values.append(float(row[value_col]))

                if len(pair_labels) < 2:
                    st.warning("Not enough valid lineup pairs found to build a network diagram.")
                else:
                    net_color = resolve_color_input(color_input_with_dropdown("network_color_box")) or DEFAULT_COLOR
                    fig = build_network_diagram(pair_labels, pair_values, net_color, value_label=value_col.replace("_", " ").title())
                    st.pyplot(fig)
                    title = f"Lineup Network -- {onoff_team_name}"
                    offer_share_to_community(fig, title, "share_network")
                    add_to_tableau_dashboard(fig, title, "tableau_network")

    st.stop()

elif category == "Advanced Stats":
    st.title("Advanced Stats")
    st.caption("Efficiency, playmaking, rebounding, and impact metrics in one view, for any player or team.")

    adv_category = st.selectbox(
        "Category:",
        [
            "Offense -- Shooting, Playmaking & Impact",
            "Defense -- Shot Defense",
            "Hustle -- Effort Stats",
            "Clutch -- Last 5 Min, Close Games",
            "Play-Type -- Efficiency by Offensive Set",
            "Matchups -- Head-to-Head",
        ],
        key="adv_category",
    )

    if adv_category == "Matchups -- Head-to-Head":
        c1, c2 = st.columns(2)
        matchup_p1 = c1.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.", key="matchup_p1")
        matchup_p2 = c2.selectbox("Versus:", ALL_PLAYER_NAMES, index=None, placeholder="Enter opposing player name.", key="matchup_p2")
        matchup_season = st.selectbox(
            "Season:", ALL_SEASONS, index=0, key="matchup_season",
        )
        if matchup_p1 and matchup_p2:
            with st.spinner(f"Loading head-to-head data..."):
                try:
                    p1_id = PLAYER_NAME_TO_RECORD[matchup_p1]["id"]
                    p2_id = PLAYER_NAME_TO_RECORD[matchup_p2]["id"]
                    matchup_df = get_player_vs_player(p1_id, p2_id, matchup_season)
                except Exception as e:
                    matchup_df = None
                    st.error(f"Couldn't load matchup data: {e}")
            if matchup_df is not None and not matchup_df.empty:
                row = matchup_df.iloc[0]
                fields = [("GP", "Games", False), ("MIN", "Minutes", False), ("PTS", "PTS", False),
                          ("FG_PCT", "FG%", True), ("AST", "AST", False), ("REB", "REB", False)]
                cols = st.columns(len(fields))
                for col, (field, label, is_pct) in zip(cols, fields):
                    if field in row.index and pd.notna(row[field]):
                        val = row[field]
                        col.metric(label, f"{val:.1%}" if is_pct else f"{val:.1f}")
                    else:
                        col.metric(label, "--")
            elif matchup_df is not None:
                st.warning(f"No head-to-head minutes found between {matchup_p1} and {matchup_p2} in {matchup_season}.")
        st.stop()

    elif adv_category in ("Defense -- Shot Defense", "Hustle -- Effort Stats",
                           "Clutch -- Last 5 Min, Close Games", "Play-Type -- Efficiency by Offensive Set"):
        subj_season = st.selectbox(
            "Season:", ALL_SEASONS, index=0, key="subj_season",
        )
        subj_player = st.selectbox(
            "Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.", key="subj_player",
        )
        if subj_player:
            with st.spinner(f"Downloading {subj_season} data..."):
                try:
                    if adv_category == "Defense -- Shot Defense":
                        df = get_player_defense_stats(subj_season)
                    elif adv_category == "Hustle -- Effort Stats":
                        df = get_player_hustle_stats(subj_season)
                    elif adv_category == "Clutch -- Last 5 Min, Close Games":
                        df = get_player_clutch_stats(subj_season)
                    else:
                        df = get_player_playtype_stats(subj_season)
                except Exception as e:
                    df = None
                    st.error(f"Couldn't load this data: {e}")

            if df is not None:
                # PlayerName column varies by endpoint (confirmed via
                # nba_api's own documented schemas -- PLAYER_NAME for
                # most, but the play-type endpoint's documentation only
                # shows team-level fields even when queried at the
                # player level, so this checks both rather than
                # assuming one).
                name_col = next((c for c in ("PLAYER_NAME", "TEAM_NAME") if c in df.columns), None)
                if name_col is None:
                    st.error("This dataset didn't come back in the expected shape -- couldn't find a player or team name column.")
                else:
                    matches = df[df[name_col] == subj_player] if name_col == "PLAYER_NAME" else df
                    if matches.empty:
                        st.warning(f"No {subj_season} data found for {subj_player} in this category.")
                    else:
                        st.dataframe(matches, use_container_width=True, hide_index=True)
        st.stop()

    adv_mode = st.radio("Player or team:", ["Player", "Team"], horizontal=True, key="adv_mode")
    adv_season = st.selectbox(
        "Season:", ALL_SEASONS,
        index=0, key="adv_season",
    )

    if adv_mode == "Player":
        adv_subject = st.selectbox(
            "Player:", ALL_PLAYER_NAMES, index=None,
            placeholder="Enter player name.", key="adv_player",
        )
    else:
        adv_subject = st.selectbox(
            "Team:", ALL_TEAM_NAMES, index=None,
            placeholder="Enter team name.", key="adv_team",
        )

    if adv_subject:
        with st.spinner(f"Downloading {adv_season} stats..."):
            try:
                adv_df = get_player_stats(adv_season, per_mode="PerGame") if adv_mode == "Player" else get_team_stats(adv_season, per_mode="PerGame")
            except Exception as e:
                adv_df = None
                st.error(f"Couldn't load stats for {adv_season}: {e}")

        if adv_df is not None:
            name_col = "PLAYER_NAME" if adv_mode == "Player" else "TEAM_NAME"
            if name_col not in adv_df.columns:
                st.error(f"Couldn't find {name_col} in the returned stats.")
            else:
                row_match = adv_df[adv_df[name_col] == adv_subject]
                if row_match.empty:
                    st.warning(f"No {adv_season} stats found for {adv_subject}.")
                else:
                    row = row_match.iloc[0]

                    def _metric_row(fields):
                        cols = st.columns(len(fields))
                        for col, (field, label, is_pct) in zip(cols, fields):
                            if field in row.index and pd.notna(row[field]):
                                val = row[field]
                                display = f"{val:.1%}" if is_pct else f"{val:.1f}"
                                col.metric(label, display)
                            else:
                                col.metric(label, "--")

                    st.subheader("Shooting Efficiency")
                    _metric_row([
                        ("TS_PCT", "TS%", True), ("EFG_PCT", "EFG%", True),
                        ("FG_PCT", "FG%", True), ("FG3_PCT", "3P%", True),
                    ])

                    st.subheader("Playmaking & Ball Security")
                    _metric_row([
                        ("AST_PCT", "AST%", True), ("AST_TOV", "AST/TOV", False),
                        ("AST_RATIO", "AST Ratio", False), ("TM_TOV_PCT", "TOV%", True),
                    ])

                    st.subheader("Rebounding")
                    _metric_row([
                        ("OREB_PCT", "OREB%", True), ("DREB_PCT", "DREB%", True),
                        ("REB_PCT", "REB%", True),
                    ])

                    st.subheader("Overall Impact")
                    _metric_row([
                        ("OFF_RATING", "Off Rating", False), ("DEF_RATING", "Def Rating", False),
                        ("NET_RATING", "Net Rating", False),
                    ])
                    _metric_row([
                        ("PACE", "Pace", False), ("PIE", "PIE", False),
                        ("USG_PCT", "USG%", True) if adv_mode == "Player" else ("W_PCT", "Win%", True),
                    ])

                    st.subheader("Full Stat Table")
                    all_fields = [
                        ("TS_PCT", "TS%", True), ("EFG_PCT", "EFG%", True),
                        ("FG_PCT", "FG%", True), ("FG3_PCT", "3P%", True),
                        ("AST_PCT", "AST%", True), ("AST_TOV", "AST/TOV", False),
                        ("AST_RATIO", "AST Ratio", False), ("TM_TOV_PCT", "TOV%", True),
                        ("OREB_PCT", "OREB%", True), ("DREB_PCT", "DREB%", True),
                        ("REB_PCT", "REB%", True),
                        ("OFF_RATING", "Off Rating", False), ("DEF_RATING", "Def Rating", False),
                        ("NET_RATING", "Net Rating", False), ("PACE", "Pace", False),
                        ("PIE", "PIE", False),
                    ]
                    if adv_mode == "Player":
                        all_fields.append(("USG_PCT", "USG%", True))
                    else:
                        all_fields.append(("W_PCT", "Win%", True))

                    static_table_rows = []
                    for field, label, is_pct in all_fields:
                        value = row[field] if field in row.index and pd.notna(row[field]) else None
                        static_table_rows.append((label, value, is_pct))

                    stat_fig = build_static_stat_table_image(adv_subject, static_table_rows)
                    st.pyplot(stat_fig, use_container_width=True)
                    offer_share_to_community(stat_fig, f"Advanced Stats -- {adv_subject}", "share_advanced_stats")
                    add_to_tableau_dashboard(stat_fig, f"Advanced Stats -- {adv_subject}", "tableau_advanced_stats")
                    plt.close(stat_fig)
    st.stop()

elif category == "Tableau Dashboard":
    st.title("Tableau Dashboard")
    st.caption(
        "Build a custom collage from up to 6 charts. Click the + on an "
        "empty slot to jump to a page, generate any chart the regular "
        "way, then use its \"Add to Tableau Dashboard\" button. Slots "
        "can be reordered with the dropdown under each one."
    )

    if "tableau_slots" not in st.session_state:
        st.session_state.tableau_slots = [None] * 6

    def _render_tableau_slot(idx):
        slot = st.session_state.tableau_slots[idx]
        if slot is None:
            st.markdown(
                '<div style="background:#1a1a1a; border:2px dashed #3a3a3a; border-radius:8px; '
                'height:200px; display:flex; align-items:center; justify-content:center;">'
                '<span style="font-size:48px; color:#555;">+</span></div>',
                unsafe_allow_html=True,
            )
            if st.button("Generate a chart for this slot", key=f"tableau_plus_{idx}", use_container_width=True):
                st.session_state["tableau_target_slot"] = idx
                nav_to("Search by Player")
        else:
            st.image(slot["image_bytes"], use_container_width=True, caption=slot["source"])
            mcol1, mcol2 = st.columns(2)
            with mcol1:
                move_to = st.selectbox(
                    f"Move slot {idx + 1} to:", list(range(1, 7)), index=idx,
                    key=f"tableau_move_{idx}", label_visibility="collapsed",
                )
                if move_to - 1 != idx:
                    st.session_state.tableau_slots[idx], st.session_state.tableau_slots[move_to - 1] = (
                        st.session_state.tableau_slots[move_to - 1], st.session_state.tableau_slots[idx],
                    )
                    st.rerun()
            with mcol2:
                if st.button("Remove", key=f"tableau_remove_{idx}", use_container_width=True):
                    st.session_state.tableau_slots[idx] = None
                    st.rerun()

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

elif category == "Community Uploads":
    st.title("Community Uploads")
    st.caption(
        "Charts shared by anyone using this app. Generate a chart in "
        "Search by Player, Search by Team, Search by Criteria, or Trade "
        "Machine, then use the \"Share to Community Uploads\" "
        "option underneath it to publish here."
    )
    st.caption(
        "Storage note: these are saved to this app's own files, so they "
        "persist for as long as the current deployment stays up, but "
        "redeploying the app resets this gallery -- see "
        "community_storage.py for the upgrade path to permanent storage."
    )

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
BOTH_MODE_COMPARISON_GRAPHS = ['Head-to-Head']
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

viz_category = st.radio(
    "Visualization Category:",
    list(VIZ_CATEGORIES.keys()),
    horizontal=True,
    key="viz_category",
)
all_visualizations = [v for v in VIZ_CATEGORIES[viz_category] if v in all_visualizations_unfiltered]

visualization = st.selectbox(
    "Visualization:",
    all_visualizations,
    index=None,
    placeholder="Choose visualization.",
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

            with st.spinner("Looking up available seasons..."):
                real_seasons = get_player_career_seasons(player_id)

            if real_seasons is None:
                # Fallback if the career-span lookup fails for any
                # reason (network issue, proxy problem, etc.) --
                # a reasonable recent-seasons range rather than a
                # hard crash.
                from datetime import date
                today = date.today()
                current_season_start_year = today.year if today.month >= 10 else today.year - 1
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
        run = st.button("RUN", use_container_width=True)
    else:
        run = False

    if run:
        if mode == "player" and player_id:
            with st.spinner("Downloading shot data..."):
                shots = get_player_shots(player_id, season)

            team_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR

            if visualization == "Shot Chart":
                fig = build_shot_chart(shots, team_color)
                st.pyplot(fig)
                offer_share_to_community(fig, f"Search by {mode.capitalize()} -- Shot Chart", "share_shot_chart")
                add_to_tableau_dashboard(fig, f"Search by {mode.capitalize()} -- Shot Chart", "tableau_shot_chart")
            elif visualization == "Heat Map":
                fig = build_heat_map(shots, team_color)
                st.pyplot(fig)
                offer_share_to_community(fig, f"Search by {mode.capitalize()} -- Heat Map", "share_heat_map")
                add_to_tableau_dashboard(fig, f"Search by {mode.capitalize()} -- Heat Map", "tableau_heat_map")
            elif visualization == "Hex Shot Chart":
                with st.spinner("Downloading league-wide comparison data..."):
                    league_shots = get_league_shots(season)
                fig = build_hex_shot_chart(shots, league_shots, team_color)
                st.pyplot(fig)
                offer_share_to_community(fig, f"Search by {mode.capitalize()} -- Hex Shot Chart", "share_hex_chart")
                add_to_tableau_dashboard(fig, f"Search by {mode.capitalize()} -- Hex Shot Chart", "tableau_hex_chart")
            elif visualization == "Animated Shot Chart":
                with st.spinner("Building animation -- this takes a little longer..."):
                    gif_buffer = build_animated_shot_chart(shots, team_color)
                st.image(gif_buffer)
                offer_share_to_community(gif_buffer, f"Search by {mode.capitalize()} -- Animated Shot Chart", "share_animated_chart")
                add_to_tableau_dashboard(gif_buffer, f"Search by {mode.capitalize()} -- Animated Shot Chart", "tableau_animated_chart")
            elif visualization == "Court Zone Map":
                fig = build_court_zone_map(shots, picked_name)
                st.pyplot(fig)
                offer_share_to_community(fig, f"Search by {mode.capitalize()} -- Court Zone Map", "share_zone_map")
                add_to_tableau_dashboard(fig, f"Search by {mode.capitalize()} -- Court Zone Map", "tableau_zone_map")
            else:
                st.info(f"{visualization} is being built next.")
        elif mode == "team" and team_query:
            with st.spinner("Downloading shot data..."):
                shots = get_team_shots(TEAM_NAME_TO_RECORD[team_query]["id"], season)

            team_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR

            if visualization == "Shot Chart":
                fig = build_shot_chart(shots, team_color)
                st.pyplot(fig)
                offer_share_to_community(fig, "Search by Team -- Shot Chart", "share_team_shot_chart")
                add_to_tableau_dashboard(fig, "Search by Team -- Shot Chart", "tableau_team_shot_chart")
            elif visualization == "Heat Map":
                fig = build_heat_map(shots, team_color)
                st.pyplot(fig)
                offer_share_to_community(fig, "Search by Team -- Heat Map", "share_team_heat_map")
                add_to_tableau_dashboard(fig, "Search by Team -- Heat Map", "tableau_team_heat_map")
            elif visualization == "Hex Shot Chart":
                with st.spinner("Downloading league-wide comparison data..."):
                    league_shots = get_league_shots(season)
                fig = build_hex_shot_chart(shots, league_shots, team_color)
                st.pyplot(fig)
                offer_share_to_community(fig, "Search by Team -- Hex Shot Chart", "share_team_hex_chart")
                add_to_tableau_dashboard(fig, "Search by Team -- Hex Shot Chart", "tableau_team_hex_chart")
            elif visualization == "Animated Shot Chart":
                with st.spinner("Building animation -- this takes a little longer..."):
                    gif_buffer = build_animated_shot_chart(shots, team_color)
                st.image(gif_buffer)
                offer_share_to_community(gif_buffer, "Search by Team -- Animated Shot Chart", "share_team_animated_chart")
                add_to_tableau_dashboard(gif_buffer, "Search by Team -- Animated Shot Chart", "tableau_team_animated_chart")
            elif visualization == "Court Zone Map":
                fig = build_court_zone_map(shots, f"{team_query}")
                st.pyplot(fig)
                offer_share_to_community(fig, "Search by Team -- Court Zone Map", "share_team_zone_map")
                add_to_tableau_dashboard(fig, "Search by Team -- Court Zone Map", "tableau_team_zone_map")
            else:
                st.info(f"{visualization} is being built next.")
        else:
            st.warning("Enter a valid player or team name first.")


# ---------------------------------------------------------------- Branch: Bar Chart
# ---------------------------------------------------------------- Branch: Line / Trend Chart
elif is_line_chart:

    # Its own player picker -- this branch is a sibling of the court-graphs
    # block above, not nested inside it, so player_id/picked_name aren't
    # set by that block's own selectbox for this branch.
    picked_name = st.selectbox(
        "Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.",
    )
    player_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    chosen_category = st.selectbox("Stat category:", category_names)

    stats_in_category = dict(categories)[chosen_category]
    stat_labels = [label for _, label, _, _ in stats_in_category]
    chosen_stat_label = st.selectbox("Stat:", stat_labels)

    chosen_stat = next(s for s in stats_in_category if s[1] == chosen_stat_label)
    stat_field = chosen_stat[0]

    season = st.selectbox("Season:", ALL_SEASONS, index=0)

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

    default_team = _default_color_team("player", picked_name, season)
    color_input = color_input_with_dropdown(f"line_color_box_{picked_name}_{season}", default_team)

    if season:
        run = st.button("RUN", use_container_width=True)
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
        elif not player_id:
            st.warning("Pick a player first.")
        else:
            with st.spinner("Downloading game log..."):
                game_log = get_player_game_log(player_id, season)

            # PlayerGameLog's raw stat abbreviations (PTS, AST, REB, ...)
            # match this app's own base stat_field names directly for
            # counting stats, but advanced/bio fields (TS%, USG%, etc.)
            # aren't in a single game's box score at all -- confirmed via
            # the endpoint's own documented columns, not assumed.
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
                st.pyplot(fig)
                offer_share_to_community(fig, f"Line Chart -- {picked_name}", "share_line_chart")
                add_to_tableau_dashboard(fig, f"Line Chart -- {picked_name}", "tableau_line_chart")


elif is_waterfall_chart:

    picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    player_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    default_team = _default_color_team("player", picked_name, season)
    color_input = color_input_with_dropdown(f"waterfall_color_box_{picked_name}_{season}", default_team)

    run = st.button("RUN", use_container_width=True) if (season and picked_name) else False

    if run:
        with st.spinner("Downloading stats..."):
            stats_df = get_player_stats(season, per_mode="PerGame")

        player_row = stats_df[stats_df["PLAYER_NAME"] == picked_name]
        if player_row.empty:
            st.error(f"No stats found for {picked_name} in {season}.")
        else:
            row = player_row.iloc[0]
            ftm, fg3m, fgm = float(row["FTM"]), float(row["FG3M"]), float(row["FGM"])
            fg2m = fgm - fg3m
            wf_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
            fig = build_waterfall_chart(
                ["FT pts", "2PT pts", "3PT pts"], [ftm * 1, fg2m * 2, fg3m * 3],
                "Total PTS", wf_color,
            )
            st.pyplot(fig)
            offer_share_to_community(fig, f"Waterfall -- {picked_name}", "share_waterfall")
            add_to_tableau_dashboard(fig, f"Waterfall -- {picked_name}", "tableau_waterfall")


# ---------------------------------------------------------------- Branch: Combo Chart
elif is_combo_chart:

    picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    player_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    bar_category = st.selectbox("Bar stat category (volume stat):", category_names, key="combo_bar_cat")
    bar_stats_in_cat = dict(categories)[bar_category]
    bar_label_choice = st.selectbox("Bar stat:", [label for _, label, _, _ in bar_stats_in_cat], key="combo_bar_stat")

    line_category = st.selectbox("Line stat category (rate stat):", category_names, key="combo_line_cat")
    line_stats_in_cat = dict(categories)[line_category]
    line_label_choice = st.selectbox("Line stat:", [label for _, label, _, _ in line_stats_in_cat], key="combo_line_stat")

    color_input = color_input_with_dropdown("combo_color_box")

    run = st.button("RUN", use_container_width=True) if picked_name else False

    if run:
        bar_stat = next(s for s in bar_stats_in_cat if s[1] == bar_label_choice)
        line_stat = next(s for s in line_stats_in_cat if s[1] == line_label_choice)

        if bar_stat[2] == "bradley_rating" or line_stat[2] == "bradley_rating" or bar_stat[2] not in ("base", "advanced", "calculated") or line_stat[2] not in ("base", "advanced", "calculated"):
            st.warning(
                "Combo Chart's career-trend view currently supports base/advanced/calculated stats "
                "only (the season-by-season table it's built on doesn't include defense-tracking, "
                "hustle, or clutch endpoints)."
            )
        else:
            with st.spinner("Looking up career seasons..."):
                seasons = get_player_career_seasons(player_id)

            if not seasons:
                st.error(f"Couldn't determine {picked_name}'s career span.")
            else:
                bar_values, line_values, valid_seasons = [], [], []
                with st.spinner(f"Downloading {len(seasons)} seasons of stats..."):
                    for s in reversed(seasons):  # oldest first, for a left-to-right trend
                        s_df = get_player_stats(s, per_mode="PerGame")
                        s_row = s_df[s_df["PLAYER_NAME"] == picked_name]
                        if not s_row.empty and bar_stat[0] in s_row.columns and line_stat[0] in s_row.columns:
                            bar_values.append(float(s_row.iloc[0][bar_stat[0]]))
                            line_values.append(float(s_row.iloc[0][line_stat[0]]))
                            valid_seasons.append(s)

                if not valid_seasons:
                    st.error(f"No matching seasons of data found for {picked_name}.")
                else:
                    line_is_pct = line_stat[0].endswith("_PCT")
                    combo_color = resolve_color_input(color_input) or DEFAULT_COLOR
                    fig = build_combo_chart(
                        valid_seasons, bar_values, line_values, bar_label_choice, line_label_choice,
                        combo_color, line_is_percentage=line_is_pct,
                    )
                    st.pyplot(fig)
                    offer_share_to_community(fig, f"Combo Chart -- {picked_name}", "share_combo")
                    add_to_tableau_dashboard(fig, f"Combo Chart -- {picked_name}", "tableau_combo")


# ---------------------------------------------------------------- Branch: Tornado Chart
elif is_tornado_chart:

    picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    player_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    chosen_category = st.selectbox("Stat category:", category_names)
    stats_in_category = dict(categories)[chosen_category]
    chosen_labels = st.multiselect(
        "Stats to compare against league average:", [label for _, label, _, _ in stats_in_category],
        default=[label for _, label, _, _ in stats_in_category][:5],
    )
    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    default_team = _default_color_team("player", picked_name, season)
    color_input = color_input_with_dropdown(f"tornado_color_box_{picked_name}_{season}", default_team)

    run = st.button("RUN", use_container_width=True) if (season and picked_name and chosen_labels) else False

    if run:
        chosen_stats = [s for s in stats_in_category if s[1] in chosen_labels]
        eligible = [s for s in chosen_stats if s[2] in ("base", "advanced", "calculated")]
        skipped = [s[1] for s in chosen_stats if s not in eligible]
        if skipped:
            st.caption(f"Skipped (not available for direct league-average comparison): {', '.join(skipped)}")

        if not eligible:
            st.warning("None of the selected stats can be compared this way -- pick base/advanced/calculated stats.")
        else:
            with st.spinner("Downloading stats..."):
                stats_df = get_player_stats(season, per_mode="PerGame")

            player_row = stats_df[stats_df["PLAYER_NAME"] == picked_name]
            if player_row.empty:
                st.error(f"No stats found for {picked_name} in {season}.")
            else:
                labels, diffs, any_pct = [], [], False
                for field, label, _, _ in eligible:
                    if field in stats_df.columns:
                        league_avg = stats_df[field].mean()
                        player_val = float(player_row.iloc[0][field])
                        labels.append(label.split(" (")[0])
                        diffs.append(player_val - league_avg)
                        if field.endswith("_PCT"):
                            any_pct = True

                tornado_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                fig = build_tornado_chart(labels, diffs, picked_name, tornado_color, is_percentage=False)
                st.pyplot(fig)
                offer_share_to_community(fig, f"Tornado -- {picked_name}", "share_tornado")
                add_to_tableau_dashboard(fig, f"Tornado -- {picked_name}", "tableau_tornado")


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
    color_input = color_input_with_dropdown("slope_color_box")

    run = st.button("RUN", use_container_width=True) if (before_season and after_season) else False

    if run:
        stat_field = chosen_stat[0]
        if chosen_stat[2] == "bradley_rating":
            st.warning("Bradley Rating stats aren't available for this comparison yet.")
        else:
            with st.spinner("Downloading both seasons..."):
                if mode == "player":
                    before_df = get_player_stats(before_season, per_mode="PerGame")
                    after_df = get_player_stats(after_season, per_mode="PerGame")
                else:
                    before_df = get_team_stats(before_season, per_mode="PerGame")
                    after_df = get_team_stats(after_season, per_mode="PerGame")

            name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
            if stat_field not in before_df.columns or stat_field not in after_df.columns:
                st.error(f"Couldn't find {chosen_stat_label} in the returned stats.")
            else:
                merged = before_df[[name_col, stat_field]].merge(
                    after_df[[name_col, stat_field]], on=name_col, suffixes=("_before", "_after"),
                )
                included_names = [n.strip() for n in included_input.split(",") if n.strip()] if included_input else []
                if included_names:
                    merged = merged[merged[name_col].isin(included_names)]
                else:
                    merged = merged.nlargest(int(top_n), f"{stat_field}_after")

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
                    offer_share_to_community(fig, "Slope Chart", "share_slope")
                    add_to_tableau_dashboard(fig, "Slope Chart", "tableau_slope")



# ---------------------------------------------------------------- Branch: Bar Chart
# ---------------------------------------------------------------- Branch: Radar Chart
elif is_radar_chart:

    picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    player_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None

    compare_toggle = st.checkbox("Compare against a second player")
    second_name = None
    if compare_toggle:
        second_name = st.selectbox("Second player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.", key="radar_p2")

    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    default_team = _default_color_team("player", picked_name, season)
    color_input = color_input_with_dropdown(f"radar_color_box_{picked_name}_{season}", default_team)

    run = st.button("RUN", use_container_width=True) if (season and picked_name and (not compare_toggle or second_name)) else False

    if run:
        with st.spinner("Downloading stats..."):
            stats_df = get_player_stats(season, per_mode="PerGame")

        # 5 categories, each backed by one representative stat already
        # present in get_player_stats()'s combined base+advanced table --
        # Defense combines steals and blocks into one simple sum rather
        # than picking just one, since neither alone captures "defense"
        # well on its own.
        radar_categories = [
            ("Scoring", "PTS"), ("Playmaking", "AST"), ("Rebounding", "REB"),
            ("Defense", None), ("Efficiency", "TS_PCT"),
        ]
        required_cols = {"PTS", "AST", "REB", "STL", "BLK", "TS_PCT", "PLAYER_NAME"}
        if not required_cols.issubset(stats_df.columns):
            st.error("Couldn't find all the stats this profile needs in the returned data.")
        else:
            stats_df = stats_df.copy()
            stats_df["_DEFENSE_COMBO"] = stats_df["STL"] + stats_df["BLK"]

            def player_percentiles(name):
                row = stats_df[stats_df["PLAYER_NAME"] == name]
                if row.empty:
                    return None
                percentiles = []
                for _, field in radar_categories:
                    col = "_DEFENSE_COMBO" if field is None else field
                    pct_rank = float((stats_df[col] < row.iloc[0][col]).mean() * 100)
                    percentiles.append(pct_rank)
                return percentiles

            p1_percentiles = player_percentiles(picked_name)
            if p1_percentiles is None:
                st.error(f"No stats found for {picked_name} in {season}.")
            else:
                p2_percentiles = player_percentiles(second_name) if second_name else None
                if second_name and p2_percentiles is None:
                    st.warning(f"No stats found for {second_name} in {season} -- showing {picked_name} alone.")

                radar_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                fig = build_radar_chart(
                    [c for c, _ in radar_categories], p1_percentiles, picked_name, radar_color,
                    second_percentiles=p2_percentiles, second_name=second_name,
                )
                st.pyplot(fig)
                title = f"Radar -- {picked_name}" + (f" vs {second_name}" if p2_percentiles else "")
                offer_share_to_community(fig, title, "share_radar")
                add_to_tableau_dashboard(fig, title, "tableau_radar")



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
    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    default_team_a = _default_color_team(mode, picked_name, season)
    default_team_b = _default_color_team(mode, second_name, season)
    color_input_a = color_input_with_dropdown(f"h2h_color_a_{mode}_{picked_name}_{season}", default_team_a)
    color_input_b = color_input_with_dropdown(f"h2h_color_b_{mode}_{second_name}_{season}", default_team_b)

    run = st.button("RUN", use_container_width=True) if (season and picked_name and second_name) else False

    if run:
        with st.spinner("Downloading stats..."):
            stats_df = get_player_stats(season, per_mode="PerGame") if mode == "player" else get_team_stats(season, per_mode="PerGame")

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
            offer_share_to_community(fig, title, "share_h2h")
            add_to_tableau_dashboard(fig, title, "tableau_h2h")



# ---------------------------------------------------------------- Branch: Bar Chart
# ---------------------------------------------------------------- Branch: Calendar Heat Map
elif is_calendar_heat_map:

    picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    player_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]
    chosen_category = st.selectbox("Stat category:", category_names)
    stats_in_category = dict(categories)[chosen_category]
    chosen_stat_label = st.selectbox("Stat:", [label for _, label, _, _ in stats_in_category])
    chosen_stat = next(s for s in stats_in_category if s[1] == chosen_stat_label)

    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    default_team = _default_color_team("player", picked_name, season)
    color_input = color_input_with_dropdown(f"calendar_color_box_{picked_name}_{season}", default_team)

    run = st.button("RUN", use_container_width=True) if (season and picked_name) else False

    if run:
        stat_field = chosen_stat[0]
        if chosen_stat[2] == "bradley_rating":
            st.warning("Bradley Rating stats aren't available on a per-game basis.")
        elif not player_id:
            st.warning("Pick a player first.")
        else:
            with st.spinner("Downloading game log..."):
                game_log = get_player_game_log(player_id, season)

            if stat_field not in game_log.columns:
                st.error(
                    f"{chosen_stat_label} isn't available on a per-game basis (advanced/bio stats are "
                    "season-level only) -- try a base counting stat like Points, Rebounds, or Assists."
                )
            elif game_log.empty:
                st.warning(f"No games found for {picked_name} in {season}.")
            else:
                cal_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                fig = build_calendar_heat_map(
                    game_log["GAME_DATE"].tolist(), game_log[stat_field].tolist(),
                    chosen_stat_label, picked_name, cal_color,
                )
                st.pyplot(fig)
                offer_share_to_community(fig, f"Calendar -- {picked_name}", "share_calendar")
                add_to_tableau_dashboard(fig, f"Calendar -- {picked_name}", "tableau_calendar")


# ---------------------------------------------------------------- Branch: Small Multiples
elif is_small_multiples:

    picked_names = st.multiselect(
        "Players (up to 9):", ALL_PLAYER_NAMES, max_selections=9,
    )
    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    color_input = color_input_with_dropdown("smallmult_color_box")

    run = st.button("RUN", use_container_width=True) if (season and len(picked_names) >= 2) else False

    if run:
        players_shots = []
        with st.spinner(f"Downloading shots for {len(picked_names)} players..."):
            for name in picked_names:
                pid = PLAYER_NAME_TO_RECORD[name]["id"]
                shots = get_player_shots(pid, season)
                if not shots.empty:
                    players_shots.append((name, shots))

        if not players_shots:
            st.error("No shot data found for any of the selected players in that season.")
        else:
            sm_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
            fig = build_small_multiples_shot_charts(players_shots, sm_color)
            st.pyplot(fig)
            title = f"Small Multiples -- {len(players_shots)} Players"
            offer_share_to_community(fig, title, "share_small_multiples")
            add_to_tableau_dashboard(fig, title, "tableau_small_multiples")


# ---------------------------------------------------------------- Branch: Court + Radar Hybrid
elif is_court_radar_hybrid:

    picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    player_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    default_team = _default_color_team("player", picked_name, season)
    color_input = color_input_with_dropdown(f"hybrid_color_box_{picked_name}_{season}", default_team)

    run = st.button("RUN", use_container_width=True) if (season and picked_name) else False

    if run:
        with st.spinner("Downloading shots..."):
            shots = get_player_shots(player_id, season)

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
            fig = build_court_radar_hybrid(shots, labels, values, picked_name, hybrid_color)
            st.pyplot(fig)
            title = f"Court + Radar Hybrid -- {picked_name}"
            offer_share_to_community(fig, title, "share_hybrid")
            add_to_tableau_dashboard(fig, title, "tableau_hybrid")


# ---------------------------------------------------------------- Branch: Shot Flow (Sankey)
elif is_sankey_flow:

    picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    player_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    default_team = _default_color_team("player", picked_name, season)
    color_input = color_input_with_dropdown(f"sankey_color_box_{picked_name}_{season}", default_team)
    st.caption(
        "Shows how shot attempts split by zone, then by outcome -- a scoped-down version of "
        "the fuller \"possession -> play type -> shot type -> outcome\" flow, since play-type-level "
        "possession data isn't available from this data source; zone-to-outcome is."
    )

    run = st.button("RUN", use_container_width=True) if (season and picked_name) else False

    if run:
        with st.spinner("Downloading shots..."):
            shots = get_player_shots(player_id, season)

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
            fig = build_sankey_flow(stage_labels, flows, sankey_color)
            st.pyplot(fig)
            title = f"Shot Flow -- {picked_name}"
            offer_share_to_community(fig, title, "share_sankey")
            add_to_tableau_dashboard(fig, title, "tableau_sankey")


# ---------------------------------------------------------------- Branch: Impact Clock
elif is_impact_clock:

    picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    player_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    default_team = _default_color_team("player", picked_name, season)
    color_input = color_input_with_dropdown(f"impactclock_color_box_{picked_name}_{season}", default_team)
    st.caption(
        "Adapted to clutch-vs-overall season stats (last 5 minutes, close games -- the NBA's own "
        "standard definition of \"clutch\"), since true minute-by-minute in-game data isn't "
        "available from this data source."
    )

    run = st.button("RUN", use_container_width=True) if (season and picked_name) else False

    if run:
        with st.spinner("Downloading overall and clutch stats..."):
            overall_df = get_player_stats(season, per_mode="PerGame")
            clutch_df = get_player_clutch_stats(season)

        overall_row = overall_df[overall_df["PLAYER_NAME"] == picked_name]
        clutch_row = clutch_df[clutch_df["PLAYER_NAME"] == picked_name] if "PLAYER_NAME" in clutch_df.columns else pd.DataFrame()

        if overall_row.empty:
            st.error(f"No stats found for {picked_name} in {season}.")
        elif clutch_row.empty:
            st.warning(f"No clutch-situation data found for {picked_name} in {season} (may not have played enough clutch minutes).")
        else:
            o, c = overall_row.iloc[0], clutch_row.iloc[0]
            overall_stats = {"PTS": f"{o['PTS']:.1f}", "FG%": f"{o['FG_PCT']:.1%}", "+/-": f"{o['PLUS_MINUS']:+.1f}"}
            clutch_stats = {"PTS": f"{c['PTS']:.1f}", "FG%": f"{c['FG_PCT']:.1%}", "+/-": f"{c['PLUS_MINUS']:+.1f}"}

            clock_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
            fig = build_impact_clock(overall_stats, clutch_stats, picked_name, clock_color)
            st.pyplot(fig)
            title = f"Impact Clock -- {picked_name}"
            offer_share_to_community(fig, title, "share_impact_clock")
            add_to_tableau_dashboard(fig, title, "tableau_impact_clock")


# ---------------------------------------------------------------- Branch: Bump Chart
elif is_bump_chart:

    picked_names = st.multiselect("Players to track (2-6):", ALL_PLAYER_NAMES, max_selections=6)

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
    color_input = color_input_with_dropdown("bump_color_box")

    run = st.button("RUN", use_container_width=True) if (most_recent_season and len(picked_names) >= 2) else False

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
                with st.spinner(f"Downloading {len(season_list)} seasons of league-wide stats..."):
                    for s in season_list:
                        s_df = get_player_stats(s, per_mode="PerGame") if mode == "player" else get_team_stats(s, per_mode="PerGame")
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
                    st.error("Not enough complete data across those seasons for at least 2 of the selected players.")
                else:
                    bump_color = resolve_color_input(color_input) or DEFAULT_COLOR
                    fig = build_bump_chart(season_list, complete_ranks, bump_color)
                    st.pyplot(fig)
                    title = f"Bump Chart -- {chosen_stat_label} Rank"
                    offer_share_to_community(fig, title, "share_bump")
                    add_to_tableau_dashboard(fig, title, "tableau_bump")


# ---------------------------------------------------------------- Branch: Passing Connections
elif is_court_connection:

    picked_name = st.selectbox("Player:", ALL_PLAYER_NAMES, index=None, placeholder="Enter player name.")
    player_id = PLAYER_NAME_TO_RECORD[picked_name]["id"] if picked_name else None
    season = st.selectbox("Season:", ALL_SEASONS, index=0)
    top_n = st.number_input("Show top __ passing connections:", min_value=3, max_value=10, value=5)
    default_team = _default_color_team("player", picked_name, season)
    color_input = color_input_with_dropdown(f"connection_color_box_{picked_name}_{season}", default_team)
    st.caption(
        "The honest version of a court \"connection\" map this data source can actually support: "
        "real passer-to-receiver volume and resulting makes, not literal spatial pass trajectories "
        "(not tracked anywhere in this data source) -- receivers are placed at representative court "
        "spots, not their real positions at the moment of each pass, which also isn't tracked."
    )

    run = st.button("RUN", use_container_width=True) if (season and picked_name) else False

    if run:
        with st.spinner("Downloading passing data..."):
            try:
                passes_df = get_player_passes(player_id, season)
            except Exception as e:
                passes_df = None
                st.error(f"Couldn't load passing data for {picked_name} in {season}: {e}")

        if passes_df is not None:
            if passes_df.empty or "PASS_TO" not in passes_df.columns:
                st.error(f"No passing data found for {picked_name} in {season}.")
            else:
                top_passes = passes_df.nlargest(int(top_n), "PASS")
                # PlayerDashPtPass, unlike most other endpoints in this
                # API, returns PASS_TO as "Last, First" (e.g. "Brown,
                # Jaylen") rather than "First Last" -- confirmed
                # directly from the live response, not assumed. Left
                # unreformatted, this also silently broke the receiver
                # headshot lookup just below, since
                # PLAYER_NAME_TO_RECORD is keyed by "First Last" and
                # would never match a "Last, First" string, always
                # falling back to the plain colored circle.
                def _reformat_last_first(name):
                    if "," in name:
                        last, first = (p.strip() for p in name.split(",", 1))
                        name = f"{first} {last}"
                    # PLAYER_NAME_TO_RECORD is keyed by accent-stripped
                    # names (see _load_all_players), so this needs the
                    # same treatment or a receiver like "Jokic, Nikola"
                    # would reformat to "Nikola Jokić" (accented) and
                    # still fail the lookup below.
                    return _strip_accents(name)

                receiver_names = [_reformat_last_first(n) for n in top_passes["PASS_TO"].tolist()]
                receiver_values = top_passes["PASS"].tolist()
                receiver_makes = top_passes["FGM"].tolist() if "FGM" in top_passes.columns else [0] * len(receiver_names)

                # PASS_TO names come from the passing endpoint itself,
                # not this app's own player list, so this looks each one
                # up defensively rather than assuming an exact match --
                # any receiver that doesn't resolve to a known player_id
                # just falls back to the plain colored circle instead of
                # a real headshot.
                passer_image_url = f"https://cdn.nba.com/headshots/nba/latest/1040x760/{player_id}.png"
                receiver_image_urls = []
                for name in receiver_names:
                    record = PLAYER_NAME_TO_RECORD.get(name)
                    receiver_image_urls.append(
                        f"https://cdn.nba.com/headshots/nba/latest/1040x760/{record['id']}.png" if record else None
                    )

                connection_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                fig = build_court_connection_map(
                    picked_name, receiver_names, receiver_values, receiver_makes, connection_color,
                    passer_image_url=passer_image_url, receiver_image_urls=receiver_image_urls,
                )
                st.pyplot(fig)
                title = f"Passing Connections -- {picked_name}"
                offer_share_to_community(fig, title, "share_connections")
                add_to_tableau_dashboard(fig, title, "tableau_connections")


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

    included_input = st.text_input(
        f"Enter {'player' if mode == 'player' else 'team'}(s) to include (comma separated, optional):"
    )

    season = st.selectbox("Season:", ALL_SEASONS, index=0)

    display_as = st.radio("Display As:", ["Vertical Bar", "Horizontal Bar", "Dot Plot"], horizontal=True)

    color_input = color_input_with_dropdown("bar_color_box")

    if season:
        run = st.button("RUN", use_container_width=True)
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
            with st.spinner("Downloading stats..."):
                stats_df = fetch_stats_for_source(stat_source, season, mode)

            if stat_field not in stats_df.columns:
                st.error(f"Couldn't find {stat_field} in the returned stats.")
            else:
                name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
                id_col = "PLAYER_ID" if mode == "player" else "TEAM_ID"
                leaderboard = stats_df.nlargest(int(top_n), stat_field)[[name_col, id_col, stat_field]]
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
                        stat_source=stat_source, is_percentage=is_pct,
                    )
                else:
                    fig = build_bar_chart(
                        leaderboard, stat_display_name=chosen_stat_label, season=season,
                        top_n=int(top_n), team_color=bar_team_color, included_names=included_names,
                        orientation="vertical" if display_as == "Vertical Bar" else "horizontal",
                        stat_source=stat_source, is_percentage=is_pct,
                    )
                st.pyplot(fig)
                offer_share_to_community(fig, "Bar Chart", "share_bar_chart")
                add_to_tableau_dashboard(fig, "Bar Chart", "tableau_bar_chart")


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
        run = st.button("RUN", use_container_width=True)
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
            with st.spinner("Downloading stats..."):
                stats_df = fetch_stats_for_source(stat_source, season, mode)

            if stat_field not in stats_df.columns:
                st.error(f"Couldn't find {stat_field} in the returned stats.")
            elif display_as == "Density Plot" and stats_df[stat_field].dropna().shape[0] < 5:
                st.warning("Not enough players with this stat to estimate a density curve.")
            else:
                is_pct = stat_field.endswith("_PCT")
                hist_color = resolve_color_input(color_input) if color_input else DEFAULT_COLOR
                values = stats_df[stat_field].dropna().tolist()
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
                offer_share_to_community(fig, "Histogram", "share_histogram")
                add_to_tableau_dashboard(fig, "Histogram", "tableau_histogram")


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
        run = st.button("RUN", use_container_width=True)
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
            with st.spinner("Downloading stats..."):
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
                    stats_df[stat_field].dropna().tolist(), stat_display_name=chosen_stat_label,
                    season=season, team_color=cumdist_color, is_percentage=is_pct,
                    highlight_value=highlight_value, highlight_name=highlight_input,
                )
                st.pyplot(fig)
                offer_share_to_community(fig, "Cumulative Distribution Plot", "share_cumdist")
                add_to_tableau_dashboard(fig, "Cumulative Distribution Plot", "tableau_cumdist")


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
        run = st.button("RUN", use_container_width=True)
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
            with st.spinner("Downloading stats..."):
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

                groups = {
                    team: sub[stat_field].dropna().tolist()
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
                    st.pyplot(fig)
                    offer_share_to_community(fig, "Box Plot", "share_box_plot")
                    add_to_tableau_dashboard(fig, "Box Plot", "tableau_box_plot")


# ---------------------------------------------------------------- Branch: Scatter Plot
elif is_scatter_plot:

    categories = get_stats_for_mode(mode, exclude_bradley_rating=True)
    category_names = [c for c, _ in categories]

    st.markdown("**First stat measurement (Y axis):**")
    y_category = st.selectbox("Category (Y):", category_names, key="y_cat")
    y_stats = dict(categories)[y_category]
    y_label = st.selectbox("Stat (Y):", [label for _, label, _, _ in y_stats], key="y_stat")

    st.markdown("**Second stat measurement (X axis):**")
    x_category = st.selectbox("Category (X):", category_names, key="x_cat")
    x_stats = dict(categories)[x_category]
    x_label = st.selectbox("Stat (X):", [label for _, label, _, _ in x_stats], key="x_stat")

    top_n = st.number_input("Display the top __ (ranked by Y axis):", min_value=1, max_value=499, value=10)

    included_input = st.text_input(
        f"Enter {'player' if mode == 'player' else 'team'}(s) to include (comma separated, optional):"
    )

    season = st.selectbox("Season:", ALL_SEASONS, index=0)

    # No color prompt -- Scatter Plot shows only player headshots or
    # team logos, matching bradley_analytics.py's is_scatter_plot
    # branch exactly.

    run = st.button("RUN", use_container_width=True) if season else False

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
            with st.spinner("Downloading stats..."):
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
                name_col = "PLAYER_NAME" if mode == "player" else "TEAM_NAME"
                leaderboard = stats_df.nlargest(int(top_n), y_field)[[name_col, id_col, y_field, x_field]]
                leaderboard.columns = ["name", "player_id", "y_value", "x_value"]
                if mode == "player":
                    leaderboard["image_url"] = leaderboard["player_id"].apply(get_player_headshot_url)
                else:
                    leaderboard["image_url"] = leaderboard["player_id"].apply(get_team_logo_url)

                included_names = [n.strip() for n in included_input.split(",") if n.strip()] if included_input else []
                leaderboard["is_included"] = leaderboard["name"].isin(included_names) if included_names else False

                fig = build_scatter_plot(leaderboard, stat_label_y=y_label, stat_label_x=x_label)
                st.pyplot(fig)
                offer_share_to_community(fig, "Scatter Plot", "share_scatter_plot")
                add_to_tableau_dashboard(fig, "Scatter Plot", "tableau_scatter_plot")

