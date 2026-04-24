"""
Qwoted Profile — get / create / update the user's "Source" persona.

Why this exists
---------------
Qwoted only delivers a pitch to a reporter when the pitch is attached
to at least one *pitchable entity* (a Source, Company or Product
representing the human being pitched). The pitch API will happily
accept a submission without one (HTTP 200, draft=false), but the
reporter is never notified. This script makes sure the user has a
Source persona configured BEFORE they try to pitch.

What it does
------------
* `--action get` (default): probes the user's account and prints the
  current Source(s)/Company(ies)/Product(s).
* `--action create`: fills the new-Source wizard at
  `/users/<slug>/represented_sources` end-to-end via a single
  multipart POST. Required: --full-name. Optional: --bio, --location,
  --gender, --email, --url, --linkedin, --twitter, --phone.
* `--action update`: PATCHes an existing Source via
  `/sources/<slug>` with the same fields. Pass --source-slug to pick
  one (defaults to the first Source on the account).

Field reference (mirrors the Qwoted edit form):

    source[full_name]           string, required
    source[bio]                 textarea, free text
    source[gender]              one of: f, m, nb, sd
    source[gender_self_desc]    free text (only when gender=sd)
    source[location_string]     "City, State, Country" (Qwoted geocodes)
    source[off_the_record]      "0" / "1"
    source[hide_from_search_engines]  "0" / "1"
    source[contact_infos_attributes][][value]      multi
    source[contact_infos_attributes][][info_type]  email|phone|url|twitter|facebook|linkedin|instagram
    source[contact_infos_attributes][][primary]    "true"/"false"
    source[contact_infos_attributes][][id]         (only when updating an existing one)

The CREATE form additionally requires:
    source[represented_sources_attributes][0][user_id] = <numeric user id>

We auto-discover the user's slug + numeric ID from any logged-in page,
so callers only need to supply the human-facing fields.

Output
------
Always prints `RESULT: { ... }` JSON on stdout for AI agents to parse.
The result includes the full `entity_id`/`entity_type` triple needed by
`qwoted_pitch.py`.
"""

from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from qwoted_common import (  # noqa: E402
    QWOTED_BASE,
    USER_AGENT,
    authed_get,
    common_headers,
    extract_csrf,
    extract_user_id,
    fetch_session_context,
    log,
    looks_like_login_page,
    profile_file,
    require_cookies,
    result_line,
)


# ---------------------------------------------------------------------------
# HTML edit-form supplement
# ---------------------------------------------------------------------------
#
# Qwoted's JSON:API at /api/internal/jsonapi/users/<id> does NOT expose the
# Source's `bio` attribute (nor its canonical `slug`, nor a LinkedIn-style
# contact URL). Those fields only live in the HTML edit form at
# /sources/<id_or_slug>/edit.
#
# Prior versions of this script would therefore always report bio as missing
# even for fully-populated profiles, which led at least one agent to PATCH
# over a good user-written bio with an auto-generated one. Don't do that.
# Always fetch the edit form to check what's really there.
# ---------------------------------------------------------------------------
_BIO_TEXTAREA_RE = re.compile(
    r'<textarea[^>]*name="source\[bio\]"[^>]*>(.*?)</textarea>',
    re.S,
)
_FORM_ACTION_RE = re.compile(
    r'<form\s+class="edit_source"[^>]+action="(/sources/[^"]+)"'
)
_LOCATION_RE = re.compile(
    r'<input[^>]*name="source\[location_string\]"[^>]*value="([^"]*)"'
)


