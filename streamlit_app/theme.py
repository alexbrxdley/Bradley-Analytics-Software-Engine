"""
theme.py
--------
CSS injected into the Streamlit app to match the dark, serif,
glowing-title aesthetic shown in the mockup.
"""

CSS = """
<style>
.stApp {
    background-color: #0a0a0a;
    background-image: radial-gradient(circle at 50% 0%, #1a1a1a 0%, #0a0a0a 60%);
}

/* Serif glowing title */
.bradley-title {
    font-family: Georgia, 'Times New Roman', serif;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-align: center;
    font-size: 3.2rem;
    color: #f5f5f5;
    text-shadow: 0 0 18px rgba(255, 255, 255, 0.55), 0 0 40px rgba(255, 255, 255, 0.25);
    margin-bottom: 1.75rem;
}

.bradley-footer {
    text-align: center;
    color: #7a7a7a;
    font-size: 0.85rem;
    margin-top: 3rem;
}

.bradley-footer a {
    color: #9a9a9a;
    text-decoration: none;
}

/* Buttons: dark gradient, rounded, glow on hover */
.stButton > button {
    background: linear-gradient(180deg, #2a2a2a 0%, #101010 100%);
    color: #e5e5e5;
    border: 1px solid #4a4a4a;
    border-radius: 10px;
    font-family: Georgia, 'Times New Roman', serif;
    padding: 0.6rem 1rem;
    width: 100%;
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
}

.stButton > button:hover {
    border-color: #cfcfcf;
    box-shadow: 0 0 14px rgba(255, 255, 255, 0.35);
    color: #ffffff;
}

/* Text input, selectbox styling */
.stTextInput > div > div > input,
.stSelectbox > div > div,
.stMultiSelect > div > div {
    background-color: #141414;
    color: #e5e5e5;
    border: 1px solid #4a4a4a;
    border-radius: 10px;
    font-family: Georgia, 'Times New Roman', serif;
}

label, .stMarkdown, .stCaption {
    font-family: Georgia, 'Times New Roman', serif;
    color: #d8d8d8 !important;
}

.summary-pill {
    display: inline-block;
    background: #141414;
    border: 1px solid #4a4a4a;
    border-radius: 10px;
    padding: 0.5rem 1rem;
    margin: 0.2rem 0.3rem 0.2rem 0;
    color: #e5e5e5;
    font-family: Georgia, 'Times New Roman', serif;
}

.team-swatch {
    display: inline-block;
    width: 0.85rem;
    height: 0.85rem;
    border-radius: 3px;
    margin-left: 0.5rem;
    vertical-align: middle;
    border: 1px solid #666;
}
</style>
"""
