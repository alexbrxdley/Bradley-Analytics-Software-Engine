"""
community_storage.py

Storage for Community Uploads -- shared charts, plus the stat formulas people
invent in the Stat Formula Creator (a formula is stored as a small entry with
formula_data, so both kinds live in the same place).

WHY SHARES USED TO VANISH
  Streamlit Community Cloud's disk is ephemeral. Whenever the app sleeps and
  wakes, is rebooted, or is redeployed, its container is rebuilt from your
  repo and anything the app wrote to disk is gone. Files written to
  community_data/ at runtime are therefore lost unless they are also saved
  somewhere permanent.

HOW IT IS MADE PERMANENT
  Every share is also committed to a GitHub repo through the GitHub Contents
  API, and the gallery is rebuilt from that repo whenever a fresh container
  starts. Local files are still written first, so the app stays instant, and
  the app keeps working (just not permanently) if GitHub is not configured.

SETUP (once, about two minutes)
  1. GitHub -> Settings -> Developer settings -> Personal access tokens ->
     Fine-grained tokens -> Generate new token.
       - Repository access: "Only select repositories" -> this repo.
       - Permissions -> Repository permissions -> Contents: Read and write.
  2. Streamlit Community Cloud -> your app -> Settings -> Secrets, add:

        GITHUB_TOKEN  = "github_pat_..."
        GITHUB_REPO   = "owner/repo-name"
        GITHUB_BRANCH = "community-data"

     GITHUB_BRANCH is optional but recommended: shares are then committed to
     their own branch (created automatically) instead of your deployed one,
     so they never touch the branch Streamlit deploys or GitHub Pages builds.
     Without it, shares go to "main".
  3. Open the Community Uploads page: its status line says whether backup is
     working. Tokens expire (you choose when when you create one); an expired
     token shows up there as a "Bad credentials" error.

Failures are never silent: the last save's result is kept and shown on the
Community Uploads page and right after a share is posted.
"""

import base64
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

try:
    import streamlit as st
except ImportError:
    st = None

try:
    import requests
except ImportError:
    requests = None

_DATA_DIR = os.path.join(os.path.dirname(__file__), "community_data")
_METADATA_PATH = os.path.join(_DATA_DIR, "visualizations.json")
_IMAGES_DIR = os.path.join(_DATA_DIR, "images")

# Where the same files live inside the GitHub repo (kept identical to earlier
# versions so anything already backed up is still found).
_REMOTE_PREFIX = "streamlit/community_data"
_REMOTE_META = f"{_REMOTE_PREFIX}/visualizations.json"

_GITHUB_API = os.environ.get("BA_GITHUB_API", "https://api.github.com")  # env override exists for tests
_SYNC_TTL_SECONDS = 60          # how often a page view may re-check GitHub for new shares
_CHECK_TTL_SECONDS = 300        # how long a connection check is trusted
_MISSING_IMAGE_RETRY_SECONDS = 300
_MAX_PUSH_BYTES = 25 * 1024 * 1024

_lock = threading.RLock()       # one GitHub write at a time per server process
_status = {"ok": None, "error": None, "at": 0.0}       # result of the most recent save
_sync_state = {"at": 0.0}
_check_state = {"at": 0.0, "ok": None, "msg": ""}
_branch_ready = set()
_missing_until = {}


class GitHubError(Exception):
    def __init__(self, status, message):
        super().__init__(f"{status}: {message}" if status else message)
        self.status = status


def _ensure_dirs():
    os.makedirs(_IMAGES_DIR, exist_ok=True)


# --------------------------------------------------------------------------- config + HTTP
def _github_config():
    """(token, repo, branch) if GitHub persistence is configured, else None. Read fresh each call."""
    if st is None or requests is None:
        return None
    try:
        token = st.secrets.get("GITHUB_TOKEN")
        repo = st.secrets.get("GITHUB_REPO")
        branch = st.secrets.get("GITHUB_BRANCH")
    except Exception:
        return None
    if not token or not repo:
        return None
    return str(token).strip(), str(repo).strip().strip("/"), (str(branch).strip() if branch else "main")


