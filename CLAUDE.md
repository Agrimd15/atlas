# Atlas - Company Research Tool

## ▶️ Auto run routine UNPAUSED — daily budget: 5 reports per day

Per the user's instruction on 2026-06-11, scheduled / automatic / routine-triggered Atlas runs are
enabled with a budget that **resets every day**. Live counter: **0 remaining for 2026-06-11** (the
2026-06-11 scheduled run already published 5 briefs: CRWV, AVGO, APP, FIG, databricks).

Bookkeeping (mandatory for schedule/trigger-started sessions), in order, before running:
1. **Roll the day.** If the date in the counter line above is not today, reset the line to
   "5 remaining for <today's date>" — the new day starts with a fresh budget of 5.
2. **Respect the cap.** If the counter reads **0** remaining for today, do not run the pipeline:
   end the session with a one-line note that today's 5-report budget is exhausted (it resets
   tomorrow automatically — no pause block needed, no user action required).
3. **Decrement on publish.** Each time the session publishes a finished report (brief), reduce the
   counter by the number of reports published and commit that edit together with the run.

Manual, user-initiated requests are unaffected and never count against the budget.

## What This Is
Atlas turns a single company name or ticker into a banker-grade research brief. You (Claude Code)
act as a tech investment-banking analyst: dispatch parallel research agents, synthesize, and ship a
sourced HTML + PDF brief saved to a coverage database. Atlas is the first tool of the **Alfred**
analyst project.

**Coverage focus:** Software · Internet · Semis · Cloud/Infra · Cybersecurity · Vertical SaaS · TMT

When the user types a company name (e.g. "Salesforce", "CRM", "Palantir") - or runs `/atlas <name>` -
treat it as a research-run request and follow the **Execution Protocol** below automatically. Do not
ask for confirmation.

---

## Core Rules
- Start narrow, not broad
- Always include human review before any output is used
- Separate data gathering from writing
- Build reusable workflows
- Never produce client-ready outputs without a review step

---

## Data Freshness Mandate (non-negotiable)

Numbers in a brief - **especially trading multiples (EV/Rev, P/S, market cap, growth, margins)** - must come from a **live pull**, never from model memory. An MD will catch a stale or mis-dated multiple instantly, and it destroys trust in the whole brief.

1. **Live only.** Every multiple, price, and KPI must be sourced from `agents/data_agent.py` (yfinance/FMP) or a current web/API fetch at run time. If you cannot fetch it live, label it as an estimate with its date - do **not** silently use a remembered number.
2. **One close, every ticker.** All comps in a run are pulled together via `data_agent.live_quote()` so they share a single `marketCloseAsOf` anchor. Never mix a May close for one name with a June close for another. `data_agent.run()` emits `marketCloseAsOf` + a `freshnessNote` that flags any ticker lagging the rest - surface it, don't bury it.
3. **EV/Rev is recomputed, not borrowed.** `live_quote()` recomputes EV from `last close × shares + net debt` so the multiple is internally consistent and dated - not Yahoo's opaque pre-computed `enterpriseValue`.
4. **Date + source on every datapoint.** Every metric carries `priceAsOf` (the actual market close, not the run date), a `source`, and a `sourceUrl`. The brief must state the as-of close date plainly (e.g. "Multiples as of the 2026-05-30 close").
5. **Reasoning travels with the number.** When a figure could be questioned, note where it came from and how it was derived (e.g. "EV/Rev recomputed from last close × shares + net debt, yfinance").

If a number has no live source and no honest as-of date, leave it out rather than guess.

---

## Metric Clarity & Consistency Mandate (non-negotiable)

A number is only useful if the reader knows **what period it covers** and trusts that it **says the same thing everywhere it appears**. An MD spots a self-contradicting brief instantly - a revenue that reads $202M in the metrics grid and $210M in a slide bullet, or a "Q3 revenue" that happens to equal the full-year figure - and once one number doesn't tie, the whole brief is suspect.

