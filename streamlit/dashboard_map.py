"""
dashboard_map.py -- everything AI Search knows about the dashboard itself (and a little about the website), read
straight from the code every time the code changes, so it never goes out of date.

Nothing here is a hand-kept list of pages. It reads:

  app.py             the sidebar (CATEGORIES), every page's block (`if category == "..."`): its titles, captions,
                     info cards, sub-tabs (`*_tabs = [...]`) and what each tab shows, the labels of its controls, and
                     the docstrings of the functions each page calls; Search by Player / Team's visualization list
                     (per mode) and each chart's controls; the Glossary's descriptions
  stats_config.py    the visualization categories (VIZ_CATEGORIES)
  criteria_tools.py  Search by Criteria's tools and their captions
  ../docs            the website: its menu, each page's headings, the home page's sections and live windows,
                     and the Author page

Public:

    site_map()               {"pages": [...], "places": {place_id: place}, "website": {...}}  (cached per file change)
    outline_text()           a compact outline of the whole dashboard, for AI Search's system prompt
    search(query, limit=6)   the places that best match a question like "where is the tax calculator?"
    place(place_id)          one place (None if unknown)

A place is somewhere AI Search can link to: {"id", "page", "path", "what", "controls", "nav", "soon"}. "nav" is what
app.py needs to open it: {"page": ..., "viz_category"/"visualization" | "tab" | "tool" | "term": ...}.
"""

import ast
import functools
import html as _html
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
APP = os.path.join(HERE, "app.py")
STATS_CONFIG = os.path.join(HERE, "stats_config.py")
CRITERIA = os.path.join(HERE, "criteria_tools.py")
DOCS = os.path.join(ROOT, "docs")

CREATOR = "Alex Bradley"
DASHBOARD_URL = "https://bradleyanalytics.streamlit.app"

_WIDGETS = {"selectbox", "radio", "multiselect", "slider", "select_slider", "number_input", "text_input", "text_area",
            "button", "toggle", "checkbox", "file_uploader", "pills", "segmented_control", "download_button",
            "date_input", "color_picker", "chat_input"}
_HEADINGS = {"title", "header", "subheader"}
_TEXTS = {"caption", "write", "info"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-") or "x"


# ------------------------------------------------------------------------------------------------ reading the code
def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _str(node):
    """The text of a string literal, an implicitly joined one, or an f-string's fixed parts ({...} as '...')."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "..." for v in node.values).strip()
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = _str(node.left), _str(node.right)
        return (a or "") + (b or "") if (a or b) else None
    return None


def _literal(node):
    try:
        return ast.literal_eval(node)
    except Exception:  # noqa: BLE001
        return None


def _clean(text, limit=320):
    t = re.sub(r"<[^>]+>", " ", str(text or ""))
    t = _html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + "..."


def _first_para(doc):
    if not doc:
        return ""
    return _clean(doc.strip().split("\n\n")[0], 360)


def _call_name(call):
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


_GENERIC_CONTROLS = {"Download .png", "Add to Tableau Dashboard", 'Share to the "Community Uploads" page', "Your name:",
                     "Description:", "Post", "Or enter a color code instead:", "Download the full PDF"}
_HEADING_HELPERS = {"_sec", "_sub", "section_heading", "_heading"}


class _Collector:
    """Walks some statements and gathers what a person would see: headings, captions, control labels, info cards, and
    (a level or two down) the contents of the page's own functions it calls -- the docstrings only of the ones that draw
    something (render_...), so a helper's notes never pass for a page's description."""

    def __init__(self, funcs, depth=3):
        self.funcs, self.depth = funcs, depth

    def collect(self, stmts, depth=None, seen=None, funcs=None):
        depth = self.depth if depth is None else depth
        seen = set() if seen is None else seen
        funcs = self.funcs if funcs is None else funcs
        out = {"headings": [], "texts": [], "controls": [], "docs": [], "soon": []}
        for node in (n for s in stmts for n in ast.walk(s)):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            arg0 = _str(node.args[0]) if node.args else None
            if (name in _HEADINGS or name in _HEADING_HELPERS) and arg0:
                out["headings"].append(_clean(arg0, 90))
            elif name == "markdown" and arg0 and arg0.lstrip().startswith("#"):
                out["headings"].append(_clean(arg0.lstrip("# ").strip(), 90))
            elif name in _TEXTS and arg0 and len(arg0) > 12:
                out["texts"].append(_clean(arg0))
            elif name in _WIDGETS and arg0 and arg0.strip() and len(arg0) < 90 and arg0 not in _GENERIC_CONTROLS:
                out["controls"].append(_clean(arg0, 90))
            elif name in ("info_card",) and arg0:
                body = _str(node.args[1]) if len(node.args) > 1 else ""
                out["texts"].append(_clean(f"{arg0}: {body}"))
            elif name == "coming_soon" and arg0:
                out["soon"].append(arg0)
            fn, sub_funcs, key = None, funcs, name
            if isinstance(node.func, ast.Name) and name in funcs:
                fn = funcs[name]
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                sub_funcs = _module_funcs(node.func.value.id)       # a function in one of the dashboard's own modules
                fn, key = sub_funcs.get(name), f"{node.func.value.id}.{name}"
            if fn is not None and key not in seen and depth > 0:
                seen.add(key)
                if fn.name.startswith("render"):
                    doc = _first_para(ast.get_docstring(fn))
                    if doc:
                        out["docs"].append(doc)
                sub = self.collect(fn.body, depth - 1, seen, sub_funcs)
                for k in out:
                    out[k].extend(sub[k])
        for k in out:
            out[k] = list(dict.fromkeys(x for x in out[k] if x))
        return out


@functools.lru_cache(maxsize=64)
def _module_funcs(mod):
    """{function name: FunctionDef} of the dashboard's own module `mod` (streamlit/<mod>.py), {} for anything else."""
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", mod or "") or mod in ("st", "pd", "np", "plt", "os", "re", "json"):
        return {}
    tree = _parse(os.path.join(HERE, mod + ".py"))
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)} if tree else {}