def _explain(status, message):
    if status == 401:
        return "GitHub rejected the token (wrong, expired or revoked) -- create a new GITHUB_TOKEN"
    if status == 403:
        return f"GitHub refused access ({message or 'permission or rate limit'}) -- the token needs 'Contents: Read and write' on this repo"
    if status == 404:
        return "repo or branch not found -- check GITHUB_REPO is spelled 'owner/repo' and that the token was granted access to it"
    return message or "unexpected response"


def _request(method, path, cfg, params=None, json_body=None, raw=False, ok=(200,), missing_ok=False):
    token = cfg[0]
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        r = requests.request(method, f"{_GITHUB_API}{path}", headers=headers, params=params, json=json_body, timeout=20)
    except Exception as e:
        raise GitHubError(0, f"could not reach GitHub ({type(e).__name__})")
    if r.status_code in ok:
        return r
    if missing_ok and r.status_code == 404:
        return None
    try:
        message = r.json().get("message", "")
    except Exception:
        message = (r.text or "")[:120]
    raise GitHubError(r.status_code, _explain(r.status_code, message))


def _get_file(path, cfg, want_bytes=True):
    """(bytes, sha) of a repo file, or (None, None) if it doesn't exist yet. Works for files of any size."""
    _, repo, branch = cfg
    r = _request("GET", f"/repos/{repo}/contents/{path}", cfg, params={"ref": branch}, missing_ok=True)
    if r is None:
        return None, None
    data = r.json()
    if isinstance(data, list):
        raise GitHubError(0, f"{path} is a folder, not a file")
    sha = data.get("sha")
    if not want_bytes:
        return None, sha
    if data.get("encoding") == "base64" and data.get("content"):
        return base64.b64decode(data["content"]), sha
    # Files over 1 MB (animated GIFs) come back with EMPTY content here; ask for the raw bytes instead.
    return _request("GET", f"/repos/{repo}/contents/{path}", cfg, params={"ref": branch}, raw=True).content, sha


def _put_file(path, content, message, cfg):
    """Commit one file. Retries when someone else changed it between our read and our write."""
    _, repo, branch = cfg
    if len(content) > _MAX_PUSH_BYTES:
        raise GitHubError(0, f"{os.path.basename(path)} is larger than {_MAX_PUSH_BYTES // 1048576} MB")
    for attempt in range(3):
        _, sha = _get_file(path, cfg, want_bytes=False)
        body = {"message": message, "content": base64.b64encode(content).decode(), "branch": branch}
        if sha:
            body["sha"] = sha
        try:
            _request("PUT", f"/repos/{repo}/contents/{path}", cfg, json_body=body, ok=(200, 201))
            return
        except GitHubError as e:
            if e.status in (409, 422) and attempt < 2:
                continue
            raise


def _ensure_branch(cfg):
    """Create the data branch from the default branch the first time it's needed."""
    _, repo, branch = cfg
    if (repo, branch) in _branch_ready:
        return
    if _request("GET", f"/repos/{repo}/branches/{branch}", cfg, missing_ok=True) is None:
        default = _request("GET", f"/repos/{repo}", cfg).json().get("default_branch", "main")
        head = _request("GET", f"/repos/{repo}/git/ref/heads/{default}", cfg).json()["object"]["sha"]
        _request("POST", f"/repos/{repo}/git/refs", cfg, json_body={"ref": f"refs/heads/{branch}", "sha": head}, ok=(201,))
    _branch_ready.add((repo, branch))


