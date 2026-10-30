"""Keeps a copy of 2kratings.com's Celtics logo in the repo (streamlit/assets/logos/ and docs/assets/logos/), so the
dashboard and the website always have the right logo even when 2kratings.com is slow or turns a server away (the
dashboard then fell back to a plain green "BOS" circle). The dashboard still asks 2kratings first; this copy is only
the backup. Also saves a PNG of it for the website's alerts. Run weekly by .github/workflows/logos.yml (needs cairosvg for the PNG).

    python3 scripts/fetch_logos.py
"""
import os
import time
import urllib.request

LOGOS = ["https://www.2kratings.com/wp-content/uploads/Boston-Celtics-Current-Logo.svg"]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36",
           "Referer": "https://www.2kratings.com/", "Accept": "image/svg+xml,image/*;q=0.8,*/*;q=0.5", "Accept-Language": "en-US,en;q=0.9"}
FOLDERS = ["streamlit/assets/logos", "docs/assets/logos"]


def main():
    for url in LOGOS:
        data = None
        for k in range(4):
            try:
                data = urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30).read()
                break
            except Exception as e:
                print("Try", k + 1, "failed:", e)
                time.sleep(5 * (k + 1))
        if not data or b"<svg" not in data[:4000]:
            print("Couldn't get", url, "- keeping the copy already saved.")
            continue
        name = url.rsplit("/", 1)[-1]
        for folder in FOLDERS:
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, name), "wb") as f:
                f.write(data)
        # a PNG of it too, for the website's alerts (a notification can't show an SVG)
        try:
            import cairosvg
            cairosvg.svg2png(bytestring=data, write_to=os.path.join("docs/assets/logos", name[:-4] + ".png"), output_height=512)
        except Exception as e:
            print("No PNG made:", e)
        print("Saved", name, len(data), "bytes")


if __name__ == "__main__":
    main()
