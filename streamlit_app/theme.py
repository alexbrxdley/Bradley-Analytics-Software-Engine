"""
theme.py
--------
CSS injected into the Streamlit app.

Background: a small, vector-generated (SVG feTurbulence) grain texture
tiled at native size behind a radial gradient. Earlier versions used
the user's raster background image stretched with `background-size:
cover`, which blurred the grain on any screen bigger than the source
image. Tiling a small vector texture instead means it never gets
scaled up, so it can't blur regardless of screen size.

Title: Kalnia Medium (weight 500), forced to stay on a single line.

Toggle: the Player/Team switch is NOT Streamlit's native st.radio.
Reskinning st.radio with CSS proved unreliable because its internal
DOM/class names aren't a stable target. Instead, app.py renders it as
two real st.button() widgets inside st.container(key=...) wrappers,
and this stylesheet is rebuilt on every rerun with the "active" class
applied to whichever one matches the current session_state -- a
proper segmented control, not a re-painted radio input.
"""

import base64

# Small tileable grain texture. Rendered as an SVG filter so it's
# vector-based -- tiling it small means the browser never stretches
# individual pixels, so there's no blur at any screen size.
_NOISE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
    '<filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.85" '
    'numOctaves="2" stitchTiles="stitch"/>'
    '<feColorMatrix type="saturate" values="0"/></filter>'
    '<rect width="100%" height="100%" filter="url(#n)" opacity="0.06"/>'
    "</svg>"
)


def _noise_data_uri() -> str:
    encoded = base64.b64encode(_NOISE_SVG.encode()).decode()
    return f"data:image/svg+xml;base64,{encoded}"


def build_css(active_mode: str = "Player", active_view: str = "Dashboard") -> str:
    """
    Build the full stylesheet. active_mode/active_view control which
    option is highlighted in each segmented control, so this must be
    called (and re-injected) on every rerun.
    """
    noise_uri = _noise_data_uri()

    player_style = _pill_style(active=(active_mode == "Player"))
    team_style = _pill_style(active=(active_mode == "Team"))

    view_keys = {
        "Dashboard": "view-dashboard",
        "Select visualization": "view-select",
        "Custom dashboard": "view-custom",
    }
    view_rules = "\n".join(
        f".st-key-{key} {{ {_pill_style(active=(name == active_view))} }}\n"
        f".st-key-{key} button {{ color: {'#f5f5f5' if name == active_view else '#9a9a9a'}; }}"
        for name, key in view_keys.items()
    )

    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Kalnia:wght@400;500;600;700&family=Playfair+Display:wght@500;600;700&display=swap');

.stApp {{
    background-color: #0a0a0a;
    background-image:
        radial-gradient(circle at 50% 0%, #1c1c1c 0%, #0a0a0a 65%),
        url("{noise_uri}");
    background-size: auto, 200px 200px;
    background-position: center, top left;
    background-repeat: no-repeat, repeat;
}}

header[data-testid="stHeader"] {{
    background: transparent !important;
}}

#MainMenu {{
    visibility: hidden !important;
}}

/* Playfair Display Medium everywhere by default */
html, body, [class*="css"], .stMarkdown, .stCaption, .stText,
label, p, span, div {{
    font-family: 'Playfair Display', serif;
    font-weight: 500;
}}

/* Numbers (season years, stats, etc.) use Times New Roman */
.numbers-font, .numbers-font input, .numbers-font div,
.st-key-season-select, .st-key-season-select div, .st-key-season-select span {{
    font-family: 'Times New Roman', Times, serif !important;
    font-weight: 400 !important;
}}

/* Kalnia Medium title, forced to a single line */
.bradley-title {{
    font-family: 'Kalnia', serif;
    font-weight: 500;
    letter-spacing: 0.06em;
    text-align: center;
    white-space: nowrap;
    font-size: clamp(1.6rem, 4.6vw, 3.2rem);
    color: #f5f5f5;
    text-shadow: 0 0 18px rgba(255, 255, 255, 0.55), 0 0 40px rgba(255, 255, 255, 0.25);
    margin-bottom: 1.75rem;
}}