1. **Every figure carries its period.** No bare number. Each `keyMetrics` value must make its window explicit - either inline (`"$202M (+28% YoY)"` under a `quarter`-stamped section, `"68.1% (LTM)"`, `"118% (as of July 31, 2025)"`, `"Revenue $90.5-91.0M (FY2026 guidance)"`) or via the section's `earningsTakeaways.quarter`. The deliverable agent renders a period tag on **every** metric card; if you leave a metric undated and the section has no `quarter`, QA flags it.
2. **Always set `earningsTakeaways.quarter` and `reportDate`.** `quarter` is the default reporting period for the whole metrics grid (e.g. `"Q1 FY2027 (ended April 30, 2026)"`); `reportDate` is when it was reported. The brief prints these as the anchor line under "Financials & Key Metrics".
3. **The same metric must match everywhere.** If a figure appears in `keyMetrics`, `revenueHistory`, a comp row, a slide bullet, and the prose, every instance must agree (within rounding). Recompute, don't re-type. When two figures legitimately differ, it's because the **period or basis differs** (quarterly revenue vs. ARR vs. LTM revenue vs. ARR growth) - so label each so the difference is obvious, never silent.
4. **A quarterly flow can't equal the annual flow.** Revenue, EBITDA, FCF, and net income are earned *over* a period; a quarter's value should be ~¼ of the year's, never identical. If a quarterly and an annual figure tie exactly, one is mislabeled - fix it.
5. **Don't conflate the subject with peers.** A peer's ARR/revenue in the narrative (e.g. "Zscaler ($2.2B ARR)") is not the subject's number - keep them clearly attributed so neither the reader nor the consistency auditor confuses them.
6. **Market multiples are live-only - never hard-type them into prose.** EV/Rev and market cap stored in `keyMetrics` are auto-overwritten at render time with the same live pull the hero bar and comps table use (one number, one close date, everywhere). Don't embed a raw multiple in slide bullets, SWOT points, or comp notes ("4.3x EV/Rev on 13% growth") - it goes stale the next trading day; describe it qualitatively ("the cheapest EV/Rev in its megacap peer set, live multiple in the comps table") or date the claim. The render QA compares every undated EV/Rev-style "N.Nx" in prose against the live multiple and warns on drift.

`agents/metric_audit.py` enforces 3-4 at render time (run inside `deliverable_agent.py`): it cross-checks every dollar figure, reports a **contradiction** (same metric + period, two values) as a BLOCKING error, and flags quarter-equals-annual collisions and undated headline figures as warnings. Rule 6's drift check runs in the deliverable agent's QA pass. Read the `🧮 QA metrics` line every run.

---

## Architecture (Wave Model)

### Wave 1 - Parallel Data Gathering (run simultaneously)
| Agent | Responsibility |
|---|---|
| Research | Company overview, product, market positioning, competitors, end markets, growth drivers |
| News | Recent headlines, M&A, funding, product launches, mgmt changes, regulatory shifts |
| Transcript | Earnings summaries, key quotes, mgmt tone, guidance, demand commentary |
| Data | KPIs, comps, trading metrics, ARR/NRR/bookings/RPO, margins, revenue mix |

### Wave 2 - Synthesis (after Wave 1 completes)
| Agent | Responsibility |
|---|---|
| Writing | Combines Wave 1 outputs → banker-style notes, slide bullets, memos, takeaways |

### Orchestrator (main agent)
Accepts input (ticker/company/theme) → dispatches Wave 1 in parallel → waits → triggers Wave 2 →
returns the brief with sources and draft status.

---

## Standard Output Format
1. Business Overview
2. Product and Revenue Model
3. Recent News
4. Latest Earnings Takeaways
5. Key Risks / Debates
6. Peer Companies / Comps Ideas
7. 5 Slide-Ready Bullets
8. 3 Smart Diligence Questions

---

## Folder Structure

```
atlas/
  CLAUDE.md                ← this file (operating spec)
  README.md · SETUP.md
  .env                     ← API keys (optional FMP) - never committed
  /agents                  ← data_agent.py, research_agent.py (incl. prompt templates), deliverable_agent.py, sources.py
  /design                  ← DESIGN.md (design language - all UI complies)
  /site                    ← static coverage site (build.mjs, template/, dist/)
  vercel.json · package.json · middleware.js   ← deploy config + password gate
  /data-dumps              ← the coverage database (one folder per company)
    /SNOW/
      profile.json         ← latest run (the coverage site reads this)
      /runs/2026-05-31/
        research.json · news.json · transcript.json · data.json
        SNOW_brief_2026-05-31.html (+ .pdf)
```

