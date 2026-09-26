"""
Keeps Streamlit Community Cloud apps awake by actually visiting them in a real
headless browser, and CHECKS that each app really came up.

Why a browser, and why not UptimeRobot
  Community Cloud puts any app with no traffic for 12 hours to sleep
  (docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app), and its
  documented fix is to "simply visit your app". An uptime monitor only sends a
  plain HTTP request: the platform's small web page answers 200 OK, so the
  monitor reports "up" while the app itself is still asleep, and no real
  session (the websocket a browser opens) ever exists. So UptimeRobot can tell
  you a page answered, but it can neither wake an app nor keep one awake.
  Only a real visit does, which is what this script does. It is not needed
  alongside this job, and it does not replace it.

What each run does, per app
  1. Opens the app. If the "Zzzz... gone to sleep" page appears, clicks
     "Yes, get this app back up!".
  2. Waits (up to KEEP_ALIVE_BOOT_TIMEOUT seconds, default 300) until the app
     has actually rendered. A cold start can take a few minutes.
  3. Stays on it briefly so it counts as real traffic.
  4. Tries once more from a fresh browser if that failed.
  If an app still isn't up, the script exits with an error, so the GitHub
  Actions run turns red and GitHub emails you, instead of staying green while
  the app sleeps.

Settings (environment variables, all optional)
  KEEP_ALIVE_URLS          comma-separated URLs, instead of APP_URLS below
  KEEP_ALIVE_BOOT_TIMEOUT  seconds to wait for an app to come up (default 300)
  KEEP_ALIVE_STAY          seconds to stay on the app once it is up (default 20)
"""

import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

# Add every dashboard URL that needs to stay awake here.
APP_URLS = [
    "https://bradleyanalytics.streamlit.app",
    "https://bradleyquant.streamlit.app",
]
if os.environ.get("KEEP_ALIVE_URLS"):
    APP_URLS = [u.strip() for u in os.environ["KEEP_ALIVE_URLS"].split(",") if u.strip()]

BOOT_TIMEOUT_S = int(os.environ.get("KEEP_ALIVE_BOOT_TIMEOUT", "300"))
STAY_S = int(os.environ.get("KEEP_ALIVE_STAY", "20"))

# Wording of the sleeping-app page's button. Matched case-insensitively.
WAKE_PATTERNS = [r"get this app back up", r"wake (this app )?up"]


def app_is_up(page) -> bool:
    """True once a running Streamlit app has rendered. Looks in every frame: on Community Cloud the app sits inside an iframe."""
    for frame in page.frames:
        try:
            if frame.locator('[data-testid="stApp"]').count() > 0:
                return True
        except Exception:
            continue
    return False


def click_wake_button(page) -> bool:
    for frame in page.frames:
        for pattern in WAKE_PATTERNS:
            rx = re.compile(pattern, re.I)
            try:
                for locator in (frame.get_by_role("button", name=rx), frame.get_by_text(rx)):
                    if locator.count() > 0:
                        locator.first.click(timeout=5_000)
                        return True
            except Exception:
                continue
    return False


def visit(playwright, url: str):
    """(True, how) if the app is up after this visit, else (False, why)."""
    browser = playwright.chromium.launch()
    try:
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(url, timeout=90_000, wait_until="domcontentloaded")
        woke = False
        deadline = time.time() + BOOT_TIMEOUT_S
        while time.time() < deadline:
            if app_is_up(page):
                page.wait_for_timeout(STAY_S * 1000)
                return True, "woken up and running" if woke else "already awake"
            if click_wake_button(page):
                woke = True
                page.wait_for_timeout(3_000)
                continue
            page.wait_for_timeout(2_000)
        try:
            seen = re.sub(r"\s+", " ", page.inner_text("body"))[:160]
        except Exception:
            seen = "(page not readable)"
        return False, f"app did not come up within {BOOT_TIMEOUT_S}s; the page said: {seen!r}"
    finally:
        browser.close()


def main() -> int:
    failed = []
    with sync_playwright() as playwright:
        for url in APP_URLS:
            print(f"Visiting {url} ...", flush=True)
            ok, detail = False, ""
            for attempt in (1, 2):
                try:
                    ok, detail = visit(playwright, url)
                except Exception as exc:
                    ok, detail = False, f"{type(exc).__name__}: {str(exc)[:160]}"
                if ok:
                    break
                print(f"  attempt {attempt} failed: {detail}", flush=True)
                if attempt == 1:
                    time.sleep(20)
            print(f"  {'OK' if ok else 'FAILED'}: {url} -- {detail}", flush=True)
            if not ok:
                failed.append(url)
    if failed:
        print(f"\n{len(failed)} app(s) did not come up: {', '.join(failed)}", flush=True)
        return 1
    print(f"\nAll {len(APP_URLS)} app(s) are awake.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