def _compare_eq(test, left_pred):
    """'X == "Name"' (left_pred(X) true) -> "Name", else None."""
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq) and left_pred(test.left):
        return _str(test.comparators[0])
    return None


def _if_chain(node):
    """An if / elif / elif ... chain as [(test, body), ...]."""
    out = []
    while isinstance(node, ast.If):
        out.append((node.test, node.body))
        node = node.orelse[0] if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If) else None
    return out


def _name_is(n, *ids):
    return isinstance(n, ast.Name) and n.id in ids


def _assigned(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(_name_is(t, name) for t in node.targets):
            return node.value
    return None


# ------------------------------------------------------------------------------------------------ the dashboard
def _pages(tree, funcs):
    col = _Collector(funcs)
    cats = _literal(_assigned(tree, "CATEGORIES")) or []
    blocks = {}
    for node in tree.body:
        for test, body in _if_chain(node):
            cat = _compare_eq(test, lambda n: _name_is(n, "category"))
            if cat and cat not in blocks:
                blocks[cat] = body
    # Search by Player / Search by Team: everything after `mode = "player" if category == "Search by Player" ...`
    tail = []
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.Assign) and any(_name_is(t, "mode") for t in node.targets):
            tail = tree.body[i:]
            break
    pages = []
    empty = {"headings": [], "texts": [], "controls": [], "docs": [], "soon": []}
    for cat in cats:
        body = blocks.get(cat)
        info = col.collect(body) if body else dict(empty)
        own = col.collect([s for s in body if not isinstance(s, ast.If)], depth=1) if body else dict(empty)
        info["own_headings"] = own["headings"]
        info["intro"] = own["texts"][:2] or [d for d in own["docs"] if not re.search(r"\bReturns?\b|callers", d)][:1]
        tabs, tab_info = [], {}
        if body:
            for node in (n for s in body for n in ast.walk(s)):
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id.endswith("_tabs") for t in node.targets):
                    lst = _literal(node.value)
                    if isinstance(lst, list) and all(isinstance(x, str) for x in lst):
                        tabs = lst
                if isinstance(node, ast.If):
                    for test, tbody in _if_chain(node):
                        tab = _compare_eq(test, lambda n: isinstance(n, ast.Name) and n.id.endswith("_tab"))
                        if tab and tab not in tab_info:
                            tab_info[tab] = col.collect(tbody)
            # a header helper that takes the tab list and a subtitle (Front Office / Coaching)
            for node in (n for s in body for n in ast.walk(s)):
                if isinstance(node, ast.Call) and _call_name(node) == "render_section_header":
                    for kw in node.keywords:
                        if kw.arg == "subtitle" and _str(kw.value):
                            info["texts"].insert(0, _clean(_str(kw.value)))
                            info["intro"] = [_clean(_str(kw.value))]
        pages.append({"name": cat, "info": info, "tabs": tabs, "tab_info": tab_info,
                      "viz": _visualizations(tree, tail, col, cat) if cat in ("Search by Player", "Search by Team") and tail else None})
    return pages