# --------------------------------------------------------------------------- local files
def _read_local_items():
    try:
        with open(_METADATA_PATH, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _atomic_write(path, data: bytes):
    _ensure_dirs()
    tmp = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def _write_local_items(items):
    _atomic_write(_METADATA_PATH, json.dumps(items, indent=2).encode())


def _parse_items(content):
    try:
        data = json.loads(content)
        return data if isinstance(data, list) else []
    except (ValueError, UnicodeDecodeError):
        return []


def _merge_items(local, remote):
    """Union by id (this copy wins a tie), oldest first. Nothing is ever dropped, so a save can't erase someone else's."""
    by_id = {}
    for item in list(remote) + list(local):
        if isinstance(item, dict) and item.get("id"):
            by_id[item["id"]] = item
    return sorted(by_id.values(), key=lambda x: x.get("shared_at", 0))


def _safe_name(name):
    return name if name and os.path.basename(name) == name and not name.startswith(".") else None


# --------------------------------------------------------------------------- status
def _note_success():
    _status.update(ok=True, error=None, at=time.time())


def _note_failure(message):
    _status.update(ok=False, error=message, at=time.time())


def last_push_error():
    """Why the most recent save could not be backed up to GitHub, or None if it was (or nothing has been saved yet)."""
    return _status["error"] if _status["ok"] is False else None


def github_check(force=False):
    """(ok, message): can we reach the repo with this token? Read-only, cached for a few minutes. ok is None if not configured."""
    cfg = _github_config()
    if not cfg:
        return None, "not configured"
    with _lock:
        if not force and _check_state["ok"] is not None and time.time() - _check_state["at"] < _CHECK_TTL_SECONDS:
            return _check_state["ok"], _check_state["msg"]
        try:
            _request("GET", f"/repos/{cfg[1]}", cfg)
            if cfg[2] != "main":
                _request("GET", f"/repos/{cfg[1]}/branches/{cfg[2]}", cfg, missing_ok=True)   # a missing data branch is created on first save
            ok, msg = True, ""
        except GitHubError as e:
            ok, msg = False, str(e)
        _check_state.update(at=time.time(), ok=ok, msg=msg)
    return ok, msg


def github_persistence_status() -> str:
    """One honest sentence about whether shares will survive a sleep or reboot right now."""
    cfg = _github_config()
    if not cfg:
        return ("Not permanent yet: shares are kept on this server only and disappear when the app sleeps, reboots or redeploys. "
                "The site owner can fix this by adding GITHUB_TOKEN and GITHUB_REPO under the app's Secrets (see community_storage.py).")
    if _status["ok"] is False:
        return (f"GitHub backup is set up, but the last save failed ({_status['error']}). Shares are kept for now but will be lost "
                "the next time the app sleeps or reboots until this is fixed.")
    ok, msg = github_check()
    if not ok:
        return f"GitHub backup is set up but not working ({msg}). Shares will be lost the next time the app sleeps or reboots until this is fixed."
    if _status["ok"]:
        return "Permanent: shares are backed up to GitHub and survive the app sleeping, rebooting and redeploying."
    return "GitHub backup is connected. The next share will confirm it can save; after that, shares survive the app sleeping and rebooting."


# --------------------------------------------------------------------------- GitHub sync
def _fetch_image(name, cfg):
    """Download one image into the local folder if it isn't there. Returns True if it now exists."""
    name = _safe_name(name)
    if not name:
        return False
    path = os.path.join(_IMAGES_DIR, name)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True
    if _missing_until.get(name, 0) > time.time():
        return False
    try:
        content, _ = _get_file(f"{_REMOTE_PREFIX}/images/{name}", cfg)
    except GitHubError:
        content = None
    if not content:
        _missing_until[name] = time.time() + _MISSING_IMAGE_RETRY_SECONDS
        return False
    _atomic_write(path, content)
    return True


def _sync_from_github(force=False):
    """
    Pull anything shared elsewhere (or before this container started) into the local copy. Rate-limited so ordinary page
    views don't each cost a GitHub call. Images are fetched in parallel here and, if any are missed, on demand later.
    """
    cfg = _github_config()
    if not cfg:
        return
    with _lock:
        if not force and time.time() - _sync_state["at"] < _SYNC_TTL_SECONDS:
            return
        try:
            content, _ = _get_file(_REMOTE_META, cfg)
        except GitHubError as e:
            _sync_state["at"] = time.time() - _SYNC_TTL_SECONDS + 15   # back off briefly instead of retrying on every rerun
            if _status["ok"] is not False:
                _note_failure(f"could not read shared items from GitHub: {e}")
            return
        _sync_state["at"] = time.time()
        if content is None:
            return
        local = _read_local_items()
        merged = _merge_items(local, _parse_items(content))
        if len(merged) != len(local):
            _ensure_dirs()
            _write_local_items(merged)
        missing = [i["image_filename"] for i in merged
                   if _safe_name(i.get("image_filename")) and not os.path.exists(os.path.join(_IMAGES_DIR, i["image_filename"]))]
    if missing:
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda n: _fetch_image(n, cfg), missing[-60:]))