This repo IS the database. Git history shows how each company's profile evolved over time. The
published coverage site is just the lens. This public repo ships only the demo
companies; companies you research are gitignored by default (see `.gitignore`).

---

## Data Convention
- `profile.json` - always reflects the latest research run. The coverage site reads this.
- `runs/YYYY-MM-DD/` - full raw dump for each research run, never overwritten.
- After every run, write/overwrite `profile.json` and create a new dated `runs/` folder.

---

## Execution Protocol (run this every time a company name is typed)

**Step 0 - Resolve**
- Identify the canonical company name and determine if it is PUBLIC or PRIVATE.
- **Public:** use the exchange ticker as the folder ID (e.g. "Snowflake" → `SNOW`).
- **Private:** lowercase kebab-case slug of the company name - NO invented tickers (e.g. "Applied Intuition" → `applied-intuition`, "Databricks" → `databricks`).
- Determine today's date (YYYY-MM-DD). Create run folder `data-dumps/FOLDER_ID/runs/YYYY-MM-DD/`.

**Step 1 - Wave 1: run 4 searches in parallel**
Dispatch as parallel sub-agents simultaneously. **Trusted sources rule:** all agents MUST restrict searches to the source tiers in `agents/sources.py`. Do not cite random blogs, aggregators, Reddit, or unknown Substacks. See `agents/research_agent.py` for full prompt templates.

- **Research Agent** - `"[Company]" business model product revenue segments 2024 2025 (site:wsj.com OR site:bloomberg.com OR site:ft.com OR site:axios.com OR site:techcrunch.com OR site:theinformation.com OR site:stratechery.com OR site:sacra.com)` - also search `site:[company].com/leadership` for the current executive team; every leadership entry must be sourced from a live URL, never inferred from training data.
- **News Agent** - `"[Company]" news M&A funding announcement 2025 (site:wsj.com OR site:bloomberg.com OR site:ft.com OR site:reuters.com OR site:nytimes.com OR site:axios.com OR site:techcrunch.com OR site:theinformation.com OR site:semafor.com)`
- **Transcript Agent** - `"[Company]" earnings call transcript Q4 2024 OR Q1 2025 guidance (site:wsj.com OR site:bloomberg.com OR site:ft.com OR site:reuters.com OR site:cnbc.com OR site:seekingalpha.com)` - for private cos: CEO interviews on Axios, Bloomberg, WSJ.
- **Data Agent** - `"[Company]" ARR NRR revenue growth gross margin KPIs 2024 2025 (site:sacra.com OR site:meritech.com OR site:bvp.com OR site:wsj.com)` - and use `agents/data_agent.py` for live public trading data. **Additionally, for software/SaaS/AI companies call the Ramp Data MCP tools** (`ramp-data:ai_index_get_adoption`, `ramp-data:ai_index_get_adoption_by_sector`, `ramp-data:ramp_rate_get_vendor`) to get B2B demand signals — vendor adoption trends, growth rate, and share-of-spend across 50k+ businesses. Include results in `data.json` under `rampDemandSignal` using the schema in `agents/data_agent.py`. Skip for semis/hardware companies where corporate card spend is not a useful proxy. Ramp Data is free and citable as source: "Ramp Data (ramp.com/data)".

Each agent returns a structured JSON summary saved to the run folder. **Every news item, quote, and metric must include a `source` (publication) and `sourceUrl` (direct URL).** Items without sources are invalid. **Deep links only** - the `sourceUrl` points to the specific article/filing/page, never a homepage (`bloomberg.com`) or section landing page. Stay inside the `agents/sources.py` tiers; press-release aggregators (nasdaq.com, stocktitan), Motley Fool, and unknown blogs are **not** sources.

