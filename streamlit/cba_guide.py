"""
cba_guide.py

Front Office > CBA Guide: an in-depth, salary-cap focused guide to the NBA's 2023 Collective Bargaining Agreement,
written for the three people who care about it: the front office (what it can and can't do), the coaching staff
(how the rules reach the court) and fans (why teams do what they do).

One public function:

    render(team_name, team_color, team_payrolls)

team_name      e.g. "Boston Celtics"
team_color     that team's hex colour, used only for the "your team" pieces (gold is the house accent everywhere else)
team_payrolls  {"2026-27": 187_500_000, ...}: the team's committed salary per season (may be empty or partial)

Everything is drawn with st.markdown: inline HTML plus inline SVG charts built here (no plotting library). Each SVG
chart is built twice, a wide version for desktop and a narrow one for phones, and CSS shows the right one, so text
stays readable at 360px. The only widgets are the small luxury-tax calculator's slider and radio (keys start with
"cba_"). No network calls: every figure is a constant below, checked against the sources listed next. Importing the
module has no side effects.

Money is written two ways on purpose: official league figures to the thousand ($164.961M), rounded or computed
figures to one decimal ($14.1M). Dollar signs are emitted as &#36; so Streamlit's markdown never reads a pair of
them as LaTeX.
"""

# ------------------------------------------------------------------------------------------------------------------
# Sources (checked 2026-09-29)
#   The 2023 CBA itself (the PDF shipped at assets/NBA-Collective-Bargaining-Agreement.pdf): cap formula (Art. VII
#     Sec. 2(a)), 121.5% tax level, apron indexing, 90% floor and its penalties, 10% growth limit (Sec. 2(a)(6)),
#     tax brackets and rates incl. the new rates from 2025-26 (Sec. 2(d)), Transaction Restrictions Table (Sec. 2(e)),
#     draft pick penalty (Sec. 2(f)), exceptions (Sec. 6), traded player exceptions and salary matching (Sec. 6(j)),
#     trade rules and 5.15% cash limit (Sec. 8), raises (Sec. 5), extensions (Sec. 7), max salary tiers (Art. II
#     Sec. 7), contract length (Art. IX), cap holds (Art. VII Sec. 4(d)), two-way rules (Art. II Sec. 11), roster
#     size and postseason eligibility (Art. XXIX), 65-game award rule (Art. XXIX Sec. 6), BRI 49-51% share, term and
#     2029 opt-out (Art. XXXIX), free agency timing (Art. XI).
#   https://www.nba.com/news/nba-salary-cap-2026-27-season           2026-27 cap/tax/aprons/floor/MLEs
#   https://pr.nba.com/nba-salary-cap-2025-26-season                   2025-26 cap/tax/aprons/floor/MLEs
#   https://bleacherreport.com/articles/25448479-2026-27-nba-salary-cap-1st-and-2nd-aprons-luxury-tax-levels-revealed-fa
#   https://www.salaryswish.com/bi-annual-exception                    2026-27 BAE $5,477,000
#   https://www.salaryswish.com/maximum-salary-faq                     max salaries 2025-26 / 2026-27
#   https://www.salaryswish.com/luxury-tax                             2026-27 tax brackets ($6.064M) and rates
#   https://www.salaryswish.com/salary-cap                             cap / tax / apron history
#   https://basketball.realgm.com/nba/info/salary_cap                  cap / tax / apron history
#   https://www.salaryswish.com/minimum-salary-calculator/2026         2025-26 minimums
#   https://www.yardbarker.com/nba/articles/nba_minimum_salaries_for_202627/s1_14822_44016395   2026-27 minimums
#   https://www.yardbarker.com/nba/articles/rookie_scale_salaries_for_2026_nba_first_round_picks/s1_14822_44021884
#   https://www.nbcnewyork.com/nba/nba-key-dates-2026-27-opening-night-trade-deadline-finals/6535379/   2026-27 dates
#   https://www.yardbarker.com/nba/articles/decision_day_arrives_for_nba_players_on_non_guaranteed_deals/s1_17038_43299119
#   https://basketball.realgm.com/analysis/249279/CBA-Encyclopedia-Stepien-Rule
#   https://sports.betmgm.com/en/blog/nba/how-many-years-of-picks-can-be-traded-nba-explanation-bm06/
# Derived (from the CBA's own formulas, labelled "about" in the UI): the 2026-27 trade-matching cushion ($7.5M x
# cap / 2023-24 cap = about $9.1M), the 2025-26 tax bracket ($5.685M) and the 2026-27 cash-in-trades limit.
# ------------------------------------------------------------------------------------------------------------------

import html as _html
import math
import re

import streamlit as st

from salary_table import CAP_FIGURES

# ---------------------------------------------------------------------------------------------------- the numbers
CUR = "2026-27"
PREV = "2025-26"
CAP_2023_24 = 136_021_000            # every indexed amount in the 2023 CBA is scaled by cap / this

MIN_TEAM_SALARY = {"2025-26": 139_182_000, "2026-27": 148_465_000}

# season, cap, tax, apron (the single pre-2023 apron, then the 1st apron), 2nd apron (from 2023-24)
_HISTORY = [
    ("2015-16", 70_000_000, 84_740_000, 88_740_000, None),
    ("2016-17", 94_143_000, 113_287_000, 117_287_000, None),
    ("2017-18", 99_093_000, 119_266_000, 125_266_000, None),
    ("2018-19", 101_869_000, 123_733_000, 129_817_000, None),
    ("2019-20", 109_140_000, 132_627_000, 138_928_000, None),
    ("2020-21", 109_140_000, 132_627_000, 138_928_000, None),
    ("2021-22", 112_414_000, 136_606_000, 143_002_000, None),
    ("2022-23", 123_655_000, 150_267_000, 156_983_000, None),
    ("2023-24", 136_021_000, 165_294_000, 172_346_000, 182_794_000),
    ("2024-25", 140_588_000, 170_814_000, 178_132_000, 188_931_000),
]

# label, 2025-26, 2026-27
EXCEPTION_VALUES = [
    ("Non-taxpayer MLE", 14_104_000, 15_044_000),
    ("Room MLE", 8_781_000, 9_366_000),
    ("Taxpayer MLE", 5_685_000, 6_064_000),
    ("Bi-annual exception", 5_134_000, 5_477_000),
    ("Veteran minimum (10+ yrs)", 3_634_153, 3_876_529),
    ("Rookie minimum", 1_272_870, 1_357_763),
    ("Two-way salary", 636_435, 678_882),
]

# 2026-27 minimum salary by years of service (0 ... 10+)
MIN_SCALE_CUR = [1_357_763, 2_185_116, 2_449_421, 2_537_526, 2_625_627, 2_845_883, 3_066_143, 3_286_399,
                 3_506_659, 3_524_115, 3_876_529]
MAX_PCT = {"0-6": 0.25, "7-9": 0.30, "10+": 0.35}
ROOKIE_NO1_CUR = 14_748_000          # 2026 No. 1 pick, first season, at 120% of scale
ROOKIE_NO30_CUR = 2_926_800          # 2026 No. 30 pick, first season, at 120% of scale

TAX_STANDARD = [1.00, 1.25, 3.50, 4.75]   # from 2025-26; +$0.50 per further bracket
TAX_REPEATER = [3.00, 3.25, 5.50, 6.75]
CASH_PCT = 0.0515
TRADE_DEADLINE = "Thursday, Feb. 11, 2027"
OPENING_NIGHT = "Tuesday, Oct. 20, 2026"

# ------------------------------------------------------------------------------------------------------ the look
GOLD, GOLD_L = "#D4AF37", "#F5D370"
INK, BODY, SUB, MUTED = "#ffffff", "#e6e6e6", "#b8b8b8", "#8f8f8f"
GRID, AXIS, SURF = "#2c2c2c", "#3a3a3a", "#141414"
C_FLOOR, C_CAP, C_TAX, C_AP1, C_AP2 = "#8f8f8f", "#3987e5", GOLD, "#d95926", "#9085e9"
C_PREV, C_REPEAT, C_OK, C_NO = "#6b6b6b", "#e66767", "#0ca30c", "#d03b3b"
FONT = "Arial, sans-serif"

# desktop / phone versions of each SVG chart: viewBox width and base font size
_DESK = {"w": 960, "fs": 14, "tick": 13}
_MOB = {"w": 340, "fs": 14, "tick": 13}

_CSS = """<style>
.cba{font-family:Arial,sans-serif;color:#e6e6e6}
.cba p{margin:0 0 .75em;line-height:1.55;font-size:.88rem;color:#e6e6e6}
.cba ul{margin:.1em 0 .9em 1.15em;padding:0}
.cba li{margin:.28em 0;line-height:1.5;font-size:.88rem;color:#e6e6e6}
.cba b{color:#ffffff}
.cba .g{color:#F5D370}
.cba-lead{border-left:3px solid #D4AF37;padding:4px 0 4px 14px;margin:4px 0 16px}
.cba-lead p{font-size:.95rem}
.cba-card{background:#141414;border:1px solid #2a2a2a;border-radius:8px;padding:14px 16px 12px;margin:10px 0 20px}
.cba-ct{font-size:.86rem;font-weight:700;color:#ffffff;margin:0 0 2px;line-height:1.35}
.cba-cs{font-size:.72rem;color:#9a9a9a;margin:0 0 10px;line-height:1.4}
.cba-note{font-size:.72rem;color:#9a9a9a;line-height:1.45;margin:8px 0 0}
.cba-d{display:block}.cba-m{display:none}
.cba svg{display:block;width:100%;height:auto;overflow:visible}
.cba-lg{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.72rem;color:#c9c9c9;margin:0 0 8px}
.cba-lg span{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.cba-lg .sw{display:inline-block;width:12px;height:12px;border-radius:3px}
.cba-lg .ln{display:inline-block;width:16px;height:3px;border-radius:2px}
.cba-tiles{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin:6px 0 18px}
.cba-tile{background:#141414;border:1px solid #2a2a2a;border-radius:8px;padding:10px 12px;min-width:0}
.cba-tile .k{font-size:.68rem;color:#a8a8a8;letter-spacing:.02em;display:flex;align-items:center;gap:6px}
.cba-tile .k .sw{display:inline-block;width:10px;height:10px;border-radius:2px;flex:0 0 auto}
.cba-tile .v{font-size:1.1rem;color:#ffffff;font-weight:700;margin-top:4px;white-space:nowrap}
.cba-tile .s{font-size:.66rem;color:#8f8f8f;margin-top:2px}
.cba-tile .v.sm{font-size:.9rem;line-height:1.3}
.cba-toc{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 22px}
.cba-toc a{font-size:.72rem;color:#e6e6e6 !important;text-decoration:none !important;border:1px solid #333;
 border-radius:999px;padding:4px 11px;background:#121212}
.cba-toc a:hover{border-color:#D4AF37;color:#F5D370 !important}
.cba-tw{width:100%;overflow-x:auto;margin:6px 0 18px}
.cba-t{width:100%;border-collapse:collapse;font-family:Arial,sans-serif;font-size:.76rem}
.cba-t th{text-align:left;font-weight:700;padding:8px 10px;border-bottom:1px solid #3a3a3a;white-space:nowrap}
.cba-t td{padding:8px 10px;border-bottom:1px solid #262626;vertical-align:top;color:#e6e6e6;line-height:1.45}
.cba-t td.n{white-space:nowrap;font-variant-numeric:tabular-nums}
.cba-t tr:last-child td{border-bottom:none}
.cba-t td:first-child{color:#ffffff;font-weight:700}
.cba .cba-t,.cba .cba-t th,.cba .cba-t td{border-left:none !important;border-right:none !important;
 border-top:none !important;background:transparent}
.cba .cba-t{border:none !important;margin:0}
.cba-mx th{white-space:normal;vertical-align:bottom}
.cba-mx td{vertical-align:middle}
.cba-pill.x{background:rgba(255,255,255,.05);color:#9a9a9a;border:1px solid #3a3a3a}
.cba-pill{display:inline-block;font-size:.66rem;font-weight:700;padding:2px 8px;border-radius:999px;white-space:nowrap}
.cba-pill.y{background:rgba(12,163,12,.16);color:#6fdc6f;border:1px solid rgba(12,163,12,.45)}
.cba-pill.n{background:rgba(208,59,59,.16);color:#ff8d8d;border:1px solid rgba(208,59,59,.5)}
.cba-pill.c{background:rgba(212,175,55,.14);color:#F5D370;border:1px solid rgba(212,175,55,.45)}
.cba-hb{margin:4px 0 2px}
.cba-hb-row{display:grid;grid-template-columns:minmax(0,210px) minmax(0,1fr);gap:4px 14px;align-items:center;
 padding:7px 0;border-bottom:1px solid #222}
.cba-hb-row:last-child{border-bottom:none}
.cba-hb-l{font-size:.76rem;color:#ffffff;font-weight:700;line-height:1.3}
.cba-hb-l small{display:block;font-weight:400;color:#9a9a9a;font-size:.66rem;margin-top:2px}
.cba-hb-b{display:flex;align-items:center;gap:8px;margin:2px 0;min-width:0}
.cba-hb-b .bar{height:12px;border-radius:0 4px 4px 0;flex:0 0 auto;min-width:2px}
.cba-hb-b .val{font-size:.7rem;color:#e6e6e6;white-space:nowrap;font-variant-numeric:tabular-nums}
.cba-hb-b .val em{font-style:normal;color:#8f8f8f}
.cba-flow{display:flex;flex-wrap:wrap;align-items:stretch;gap:8px;margin:4px 0 6px}
.cba-flow .st{flex:1 1 150px;background:#101010;border:1px solid #2e2e2e;border-radius:8px;padding:10px 12px;min-width:0}
.cba-flow .st .h{font-size:.7rem;font-weight:700;color:#ffffff;margin-bottom:4px}
.cba-flow .st .b{font-size:.68rem;color:#bdbdbd;line-height:1.45}
.cba-flow .ar{align-self:center;color:#D4AF37;font-size:1rem;flex:0 0 auto}
.cba-flow .st.hot{border-color:#9085e9;box-shadow:inset 3px 0 0 #9085e9}
.cba-flow .st.end{border-color:#D4AF37;box-shadow:inset 3px 0 0 #D4AF37}
.cba-tl{position:relative;margin:4px 0 8px 6px;padding-left:18px;border-left:2px solid #2e2e2e}
.cba-tl-i{position:relative;padding:0 0 14px}
.cba-tl-i:before{content:"";position:absolute;left:-25px;top:4px;width:10px;height:10px;border-radius:50%;
 background:#D4AF37;box-shadow:0 0 0 3px #141414}
.cba-tl-i.soft:before{background:#6b6b6b}
.cba-tl-d{font-size:.72rem;font-weight:700;color:#F5D370}
.cba-tl-t{font-size:.8rem;font-weight:700;color:#ffffff;margin-top:1px}
.cba-tl-x{font-size:.72rem;color:#bdbdbd;line-height:1.45;margin-top:2px}
.cba-3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:6px 0 20px}
.cba-3 .cba-card{margin:0}
.cba-3 h5{font-family:Arial,sans-serif !important;font-size:.86rem;font-weight:700 !important;margin:0 0 8px;
 padding:0}
.cba-3 li{font-size:.78rem}
.cba-gl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 28px;margin:4px 0 12px}
.cba-gl div{padding:9px 0;border-bottom:1px solid #232323;font-size:.78rem;line-height:1.5;color:#d6d6d6}
.cba-gl b{color:#F5D370}
.cba details{margin:8px 0 0}
.cba summary{cursor:pointer;font-size:.72rem;color:#b8b8b8}
.cba summary:hover{color:#F5D370}
@media (max-width:900px){.cba-tiles{grid-template-columns:repeat(3,minmax(0,1fr))}
 .cba-3{grid-template-columns:1fr}}
@media (max-width:640px){
 .cba-d{display:none}.cba-m{display:block}
 .cba p,.cba li{font-size:.8rem}
 .cba-tiles{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
 .cba-tile .v{font-size:.86rem}
 .cba-card{padding:12px 12px 10px}
 .cba-hb-row{grid-template-columns:1fr}
 .cba-gl{grid-template-columns:1fr}
 .cba-t.stack thead{display:none}
 .cba-t.stack,.cba-t.stack tbody,.cba-t.stack tr,.cba-t.stack td{display:block;width:100%}
 .cba-t.stack tr{border-bottom:1px solid #333;padding:6px 0}
 .cba-t.stack td{border:none;padding:3px 2px;white-space:normal}
 .cba-t.stack td:before{content:attr(data-l);display:block;font-size:.62rem;color:#8f8f8f;font-weight:400;
  text-transform:uppercase;letter-spacing:.04em}
 .cba-t.stack td:first-child:before{display:none}
 .cba-t.stack td:first-child{font-size:.84rem;padding-top:6px}
 .cba-t.stack td.n{display:inline-block;width:48%;vertical-align:top}
 .cba-mx th,.cba-mx td{padding:6px 3px;font-size:.62rem}
 .cba-mx td:first-child{font-size:.66rem;padding-right:6px}
 .cba-mx .cba-pill{padding:1px 6px;font-size:.58rem}
 .cba-t.tight th,.cba-t.tight td{padding:6px 5px;font-size:.68rem}
 .cba-t.tight th{white-space:normal}
 .cba-flow{flex-direction:column}
 .cba-flow .st{flex:0 0 auto}
 .cba-flow .ar{transform:rotate(90deg);line-height:1}
 .cba-lg span{white-space:normal}
 .cba-tile .v.sm{font-size:.82rem}
}
</style>"""


