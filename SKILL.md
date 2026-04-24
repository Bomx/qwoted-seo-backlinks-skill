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

The skill ships four CLI scripts you call as subprocesses, plus a
research playbook and an HTML template. Each script prints a single
`RESULT: { ... }` JSON line on stdout that you parse to decide the
next step. Detailed human-readable logs go to stderr.

```
qwoted_login.py                      # one-time auth (browser the user signs into)
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

Stage 3 is the multiplier. A naked pitch lands one quote in one
article. A pitch that links to a thoroughly-sourced stats page lands
*recurring* citations for months because reporters who search for
"<topic> statistics 2026" find the page and cite it on their own.
**Always offer Stage 3 when the topic is broad enough and the
deadline allows.** See `STATISTICS_PAGE_PLAYBOOK.md` for when to skip
it.

---

## Decision tree — what to do based on what the user asks

| User intent | Skill stage(s) |
|---|---|
| "Set me up on Qwoted" / first time | Stage 1: `qwoted_login.py` → `qwoted_profile.py --action get` → create/update as needed |
| "Update my Qwoted bio" / "change my expert profile" | Stage 1c: `qwoted_profile.py --action update --bio '...'` |
| "Find PR opportunities about X" | Stage 2: `qwoted_search.py --query "X" --max-hits 30` |
| "Build me a stats page on X" / "make a research page about X" | Stage 3 only: read `STATISTICS_PAGE_PLAYBOOK.md` and execute |
| "Pitch opportunity #N" / "draft a pitch for SR 235897" | Stages 2 → 3 (if applicable) → 4: dry-run → user approves → `--send` |
| "Pitch the top 3 opportunities about X" | Stage 2 → Stage 3 ONCE for X → Stage 4 looped 3x with the same `--research-page-url` |

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

Parse the `RESULT:` JSON.

* If `seo_ready == true` → skip to Stage 2.
* If `ready_to_pitch == true` but `seo_ready == false` → the persona
  exists but is incomplete. Look at `missing_for_seo` (an array). For
  each item, ask the user the corresponding question and patch with
  `--action update`:
  * `business_url` → "What URL should reporters link to when they
    credit you?" → `--action update --url https://acme.com`
  * `bio` → draft a 2-4 sentence bio, get user approval, then
    `--action update --bio "..."`
  * `email` → "Which email should reporters reply to?" →
    `--action update --email jane@acme.com`

  Run `--action get` again afterwards to confirm `seo_ready` is now true.

* If `ready_to_pitch == false` → no persona exists. Go to the create
  flow below.

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