**Paywalled / bot-blocked Tier-1 domains (expected, not an error).** WSJ, FT, Reuters, Bloomberg, and sec.gov HTML pages routinely refuse direct page fetches (401/403/429 or a bot wall). That does NOT disqualify them as sources and is no reason to fall back to an untrusted aggregator: cite the article from its search-result headline/snippet with the deep link (the source auditor treats a paywall response as a live link), pull the same fact from a non-paywalled Tier 1/2 outlet (Reuters wire stories are often mirrored on cnbc.com/axios.com) or the company's own IR/press page when you need the body text, and get SEC data through `agents/data_agent.py`'s helpers (`get_xbrl_facts`, `latest_filings` — they call the EDGAR JSON APIs with the SEC-required User-Agent; set `SEC_USER_AGENT` in `.env` to put your own contact on the requests) instead of scraping sec.gov HTML. Never substitute a remembered number because the page body wouldn't load.

**Step 2 - Wave 2: synthesize**
Read all 4 JSON files and produce a `brief` object with: `runDate`, `businessOverview`, `productModel`, `recentNews` (date, headline, whyItMatters, source, sourceUrl), `earningsTakeaways` (quarter, reportDate, keyMetrics, aiCommentary, demandCommentary, **`sources`**), `keyRisks` (a list of `"Label: detail"` strings — flatten, don't emit `{risk, detail}` objects), `comps` (name, ticker, evRevenue, revenueGrowth, note - **multiples MUST come from the Data Agent's live `data.json`, never from memory**; the deliverable agent re-pulls them live at render time), `revenueHistory`, `swot`, `slideBullets` (5), `diligenceQuestions` (3).

**Revenue on both a quarterly and annual basis (`brief.revenueHistory`).** Populate `revenueHistory` as a list of **annual** revenue points — `{year, value, label, source}`, `value` in $B (e.g. `{"year": "FY2026", "value": 41.45, "label": "$41.5B", "source": …}`) — with 3–4 fiscal years plus an `LTM` point. This drives the **annual revenue bar chart**. Separately, the deliverable agent pulls the **last ~5 quarters live from yfinance** at render time for the **quarterly revenue chart + table** (public tickers only — private cos show annual only). So every public brief shows revenue on both a quarterly *and* an annual basis with no manual quarterly entry; just make sure `revenueHistory` is present so the annual chart renders. **For US filers, source the annual points from `data.json`'s `secFacts` (SEC XBRL as-reported figures pulled by `data_agent.get_xbrl_facts`) rather than Yahoo aggregates** — they are the company's own filed numbers and the highest-trust cite (source: "SEC EDGAR (as reported)").

**Street & balance-sheet context renders automatically (public tickers).** The brief adds a live context strip under the hero: analyst consensus target/upside/rating count, forward P/E, the 52-week EV/Rev band (price effect only — labeled), short interest % of float, net cash/(debt), SBC as % of LTM revenue, and 1M/YTD/1Y performance vs QQQ in percentage-point spreads. All of it comes from the same render-time pulls (`live_quote`, `sbc_pct_revenue`, `relative_performance`) — never write these into `keyMetrics` by hand.

**SWOT analysis (`brief.swot`, renders next to the comps table).** A detailed 2×2 that shows how the target stands out from the comp set, not a word cloud. Shape: `{standoutSummary, strengths, weaknesses, opportunities, threats, sources}`. `standoutSummary` is a one-line "how this name is different vs peers" thesis. Each of `strengths`/`weaknesses`/`opportunities`/`threats` is a list whose items are either `"Label: detail"` strings or `{point, detail}` objects (the brief bolds the label/point and renders the detail). Anchor each point in specifics surfaced by the comps and differentiation work, e.g. trading multiple vs peers, margin/FCF profile, moat, scale, concentration. `swot.sources` is a list of `{name, url}`.

**Gartner Magic Quadrant (`profile.gartnerMap`, optional — include when one exists).** If the company is placed in a current Gartner Magic Quadrant for its category, save the quadrant image into the run folder (e.g. `runs/YYYY-MM-DD/gartner_mq.png`) and set `profile["gartnerMap"] = {imageUrl, title, asOf, caption, source: "Gartner", sourceUrl}`. `imageUrl` is a path relative to the run folder (or a remote URL); the deliverable agent inlines it as a data URI so the HTML/PDF stay self-contained. Omit the field entirely if no current MQ covers the company — never fabricate a placement.

