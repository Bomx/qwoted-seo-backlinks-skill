# Statistics Page Playbook

> Read this when you (Claude) are about to build a research-backed
> statistics page for the user as part of the Qwoted pitching workflow.
> The goal is to produce a *linkable asset* — one URL the user can
> point dozens of journalists to over months — not just a one-off
> piece of supporting material for a single pitch.

## Why we do this

Pitches that link to a comprehensive statistics roundup convert
dramatically better than naked opinion pitches. Reasons:

1. **Reporters are paid to cite numbers, not opinions.** Giving them
   pre-vetted, sourced stats makes you the easiest possible source to
   work with — they can quote, screenshot, or link to your page
   without doing any extra work.
2. **The page keeps earning backlinks for years.** Once it ranks,
   journalists searching `"<topic> statistics 2026"` find it
   themselves and cite it. Your one pitch turns into 10-50+ cumulative
   backlinks.
3. **Stats pages are AI-search friendly.** ChatGPT, Perplexity and
   Google's AI Overviews preferentially cite pages with structured
   data and numbered facts (per Distribb's own SEO stats page,
   *"Pages with structured answers and entity-driven content were 3.2
   times more likely to show up in AI summaries in 2025"*).

## When to build a stats page (vs just pitching directly)

Build a stats page when **at least one** of these is true:

- The opportunity is broad enough that a stats roundup would be
  helpful (e.g. "marketing automation trends" — yes; "looking for
  founders who pivoted in 2024" — no, that's an anecdote ask).
- The user already has 1-2 strong stats pages on their site and you
  want to cluster more.
- The reporter is at a tier-1 publication (TechCrunch, Forbes, Inc.,
  WSJ, etc.) — worth the extra effort.
- There are multiple opportunities on Qwoted on the same topic —
  build the page once, pitch it 5+ times.

Skip the stats page (just pitch directly) when:
- The deadline is < 24 hours away — there's no time to research and
  publish properly.
- The reporter explicitly wants personal anecdotes / case studies.
- The topic is so niche there isn't enough public data.

---

## Step 1 — Identify the angle

Before researching, lock in:

1. **Topic** — extracted from the source request. e.g. *"AI in
   marketing"*, *"SaaS pricing trends"*, *"remote work productivity"*.
2. **Slug** — `<topic-words>-statistics-2026`. Used as both the file
   name and the suggested URL slug for the user's CMS.
3. **Title** — `<TOPIC> Statistics You Need to Know in 2026`. Boring
   on purpose — this is the exact phrase journalists search for.
   Don't try to be clever (`"The Ultimate Guide..."` ranks worse).
4. **Sections** — a list of 6-12 themed buckets you'll fill. Common
   patterns:
   - Market Size & Growth
   - User / Buyer Behavior
   - Adoption & Usage
   - Technology / Platform Trends
   - ROI & Performance
   - Investment & Spending
   - Industry Benchmarks
   - Regional / Demographic Breakdown
   - Future Projections / Predictions
   - Conclusion + (optional) FAQ

Tell the user the planned title and section list before researching,
so they can redirect if the angle is off.

---

## Step 2 — Research (the bar is high)

### Sources to PREFER, in priority order

1. **Primary research from analyst firms** — Gartner, Forrester,
   McKinsey, Deloitte, Accenture, IDC, IBM Institute, BCG.
2. **Vendor "State of X" reports with stated methodology** — HubSpot
   State of Marketing, Salesforce State of Sales/Service/Marketing,
   Semrush, Ahrefs, Buffer, Notion, Stripe, Slack, Zapier State of X.
3. **Industry trade publications with original reporting** — Search
   Engine Land, Marketing Brew, Inc., HBR, MIT Sloan Review,
   TechCrunch (when they cite a primary report).
4. **Government / inter-governmental data** — US BLS, US Census,
   Eurostat, WIPO, OECD, UN.
5. **Academic / peer-reviewed** — Google Scholar, arxiv.org for
   technical topics.
6. **Reputable market sizing reports** — IMARC, Grand View Research,
   Mordor Intelligence, Statista (often paywalled, cite via vendor
   blogs that summarise).
7. **Reputable surveys** — Pew Research, Edelman Trust Barometer,
   Gallup, Morning Consult, YouGov.

### Sources to AVOID

- Random listicle blogs that just cite each other (always trace to
  the primary source — if you can't find one, drop the stat).
- Press releases without underlying data.
- Affiliate / vendor-promotional content masquerading as research.
- AI-generated stats roundups (the source of most hallucinated
  numbers polluting the web — don't propagate them).
- Stats older than 3 years unless they're the only authoritative
  number (label them with the year clearly).
- Wikipedia (always cite the primary source Wikipedia is citing).

### Quality bar — every single stat must pass ALL of these

- ☑ Has a **named source** (organisation/publication, not "experts say")
- ☑ Has a **year** (this year, last year, or labelled appropriately)
- ☑ Is **specific** (a number, percentage, ratio — not vague modifiers)
- ☑ Has a **real URL you actually fetched** (not a search result snippet).
  ⚠️ This URL is for YOUR verification during research only. It is
  stored in the research JSON as proof-of-existence. It is **not**
  rendered as a clickable link in the final HTML — see "Hoard the
  juice" below.
- ☑ Is **quoted faithfully** (don't round or extrapolate)
- ☑ The source URL **works at the time of writing** (so if anyone
  spot-checks it they find the original — but again, not rendered
  as a clickable link)

---

## 🔒 Hoard the juice — ZERO outbound links in the rendered HTML

The statistics page is a **linkable asset**: its job is to ATTRACT
inbound links from journalists, bloggers and other stat roundups —
not to DISTRIBUTE authority outward. Every outbound `<a href>` leaks
a little PageRank and gives crawlers a reason to follow a link off
the user's domain instead of deeper into it. We refuse to do that.

**Hard rule: the rendered HTML must contain ZERO `<a>` tags pointing
to any domain other than the page's own domain.** No exceptions, no
`nofollow` workarounds (nofollow is just a hint in 2026 and still
triggers crawl).

### What this means in practice

| Pattern | Allowed? | Example |
|---|---|---|
| Source attribution as **plain text** | ✅ REQUIRED | `(Source: HubSpot State of Marketing, 2026)` |
| Source attribution as a clickable link | ❌ FORBIDDEN | `(Source: <a href="https://hubspot.com/…">HubSpot</a>, 2026)` |
| Internal TOC anchor link | ✅ Fine | `<a href="#market-size">Market Size</a>` |
| Author-bio CTA to the user's own business URL (SAME domain as the page) | ✅ Fine | `<a href="https://distribb.io">Distribb →</a>` when the page lives at `distribb.io/blog/...` |
| Link to an analyst firm's methodology page | ❌ FORBIDDEN | strip it |
| Link to a social profile (LinkedIn/Twitter of a quoted analyst) | ❌ FORBIDDEN | strip it |
| Link to the publisher's homepage / other article | ❌ FORBIDDEN | strip it |

### Rendering source attribution

Every time a stat appears, attribute it inline as plain text. Use
this exact pattern so the "Source:" prefix is consistent and the
year is always present:

```html
<li><strong>42% of B2B marketers say AI is their #1 priority.</strong>
    <span class="source">(Source: HubSpot State of Marketing, 2026)</span></li>
```

NOT:

```html
<!-- WRONG — leaks juice -->
<li><strong>42% of B2B marketers…</strong>
    <span class="source">(Source: <a href="https://hubspot.com/…">HubSpot</a>, 2026)</span></li>
```

### Where the source URLs live

- In the research JSON (Step 3) — that's your audit trail and what
  proves the stat wasn't hallucinated.
- Optionally, at the bottom of the rendered HTML inside an HTML
  comment so a human reviewer can open view-source and spot-check:

```html
<!--
audit_trail:
- stat: "42% of B2B marketers say AI is their #1 priority"
  source_name: "HubSpot State of Marketing"
  source_url: "https://www.hubspot.com/state-of-marketing/2026"
  year: 2026
- ...
-->
```

HTML comments are invisible to readers and not followed by crawlers.

### Why not just use `rel="nofollow noopener"`?

1. Google treats `nofollow` as a "hint" since 2020 and still crawls
   through them.
2. Some minor PageRank leakage is still debated.
3. Zero `<a>` tags is the only *provably* leak-free posture.
4. It's also simpler to audit: a `grep 'href="http'` on the rendered
   file should return zero hits (apart from the canonical link in
   `<head>` and on-domain internal links).

### One trade-off to acknowledge

Well-placed outbound links to authoritative sources are a mild
positive ranking signal (Google has confirmed this). On a brand-new
domain with zero authority, a stats page with zero outbound links
may rank slightly slower initially. Mitigations we already apply:

- Rich on-page signals (Article + FAQPage schema, author bio, date
  stamps, named sources in plain text).
- Strong internal linking from the user's blog to the new page.
- Pitch-driven backlinks from the Stage 4 workflow build authority
  over time.

For a domain that already has authority (e.g. `distribb.io`), the
no-outbound posture is a pure win. Accept the small cold-start cost
for new domains.

### Research workflow

```
For each section in your planned outline:

  1. Run 2-4 web searches using these query patterns:
     - "{topic} statistics {YEAR}"
     - "{topic} market size {YEAR}"
     - "{topic} survey results {YEAR}"
     - "state of {topic} report {YEAR}"
     - "{topic} ROI" OR "{topic} effectiveness"
     - "{topic}" research site:gartner.com OR site:forrester.com OR site:mckinsey.com
     - "{topic}" filetype:pdf {YEAR}

  2. For each promising hit, FETCH the page (don't trust snippets).

  3. Extract candidate stats. For each one, capture:
       { "stat": "94% of marketers plan to use AI in content creation processes in 2026",
         "source_name": "HubSpot",
         "source_url": "https://www.hubspot.com/state-of-marketing/...",
         "year": 2026,
         "section": "Content Strategy and AI" }

  4. Discard any stat where you can't verify all 6 quality criteria.

  5. Stop when you have 5-12 verified stats for that section.
     If after 4 searches you still have <3 stats, drop the section.
```

### Stat count targets

- **Total**: 40-80 stats across the whole page.
- **Per section**: 5-12 (sections with fewer feel thin; more than 12
  becomes scannable spam).
- **Unique source domains**: at least 8.
- **Recency**: ≥ 60% of stats from current or previous year.

### What to do when stats conflict

If two reputable sources give different numbers for the same fact
(e.g. global SEO market size), include both with their attributions
— don't pick one. Reporters love seeing the spread.

---

## Step 3 — Build the HTML page

Use `templates/statistics_page_example.html` as your starting point.
It's a single self-contained file with:

- Modern responsive layout (mobile-first, CSS Grid)
- Embedded Chart.js (CDN) for charts
- Schema.org Article + FAQPage JSON-LD
- Print-friendly styles
- Anchor-linked table of contents (internal fragments only)
- "Headline stat" callouts inside each section
- Tables for ranking/comparison data
- Author bio footer with link to user's site (on-domain CTA only)
- **Zero outbound `<a>` tags** — source citations are plain text
  (see "Hoard the juice" section above)

### What you fill in

Open the template, find every `{{...}}` placeholder and replace it.
The placeholders are:

| Placeholder | Source | Example |
|---|---|---|
| `{{TITLE}}` | Step 1 #3 | `AI in Marketing Statistics You Need to Know in 2026` |
| `{{SLUG}}` | Step 1 #2 | `ai-in-marketing-statistics-2026` |
| `{{TOPIC}}` | Step 1 #1 | `AI in Marketing` |
| `{{TOPIC_LOWER}}` | derived | `ai in marketing` |
| `{{INTRO_PARAGRAPH}}` | you write, 2-3 sentences | – |
| `{{LAST_UPDATED}}` | today's date | `April 22, 2026` |
| `{{AUTHOR_NAME}}` | from `qwoted_profile.py --action get` | `Jane Doe` |
| `{{AUTHOR_TITLE}}` | from profile (employments_string_without_company) | `Founder, Acme Inc` |
| `{{AUTHOR_URL}}` | from profile (`url` field) | `https://acme.com` |
| `{{AUTHOR_BIO}}` | from profile (`bio` field) | – |
| `{{ACCENT_COLOR}}` | match user's brand if known, else `#3a86ff` | – |
| `{{SECTIONS}}` | list of `{id, title, intro, headline_stat, stats[], chart?, table?}` | – |
| `{{SOURCES}}` | deduped list of source names (PLAIN TEXT, not links) used | `Gartner, HubSpot, Semrush, McKinsey, ...` |
| `{{FAQS}}` | optional 4-6 Q&A pairs | – |

Per-stat placeholders inside the template (`{{SOURCE_NAME_N}}`,
`{{YEAR_N}}`, `{{STAT_N}}`) are all rendered as plain text. There is
NO `{{SOURCE_URL_N}}` / `{{URL}}` placeholder anymore — those were
removed when we locked in the no-outbound-links rule. Store source
URLs only in the research JSON (Step 3) and, optionally, in the
audit-trail HTML comment at the bottom of the page.

### Charts

Add 1-3 Chart.js charts only when there's actual quantitative data
worth visualising. Good cases:

- **Line chart** — a metric over time (e.g. AI search volume year-over-year)
- **Bar chart** — comparison across categories (e.g. organic traffic share by industry)
- **Doughnut/Pie** — share-of-X breakdown (e.g. click share by SERP position)
- **Stacked bar** — composition over time

Bad cases (don't force a chart):
- A single number (just use a callout)
- 2 data points (just write a sentence)
- Comparisons across radically different scales (charts mislead more than help)

The example template has 2 commented chart blocks you can copy-paste.
Each one is ~12 lines of self-contained Chart.js inside a
`<div class="chart-card">` wrapper.

### Tables

Use HTML tables for ranking/comparison data with 4+ rows and 2+
columns. Examples that work well:

- Click-through rate by SERP position
- Market size by year (current + projected)
- Adoption rate by region/industry
- Tool comparison (features × vendors)

### Schema markup

The template has working `Article` and `FAQPage` JSON-LD blocks.
Don't remove them — they're what gets you into AI Overviews / ChatGPT
citations. If you have FAQ data, fill in the `FAQPage` block; if not,
delete just that one `<script type="application/ld+json">` block.

---

## Step 4 — Save and preview

Output the finished HTML to:

```
./statistics_pages/<slug>.html
```

(Create the directory if it doesn't exist.)

Tell the user the file path and how to preview it. Two simple options:

```bash
# Option A — open directly (charts work fine over file://)
open ./statistics_pages/ai-in-marketing-statistics-2026.html

# Option B — local server (recommended for testing schema with Google Rich Results)
cd statistics_pages && python3 -m http.server 7411
# then visit http://localhost:7411/ai-in-marketing-statistics-2026.html
```

**Always preview the page before pitching.** Visually scan for:

- Broken layout / overflowing tables
- Charts that didn't render (open browser console)
- Stats that look implausible (extra zero, wrong %)
- Source attribution missing on any stat
- Author bio + URL correct

---

## Step 5 — Hand off to the user for publishing

The user publishes the page on **their own site** at a URL like
`https://acme.com/blog/ai-in-marketing-statistics-2026`. They'll do
this in their CMS (WordPress, Webflow, Shopify, Next.js, Jekyll, etc.)
— it's outside the skill's scope.

Tell them, plain English:

> *"I've saved the page to `./statistics_pages/<slug>.html`. Open it
> in your browser to review. When you're happy, publish it on your
> site (paste the HTML body into your CMS as a custom HTML block, or
> upload the file as-is). Tell me the public URL when it's live and
> I'll write the pitch around it."*

If the user is on WordPress, suggest the **Custom HTML block** in
Gutenberg. If they're on Webflow, they can paste the HTML into a
"Custom Code" embed. If they're on a static site, they can drop the
file under `/blog/`.

---

## Step 6 — Pitch with the URL

Once the user provides the live URL, build the pitch around it:

```
Hi {reporter_name},

Saw your request about {topic}. I'm {author}, {role} at {company} —
we work on {1-sentence relevance}.

I just published a {stat-count}-stat roundup on {topic} that pulls
together the most-cited 2025/2026 numbers in one place: {public_url}

A few that might fit the angle of your piece:
  • {standout stat 1, with source}
  • {standout stat 2, with source}
  • {standout stat 3, with source}

Happy to expand on any of these or hop on a quick call if useful.
Credit me as {full_name}, {role} at {company} ({short_url}).

— {first_name}
```

Then run it through `qwoted_pitch.py` with the new
`--research-page-url` flag so the publication URL gets logged in
`~/.qwoted/sent_pitches.json` for traceability:

```bash
python3 qwoted_pitch.py \
  --source-request-id 235897 \
  --pitch-text-file /tmp/qwoted_pitch.txt \
  --research-page-url https://acme.com/blog/ai-in-marketing-statistics-2026 \
  --send
```

---

## Anti-patterns to avoid

- ❌ **Inventing stats.** If you can't find it, leave it out. One
  fabricated stat caught by a journalist torpedoes the user's
  reputation forever.
- ❌ **Citing AI-generated stats roundups as primary.** A lot of
  recent web pages are AI-written stat lists with hallucinated
  numbers. Trace every stat to a real research source.
- ❌ **Writing 10,000-word "ultimate guides".** Stats pages are scanned,
  not read. 1500-3500 words is the sweet spot.
- ❌ **Hiding sources.** Number every stat and cite at the end of each
  bullet. List all unique source domains in a Sources section at the
  bottom.
- ❌ **Forcing charts where there's no data story.** A bar chart with
  3 random numbers looks like padding.
- ❌ **Hot take topics with little public data.** Stats pages need
  stats; opinion pieces need a different format. Don't try to make a
  stats page about something genuinely qualitative.
- ❌ **Republishing the page on Medium, LinkedIn, etc. before the
  user's own site.** The canonical version must live on the user's
  domain — that's the whole point of the backlinks.

---

## Files this playbook references

- `templates/statistics_page_example.html` — the HTML scaffold to
  fill in.
- `qwoted_profile.py --action get` — pulls the author name / bio /
  URL you'll inject into the page.
- `qwoted_pitch.py --research-page-url <URL> --send` — logs the
  research page URL alongside each pitch.