# ------------------------------------------------------------------------------------------------- small helpers
def _e(s):
    return _html.escape(str(s), quote=True)


def _m(v, d=3):
    """$164.961M (d=3, official figures) or $14.1M (d=1, rounded/computed). HTML-safe dollar sign."""
    if v is None:
        return "n/a"
    sign = "-" if v < 0 else ""
    return f"{sign}&#36;{abs(v) / 1e6:,.{d}f}M"


def _m_plain(v, d=1):
    """Plain-text money for SVG <title> tooltips (no entities needed inside title)."""
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v) / 1e6:,.{d}f}M"


def _pct(v, d=1):
    return f"{v * 100:.{d}f}%"


def _html_block(s):
    """st.markdown treats a blank line as the end of an HTML block, so emit one line."""
    st.markdown(re.sub(r"\s*\n\s*", " ", s), unsafe_allow_html=True)


def _prose(*parts):
    _html_block('<div class="cba">' + "".join(parts) + "</div>")


def _p(text):
    return f"<p>{text}</p>"


def _ul(items):
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def _hex_rgb(h):
    h = (h or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        return None
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(rgb):
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _readable_team_color(color):
    """The team colour, lightened toward white until it clears 3:1 against the dark chart surface (a black or navy
    team colour would otherwise vanish). Falls back to gold for anything unparseable."""
    rgb = _hex_rgb(color)
    if rgb is None:
        return GOLD
    surf = _lum(_hex_rgb(SURF))
    for t in [i / 20 for i in range(0, 17)]:
        mixed = tuple(round(c + (255 - c) * t) for c in rgb)
        if (_lum(mixed) + 0.05) / (surf + 0.05) >= 3.0:
            return "#%02x%02x%02x" % mixed
    return GOLD


def _text_on(color):
    rgb = _hex_rgb(color) or (212, 175, 55)
    return "#111111" if (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) > 160 else "#ffffff"


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_") or "team"


def _season_start(s):
    m = re.match(r"^\s*(\d{4})", str(s))
    return int(m.group(1)) if m else None


def _season_name(y):
    return f"{y}-{str(y + 1)[-2:]}"


def _history():
    """Cap / tax / apron / 2nd apron by season, 2015-16 on, with the two current seasons taken from CAP_FIGURES."""
    rows = {r[0]: r for r in _HISTORY}
    for s, f in CAP_FIGURES.items():
        rows[s] = (s, f["cap"], f["tax"], f["apron1"], f["apron2"])
    return [rows[s] for s in sorted(rows)]


def _figs(season):
    """{cap, tax, apron1, apron2, floor?} for a season with two aprons (2023-24 on), else None."""
    if season in CAP_FIGURES:
        f = dict(CAP_FIGURES[season])
    else:
        row = next((r for r in _HISTORY if r[0] == season and r[4]), None)
        if row is None:
            return None
        f = {"cap": row[1], "tax": row[2], "apron1": row[3], "apron2": row[4]}
    if season in MIN_TEAM_SALARY:
        f["floor"] = MIN_TEAM_SALARY[season]
    return f


def _indexed(amount_2023, season):
    """An amount the CBA states for 2023-24 and indexes to the cap, for a later season."""
    f = CAP_FIGURES.get(season)
    return amount_2023 * f["cap"] / CAP_2023_24 if f else None


def _bracket(season=CUR):
    return _indexed(5_000_000, season)


def _tax_rate(i, repeater):
    base = TAX_REPEATER if repeater else TAX_STANDARD
    return base[i] if i < len(base) else base[-1] + 0.5 * (i - len(base) + 1)


def tax_bill(over, repeater=False, season=CUR):
    """Luxury tax owed on `over` dollars above the tax line (2025-26 rates and later)."""
    if over <= 0:
        return 0.0
    b = _bracket(season)
    bill, i, rem = 0.0, 0, over
    while rem > 0:
        chunk = min(rem, b)
        bill += chunk * _tax_rate(i, repeater)
        rem -= chunk
        i += 1
    return bill


def _match_cushion(season=CUR):
    return _indexed(7_500_000, season)


def max_incoming(outgoing, over_first_apron, season=CUR):
    """Most salary a team over the cap can take back for `outgoing` salary in one trade."""
    if over_first_apron:
        return outgoing
    x = _match_cushion(season)
    return max(min(2 * outgoing + 250_000, outgoing + x), 1.25 * outgoing + 250_000)


def _zone(p, f):
    if p <= f["cap"]:
        return 0
    if p <= f["tax"]:
        return 1
    if p <= f["apron1"]:
        return 2
    if p <= f["apron2"]:
        return 3
    return 4


_ZONE_NAMES = ["Under the cap", "Over the cap, under the tax", "Taxpayer, under the 1st apron",
               "Between the 1st and 2nd aprons", "Above the 2nd apron"]


def _nice_ticks(lo, hi, step):
    t = math.ceil(lo / step) * step
    out = []
    while t <= hi + 1e-9:
        out.append(t)
        t += step
    return out


# ------------------------------------------------------------------------------------------------ SVG utilities
def _svg(w, h, body, label, img=None, head=None):
    """img: a file name -- the chart is shown as a see-through picture (PNG) that can be saved or downloaded, drawn by
    the page from this same SVG (so it looks exactly the same), with a "Download .png" button under it.
    head: (svg, height) from _svg_head -- the card's own title, subtitle and key, drawn at the top of the chart so the
    picture (and its download) holds everything in the card above the "Download .png" button."""
    if head and head[1] > 0:
        head_svg, hh = head
        body = f'{head_svg}<g transform="translate(0,{hh:.1f})">{body}</g>'
        h = h + hh
    tag = f' data-ba-img="{_e(img)}"' if img else ""
    return (f'<svg viewBox="0 0 {w} {h:.0f}" preserveAspectRatio="xMidYMid meet" role="img" '
            f'aria-label="{_e(label)}" style="font-family:{FONT}"{tag}>{body}</svg>')


# Arial's character widths (per 1000 of the font size; Liberation Sans has the same metrics), ASCII 32-126 -- to wrap
# a picture's heading the way the page would, without needing the font on the server
_AW_REG = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556,
           556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278,
           500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469,
           556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
           278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_AW_BOLD = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556,
            556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278,
            556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584,
            556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556,
            333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584]


def _tw(text, size, bold=False):
    """Width of plain text in Arial at `size`."""
    table = _AW_BOLD if bold else _AW_REG
    return sum(table[ord(ch) - 32] if 32 <= ord(ch) <= 126 else 600 for ch in text) * size / 1000.0


def _svg_txt(text):
    """Plain text -> safe inside the SVG (and never a markdown dollar pair)."""
    return _e(text).replace("$", "&#36;")


def _svg_head(cfg, title=None, sub=None, legend=None):
    """A card's heading as SVG, for a chart shown as a picture: the title (bold, white), the subtitle (grey; a list of
    ("t", text) and ("pill", text, background, text colour) pieces) and the colour key ((label, color, "sw" | "ln")),
    each wrapped to the chart's width like the page would. Text is plain (no HTML). Returns (svg, height)."""
    W = cfg["w"]
    mobile = W < 500
    ts, ss, ls = (14.0, 11.5, 11.5) if mobile else (15.0, 12.0, 12.0)
    out, y = [], 0.0

    def base(top, lh, size):                         # where a line's text sits in a line box (Arial's ascent/descent)
        return top + (lh - 1.117 * size) / 2 + 0.905 * size

    def flow(pieces, size, lh, gap_x):
        """Lays pieces [(width, draw(x, top))] out in rows no wider than the chart; returns the height used."""
        rows, row, used = [], [], 0.0
        for w, draw in pieces:
            need = w if not row else used + gap_x + w
            if row and need > W - 1:
                rows.append(row)
                row, used = [], 0.0
                need = w
            row.append((w, draw))
            used = need
        if row:
            rows.append(row)
        for r_i, r in enumerate(rows):
            x = 0.0
            for w, draw in r:
                out.append(draw(x, y + r_i * lh))
                x += w + gap_x
        return len(rows) * lh

    if title:
        lh = ts * 1.35
        words = str(title).split()
        pieces = [(_tw(wd, ts, True), (lambda wd: lambda x, top: _t(x, base(top, lh, ts), _svg_txt(wd), ts, INK, "start",
                                                                      "700"))(wd)) for wd in words]
        y += flow(pieces, ts, lh, _tw(" ", ts, True)) + 2
    if sub:
        lh = ss * 1.7
        pieces = []
        for part in sub:
            if part[0] == "pill":
                txt, bg, fg = part[1], part[2], part[3]
                w = _tw(txt, ss, True) + 16
                h = ss * 1.45

                def draw(x, top, txt=txt, bg=bg, fg=fg, w=w, h=h):
                    y0 = top + (lh - h) / 2
                    return (f'<rect x="{x:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h / 2:.1f}" '
                            f'fill="{bg}"/>' + _t(x + 8, base(top, lh, ss), _svg_txt(txt), ss, fg, "start", "700"))
                pieces.append((w, draw))
            else:
                for wd in str(part[1]).split():
                    pieces.append((_tw(wd, ss), (lambda wd: lambda x, top: _t(x, base(top, lh, ss), _svg_txt(wd), ss,
                                                                             "#9a9a9a"))(wd)))
        y += flow(pieces, ss, lh, _tw(" ", ss)) + 8
    if legend:
        lh = ls * 1.5
        pieces = []
        for label, color, kind in legend:
            key_w = 12 if kind == "sw" else 16
            w = key_w + 6 + _tw(label, ls)

            def draw(x, top, label=label, color=color, kind=kind, key_w=key_w):
                mid = top + lh / 2
                key = (f'<rect x="{x:.1f}" y="{mid - 6:.1f}" width="12" height="12" rx="3" fill="{color}"/>' if kind == "sw"
                       else f'<rect x="{x:.1f}" y="{mid - 1.5:.1f}" width="16" height="3" rx="1.5" fill="{color}"/>')
                return key + _t(x + key_w + 6, base(top, lh, ls), _svg_txt(label), ls, "#c9c9c9")
            pieces.append((w, draw))
        y += flow(pieces, ls, lh, 16) + 8
    return "".join(out), (y + 6 if out else 0.0)


def _img_name(team_label, what):
    return f"bradley-analytics-{_slug(team_label).replace('_', '-')}-{what}.png"


def _t(x, y, s, size, fill=SUB, anchor="start", weight="400", extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}" {extra}>{s}</text>')


def _ln(x1, y1, x2, y2, color, w=1, extra=""):
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{w}" '
            f'vector-effect="non-scaling-stroke" {extra}/>')


def _dual(desktop, mobile):
    return f'<div class="cba-d">{desktop}</div><div class="cba-m">{mobile}</div>'


