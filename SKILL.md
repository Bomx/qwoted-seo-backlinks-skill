---
name: qwoted-seo-backlinks
description: |
  Automate Qwoted (HARO-style PR platform) end-to-end: log in, set up the
  user's "expert" Source persona (bio + employer + contacts), search the
  Algolia-backed opportunity index, draft pitches as the user, and submit
  them to journalists. Earn high-DR backlinks and press mentions on
  autopilot. Use this skill whenever the user asks for "PR opportunities",
  "Qwoted opportunities", "press mentions", "journalist requests",
  "HARO replies", "media pitches", "podcast guesting", "expert quotes",
  or "backlinks from journalists".
---

# Qwoted SEO Backlinks Skill — playbook for Claude

Your job is to get the user **press mentions and high-DR backlinks** from
journalists who post requests on [Qwoted](https://app.qwoted.com).

The skill ships four CLI scripts you call as subprocesses. Each one
prints a single `RESULT: { ... }` JSON line on stdout that you parse to
decide the next step. Detailed human-readable logs go to stderr.

```
qwoted_login.py     # one-time auth (opens a browser the user signs into)
qwoted_profile.py   # get/create/update the user's "expert" Source persona
qwoted_search.py    # search opportunities (Algolia, returns JSON)
qwoted_pitch.py     # draft + send a pitch to a specific opportunity
```

All cookies, sent-pitch logs and search results live under `~/.qwoted/`.

---

## Decision tree — what to do based on what the user asks

| User intent | Skill command(s) |
|---|---|
| "Set me up on Qwoted" / first time | `qwoted_login.py` → `qwoted_profile.py --action get` → if empty, `qwoted_profile.py --action create ...` |
| "Update my Qwoted bio" / "change my expert profile" | `qwoted_profile.py --action update --bio '...'` |
| "Find PR opportunities about X" / "show me Qwoted requests" | `qwoted_search.py --query "X" --max-hits 30` |
| "Pitch opportunity #N" / "draft a pitch for SR 235897" | `qwoted_pitch.py --source-request-id N --pitch-text-file /tmp/pitch.txt` (dry-run) → user approves → re-run with `--send` |
| "Pitch the top 3 opportunities" | Loop: read JSON from search, draft custom pitch per opp, run dry-run, ask user, then `--send` |

---

## Stage 1 — Onboarding (run ONCE per user)

### 1a. Install

If the user doesn't have the skill installed, pip-install the deps and
run Playwright's browser bootstrap:

```bash
pip install -r requirements.txt
playwright install chromium
```

### 1b. Log in

```bash
python3 qwoted_login.py
```

A Chromium window opens. **Tell the user to sign in to Qwoted in that
window.** When they reach a logged-in page the script auto-detects it,
saves cookies to `~/.qwoted/storage_state.json`, closes the browser and
exits. The next login is one click because Chromium remembers them.

If the user doesn't have a Qwoted account yet, send them to
[qwoted.com](https://qwoted.com) to sign up first (free for sources).

### 1c. Set up the expert profile (Source persona) — REQUIRED

**Critical constraint**: Qwoted only delivers a pitch to a reporter
when the pitch is attached to a *pitchable entity* — a Source, Company
or Product the user is allowed to pitch as. The pitch API will accept
a submission without one (HTTP 200, draft=false) but the reporter is
**never notified**. Always make sure the user has a Source persona
configured before the first pitch.

Check first:

```bash
python3 qwoted_profile.py --action get
```

Parse the `RESULT:` JSON. If `ready_to_pitch == true`, skip to Stage 2.

If `ready_to_pitch == false`, gather the user's details (ask them
politely; don't make them up) and create the persona:

```bash
python3 qwoted_profile.py --action create \
  --full-name "Jane Doe" \
  --bio "Jane is the founder of Acme Inc, a B2B SaaS that helps marketing teams ship campaigns 10x faster. She advises on growth, GTM and pricing." \
  --location "San Francisco, CA, USA" \
  --gender f \
  --email jane@acme.com \
  --url https://acme.com \
  --linkedin https://www.linkedin.com/in/jane-doe/
```

Optional fields you can also pass: `--phone`, `--twitter`, `--facebook`,
`--instagram`, `--off-the-record`, `--hide-from-search-engines`. Repeat
flags to add multiple values (first one is marked as primary).

To update an existing persona later (e.g. the user got a new title):

```bash
python3 qwoted_profile.py --action update \
  --bio "Jane is now CEO of Acme Inc..."
```

`--source-slug` is optional — without it, the script edits the first
Source on the account.

---

## Stage 2 — Find opportunities

```bash
python3 qwoted_search.py --query "marketing automation" --max-hits 30
```

Empty `--query ""` returns the full index in the order Qwoted shows it
on the homepage (newest first).

Read the resulting JSON file (path is in the `RESULT:` line under
`out_path`). The structure is:

```json
{
  "query": "marketing automation",
  "scraped_at": "2026-04-22T...",
  "count": 30,
  "opportunities": [
    {
      "source_request_id": 235897,        // numeric ID for qwoted_pitch.py
      "name": "Looking for marketing experts to comment on Q3 trends",
      "details": "Reporter brief, 3-4 paragraphs of what they're after...",
      "request_type": "Online article",
      "deadline": "2026-04-28T17:00:00Z",
      "want_pitches": true,
      "publication": {"name": "TechCrunch", "top_publication": true, ...},
      "hashtags": ["#marketing", "#saas"],
      "url": "https://app.qwoted.com/source_requests/235897",
      ...
    },
    ...
  ]
}
```

### Picking the best opportunities

When the user asks for "the best", "top", or "easy wins", rank by:

1. `publication.top_publication == true` (high-DR sites)
2. `easy_win == true` (Qwoted's signal: low pitch count, high responsiveness)
3. `paid == true` (paid placements when applicable)
4. `pitch_count_category` (lower is better — "low" beats "very_high")
5. Match against the user's expertise (use the bio you already have)
6. Deadline proximity (`deadline_approaching`, `deadline`)

Only suggest opportunities where the user genuinely has expertise —
journalists ignore obviously irrelevant pitches and Qwoted scores PR
accounts on response rate.

---

## Stage 3 — Draft and send pitches

### How to write a great pitch (this is on YOU, the AI)

Each pitch should be:

* **2-4 short paragraphs**, max 250-400 words.
* **First sentence** says who the user is and why they're qualified for
  *this specific* request. (Don't recycle the bio — synthesize.)
* **Body** gives the reporter *concrete, quotable insights* directly
  answering the request. 2-4 bullet points work great. Numbers,
  specific examples and contrarian takes get used; vague platitudes
  get deleted.
* **Last sentence** offers a credit format (e.g. `Credit me as Jane
  Doe, founder of Acme Inc (acme.com)`) and an offer to expand or
  hop on a quick call.
* **No links in the pitch body** unless directly requested — Qwoted
  has a separate "publicizable" field that handles that.
* **No corporate marketing speak.** Talk like a smart founder
  emailing a friend at TechCrunch.

Save it to a tempfile so quoting is reliable:

```bash
cat > /tmp/qwoted_pitch.txt <<'EOF'
Hi! Borja Obeso here — founder of Distribb, a content distribution
and SEO platform that pushes one piece of content across 200+ DR40+
sites and channels. I see this national-vs-local split every day...
[2-4 paragraphs of substance]
Credit me as Borja Obeso, founder of Distribb (distribb.io).
— Borja
EOF
```

### Step 1 — DRY-RUN first (always)

```bash
python3 qwoted_pitch.py \
  --source-request-id 235897 \
  --pitch-text-file /tmp/qwoted_pitch.txt
```

This creates a draft on Qwoted and autosaves the text. **The reporter
is NOT notified.** Show the resulting draft to the user (or summarise
it) and ask for approval.

### Step 2 — Send it for real

```bash
python3 qwoted_pitch.py \
  --source-request-id 235897 \
  --pitch-text-file /tmp/qwoted_pitch.txt \
  --send
```

`status: "sent"` in the RESULT line means the reporter has been
notified. The pitch is also appended to `~/.qwoted/sent_pitches.json`.

### Duplicate guard

The script refuses to pitch a source-request that's already in
`sent_pitches.json` (returns `status: "skipped_duplicate"`). It also
detects pitches sent through the Qwoted UI (returns an error like
`source_request_id=N already has a SENT pitch`). To override locally,
pass `--allow-duplicates` (Qwoted itself only allows one pitch per
source-request, so the server-side block is hard).

---

## Common error patterns and how to handle them

| `RESULT.error` contains... | Meaning | Action |
|---|---|---|
| `No Qwoted session found` / `session expired` | Cookies missing or expired | Run `python3 qwoted_login.py` |
| `Cannot --send: no pitchable Source/Company/Product` | User skipped Stage 1c | Run `qwoted_profile.py --action create ...` |
| `already has a SENT pitch` | This SR has been pitched already | Pick a different opportunity |
| `is stuck in a non-draft, non-delivered state` | Previous submit attempt without entities | Pick a different opportunity (Qwoted won't let us re-edit) |
| `validation errors: ['Bio is too short']` | Form-level issue | Adjust the field and re-run |

---

## Things you should NEVER do

* **Never run `--send` without showing the pitch to the user first.** A
  pitch is a real message to a real journalist — they remember spammers.
* **Never invent biographical details** about the user. Ask if you don't
  know.
* **Never pitch opportunities outside the user's expertise.** Qwoted
  tracks reply rate and bad pitches hurt the account permanently.
* **Never modify `~/.qwoted/sent_pitches.json`** by hand — the
  duplicate guard relies on it. Treat it as append-only state.
* **Never commit `~/.qwoted/` to git.** It contains the user's session
  cookies (`storage_state.json`) — full account access.

---

## Quick reference — every command

```bash
# Setup
python3 qwoted_login.py                                  # one-time
python3 qwoted_login.py --reset                          # force re-login
python3 qwoted_login.py --headless                       # only if profile already valid

# Profile
python3 qwoted_profile.py --action get                   # what entities exist?
python3 qwoted_profile.py --action create --full-name '...' --bio '...' --email '...'
python3 qwoted_profile.py --action update --bio '...'    # edit first Source

# Search
python3 qwoted_search.py --query "marketing automation" --max-hits 30
python3 qwoted_search.py --query "" --max-hits 50        # all opportunities

# Pitch
python3 qwoted_pitch.py --source-request-id 235897 --pitch-text-file /tmp/p.txt
python3 qwoted_pitch.py --source-request-id 235897 --pitch-text-file /tmp/p.txt --send
python3 qwoted_pitch.py --opportunity-id de1ccdba --pitch-text-file /tmp/p.txt --send  # short URL form
```

State directory: `~/.qwoted/` (override with `QWOTED_HOME` env var).