.bradley-footer {{
    text-align: center;
    color: #7a7a7a;
    font-size: 0.85rem;
    margin-top: 3rem;
    font-family: 'Playfair Display', serif;
}}

.bradley-footer a {{
    color: #9a9a9a;
    text-decoration: none;
}}

/* Buttons: dark gradient, rounded, glow on hover */
.stButton > button {{
    background: linear-gradient(180deg, #2a2a2a 0%, #101010 100%);
    color: #e5e5e5;
    border: 1px solid #4a4a4a;
    border-radius: 10px;
    font-family: 'Playfair Display', serif;
    font-weight: 600;
    padding: 0.6rem 1rem;
    width: 100%;
    transition: box-shadow 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}}

.stButton > button:hover {{
    border-color: #cfcfcf;
    box-shadow: 0 0 14px rgba(255, 255, 255, 0.35);
    color: #ffffff;
}}

/* Text input, selectbox, multiselect styling */
.stTextInput > div > div > input,
.stSelectbox > div > div,
.stMultiSelect > div > div {{
    background-color: #141414;
    color: #e5e5e5;
    border: 1px solid #4a4a4a;
    border-radius: 10px;
    font-family: 'Playfair Display', serif;
}}

.summary-pill {{
    display: inline-block;
    background: #141414;
    border: 1px solid #4a4a4a;
    border-radius: 10px;
    padding: 0.5rem 1rem;
    margin: 0.2rem 0.3rem 0.2rem 0;
    color: #e5e5e5;
    font-family: 'Playfair Display', serif;
}}

.team-swatch {{
    display: inline-block;
    width: 0.85rem;
    height: 0.85rem;
    border-radius: 3px;
    margin-left: 0.5rem;
    vertical-align: middle;
    border: 1px solid #666;
}}

/* ---- Segmented Player/Team control ----
   Two real buttons, wrapped in keyed containers so this stylesheet
   can target each one individually and mark whichever is active. */
.st-key-toggle-row {{
    display: flex;
    justify-content: center;
    margin-bottom: 1.25rem;
}}

.st-key-toggle-player button, .st-key-toggle-team button {{
    background: transparent;
    border: none;
    border-radius: 0;
    color: #9a9a9a;
    font-weight: 600;
    box-shadow: none;
    padding: 0.6rem 2.2rem;
}}

.st-key-toggle-player {{
    border: 1px solid #4a4a4a;
    border-radius: 10px 0 0 10px;
    border-right: none;
    {player_style}
}}

.st-key-toggle-team {{
    border: 1px solid #4a4a4a;
    border-radius: 0 10px 10px 0;
    {team_style}
}}

.st-key-toggle-player button {{ color: {"#f5f5f5" if active_mode == "Player" else "#9a9a9a"}; }}
.st-key-toggle-team button {{ color: {"#f5f5f5" if active_mode == "Team" else "#9a9a9a"}; }}

/* ---- Dashboard / Select visualization / Custom dashboard control ---- */
.st-key-view-dashboard button, .st-key-view-select button, .st-key-view-custom button {{
    background: transparent;
    border: none;
    box-shadow: none;
    font-weight: 600;
    padding: 0.55rem 1.2rem;
}}

.st-key-view-dashboard {{
    border: 1px solid #4a4a4a;
    border-radius: 10px 0 0 10px;
    border-right: none;
}}

.st-key-view-select {{
    border: 1px solid #4a4a4a;
    border-top: none;
    border-bottom: none;
}}

.st-key-view-custom {{
    border: 1px solid #4a4a4a;
    border-radius: 0 10px 10px 0;
    border-left: none;
}}

{view_rules}
</style>
"""


def _pill_style(active: bool) -> str:
    """Inline CSS declarations for one half of the toggle, active or not."""
    if active:
        return (
            "background: linear-gradient(180deg, #3a3a3a 0%, #161616 100%); "
            "box-shadow: 0 0 14px rgba(255, 255, 255, 0.3);"
        )
    return "background: #0e0e0e;"
