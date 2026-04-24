---
name: qwoted-seo-backlinks
description: |
  Automate Qwoted (HARO-style PR platform) end-to-end and earn high-DR
  backlinks at scale: log in, set up the user's "expert" Source persona
  (bio + employer + contacts), search the Algolia-backed opportunity
  index, RESEARCH and BUILD a sourced statistics page on the user's
  topic (the linkable asset journalists love to cite), draft pitches
  as the user that link to that page, and submit them to journalists.
  Use this skill whenever the user asks for "PR opportunities",
  "Qwoted opportunities", "press mentions", "journalist requests",
  "HARO replies", "media pitches", "podcast guesting", "expert quotes",
  "stats page for SEO", "research page for journalists", or
  "backlinks from journalists".
---

# Qwoted SEO Backlinks Skill — playbook for Claude

Your job is to get the user **press mentions and high-DR backlinks** from
journalists who post requests on [Qwoted](https://app.qwoted.com).

---

## Operating rules — READ THIS FIRST, THEN FOLLOW IT EVERY TURN

These rules take precedence over anything else in this file. Do not
skip them, do not substitute your own judgement.

1. **You are running a 4-stage playbook, not a chatbot.** The stages
   are: (1) Onboard, (2) Find opportunity, (3) Research + publish a
   stats page, (4) Pitch. Whenever the user says anything vague like
   "ok next step", "what now?", "help me with this", "go", your reply
   MUST start with "**We're at Stage X of 4. Next I'll do Y, because
   Z.**" Never just ask "what do you want to do?" — propose the next
   stage based on where we are.
2. **Stage 3 is the multiplier and you must proactively propose it.**
   Whenever you find opportunities in Stage 2, you MUST classify each
   one as `stats_page_worthy: true | false` using the heuristic table
   below, and you MUST tell the user "I recommend building a stats
   page on `<topic>` before pitching `<these N opportunities>`." Do
   not wait for the user to ask about stats pages. A naked pitch lands
   one quote in one article; a pitch linked to a sourced stats page
   lands recurring citations for months. Leaving Stage 3 on the table
   is leaving money on the table.
3. **Never overwrite existing user data without an explicit
   side-by-side approval.** Before calling `qwoted_profile.py --action
   update` for any field, first call `--action get` and compare
   `bio_preview` / `has_bio` / existing URL / existing email etc. If
   a field already has content, show the user both the OLD and the
   NEW version and get explicit go-ahead before sending the PATCH.
   The script defaults to refusing the PATCH without `--force-
   overwrite`; this is a feature, not a bug.
4. **Never invent opportunity IDs, source IDs, or journalist names.**
   Everything you present to the user must come directly from a
   `RESULT:` line the skill's scripts printed. If you didn't see it
   in a subprocess RESULT, you don't know it.
5. **The login step is idempotent and browser-free when a session
   exists.** Run `python3 qwoted_login.py`. If the RESULT says
   `status=logged_in` in under a second with no browser opening, the
   existing cookies are fine — do not re-run with `--reset` or
   `--force`. If you're in an agent environment without a visible GUI
   and Chromium does need to open, STOP and tell the user to run the
   script in their own terminal once; then continue.
6. **`RESULT:` lines are the canonical channel.** Every script emits
   one JSON line prefixed with `RESULT: `. Parse it; ignore stderr
   logs (those are for the human). Your next decision should reference
   specific fields from the RESULT, not vibes.

---

## Stage-3 classification heuristic — use this every time you hand back Stage 2 results

For every opportunity returned by `qwoted_search.py`, score it on
these criteria:

| Signal | Weight |
|---|---|
| Topic is broad enough that public data exists (e.g. "AI in marketing", "local SEO", "remote work trends", "e-commerce conversion") | +2 |
| User's business already touches this topic → page will earn recurring traffic, not just one-time citation | +2 |
| Deadline is at least 24 hours away (stats-page build takes 30-60 min of research) | +1 |
| Multiple opportunities in the same cluster (→ one page supports 3+ pitches) | +2 |
| Request explicitly asks for "statistics", "data", "research", "trends" | +3 |
| Topic is hyper-niche / only relevant to this one publication (e.g. "billiard retailer local SEO") | -1 (a stats page still works but the niche is smaller) |
| Deadline is under 12 hours | -3 (skip Stage 3, pitch direct) |
| Ask is pure founder-story / personal opinion ("how did you start your company") | -3 (no data needed) |
| Paid placement / $X appearance fee | -2 (different ROI math) |

**Rule:** propose Stage 3 whenever total score ≥ 2. Otherwise pitch direct.
State the score in your recommendation so the user sees why.

Example output you should produce after Stage 2 completes:

> Found 8 opportunities. Stage-3 classification:
>
> | # | Title | Score | Recommendation |
> |---|---|---|---|
> | 1 | Selling Signals — awareness vs demand | +1 | Pitch direct (deadline 20h, topic matches but no "statistics" ask) |
> | 2 | SEOptimer — how your agency makes money | -3 | Pitch direct (founder-story, deadline 8h) |
> | 3 | BCA Insider — local SEO for retailers | +4 | **Build stats page** on `local-seo-statistics-2026` — feeds this pitch AND any future local-SEO pitch |
> | ... |
>
> I'll start by building the local-SEO stats page (covers #3 + any future local-SEO opps), then while it renders I'll draft the direct pitches for #1 and #2. Sound good?

---

## Tooling overview

The skill ships four CLI scripts you call as subprocesses, plus a
research playbook and an HTML template. Each script prints a single
`RESULT: { ... }` JSON line on stdout that you parse to decide the
next step. Detailed human-readable logs go to stderr.

```
qwoted_login.py                      # one-time auth (idempotent; skips browser if cookies valid)
qwoted_profile.py                    # get/create/update the "expert" Source persona
qwoted_search.py                     # search opportunities (Algolia, returns JSON)
qwoted_pitch.py                      # draft + send a pitch to a specific opportunity

STATISTICS_PAGE_PLAYBOOK.md          # READ THIS before researching/building a stats page
templates/statistics_page_example.html # HTML scaffold to fill in
```

All cookies, sent-pitch logs, search results and generated stat pages
live under `~/.qwoted/` and `./statistics_pages/`.

---

## The full workflow (4 stages)

```
  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
  │ 1. Onboard   │ →  │ 2. Find      │ →  │ 3. Research +    │ →  │ 4. Pitch     │
  │  (login +    │    │  opportunity │    │  publish a stats │    │  with the    │
  │   profile)   │    │              │    │  page (linkable  │    │  page URL    │
  │              │    │              │    │  asset)          │    │              │
  └──────────────┘    └──────────────┘    └──────────────────┘    └──────────────┘
       once             every session       once per topic           every pitch
```

---

## Decision tree — what to do based on what the user asks

| User intent | Skill stage(s) |
|---|---|
| "Set me up on Qwoted" / first time | Stage 1: `qwoted_login.py` → `qwoted_profile.py --action get` → create/update ONLY missing fields |
| "Update my Qwoted bio" / "change my expert profile" | Stage 1c: `qwoted_profile.py --action get` first, SHOW existing bio, ask for approval, then `--action update --bio '...' --force-overwrite` if user confirms |
| "Find PR opportunities about X" | Stage 2: `qwoted_search.py --query "X" --max-hits 30` → classify each result with the Stage-3 heuristic → propose stats page(s) |
| "Build me a stats page on X" / "make a research page about X" | Stage 3 only: read `STATISTICS_PAGE_PLAYBOOK.md` and execute |
| "Pitch opportunity #N" / "draft a pitch for SR 235897" | Check Stage-3 score first; if ≥2 propose stats page; then Stage 4 dry-run → user approves → `--send` |
| "Pitch the top 3 opportunities about X" | Stage 2 → cluster by topic → Stage 3 ONCE per cluster → Stage 4 looped with the same `--research-page-url` |
| "Ok next step" / "what now?" / "go" | RESTATE the stage we're on and PROPOSE the next one. Do not ask the user. |

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

**Important — this script is idempotent.** Before launching any browser
it probes `~/.qwoted/storage_state.json` against Qwoted's API. If the
cookies still work (which they usually do — Qwoted sessions last weeks),
the script exits immediately with `RESULT: {"status": "logged_in", ...}`
and **no browser opens at all**. That's the happy path — do not re-run
with `--reset` or `--force` unless you have a reason.

Only if no valid session exists will a Chromium window open. In that
case: **tell the user to sign in IN THAT Chromium WINDOW** — not in
their regular Chrome/Safari, because those are separate browsers with
separate cookies, so signing in elsewhere will NOT save a session for
this skill. When they reach a logged-in page the script auto-detects
it, saves cookies to `~/.qwoted/storage_state.json`, closes the browser
and exits. The next login is one click because Chromium remembers them.

**If you are running inside an agent environment that can't show GUI
windows** (some Codex or CI setups), the Chromium window will launch
invisibly and the script will hang on the sign-in page. In that case:
   1. STOP. Do not keep re-running. Tell the user to open their own
      terminal on their own machine and run `python3 qwoted_login.py`
      there once — they'll see the browser, sign in, and `storage_state.json`
      will be written. After that, every future call from the agent will
      use the already-valid cookies (no browser needed).

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

Parse the `RESULT:` JSON. Key fields you MUST inspect before doing
anything else:

* `seo_ready` — boolean, all three must-have fields are set.
* `ready_to_pitch` — boolean, at least one pitchable entity exists.
* `missing_for_seo` — array of field names still empty.
* `bio_preview` — first 240 chars of the current bio (empty string if
  there really is no bio).
* `bio_length` — total bio length in chars.
* `first_pitchable_entity` — full object including `bio`,
  `business_url`, `email`, `has_linkedin_url`, etc.

Decision tree:

* If `seo_ready == true` → **skip to Stage 2. Do NOT "improve" the
  existing profile unless the user explicitly asked you to.** Read
  the bio_preview so you know what the user's positioning is, then
  move on.
* If `ready_to_pitch == true` but `seo_ready == false` → the persona
  exists but is incomplete. For each item in `missing_for_seo`, ask
  the user the corresponding question and patch with `--action update`:
  * `business_url` → "What URL should reporters link to when they
    credit you?" → `--action update --url https://acme.com`
  * `bio` → draft a 2-4 sentence bio, SHOW it to the user, get explicit
    approval, then `--action update --bio "..."`. (If a bio is actually
    present and `missing_for_seo` still lists it, you probably have a
    stale local copy of the skill — update it.)
  * `email` → "Which email should reporters reply to?" →
    `--action update --email jane@acme.com`
  Run `--action get` again afterwards to confirm `seo_ready` is now
  true.
* If `ready_to_pitch == false` → no persona exists. Go to the create
  flow below.

**⚠️ Safety rail — overwrite protection.** If the user asks you to
*change* an already-populated field (e.g. "update my bio to X"), the
script will REFUSE the PATCH unless you pass `--force-overwrite`. This
is intentional. The correct flow is:

1. Run `--action get` and read `bio_preview`.
2. Show the user BOTH the current bio AND the proposed new one.
3. Ask explicitly: "Replace the current bio with this one?"
4. Only if they say yes, re-run with `--force-overwrite`.

Never pass `--force-overwrite` preemptively "just in case".

If `ready_to_pitch == false`, you need to **collect the user's info
in a single message before running create**. Don't drip-ask one field
at a time. Use this exact checklist:

> **REQUIRED to even create the profile:**
> - `--full-name` — the user's real name as the byline should appear
>
> **STRONGLY RECOMMENDED — without these the profile is useless for SEO:**
> - `--url` — the user's **business website URL** (e.g. `https://acme.com`).
>   ⚠️ This is the link journalists put in their articles when they
>   credit the user. **No URL = no backlink = the whole point of this
>   skill is defeated.** Confirm it before running create.
> - `--bio` — a 2-4 sentence description of who the user is, what they
>   do, and what topics they can credibly speak to. The bio is what
>   reporters skim when deciding whether to use a quote. Mention the
>   business name, role, and 2-3 areas of expertise. If the user gave
>   you their bio elsewhere, use that. If not, draft one from what they
>   told you and **show it to them for approval before submitting**.
> - `--email` — the user's professional email (where reporters reply).
>
> **NICE TO HAVE (ask but don't block on):**
> - `--linkedin` — full LinkedIn profile URL (boosts credibility a lot)
> - `--location` — `"City, State, Country"` (some pubs filter by region)
> - `--gender` — one of `f` / `m` / `nb` / `sd` (for pronouns in articles)
> - `--twitter`, `--phone`, `--facebook`, `--instagram` — only if the
>   user wants reporters to have these channels.

**Always ask the user to confirm at minimum the URL, bio and email**
before firing the create command. Those three are what end up in
articles. Example of how to ask:

> "Before I set up your Qwoted expert profile, I need to confirm a few
> things that journalists will see and link to:
>
> 1. **Business URL** — what site should reporters link to when they
>    credit you? (e.g. `https://acme.com`)
> 2. **Bio** — here's a draft based on what you told me: *"Jane is the
>    founder of Acme Inc, a B2B SaaS that helps marketing teams ship
>    campaigns 10x faster. She speaks to growth, GTM and pricing."*
>    Sound right?
> 3. **Reply-to email** — which email should reporters use to follow up?
>
> Anything you'd like to add (LinkedIn, location, etc.)?"

Then build the command from their answers:

```bash
python3 qwoted_profile.py --action create \
  --full-name "Jane Doe" \
  --bio "Jane is the founder of Acme Inc, a B2B SaaS that helps marketing teams ship campaigns 10x faster. She advises on growth, GTM and pricing." \
  --url https://acme.com \
  --email jane@acme.com \
  --linkedin https://www.linkedin.com/in/jane-doe/ \
  --location "San Francisco, CA, USA" \
  --gender f
```

Repeat any contact flag to add multiple values (the first one becomes
primary). Other flags: `--off-the-record`, `--hide-from-search-engines`.

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

### ⚠️ MANDATORY — classify EVERY opportunity with the Stage-3 heuristic

After you've picked a shortlist, you MUST run each one through the
Stage-3 heuristic table at the top of this file and present the
classification to the user in a table. **Do not skip this step, do
not wait for the user to ask about stats pages.** A typical output
looks like this:

> I'd prioritise 5 of the 8 opportunities. Here's the Stage-3 classification:
>
> | SR ID | Publication | Topic | Deadline | Stats-page score | Action |
> |---|---|---|---|---|---|
> | 235897 | TechCrunch | marketing automation trends | 3d | **+5** | **Build `marketing-automation-statistics-2026.html`**, then pitch |
> | 236422 | Selling Signals | awareness vs demand | 20h | +1 | Pitch direct |
> | 234782 | BCA Insider | local SEO for retailers | 5d | **+4** | **Build `local-seo-statistics-2026.html`**, then pitch |
> | 236145 | SEOptimer | how agencies make money | 8h | -3 | Pitch direct (too tight, founder-story) |
> | 232532 | Business RoundUp | founder interview | 8d | -3 | Skip ($95 fee, founder-story) |
>
> Plan: I'll build the 2 stats pages first (they cluster future
> opportunities too), then draft direct pitches for #235897, #236422
> and #234782 that link to them. I'll draft a plain pitch for #236145
> because of the deadline. Sound good?

When the user replies "ok" / "yes" / "go", move on to Stage 3 for
the pages you identified, then Stage 4 for the pitches.

---

## Stage 3 — Build a sourced statistics page (the linkable asset)

> **READ `STATISTICS_PAGE_PLAYBOOK.md` BEFORE EXECUTING THIS STAGE.**
> This section is just the *when*. The *how* (research methodology,
> source quality bar, HTML build, anti-hallucination rules) lives in
> the playbook.

### Why it matters

A pitch that just contains opinion gets one quote in one article. A
pitch that links to a comprehensive, sourced statistics page on the
same topic gets the user *recurring* citations for months — because
the next reporter who searches `"<topic> statistics 2026"` finds the
page on the user's domain and cites it without ever knowing the user
exists. **This is the move that turns Qwoted from a one-off PR tool
into a compounding SEO engine.**

### When to build a stats page (decision rule)

Offer to build one when **all** of these are true:

1. The opportunity topic is broad enough to support a stats roundup
   (e.g. "AI in marketing trends" — yes; "founders who pivoted in
   2024" — no, that's an anecdote ask).
2. The deadline is **at least 24-48 hours away** (research takes time
   if you're going to do it well).
3. The user doesn't already have a recent, high-quality stats page on
   the same topic.

Skip and go straight to Stage 4 when the deadline is tight or the ask
is qualitative (anecdotes, opinions, case studies).

If multiple Stage 2 opportunities are on the same topic, **build the
stats page once and reuse it across every pitch in that batch** with
the same `--research-page-url` flag.

### How to ask the user

Don't just unilaterally start building a 3000-word page. Ask:

> *"Two of the opportunities I found are about [topic]. I can build
> you a sourced statistics page on this — it's a one-time effort that
> typically earns you backlinks for months because journalists cite
> it organically. The page would have ~50-80 stats, 2 charts, and a
> couple of comparison tables. Takes me ~5-10 minutes to research and
> draft. Want me to do it before pitching, or just pitch directly?"*

### How to execute

1. **Read `STATISTICS_PAGE_PLAYBOOK.md`** — it has the full research
   methodology, source quality bar, and HTML build instructions.
2. **Pull the user's bio info** so the byline + author footer are
   filled correctly:
   ```bash
   python3 qwoted_profile.py --action get
   ```
   Use `first_pitchable_entity.name`, `.url`, `.company_name`, `.bio`.
3. **Research** using the playbook's source priority + quality bar.
4. **Build the HTML** by filling in the placeholders in
   `templates/statistics_page_example.html`.
5. **Save to** `./statistics_pages/<slug>.html`.
6. **Tell the user** how to preview (`open ./statistics_pages/<slug>.html`)
   and ask them to publish on their own site (their CMS, their call).
7. **Wait for the public URL** — don't proceed to Stage 4 without it.

---

## Stage 4 — Draft and send pitches

### How to write a great pitch (this is on YOU, the AI)

Each pitch should be:

* **2-4 short paragraphs**, max 250-400 words.
* **First sentence** says who the user is and why they're qualified for
  *this specific* request. (Don't recycle the bio — synthesize.)
* **Body** gives the reporter *concrete, quotable insights* directly
  answering the request. 2-4 bullet points work great. Numbers,
  specific examples and contrarian takes get used; vague platitudes
  get deleted.
* **If you built a Stage 3 stats page** for this topic, reference
  the URL in the second paragraph: *"I just published a 50-stat
  roundup on [topic] at [URL] — happy to pull the most relevant
  ones for your angle."* This is the move that gets the page cited.
  Quote 2-3 of the most striking stats inline so the reporter sees
  immediate value without clicking.
* **Last sentence** offers a credit format (e.g. `Credit me as Jane
  Doe, founder of Acme Inc (acme.com)`) and an offer to expand or
  hop on a quick call.
* **No links in the pitch body OTHER than the stats page URL** — keep
  the pitch focused. The stats page is the only link that earns a
  backlink.
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
  --research-page-url https://acme.com/blog/ai-marketing-statistics-2026 \
  --send
```

The `--research-page-url` flag is optional but **strongly recommended
when you built a Stage 3 stats page**. It gets logged alongside the
pitch in `~/.qwoted/sent_pitches.json` so you can later answer
questions like "which research pages drove the most pitches" or
"which page is the user citing in this PR push".

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
* **Never invent statistics in a Stage 3 page.** Every stat must have a
  real URL you actually fetched. One fabricated stat caught by a
  journalist torpedoes the user's reputation forever. See the
  anti-hallucination rules in `STATISTICS_PAGE_PLAYBOOK.md`.
* **Never pitch opportunities outside the user's expertise.** Qwoted
  tracks reply rate and bad pitches hurt the account permanently.
* **Never modify `~/.qwoted/sent_pitches.json`** by hand — the
  duplicate guard relies on it. Treat it as append-only state.
* **Never commit `~/.qwoted/` to git.** It contains the user's session
  cookies (`storage_state.json`) — full account access.
* **Never publish a Stage 3 stats page on Medium / LinkedIn / dev.to
  before the user's own domain.** The canonical version must live at
  `https://<theirsite>/...` — that's where the backlinks need to go.

---

## Quick reference — every command

```bash
# Setup
python3 qwoted_login.py                                  # idempotent: skips browser if session is still valid
python3 qwoted_login.py --force                          # open browser even if session is valid (switch accounts)
python3 qwoted_login.py --reset                          # wipe saved profile + cookie jar, start fresh
python3 qwoted_login.py --headless                       # headless only works if an existing session is valid

# Profile
python3 qwoted_profile.py --action get                   # what entities exist?
python3 qwoted_profile.py --action create --full-name '...' --bio '...' --email '...'
python3 qwoted_profile.py --action update --bio '...'    # edit first Source

# Search
python3 qwoted_search.py --query "marketing automation" --max-hits 30
python3 qwoted_search.py --query "" --max-hits 50        # all opportunities

# Build a stats page (Stage 3)
# 1. READ STATISTICS_PAGE_PLAYBOOK.md for the research methodology
# 2. Open templates/statistics_page_example.html
# 3. Fill in placeholders → save to ./statistics_pages/<slug>.html
# 4. open ./statistics_pages/<slug>.html  # preview
# 5. User publishes on their site → returns public URL

# Pitch
python3 qwoted_pitch.py --source-request-id 235897 --pitch-text-file /tmp/p.txt
python3 qwoted_pitch.py --source-request-id 235897 --pitch-text-file /tmp/p.txt --send
python3 qwoted_pitch.py --source-request-id 235897 --pitch-text-file /tmp/p.txt \
    --research-page-url https://acme.com/blog/x-stats-2026 --send       # with stats page
python3 qwoted_pitch.py --opportunity-id de1ccdba --pitch-text-file /tmp/p.txt --send  # short URL form
```

State directory: `~/.qwoted/` (override with `QWOTED_HOME` env var).
