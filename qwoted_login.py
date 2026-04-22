"""
Qwoted Login — open a browser, let the user sign in, save the cookies.

Usage
-----
First-time / refresh login (default — opens a Chromium window):

    python3 qwoted_login.py

Headless re-login (only works if Qwoted didn't trigger MFA / captcha):

    python3 qwoted_login.py --headless

Force a brand-new browser profile (wipes saved Chromium state, asks the
user to log in from scratch):

    python3 qwoted_login.py --reset

What it does
------------
1. Launches a Chromium browser (Playwright's bundled Chromium — no
   conflict with the user's regular Chrome profile).
2. Uses a persistent profile under `~/.qwoted/chromium-profile/` so
   Qwoted's "remember me" cookie survives between runs and the next
   login is one click.
3. Navigates to https://app.qwoted.com/users/sign_in and waits for the
   user to finish signing in (including MFA, "I am not a robot", etc.).
4. As soon as the URL changes to anything other than the sign-in page,
   the script considers the user logged in, exports the cookies to
   `~/.qwoted/storage_state.json`, and exits cleanly.

The cookie jar is the ONLY artifact other scripts (search, profile,
pitch) need. They never touch the browser.

Why Playwright?
---------------
Qwoted occasionally challenges fresh sessions with reCAPTCHA, and on
some accounts requires MFA. The simplest UX that survives both is "open
a real browser, the human does the human bits, we just snapshot the
session". Pure-HTTP login would break the moment Qwoted nudges security.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# Lazy-import Playwright so `--help` works even if it's not installed yet.
def _import_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        print(
            "ERROR: Playwright is not installed.\n"
            "Install it with:\n"
            "    pip install playwright\n"
            "    playwright install chromium",
            file=sys.stderr,
        )
        sys.exit(2)


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from qwoted_common import (  # noqa: E402
    QWOTED_BASE,
    USER_AGENT,
    log,
    qwoted_home,
    result_line,
    session_file,
)

LOGIN_URL = f"{QWOTED_BASE}/users/sign_in"
PROFILE_DIRNAME = "chromium-profile"
DEFAULT_LOGIN_TIMEOUT_S = 300  # 5 minutes for a human to log in (MFA etc.)


def _profile_dir() -> Path:
    p = qwoted_home() / PROFILE_DIRNAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _is_logged_in_url(url: str) -> bool:
    """We consider any path other than /users/sign_in (or /users/password
    for recovery flows) to mean the user is signed in."""
    try:
        path = urlparse(url).path or "/"
    except Exception:
        return False
    if path.startswith("/users/sign_in"):
        return False
    if path.startswith("/users/password"):
        return False
    return True


def run(headless: bool = False, reset: bool = False, timeout_s: int = DEFAULT_LOGIN_TIMEOUT_S) -> bool:
    """Open Chromium, wait for the user to log in, save cookies. Returns True on success."""
    sync_playwright = _import_playwright()
    profile_dir = _profile_dir()

    if reset and profile_dir.exists():
        log(f"--reset: wiping {profile_dir}")
        shutil.rmtree(profile_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)

    log(
        "starting Qwoted login",
        headless=headless,
        profile_dir=str(profile_dir),
        cookie_jar=str(session_file()),
        timeout_s=timeout_s,
    )

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=headless,
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            args=["--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        log(f"opening {LOGIN_URL}")
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:
            log(f"ERROR navigating to login URL: {e}")
            ctx.close()
            return False

        # If the persistent profile already has a valid cookie, we'll get
        # bounced off /users/sign_in immediately. Give it a moment to settle.
        time.sleep(2.0)
        current_url = page.url
        log(f"  current URL after load: {current_url}")

        if _is_logged_in_url(current_url):
            log("already logged in via saved profile — skipping interactive step")
        else:
            if headless:
                log(
                    "ERROR: --headless mode but not already logged in. "
                    "Re-run without --headless so you can sign in manually "
                    "(MFA, captcha, etc. require a real browser window)."
                )
                ctx.close()
                return False

            print("\n" + "=" * 70, file=sys.stderr)
            print(
                "  >>> A Chromium window just opened. Please sign in to Qwoted.\n"
                "      As soon as you're on a logged-in page, this script will\n"
                "      detect it automatically and save your session.\n"
                f"      (timeout: {timeout_s} seconds — re-run if you need more)",
                file=sys.stderr,
            )
            print("=" * 70 + "\n", file=sys.stderr)

            deadline = time.time() + timeout_s
            while time.time() < deadline:
                try:
                    if _is_logged_in_url(page.url):
                        break
                except Exception:
                    pass
                time.sleep(1.0)
            else:
                log(f"ERROR: did not detect login within {timeout_s}s. Aborting.")
                ctx.close()
                return False

            # Give Qwoted a couple more seconds to set any post-login cookies.
            log(f"  detected logged-in URL: {page.url}. Letting it settle...")
            time.sleep(3.0)

        # Save the cookie jar
        try:
            ctx.storage_state(path=str(session_file()))
            log(f"saved cookie jar to {session_file()}")
        except Exception as e:
            log(f"ERROR saving cookie jar: {e}")
            ctx.close()
            return False

        ctx.close()

    # Sanity check the saved file
    if not session_file().exists():
        log("ERROR: cookie jar file is missing after save")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Open a browser to log into Qwoted, then save cookies "
                    "to ~/.qwoted/storage_state.json for the other skill scripts.",
    )
    p.add_argument(
        "--headless", action="store_true",
        help="Run Chromium headlessly. Only works when an existing saved profile "
             "is already logged in (no MFA/captcha). Default is headed.",
    )
    p.add_argument(
        "--reset", action="store_true",
        help="Wipe the saved Chromium profile before starting (forces a fresh login).",
    )
    p.add_argument(
        "--timeout", type=int, default=DEFAULT_LOGIN_TIMEOUT_S,
        help=f"Seconds to wait for the user to finish logging in "
             f"(default: {DEFAULT_LOGIN_TIMEOUT_S}).",
    )
    args = p.parse_args(argv)

    ok = run(headless=args.headless, reset=args.reset, timeout_s=args.timeout)
    if ok:
        result_line({"status": "logged_in", "cookie_jar": str(session_file())})
        return 0
    result_line({"status": "error", "error": "login failed; see logs above"})
    return 1


if __name__ == "__main__":
    sys.exit(main())
