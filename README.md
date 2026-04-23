# Qwoted SEO Backlinks Skill

> **AI-powered PR automation for Qwoted, with linkable-asset
> generation built in.** Let your Claude Code agent set up your
> expert profile, find journalist requests, **research and build a
> sourced statistics page on the topic** (the kind journalists love
> to cite), and send pitches that link to it — earning press
> mentions and recurring high-DR backlinks while you focus on the
> work that matters.

[Qwoted](https://qwoted.com) is the modern HARO replacement: every day,
journalists at TechCrunch, Forbes, Inc., 1851 Franchise, Adweek and
6,000+ other publications post requests for expert sources on a topic
they're writing about. Reply with a thoughtful pitch and you might land
in the article — usually with a do-follow link back to your site (which
is why this is one of the best white-hat SEO backlink channels in 2026).

**The unique move in this skill is Stage 3:** instead of just sending
a naked opinion pitch, Claude can research and generate a
comprehensive HTML statistics page on the topic (40-80 sourced stats,
Chart.js charts, schema.org markup, ready to publish on your CMS).
You publish it, Claude pitches with the link. The journalist gets
quotable numbers; you get one-shot mentions *plus* recurring
citations for months as other reporters discover your page through
search.

This skill teaches Claude Code (or any AI agent that can shell out) how
to drive Qwoted end-to-end on your behalf, so you can say things like:

- *"Find me PR opportunities about marketing automation today."*
- *"Build me a sourced stats page on AI in marketing, then pitch
  the top 3 opportunities about it."*
- *"Update my Qwoted bio to reflect my new role."*

…and have it actually happen.

---

## Install as a Claude Code skill

```bash
npx skills add Bomx/qwoted-seo-backlinks-skill
```

Or clone manually:

```bash
git clone https://github.com/Bomx/qwoted-seo-backlinks-skill.git
cd qwoted-seo-backlinks-skill
pip install -r requirements.txt
playwright install chromium
```

That's it. Claude reads `SKILL.md` to learn the workflow.

## Setup (3 minutes, one time)

### 1. Sign up for Qwoted

Free account at [qwoted.com](https://qwoted.com). Pick the "I am a
source / brand" option (not "I am media"). You'll get an email to
verify.

### 2. Tell Claude to set you up

Once the skill is installed, just say:

> *"Set me up on Qwoted. My name is Jane Doe, I'm the founder of Acme
> Inc, our website is acme.com and my LinkedIn is /in/jane-doe. We do
> marketing automation for B2B SaaS."*

Claude will:

1. Run `qwoted_login.py` — a Chromium window opens; you sign in to
   Qwoted (this includes MFA, captchas, anything Qwoted asks for).
2. Save your session cookies to `~/.qwoted/storage_state.json`.
3. Run `qwoted_profile.py --action create ...` to fill out your
   "expert" Source persona (the thing Qwoted attaches to every pitch
   so reporters know who's pitching them).
4. Confirm everything is wired up correctly.

### 3. Done — start pitching

> *"Find Qwoted opportunities about SaaS pricing this week, then pitch
> the top 3."*

Claude will search the index, draft a custom pitch per opportunity
based on your bio, **show each pitch to you for approval**, and then
submit only the ones you say yes to. Sent pitches are logged to
`~/.qwoted/sent_pitches.json` so the same opportunity never gets
pitched twice.

---

## What the skill ships

| File | What it does |
|---|---|
| `qwoted_login.py` | One-time browser login. Saves cookies to `~/.qwoted/`. Re-runs only if cookies expire (typically every 30 days). |
| `qwoted_profile.py` | Get / create / update your Qwoted "Source" persona — the bio, employer, location and contact links every pitch is attached to. |
| `qwoted_search.py` | Searches the same Algolia index Qwoted's website uses. Returns clean JSON with deadline, publication, request type, hashtags, etc. |
| `qwoted_pitch.py` | Drafts and (optionally) submits pitches via Qwoted's internal API. Defaults to dry-run; you must pass `--send` to actually fire. Optional `--research-page-url` flag logs the linked stats-page URL for traceability. |
| `STATISTICS_PAGE_PLAYBOOK.md` | The research methodology Claude follows when building a Stage-3 stats page: source quality bar, anti-hallucination rules, structure, length targets, anti-patterns. |
| `templates/statistics_page_example.html` | Self-contained HTML scaffold (modern responsive CSS, Chart.js charts, Article + FAQPage schema markup, print-friendly). Claude fills in the placeholders. |
| `SKILL.md` | The Claude Code playbook itself — frontmatter + 4-stage workflow. |

All four scripts are pure Python (`requests` + `playwright`) and have
an opinionated `RESULT: { ... }` JSON output line so AI agents can
chain them together reliably.

---

## The 4-stage workflow

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
*recurring* citations for months because the next reporter who
searches `"<topic> statistics 2026"` finds the page on your domain
and cites it on their own.

## State directory

Everything lives under `~/.qwoted/` and `./statistics_pages/`:

```
~/.qwoted/
├── storage_state.json     # session cookies (full account access — do NOT share)
├── chromium-profile/      # persistent Chromium profile so re-logins are 1-click
├── profile_state.json     # snapshot of your Sources/Products/Companies
├── sent_pitches.json      # append-only log w/ research_page_url tracking
└── opportunities/         # JSON dumps from each search
    └── marketing_20260422_153058.json

./statistics_pages/        # generated stats pages (Stage 3 output)
└── ai-in-marketing-statistics-2026.html
```

Override the `~/.qwoted/` location with `QWOTED_HOME=/some/path`.
Reset by deleting the folder.

---

## Running the scripts directly (no AI)

You can use this skill as a regular CLI too:

```bash
# Set up
python3 qwoted_login.py
python3 qwoted_profile.py --action get

# Find opportunities about SaaS pricing
python3 qwoted_search.py --query "saas pricing" --max-hits 20

# Dry-run a pitch (no email sent)
python3 qwoted_pitch.py \
  --source-request-id 235897 \
  --pitch-text-file ./my_pitch.txt

# Actually send it
python3 qwoted_pitch.py \
  --source-request-id 235897 \
  --pitch-text-file ./my_pitch.txt \
  --send
```

Run any script with `--help` for the full flag list.

---

## Why a separate "expert" Source persona is required

Qwoted's pitch API will happily accept a submission *without* a
pitchable entity attached (HTTP 200, draft=false), but **the reporter
is never notified**. The pitch is functionally dead. We learned this
the hard way; the skill now refuses to fire `--send` if no Source /
Product is attached, and the setup wizard makes sure you have one
before you can pitch.

---

## Privacy + security

- **No telemetry.** Every script makes one of: a Qwoted API call, an
  Algolia search, or a local file write. There is no third-party
  reporting, analytics or "phone home". Read the source, all 5 files
  are < 700 lines each.
- **Cookies stay local.** `~/.qwoted/storage_state.json` never leaves
  your machine. It IS effectively your Qwoted password — `.gitignore`
  blocks it from being committed accidentally.
- **MIT license.** Fork it, ship a paid SaaS on top of it, whatever.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No Qwoted session found` | `python3 qwoted_login.py` |
| Login window opens but never closes | You're stuck on Qwoted's login page. Sign in fully. |
| `Cannot --send: no pitchable Source/Company/Product` | Run `qwoted_profile.py --action create ...` first. |
| `already has a SENT pitch` | Qwoted only allows one pitch per source-request. Pick a different one. |
| Playwright says `Executable doesn't exist` | Run `playwright install chromium` once. |

---

## Built by

[Borja Obeso](https://www.linkedin.com/in/borja-obeso/), founder of
[Distribb](https://distribb.io) — a content distribution & SEO
platform that syndicates one piece of content across 200+ DR40+ sites
and channels.

If you want this on autopilot for your whole content engine (not just
Qwoted), check out [distribb.io](https://distribb.io) and the
[Distribb skill](https://github.com/Bomx/distribb-skill) for keyword
research, backlink exchange and CMS publishing.

---

## Related searches this repo answers

`qwoted automation`, `qwoted api`, `qwoted skill claude`, `claude code
seo skill`, `auto pr backlinks`, `journalist pitch automation`, `haro
alternative automation`, `pr outreach ai agent`, `expert source pr
tool`, `automated press mentions`, `ai-generated statistics page`,
`linkable asset for seo`, `journalist citation backlinks`,
`programmatic seo pr`, `claude code stats page generator`,
`haro pitch automation 2026`.