def _fetch_source_edit_form_extras(
    cookies: dict[str, str], source_ref: str | int,
) -> dict[str, str]:
    """Fetch /sources/<ref>/edit and parse the fields that the JSON:API omits.

    Returns {"bio": "...", "slug": "...", "location": "..."} on success,
    or {} on any failure (caller treats missing keys as empty).

    Never raises — this is a best-effort supplement. If the agent can't
    load the form (rare), we still return the JSON:API data, we just lose
    the bio-presence check.
    """
    try:
        r = authed_get(f"/sources/{source_ref}/edit", cookies, timeout=15)
    except Exception as e:
        log(f"  could not fetch edit form for source {source_ref}: {e}")
        return {}
    if r.status_code != 200 or looks_like_login_page(r.text):
        log(f"  edit form for source {source_ref} returned HTTP {r.status_code}")
        return {}

    out: dict[str, str] = {}
    m = _BIO_TEXTAREA_RE.search(r.text)
    if m:
        out["bio"] = html_mod.unescape(m.group(1)).strip()
    m = _FORM_ACTION_RE.search(r.text)
    if m:
        out["slug"] = m.group(1).rsplit("/", 1)[-1]
    m = _LOCATION_RE.search(r.text)
    if m:
        out["location"] = html_mod.unescape(m.group(1)).strip()
    return out


# ---------------------------------------------------------------------------
# Source discovery via JSON:API
# ---------------------------------------------------------------------------
def _list_pitchable_entities(
    cookies: dict[str, str], csrf: str, referer: str, user_id: int
) -> dict[str, list[dict[str, str]]]:
    """Returns a dict like
        {
            "sources":   [{"id":"304105","name":"Borja Obeso","slug":"borja-obeso-...","entity_type":"Source"}, ...],
            "products":  [...],
            "companies": [...],
        }
    The 'entity_type' key matches what qwoted_pitch.py expects.
    """
    # Note: `companies` is NOT a valid relationship on the User JSON:API
    # endpoint (returns HTTP 400 "Invalid field"). Companies are reachable
    # via `represented_sources` instead, but in practice the user's
    # pitchable identity is always a Source or Product.
    url = (
        f"{QWOTED_BASE}/api/internal/jsonapi/users/{user_id}"
        "?include=sources,products,represented_sources,represented_products"
    )
    headers = {**common_headers(csrf, referer), "Accept": "application/vnd.api+json"}
    r = requests.get(url, headers=headers, cookies=cookies, timeout=20)
    if r.status_code != 200:
        log(f"  WARNING: pitchable-entity lookup HTTP {r.status_code}: {r.text[:200]}")
        return {"sources": [], "products": [], "companies": []}

    body = r.json()
    rels = (body.get("data") or {}).get("relationships") or {}
    included = body.get("included") or []

    def _details_for(rel_type: str, rel_data: list[dict]) -> list[dict[str, str]]:
        out = []
        for item in rel_data:
            iid = str(item.get("id"))
            inc = next(
                (x for x in included if x.get("type") == rel_type and str(x.get("id")) == iid),
                None,
            )
            attrs = (inc or {}).get("attributes") or {}
            # The JSON:API exposes a flat set of contact fields directly on
            # the entity (url, email, phone, twitter, facebook). Claude
            # uses these to confirm the persona has a website URL — no
            # URL means a Qwoted-quote in an article will earn no
            # backlink, which defeats the purpose of this whole skill.
            out.append({
                "id": iid,
                "name": attrs.get("full_name") or attrs.get("name") or attrs.get("title") or "",
                "slug": attrs.get("slug") or "",
                "bio": attrs.get("bio") or attrs.get("description") or "",
                "url": (attrs.get("url") or "").strip(),
                "email": (attrs.get("email") or "").strip(),
                "phone": (attrs.get("phone") or "").strip(),
                "twitter": (attrs.get("twitter") or "").strip(),
                "facebook": (attrs.get("facebook") or "").strip(),
                "company_name": (attrs.get("company_name") or "").strip(),
                "has_business_url": bool((attrs.get("url") or "").strip()),
            })
        return out

    sources_raw = (rels.get("sources") or {}).get("data") or []
    products_raw = (rels.get("products") or {}).get("data") or []

    sources = [
        {**d, "entity_type": "Source"} for d in _details_for("sources", sources_raw)
    ]

    # Supplement each Source with the HTML-form fields the JSON:API hides.
    # This is the ONLY way to know whether a bio is actually set.
    for src in sources:
        extras = _fetch_source_edit_form_extras(cookies, src["id"])
        if extras.get("bio"):
            src["bio"] = extras["bio"]
        if extras.get("slug") and not src.get("slug"):
            src["slug"] = extras["slug"]
        if extras.get("location"):
            src["location"] = extras["location"]
        src["has_bio"] = bool(src.get("bio"))
        src["bio_length"] = len(src.get("bio") or "")

    return {
        "sources": sources,
        "products": [
            {**d, "entity_type": "Product"} for d in _details_for("products", products_raw)
        ],
        "companies": [],  # not exposed on the User endpoint; kept for API symmetry
    }


