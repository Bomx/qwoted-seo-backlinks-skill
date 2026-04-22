"""
Qwoted Opportunity Search — query the same Algolia index that powers
app.qwoted.com/source_requests, save the hits as JSON.

How it works
------------
Qwoted's `/source_requests` page is a React app whose JS bundle embeds a
public, search-only Algolia API key. We reuse the saved cookies to load
that page, regex out the credentials, and then hit Algolia's REST API
directly. No browser/JS-renderer needed — just `requests`.

Why this is great for AI agents
-------------------------------
The output is clean structured JSON: opportunity name, full details
(reporter brief), publication, deadline, hashtags, share_url, and the
numeric `source_request_id` you need for `qwoted_pitch.py`. Drop the
file path into a `Read` tool call and you have everything you need to
draft pitches.

Usage
-----
    python3 qwoted_search.py --query "marketing automation"
    python3 qwoted_search.py --query "SEO" --max-hits 100
    python3 qwoted_search.py --query "" --max-hits 30   # all opps

Output
------
Writes to ~/.qwoted/opportunities/<safe_query>_<timestamp>.json by
default. Override with --out-dir.
Always prints a one-line `RESULT: {"status": "...", "out_path": "..."}`
to stdout so AI agents can chain commands.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from qwoted_common import (  # noqa: E402
    QWOTED_BASE,
    USER_AGENT,
    authed_get,
    log,
    looks_like_login_page,
    opportunities_dir,
    require_cookies,
    result_line,
)

HITS_PER_PAGE = 20  # Algolia hits per page; 20 is the React UI default


# ---------------------------------------------------------------------------
# Algolia credential discovery
# ---------------------------------------------------------------------------
_REACT_PROPS_RE = re.compile(
    r'data-react-class="source_requests/top_level_search"\s+data-react-props="([^"]+)"'
)


def _fetch_algolia_credentials(cookies: dict[str, str]) -> dict[str, str] | None:
    """Pull the React props out of /source_requests so we can talk to Algolia.

    Returns None if the session is dead (caller should re-login)."""
    r = authed_get("/source_requests", cookies)
    log(f"/source_requests → status {r.status_code}, len {len(r.text)}")
    if r.status_code != 200 or looks_like_login_page(r.text):
        return None

    m = _REACT_PROPS_RE.search(r.text)
    if not m:
        log("ERROR: could not find 'source_requests/top_level_search' react props")
        return None

    try:
        props = json.loads(html_lib.unescape(m.group(1)))
    except Exception as e:
        log(f"ERROR: could not JSON-decode react props: {e}")
        return None

    creds = {
        "app_id": props.get("algoliaAppId"),
        "search_key": props.get("algoliaSearchKey"),
        "index_name": props.get("indexName"),
    }
    if not all(creds.values()):
        log(f"ERROR: Algolia creds incomplete: {creds}")
        return None
    log(f"Algolia: app_id={creds['app_id']}, index={creds['index_name']}")
    return creds


# ---------------------------------------------------------------------------
# Algolia query
# ---------------------------------------------------------------------------
def _algolia_query(creds: dict[str, str], query: str, page: int = 0,
                   hits_per_page: int = HITS_PER_PAGE) -> dict:
    url = f"https://{creds['app_id']}-dsn.algolia.net/1/indexes/{creds['index_name']}/query"
    headers = {
        "X-Algolia-API-Key": creds["search_key"],
        "X-Algolia-Application-Id": creds["app_id"],
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        # The public Algolia key is referer-locked to qwoted.com.
        "Referer": f"{QWOTED_BASE}/",
        "Origin": QWOTED_BASE,
    }
    encoded = urllib.parse.urlencode({
        "query": query or "",
        "hitsPerPage": hits_per_page,
        "page": page,
    })
    body = {"params": encoded}
    r = requests.post(url, headers=headers, json=body, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Algolia returned {r.status_code}: {r.text[:300]}")
    return r.json()


# ---------------------------------------------------------------------------
# Hit normalisation — drop the noisy fields, keep what's useful for pitching
# ---------------------------------------------------------------------------
def _normalise_hit(hit: dict) -> dict:
    pub = hit.get("publication") or {}
    shared = hit.get("shared_article") or {}
    hashtags = [h.get("hashtag", "") for h in (hit.get("hashtags") or []) if h.get("hashtag")]
    share_url = hit.get("share_url") or ""
    src_path = hit.get("source_request_path") or ""
    full_url = (
        share_url if share_url.startswith("http")
        else (f"{QWOTED_BASE}{src_path}" if src_path else share_url)
    )
    # Algolia exposes the numeric SR id as objectID (string). Keep both.
    source_request_id = None
    obj_id = hit.get("objectID")
    if obj_id and obj_id.isdigit():
        source_request_id = int(obj_id)

    return {
        "source_request_id": source_request_id,
        "object_id": obj_id,
        "name": hit.get("name", ""),
        "details": hit.get("details", ""),
        "request_type": hit.get("request_type_text", ""),
        "request_sub_type": hit.get("request_sub_type_text_filtered", ""),
        "deadline": hit.get("source_request_submit_date", ""),
        "no_deadline": hit.get("no_deadline", False),
        "deadline_approaching": hit.get("deadline_approaching", False),
        "published_at": hit.get("published_at", ""),
        "want_pitches": hit.get("want_pitches", False),
        "free_to_pitch": hit.get("source_request_free_to_pitch", False),
        "paid": hit.get("paid", False),
        "is_new": hit.get("is_new", False),
        "easy_win": hit.get("easy_win", False),
        "pitch_count_category": hit.get("pitch_count_category", ""),
        "publication": {
            "name": pub.get("name", ""),
            "logo_url": pub.get("logo_url", ""),
            "publication_path": pub.get("publication_path", ""),
            "top_publication": pub.get("top_publication", False),
            "region": pub.get("region"),
        },
        "shared_article": {
            "title": shared.get("title"),
            "publication_name": shared.get("publication_name"),
            "content_excerpt": shared.get("content_excerpt"),
            "image_url": shared.get("image_url"),
        },
        "hashtags": hashtags,
        "url": full_url,
    }


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------
def _safe_filename(query: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", (query or "all").strip()).strip("_")
    return s.lower() or "all"


def search(query: str, max_hits: int, out_dir: Path | str | None = None) -> dict:
    cookies = require_cookies()
    creds = _fetch_algolia_credentials(cookies)
    if creds is None:
        raise PermissionError(
            "Qwoted session expired (could not load Algolia credentials). "
            "Run: python3 qwoted_login.py"
        )

    out_dir = Path(out_dir) if out_dir else opportunities_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    all_hits: list[dict] = []
    seen_ids: set[str] = set()
    nb_total: int | None = None
    pages_fetched = 0
    page = 0

    while len(all_hits) < max_hits:
        try:
            data = _algolia_query(creds, query, page=page, hits_per_page=HITS_PER_PAGE)
        except Exception as e:
            log(f"ERROR: Algolia query failed on page {page}: {e}")
            break

        hits = data.get("hits") or []
        nb_total = data.get("nbHits", nb_total)
        nb_pages = data.get("nbPages", 0)
        pages_fetched += 1
        log(
            f"page {page} → {len(hits)} hits "
            f"(running total {len(all_hits)}/{max_hits}, "
            f"index nbHits={nb_total}, nbPages={nb_pages})"
        )
        if not hits:
            break

        new_count = 0
        for h in hits:
            obj_id = h.get("objectID")
            if not obj_id or obj_id in seen_ids:
                continue
            seen_ids.add(obj_id)
            normalised = _normalise_hit(h)
            normalised["scraped_from_page"] = page
            all_hits.append(normalised)
            new_count += 1
            if len(all_hits) >= max_hits:
                break

        if new_count == 0:
            break
        if nb_pages and page + 1 >= nb_pages:
            break
        page += 1
        time.sleep(0.4)  # polite

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{_safe_filename(query)}_{ts}.json"
    payload = {
        "query": query,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "algolia",
        "algolia_index": creds["index_name"],
        "algolia_app_id": creds["app_id"],
        "nb_hits_total_in_index": nb_total,
        "pages_fetched": pages_fetched,
        "count": len(all_hits),
        "opportunities": all_hits,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    log(f"wrote {len(all_hits)} opportunities to {out_path}")

    return {
        "status": "ok",
        "out_path": str(out_path),
        "count": len(all_hits),
        "nb_hits_total_in_index": nb_total,
        "query": query,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Search Qwoted opportunities (PR/journalist source requests) "
                    "via the same Algolia index the website uses."
    )
    p.add_argument("--query", default="",
                   help="Search term. Empty string returns the full index ordered as on the site.")
    p.add_argument("--max-hits", type=int, default=30,
                   help="Maximum opportunities to return (default: 30).")
    p.add_argument("--out-dir", default=None,
                   help="Directory to write the JSON file to "
                        "(default: ~/.qwoted/opportunities/).")
    args = p.parse_args(argv)

    log("starting Qwoted search", query=args.query, max_hits=args.max_hits)
    try:
        result = search(args.query, args.max_hits, out_dir=args.out_dir)
    except PermissionError as e:
        log(f"AUTH FAILED: {e}")
        result_line({"status": "error", "error": str(e)})
        return 1
    except Exception as e:
        log(f"ERROR: {e}")
        result_line({"status": "error", "error": str(e)})
        return 1

    result_line(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