**Sourcing the synthesized sections (so every fact is attributable):** also populate `businessOverviewSources`, `productModelSources`, `keyRisksSources`, and `earningsTakeaways.sources` — each a list of `{name, url}` pointing to the primary documents the section draws on (the earnings release, the 10-K/10-Q/8-K on SEC EDGAR, the IR page, or the Tier 1/2 article). The brief renders these as a "Sources:" row under each section, and the source auditor in Step 4 flags any section that ships without one.

**Required: the 3-level explainer (non-negotiable on every brief).** Always produce a top-level `explainer` object (a sibling of `brief`, not inside it) with three keys, each a short list of bullets (or a short paragraph): `plain` ("Plain English" — what the business does for a normal reader), `technical` ("The technical version" — the precise mechanism/architecture/financial model in industry terms), and `simple` ("Explained simply" — an ELI5/analogy a non-expert instantly gets). These render as the three explainer cards at the top of the Business Overview and are the reader's entry point. **All three are mandatory** — the QA pass in Step 4 raises a BLOCKING error if the `explainer` block is missing or any level is empty.

**Explainer bullets must SCAN (this block is the product's differentiator).** Write each level as a list of 3-4 bullets, **one idea per bullet, ≤ ~20 words each** — a 40-word bullet is a paragraph wearing a bullet costume, and the QA pass warns on any bullet over ~220 characters (the renderer also caps display at 5 per card). The brief opens the block with an "In one sentence" lede pulled from `shortDescription` (falling back to the first `simple` bullet), so make `shortDescription` a sentence a reader could repeat at dinner.

**"What matters" band (`brief.whatMatters`, optional but encouraged).** The first thing an MD reads, rendered directly under the nav: `{thesis, debate, catalyst}` — `thesis` is the one-sentence call ("why this name, why now"), `debate` the live controversy a reader must have a view on, `catalyst` the next dated event. When absent, the renderer composes it from what's already sourced: `swot.standoutSummary` (thesis), the first `keyRisks` item (debate), and the live next-earnings date from yfinance or a stated guidance metric (catalyst). Write the explicit object when the composed default wouldn't be the call you'd actually make.

**Decode the jargon — `explainer.glossary` (include it whenever the product is acronym/jargon-heavy).** The whole point of the explainer is that a reader who isn't a domain expert can understand what the company actually does. When the business is built on specialized terms an average reader (or a generalist MD) won't know on sight — e.g. Netskope's **SSE** and **SASE**, or **CASB / ZTNA / DLP**, semis terms like **EUV / HBM / chiplet**, infra terms like **eBPF / Kubernetes operator** — you MUST add a `glossary` so those terms are spelled out, not assumed. Set `explainer.glossary` to a list of `{term, expansion, definition}` objects: `term` is the acronym/word (e.g. `"SASE"`), `expansion` is what it stands for (e.g. `"Secure Access Service Edge"`, omit if it isn't an acronym), and `definition` is a one-sentence plain-English explanation a non-expert instantly gets (e.g. `"Bundling networking and security into one cloud service, so remote staff connect safely without routing traffic back to a corporate data center."`). It renders as a "Key terms, decoded" block directly under the three cards. **Be smart about when this is needed:** include it for cybersecurity / cloud / infra / semis / deep-tech names that lean on insider acronyms; skip it for self-explanatory businesses (a payments app, a retailer) where no decoding is needed — an empty glossary is fine there. The Step 4 QA prints an advisory `🔗`-style warning (non-blocking) if the explainer uses several specialized acronyms with no glossary and none expanded inline, as a reminder to decode them.

**Period + consistency (per the Metric Clarity & Consistency Mandate):** always set `earningsTakeaways.quarter` (e.g. `"Q1 FY2027 (ended April 30, 2026)"`) and `reportDate` — they anchor the whole metrics grid. Give every `keyMetrics` value its own window when it differs from that default: `"68.1% (LTM)"`, `"118% (as of July 31, 2025)"`, `"Revenue $90.5-91.0M (FY2026 guidance)"`. Make sure each figure ties to itself everywhere it appears (metrics grid, `revenueHistory`, comp row, slide bullets, prose) — when two numbers differ it must be because the period or basis differs, and that difference must be labeled, not silent. Never let a quarterly revenue/EBITDA/FCF figure equal the annual one. The metric auditor in Step 4 blocks on contradictions.