def _legend(items):
    """items: (label, color, kind) with kind 'sw' (swatch) or 'ln' (line key)."""
    return '<div class="cba-lg">' + "".join(
        f'<span><span class="{k}" style="background:{c}"></span>{_e(lbl)}</span>' for lbl, c, k in items) + "</div>"


def _card(title, sub, inner, note=""):
    return ('<div class="cba-card">' + (f'<div class="cba-ct">{title}</div>' if title else "") +
            (f'<div class="cba-cs">{sub}</div>' if sub else "") + inner +
            (f'<div class="cba-note">{note}</div>' if note else "") + "</div>")


def _spread_labels(items, min_gap, lo, hi):
    """items: list of [y, ...]; nudges label y positions apart (keeping order) inside [lo, hi]."""
    items = sorted(items, key=lambda it: it[0])
    for i in range(1, len(items)):
        if items[i][0] - items[i - 1][0] < min_gap:
            items[i][0] = items[i - 1][0] + min_gap
    if items and items[-1][0] > hi:
        shift = items[-1][0] - hi
        for it in items:
            it[0] -= shift
        for i in range(len(items) - 2, -1, -1):
            if items[i + 1][0] - items[i][0] < min_gap:
                items[i][0] = items[i + 1][0] - min_gap
    return items


def _table(headers, rows, accent=GOLD, stack=True, num_cols=(), cls=""):
    """Dark-theme HTML table. On phones a stacked table turns each row into a small card (header text becomes each
    cell's caption, numbers sit side by side), so nothing scrolls sideways. cls adds extra classes ("cba-mx" for the
    compact yes/no matrix, "tight" for small tables that stay tabular on phones)."""
    th = "".join(f'<th style="color:{accent}">{h}</th>' for h in headers)
    body = ""
    for r in rows:
        tds = ""
        for i, c in enumerate(r):
            td_cls = ' class="n"' if i in num_cols else ""
            tds += f'<td{td_cls} data-l="{_e(re.sub("<[^>]+>", "", headers[i]))}">{c}</td>'
        body += f"<tr>{tds}</tr>"
    return (f'<div class="cba-tw"><table class="cba-t{" stack" if stack else ""}{" " + cls if cls else ""}">'
            f"<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>")


def _pill(kind, text=None):
    text = text or {"y": "Yes", "n": "No", "c": "Limited", "x": "n/a"}[kind]
    return f'<span class="cba-pill {kind}">{text}</span>'


def _hbars(rows, colors, scale_max, fmt=_m):
    """HTML horizontal bars (they stay readable at any width). rows: (label, sublabel, [values...])."""
    out = '<div class="cba-hb">'
    for label, sub, vals in rows:
        bars = ""
        for v, c in zip(vals, colors):
            if v is None:
                continue
            w = max(0.4, 78.0 * v / scale_max)
            bars += (f'<div class="cba-hb-b"><span class="bar" style="width:{w:.2f}%;background:{c}"></span>'
                     f'<span class="val">{fmt(v)}</span></div>')
        sub_html = f"<small>{sub}</small>" if sub else ""
        out += f'<div class="cba-hb-row"><div class="cba-hb-l">{label}{sub_html}</div><div>{bars}</div></div>'
    return out + "</div>"


# ------------------------------------------------------------------------------------------------------ the charts
def _ladder_svg(cfg, f, season, marker=None, vertical=False, img_team=None, head=None):
    """The salary ladder for one season: floor, cap, tax line and both aprons on one dollar scale, the zones
    between them shaded, and (optionally) a team's payroll marked on it. marker = (label, value, color)."""
    fs, tk = cfg["fs"], cfg["tick"]
    levels = [("Salary floor", f.get("floor"), C_FLOOR), ("Salary cap", f["cap"], C_CAP), ("Tax line", f["tax"], C_TAX),
              ("1st apron", f["apron1"], C_AP1), ("2nd apron", f["apron2"], C_AP2)]
    levels = [lv for lv in levels if lv[1]]
    lo = min(v for _, v, _ in levels) - 12e6
    hi = f["apron2"] + 16e6
    if marker:
        lo = min(lo, marker[1] - 10e6)
        hi = max(hi, marker[1] + 12e6)
    floor = f.get("floor")
    zones = ([(lo, floor, "Below floor"), (floor, f["cap"], "Cap room")] if floor else [(lo, f["cap"], "Cap room")])
    zones += [(f["cap"], f["tax"], "Over the cap"), (f["tax"], f["apron1"], "Tax"),
              (f["apron1"], f["apron2"], "Apron zone"), (f["apron2"], hi, "Above 2nd apron")]
    fills = {"Below floor": "rgba(255,255,255,.02)", "Cap room": "rgba(57,135,229,.10)",
             "Over the cap": "rgba(255,255,255,.035)", "Tax": "rgba(212,175,55,.12)",
             "Apron zone": "rgba(217,89,38,.14)", "Above 2nd apron": "rgba(144,133,233,.16)"}
    b = []
    label = f"{season} salary ladder"
    if not vertical:
        W = cfg["w"]
        top = 50 + (40 if marker else 0)
        bh = 28
        H = top + bh + 40
        L, R = 16, 16
        sx = lambda v: L + (v - lo) / (hi - lo) * (W - L - R)
        mx = sx(marker[1]) if marker else None
        for a, z, name in zones:
            x1, x2 = sx(a), sx(z)
            b.append(f'<rect x="{x1:.1f}" y="{top}" width="{max(0, x2 - x1 - 2):.1f}" height="{bh}" '
                     f'fill="{fills[name]}" rx="3"/>')
            half_w = len(name) * (tk - 1) * 0.3 + 6
            clear = mx is None or abs(mx - (x1 + x2) / 2) > half_w + 4
            if x2 - x1 > 2 * half_w and clear:
                b.append(_t((x1 + x2) / 2, top + bh / 2 + tk * 0.36, _e(name), tk - 1, MUTED, "middle"))
        items = [[sx(v), n, v, c] for n, v, c in levels]
        for x, n, v, c in items:
            b.append(_ln(x, top - 6, x, top + bh + 6, c, 2))
        # names above, values below; nudge apart only when two levels sit close together
        placed = _spread_labels([list(it) for it in items], 88, L + 40, W - R - 40)
        for (lx, n, v, c), (x, *_rest) in zip(placed, sorted(items, key=lambda it: it[0])):
            b.append(_t(lx, top - 24, _e(n), fs, INK, "middle", "700"))
            b.append(_t(lx, top + bh + 26, _m(v), tk, SUB, "middle"))
            if abs(lx - x) > 2:
                b.append(_ln(lx, top - 19, x, top - 7, AXIS, 1))
        if marker:
            name, v, c = marker
            x = sx(v)
            b.append(_ln(x, top - 40, x, top + bh + 4, INK, 6, 'stroke-opacity=".85"'))
            b.append(_ln(x, top - 40, x, top + bh + 4, c, 3))
            b.append(f'<path d="M{x - 7:.1f},{top - 50} L{x + 7:.1f},{top - 50} L{x:.1f},{top - 40} Z" fill="{c}"/>')
            anchor = "start" if x < W * 0.6 else "end"
            dx = 10 if anchor == "start" else -10
            b.append(_t(x + dx, top - 54, f"{_e(name)}: {_m(v)}", fs, INK, anchor, "700"))
        return _svg(W, H, "".join(b), label, img=_img_name(img_team or marker[0], f"{season}-salary-ladder") if marker else None,
                    head=head)
    # vertical (phones): dollars run bottom to top; one label per line on the right, "Name  $value", with the team
    # marker spread together with the thresholds so no two labels ever overlap
    W = cfg["w"]
    H = 440
    T, B = 14, 14
    bx, bw = 8, 58
    sy = lambda v: H - B - (v - lo) / (hi - lo) * (H - T - B)
    for a, z, name in zones:
        y1, y2 = sy(z), sy(a)
        b.append(f'<rect x="{bx}" y="{y1:.1f}" width="{bw}" height="{max(0, y2 - y1 - 2):.1f}" fill="{fills[name]}" rx="3"/>')
    items = [[sy(v), n, v, c, False] for n, v, c in levels]
    for y, n, v, c, _mk in items:
        b.append(_ln(bx - 3, y, bx + bw + 5, y, c, 2))
    if marker:
        name, v, c = marker
        y = sy(v)
        b.append(_ln(bx - 3, y, bx + bw + 5, y, INK, 8, 'stroke-opacity=".85"'))
        b.append(_ln(bx - 3, y, bx + bw + 5, y, c, 5))
        items.append([y, name, v, c, True])
    placed = _spread_labels([list(it) + [it[0]] for it in items], fs + 9, T + fs, H - B - 2)
    tx = bx + bw + 24
    for ly, n, v, c, is_marker, orig in placed:
        b.append(_ln(bx + bw + 6, orig, tx - 5, ly - fs * 0.33, c if is_marker else AXIS, 2 if is_marker else 1))
        if is_marker:
            b.append(f'<rect x="{tx - 2}" y="{ly - fs - 2:.1f}" width="{W - tx - 2}" height="{fs + 9}" rx="4" '
                     f'fill="{c}" fill-opacity=".22" stroke="{c}" stroke-width="1" vector-effect="non-scaling-stroke"/>')
        b.append(_t(tx + 4, ly, _e(n), fs, INK, "start", "700"))
        b.append(_t(W - 6, ly, _m(v), tk, INK if is_marker else SUB, "end", "700" if is_marker else "400"))
    return _svg(W, H, "".join(b), label, img=_img_name(img_team or marker[0], f"{season}-salary-ladder") if marker else None,
                head=head)


def _history_chart(cfg, mobile=False):
    hist = [r for r in _history() if r[0] >= "2016-17"]
    seasons = [r[0] for r in hist]
    series = [("Salary cap", C_CAP, [r[1] for r in hist]), ("Tax line", C_TAX, [r[2] for r in hist]),
              ("Apron / 1st apron", C_AP1, [r[3] for r in hist]), ("2nd apron", C_AP2, [r[4] for r in hist])]
    W = cfg["w"]
    H = 330 if mobile else 380
    L, R, T, B = (48, 66, 16, 32) if mobile else (62, 150, 16, 34)
    y0, y1 = 80e6, 230e6
    sx = lambda i: L + i * (W - L - R) / (len(seasons) - 1)
    sy = lambda v: T + (y1 - v) / (y1 - y0) * (H - T - B)
    b = []
    for t in _nice_ticks(y0, y1, 25e6 if not mobile else 50e6):
        b.append(_ln(L, sy(t), W - R, sy(t), GRID))
        b.append(_t(L - 8, sy(t) + cfg["tick"] * 0.35, f"&#36;{t / 1e6:.0f}M", cfg["tick"], MUTED, "end"))
    every = 2 if mobile else 1
    for i, s in enumerate(seasons):
        if i % every == 0 or i == len(seasons) - 1:
            lab = s[2:] if mobile else s
            b.append(_t(sx(i), H - B + cfg["tick"] + 8, lab, cfg["tick"], MUTED, "middle"))
    # the 2023 CBA line
    i23 = seasons.index("2023-24")
    xg = (sx(i23) + sx(i23 - 1)) / 2
    b.append(_ln(xg, T, xg, H - B, AXIS, 1))
    b.append(_t(xg + 6, T + cfg["tick"], "2023 CBA", cfg["tick"] - 1, MUTED))
    ends = []
    for name, c, vals in series:
        pts = [(sx(i), sy(v)) for i, v in enumerate(vals) if v]
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        b.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="2.5" stroke-linejoin="round" '
                 f'stroke-linecap="round" vector-effect="non-scaling-stroke"/>')
        for i, v in enumerate(vals):
            if v:
                b.append(f'<g><title>{seasons[i]} {name}: {_m_plain(v, 3)}</title>'
                         f'<circle cx="{sx(i):.1f}" cy="{sy(v):.1f}" r="11" fill="transparent"/>'
                         f'<circle cx="{sx(i):.1f}" cy="{sy(v):.1f}" r="{3.5 if mobile else 4}" fill="{c}" '
                         f'stroke="{SURF}" stroke-width="2"/></g>')
        ends.append([sy(vals[-1]), name, vals[-1], c])
    gap = cfg["fs"] + 3
    placed = _spread_labels([list(e) for e in ends], gap, T + 8, H - B)
    xe = sx(len(seasons) - 1)
    for ly, name, v, c in placed:
        orig = next(e[0] for e in ends if e[1] == name)
        if abs(ly - orig) > 2:
            b.append(_ln(xe + 5, orig, xe + 12, ly - 4, AXIS, 1))
        txt = _m(v, 1) if mobile else f"{_e(name.replace('Apron / ', ''))} {_m(v, 1)}"
        b.append(_t(xe + 14, ly, txt, cfg["tick"], BODY, "start", "700"))
    return _svg(W, H, "".join(b), "NBA salary cap, tax line and aprons, 2016-17 to 2026-27")


