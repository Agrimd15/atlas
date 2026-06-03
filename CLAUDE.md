# Atlas - Company Research Tool

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
  /agents                  ← data_agent.py, research_agent.py, deliverable_agent.py, sources.py
  /prompts                 ← prompt templates per agent
  /design                  ← DESIGN.md (design language - all UI complies)
  /site                    ← static coverage site (build.mjs, template/, dist/)
  vercel.json · package.json · middleware.js   ← deploy config + password gate
  /viewer                  ← optional local viewer (atlas.html + FastAPI backend)
  /data-dumps              ← the coverage database (one folder per company)
    /SNOW/
      profile.json         ← latest run (the viewer reads this)
      /runs/2026-05-31/
        research.json · news.json · transcript.json · data.json
        SNOW_brief_2026-05-31.html (+ .pdf)
```

This repo IS the database. Git history shows how each company's profile evolved over time. The
viewer (`atlas.html` / the published site) is just the lens. This public repo ships only the demo
companies; companies you research are gitignored by default (see `.gitignore`).

---

## Data Convention
- `profile.json` - always reflects the latest research run. The viewer reads this.
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
- **Data Agent** - `"[Company]" ARR NRR revenue growth gross margin KPIs 2024 2025 (site:sacra.com OR site:meritech.com OR site:bvp.com OR site:wsj.com)` - and use `agents/data_agent.py` for live public trading data.

Each agent returns a structured JSON summary saved to the run folder. **Every news item, quote, and metric must include a `source` (publication) and `sourceUrl` (direct URL).** Items without sources are invalid.

**Step 2 - Wave 2: synthesize**
Read all 4 JSON files and produce a `brief` object with: `runDate`, `businessOverview`, `productModel`, `recentNews` (date, headline, whyItMatters), `earningsTakeaways` (quarter, reportDate, keyMetrics, aiCommentary, demandCommentary), `keyRisks`, `comps` (name, ticker, evRevenue, revenueGrowth, note - **multiples MUST come from the Data Agent's live `data.json`, never from memory**; the deliverable agent re-pulls them live at render time), `slideBullets` (5), `diligenceQuestions` (3).

**Step 3 - Write profile.json**
Write/overwrite `data-dumps/FOLDER_ID/profile.json` with ALL fields including the `brief` object. profile.json is the single source of truth - the viewer reads it.

**Step 4 - Generate the brief (HTML + PDF)**
Run `python3 agents/deliverable_agent.py FOLDER_ID`. This writes a self-contained HTML brief and a print-faithful PDF (rendered via your local headless Chrome) to the run folder. **No email is sent - the deliverables are the files.** Report the local paths.

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
| `agents/data_agent.py` | Live trading data via yfinance (no key) + FMP (free key). Run: `python3 agents/data_agent.py TICKER [COMP1 COMP2]` |
| `agents/research_agent.py` | Prompt templates for public and private company research. |
| `agents/deliverable_agent.py` | Generates a self-contained HTML brief (+ PDF) from profile.json. Run: `python3 agents/deliverable_agent.py TICKER [--detailed]` |
| `agents/sources.py` | Canonical trusted-source registry (Tier 1/2 publications + curated X accounts). |
| `site/build.mjs` | Builds the static coverage site from `data-dumps/`. Run: `node site/build.mjs`. Choose public-demo companies via `DEMO_IDS` at the top. |
| `viewer/` | Optional local viewer: a single-file browser app (`atlas.html`) + a small FastAPI backend. Run: `viewer/start.sh`. |

---

## Environment Setup

```bash
pip3 install yfinance requests

# Optional: free FMP key for live comps (yfinance works without one)
cp .env.example .env          # then add FMP_API_KEY=...
```

PDF rendering uses your local Google Chrome / Chromium - no install or credentials needed.

---

## Deploying the coverage site (Vercel)

`site/build.mjs` builds the site into `site/dist/` - a **public demo** at `/` (the companies in
`DEMO_IDS`) and your **full coverage** at `/full`, gated by the `SITE_PASSWORD` env var via
`middleware.js`. To deploy: import this repo into Vercel, **leave the Root Directory at the repo
root**, Framework = Other (build command + output come from `vercel.json`). Add `SITE_PASSWORD` to
gate `/full`. HTTPS + security headers are configured out of the box.

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