**Step 3 - Write profile.json**
Write/overwrite `data-dumps/FOLDER_ID/profile.json` with ALL fields including the `brief` object **and the required top-level `explainer` block** (`plain` / `technical` / `simple`). profile.json is the single source of truth - the coverage site reads it.

**Step 4 - Generate the brief (HTML + PDF)**
Run `python3 agents/deliverable_agent.py FOLDER_ID`. This writes a self-contained HTML brief and a print-faithful PDF (rendered via your local headless Chrome) to the run folder. **No email is sent - the deliverables are the files.** Report the local paths.

It also runs three QA passes and prints a report: a layout/overflow check; a **source-integrity audit** (`agents/source_audit.py`) that live-checks every link, flags untrusted/Tier-3 domains and shallow homepage links, and lists any section shipping without a source; and a **metric consistency & clarity audit** (`agents/metric_audit.py`) that cross-checks every dollar figure, flags any metric that doesn't tie to itself across sections, catches quarterly-equals-annual collisions, and flags undated headline figures. The completeness check also raises a **BLOCKING error if the required `explainer` block (plain / technical / simple) is missing or incomplete**, and a metric **contradiction always blocks** (a number that doesn't tie is a factual defect). `--strict` additionally makes source + metric + completeness *warnings* blocking (the brief is still written; a non-zero exit means "review before shipping"). Always read the `🔗 QA sources` and `🧮 QA metrics` lines and fix broken/untrusted/missing sources and any number that doesn't tie before treating a brief as client-ready.

**Notion mirror runs automatically.** At the end of every brief generation, `deliverable_agent.py` calls `agents/notion_sync.py` to upsert this company's row into the Notion coverage DB. It's a silent no-op unless `NOTION_TOKEN` + `NOTION_DB_ID` are set in `.env`, and it never fails the brief (a Notion error prints a `⚠️` and is swallowed). No manual step is needed — see "Mirroring coverage to Notion" below for the column setup. The brief link in the row resolves once Step 5 deploys the run to the web.

**Notion mirror via MCP (mandatory — the primary path in cloud/phone sessions).** The token-based `notion_sync.py` above is a no-op whenever `NOTION_TOKEN`/`NOTION_DB_ID` are unset, which is the *usual* case in a cloud sandbox — so the row silently never gets written. Therefore: **in any session where a Notion MCP is connected, you (Claude) MUST upsert this company's row into the `atlas tracker` database yourself via the Notion MCP at the end of every run** — do not skip it and do not assume the token sync covered it. This is part of the standard pipeline, not an optional extra. Procedure:
  1. **Upsert, never duplicate.** Search the database for an existing row whose **Company Name** matches; if one exists, update it in place, otherwise create a new page. One row per company.
  2. **Target.** Database "🚀 atlas tracker", data source `c2b483d1-4dd7-41df-a6f8-42475576b9ff`. Schema: `Company Name` (title), `Description` (text), `Stage` (select: `Public`/`Seed`/`Series A`), `Valuation` (text), `Last Updated` (date), `report` (url). Match by property name to whatever the live schema shows — re-fetch the data source first if unsure, since columns can change.
  3. **Field mapping (all from the live run, never memory):** `Description` = the profile's one-line `shortDescription` (prefix `• `, match the existing rows' style); `Stage` = `Public` for listed names, else the latest round; `Valuation` = a live snapshot line from the Data Agent pull (market cap + EV + EV/Rev LTM + forward P/E + beta + 52-wk range + analyst consensus/target, e.g. the format used in the existing Micron row); `Last Updated` = the run date; `report` = `https://atlas-private.vercel.app/full/briefs/<FOLDER_ID>/<run-date>.html` (the same URL convention the other rows use).
  4. **Confirm it landed** and report the row URL in your run summary. If no Notion MCP is connected *and* no token creds are set, say so plainly in the summary rather than leaving the omission silent.

**Step 5 - Ship to `main` (standing instruction).** Atlas runs should land on `main`, not sit in a draft. After the brief is generated and QA is clean: commit the run on the working branch, push it, and open the PR **ready-for-review (NOT a draft)** so the repo's auto-merge workflow can take it in. If auto-merge does not merge it (e.g. it's disabled or the PR stays open) and `mergeable_state` is `clean`, **merge it into `main` yourself** (squash). Only hold off and ask first if QA is blocking/unresolved, there's a merge conflict, or the diff touches code/config beyond `data-dumps/` (a brief that's just a new `data-dumps/<ID>/` run is safe to land automatically). This overrides the default "open as draft and wait" behavior for Atlas research runs.

