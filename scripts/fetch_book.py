"""Keeps the Bradley Analytics Book on the Portfolio page in step with its Google Slides deck:

  1. reads the deck's public embed page and saves its slides' ids, in order, to docs/data/book.json, so the page strip
     and the page count always match the deck;
  2. renders every page into docs/data/book/: a sharp one for the main view (l/<id>.webp, 1080 x 1350) and a small one
     for the strip (s/<id>.webp, 120 x 150). Each page is Google's own vector (SVG) copy of the slide, drawn by a real
     browser (headless Chromium), so photos with cut-outs, masks and transparency look exactly as they do in Slides.
     (The deck's PDF copy loses some of those effects; it's only used for a page whose SVG can't be read.)

Run daily by .github/workflows/book.yml (needs: pip install playwright pymupdf pillow, then
python -m playwright install --with-deps chromium). Pictures of removed pages are deleted.

    python3 scripts/fetch_book.py docs/data/book.json
"""
import io
import json
import os
import re
import sys
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (bradley-analytics book)"}
LARGE, SMALL = (1080, 1350), (120, 150)


def get(url, tries=4):
    for k in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read()
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(5 * (k + 1))


def page_ids(deck):
    html = get("https://docs.google.com/presentation/d/%s/embed?start=false&loop=false&rm=minimal" % deck).decode("utf-8", "replace").replace('\\"', '"')
    seen, pages = set(), []
    for m in re.finditer(r'\["([A-Za-z0-9_]+)",(\d+),"((?:[^"\\]|\\.)*)",\[\]', html):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            pages.append((int(m.group(2)), m.group(1)))
    return [p for _, p in sorted(pages)]


def save(im, folder, pid, Image):
    im = im.convert("RGB")
    im.resize(LARGE, Image.LANCZOS).save(os.path.join(folder, "l", pid + ".webp"), "WEBP", quality=84, method=6)
    im.resize(SMALL, Image.LANCZOS).save(os.path.join(folder, "s", pid + ".webp"), "WEBP", quality=72, method=6)


def from_svg(deck, pages, folder, Image):
    """Every page drawn from its SVG by headless Chromium. Returns the ids it couldn't do."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright isn't installed: using the PDF copy.")
        return list(pages)
    missed = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": LARGE[0], "height": LARGE[1]}, device_scale_factor=1)
        for k, pid in enumerate(pages):
            try:
                svg = get("https://docs.google.com/presentation/d/%s/export/svg?pageid=%s" % (deck, pid)).decode("utf-8", "replace")
                pg.set_content('<!doctype html><html><body style="margin:0;background:#000;overflow:hidden">'
                               '<div id="s" style="width:%dpx;height:%dpx">%s</div></body></html>' % (LARGE[0], LARGE[1], svg))
                pg.evaluate("""() => { const s = document.querySelector('#s svg'); s.setAttribute('width', '100%%'); s.setAttribute('height', '100%%');
                               s.setAttribute('preserveAspectRatio', 'xMidYMid meet'); }""")
                pg.wait_for_load_state("networkidle", timeout=30000)
                pg.evaluate("() => Promise.all([...document.images].map(i => i.decode ? i.decode().catch(() => 0) : 0))")
                png = pg.screenshot(clip={"x": 0, "y": 0, "width": LARGE[0], "height": LARGE[1]})
                save(Image.open(io.BytesIO(png)), folder, pid, Image)
            except Exception as e:  # noqa: BLE001
                print("Page", k + 1, "couldn't be drawn from its SVG:", e)
                missed.append(pid)
            time.sleep(0.4)                                  # (gently: Google limits how fast one visitor can read)
        b.close()
    return missed


def from_pdf(deck, pages, only, folder, Image):
    try:
        try:
            import pymupdf as fitz                   # PyMuPDF
        except ImportError:
            import fitz
    except ImportError:
        print("PyMuPDF isn't installed: skipping", len(only), "page(s).")
        return False
    pdf = fitz.open(stream=get("https://docs.google.com/presentation/d/%s/export/pdf" % deck), filetype="pdf")
    if pdf.page_count != len(pages):
        print("The PDF has %d pages but the deck lists %d: skipping those pages." % (pdf.page_count, len(pages)))
        return False
    for i, pid in enumerate(pages):
        if pid not in only:
            continue
        page = pdf[i]
        zoom = LARGE[1] / page.rect.height
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        save(Image.open(io.BytesIO(pix.tobytes("png"))), folder, pid, Image)
    return True


def pictures(deck, pages, folder):
    try:
        from PIL import Image
    except ImportError:
        print("Pillow isn't installed: skipping the page pictures.")
        return False
    for sub in ("s", "l"):
        os.makedirs(os.path.join(folder, sub), exist_ok=True)
    missed = from_svg(deck, pages, folder, Image)
    if missed:
        from_pdf(deck, pages, set(missed), folder, Image)
    have = set(f[:-5] for f in os.listdir(os.path.join(folder, "l")))
    if not all(p in have for p in pages):
        print("Some pages have no picture yet: keeping Google's copies on the site for now.")
        return False
    keep = set(p + ".webp" for p in pages)
    for sub in ("s", "l"):
        for f in os.listdir(os.path.join(folder, sub)):
            if f not in keep:
                os.remove(os.path.join(folder, sub, f))
    print("Saved pictures of all %d pages." % len(pages))
    return True


def main(path):
    book = json.load(open(path))
    pages = page_ids(book["deck"]) or book.get("pages", [])
    if len(pages) >= 2:
        book["pages"] = pages
    folder = os.path.join(os.path.dirname(path), "book")
    if pictures(book["deck"], book["pages"], folder):
        book["pictures"] = "data/book/"
        book["ext"] = ".webp"
    with open(path, "w") as f:
        json.dump(book, f)
    print("Book: %d pages." % len(book["pages"]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/data/book.json")