def _growth_chart(cfg, mobile=False):
    hist = _history()
    rows = [(hist[i][0], hist[i][1] / hist[i - 1][1] - 1) for i in range(1, len(hist))]
    W = cfg["w"]
    H = 250 if mobile else 280
    L, R, T, B = (38, 8, 22, 30) if mobile else (52, 16, 24, 34)
    y1 = 0.36
    n = len(rows)
    band = (W - L - R) / n
    bw = min(24, band * 0.6)
    sy = lambda v: T + (y1 - v) / y1 * (H - T - B)
    b = []
    for t in [0, 0.1, 0.2, 0.3]:
        b.append(_ln(L, sy(t), W - R, sy(t), GRID if t else AXIS))
        b.append(_t(L - 7, sy(t) + cfg["tick"] * 0.35, f"{t * 100:.0f}%", cfg["tick"], MUTED, "end"))
    for i, (s, g) in enumerate(rows):
        cx = L + band * (i + 0.5)
        y = sy(max(g, 0))
        h = sy(0) - y
        if h > 0.5:
            r = min(4, h)
            b.append(f'<g><title>{s}: cap {"up" if g >= 0 else "down"} {abs(g) * 100:.2f}%</title>'
                     f'<rect x="{cx - band / 2:.1f}" y="{T}" width="{band:.1f}" height="{H - T - B}" fill="transparent"/>'
                     f'<path d="M{cx - bw / 2:.1f},{sy(0):.1f} V{y + r:.1f} Q{cx - bw / 2:.1f},{y:.1f} {cx - bw / 2 + r:.1f},{y:.1f} '
                     f'H{cx + bw / 2 - r:.1f} Q{cx + bw / 2:.1f},{y:.1f} {cx + bw / 2:.1f},{y + r:.1f} V{sy(0):.1f} Z" '
                     f'fill="{GOLD}"/></g>')
        else:
            b.append(f'<g><title>{s}: no change</title><rect x="{cx - bw / 2:.1f}" y="{sy(0) - 2:.1f}" width="{bw:.1f}" '
                     f'height="2" fill="{MUTED}"/></g>')
        labelled = ("2016-17", "2020-21", "2026-27") if mobile else ("2016-17", "2020-21", "2026-27", "2022-23",
                                                                      "2023-24", "2025-26")
        if s in labelled:
            b.append(_t(cx, y - 6, f"{g * 100:.{0 if abs(g * 100 - round(g * 100)) < 0.05 else 1}f}%",
                        cfg["tick"] - (1 if mobile else 0), BODY, "middle", "700"))
        if not mobile or (n - 1 - i) % 2 == 0:
            b.append(_t(cx, H - B + cfg["tick"] + 8, s[2:] if mobile else s, cfg["tick"] - (0.5 if not mobile else 0),
                        MUTED, "middle"))
    # the 10% ceiling, labelled over the low-growth seasons (2017-18 on) where nothing else sits
    b.append(_ln(L, sy(0.10), W - R, sy(0.10), INK, 1.5, 'stroke-opacity=".75"'))
    b.append(_t(L + band * 1.1, sy(0.10) - 7, "10% ceiling" if mobile else "10% ceiling on annual growth (2023 CBA)",
                cfg["tick"], INK, "start", "700"))
    return _svg(W, H, "".join(b), "Year-over-year salary cap growth")


def _salary_band_chart(cfg, mobile=False):
    cap = CAP_FIGURES[CUR]["cap"]
    tiers = []
    for yos in range(11):
        std = MAX_PCT["0-6"] if yos <= 6 else (MAX_PCT["7-9"] if yos <= 9 else MAX_PCT["10+"])
        ext = 0.30 if yos == 4 else (0.35 if yos in (8, 9) else None)
        tiers.append((yos, MIN_SCALE_CUR[yos], std * cap, ext * cap if ext else None))
    W = cfg["w"]
    H = 300 if mobile else 340
    L, R, T, B = (40, 6, 34, 40) if mobile else (58, 14, 40, 44)
    y1 = 62e6
    band = (W - L - R) / 11
    bw = min(26, band * 0.62)
    sy = lambda v: T + (y1 - v) / y1 * (H - T - B)
    b = []
    for t in _nice_ticks(0, 60e6, 20e6 if mobile else 10e6):
        b.append(_ln(L, sy(t), W - R, sy(t), GRID if t else AXIS))
        b.append(_t(L - 7, sy(t) + cfg["tick"] * 0.35, f"&#36;{t / 1e6:.0f}M", cfg["tick"], MUTED, "end"))
    for yos, mn, mx, ext in tiers:
        cx = L + band * (yos + 0.5)
        x0 = cx - bw / 2
        lab = "10+" if yos == 10 else str(yos)
        tip = (f"{lab} years of service: minimum {_m_plain(mn, 3)}, standard max {_m_plain(mx, 3)}"
               + (f", up to {_m_plain(ext, 3)} with award criteria" if ext else ""))
        parts = [f'<rect x="{cx - band / 2:.1f}" y="{T}" width="{band:.1f}" height="{H - T - B}" fill="transparent"/>']
        # minimum (grey), 2px surface gap, then the range up to the max (gold), then the award-based extra
        parts.append(f'<rect x="{x0:.1f}" y="{sy(mn):.1f}" width="{bw:.1f}" height="{sy(0) - sy(mn):.1f}" fill="{C_PREV}"/>')
        ytop = sy(mx)
        parts.append(f'<rect x="{x0:.1f}" y="{ytop:.1f}" width="{bw:.1f}" height="{max(0, sy(mn) - ytop - 2):.1f}" '
                     f'fill="{GOLD}" rx="{0 if ext else 4}"/>')
        if not ext:
            parts.append(f'<rect x="{x0:.1f}" y="{ytop + 4:.1f}" width="{bw:.1f}" height="{max(0, sy(mn) - ytop - 6):.1f}" fill="{GOLD}"/>')
        if ext:
            ye = sy(ext)
            hh = max(0, ytop - ye - 2)
            parts.append(f'<rect x="{x0:.1f}" y="{ye:.1f}" width="{bw:.1f}" height="{hh:.1f}" fill="{GOLD_L}" rx="4"/>')
            parts.append(f'<rect x="{x0:.1f}" y="{ye + min(4, hh / 2):.1f}" width="{bw:.1f}" '
                         f'height="{max(0, hh - min(4, hh / 2)):.1f}" fill="{GOLD_L}"/>')
        b.append(f"<g><title>{tip}</title>{''.join(parts)}</g>")
        b.append(_t(cx, H - B + cfg["tick"] + 8, lab, cfg["tick"], MUTED, "middle"))
    b.append(_t((W + L - R) / 2, H - 4, "Years of service", cfg["tick"], MUTED, "middle"))
    # tier labels, one per tier: 25% just above its columns (left-aligned, clear of the year-4 extra), 30% one row
    # above the supermax columns, 35% right-aligned over the last column
    y35 = sy(0.35 * cap) - 8
    x_of = lambda col: L + band * col + (band - bw) / 2
    fmt = (lambda pct, v: f"{int(pct * 100)}%: {_m(v, 1)}") if mobile else \
        (lambda pct, v: f"{int(pct * 100)}% max {_m(v, 1)}")
    b.append(_t(x_of(0), sy(0.25 * cap) - 8, fmt(0.25, 0.25 * cap), cfg["tick"], BODY, "start", "700"))
    b.append(_t(x_of(7) + bw, sy(0.30 * cap) - 8, fmt(0.30, 0.30 * cap), cfg["tick"], BODY, "end", "700"))
    b.append(_t(W - R, y35, fmt(0.35, 0.35 * cap), cfg["tick"], BODY, "end", "700"))
    return _svg(W, H, "".join(b), f"{CUR} salary range by years of service")


def _trade_chart(cfg, mobile=False):
    W = cfg["w"]
    H = 300 if mobile else 340
    L, R, T, B = (44, 12, 18, 44) if mobile else (62, 24, 20, 48)
    x1, y1 = 50e6, 70e6
    sx = lambda v: L + v / x1 * (W - L - R)
    sy = lambda v: T + (y1 - v) / y1 * (H - T - B)
    b = []
    for t in _nice_ticks(0, y1, 10e6 if not mobile else 20e6):
        b.append(_ln(L, sy(t), W - R, sy(t), GRID if t else AXIS))
        b.append(_t(L - 7, sy(t) + cfg["tick"] * 0.35, f"&#36;{t / 1e6:.0f}M", cfg["tick"], MUTED, "end"))
    for t in _nice_ticks(0, x1, 10e6):
        b.append(_t(sx(t), H - B + cfg["tick"] + 8, f"&#36;{t / 1e6:.0f}M", cfg["tick"], MUTED, "middle"))
    b.append(_t((W + L - R) / 2, H - 6, "Salary sent out", cfg["tick"], MUTED, "middle"))
    x = _match_cushion()
    k1 = x - 250_000
    k2 = 4 * k1
    for k in (k1, k2):
        b.append(_ln(sx(k), T, sx(k), H - B, GRID))
    xs = [i * 0.25e6 for i in range(int(x1 / 0.25e6) + 1)]
    for over, c, name in ((False, GOLD, "Ends under the 1st apron"), (True, C_AP1, "Ends above the 1st apron")):
        pts = [(sx(v), sy(max_incoming(v, over))) for v in xs]
        d = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts)
        b.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="2.5" stroke-linejoin="round" '
                 f'vector-effect="non-scaling-stroke"/>')
        for v in (5e6, 10e6, 20e6, 30e6, 40e6, 50e6):
            mi = max_incoming(v, over)
            b.append(f'<g><title>{name}: send {_m_plain(v)}, take back up to {_m_plain(mi, 2)}</title>'
                     f'<circle cx="{sx(v):.1f}" cy="{sy(mi):.1f}" r="11" fill="transparent"/>'
                     f'<circle cx="{sx(v):.1f}" cy="{sy(mi):.1f}" r="3.5" fill="{c}" stroke="{SURF}" stroke-width="2"/></g>')
    # rule labels along the gold line
    fsz = cfg["tick"] - (0.5 if mobile else 0)
    # rule labels sit above-left of a point on the gold line (the line only rises to the right, so text never
    # crosses it); text wears ink colours, the line beside it carries the identity
    if mobile:
        labs = [(k1, "200%"), ((k1 + k2) / 2, "+" + _m(x, 1)), (k2 + 9e6, "125%")]
    else:
        labs = [(k1, "200% + &#36;0.25M"), ((k1 + k2) / 2, "Outgoing + about " + _m(x, 1)),
                (k2 + 9e6, "125% + &#36;0.25M")]
    for v, txt in labs:
        yv = sy(max_incoming(v, False))
        b.append(_t(sx(v) - 8, yv - 8, txt, fsz, INK, "end", "700"))
    if not mobile:
        for k in (k1, k2):
            b.append(_t(sx(k) + 5, H - B - 8, _m(k, 1), cfg["tick"] - 1, MUTED, "start"))
    b.append(_t(sx(x1) - 2, sy(max_incoming(x1, True)) + 18, "100%", fsz, INK, "end", "700"))
    return _svg(W, H, "".join(b), "Trade salary matching, 2026-27")


def _tax_chart(cfg, mobile=False, team=None, head=None):
    """Tax bill by dollars over the tax line, standard vs repeater. team = (label, over, color) or None."""
    br = _bracket()
    x_max = br * 6
    if team and team[1] > br * 5:
        x_max = br * (math.ceil(team[1] / br) + 1)
    y_max = tax_bill(x_max, True) * 1.08
    step_y = 50e6 if y_max < 320e6 else 100e6
    W = cfg["w"]
    H = 300 if mobile else 350
    L, R, T, B = (50, 60, 18, 44) if mobile else (66, 150, 20, 48)
    sx = lambda v: L + v / x_max * (W - L - R)
    sy = lambda v: T + (y_max - v) / y_max * (H - T - B)
    b = []
    for t in _nice_ticks(0, y_max, step_y if not mobile else step_y * 2):
        b.append(_ln(L, sy(t), W - R, sy(t), GRID if t else AXIS))
        b.append(_t(L - 7, sy(t) + cfg["tick"] * 0.35, f"&#36;{t / 1e6:.0f}M", cfg["tick"], MUTED, "end"))
    # bracket boundaries
    i = 1
    while br * i < x_max - 1:
        b.append(_ln(sx(br * i), T, sx(br * i), H - B, "#232323"))
        i += 1
    for t in _nice_ticks(0, x_max, 10e6):
        b.append(_t(sx(t), H - B + cfg["tick"] + 8, f"&#36;{t / 1e6:.0f}M", cfg["tick"], MUTED, "middle"))
    b.append(_t((W + L - R) / 2, H - 6, "Team salary over the tax line", cfg["tick"], MUTED, "middle"))
    xs = [x_max * k / 240 for k in range(241)]
    ends = []
    for rep, c, name in ((False, GOLD, "Standard"), (True, C_REPEAT, "Repeater")):
        d = "M" + " L".join(f"{sx(v):.1f},{sy(tax_bill(v, rep)):.1f}" for v in xs)
        b.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="2.5" stroke-linejoin="round" '
                 f'vector-effect="non-scaling-stroke"/>')
        for k in range(1, int(round(x_max / br)) + 1):
            v = br * k
            bill = tax_bill(v, rep)
            b.append(f'<g><title>{name} rates: {_m_plain(v)} over the line costs {_m_plain(bill)} in tax</title>'
                     f'<circle cx="{sx(v):.1f}" cy="{sy(bill):.1f}" r="11" fill="transparent"/>'
                     f'<circle cx="{sx(v):.1f}" cy="{sy(bill):.1f}" r="3.5" fill="{c}" stroke="{SURF}" stroke-width="2"/></g>')
        ends.append([sy(tax_bill(x_max, rep)), name, tax_bill(x_max, rep), c])
    placed = _spread_labels(ends, cfg["fs"] + 4, T + 8, H - B)
    for ly, name, v, c in placed:
        txt = _m(v, 1) if mobile else f"{name} {_m(v, 1)}"
        b.append(_t(sx(x_max) + 8, ly + 4, txt, cfg["tick"], BODY, "start", "700"))
    if team:
        name, over, c = team
        for rep in (False, True):
            bill = tax_bill(over, rep)
            b.append(f'<circle cx="{sx(over):.1f}" cy="{sy(bill):.1f}" r="6" fill="{c}" stroke="{INK}" stroke-width="2"/>')
        yb = sy(tax_bill(over, True))
        anchor = "end" if sx(over) > W * 0.55 else "start"
        dx = -10 if anchor == "end" else 10
        b.append(_t(sx(over) + dx, yb - 10, f"{_e(name)}: {_m(over, 1)} over", cfg["tick"], INK, anchor, "700"))
    return _svg(W, H, "".join(b), "Luxury tax bill by salary over the tax line",
                img=_img_name(team[0], "luxury-tax") if team else None, head=head if team else None)


def _cap_range(season):
    """(lowest, highest) possible cap for a season the league hasn't set: it can't fall and can't grow >10%/yr."""
    last = max(CAP_FIGURES)
    yrs = (_season_start(season) or 0) - _season_start(last)
    if yrs <= 0:
        return None
    base = CAP_FIGURES[last]["cap"]
    return base, base * 1.10 ** yrs