---

## What NOT to Build Yet
- Full operating models / valuation models
- Autonomous decision-making
- Fully automated comp sheet population (always needs review)
- Client-ready outputs without human sign-off

---

## Files

| File | Purpose |
|---|---|
| `.claude/settings.json` | Project-level Claude Code config — registers the `ramp-data` MCP server (HTTP transport). |
| `agents/data_agent.py` | Live trading data via yfinance (no key) + FMP (free key) + Ramp demand signals (MCP, no key). Run: `python3 agents/data_agent.py TICKER [COMP1 COMP2]` |
| `agents/research_agent.py` | Prompt templates for public and private company research. |
| `agents/deliverable_agent.py` | Generates a self-contained HTML brief (+ PDF) from profile.json, with a period tag on every metric card. Run: `python3 agents/deliverable_agent.py TICKER [--detailed]` |
| `agents/source_audit.py` | Source-integrity QA: live link check + trust tier + shallow-link + coverage. Prints the `🔗 QA sources` line. |
| `agents/metric_audit.py` | Metric consistency & clarity QA: cross-checks every $ figure ties, catches quarter-equals-annual collisions, flags undated headline figures. Prints the `🧮 QA metrics` line. Run standalone: `python3 agents/metric_audit.py TICKER`. |
| `agents/sources.py` | Canonical trusted-source registry (Tier 1/2 publications + curated X accounts). |
| `site/build.mjs` | Builds the static coverage site from `data-dumps/`. Run: `node site/build.mjs`. Choose public-demo companies via `DEMO_IDS` at the top. |
| `agents/notion_sync.py` | Mirror a run into a Notion database — upserts one row per company (description, competitors, founders, public/private, stage/series, revenue, valuation) with a link back to the published brief. **Runs automatically at the end of `deliverable_agent.py`** (no-op unless creds are set). Standalone: `python3 agents/notion_sync.py FOLDER_ID [--body] [--dry-run]`. Needs `NOTION_TOKEN`, `NOTION_DB_ID`, `ATLAS_SITE_URL` in `.env`; see "Mirroring coverage to Notion" below. |

---

## Environment Setup

```bash
pip3 install -r requirements.txt   # yfinance + requests (same as: pip3 install yfinance requests)

# Optional: free FMP key for live comps (yfinance works without one)
cp .env.example .env          # then add FMP_API_KEY=...
```

PDF rendering uses your local Google Chrome / Chromium - no install or credentials needed.

---

## Running Atlas in a cloud / mobile session (self-bootstrap)

A cloud sandbox (the Claude app on a phone, or any web/headless session) starts **without the
Python deps, without a local Chrome, and without the `ramp-data` MCP connected** — and the
`atlas-research` plugin that defines the `/atlas` slash command is usually **not loaded** there. So a
cloud run must bootstrap itself instead of assuming the local setup. When you (Claude) detect you are
running a research request in an environment where `import yfinance` fails or `/atlas` is unavailable,
do the following automatically — do not make the user issue extra commands:

1. **Trigger by company name, not the slash command.** The plugin may be absent, but this `CLAUDE.md`
   loads from the repo, so a bare company name (e.g. "Snowflake") already invokes the Execution
   Protocol above. Treat it as a run request exactly as on desktop.
2. **Install deps first.** Run `pip3 install -r requirements.txt` (falls back to
   `pip3 install yfinance requests`) before the Data Agent step. If outbound network is blocked and
   the install fails, say so plainly and stop — do **not** fall back to remembered numbers (that
   violates the Data Freshness Mandate).
3. **PDF is optional, HTML is the deliverable.** `deliverable_agent.py` already searches for
   Playwright's headless Chromium and, finding no browser, prints `⚠️ No Chrome … HTML only` and
   continues. A cloud run is expected to produce the self-contained **HTML** brief; don't treat a
   missing PDF as a failure.
4. **Skip Ramp demand signals gracefully.** The `ramp-data:*` MCP tools won't be connected in cloud.
   Omit `rampDemandSignal` rather than blocking the run — every other section still renders.
