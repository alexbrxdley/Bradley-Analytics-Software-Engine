"""Keeps an archive of the @bradleyanalytics Instagram posts for the website, so its grid can show the 9 most recent
even though Behold's free feed only ever lists the latest 6: every run adds the feed's posts (and a copy of each post's
picture, in docs/data/ig/) to docs/data/instagram.json, newest first, keeping the last 24. The site shows the live feed
and fills the rest of the grid from here. Run every few hours by .github/workflows/instagram.yml; standard library only.

    python3 scripts/fetch_instagram.py docs/data/instagram.json
"""
import json
import os
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (bradley-analytics instagram)"}


def feed_id():
    cfg = open(os.path.join("docs", "_config.yml"), encoding="utf-8").read()
    m = re.search(r'^behold_feed_id:\s*"?([A-Za-z0-9_-]+)"?', cfg, re.M)
    return m.group(1) if m else ""


def main(path):
    fid = feed_id()
    if not fid:
        print("No behold_feed_id in docs/_config.yml.")
        return
    d = json.loads(urllib.request.urlopen(urllib.request.Request("https://feeds.behold.so/" + fid, headers=UA), timeout=30).read())
    try:
        old = json.load(open(path, encoding="utf-8"))
    except Exception:
        old = {"posts": []}
    have = {p["id"]: p for p in old.get("posts", [])}
    folder = os.path.join(os.path.dirname(path), "ig")
    os.makedirs(folder, exist_ok=True)
    for p in d.get("posts", []):
        sz = p.get("sizes") or {}
        src = (sz.get("medium") or {}).get("mediaUrl") or p.get("thumbnailUrl") or p.get("mediaUrl")
        ext = ".webp" if src and ".webp" in src else ".jpg"
        name = re.sub(r"[^A-Za-z0-9_-]", "", str(p["id"])) + ext
        if src and not os.path.exists(os.path.join(folder, name)):
            try:
                with open(os.path.join(folder, name), "wb") as f:
                    f.write(urllib.request.urlopen(urllib.request.Request(src, headers=UA), timeout=60).read())
            except Exception as e:
                print("Couldn't save the picture for", p["id"], e)
                continue
        have[p["id"]] = {"id": p["id"], "timestamp": p.get("timestamp"), "permalink": p.get("permalink"), "mediaType": p.get("mediaType"),
                         "isReel": p.get("isReel"), "prunedCaption": (p.get("prunedCaption") or p.get("caption") or "")[:200], "img": "data/ig/" + name}
    posts = sorted(have.values(), key=lambda p: p.get("timestamp") or "", reverse=True)[:24]
    keep = set(os.path.basename(p["img"]) for p in posts)
    for f in os.listdir(folder):
        if f not in keep:
            os.remove(os.path.join(folder, f))
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"posts": posts}, f, ensure_ascii=False)
    print("%d posts archived." % len(posts))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "docs/data/instagram.json")
