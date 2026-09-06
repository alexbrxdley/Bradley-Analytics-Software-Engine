"""
community_storage.py

Storage for Community Visualizations -- shared charts anyone using this
app has generated and chosen to publish for others to browse.

HONEST LIMITATION: this uses local JSON + PNG files on disk. That
works correctly right now, with zero extra setup, and persists across
reruns and restarts for as long as the current deployment stays up.
But Streamlit Community Cloud's filesystem is ephemeral -- redeploying
the app (pushing new code) wipes it. For true persistence across
redeploys, this would need to write somewhere outside the app's own
container instead, and the two realistic no-extra-cost-service options
are:

  1. Commit each share back to this GitHub repo via the GitHub API
     (needs a personal access token added as a Streamlit secret) --
     genuinely persistent, no new service to sign up for, but every
     share becomes a commit.
  2. A free-tier external database (Supabase, Firebase, etc.) -- the
     more conventional path, needs an account and a connection string
     added as a Streamlit secret.

Either upgrade only requires swapping the four functions below
(load_all/save_all) for equivalent read/write calls against whichever
backend is chosen -- the rest of the app only ever calls these four
functions and never touches the storage format directly.
"""

import json
import os
import time
import uuid

_DATA_DIR = os.path.join(os.path.dirname(__file__), "community_data")
_METADATA_PATH = os.path.join(_DATA_DIR, "visualizations.json")
_IMAGES_DIR = os.path.join(_DATA_DIR, "images")


def _ensure_dirs():
    os.makedirs(_IMAGES_DIR, exist_ok=True)


def load_all() -> list:
    """Every shared visualization's metadata, most recent first."""
    _ensure_dirs()
    if not os.path.exists(_METADATA_PATH):
        return []
    try:
        with open(_METADATA_PATH, "r") as f:
            items = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return sorted(items, key=lambda x: x.get("shared_at", 0), reverse=True)


def save_visualization(fig, name: str, description: str, source_section: str) -> str:
    """
    Saves a matplotlib figure -- OR, if fig is actually a GIF buffer
    (an animated visualization, which has no matplotlib figure object
    to save), saves that instead. Detected by duck-typing on savefig()
    rather than assuming a specific buffer type, since
    build_animated_shot_chart() returns an io.BytesIO, not raw bytes.
    Both branches write into the same images directory and metadata
    file, so Community Uploads renders either kind identically via its
    existing gallery loop.
    """
    _ensure_dirs()
    entry_id = str(uuid.uuid4())
    is_gif = not hasattr(fig, "savefig")
    image_filename = f"{entry_id}.gif" if is_gif else f"{entry_id}.png"
    image_path = os.path.join(_IMAGES_DIR, image_filename)
    if is_gif:
        fig.seek(0)
        with open(image_path, "wb") as f:
            f.write(fig.read())
    else:
        fig.savefig(image_path, dpi=120, bbox_inches="tight", transparent=True)

    items = load_all()
    items.append({
        "id": entry_id,
        "name": name,
        "description": description,
        "source_section": source_section,
        "image_filename": image_filename,
        "shared_at": time.time(),
    })
    with open(_METADATA_PATH, "w") as f:
        json.dump(items, f, indent=2)
    return entry_id


def get_image_path(image_filename: str) -> str:
    return os.path.join(_IMAGES_DIR, image_filename)
