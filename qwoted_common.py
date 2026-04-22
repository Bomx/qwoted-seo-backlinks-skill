"""
Shared helpers for the Qwoted SEO Backlinks skill.

What lives here
---------------
* `qwoted_home()` — the per-user state directory (`~/.qwoted` by default,
  overridable via the `QWOTED_HOME` env var). All cookies, sent-pitch
  logs and scraped opportunities are stored under this folder so a
  user can wipe one directory to reset everything.
* Cookie helpers — `load_cookies()`, `save_cookies()`, the file path
  itself.
* Authenticated GET helpers — pull the CSRF token, the current user's
  numeric ID, and the user's URL slug out of any logged-in HTML page,
  with regexes that survive Qwoted's React vs analytics-only rendering.
* `result_line()` / `log()` — consistent stdout for AI agents to parse.

Open-source friendly
--------------------
Everything in this module is local-only. No telemetry, no third-party
calls, no hardcoded credentials. Bring your own Qwoted account.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
QWOTED_BASE = "https://app.qwoted.com"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)

# Files inside qwoted_home()
SESSION_FILENAME = "storage_state.json"
PITCHES_FILENAME = "sent_pitches.json"
PROFILE_FILENAME = "profile_state.json"


# ---------------------------------------------------------------------------
# State directory
# ---------------------------------------------------------------------------
def qwoted_home() -> Path:
    """Return the directory where this skill stores its state.

    Default: `~/.qwoted` (Mac/Linux/Windows all support `Path.home()`).
    Override by setting the `QWOTED_HOME` env var to any absolute path.
    """
    override = os.environ.get("QWOTED_HOME")
    if override:
        p = Path(override).expanduser().resolve()
    else:
        p = Path.home() / ".qwoted"
    p.mkdir(parents=True, exist_ok=True)
    return p


def session_file() -> Path:
    return qwoted_home() / SESSION_FILENAME


def pitches_file() -> Path:
    return qwoted_home() / PITCHES_FILENAME


def profile_file() -> Path:
    return qwoted_home() / PROFILE_FILENAME


def opportunities_dir() -> Path:
    p = qwoted_home() / "opportunities"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
def log(msg: str, **extra: Any) -> None:
    """Human-readable timestamped log line on stderr (so stdout stays clean
    for `RESULT:` lines that AI agents parse)."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if extra:
        msg = f"{msg} | {json.dumps(extra, default=str)}"
    print(f"[{ts}] {msg}", flush=True, file=sys.stderr)


def result_line(payload: dict[str, Any]) -> None:
    """Single-line `RESULT: {...}` JSON on stdout — the canonical channel
    for AI agents and shell scripts to parse the outcome of any command."""
    print(f"RESULT: {json.dumps(payload, default=str)}", flush=True)


# ---------------------------------------------------------------------------
# Cookie helpers (Playwright-style storage_state.json)
# ---------------------------------------------------------------------------
def load_cookies() -> dict[str, str] | None:
    """Return `{name: value}` from the saved storage_state, or None if
    the file is missing/empty/corrupt. Caller is responsible for
    triggering a re-login if this returns None."""
    fp = session_file()
    if not fp.exists():
        return None
    try:
        state = json.loads(fp.read_text())
        cookies = state.get("cookies") or []
        if not cookies:
            return None
        return {c["name"]: c["value"] for c in cookies if "name" in c and "value" in c}
    except Exception as e:
        log(f"WARNING: could not parse cookie jar at {fp}: {e}")
        return None


def require_cookies() -> dict[str, str]:
    """Like `load_cookies()` but raises with an actionable message."""
    cookies = load_cookies()
    if not cookies:
        raise FileNotFoundError(
            f"No Qwoted session found at {session_file()}.\n"
            f"Run: python3 qwoted_login.py\n"
            f"(then re-run this command)."
        )
    return cookies


# ---------------------------------------------------------------------------
# Page-level extractors
# ---------------------------------------------------------------------------
_CSRF_META_RE = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"')

# user_id can appear in any of these forms depending on which React
# components rendered. Try them in order.
_USER_ID_RES: list[re.Pattern[str]] = [
    re.compile(r'userId&quot;:(\d+)'),
    re.compile(r"['\"]userId['\"]\s*,\s*(\d+)"),
    re.compile(r'data-user-id=["\'](\d+)["\']'),
    re.compile(
        r'name="source\[represented_sources_attributes\]\[0\]\[user_id\]"[^>]*value="(\d+)"'
    ),
    # value may come BEFORE name in the HTML (Rails outputs both orders)
    re.compile(
        r'value="(\d+)"[^>]*name="source\[represented_sources_attributes\]\[0\]\[user_id\]"'
    ),
]

# user URL slug appears in /pr_users/<slug> links across logged-in pages
_USER_SLUG_RE = re.compile(r"/pr_users/([a-z0-9-]+)")


def extract_csrf(html: str) -> str | None:
    m = _CSRF_META_RE.search(html)
    return m.group(1) if m else None


def extract_user_id(html: str) -> int | None:
    for rx in _USER_ID_RES:
        m = rx.search(html)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def extract_user_slug(html: str) -> str | None:
    m = _USER_SLUG_RE.search(html)
    return m.group(1) if m else None


def looks_like_login_page(text: str) -> bool:
    """True if Qwoted served the login form instead of the page we asked for."""
    head = text[:6000].lower()
    if "users/sign_in" in head:
        return True
    return ("welcome back" in head and "password" in head)


# ---------------------------------------------------------------------------
# HTTP helpers (authenticated)
# ---------------------------------------------------------------------------
def common_headers(csrf: str | None = None, referer: str | None = None) -> dict[str, str]:
    h = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": QWOTED_BASE,
    }
    if csrf:
        h["X-CSRF-Token"] = csrf
        h["X-Requested-With"] = "XMLHttpRequest"
    if referer:
        h["Referer"] = referer
    return h


def authed_get(
    path_or_url: str,
    cookies: dict[str, str],
    accept: str | None = None,
    timeout: int = 30,
) -> requests.Response:
    """GET an authenticated Qwoted URL. Pass either `/source_requests`
    (relative) or a full https:// URL."""
    url = path_or_url if path_or_url.startswith("http") else f"{QWOTED_BASE}{path_or_url}"
    headers = common_headers()
    if accept:
        headers["Accept"] = accept
    return requests.get(url, cookies=cookies, headers=headers, timeout=timeout, allow_redirects=True)


def fetch_session_context() -> dict[str, Any]:
    """Hit a known logged-in landing page and pull the user's slug,
    numeric id and a fresh CSRF token in one round-trip. Used by
    profile/search/pitch as a cheap "am I still logged in?" probe.

    Raises PermissionError if the session is dead.
    """
    cookies = require_cookies()
    r = authed_get("/source_requests", cookies)
    if r.status_code != 200 or looks_like_login_page(r.text):
        raise PermissionError(
            "Qwoted session expired. Run: python3 qwoted_login.py"
        )
    csrf = extract_csrf(r.text)
    user_id = extract_user_id(r.text)
    user_slug = extract_user_slug(r.text)
    if not csrf:
        raise RuntimeError("Could not find CSRF token on /source_requests")
    return {
        "cookies": cookies,
        "csrf": csrf,
        "user_id": user_id,
        "user_slug": user_slug,
        "page_url": r.url,
    }