def _team_seasons_chart(cfg, team_label, color, payrolls, mobile=False, head=None):
    seasons = sorted(payrolls)
    figs = {s: _figs(s) for s in seasons}
    ranges = {s: (_cap_range(s) if not figs[s] else None) for s in seasons}
    top_v = max([payrolls[s] for s in seasons] + [f["apron2"] for f in figs.values() if f] +
                [r[1] for r in ranges.values() if r])
    y1 = top_v * 1.1
    step = 50e6
    W = cfg["w"]
    H = 290 if mobile else 330
    L, R, T, B = (50, 8, 20, 34) if mobile else (62, 16, 24, 38)
    n = len(seasons)
    band = (W - L - R) / max(n, 1)
    bw = min(44 if not mobile else 30, band * 0.5)
    sy = lambda v: T + (y1 - v) / y1 * (H - T - B)
    b, bg = [], []
    for t in _nice_ticks(0, y1, step if not mobile else 100e6):
        b.append(_ln(L, sy(t), W - R, sy(t), GRID if t else AXIS))
        b.append(_t(L - 7, sy(t) + cfg["tick"] * 0.35, f"&#36;{t / 1e6:.0f}M", cfg["tick"], MUTED, "end"))
    for i, s in enumerate(seasons):
        cx = L + band * (i + 0.5)
        p = payrolls[s]
        y = sy(p)
        h = sy(0) - y
        r = min(4, h)
        f = figs[s]
        tip = f"{team_label} {s} committed salary: {_m_plain(p, 3)}"
        if f:
            tip += (f" (cap {_m_plain(f['cap'], 3)}, tax {_m_plain(f['tax'], 3)}, 1st apron {_m_plain(f['apron1'], 3)}, "
                    f"2nd apron {_m_plain(f['apron2'], 3)})")
        b.append(f'<g><title>{_e(tip)}</title>'
                 f'<rect x="{cx - band / 2:.1f}" y="{T}" width="{band:.1f}" height="{H - T - B}" fill="transparent"/>'
                 f'<path d="M{cx - bw / 2:.1f},{sy(0):.1f} V{y + r:.1f} Q{cx - bw / 2:.1f},{y:.1f} {cx - bw / 2 + r:.1f},{y:.1f} '
                 f'H{cx + bw / 2 - r:.1f} Q{cx + bw / 2:.1f},{y:.1f} {cx + bw / 2:.1f},{y + r:.1f} V{sy(0):.1f} Z" '
                 f'fill="{color}"/></g>')
        half = min(band * 0.46, bw / 2 + (26 if not mobile else 12))
        if f:
            for key, c in (("cap", C_CAP), ("tax", C_TAX), ("apron1", C_AP1), ("apron2", C_AP2)):
                b.append(_ln(cx - half, sy(f[key]), cx + half, sy(f[key]), SURF, 6))
                b.append(_ln(cx - half, sy(f[key]), cx + half, sy(f[key]), c, 2.5))
        rng = ranges.get(s)
        if rng:
            y_hi, y_lo = sy(rng[1]), sy(rng[0])
            bg.append(f'<g><title>{s} cap will land between {_m_plain(rng[0], 3)} and {_m_plain(rng[1], 3)}</title>'
                     f'<rect x="{cx - half:.1f}" y="{y_hi:.1f}" width="{2 * half:.1f}" height="{y_lo - y_hi:.1f}" '
                     f'fill="{C_CAP}" fill-opacity=".16" rx="3"/></g>')
            b.append(_ln(cx - half, y_lo, cx + half, y_lo, C_CAP, 1.5, 'stroke-opacity=".7"'))
            b.append(_ln(cx - half, y_hi, cx + half, y_hi, C_CAP, 1.5, 'stroke-opacity=".7"'))
        # the value sits just above its bar unless a threshold line or the range band is in the way; then above all
        marks = ([sy(f[k]) for k in ("cap", "tax", "apron1", "apron2")] if f else []) + \
                ([sy(rng[0]), sy(rng[1])] if rng else [])
        lab_y = y - 9
        if any(lab_y - cfg["tick"] - 3 <= m <= y + 2 for m in marks) or (rng and sy(rng[1]) <= y <= sy(rng[0])):
            lab_y = min([y] + marks) - 9
        b.append(_t(cx, lab_y, _m(p, 1), cfg["tick"], INK, "middle", "700"))
        b.append(_t(cx, H - B + cfg["tick"] + 8, s[2:] if (mobile and n > 3) else s, cfg["tick"], MUTED, "middle"))
    return _svg(W, H, "".join(bg + b), f"{team_label} committed salary by season",
                img=_img_name(team_label, "committed-salary"), head=head)


# ------------------------------------------------------------------------------------------------------ sections
def _sec(title):
    st.markdown(f"### {title}")


def _sub(title):
    st.markdown(f"#### {title}")


_TOC = [("big-picture", "The big picture"), ("thresholds", "Thresholds"), ("aprons", "The aprons"),
        ("exceptions", "Exceptions"), ("contracts", "Contracts"), ("trades", "Trades"), ("tax", "Luxury tax"),
        ("floor", "Salary floor"), ("calendar", "Free agency and calendar"), ("your-team", "Your team"),
        ("audiences", "Who it matters to"), ("glossary", "Glossary")]


def _anchor(key):
    _html_block(f'<div id="cba-{key}" style="position:relative;top:-70px;height:0"></div>')


def _intro(team_name):
    f = CAP_FIGURES[CUR]
    tiles = [("Salary floor", MIN_TEAM_SALARY[CUR], C_FLOOR, "90% of the cap"),
             ("Salary cap", f["cap"], C_CAP, "+6.67% vs 2025-26"),
             ("Tax line", f["tax"], C_TAX, "121.5% of the cap"),
             ("1st apron", f["apron1"], C_AP1, "trade and signing limits"),
             ("2nd apron", f["apron2"], C_AP2, "the hardest limits")]
    tiles_html = '<div class="cba-tiles">' + "".join(
        f'<div class="cba-tile"><div class="k"><span class="sw" style="background:{c}"></span>{_e(k)}</div>'
        f'<div class="v">{_m(v)}</div><div class="s">{s}</div></div>' for k, v, c, s in tiles) + "</div>"
    toc = '<div class="cba-toc">' + "".join(f'<a href="#cba-{k}" target="_self">{_e(t)}</a>' for k, t in _TOC) + "</div>"
    _prose(
        '<div class="cba-lead">',
        _p(f"Everything salary-cap related in the 2023 Collective Bargaining Agreement, with the {CUR} numbers: "
           "how the cap is set, the tax line and the two aprons, every exception, contract and trade rule, the luxury "
           f"tax, the calendar, and where the <b>{_e(team_name)}</b> sit today. Written for the front office, the "
           "coaching staff and fans."),
        "</div>",
        f'<div class="cba-cs" style="margin-bottom:6px">{CUR} league-wide thresholds (official, set July 1, 2026)</div>',
        tiles_html, toc)


def _big_picture():
    _anchor("big-picture")
    _sec("The big picture")
    f = CAP_FIGURES[CUR]
    _prose(
        _p("The NBA has a <b>soft cap</b>. The salary cap limits how much a team can spend on <i>other teams'</i> "
           "free agents, but a team can go over it to keep its own players (Bird rights), to use its exceptions "
           "(mid-level, minimum contracts, rookie deals) and to make trades. Instead of one hard ceiling, the CBA "
           "stacks four lines on top of each other. Each one you cross takes tools away or costs money."),
        _ul([
            "<b>Where the money comes from.</b> Players are guaranteed between 49% and 51% of Basketball Related "
            "Income (BRI: TV deals, tickets, sponsorships and more), with 50% as the target. Up to 10% of every "
            "salary is held in escrow during the season and returned or kept once the audit shows the real split.",
            "<b>How the cap is set.</b> Each summer the cap is 44.74% of projected BRI, minus projected player "
            "benefits, divided by 30 teams. The other lines are tied to it: the tax line is 121.5% of the cap, the "
            "salary floor is 90%, and both aprons rise at the same rate as the cap.",
            "<b>The 10% smoothing rule.</b> New in this CBA: the cap and every threshold can never go down from one "
            "season to the next and can never rise more than 10%. That stops a repeat of 2016, when a TV-money "
            "spike lifted the cap 34.5% in one summer. 2025-26 hit the 10% ceiling; 2026-27 rose 6.67%.",
            "<b>How long it runs.</b> The deal took effect July 1, 2023 and runs through the 2029-30 season "
            "(June 30, 2030). Either side can opt out after 2028-29 by giving notice by Oct. 15, 2028.",
        ]))
    desk = _ladder_svg(_DESK, _figs(CUR), CUR)
    mob = _ladder_svg(_MOB, _figs(CUR), CUR, vertical=True)
    _html_block('<div class="cba">' + _card(
        f"The {CUR} salary ladder",
        "Every team's payroll sits somewhere on this scale. The shaded zones between the lines are where the "
        "rules change.", _dual(desk, mob),
        f"The tax line ({_m(f['tax'])}) only costs money. The two aprons are where the CBA starts taking tools "
        "away, which is why front offices talk about aprons more than the tax.") + "</div>")


def _thresholds():
    _anchor("thresholds")
    _sec("The thresholds and what each one means")
    p, c = _figs(PREV), _figs(CUR)
    rows = [
        ["Salary floor", _m(p["floor"]), _m(c["floor"]), "90% of the cap",
         "Teams below it on opening night pay the shortfall and lose their share of the tax payout."],
        ["Salary cap", _m(p["cap"]), _m(c["cap"]), "44.74% of projected BRI, less benefits, / 30",
         "Below it: sign any free agent with cap space and absorb salary in trades. Above it: only Bird rights, "
         "exceptions and matched trades."],
        ["Tax line", _m(p["tax"]), _m(c["tax"]), "121.5% of the cap",
         "Above it at season's end: pay luxury tax on every dollar over, and no share of the tax payout. "
         "No roster rules change here."],
        ["1st apron", _m(p["apron1"]), _m(c["apron1"]), "2023-24 tax line + &#36;7.052M, grows with the cap",
         "Above it: no Non-taxpayer MLE or Bi-annual, 100% salary matching, no sign-and-trade acquisitions, no "
         "big buyout signings, no prior-season trade exceptions."],
        ["2nd apron", _m(p["apron2"]), _m(c["apron2"]), "2023-24 tax + $17.5M, grows with the cap".replace("$", "&#36;"),
         "Above it: all of the above, plus no salary aggregation, no cash in trades, no Taxpayer MLE, and a frozen "
         "future first-round pick."],
    ]
    _html_block('<div class="cba">' + _table(["Threshold", PREV, CUR, "How it's set", "What changes above it"], rows,
                                              num_cols=(1, 2)) + "</div>")
    hist = [r for r in _history() if r[0] >= "2016-17"]
    lg = _legend([("Salary cap", C_CAP, "ln"), ("Tax line", C_TAX, "ln"), ("Apron (1st apron from 2023-24)", C_AP1, "ln"),
                  ("2nd apron (new in 2023)", C_AP2, "ln")])
    trows = [[r[0], _m(r[1]), _m(r[2]), _m(r[3]), _m(r[4]) if r[4] else "n/a"] for r in hist]
    details = ("<details><summary>Show the numbers</summary>" +
               _table(["Season", "Cap", "Tax line", "Apron / 1st apron", "2nd apron"], trows, stack=False,
                      num_cols=(1, 2, 3, 4)) + "</details>")
    _html_block('<div class="cba">' + _card(
        "Ten years of the cap, the tax line and the aprons",
        "2016-17 to 2026-27. Before 2023 there was one apron (tax line + about &#36;4M to &#36;6.7M) that only "
        "mattered for a few moves; the 2023 CBA turned it into the 1st apron and added a 2nd.",
        lg + _dual(_history_chart(_DESK), _history_chart(_MOB, mobile=True)) + details,
        "The cap has grown from &#36;94.1M to &#36;165.0M (+75%) in ten seasons. Hover a point for the exact figure.")
        + "</div>")
    _html_block('<div class="cba">' + _card(
        "How fast the cap grows each year",
        "Year-over-year change in the salary cap. The white line is the new 10% ceiling.",
        _dual(_growth_chart(_DESK), _growth_chart(_MOB, mobile=True)),
        "2020-21 stayed flat after the pandemic season. With the new national TV deals starting in 2025-26, the "
        "smoothing rule is what keeps the cap from jumping the way it did in 2016.") + "</div>")