def _visualizations(tree, tail, col, cat):
    """Search by Player / Team: {category: [(internal name, shown name, controls), ...]} for this mode."""
    try:
        import stats_config as sc
    except Exception:  # noqa: BLE001
        return None
    mode = "player" if cat == "Search by Player" else "team"
    both = _literal(_assigned(tree, "BOTH_MODE_COMPARISON_GRAPHS")) or []
    team_only = _literal(_assigned(tree, "TEAM_ONLY_AXIS_GRAPHS")) or []
    player_only = [g for g in getattr(sc, "COMPARISON_GRAPHS", []) if g not in both]
    offered = (list(getattr(sc, "COURT_GRAPHS", [])) + list(getattr(sc, "AXIS_GRAPHS", [])) + list(getattr(sc, "ANIMATED_GRAPHS", []))
               + both + ((list(getattr(sc, "GAME_LOG_GRAPHS", [])) + player_only) if mode == "player" else team_only))
    hidden = set()
    for node in ast.walk(tree):          # the display modes that aren't their own entries (Dot Plot, Density Plot ...)
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.NotIn) \
                and isinstance(node.comparators[0], ast.Tuple) and _name_is(node.left, "v"):
            t = _literal(node.comparators[0])
            if t and "Dot Plot" in t:
                hidden |= set(t)
    shown = _literal(_assigned(tree, "VIZ_DISPLAY_NAMES")) or {}
    flags = {}
    for node in tail:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            v = _compare_eq(node.value, lambda n: _name_is(n, "visualization"))
            if v:
                flags[node.targets[0].id] = v
    controls = {}
    for node in (n for s in tail for n in ast.walk(s)):
        if not isinstance(node, ast.If):
            continue
        names = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
        hits = [flags[n] for n in names if n in flags]
        if len(hits) == 1 and hits[0] not in controls:
            controls[hits[0]] = col.collect(node.body, depth=1)["controls"][:14]
    out = {}
    for vcat, items in getattr(sc, "VIZ_CATEGORIES", {}).items():
        lst = [(v, shown.get(v, v), controls.get(v, [])) for v in items if v in offered and v not in hidden]
        if lst:
            out[vcat] = lst
    return out


def _loose_str(node):
    """A string, or for something computed (e.g. a dict lookup with a default) the longest string written in it."""
    s = _str(node)
    if s is not None:
        return s
    found = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return max(found, key=len) if found else ""


