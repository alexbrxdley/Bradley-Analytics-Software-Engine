"""Keeps the Bradley Analytics Book on the Portfolio page in step with its Google Slides deck:

  1. reads the deck's public embed page and saves its slides' ids, in order, to docs/data/book.json, so the page strip
     and the page count always match the deck;
  2. downloads the whole deck once as a PDF and renders every page into docs/data/book/: a sharp one for the main view
     (l/<id>.webp, 1080 x 1350) and a small one for the strip (s/<id>.webp, 120 x 150). The website loads these from
     the site itself, so every page shows at once, scrubbing is instant, and the page is crisp (Google's own page
     pictures are only 384 x 480 and it limits how many one visitor can load).

Run daily by .github/workflows/book.yml (needs: pip install pymupdf pillow). Pictures of removed pages are deleted.

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


def pictures(deck, pages, folder):
    try:
        try:
            import pymupdf as fitz                   # PyMuPDF
        except ImportError:
            import fitz
        from PIL import Image
    except ImportError:
        print("PyMuPDF / Pillow aren't installed: skipping the page pictures.")
        return False
    pdf = fitz.open(stream=get("https://docs.google.com/presentation/d/%s/export/pdf" % deck), filetype="pdf")
    if pdf.page_count != len(pages):
        print("The PDF has %d pages but the deck lists %d: skipping the pictures this time." % (pdf.page_count, len(pages)))
        return False
    for sub in ("s", "l"):
        os.makedirs(os.path.join(folder, sub), exist_ok=True)
    for i, pid in enumerate(pages):
        page = pdf[i]
        zoom = LARGE[1] / page.rect.height
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        im.resize(LARGE, Image.LANCZOS).save(os.path.join(folder, "l", pid + ".webp"), "WEBP", quality=80, method=6)
        im.resize(SMALL, Image.LANCZOS).save(os.path.join(folder, "s", pid + ".webp"), "WEBP", quality=72, method=6)
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