def _aprons():
    _anchor("aprons")
    _sec("The aprons in detail")
    c = _figs(CUR)
    _prose(
        _p("The aprons are measured with <b>apron salary</b>: team salary plus every incentive in the players' "
           "contracts, even ones they are unlikely to earn. They apply at the moment of each transaction, and many "
           "moves also <b>hard cap</b> the team at an apron for the rest of the season: once you use them, you "
           "can't go over that line again until next July, no matter what."))
    _sub(f"1st apron: {_m(c['apron1'])} in {CUR}".replace("&#36;", "\\$"))
    _prose(_ul([
        "<b>Trades must be dollar-for-dollar.</b> A team that ends a trade above the 1st apron can take back no more "
        "than 100% of the salary it sends out, with no &#36;250K cushion.",
        f"<b>No Non-taxpayer MLE and no Bi-annual.</b> Only the smaller Taxpayer MLE ({_m(6_064_000)} for up to "
        f"2 years instead of {_m(15_044_000)} for up to 4).",
        "<b>No sign-and-trade acquisitions.</b> You can't receive a player in a sign-and-trade.",
        f"<b>No big buyout signings.</b> Can't sign a player waived during the season if his salary before the "
        f"waiver was above the Non-taxpayer MLE ({_m(15_044_000)}).",
        "<b>No old trade exceptions.</b> A traded player exception can't be used once the regular season in which "
        "it was created is over.",
        "<b>Hard cap at the 1st apron</b> for any team that uses the Non-taxpayer MLE, the Bi-annual, a "
        "sign-and-trade acquisition, the expanded 200%/125% trade matching, a prior-season trade exception, or "
        "signs one of those buyout players.",
    ]))
    _sub(f"2nd apron: {_m(c['apron2'])} in {CUR}".replace("&#36;", "\\$"))
    _prose(_ul([
        "<b>Everything the 1st apron forbids</b>, plus:",
        "<b>No aggregation.</b> Can't combine two or more players' salaries to take back one bigger contract.",
        "<b>No cash.</b> Can't send cash in a trade.",
        "<b>No Taxpayer MLE.</b> The last mid-level option disappears.",
        "<b>No sign-and-trade exceptions.</b> Can't use a trade exception created by sending out a sign-and-trade "
        "player.",
        "<b>The frozen pick.</b> If a team is above the 2nd apron at the start of its last regular-season game, its "
        "first-round pick seven drafts out can't be traded. For 2026-27 that is the 2034 first.",
        "<b>The pick drops to No. 30.</b> If the team is above the 2nd apron in 2 or more of the next 4 seasons, that "
        "frozen pick moves to the end of the first round. It unfreezes once the team stays under the line for 3 of "
        "those 4 seasons.",
        "<b>Hard cap at the 2nd apron</b> for any team that aggregates salaries, sends cash, uses the Taxpayer MLE, "
        "or uses a sign-and-trade trade exception.",
    ]))
    # restriction matrix
    Y, N, X = _pill("y"), _pill("n"), _pill("x")
    moves = [
        ("Re-sign own players with Bird rights", Y, Y, Y, Y),
        ("Minimum-salary contracts", Y, Y, Y, Y),
        ("Non-taxpayer MLE (&#36;15.044M, up to 4 yrs)", Y, Y, N, N),
        ("Taxpayer MLE (&#36;6.064M, up to 2 yrs)", X, X, Y, N),
        ("Bi-annual exception (&#36;5.477M)", Y, Y, N, N),
        ("Trade matching: 200% / +&#36;9.1M / 125%", Y, Y, N, N),
        ("Trade matching: 100% of outgoing", Y, Y, Y, Y),
        ("Aggregate salaries in a trade", Y, Y, Y, N),
        ("Send cash in a trade", Y, Y, Y, N),
        ("Acquire a player in a sign-and-trade", Y, Y, N, N),
        ("Use a prior-season trade exception", Y, Y, N, N),
        ("Sign a buyout player who earned over the NT-MLE", Y, Y, N, N),
        ("Trade the first-round pick seven drafts out (judged at the last game)", Y, Y, Y, _pill("n", "Frozen")),
        ("Share of the luxury tax payout", Y, N, N, N),
    ]
    rows = [[m, a, b, cc, d] for m, a, b, cc, d in moves]
    _html_block('<div class="cba">' + _card(
        "What each zone can do",
        "For teams over the cap. A move is allowed only if the team is still under the listed line right after it.",
        _table(["Move", "Under the tax", "Tax to 1st apron", "1st to 2nd apron", "Above 2nd apron"], rows,
               stack=False, cls="cba-mx"),
        "The first two columns are almost the same: the tax line only costs money, the aprons change the rules. "
        "n/a: the Taxpayer MLE is only for teams that end up above the 1st apron; teams below it use the bigger "
        "Non-taxpayer MLE. The +&#36;9.1M trade cushion is the CBA's &#36;7.5M indexed to the 2026-27 cap (about).")
        + "</div>")
    flow = ('<div class="cba-flow">'
            '<div class="st hot"><div class="h">2026-27: above the 2nd apron</div><div class="b">Measured at the start '
            'of the last regular-season game. The 2034 first-round pick is frozen: it can\'t be traded.</div></div>'
            '<div class="ar">&rarr;</div>'
            '<div class="st"><div class="h">2027-28 to 2030-31</div><div class="b">The next four seasons are the '
            'watch window. Each season above the 2nd apron counts.</div></div>'
            '<div class="ar">&rarr;</div>'
            '<div class="st"><div class="h">2 or more of the 4 above</div><div class="b">The 2034 pick becomes the '
            'last pick of the first round (No. 30, or near it if other teams are penalized too).</div></div>'
            '<div class="ar">&rarr;</div>'
            '<div class="st end"><div class="h">3 of the 4 below</div><div class="b">The pick unfreezes after the third '
            'season under the line and can be traded again, with no penalty.</div></div></div>')
    _html_block('<div class="cba">' + _card("How the 2nd-apron draft penalty plays out", "The pick seven drafts "
                                            "out is at stake every season a team finishes above the 2nd apron.",
                                            flow) + "</div>")


def _exceptions():
    _anchor("exceptions")
    _sec("Exceptions: how teams add players over the cap")
    _prose(_p("Exceptions are the CBA's permission slips for spending past the cap. Most are sized as a percentage "
              "of the cap, so they grow every year with it."))
    rows = [
        ["Non-taxpayer MLE", _m(14_104_000), _m(15_044_000), "Up to 4 yrs, 5% raises",
         "Teams over the cap that stay under the 1st apron (9.12% of the cap). Hard caps at the 1st apron."],
        ["Taxpayer MLE", _m(5_685_000), _m(6_064_000), "Up to 2 yrs",
         "Teams above the 1st apron. Hard caps at the 2nd apron; gone above it."],
        ["Room MLE", _m(8_781_000), _m(9_366_000), "Up to 3 yrs",
         "Teams that went under the cap to use space (5.678% of the cap). Replaces the other MLEs and the Bi-annual."],
        ["Bi-annual exception", _m(5_134_000), _m(5_477_000), "Up to 2 yrs",
         "3.32% of the cap; not in back-to-back seasons; under the 1st apron. Hard caps at the 1st apron."],
        ["Minimum salary", f"{_m(1_272_870)} to {_m(3_634_153)}", f"{_m(1_357_763)} to {_m(3_876_529)}",
         "Up to 2 yrs", "Every team, any time, no limit. Amount depends on years of service."],
        ["Rookie scale", "By pick", f"No. 1: {_m(ROOKIE_NO1_CUR)}", "2 yrs + 2 team options",
         "First-round picks, 80% to 120% of the scale (almost all sign at 120%)."],
        ["Bird rights (Full)", "Up to the max", "Up to the max", "Up to 5 yrs, 8% raises",
         "Own free agent after 3 seasons without changing teams as a free agent."],
        ["Early Bird", "175% of salary", "175% of salary", "2 to 4 yrs, 8% raises",
         "After 2 seasons: 175% of last salary or 105% of the league average salary, whichever is more."],
        ["Non-Bird", "120% of salary", "120% of salary", "Up to 4 yrs, 5% raises",
         "After 1 season: 120% of last salary or 120% of the minimum."],
        ["Disabled Player (DPE)", "Up to NT-MLE", "Up to " + _m(15_044_000), "1 season",
         "Half of an injured player's salary or the NT-MLE, whichever is less. Apply July 1 to Jan. 15; expires "
         "March 10."],
        ["Traded player exception", "Outgoing + &#36;0.25M", "Outgoing + &#36;0.25M", "Used within 1 year",
         "Created when a team sends out more salary than it takes back; absorbs a player later without matching."],
        ["Second-round pick", "Minimum-based", "Minimum-based", "2+1 or 3+1 yrs",
         "Signs the team's own second-round picks on 2-year or 3-year deals with a team option."],
    ]
    _html_block('<div class="cba">' + _table(["Exception", PREV, CUR, "Length", "Who gets it"], rows,
                                              num_cols=(1, 2)) + "</div>")
    lg = _legend([(PREV, C_PREV, "sw"), (CUR, GOLD, "sw")])
    bars = _hbars([(lbl, None, [a, b]) for lbl, a, b in EXCEPTION_VALUES], [C_PREV, GOLD],
                  max(b for _, _, b in EXCEPTION_VALUES))
    _html_block('<div class="cba">' + _card(
        f"Exception values, {PREV} vs {CUR}",
        "First-year salary each exception allows. They rose 6.67% with the cap.",
        lg + bars,
        "The Non-taxpayer MLE is worth about 2.5 times the Taxpayer MLE. Crossing the 1st apron is the difference "
        "between signing a starter and signing a rotation player.") + "</div>")


def _contracts():
    _anchor("contracts")
    _sec("Contracts: max deals, rookies, minimums and extensions")
    cap = CAP_FIGURES[CUR]["cap"]
    _sub("Maximum salaries")
    _prose(_ul([
        f"<b>0 to 6 years of service:</b> 25% of the cap ({_m(0.25 * cap)} in {CUR}).",
        f"<b>7 to 9 years:</b> 30% ({_m(0.30 * cap)}).",
        f"<b>10 or more years:</b> 35% ({_m(0.35 * cap)}).",
        "<b>Or 105% of the player's previous salary</b>, if that is higher.",
        "<b>5th-year max (the Rose rule).</b> A player finishing his rookie deal can get up to 30% if he made an "
        "All-NBA team or won Defensive Player of the Year in the last season or 2 of the last 3, or won MVP in one "
        "of the last 3.",
        "<b>Supermax (Designated Veteran).</b> A player with 8 or 9 years of service, all with the team he first "
        "signed with (or traded only during his first four seasons), who meets the same award criteria, can get 35% "
        "from that team. Only his own team can offer it.",
    ]))
    lg = _legend([("Minimum salary", C_PREV, "sw"), ("Range up to the standard max", GOLD, "sw"),
                  ("Extra with award criteria (5th-year max, supermax)", GOLD_L, "sw")])
    band_rows = [["10+" if i == 10 else str(i), _m(MIN_SCALE_CUR[i])] for i in range(11)]
    details = ("<details><summary>Show the 2026-27 minimum salary scale</summary>" +
               _table(["Years of service", "Minimum salary"], band_rows, stack=False, num_cols=(1,)) + "</details>")
    _html_block('<div class="cba">' + _card(
        f"What a player can earn by years of service, {CUR}",
        "From the minimum to the max for a contract signed this season.",
        lg + _dual(_salary_band_chart(_DESK), _salary_band_chart(_MOB, mobile=True)) + details,
        "The jumps at 7 and 10 years are why agents time free agency around service milestones.") + "</div>")
    # the value of Bird rights on a max contract
    rows = []
    for pct, lbl in ((0.25, "25% max (0 to 6 yrs)"), (0.30, "30% max (7 to 9 yrs)"), (0.35, "35% max (10+ yrs)")):
        first = pct * cap
        bird = first * sum(1 + 0.08 * k for k in range(5))
        other = first * sum(1 + 0.05 * k for k in range(4))
        rows.append((lbl, f"+{_m(bird - other, 1)} by staying", [bird, other]))
    lg2 = _legend([("Re-sign with own team: 5 years, 8% raises", GOLD, "sw"),
                   ("Sign elsewhere: 4 years, 5% raises", C_CAP, "sw")])
    _html_block('<div class="cba">' + _card(
        "Why stars re-sign: the value of Bird rights on a max deal",
        f"Total value of a max contract starting in {CUR}.",
        lg2 + _hbars(rows, [GOLD, C_CAP], rows[-1][2][0], fmt=lambda v: _m(v, 1)),
        "Same first-year salary either way. The extra season and bigger raises are only available from the "
        "player's current team.") + "</div>")
    _sub("Raises, length and extensions")
    _prose(_ul([
        "<b>Raises:</b> up to 8% of the first-year salary per season when re-signing your own Bird or Early Bird "
        "free agent (and in extensions); 5% for everyone else.",
        "<b>Length:</b> up to 5 seasons when re-signing your own Bird free agent, 4 for everyone else. Rookie-scale "
        "extensions and supermax extensions can run 6 seasons counting the current one.",
        "<b>Veteran extensions:</b> allowed 2 years after signing a 3 or 4-year deal (3 years after a 5 or 6-year "
        "deal); 1 and 2-year deals can't be extended. The first new season can be up to 140% of the player's "
        "current salary or 140% of the estimated average salary, whichever is more.",
        "<b>Rookie-scale extensions:</b> after the third season, from the end of the July moratorium until the day "
        "before opening night of year four.",
        f"<b>Rookie scale:</b> first-round picks get 2 guaranteed years plus team options for years 3 and 4. The "
        f"2026 No. 1 pick makes {_m(ROOKIE_NO1_CUR)} this season and the No. 30 pick {_m(ROOKIE_NO30_CUR)} "
        "(both at 120% of the scale).",
        "<b>Second-round picks</b> can sign 2-year deals with a team option for a third, or 3-year deals with an "
        "option for a fourth.",
        "<b>Two-way contracts:</b> up to 3 per team; the player can be active for up to 50 NBA games; salary is half "
        f"the rookie minimum ({_m(678_882)} in {CUR}); they don't count against the cap; not playoff-eligible "
        "unless converted before the last regular-season game.",
        f"<b>Veteran minimums:</b> a one-year minimum deal for a player with 3+ years of service counts on the cap "
        f"as a 2-year veteran ({_m(2_449_421)}); the league covers the rest. The cheapest way to add experience.",
        "<b>Guarantees and options:</b> non-guaranteed players must be waived by Jan. 7 or their salary becomes "
        "fully guaranteed on Jan. 10. Player options, team options and early termination options are decided "
        "before free agency (early termination options by June 29).",
        "<b>Bonuses and trade kickers:</b> incentives count as \"likely\" or \"unlikely\" based on the previous "
        "season, and unlikely ones can't top 15% of salary; a trade kicker can pay up to 15% of the remaining "
        "contract, only on the first trade.",
        "<b>The stretch provision:</b> a waived player's remaining guaranteed money can be spread over twice the "
        "years left plus one. Stretched dead money can't exceed 15% of the cap.",
    ]))