def _glossary(tree):
    """[(section, [(term, description), ...]), ...] from the Glossary page's GLOSSARY list."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(_name_is(t, "GLOSSARY") for t in node.targets) \
                and isinstance(node.value, ast.List):
            out = []
            for sec in node.value.elts:
                if not (isinstance(sec, ast.Tuple) and len(sec.elts) == 2 and isinstance(sec.elts[1], ast.List)):
                    continue
                terms = []
                for t in sec.elts[1].elts:
                    if isinstance(t, ast.Tuple) and len(t.elts) == 2 and _str(t.elts[0]):
                        terms.append((_str(t.elts[0]), _clean(_loose_str(t.elts[1]), 400)))
                out.append((_str(sec.elts[0]) or "", terms))
            return out
    return []


def _criteria():
    tree = _parse(CRITERIA)
    if tree is None:
        return [], {}
    tools = _literal(_assigned(tree, "TOOLS")) or []
    caps = {}
    val = _assigned(tree, "CAPTIONS")
    if isinstance(val, ast.Dict):
        for k, v in zip(val.keys, val.values):
            key = _str(k)
            if key is None and isinstance(k, ast.Subscript) and _name_is(k.value, "TOOLS"):
                i = _literal(k.slice)
                key = tools[i] if isinstance(i, int) and i < len(tools) else None
            if key:
                caps[key] = _clean(_str(v) or "")
    return tools, caps


def _parse(path):
    src = _read(path)
    try:
        return ast.parse(src) if src else None
    except SyntaxError:
        return None


# ------------------------------------------------------------------------------------------------ the website
def _website():
    site = {"url": "https://www.bradley-analytics.com", "menu": [], "pages": {}, "home": {}, "author": ""}
    cname = _read(os.path.join(DOCS, "CNAME")).strip()
    if cname:
        site["url"] = "https://" + cname
    nav = _read(os.path.join(DOCS, "_includes", "nav.html"))
    for href, text in re.findall(r'<a href="([^"#]+?\.html)"[^>]*>([^<]+)</a>', nav):
        if "brand-option" in text:
            continue
        site["menu"].append((_clean(text, 40), href))
    site["menu"] = [m for m in dict.fromkeys(site["menu"]) if not m[1].startswith("http")]
    for fn in sorted(os.listdir(DOCS)) if os.path.isdir(DOCS) else []:
        if not fn.endswith(".md"):
            continue
        txt = _read(os.path.join(DOCS, fn))
        title = (re.search(r"^title:\s*(.+)$", txt, re.M) or [None, fn[:-3]])[1].strip()
        heads = [_clean(h, 70) for h in re.findall(r"^#{2,3}\s+(.+)$", txt, re.M)][:12]
        site["pages"][fn[:-3] + ".html"] = {"title": title, "sections": heads}
        if fn == "author.md":
            body = re.sub(r"^---.*?---", "", txt, flags=re.S)
            body = re.sub(r"(?im)^(phone:.*|\(\d{3}\).*)$", "", body)
            site["author"] = _clean(re.sub(r"[#*_\[\]]", " ", re.sub(r"\]\((https?://[^)]+)\)", r" (\1)", body)), 900)
    index = _read(os.path.join(DOCS, "index.html"))
    if index:
        cards = re.findall(r'<div class="feature-card[^"]*">\s*<h3>(.*?)</h3>\s*<p>(.*?)</p>', index, re.S)
        site["home"]["engines"] = [(_clean(h, 60), _clean(p, 240)) for h, p in cards]
        heads = [_clean(h, 90) for h in re.findall(r"<h[12][^>]*>(.*?)</h[12]>", index, re.S)]
        site["home"]["headings"] = [h for h in heads if h][:10]
    js = _read(os.path.join(DOCS, "assets", "live-strip.js"))
    titles = re.findall(r'makeCard\(\{[^}]*?(?:name|title):\s*"([^"]{3,40})"', js) + \
        re.findall(r'el\("div", "ls-title", "([^"]{3,40})"\)', js)
    site["home"]["live_windows"] = list(dict.fromkeys(titles))[:16]
    return site


# ------------------------------------------------------------------------------------------------ the places
def _add(places, pid, page, path, what, controls=(), nav=None, soon=False, words=""):
    places[pid] = {"id": pid, "page": page, "path": path, "what": _clean(what, 420), "controls": list(controls)[:16],
                   "nav": nav or {"page": page}, "soon": bool(soon), "words": words}


def _build(_key):
    tree = _parse(APP)
    if tree is None:
        return {"pages": [], "places": {}, "website": _website(), "glossary": []}
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    pages = _pages(tree, funcs)
    glossary = _glossary(tree)
    gloss = {t: d for _s, terms in glossary for t, d in terms}
    tools, caps = _criteria()
    places = {}

    def gloss_for(*names):
        for n in names:
            for t, d in gloss.items():
                if n and (t == n or n in [x.strip() for x in re.split(r"/", t)]):
                    return d
        return ""

    for p in pages:
        name, info = p["name"], p["info"]
        pid = slug(name)
        what = " ".join(info.get("intro") or info["texts"][:1] or info["docs"][:1])
        if name == "Search by Criteria" and tools:
            what = "Search the whole league by criteria. Tools: " + " ".join(f"{t} - {caps.get(t, '')}" for t in tools)
        if name in ("Search by Player", "Search by Team"):
            what = (f"Pick a {'player' if name == 'Search by Player' else 'team'}, a visualization category and a chart, "
                    f"then press RUN. " + what)
        # (a page with tabs is found by its own words; what's in its tabs finds the tab)
        _add(places, pid, name, name, what or gloss_for(name), [] if p["tabs"] else info["controls"],
             words=" ".join(info["own_headings"] if p["tabs"] else info["headings"]))
        for tab in p["tabs"]:
            ti = p["tab_info"].get(tab, {"headings": [], "texts": [], "controls": [], "docs": [], "soon": []})
            soon = tab in info["soon"] or tab in ti.get("soon", [])
            twhat = "Coming soon." if soon else " ".join(ti["texts"][:2] + ti["docs"][:2])
            _add(places, f"{pid}/{slug(tab)}", name, f"{name} › {tab}", twhat, ti["controls"],
                 nav={"page": name, "tab": tab}, soon=soon, words=" ".join(ti["headings"]))
        for vcat, items in (p["viz"] or {}).items():
            _add(places, f"{pid}/{slug(vcat)}", name, f"{name} › {vcat}",
                 f"The {vcat} charts: " + ", ".join(s for _v, s, _c in items) + ".",
                 nav={"page": name, "viz_category": vcat})
            for v, shown, ctl in items:
                _add(places, f"{pid}/{slug(vcat)}/{slug(v)}", name, f"{name} › {vcat} › {shown}",
                     gloss_for(shown, v) or shown, ctl, nav={"page": name, "viz_category": vcat, "visualization": v},
                     words=v)
        if name == "Search by Criteria":
            for t in tools:
                _add(places, f"{pid}/{slug(t)}", name, f"{name} › {t}", caps.get(t, ""), nav={"page": name, "tool": t})
        if name == "Glossary":
            for _sec, terms in glossary:
                for t, d in terms:
                    _add(places, f"{pid}/{slug(t)}", name, f"Glossary › {t}", d, nav={"page": name, "term": t})
    return {"pages": pages, "places": places, "website": _website(), "glossary": glossary,
            "criteria": (tools, caps)}


def _key():
    paths = [APP, STATS_CONFIG, CRITERIA, os.path.join(DOCS, "index.html"), os.path.join(DOCS, "_includes", "nav.html")]
    return tuple(os.path.getmtime(p) if os.path.exists(p) else 0 for p in paths)


@functools.lru_cache(maxsize=4)
def _cached(key):
    return _build(key)


def site_map():
    return _cached(_key())


def place(pid):
    return site_map()["places"].get(str(pid or "").strip().lower().replace(" ", "-").strip("/"))


# ------------------------------------------------------------------------------------------------ for the AI
def outline_text(compact=False):
    """The whole dashboard, compactly: the sidebar in order, each page with its tabs / chart lists / tools, the place id
    to link each by, and a few lines about the website and who built it. compact: shorter descriptions, and the charts
    by name only (a chart's link id is its category's id + "/" + the chart's own id, which dashboard_guide gives)."""
    m = site_map()
    if compact:
        lines = [f"Created by {CREATOR}. Website {m['website']['url']} (menu: " +
                 ", ".join(t for t, _h in m["website"]["menu"]) + "); the dashboard is embedded on its home page.",
                 "SIDEBAR, top to bottom [link id]:"]
        for p in m["pages"]:
            name, pid = p["name"], slug(p["name"])
            what = _clean(m["places"].get(pid, {}).get("what", ""), 110)
            lines.append(f"- {name} [{pid}]" + (f": {what}" if what else ""))
            if p["tabs"]:
                lines.append("    tabs: " + "; ".join(
                    f"{t}{' (coming soon)' if m['places'].get(f'{pid}/{slug(t)}', {}).get('soon') else ''} [{pid}/{slug(t)}]"
                    for t in p["tabs"]))
            for vcat, items in (p["viz"] or {}).items():
                lines.append(f"    {vcat} [{pid}/{slug(vcat)}]: " + ", ".join(s for _v, s, _c in items))
            if name == "Search by Criteria":
                tools, _caps = m.get("criteria", ([], {}))
                lines.append("    tools: " + "; ".join(f"{t} [{pid}/{slug(t)}]" for t in tools))
            if name == "Glossary":
                lines.append("    each term: [glossary/<term>] via dashboard_guide")
        return "\n".join(lines)
    lines = [f"Bradley Analytics was created by {CREATOR} (the dashboard, its AI Search and the website "
             f"{m['website']['url']}). The dashboard runs at {DASHBOARD_URL} and inside the website's home page.",
             "SIDEBAR, top to bottom (link id in brackets):"]
    for p in m["pages"]:
        name, pid = p["name"], slug(p["name"])
        pl = m["places"].get(pid, {})
        head = f"- {name} [{pid}]"
        if pl.get("what"):
            head += ": " + _clean(pl["what"], 170)
        lines.append(head)
        if p["tabs"]:
            lines.append("    tabs: " + "; ".join(
                f"{t}{' (coming soon)' if m['places'].get(f'{pid}/{slug(t)}', {}).get('soon') else ''} [{pid}/{slug(t)}]"
                for t in p["tabs"]))
        for vcat, items in (p["viz"] or {}).items():
            lines.append(f"    {vcat} [{pid}/{slug(vcat)}]: " + "; ".join(
                f"{s} [{pid}/{slug(vcat)}/{slug(v)}]" for v, s, _c in items))
        if name == "Search by Criteria":
            tools, _caps = m.get("criteria", ([], {}))
            lines.append("    tools: " + "; ".join(f"{t} [{pid}/{slug(t)}]" for t in tools))
        if name == "Glossary":
            lines.append("    every term has its own link: [glossary/<term slug>] (see dashboard_guide)")
    w = m["website"]
    if w.get("menu"):
        lines.append("WEBSITE " + w["url"] + " menu: " + ", ".join(t for t, _h in w["menu"]) + ".")
    if w["home"].get("engines"):
        lines.append("Website home page: live NBA game windows (" + ", ".join(w["home"].get("live_windows", [])[:12]) +
                     "), the embedded dashboard, and 'Six engines, one dashboard': " +
                     ", ".join(h for h, _p in w["home"]["engines"]) + ".")
    return "\n".join(lines)


_STOP = {"the", "a", "an", "is", "are", "where", "what", "which", "how", "do", "i", "can", "to", "of", "in", "on", "for",
         "and", "or", "my", "me", "find", "get", "see", "show", "with", "it", "this", "that", "does", "there", "any",
         "page", "section", "tab", "dashboard", "go", "open", "use", "into", "at", "by", "from", "be", "you", "your"}


def _tokens(s):
    return [t for t in re.findall(r"[a-z0-9%/+]+", str(s).lower()) if t not in _STOP]


def search(query, limit=6):
    """The places best matching a free-text question, best first."""
    m = site_map()
    q = _tokens(query)
    if not q:
        return []
    scored = []
    for pl in m["places"].values():
        path, what = pl["path"].lower(), (pl["what"] + " " + pl.get("words", "")).lower()
        ctl = " ".join(pl["controls"]).lower()
        s = 0.0
        for t in q:
            if re.search(r"\b" + re.escape(t), path):
                s += 3.0
            if re.search(r"\b" + re.escape(t), what):
                s += 1.0
            if re.search(r"\b" + re.escape(t), ctl):
                s += 0.8
        if " ".join(q) in path:
            s += 3
        if s:
            s -= 0.15 * pl["path"].count("›")          # a tie goes to the broader place
            if pl["page"] == "Glossary":
                s -= 0.5                                 # the tool itself before its glossary entry
            scored.append((s, pl))
    scored.sort(key=lambda x: -x[0])
    return [pl for _s, pl in scored[:limit]]


def guide(query=None, limit=6):
    """The AI tool: matching places (with their link), or the whole outline when nothing is asked."""
    m = site_map()
    if not query:
        return {"outline": outline_text()}
    hits = search(query, limit)
    out = []
    for pl in hits:
        out.append({"place_id": pl["id"], "where": pl["path"], "what_it_does": pl["what"],
                    "controls": pl["controls"][:10], "sections": _clean(pl.get("words", ""), 500), "coming_soon": pl["soon"],
                    "link": f"[{pl['path'].split(' › ')[-1]}](dashboard:{pl['id']})"})
    res = {"matches": out}
    ql = str(query).lower()
    w = m["website"]
    if re.search(r"website|site|bradley-analytics\.com|home page|live window|author|creator|who (made|built|created)|alex", ql):
        res["website"] = {"url": w["url"], "menu": [t for t, _h in w["menu"]],
                          "pages": {v["title"]: v["sections"][:8] for v in w["pages"].values()},
                          "home_page": w["home"], "author_page": w["author"]}
    if not out:
        res["note"] = "Nothing in the dashboard matches that; here is the outline."
        res["outline"] = outline_text()
    return res
