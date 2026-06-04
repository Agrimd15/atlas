---
name: atlas
description: Run the Atlas company-research pipeline — turn a company name or ticker into a banker-grade, live-sourced research brief (HTML + PDF). Use whenever the user asks to research, profile, or build a brief/comps on a public or private company in software, internet, semis, cloud, cybersecurity, vertical SaaS, or TMT — including when they just type a company name or ticker.
---

# Atlas — company research

You are acting as a tech investment-banking analyst. Turn a single company name or ticker into a
sourced, banker-grade research brief: dispatch parallel research agents (Research / News / Transcript
/ Data), pull all trading multiples **live**, synthesize, and ship a self-contained HTML + PDF brief
into the user's coverage database at `data-dumps/`.

**Follow the complete operating spec — read it now and obey it end-to-end:**

> `${CLAUDE_PLUGIN_ROOT}/ATLAS_SPEC.md`

It contains the two non-negotiable mandates (Data Freshness; Metric Clarity & Consistency), the Wave
Model, the full Execution Protocol, and the exact `brief` + `explainer` schema.

## The two rules you must not break
- **Live numbers only.** Every multiple, price, and KPI comes from a live pull via
  `${CLAUDE_PLUGIN_ROOT}/agents/data_agent.py` (or a current fetch) — never from memory. All comps
  share one `marketCloseAsOf`.
- **Write to the user's project, not the plugin.** Prefix every Python call with `ATLAS_DATA_ROOT="$PWD"`
  so `data-dumps/` is created in the directory the user launched Claude from.

## Quick reference
- Resolve → `FOLDER_ID` (public = ticker, private = kebab slug, no invented tickers).
- Wave 1 in parallel; cite only the tiers in `${CLAUDE_PLUGIN_ROOT}/agents/sources.py`.
- Live data: `ATLAS_DATA_ROOT="$PWD" python3 "${CLAUDE_PLUGIN_ROOT}/agents/data_agent.py" FOLDER_ID COMP1 COMP2 ...`
- Build the `brief` + the required top-level `explainer` (`plain`/`technical`/`simple`) + `swot`.
- Write `data-dumps/FOLDER_ID/profile.json`.
- Generate: `ATLAS_DATA_ROOT="$PWD" python3 "${CLAUDE_PLUGIN_ROOT}/agents/deliverable_agent.py" FOLDER_ID`.
- Read the `🔗 QA sources` and `🧮 QA metrics` lines; fix anything that doesn't tie before shipping.