def _trades():
    _anchor("trades")
    _sec("Trades: salary matching and trade rules")
    x = _match_cushion()
    k1 = x - 250_000
    k2 = 4 * k1
    cash = CASH_PCT * CAP_FIGURES[CUR]["cap"]
    _prose(
        _p("Teams under the cap can absorb salary up to their cap room plus &#36;250K. Everyone else has to match "
           f"salaries, and how closely depends on where the trade leaves them ({CUR}):"),
        _ul([
            f"<b>Ends under the 1st apron:</b> send out up to about {_m(k1, 1)}, take back 200% + &#36;0.25M. Send "
            f"out {_m(k1, 1)} to {_m(k2, 1)}, take back that plus about {_m(x, 1)}. Send out more than "
            f"{_m(k2, 1)}, take back 125% + &#36;0.25M.",
            "<b>Ends above the 1st apron:</b> take back no more than 100% of what you send out.",
            "<b>Aggregation</b> (combining several salaries in one trade) is allowed except above the 2nd apron. "
            "A player acquired with an exception can't be aggregated for 2 months.",
            "<b>Traded player exceptions:</b> trading a player away for less salary creates an exception for the "
            "difference (plus &#36;0.25M below the 1st apron) that can absorb players within a year. It can't be "
            "combined with other salaries, and a team that would end up above the 1st apron can't use it after "
            "the regular season it was created in.",
        ]))
    lg = _legend([("Ends under the 1st apron", GOLD, "ln"), ("Ends above the 1st apron", C_AP1, "ln")])
    ex = [5e6, 10e6, 20e6, 30e6, 40e6]
    rows = [[_m(v, 1), _m(max_incoming(v, False), 2), _m(max_incoming(v, True), 2)] for v in ex]
    details = ("<details><summary>Show examples</summary>" +
               _table(["Salary sent out", "Max back (under 1st apron)", "Max back (above 1st apron)"], rows,
                      stack=False, num_cols=(0, 1, 2)) + "</details>")
    _html_block('<div class="cba">' + _card(
        f"How much salary can come back in a trade, {CUR}",
        "Maximum incoming salary for a team over the cap, by salary sent out.",
        lg + _dual(_trade_chart(_DESK), _trade_chart(_MOB, mobile=True)) + details,
        f"The cushion ({_m(x, 1)}) is the CBA's &#36;7.5M indexed to the cap. The gap between the two lines is "
        "what crossing the 1st apron costs a team at the trade deadline.") + "</div>")
    _sub("Other trade rules")
    _prose(_ul([
        "<b>Newly signed players:</b> free agents can't be traded until 3 months after signing or Dec. 15, whichever "
        "is later. A player re-signed with a raise of more than 20% by a team over the cap waits until Jan. 15. "
        "Draft picks who sign can't be traded for 30 days.",
        "<b>No-trade by rule:</b> a player on a one-year deal who will have Bird or Early Bird rights at the end of "
        "it must consent to a trade.",
        f"<b>Cash:</b> each team can send and receive up to 5.15% of the cap in cash per season (about {_m(cash, 1)} "
        "in 2026-27), and payments in and out don't cancel each other. A team above the 2nd apron can't send any.",
        "<b>Draft picks:</b> picks can be traded up to seven drafts ahead. The Stepien rule says a team can't be "
        "left without a first-round pick in two consecutive future drafts. Protections and swaps are common ways "
        "around it.",
        "<b>Sign-and-trades:</b> 3 to 4 years, the first season fully guaranteed, and the receiving team must end "
        "up under the 1st apron (and is hard capped there).",
        "<b>Expiring contracts</b> can't be traded after the deadline in their final season.",
        f"<b>Trade deadline:</b> {TRADE_DEADLINE}.",
    ]))


