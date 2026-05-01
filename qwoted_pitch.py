"""
Qwoted Pitch — submit a pitch to a Qwoted source request.

Background
----------
Qwoted's pitch wizard is a React-only flow that POSTs to
`/api/internal/pitches`. There is no static HTML form to scrape, but the
underlying API is straightforward (and documented in this docstring so
the next maintainer doesn't have to read the JS bundle):

  1. POST   /api/internal/pitches               (multipart) → creates a
     draft (`pitch[draft]=true` + `pitch[source_request_id]=N`) and
     returns `{id: <pitch_id>, ...}`.
  2. PATCH  /api/internal/pitches/<id>/autosave (JSON)      → saves the
     pitch text. Status stays `draft`.
  3. PUT    /api/internal/pitches/<id>          (multipart) → submits.
     Two non-obvious payload requirements (each one returns HTTP 500 if
     wrong):
       a) Do NOT send `pitch[draft]=false`. The React wizard omits it,
          and the server flips draft off automatically when entities
          are attached. Sending it explicitly returns 500.
       b) `pitched_entities` MUST use Rails array-append brackets:
              pitch[pitched_entities][][entity_id]=304105
              pitch[pitched_entities][][entity_type]=Source
          The indexed form `pitch[pitched_entities][0][entity_id]` also
          returns 500.
       c) File attachments are real multipart file parts. The field
          name is `pitch[attachments_attributes][][file_cloudinary][]`
          and the value is the file bytes (filename + mime). The
          server forwards the upload to Cloudinary on its side. A
          base64-data-URI shape (e.g. `[][base64File]=data:...`) is
          silently dropped — the request returns 200 but the JSON:API
          readback shows attachments=[].
  4. GET    /api/internal/jsonapi/pitches/<id>?include=pitched_entities,attachments,...
     readback to confirm an entity is attached. The JSON:API serializer
     does NOT expose `sent_at`/`pitched_at`; trust the synchronous
     submit response for those. `attachments` MUST be in the include
     list — without it the relationship `data` array comes back empty
     even when an attachment exists.

Pitchable entity requirement
----------------------------
Every pitch must reference at least one Source / Company / Product the
user is allowed to pitch as. Without one Qwoted accepts the pitch (HTTP
200, draft=false) but never notifies the reporter — the pitch is
functionally dead.

This script auto-discovers the user's pitchable entities at submit
time (or accepts an explicit --entity-id / --entity-type override) and
refuses to fire `--send` if none are found. Run `qwoted_profile.py
--action create ...` to set one up.

Usage
-----
    # Dry-run (default): create + autosave a draft, do NOT actually send.
    python3 qwoted_pitch.py \\
        --source-request-id 235897 \\
        --pitch-text "Hi! I'm Borja, founder of Distribb…"

    # Same as above, but resolve from a public short URL like /i/de1ccdba.
    python3 qwoted_pitch.py \\
        --opportunity-id de1ccdba \\
        --pitch-text-file /tmp/pitch.txt

    # Actually submit (notifies the reporter):
    python3 qwoted_pitch.py \\
        --source-request-id 235897 \\
        --pitch-text-file /tmp/pitch.txt \\
        --send

Sent-pitch tracking
-------------------
Every successful pitch is appended to `~/.qwoted/sent_pitches.json` with
the source-request ID, pitch text, pitch ID, timestamps, and a preview
of the API response. Used as a duplicate guard so the script (or an AI
agent driving it) won't pitch the same source-request twice.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from qwoted_common import (  # noqa: E402
    QWOTED_BASE,
    USER_AGENT,
    common_headers,
    extract_csrf,
    extract_user_id,
    log,
    looks_like_login_page,
    pitches_file,
    require_cookies,
    result_line,
)


# ---------------------------------------------------------------------------
# Sent-pitches log
# ---------------------------------------------------------------------------
def _read_sent_pitches() -> list[dict[str, Any]]:
    fp = pitches_file()
    if not fp.exists():
        return []
    try:
        data = json.loads(fp.read_text())
        if isinstance(data, list):
            return data
    except Exception as e:
        log(f"WARNING: could not parse {fp}: {e}")
    return []


def _append_sent_pitch(entry: dict[str, Any]) -> None:
    fp = pitches_file()
    entries = _read_sent_pitches()
    entries.append(entry)
    fp.write_text(json.dumps(entries, indent=2, default=str))
    log(f"appended pitch entry to {fp} (total={len(entries)})")


def _existing_pitch_for(source_request_id: int) -> dict[str, Any] | None:
    for e in _read_sent_pitches():
        if int(e.get("source_request_id") or 0) == int(source_request_id) and e.get("sent_at"):
            return e
    return None


# ---------------------------------------------------------------------------
# Opportunity / CSRF resolution
# ---------------------------------------------------------------------------
_SRI_NUMERIC_RE = re.compile(r'sourceRequestId&quot;:(\d+)')


def _fetch_opportunity_page(
    cookies: dict[str, str],
    source_request_id: int | None,
    opportunity_id: str | None,
) -> tuple[int, str, str, int | None]:
    """Returns (numeric_source_request_id, csrf_token, page_url, user_id)."""
    if source_request_id is None and opportunity_id is None:
        raise ValueError("Either source_request_id or opportunity_id must be provided")

    url = (
        f"{QWOTED_BASE}/source_requests/{source_request_id}"
        if source_request_id is not None
        else f"{QWOTED_BASE}/i/{opportunity_id}"
    )
    log(f"fetching opportunity page: {url}")
    r = requests.get(
        url,
        cookies=cookies,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
        timeout=30,
        allow_redirects=True,
    )
    log(f"  → {r.status_code}, final URL = {r.url}")

    if r.status_code in (401, 403) or "users/sign_in" in r.url:
        raise PermissionError("Qwoted session expired (redirected to sign-in)")
    if r.status_code != 200:
        raise RuntimeError(f"Opportunity page returned HTTP {r.status_code}")
    if looks_like_login_page(r.text):
        raise PermissionError("Opportunity page rendered the sign-in form")

    csrf = extract_csrf(r.text)
    if not csrf:
        raise RuntimeError("CSRF token not found on opportunity page")

    if source_request_id is not None:
        sri = source_request_id
    else:
        m = _SRI_NUMERIC_RE.search(r.text)
        if not m:
            raise RuntimeError(
                "Could not find numeric sourceRequestId on opportunity page; "
                "try passing --source-request-id directly."
            )
        sri = int(m.group(1))

    user_id = extract_user_id(r.text)
    log(f"resolved source_request_id={sri}, csrf={csrf[:20]}…", user_id=user_id)
    return sri, csrf, r.url, user_id


# ---------------------------------------------------------------------------
# Pitchable-entity discovery (lifted from qwoted_profile.py to keep this
# script self-contained for users who pip-clone only the pitch part)
# ---------------------------------------------------------------------------
def _fetch_pitchable_entities(
    cookies: dict[str, str], csrf: str, referer: str, user_id: int,
) -> list[dict[str, str]]:
    # `companies` is NOT a valid relationship on the User JSON:API endpoint
    # (returns HTTP 400 "Invalid field"). Don't include it here even though
    # the pitch endpoint accepts entity_type=Company.
    url = (
        f"{QWOTED_BASE}/api/internal/jsonapi/users/{user_id}"
        "?include=represented_sources,represented_products,sources,products"
    )
    headers = {**common_headers(csrf, referer), "Accept": "application/vnd.api+json"}
    r = requests.get(url, headers=headers, cookies=cookies, timeout=20)
    if r.status_code != 200:
        log(f"  WARNING: pitchable-entity lookup HTTP {r.status_code}: {r.text[:200]}")
        return []

    body = r.json()
    rels = (body.get("data") or {}).get("relationships") or {}
    entities: list[dict[str, str]] = []

    rel_to_entity_type: list[tuple[str, str]] = [
        ("sources", "Source"),
        ("products", "Product"),
    ]
    for rel_name, entity_type in rel_to_entity_type:
        for item in (rels.get(rel_name) or {}).get("data") or []:
            eid = item.get("id")
            if eid:
                entities.append({"entity_id": str(eid), "entity_type": entity_type})

    if not entities:
        # Fall back to represented_* (links via included.attributes.source_id)
        included = body.get("included") or []
        for rel_name, entity_type in [
            ("represented_sources", "Source"),
            ("represented_products", "Product"),
        ]:
            for item in (rels.get(rel_name) or {}).get("data") or []:
                rid = item.get("id")
                inc = next(
                    (x for x in included if x.get("type") == rel_name and str(x.get("id")) == str(rid)),
                    None,
                )
                attrs = (inc or {}).get("attributes") or {}
                src_id = attrs.get("source_id") or attrs.get("product_id")
                if src_id:
                    entities.append({"entity_id": str(src_id), "entity_type": entity_type})

    seen: set[tuple[str, str]] = set()
    unique = []
    for e in entities:
        key = (e["entity_id"], e["entity_type"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique


# ---------------------------------------------------------------------------
# Pitch API calls
# ---------------------------------------------------------------------------
def _api_headers(csrf: str, referer: str) -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "X-CSRF-Token": csrf,
        "Accept": "application/json, text/plain, */*",
        "Referer": referer,
        "Origin": QWOTED_BASE,
        "X-Requested-With": "XMLHttpRequest",
    }


def _find_existing_pitch(
    cookies: dict[str, str], csrf: str, referer: str, source_request_id: int,
) -> dict[str, Any] | None:
    url = (
        f"{QWOTED_BASE}/api/internal/jsonapi/pitches"
        f"?filter[source_request_id]={source_request_id}"
        "&include=pitched_entities,sources,products,companies"
    )
    headers = {**_api_headers(csrf, referer), "Accept": "application/vnd.api+json"}
    r = requests.get(url, headers=headers, cookies=cookies, timeout=20)
    if r.status_code != 200:
        log(f"  WARNING: pitch lookup HTTP {r.status_code}: {r.text[:200]}")
        return None
    try:
        data = r.json().get("data") or []
    except Exception as e:
        log(f"  WARNING: pitch lookup JSON error: {e}")
        return None
    return data[0] if data else None


def _create_or_resume_draft(
    cookies: dict[str, str], csrf: str, referer: str, source_request_id: int,
) -> tuple[dict[str, Any], bool]:
    url = f"{QWOTED_BASE}/api/internal/pitches"
    data = {"pitch[draft]": "true", "pitch[source_request_id]": str(source_request_id)}
    log(f"creating draft pitch (POST {url})", payload=data)
    r = requests.post(
        url,
        headers=_api_headers(csrf, referer),
        cookies=cookies,
        data=data,
        files={"_dummy": (None, "")},
        timeout=30,
    )
    log(f"  → {r.status_code} (ct={r.headers.get('content-type')})")

    if r.status_code == 200:
        body = r.json()
        if not body.get("id"):
            raise RuntimeError(f"create_draft returned no id: {body}")
        log(f"  created draft pitch_id={body['id']}")
        return body, False

    if r.status_code == 422 and "has already been taken" in r.text:
        log("  draft already exists for this SR — resuming")
        existing = _find_existing_pitch(cookies, csrf, referer, source_request_id)
        if not existing:
            raise RuntimeError(
                f"create_draft said 'already taken' but lookup returned no pitch: {r.text[:300]}"
            )
        attrs = existing.get("attributes") or {}
        rels = existing.get("relationships") or {}
        pitch_id = int(existing["id"])
        sent_at = attrs.get("sent_at") or attrs.get("sent-at")
        notified = attrs.get("reporter_notified_of_pitch_at") or attrs.get("reporter-notified-of-pitch-at")
        is_draft = str(attrs.get("draft")).lower() == "true"
        entities_attached = any(
            (rels.get(rn) or {}).get("data")
            for rn in ("pitched_entities", "sources", "products", "companies")
        )
        log(
            f"  resuming pitch_id={pitch_id}",
            draft=is_draft, sent_at=sent_at, entities_attached=entities_attached,
        )
        if sent_at or notified or (not is_draft and entities_attached):
            raise RuntimeError(
                f"source_request_id={source_request_id} already has a SENT pitch "
                f"(pitch_id={pitch_id}). Pick a different opportunity — "
                "Qwoted only allows one pitch per source-request."
            )
        if not is_draft:
            raise RuntimeError(
                f"pitch_id={pitch_id} for source_request_id={source_request_id} is "
                "stuck in a non-draft, non-delivered state (a previous submit failed "
                "without attaching an entity). Pick a different source-request."
            )
        return {"id": pitch_id, "draft": is_draft, **attrs}, True

    raise RuntimeError(f"create_draft failed: HTTP {r.status_code}: {r.text[:400]}")


def _autosave(
    cookies: dict[str, str], csrf: str, referer: str, pitch_id: int,
    source_request_id: int, text: str, subject: str | None,
    entities: list[dict[str, str]] | None,
) -> dict[str, Any]:
    url = f"{QWOTED_BASE}/api/internal/pitches/{pitch_id}/autosave"
    payload: dict[str, Any] = {
        "pitch": {"pitch": text, "draft": True, "source_request_id": source_request_id}
    }
    if subject:
        payload["pitch"]["subject"] = subject
    if entities:
        payload["pitch"]["pitched_entities"] = entities
    log(f"autosaving (PATCH {url})", text_len=len(text))
    r = requests.patch(
        url,
        headers={**_api_headers(csrf, referer), "Content-Type": "application/json"},
        cookies=cookies,
        json=payload,
        timeout=30,
    )
    log(f"  → {r.status_code}")
    if r.status_code != 200:
        raise RuntimeError(f"autosave failed: HTTP {r.status_code}: {r.text[:400]}")
    return r.json()


def _read_attachment(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"--attachment not found: {path}")
    if not path.is_file():
        raise ValueError(f"--attachment is not a file: {path}")
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "application/octet-stream"
    return {
        "name": path.name,
        "path": str(path),
        "mime": mime,
        "size_bytes": path.stat().st_size,
    }


def _read_attachments(paths: list[str] | None) -> list[dict[str, Any]]:
    attachments = [_read_attachment(Path(p).expanduser()) for p in (paths or [])]
    if attachments:
        log(
            "prepared pitch attachments",
            attachments=[
                {"name": a["name"], "mime": a["mime"], "size_bytes": a["size_bytes"]}
                for a in attachments
            ],
        )
    return attachments


def _submit(
    cookies: dict[str, str], csrf: str, referer: str, pitch_id: int,
    source_request_id: int, text: str, subject: str | None,
    entities: list[dict[str, str]] | None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """PUT /api/internal/pitches/:id — see module docstring for payload quirks."""
    url = f"{QWOTED_BASE}/api/internal/pitches/{pitch_id}"
    data: list[tuple[str, str]] = [
        ("pitch[pitch]", text),
        ("pitch[source_request_id]", str(source_request_id)),
        ("pitch[pitch_publicizable]", "true"),
    ]
    if subject:
        data.append(("pitch[subject]", subject))
    for ent in entities or []:
        data.append(("pitch[pitched_entities][][entity_id]", str(ent["entity_id"])))
        data.append(("pitch[pitched_entities][][entity_type]", str(ent["entity_type"])))

    # Attachments are sent as real multipart file parts under the field name
    # `pitch[attachments_attributes][][file_cloudinary][]`. Qwoted forwards
    # the upload to Cloudinary. The older base64-in-form-field shape is
    # silently dropped (200 OK but no attachment is created server-side).
    files: list[tuple[str, tuple[str | None, Any, str | None]]] = []
    for att in attachments or []:
        with open(att["path"], "rb") as f:
            file_bytes = f.read()
        files.append(
            (
                "pitch[attachments_attributes][][file_cloudinary][]",
                (att["name"], file_bytes, att["mime"]),
            )
        )
    if not files:
        files.append(("_dummy", (None, "", None)))

    log(
        f"submitting (PUT {url})",
        text_len=len(text),
        entities=entities or [],
        attachments=[
            {"name": a["name"], "mime": a.get("mime"), "size_bytes": a.get("size_bytes")}
            for a in (attachments or [])
        ],
    )
    r = requests.put(
        url,
        headers=_api_headers(csrf, referer),
        cookies=cookies,
        data=data,
        files=files,
        timeout=120,
    )
    log(f"  → {r.status_code}")
    if r.status_code not in (200, 201):
        raise RuntimeError(f"submit failed: HTTP {r.status_code}: {r.text[:600]}")
    try:
        body = r.json()
    except Exception:
        body = {"_raw": r.text[:1000]}
    inner = body.get("pitch") if isinstance(body.get("pitch"), dict) else body
    log(
        "  submit response",
        status=inner.get("status"),
        sent_at=inner.get("sent_at"),
        draft=inner.get("draft"),
    )
    return body


def _read_pitch(
    cookies: dict[str, str], csrf: str, referer: str, pitch_id: int,
) -> dict[str, Any]:
    url = (
        f"{QWOTED_BASE}/api/internal/jsonapi/pitches/{pitch_id}"
        "?include=pitched_entities,sources,products,companies,attachments"
    )
    headers = {**_api_headers(csrf, referer), "Accept": "application/vnd.api+json"}
    r = requests.get(url, headers=headers, cookies=cookies, timeout=20)
    if r.status_code != 200:
        return {"_error": f"HTTP {r.status_code}", "_body": r.text[:300]}
    try:
        return r.json()
    except Exception as e:
        return {"_error": f"json parse: {e}"}


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------
def send_pitch(
    *,
    source_request_id: int | None,
    opportunity_id: str | None,
    pitch_text: str,
    subject: str | None = None,
    send: bool = False,
    allow_duplicates: bool = False,
    entity_id: str | None = None,
    entity_type: str | None = None,
    research_page_url: str | None = None,
    attachments: list[str] | None = None,
) -> dict[str, Any]:
    if not pitch_text or not pitch_text.strip():
        raise ValueError("pitch_text is empty")

    prepared_attachments = _read_attachments(attachments)

    cookies = require_cookies()

    # 1. Resolve SR + CSRF + user_id from the opportunity page.
    try:
        sri, csrf, page_url, user_id = _fetch_opportunity_page(
            cookies, source_request_id, opportunity_id
        )
    except PermissionError:
        raise PermissionError(
            "Qwoted session expired. Run: python3 qwoted_login.py"
        )

    # 2. Cheap duplicate guard runs FIRST (before any further API calls).
    if not allow_duplicates:
        existing = _existing_pitch_for(sri)
        if existing:
            return {
                "status": "skipped_duplicate",
                "source_request_id": sri,
                "existing_pitch": existing,
            }

    # 3. Resolve which entities to pitch as.
    if entity_id and entity_type:
        entities = [{"entity_id": str(entity_id), "entity_type": str(entity_type)}]
        log("using CLI-provided pitchable entity", entities=entities)
    elif user_id:
        entities = _fetch_pitchable_entities(cookies, csrf, page_url, user_id)
        log(f"discovered pitchable entities for user_id={user_id}", entities=entities)
    else:
        entities = []
        log("WARNING: could not extract user_id from opportunity page")

    if send and not entities:
        raise RuntimeError(
            "Cannot --send: no pitchable Source/Company/Product is attached to this "
            "Qwoted account. Run:\n"
            "  python3 qwoted_profile.py --action create --full-name 'Your Name' "
            "--bio '...' --email you@example.com --linkedin https://linkedin.com/in/you/\n"
            "Or pass --entity-id <N> --entity-type Source/Company/Product."
        )

    # 4. Create or resume draft, then autosave the text.
    draft, resumed = _create_or_resume_draft(cookies, csrf, page_url, sri)
    pitch_id = int(draft["id"])
    autosave_resp = _autosave(
        cookies, csrf, page_url, pitch_id, sri, pitch_text, subject, entities
    )

    if not send:
        if prepared_attachments:
            log(
                "DRY-RUN — attachments were prepared but not uploaded. "
                "Pass --send to submit them."
            )
        log("DRY-RUN — pitch saved as draft only. Pass --send to submit.")
        return {
            "status": "draft_only",
            "source_request_id": sri,
            "pitch_id": pitch_id,
            "resumed_existing_draft": resumed,
            "page_url": page_url,
            "draft_response": draft,
            "autosave_response": autosave_resp,
            "sent_at": None,
            "attachment_count": len(prepared_attachments),
        }

    # 5. Submit.
    submit_resp = _submit(
        cookies, csrf, page_url, pitch_id, sri, pitch_text, subject, entities,
        attachments=prepared_attachments,
    )

    # 6. Verify via JSON:API readback.
    inner = (
        submit_resp.get("pitch") if isinstance(submit_resp.get("pitch"), dict)
        else submit_resp
    )
    submit_sent_at = inner.get("sent_at") or inner.get("pitched_at")
    submit_is_draft = str(inner.get("draft")).lower() == "true"

    readback = _read_pitch(cookies, csrf, page_url, pitch_id)
    rels = (readback.get("data") or {}).get("relationships") or {}
    attrs = (readback.get("data") or {}).get("attributes") or {}
    entities_attached = any(
        (rels.get(rn) or {}).get("data")
        for rn in ("pitched_entities", "sources", "products", "companies")
    )
    attachments_data = (rels.get("attachments") or {}).get("data") or []
    readback_is_draft = str(attrs.get("draft")).lower() == "true"

    log(
        "  submit verification",
        submit_sent_at=submit_sent_at,
        submit_draft=submit_is_draft,
        readback_draft=readback_is_draft,
        entities_attached=entities_attached,
        attachment_count=len(attachments_data),
    )

    if submit_is_draft and readback_is_draft:
        raise RuntimeError(
            f"submit returned 200 but pitch is still a draft: submit={inner}, readback_attrs={attrs}"
        )
    if not submit_sent_at and not entities_attached:
        raise RuntimeError(
            "Pitch was accepted (draft=false) but the reporter was NOT notified — "
            "no entities are attached and no sent_at timestamp was returned. "
            "The Qwoted account is missing a Source/Company/Product. "
            "Run: python3 qwoted_profile.py --action create ..."
        )
    if prepared_attachments and len(attachments_data) < len(prepared_attachments):
        raise RuntimeError(
            "Pitch was sent, but attachment verification failed: "
            f"expected {len(prepared_attachments)} attachment(s), "
            f"read back {len(attachments_data)}. "
            "Check the pitch in Qwoted before relying on the PDF citation."
        )

    sent_at = submit_sent_at or datetime.now(timezone.utc).isoformat()
    log_entry = {
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "source_request_id": sri,
        "opportunity_id": opportunity_id,
        "page_url": page_url,
        "pitch_id": pitch_id,
        "subject": subject,
        "pitch_text": pitch_text,
        "sent_at": sent_at,
        "entities_attached": entities,
        # Public URL of any research / statistics page the user
        # published and linked to from inside the pitch body. Captured
        # for traceability ("which research page drove the most
        # pitches?") and to make it easier to audit which Stage-3
        # asset is being promoted in any given PR push.
        "research_page_url": research_page_url,
    }
    _append_sent_pitch(log_entry)

    return {
        "status": "sent",
        "source_request_id": sri,
        "pitch_id": pitch_id,
        "sent_at": sent_at,
        "page_url": page_url,
        "log_entry": log_entry,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _read_pitch_text(args: argparse.Namespace) -> str:
    if args.pitch_text_file:
        path = Path(args.pitch_text_file)
        if not path.exists():
            raise FileNotFoundError(f"--pitch-text-file not found: {path}")
        return path.read_text()
    if args.pitch_text:
        return args.pitch_text
    raise ValueError("Provide --pitch-text or --pitch-text-file")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Send a pitch to a Qwoted source request.")
    p.add_argument("--source-request-id", type=int, default=None,
                   help="Numeric Qwoted source request ID (e.g. 235897).")
    p.add_argument("--opportunity-id", default=None,
                   help="Short ID from a /i/<id> link (e.g. 'de1ccdba').")
    p.add_argument("--pitch-text", default=None,
                   help="Pitch body (inline). Overrides --pitch-text-file.")
    p.add_argument("--pitch-text-file", default=None,
                   help="Path to a file containing the pitch body.")
    p.add_argument("--subject", default=None, help="Optional subject line.")
    p.add_argument("--send", action="store_true",
                   help="Actually submit the pitch (notifies the reporter). "
                        "Without this, the pitch stays as a draft.")
    p.add_argument("--allow-duplicates", action="store_true",
                   help="Allow re-pitching an SR already in sent_pitches.json.")
    p.add_argument("--entity-id", default=None,
                   help="Override auto-discovery: numeric Qwoted entity id "
                        "(must be used with --entity-type).")
    p.add_argument("--entity-type", default=None,
                   choices=("Source", "Product", "Company"),
                   help="Entity type for --entity-id.")
    p.add_argument("--research-page-url", default=None,
                   help="Public URL of a Stage-3 statistics/research page "
                        "you've referenced from inside the pitch body. "
                        "Logged in ~/.qwoted/sent_pitches.json for "
                        "traceability across a PR push.")
    p.add_argument("--attachment", action="append", default=None, metavar="PATH",
                   help="Path to a file (e.g. a sourced PDF) to attach to the "
                        "pitch. May be repeated to attach multiple files. "
                        "Attachments are prepared during dry-run but only "
                        "uploaded when --send is passed.")
    args = p.parse_args(argv)

    if args.source_request_id is None and not args.opportunity_id:
        result_line({"status": "error",
                     "error": "provide --source-request-id or --opportunity-id"})
        return 2
    try:
        pitch_text = _read_pitch_text(args)
    except Exception as e:
        result_line({"status": "error", "error": str(e)})
        return 2

    log("starting pitch", source_request_id=args.source_request_id,
        opportunity_id=args.opportunity_id, pitch_chars=len(pitch_text), send=args.send)

    try:
        res = send_pitch(
            source_request_id=args.source_request_id,
            opportunity_id=args.opportunity_id,
            pitch_text=pitch_text,
            subject=args.subject,
            send=args.send,
            allow_duplicates=args.allow_duplicates,
            entity_id=args.entity_id,
            entity_type=args.entity_type,
            research_page_url=args.research_page_url,
            attachments=args.attachment,
        )
    except Exception as e:
        log(f"FAILED: {e}")
        result_line({"status": "error", "error": str(e)})
        return 1

    result_line({
        "status": res.get("status"),
        "source_request_id": res.get("source_request_id"),
        "pitch_id": res.get("pitch_id"),
        "sent_at": res.get("sent_at"),
        "page_url": res.get("page_url"),
        "research_page_url": (res.get("log_entry") or {}).get("research_page_url"),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