# ---------------------------------------------------------------------------
# Field assembly — same shape for CREATE and UPDATE
# ---------------------------------------------------------------------------
ALLOWED_GENDERS = {"f", "m", "nb", "sd"}
INFO_TYPES = ("email", "phone", "url", "twitter", "facebook", "linkedin", "instagram")


def _contact_inputs(args: argparse.Namespace) -> list[tuple[str, str]]:
    """Build the multi-valued contact_infos_attributes form fields. Each
    contact gets three entries: value, info_type, primary."""
    out: list[tuple[str, str]] = []
    # Pair flag name → info_type. First entry of each list is primary.
    mapping = {
        "email": getattr(args, "email", None) or [],
        "phone": getattr(args, "phone", None) or [],
        "url": getattr(args, "url", None) or [],
        "twitter": getattr(args, "twitter", None) or [],
        "facebook": getattr(args, "facebook", None) or [],
        "linkedin": getattr(args, "linkedin", None) or [],
        "instagram": getattr(args, "instagram", None) or [],
    }
    for info_type, values in mapping.items():
        for i, v in enumerate(values):
            v = (v or "").strip()
            if not v:
                continue
            out.append(("source[contact_infos_attributes][][value]", v))
            out.append(("source[contact_infos_attributes][][info_type]", info_type))
            out.append(("source[contact_infos_attributes][][primary]", "true" if i == 0 else "false"))
    return out