def _tax(team_name, color, team_payrolls):
    _anchor("tax")
    _sec("The luxury tax")
    br = _bracket()
    c = _figs(CUR)
    _prose(
        _p(f"A team whose salary is above the tax line ({_m(c['tax'])}) at the start of its <b>last regular-season "
           "game</b> pays tax on every dollar over, including incentives actually earned. The rate climbs by "
           "bracket; each bracket was &#36;5M in 2023-24 and grows with the cap (" + _m(br) + f" in {CUR}). The "
           "rates changed in 2025-26: cheaper for the first dollars over the line, much steeper after that."),
        _ul([
            "<b>Repeaters</b> are teams that paid tax in 3 or more of the previous 4 seasons. Their rates start at "
            "&#36;3.00 per dollar.",
            "<b>Where the money goes:</b> the league can hand up to 50% of the tax collected to the teams that "
            "didn't pay tax, in equal shares. A team below the salary floor gets none of it. The rest goes to "
            "league purposes.",
            "<b>Why the last game matters:</b> salary dumped before the final regular-season game comes off the tax "
            "bill, which is why tax-avoidance trades and waivers cluster at the deadline.",
        ]))
    rows = []
    lo = 0
    for i in range(6):
        hi = br * (i + 1)
        lo_txt = "&#36;0" if lo == 0 else _m(lo, 3)
        rng = f"{lo_txt} to {_m(hi, 3)}" if i < 5 else f"{lo_txt} and up"
        more = ", then +&#36;0.50 per bracket" if i == 5 else ""
        rows.append([rng, f"&#36;{_tax_rate(i, False):.2f}{more}", f"&#36;{_tax_rate(i, True):.2f}{more}"])
        lo = hi
    _html_block('<div class="cba">' + _table([f"Over the tax line ({CUR})", "Standard rate", "Repeater rate"], rows,
                                              stack=False, cls="tight") + "</div>")
    p_cur = team_payrolls.get(CUR)
    team_mark = None
    if p_cur and p_cur > c["tax"]:
        team_mark = (team_name.split()[-1], p_cur - c["tax"], color)
    lg_items = ([("Standard rates", GOLD, "ln"), ("Repeater rates", C_REPEAT, "ln")] +
                ([(f"{team_name}, {CUR} committed salary", color, "sw")] if team_mark else []))
    ex20 = (tax_bill(20e6, False), tax_bill(20e6, True))
    tax_title, tax_sub = f"Tax bill by salary over the line, {CUR}", "The vertical hairlines mark each tax bracket."
    if team_mark:
        # a picture (it shows the team): its title, subtitle and key are part of the picture
        tax_inner = _dual(
            _tax_chart(_DESK, team=team_mark, head=_svg_head(_DESK, tax_title, [("t", tax_sub)], lg_items)),
            _tax_chart(_MOB, mobile=True, team=team_mark, head=_svg_head(_MOB, tax_title, [("t", tax_sub)], lg_items)))
        tax_title = tax_sub = None
    else:
        tax_inner = _legend(lg_items) + _dual(_tax_chart(_DESK), _tax_chart(_MOB, mobile=True))
    _html_block('<div class="cba">' + _card(
        tax_title, tax_sub, tax_inner,
        f"Example: &#36;20M over the line costs about {_m(ex20[0], 1)} in tax at standard rates and about "
        f"{_m(ex20[1], 1)} as a repeater, on top of the salary itself.") + "</div>")
    # calculator
    _sub("Tax calculator")
    slug = _slug(team_name)
    default = round((p_cur if p_cur else c["tax"] + 10e6) / 1e6 * 2) / 2
    default = min(max(default, 140.0), 320.0)
    col1, col2 = st.columns([3, 2])
    with col1:
        payroll_m = st.slider(f"{CUR} team salary at the last regular-season game (millions)", min_value=140.0,
                              max_value=320.0, value=float(default), step=0.5, format="%.1f",
                              key=f"cba_tax_payroll_{slug}")
    with col2:
        kind = st.radio("Tax rates", ["Standard", "Repeater"], horizontal=True, key=f"cba_tax_kind_{slug}")
    payroll = payroll_m * 1e6
    over = payroll - c["tax"]
    rep = kind == "Repeater"
    bill = tax_bill(over, rep)
    i = int(over // br) if over > 0 else None
    marg = _tax_rate(i, rep) if over > 0 else 0.0
    z = _ZONE_NAMES[_zone(payroll, c)]
    tiles = [("Over the tax line", _m(over, 1) if over > 0 else f"{_m(-over, 1)} under", f"line: {_m(c['tax'])}", ""),
             ("Tax bill", _m(bill, 1), f"{kind.lower()} rates", ""),
             ("Total cost", _m(payroll + bill, 1), "salary + tax", ""),
             ("Next dollar costs", f"&#36;{1 + marg:.2f}", f"&#36;1 salary + &#36;{marg:.2f} tax", ""),
             ("Zone", _e(z), "", " sm")]
    _html_block('<div class="cba"><div class="cba-tiles">' + "".join(
        f'<div class="cba-tile"><div class="k">{k}</div><div class="v{cls}" style="white-space:normal">{v}</div>'
        f'<div class="s">{s}</div></div>' for k, v, s, cls in tiles) + "</div></div>")


def _floor():
    _anchor("floor")
    _sec("The salary floor")
    p, c = MIN_TEAM_SALARY[PREV], MIN_TEAM_SALARY[CUR]
    _prose(_ul([
        f"<b>90% of the cap:</b> {_m(c)} in {CUR} ({_m(p)} in {PREV}).",
        "<b>Checked on opening night.</b> A team below it on the first day of the regular season pays the "
        "difference to the league after the season and loses its share of the luxury tax payout, which can be "
        "worth more than the shortfall itself.",
        "<b>Counted all season.</b> From opening night on, the shortfall is added to the team's salary for cap "
        "purposes, and a team that drops back below its opening-night level has to fix it by the next day.",
        "<b>Why it matters:</b> rebuilding teams with cap space often absorb bad contracts (and collect picks for "
        "it) partly to reach the floor. Under the old rules a team could simply pay the shortfall; losing the tax "
        "payout makes that far more expensive now.",
    ]))


def _calendar():
    _anchor("calendar")
    _sec("Free agency and the salary-cap calendar")
    _prose(_ul([
        "<b>Cap holds:</b> until a team re-signs or renounces its own free agent, a placeholder stays on its cap: "
        "150% of his last salary (190% if it was below the league average), 250% or 300% for players coming off "
        "rookie deals, 130% for Early Bird, 120% for Non-Bird, never more than his max. Unsigned first-round picks "
        "count at their scale amount, and in the offseason every empty roster spot below 12 counts as a rookie "
        "minimum.",
        "<b>Restricted free agency:</b> players finishing rookie deals, or with 3 or fewer years of service, become "
        "restricted if their team makes a qualifying offer by June 29. Any team can sign them to an offer sheet; the "
        "old team has until 11:59 p.m. ET the next day to match (two days later if the sheet arrived after noon). "
        "The qualifying offer stays open for the player until Oct. 1.",
        "<b>The moratorium:</b> free agents can agree to terms from 6 p.m. ET on June 30, but nothing is signed "
        "until noon ET on July 6, after the league's numbers are official.",
    ]))
    items = [
        ("June 29, 5 p.m. ET", "Qualifying offers and early termination options due", "Deadline to make a player "
         "a restricted free agent or opt out early.", True),
        ("June 30, 6 p.m. ET", "Free agency negotiations open", "Teams and free agents can start talking and "
         "agreeing to terms.", True),
        ("July 1", "New league year", f"The {CUR} cap, tax line and aprons take effect; exceptions reset; the "
         "moratorium starts.", True),
        ("July 6, noon ET", "Moratorium ends", "Contracts can be signed and trades completed.", True),
        ("Day before opening night", "Rookie-scale extension deadline", "Last day to extend fourth-year players "
         "coming off rookie deals.", False),
        (f"Opening night: {OPENING_NIGHT}", "Salary floor check", "Rosters must be at 14 or 15; the floor is "
         "measured.", True),
        ("Dec. 15", "Most summer signings become tradable", "The start of the real trade season.", True),
        ("Jan. 7, 5 p.m. ET", "Last day to waive non-guaranteed players", "Players still on the roster on Jan. 10 "
         "are guaranteed for the season. From Jan. 10, unused mid-level and Bi-annual exceptions start shrinking "
         "day by day.", True),
        ("Jan. 15", "Big Bird raises tradable; DPE deadline", "Players re-signed with 20%+ raises can be dealt; last "
         "day to apply for a Disabled Player Exception.", False),
        (f"{TRADE_DEADLINE}", "Trade deadline", "Last chance to shed salary or add talent through trades.", True),
        ("March 1", "Playoff-eligibility waiver deadline", "Players waived after this can't play in the playoffs "
         "for a new team, which is why buyouts happen before it.", False),
        ("March 10", "Disabled Player Exceptions expire", "", False),
        ("Last regular-season game", "Tax and 2nd apron measured", "The tax bill and the 2nd-apron draft penalty "
         "are based on salary at the start of this game.", True),
    ]
    tl = '<div class="cba-tl">' + "".join(
        f'<div class="cba-tl-i{"" if key else " soft"}"><div class="cba-tl-d">{d}</div><div class="cba-tl-t">{t}</div>'
        + (f'<div class="cba-tl-x">{x}</div>' if x else "") + "</div>" for d, t, x, key in items) + "</div>"
    _html_block('<div class="cba">' + _card(f"The {CUR} cap calendar", "The dates that move money. Gold dots are the "
                                            "biggest ones.", tl) + "</div>")


def _clean_payrolls(team_payrolls):
    out = {}
    for k, v in (team_payrolls or {}).items():
        y = _season_start(k)
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if y is None or not math.isfinite(v) or v <= 0:
            continue
        out[_season_name(y)] = v
    return out


def _your_team(team_name, team_color, payrolls):
    _anchor("your-team")
    _sec(f"Where the {team_name} stand")
    color = _readable_team_color(team_color)
    head_fg = _text_on(color)
    tn = _e(team_name)
    if not payrolls:
        _prose(_p(f"No committed salary has been entered for the {tn} yet, so there is nothing to place on the ladder. "
                  "Once the team's contracts are entered, this section shows each season's payroll against the cap, "
                  "the tax line and both aprons, with a plain-English read on what the team can and can't do."))
        return
    seasons = sorted(payrolls)
    cur = CUR if CUR in payrolls else next((s for s in seasons if _figs(s)), None)
    if cur:
        f = _figs(cur)
        p = payrolls[cur]
        z = _zone(p, f)
        def rel(key, name):
            d = p - f[key]
            return (name, f"{_m(abs(d))} {'over' if d > 0 else 'under'}", f"{name.lower()}: {_m(f[key])}",
                    {"cap": C_CAP, "tax": C_TAX, "apron1": C_AP1, "apron2": C_AP2}[key])
        diffs = [("Committed salary", _m(p), f"{cur}, contracts on the books", color),
                 rel("cap", "Salary cap"), rel("tax", "Tax line"), rel("apron1", "1st apron"),
                 rel("apron2", "2nd apron")]
        tiles = ('<div class="cba-tiles">' + "".join(
            f'<div class="cba-tile" style="border-top:3px solid {color}"><div class="k"><span class="sw" '
            f'style="background:{sw}"></span>{k}</div><div class="v">{v}</div><div class="s">{s}</div></div>'
            for k, v, s, sw in diffs) + "</div>")
        _html_block('<div class="cba">' + tiles + "</div>")
        short = team_name.split()[-1]
        # the card's title and "Zone:" line are drawn into the picture itself (so it downloads with them)
        lad_title, lad_sub = f"The {team_name} on the {cur} ladder", [("t", "Zone:"), ("pill", _ZONE_NAMES[z], color, head_fg)]
        desk = _ladder_svg(_DESK, f, cur, marker=(short, p, color), img_team=team_name,
                           head=_svg_head(_DESK, lad_title, lad_sub))
        mob = _ladder_svg(_MOB, f, cur, marker=(short, p, color), vertical=True, img_team=team_name,
                          head=_svg_head(_MOB, lad_title, lad_sub))
        _html_block('<div class="cba">' + _card(
            None, None,
            _dual(desk, mob),
            "Committed salary only: cap holds for unsigned free agents and draft picks, unearned incentives (which "
            "count toward the aprons) and empty-roster charges can move the real number.") + "</div>")
        _prose(_p(f"<b>What that means in {cur}:</b>"), _ul(_zone_read(z, p, f, team_name)))
    has_future = any(_cap_range(s) and not _figs(s) for s in seasons)
    lg_items = ([(f"{team_name} committed salary", color, "sw"), ("Salary cap", C_CAP, "ln"), ("Tax line", C_TAX, "ln"),
                 ("1st apron", C_AP1, "ln"), ("2nd apron", C_AP2, "ln")] +
                ([("Possible cap range (not set yet)", "rgba(57,135,229,.45)", "sw")] if has_future else []))
    # the picture holds the whole card above its "Download .png" button: title, subtitle, key and chart
    by_title = f"{team_name} committed salary by season"
    by_sub = [("t", "Threshold lines for seasons the league has set; for later seasons, the range the cap can land in.")]
    _html_block('<div class="cba">' + _card(
        None, None,
        _dual(_team_seasons_chart(_DESK, team_name, color, payrolls, head=_svg_head(_DESK, by_title, by_sub, lg_items)),
              _team_seasons_chart(_MOB, team_name, color, payrolls, mobile=True,
                                  head=_svg_head(_MOB, by_title, by_sub, lg_items)))) + "</div>")
    future = [s for s in seasons if not _figs(s) and s > max(CAP_FIGURES)]
    if future:
        last = max(CAP_FIGURES)
        base = CAP_FIGURES[last]
        items = []
        for s in future:
            yrs = _season_start(s) - _season_start(last)
            grow = 1.10 ** yrs
            p = payrolls[s]
            strict = {k: base[k] for k in ("cap", "tax", "apron1", "apron2")}
            loose = {k: base[k] * grow for k in ("cap", "tax", "apron1", "apron2")}
            z_hi, z_lo = _zone(p, strict), _zone(p, loose)
            where = (f"<b>{_e(_ZONE_NAMES[z_hi]).lower()}</b> whatever the cap does" if z_hi == z_lo else
                     f"somewhere from <b>{_e(_ZONE_NAMES[z_lo]).lower()}</b> (if the cap grows the full 10% a year) "
                     f"to <b>{_e(_ZONE_NAMES[z_hi]).lower()}</b> (if it stays flat)")
            items.append(f"<b>{s}:</b> {_m(p)} committed so far. The cap can't fall, and can't rise more than 10% a "
                         f"year, so it will land between {_m(base['cap'])} and {_m(base['cap'] * grow)} and the tax "
                         f"line between {_m(base['tax'])} and {_m(base['tax'] * grow)}. That puts the {tn} {where}.")
        _prose(_p("<b>Seasons the league hasn't set yet:</b>"), _ul(items))


def _zone_read(z, p, f, team_name):
    tn = _e(team_name)
    if z == 0:
        room = f["cap"] - p
        out = [f"The {tn} are {_m(room, 1)} under the cap: they can sign free agents outright with that space, or "
               "absorb that much salary (plus &#36;0.25M) in a trade without sending any back.",
               "Using cap space swaps the Non-taxpayer MLE and the Bi-annual for the smaller Room MLE "
               f"({_m(9_366_000)}), so teams near the cap often choose to stay over it instead.",
               "Cap holds for their own free agents count against the space until those players are renounced."]
        if f.get("floor") and p < f["floor"]:
            out.append(f"They are {_m(f['floor'] - p, 1)} below the salary floor ({_m(f['floor'])}); anything still "
                       "missing on opening night is paid as a penalty, and they would lose their share of the tax "
                       "payout.")
        return out
    if z == 1:
        return [f"Over the cap by {_m(p - f['cap'], 1)} and {_m(f['tax'] - p, 1)} under the tax line: no tax bill, "
                "and a share of the tax payout at season's end.",
                f"Full toolbox: Bird rights, the Non-taxpayer MLE ({_m(15_044_000)}), the Bi-annual "
                f"({_m(5_477_000)}), sign-and-trades and the 200%/125% trade matching, as long as each move leaves "
                f"them under the 1st apron ({_m(f['apron1'])}), which then becomes a hard cap for the season.",
                f"Room to add {_m(f['tax'] - p, 1)} before paying any tax."]
    if z == 2:
        over = p - f["tax"]
        return [f"A taxpayer: {_m(over, 1)} over the line. If it stays that way at the last regular-season game, "
                f"the bill is about {_m(tax_bill(over), 1)} at standard rates ({_m(tax_bill(over, True), 1)} as a "
                "repeater), and they give up their share of the tax payout.",
                f"Still below the 1st apron by {_m(f['apron1'] - p, 1)}, so the rules haven't changed yet: the full "
                "Non-taxpayer MLE, the Bi-annual and the wider trade matching are still available if the move keeps "
                "them under the 1st apron.",
                "Tax-saving trades before the deadline are worth watching: every dollar shed saves at least a dollar "
                "of tax."]
    if z == 3:
        over = p - f["tax"]
        return [f"Between the aprons: {_m(p - f['apron1'], 1)} over the 1st apron and {_m(f['apron2'] - p, 1)} "
                "under the 2nd.",
                f"Only the Taxpayer MLE ({_m(6_064_000)}, 2 years); no Non-taxpayer MLE, no Bi-annual, no "
                "sign-and-trade acquisitions, no buyout players who earned more than the NT-MLE.",
                "Trades must bring back no more than 100% of the salary sent out. Aggregating salaries, sending cash "
                "or using the Taxpayer MLE would hard cap them at the 2nd apron.",
                f"Tax bill if nothing changes: about {_m(tax_bill(over), 1)} standard, {_m(tax_bill(over, True), 1)} "
                "as a repeater."]
    over = p - f["tax"]
    return [f"Above the 2nd apron by {_m(p - f['apron2'], 1)}: the most restricted place in the league.",
            "Can't combine salaries in trades, send cash, use any mid-level exception or acquire sign-and-trade "
            "players; trades must bring back no more than 100% of what goes out.",
            "If they are still above the line at the start of the last regular-season game, the 2034 first-round "
            "pick is frozen, and it drops to No. 30 if they finish above the 2nd apron in 2 of the following 4 "
            "seasons.",
            f"Tax bill if nothing changes: about {_m(tax_bill(over), 1)} standard, {_m(tax_bill(over, True), 1)} as "
            "a repeater."]


def _audiences(team_name):
    _anchor("audiences")
    _sec("What it means for each audience")
    fo = _ul([
        "Know which apron every move would hard cap you at before you make it.",
        "Track the repeater clock: tax in 3 of the last 4 seasons turns &#36;1.00 rates into &#36;3.00.",
        "Plan the tax bill at the last regular-season game, including incentives likely to be hit.",
        "Keep 2nd-apron seasons to fewer than 2 in any 4-year window to protect the frozen pick.",
        "Use exceptions before Jan. 10 proration; file DPEs by Jan. 15; waive by Jan. 7.",
        "Remember the 2-month wait before newly acquired players can be aggregated.",
        "Stretched dead money is capped at 15% of the cap; use it sparingly.",
        "Keep a first-round pick in every two-year window (Stepien) when building trade packages.",
    ])
    coach = _ul([
        "Bird rights reward continuity: keeping and developing your own players is the only way to pay them past "
        "the cap.",
        "Awards need 65 games of 20+ minutes (two 15 to 20-minute games can count), or 62 with a season-ending "
        "injury. Those awards unlock the 5th-year max and the supermax, so rest days can cost a player money.",
        "Incentives are judged on last season: minutes and games decisions late in the year can push a team over "
        "the tax line, since earned bonuses count on the final bill.",
        "Two-way players can be active for 50 games and can't play in the playoffs unless converted in time.",
        "Rosters must carry 14 or 15 standard players in season; above the tax every extra roster spot costs "
        "salary plus tax.",
        "Veterans on one-year minimum deals are the cheapest experienced depth available to an apron team.",
    ])
    fans = _ul([
        "Why teams dump salary at the deadline: the tax is measured at the last game, and each dollar over can "
        "cost &#36;1 to &#36;7+ in tax.",
        "Why stars stay with their own team: only it can offer the fifth year and 8% raises (about &#36;86.6M more "
        "on a 35% max), and only it can offer the supermax.",
        "Why contenders can't just add a star: above the aprons, teams lose the mid-level, can't combine salaries "
        "and risk frozen picks, so three big contracts squeeze everything else.",
        "Why rebuilding teams take on bad contracts: they need to reach the salary floor and get picks for their "
        "cap space.",
        "Why the numbers go up every July: the cap follows league revenue, now limited to 10% growth per season.",
    ])
    _html_block('<div class="cba"><div class="cba-3">' +
                f'<div class="cba-card"><h5 style="color:{GOLD_L}">Front office checklist</h5>{fo}</div>' +
                f'<div class="cba-card"><h5 style="color:{GOLD_L}">Coaching staff</h5>{coach}</div>' +
                f'<div class="cba-card"><h5 style="color:{GOLD_L}">Fans</h5>{fans}</div>' + "</div></div>")


_GLOSSARY = [
    ("Aggregation", "Combining two or more players' salaries in one trade to match a bigger contract. Not allowed "
                    "above the 2nd apron."),
    ("Apron", "A spending line above the tax line (there are two). Crossing one takes transaction tools away."),
    ("Apron salary", "Team salary plus all incentives, likely or not. What the aprons are measured with."),
    ("Bird rights", "The right to re-sign your own free agent past the cap. Full Bird after 3 seasons, Early Bird "
                    "after 2, Non-Bird after 1."),
    ("BRI", "Basketball Related Income: the league revenue the players' 49% to 51% share and the cap are built on."),
    ("Cap hold", "A placeholder on the cap for an unsigned free agent or draft pick until he signs or is renounced."),
    ("Cap space", "How far a team's salary (including holds) is below the cap."),
    ("Dead money", "Salary still owed to players no longer on the roster, still on the cap."),
    ("Designated Veteran (supermax)", "A 35% max for an 8 or 9-year veteran who meets award criteria and has "
                                      "stayed with his first team."),
    ("Escrow", "Up to 10% of salaries withheld each season so the players' share of BRI lands in the 49% to 51% "
               "range."),
    ("Exhibit 10", "A training-camp contract clause that can pay a bonus if the player is waived and joins the "
                   "team's G League affiliate, or can convert into a two-way deal."),
    ("Hard cap", "A line a team can't cross for the rest of the season once it uses certain exceptions or trades."),
    ("Luxury tax", "What a team pays on every dollar above the tax line at the last regular-season game."),
    ("MLE (mid-level exception)", "The main exception for signing free agents over the cap: Non-taxpayer, Taxpayer "
                                  "or Room versions."),
    ("Moratorium", "July 1 to noon ET July 6: teams can agree to deals but not sign them."),
    ("Offer sheet", "A contract a restricted free agent signs with another team, which his team can match."),
    ("Qualifying offer", "A one-year offer that makes a player a restricted free agent."),
    ("Repeater", "A team that paid tax in 3 of the previous 4 seasons; pays higher rates."),
    ("Rose rule (5th-year max)", "Up to 30% for a player coming off his rookie deal who made All-NBA, won DPOY or "
                                 "MVP."),
    ("Salary floor", "90% of the cap; the least a team can spend without a penalty."),
    ("Sign-and-trade", "Re-signing a free agent in order to trade him right away; the receiving team must stay "
                       "under the 1st apron."),
    ("Soft cap", "A cap teams can exceed through exceptions, unlike a hard cap."),
    ("Stepien rule", "A team can't be without a first-round pick in two consecutive future drafts."),
    ("Stretch provision", "Spreading a waived player's remaining salary over twice the remaining years plus one."),
    ("Trade kicker", "A bonus of up to 15% of the remaining contract, paid the first time a player is traded."),
    ("Traded player exception (TPE)", "Credit created by sending out more salary than you take back; used within "
                                      "a year to absorb a player."),
    ("Two-way contract", "A deal split between the NBA team and its G League affiliate; up to 50 active NBA games "
                         "and off the cap."),
    ("Unlikely bonus", "An incentive the player didn't reach last season. Off the cap and tax until earned, but "
                       "counted for the aprons."),
    ("Years of service", "Seasons on an NBA roster; they set the minimum and maximum a player can earn."),
]


def _glossary():
    _anchor("glossary")
    _sec("Glossary of cap terms")
    _html_block('<div class="cba"><div class="cba-gl">' + "".join(
        f"<div><b>{_e(k)}.</b> {_e(v)}</div>" for k, v in _GLOSSARY) + "</div></div>")


# ------------------------------------------------------------------------------------------------------ the entry
def render(team_name, team_color, team_payrolls):
    """Draws the whole CBA Guide for one team. team_payrolls: {"2026-27": dollars, ...} (may be empty)."""
    team_name = str(team_name or "your team")
    payrolls = _clean_payrolls(team_payrolls)
    color = _readable_team_color(team_color)
    st.markdown(_CSS, unsafe_allow_html=True)
    _intro(team_name)
    _big_picture()
    _thresholds()
    _aprons()
    _exceptions()
    _contracts()
    _trades()
    _tax(team_name, color, payrolls)
    _floor()
    _calendar()
    _your_team(team_name, team_color, payrolls)
    _audiences(team_name)
    _glossary()
