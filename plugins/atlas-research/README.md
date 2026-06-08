# Atlas (atlas-research plugin)

Banker-grade company research for Claude Code. Turn a single company name or ticker into a sourced,
**live-data** research brief (HTML + PDF) — the first tool in the **Alfred** analyst toolkit. Atlas
dispatches four parallel agents (Research · News · Transcript · Data), pulls every trading multiple
live against one shared market close, synthesizes a banker-style brief (SWOT, comps, a 3-level
explainer, 5 slide bullets), and renders self-contained HTML + PDF — with source-integrity and
metric-consistency QA on every run.

## Install

```
/plugin marketplace add Agrimd15/alfred-tools
/plugin install atlas-research@alfred-tools
```

Then `/atlas SNOW` (or any name/ticker), or `/atlas-research:setup` for a guided walkthrough.

## Prerequisites

The plugin ships files, not a runtime. Locally you need:
- **Python 3.9+** — `yfinance` + `requests` auto-install via the SessionStart hook (or
  `pip3 install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`).
- **Google Chrome / Chromium** — renders the PDF; without it the HTML brief still renders.
- **(optional)** a free [FMP](https://financialmodelingprep.com) key for live comps (`FMP_API_KEY=…`);
  yfinance works with no key, and the bundled `ramp-data` MCP needs none.

## Where your briefs go

Atlas writes to `data-dumps/` **in the directory you launched Claude from** — your project, not the
read-only plugin install. Per run: `profile.json` (latest) + a dated `runs/YYYY-MM-DD/` holding the
four agent JSONs and the `<ID>_brief_<date>.html` (+ `.pdf`). Make that directory a git repo and your
history becomes the coverage database over time.

## What's bundled

`/atlas` + `/setup` commands · the `atlas` skill (auto-triggers on a company name) · `agents/*.py`
(live data, rendering, source + metric QA) · `.mcp.json` (`ramp-data`, no key) · `hooks/hooks.json`
(auto-installs deps) · **`ATLAS_SPEC.md`** (the authoritative operating protocol — the single source
of truth the commands and skill defer to).

## Out of scope

Publishing a **coverage website** (the Vercel dashboard + password gate) is the clone-based
repo-as-database model — it ships in the full [alfred-tools](https://github.com/Agrimd15/alfred-tools)
repo, not this plugin. The plugin is the research **engine**; you supply the database.

**Public info only. Every output is DRAFT until a human reviews it.**
