# Bradley Analytics — Streamlit Dashboard

Live, browser-based version of the Bradley Analytics Software Engine. Pick
any active NBA player, a year, and Regular Season/Playoffs, then generate an
interactive Plotly shot chart or shooting heat map — pulled live from the
NBA API, with the court geometry and colors matching the desktop (R/ggplot2)
version.

## Run locally

```bash
cd streamlit_app
python -m venv venv
# Windows: .\venv\Scripts\Activate.ps1
# Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Files

```
streamlit_app/
├── streamlit_app.py       # the app itself
├── requirements.txt
├── .streamlit/
│   └── config.toml        # dark theme — controls native widget contrast
├── .gitignore
└── README.md
```

`.streamlit/config.toml` is what keeps every native Streamlit widget
(dropdowns, buttons, radio, spinner) readable against the black background —
the CSS block inside `streamlit_app.py` only handles fonts, the title glow,
and the gradient/grain flourish on top of that.

## Notes

- Shot data comes live from `stats.nba.com` via `nba_api`. That endpoint can
  occasionally be slow or rate-limited — it's normally reliable from a home
  connection, less so from some cloud/shared hosting environments (worth
  knowing if you deploy this to Streamlit Community Cloud).
- No local image assets — the gradient/grain background is generated with
  pure CSS + inline SVG noise, so there's nothing extra to track in git.