def _push_entry(entry_id, image_filename, image_path):
    """Back up one new share: its image first, then the merged metadata (so metadata never points at a missing image)."""
    cfg = _github_config()
    if not cfg:
        return
    try:
        with _lock:
            _ensure_branch(cfg)
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            _put_file(f"{_REMOTE_PREFIX}/images/{image_filename}", image_bytes, f"Add community share {entry_id}", cfg)
            remote, _ = _get_file(_REMOTE_META, cfg)
            merged = _merge_items(_read_local_items(), _parse_items(remote) if remote else [])
            _write_local_items(merged)
            _put_file(_REMOTE_META, json.dumps(merged, indent=2).encode(), f"Update community metadata for {entry_id}", cfg)
            _sync_state["at"] = time.time()
        _note_success()
    except GitHubError as e:
        _note_failure(str(e))
    except OSError as e:
        _note_failure(f"local file problem: {e}")


# --------------------------------------------------------------------------- public API
def load_all() -> list:
    """Every shared visualization's metadata, most recent first."""
    _ensure_dirs()
    _sync_from_github()
    return sorted(_read_local_items(), key=lambda x: x.get("shared_at", 0), reverse=True)


def _append_entry(entry):
    _sync_from_github(force=True)          # pick up anything shared elsewhere first, so we add to the full list
    items = _read_local_items()
    items.append(entry)
    _write_local_items(items)


def save_visualization(fig, name: str, description: str, source_section: str) -> str:
    """
    Saves a matplotlib figure -- OR, if fig is a GIF buffer (an animated visualization; detected by duck-typing on
    savefig()), that instead. Both go through the same images folder, metadata file and GitHub backup.
    """
    _ensure_dirs()
    entry_id = str(uuid.uuid4())
    is_gif = not hasattr(fig, "savefig")
    image_filename = f"{entry_id}.gif" if is_gif else f"{entry_id}.png"
    image_path = os.path.join(_IMAGES_DIR, image_filename)
    if is_gif:
        fig.seek(0)
        _atomic_write(image_path, fig.read())
    else:
        fig.savefig(image_path, dpi=120, bbox_inches="tight", transparent=True)
    _append_entry({"id": entry_id, "name": name, "description": description, "source_section": source_section,
                   "image_filename": image_filename, "shared_at": time.time()})
    _push_entry(entry_id, image_filename, image_path)
    return entry_id


def save_formula(name: str, description: str, components: list) -> str:
    """
    Saves a Stat Formula Creator formula -- a named, weighted combination of stats (and/or other shared formulas).
    Stored like any share, plus formula_data (a list of {label, weight}) so it can be rebuilt and told apart from a
    chart. Its "image" is a small generated bar-per-component preview.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [c["label"] for c in components]
    weights = [c["weight"] for c in components]
    fig, ax = plt.subplots(figsize=(7, max(2, 0.6 * len(components))))
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    colors = ["#D4AF37" if w >= 0 else "#8B3A3A" for w in weights]
    ax.barh(labels, weights, color=colors)
    ax.axvline(0, color="white", linewidth=0.8)
    ax.set_xlabel("Weight", color="white", fontsize=10)
    ax.tick_params(colors="white", labelsize=9)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()

    _ensure_dirs()
    entry_id = str(uuid.uuid4())
    image_filename = f"{entry_id}.png"
    image_path = os.path.join(_IMAGES_DIR, image_filename)
    fig.savefig(image_path, dpi=120, bbox_inches="tight", transparent=True)
    plt.close(fig)

    _append_entry({"id": entry_id, "name": name, "description": description, "source_section": "Stat Formula Creator",
                   "image_filename": image_filename, "shared_at": time.time(), "formula_data": components})
    _push_entry(entry_id, image_filename, image_path)
    return entry_id


def load_all_formulas() -> list:
    """Every shared formula (not a plain chart) -- entries that have formula_data set."""
    return [item for item in load_all() if item.get("formula_data")]


def get_image_path(image_filename: str) -> str:
    """Local path of a shared image, downloading it from GitHub first if this container doesn't have it yet."""
    name = _safe_name(image_filename) or "missing.png"
    path = os.path.join(_IMAGES_DIR, name)
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        cfg = _github_config()
        if cfg:
            _fetch_image(name, cfg)
    return path