5. **Mirror to Notion via the MCP yourself.** In cloud, `notion_sync.py` almost always no-ops (no
   token), so the row is *not* written automatically. The Notion MCP, however, is typically connected
   — so upsert the company's row into the `atlas tracker` DB through the MCP as described in "Notion
   mirror via MCP" under Step 4. This is required, not optional; confirm the row and report its URL.
6. **Ship so it's readable on the phone.** Follow Step 5 (commit → push → land on `main` → deploy).
   The cleanest way to *read* the brief on a phone is the deployed coverage site, not a local file in
   the sandbox.

---

## Deploying the coverage site (Vercel)

`site/build.mjs` builds the site into `site/dist/` - a **public demo** at `/` (the companies in
`DEMO_IDS`) and your **full coverage** at `/full`, gated by the `SITE_PASSWORD` env var via
`middleware.js`. To deploy: import this repo into Vercel, **leave the Root Directory at the repo
root**, Framework = Other (build command + output come from `vercel.json`). Add `SITE_PASSWORD` to
gate `/full`. HTTPS + security headers are configured out of the box.

---

## Mirroring coverage to Notion (optional)

`agents/notion_sync.py` pushes a finished run into a Notion database so a team can browse coverage
from Notion, each row linking back to the brief on the coverage site. It's optional and additive —
nothing else depends on it. One row per company, **upserted** on the company name, so re-running a
name updates its row instead of duplicating it. Columns are matched by name (case-insensitive) and
formatted to the column's real type, so it adapts to whatever the database already has. When present
it fills these columns (aliases in parentheses):

| Column | Filled with |
|---|---|
| `Company Name` (title) | Company name |
| `Description` | One-line business summary (`shortDescription`) |
| `Competitors` · `Founders` · `Ticker` · `Website` | From the profile |
| `Type` (`Public/Private`, `Ownership`) | `Public` / `Private` |
| `Stage` (`Series`, `Series/IPO`, `Round`) | `Public` for listed names, else the latest round (`Seed`, `Series A`, …) |
| `Revenue` (`LTM Revenue`) | LTM revenue for public; latest reported figure for private (blank if undisclosed) |
| `Valuation` (`Market Cap`, `Last Valuation`) | Market cap for public; last reported post-money for private (blank if undisclosed) |
| `Brief`/`Atlas`/`Report`/`Link` (any URL column) | Link to the published brief |
| `Last Updated` (date) | Run date |

Undisclosed private revenue/valuation is left blank, never guessed. Keep `Revenue`/`Valuation` as
**text** and `Type`/`Stage` as text or **select** — a number-typed column can't hold "$42.8B" and is skipped.

One-time setup:
1. Create an internal integration at notion.so/my-integrations, copy its secret into `.env` as `NOTION_TOKEN`.
2. In the database, ••• → Connections → add the integration (gives it read/write).
3. Add the columns you want from the table above — at minimum a **URL** column for the link, plus
   `Type`, `Stage`, `Revenue`, `Valuation` (text/select) and a `Last Updated` date column.
4. Put the database id (the 32-char hash in its URL) in `.env` as `NOTION_DB_ID`, and set
   `ATLAS_SITE_URL` to your deployed site so links resolve.

**This is automatic.** `deliverable_agent.py` (Step 4) calls the sync at the end of every run, so
once `NOTION_TOKEN` + `NOTION_DB_ID` are in `.env` every brief mirrors itself with no extra step. To
run it standalone (e.g. backfill, or preview): `python3 agents/notion_sync.py FOLDER_ID` (add `--body`
to also write a summary into the new page, `--dry-run` to preview the payload without a token).

---

## Private Company Research Strategy

When the company is PRIVATE, the Research Agent uses this source priority:
1. Crunchbase - funding rounds, investors, valuation
2. TechCrunch / Bloomberg / WSJ - funding announcements
3. PitchBook excerpts indexed in search
4. SEC Form D filings - legally required private placement disclosures
5. X (Twitter) - company official account + founder posts about milestones
6. LinkedIn - employee count trend as a growth-stage proxy

Output includes: all funding rounds with sources, lead investors, last known valuation with date and source, IPO readiness assessment.