def _core_inputs(args: argparse.Namespace) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if args.full_name:
        out.append(("source[full_name]", args.full_name))
    if args.bio is not None:
        out.append(("source[bio]", args.bio))
    if args.gender:
        if args.gender not in ALLOWED_GENDERS:
            raise ValueError(f"--gender must be one of {sorted(ALLOWED_GENDERS)}, got {args.gender!r}")
        out.append(("source[gender]", args.gender))
        if args.gender == "sd" and args.gender_self_desc:
            out.append(("source[gender_self_desc]", args.gender_self_desc))
    if args.location:
        out.append(("source[location_string]", args.location))
        # Qwoted will geocode server-side if we don't pre-fill these.
        out.append(("source[location_latitude]", ""))
        out.append(("source[location_longitude]", ""))
        out.append(("source[skip_geocoding]", "false"))
    if args.off_the_record is not None:
        out.append(("source[off_the_record]", "1" if args.off_the_record else "0"))
    if args.hide_from_search_engines is not None:
        out.append(("source[hide_from_search_engines]", "1" if args.hide_from_search_engines else "0"))
    return out


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------
def _create_source(
    cookies: dict[str, str], user_slug: str, user_id: int,
    args: argparse.Namespace,
) -> dict[str, Any]:
    new_url = f"{QWOTED_BASE}/users/{user_slug}/represented_sources/new"
    log(f"loading new-Source wizard: {new_url}")
    r = authed_get(new_url, cookies)
    if r.status_code != 200 or looks_like_login_page(r.text):
        raise PermissionError("Could not load new-Source wizard (session may have expired)")

    csrf = extract_csrf(r.text) or ""
    if not csrf:
        raise RuntimeError("CSRF token not found on new-Source wizard")
    # Qwoted's new-Source form prefills the user_id from the page; if we
    # didn't already have one, pull it now.
    if not user_id:
        user_id = extract_user_id(r.text) or 0
    if not user_id:
        raise RuntimeError(
            "Could not determine numeric Qwoted user_id. Re-run with --user-id <N>."
        )

    post_url = f"{QWOTED_BASE}/users/{user_slug}/represented_sources"
    fields: list[tuple[str, str]] = [
        ("authenticity_token", csrf),
        ("utf8", "✓"),
        ("source[represented_sources_attributes][0][user_id]", str(user_id)),
    ]
    fields += _core_inputs(args)
    fields += _contact_inputs(args)

    log(f"POST {post_url}", fields_count=len(fields))
    headers = common_headers(csrf, referer=new_url)
    # Standard Rails forms expect a multipart/form-data POST when there
    # are file fields in the wizard; we don't have a file but the wizard
    # is enctype="multipart/form-data" so we mirror it.
    resp = requests.post(
        post_url,
        cookies=cookies,
        headers=headers,
        data=fields,
        files={"_dummy": (None, "")},
        timeout=45,
        allow_redirects=False,
    )
    log(f"  → {resp.status_code} (loc: {resp.headers.get('location','-')[:120]})")

    # Rails redirects to /sources/<new-slug> on success.
    new_slug: str | None = None
    if resp.status_code in (301, 302, 303):
        loc = resp.headers.get("location", "")
        m = re.search(r"/sources/([a-z0-9-]+)", loc)
        if m:
            new_slug = m.group(1)
    elif resp.status_code == 200:
        # Form re-rendered with errors. Try to surface the .invalid-feedback messages.
        errors = re.findall(r'class="invalid-feedback"[^>]*>([^<]+)<', resp.text)
        raise RuntimeError(
            f"create_source: server re-rendered the form (validation errors): "
            f"{errors[:5] if errors else 'no specific errors found, snippet: ' + resp.text[:300]}"
        )
    else:
        raise RuntimeError(f"create_source HTTP {resp.status_code}: {resp.text[:400]}")

    if not new_slug:
        raise RuntimeError(
            f"create_source: redirected but couldn't parse new-Source slug from "
            f"Location: {resp.headers.get('location')}"
        )

    log(f"  created Source slug={new_slug}")
    # Re-list entities so we can return the new numeric id.
    ctx = fetch_session_context()
    ents = _list_pitchable_entities(ctx["cookies"], ctx["csrf"], ctx["page_url"], user_id)
    new_source = next((s for s in ents["sources"] if s["slug"] == new_slug), None)
    return {
        "action": "created",
        "source_slug": new_slug,
        "source": new_source,
        "all_entities": ents,
    }


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------
def _update_source(
    cookies: dict[str, str], source_ref: str, args: argparse.Namespace,
) -> dict[str, Any]:
    """`source_ref` can be the canonical slug (e.g. `borja-obeso-<uuid>`)
    OR the numeric id (e.g. `304105`). Rails `friendly_id` accepts either.
    We always parse the canonical slug from the loaded edit form so the
    POST goes to the right URL.

    Safety rail: if `--bio` is being set and the source already has a
    non-empty bio, we REFUSE to clobber it unless the caller explicitly
    passes `--force-overwrite`. This stops the common agent failure mode
    of "get reports bio missing (false positive) → agent auto-generates
    a new bio → user's hand-written original is destroyed". Previous
    versions of this skill had that bug. The refusal surfaces as a
    clear error in the RESULT line so the agent can show both the old
    and new text to the user and wait for explicit approval.
    """
    edit_url = f"{QWOTED_BASE}/sources/{source_ref}/edit"
    log(f"loading edit form: {edit_url}")
    r = authed_get(edit_url, cookies)
    if r.status_code != 200 or looks_like_login_page(r.text):
        raise PermissionError(f"Could not load edit form for {source_ref} (session expired?)")

    csrf = extract_csrf(r.text) or ""
    if not csrf:
        raise RuntimeError("CSRF token not found on edit form")

    # Overwrite safety check — BEFORE building the POST body.
    if args.bio is not None and not args.force_overwrite:
        existing_bio_match = _BIO_TEXTAREA_RE.search(r.text)
        existing_bio = (
            html_mod.unescape(existing_bio_match.group(1)).strip()
            if existing_bio_match else ""
        )
        if existing_bio and existing_bio != (args.bio or "").strip():
            raise RuntimeError(
                "REFUSING to overwrite existing bio without --force-overwrite. "
                f"Current bio ({len(existing_bio)} chars) starts with: "
                f'"{existing_bio[:160]}..."  '
                f"Proposed bio ({len(args.bio)} chars) starts with: "
                f'"{args.bio[:160]}..."  '
                "If the user truly wants to replace it, re-run with --force-overwrite."
            )

    # Parse the form's `action` so we hit the canonical /sources/<slug> URL.
    action_match = _FORM_ACTION_RE.search(r.text)
    canonical_path = action_match.group(1) if action_match else f"/sources/{source_ref}"
    post_url = f"{QWOTED_BASE}{canonical_path}"
    canonical_slug = canonical_path.rsplit("/", 1)[-1]
    fields: list[tuple[str, str]] = [
        ("authenticity_token", csrf),
        ("utf8", "✓"),
        ("_method", "patch"),
    ]
    fields += _core_inputs(args)
    fields += _contact_inputs(args)

    log(f"POST {post_url} (PATCH)", fields_count=len(fields))
    resp = requests.post(
        post_url,
        cookies=cookies,
        headers=common_headers(csrf, referer=edit_url),
        data=fields,
        files={"_dummy": (None, "")},
        timeout=45,
        allow_redirects=False,
    )
    log(f"  → {resp.status_code} (loc: {resp.headers.get('location','-')[:120]})")

    if resp.status_code in (301, 302, 303):
        return {"action": "updated", "source_slug": canonical_slug, "source_ref": source_ref}
    if resp.status_code == 200:
        errors = re.findall(r'class="invalid-feedback"[^>]*>([^<]+)<', resp.text)
        raise RuntimeError(
            f"update_source: form re-rendered with errors: "
            f"{errors[:5] if errors else 'no specific errors found, snippet: ' + resp.text[:300]}"
        )
    raise RuntimeError(f"update_source HTTP {resp.status_code}: {resp.text[:400]}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _add_field_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--full-name", default=None,
                   help="Full name (required for --action create).")
    p.add_argument("--bio", default=None,
                   help="Free-text bio paragraph (recommended: 2-4 sentences, "
                        "covering employer/role + areas of expertise).")
    p.add_argument("--gender", default=None,
                   help="One of: f, m, nb, sd. Optional.")
    p.add_argument("--gender-self-desc", default=None,
                   help="Free text used when --gender=sd.")
    p.add_argument("--location", default=None,
                   help="Free-form 'City, State, Country' (Qwoted geocodes).")
    p.add_argument("--email", action="append", default=None,
                   help="Email address. Repeat to add multiple (first = primary).")
    p.add_argument("--phone", action="append", default=None, help="Repeatable.")
    p.add_argument("--url", action="append", default=None,
                   help="Personal/company URL. Repeatable.")
    p.add_argument("--linkedin", action="append", default=None, help="Repeatable.")
    p.add_argument("--twitter", action="append", default=None, help="Repeatable.")
    p.add_argument("--facebook", action="append", default=None, help="Repeatable.")
    p.add_argument("--instagram", action="append", default=None, help="Repeatable.")
    p.add_argument("--off-the-record", action="store_true", default=None,
                   help="Source does NOT want to be quoted by name.")
    p.add_argument("--hide-from-search-engines", action="store_true", default=None,
                   help="Hide profile from public + search engines.")
    p.add_argument("--force-overwrite", action="store_true", default=False,
                   help="Allow --action update to clobber a non-empty bio. "
                        "Default is to REFUSE and surface the existing text so "
                        "the agent can show it to the user for explicit approval.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Manage the Qwoted Source persona used to pitch journalists.",
    )
    p.add_argument("--action", choices=("get", "create", "update"), default="get")
    p.add_argument("--source-slug", default=None,
                   help="Slug of the Source to update (only for --action update). "
                        "Defaults to the first Source on the account.")
    p.add_argument("--user-id", type=int, default=None,
                   help="Numeric Qwoted user_id (auto-discovered if omitted).")
    p.add_argument("--user-slug", default=None,
                   help="URL slug of the Qwoted user (auto-discovered if omitted).")
    _add_field_args(p)
    args = p.parse_args(argv)

    log(f"starting Qwoted profile action={args.action}")
    cookies = require_cookies()
    try:
        ctx = fetch_session_context()
    except PermissionError as e:
        result_line({"status": "error", "error": str(e)})
        return 1

    user_id = args.user_id or ctx["user_id"]
    user_slug = args.user_slug or ctx["user_slug"]
    if not user_slug:
        result_line({"status": "error",
                     "error": "could not auto-discover user_slug; pass --user-slug"})
        return 1
    if not user_id:
        result_line({"status": "error",
                     "error": "could not auto-discover user_id; pass --user-id"})
        return 1
    log(f"resolved user", user_id=user_id, user_slug=user_slug)

    try:
        entities = _list_pitchable_entities(cookies, ctx["csrf"], ctx["page_url"], user_id)
    except Exception as e:
        result_line({"status": "error", "error": f"list entities failed: {e}"})
        return 1

    # Persist the snapshot to ~/.qwoted/profile_state.json so the pitch
    # script can use it without another API roundtrip.
    profile_file().write_text(json.dumps({
        "user_id": user_id,
        "user_slug": user_slug,
        "entities": entities,
    }, indent=2))

    if args.action == "get":
        first_pitchable: dict | None = None
        if entities["sources"]:
            first_pitchable = entities["sources"][0]
        elif entities["companies"]:
            first_pitchable = entities["companies"][0]
        elif entities["products"]:
            first_pitchable = entities["products"][0]

        # Surface what's missing so the calling AI agent can decide whether
        # to ask the user to fill in gaps before pitching.
        missing_for_seo: list[str] = []
        if not first_pitchable:
            missing_for_seo.append("any_pitchable_entity")
        else:
            if not first_pitchable.get("has_business_url"):
                missing_for_seo.append("business_url")
            if not first_pitchable.get("bio"):
                # This check now relies on the HTML-form supplement, not the
                # JSON:API (which never exposes bio). If we still see empty,
                # the bio is genuinely empty.
                missing_for_seo.append("bio")
            if not first_pitchable.get("email"):
                missing_for_seo.append("email")

        # Human-readable preview so the agent doesn't have to re-probe the
        # form to reason about the current bio.
        bio_preview = ""
        bio_length = 0
        if first_pitchable and first_pitchable.get("bio"):
            bio = first_pitchable["bio"]
            bio_length = len(bio)
            bio_preview = (bio[:240] + "...") if len(bio) > 240 else bio

        result_line({
            "status": "ok",
            "action": "get",
            "user_id": user_id,
            "user_slug": user_slug,
            "sources": entities["sources"],
            "products": entities["products"],
            "companies": entities["companies"],
            "first_pitchable_entity": first_pitchable,
            "ready_to_pitch": bool(first_pitchable),
            "missing_for_seo": missing_for_seo,
            "seo_ready": bool(first_pitchable) and not missing_for_seo,
            "bio_preview": bio_preview,
            "bio_length": bio_length,
            "profile_state_path": str(profile_file()),
        })
        return 0

    if args.action == "create":
        if not args.full_name:
            result_line({"status": "error", "error": "--full-name is required for --action create"})
            return 2
        try:
            res = _create_source(cookies, user_slug, user_id, args)
        except Exception as e:
            log(f"FAILED: {e}")
            result_line({"status": "error", "error": str(e)})
            return 1
        result_line({"status": "ok", **res})
        return 0

    if args.action == "update":
        ref = args.source_slug
        if not ref:
            if not entities["sources"]:
                result_line({"status": "error",
                             "error": "no existing Source to update; run with --action create first"})
                return 2
            # JSON:API doesn't expose the URL slug, but Rails accepts the
            # numeric id in the same URL slot via friendly_id.
            ref = entities["sources"][0].get("slug") or entities["sources"][0]["id"]
            log(f"  defaulting --source-slug to {ref}")
        try:
            res = _update_source(cookies, ref, args)
        except Exception as e:
            log(f"FAILED: {e}")
            result_line({"status": "error", "error": str(e)})
            return 1
        # Refresh entities so caller sees the updated bio etc.
        try:
            ents2 = _list_pitchable_entities(cookies, ctx["csrf"], ctx["page_url"], user_id)
        except Exception:
            ents2 = entities
        result_line({"status": "ok", **res,
                     "sources": ents2["sources"],
                     "products": ents2["products"],
                     "companies": ents2["companies"]})
        return 0

    result_line({"status": "error", "error": f"unknown action {args.action!r}"})
    return 2


if __name__ == "__main__":
    sys.exit(main())
