"""
theme.py
--------
CSS injected into the Streamlit app: the exact background texture the
user supplied, Kalnia for the title, Playfair Display (medium) for
everything else, Times New Roman for numeric content, and a
modernized pill-style toggle for the Player/Team switch (replacing
Streamlit's default orange radio dot).
"""

import base64
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_BACKGROUND_PATH = _ASSETS_DIR / "background.jpg"


def _background_data_uri() -> str:
    """Base64-embed the background image so no static file serving is needed."""
    data = _BACKGROUND_PATH.read_bytes()
    encoded = base64.b64encode(data).decode()
    return f"data:image/jpeg;base64,{encoded}"


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Kalnia:wght@400;600;700&family=Playfair+Display:wght@500;600;700&display=swap');

.stApp {{
    background-image: url("{_background_data_uri()}");
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
    background-repeat: no-repeat;
    background-color: #0a0a0a;
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

/* Serif glowing title, Kalnia */
.bradley-title {{
    font-family: 'Kalnia', serif;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-align: center;
    font-size: 3.2rem;
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
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
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

/* ---- Modernized Player/Team toggle ---- */
/* Streamlit renders st.radio as a BaseWeb radiogroup with a colored
   dot per option. We hide the native dot entirely and restyle each
   label as a segmented pill button instead. */
div[role="radiogroup"] {{
    gap: 0.6rem;
}}

div[role="radiogroup"] label {{
    background: linear-gradient(180deg, #202020 0%, #0e0e0e 100%);
    border: 1px solid #4a4a4a;
    border-radius: 10px;
    padding: 0.55rem 1.8rem;
    cursor: pointer;
    transition: box-shadow 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}}

div[role="radiogroup"] label:hover {{
    border-color: #8a8a8a;
}}

/* Hide the native radio dot (first inner div of each label) */
div[role="radiogroup"] label > div:first-child {{
    display: none;
}}

/* Highlight the selected pill */
div[role="radiogroup"] label:has(input:checked) {{
    border-color: #e5e5e5;
    background: linear-gradient(180deg, #3a3a3a 0%, #161616 100%);
    box-shadow: 0 0 14px rgba(255, 255, 255, 0.3);
}}

div[role="radiogroup"] label p {{
    font-family: 'Playfair Display', serif;
    font-weight: 600;
    color: #e5e5e5 !important;
    margin: 0;
}}
</style>
"""
