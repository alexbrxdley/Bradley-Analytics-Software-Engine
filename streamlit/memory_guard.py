"""
Keeps the dashboard's server process under Streamlit Community Cloud's memory limit (2.7 GB at most).

When the process goes over that limit, Community Cloud stops the app: the red "!" next to it in your workspace and
"Oh no" / "This app has gone over its resource limits" for visitors, until someone reboots it. Every visitor (and
every hidden lineup request from the website) shares this one process, so memory that is never given back adds up
over hours until it hits the limit. Two things did that here:

  * Charts. Every chart is a matplotlib figure made with plt.subplots(), and matplotlib keeps every such figure in
    its own registry until it's closed -- st.pyplot() never closes it. Each chart held on to its image (5-25 MB), so a
    few hundred charts over a day was enough to crash the app. ui_hooks closes each chart once it's on the page (it
    can still be downloaded: a closed figure can still be saved), and check() below closes any left over.
  * Cached data with no size limit (league-wide shot charts are ~100 MB a season). nba_data's caches now have
    max_entries, and check() empties every cache if the process gets close to the limit anyway.

check() runs at the start of every script run. It is cheap: it reads two small files.
"""
import ctypes
import gc
import os
import threading
import time

import matplotlib.pyplot as plt

_LOCK = threading.Lock()
_STATE = {"last_clear": 0.0, "limit": None}
_FALLBACK_LIMIT = int(2.7e9)          # Community Cloud's maximum
_SHARE = 0.72                         # empty the caches past this share of the limit
_MAX_OPEN_FIGURES = 12                # figures still registered beyond this: none of them is in use by a page any more


def rss_bytes():
    """This process's resident memory, in bytes (0 if it can't be read)."""
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except Exception:  # noqa: BLE001
        return 0


def limit_bytes():
    """The container's memory limit (cgroup v2 or v1), else Community Cloud's 2.7 GB."""
    if _STATE["limit"] is None:
        lim = None
        for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
            try:
                with open(path) as f:
                    raw = f.read().strip()
                if raw.isdigit() and 256e6 < int(raw) < 64e9:
                    lim = int(raw)
                    break
            except Exception:  # noqa: BLE001
                continue
        _STATE["limit"] = lim or _FALLBACK_LIMIT
    return _STATE["limit"]


def _give_back():
    """Let the C allocator hand freed memory back to the system (glibc keeps it otherwise)."""
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:  # noqa: BLE001
        pass


def close_figures(force=False):
    """Closes every registered matplotlib figure when there are more than a handful (or always with force). Safe for
    other visitors' runs: nothing here draws through pyplot's "current figure", and a closed figure can still be
    saved and shown."""
    try:
        if force or len(plt.get_fignums()) > _MAX_OPEN_FIGURES:
            plt.close("all")
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def check(st):
    """Run at the start of every script run."""
    closed = close_figures()
    rss, lim = rss_bytes(), limit_bytes()
    if rss and rss > _SHARE * lim and time.time() - _STATE["last_clear"] > 45:
        with _LOCK:
            if time.time() - _STATE["last_clear"] <= 45:
                return
            _STATE["last_clear"] = time.time()
            close_figures(force=True)
            try:
                st.cache_data.clear()
            except Exception:  # noqa: BLE001
                pass
            gc.collect()
            _give_back()
    elif closed:
        gc.collect()
        _give_back()
