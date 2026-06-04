# Atlas (atlas-research plugin)

Banker-grade company research for Claude Code. Turn a single company name or ticker into a sourced,
**live-data** research brief (HTML + PDF) — the first tool in the **Alfred** analyst toolkit.

> Atlas dispatches four parallel research agents (Research · News · Transcript · Data), pulls every
> trading multiple live so all comps share one market close, synthesizes a banker-style brief with a
> SWOT, comps, a 3-level explainer, and 5 slide-ready bullets, and renders it to self-contained HTML +
> PDF — with source-integrity and metric-consistency QA on every run.

## Install

```
/plugin marketplace add Agrimd15/alfred-tools
/plugin install atlas-research@alfred-tools
```

Then research anything:

```
/atlas SNOW
/atlas Databricks
```

Or run `/atlas-research:setup` for a guided walkthrough.

## Prerequisites

The plugin ships files, not a runtime. You need, locally:

- **Python 3.9+** — the research engine. `yfinance` + `requests` are auto-installed by the plugin's
  SessionStart hook (or `pip3 install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`).
- **Google Chrome / Chromium** — used to render the PDF. Without it the **HTML** brief still renders;
  only the PDF step fails.
- **(optional)** a free [FMP](https://financialmodelingprep.com) API key for live comps — export
  `FMP_API_KEY=...`. yfinance works with no key. The bundled `ramp-data` MCP (B2B demand signals)
  needs no key.

## Where your briefs go

Atlas writes its coverage database to **`data-dumps/` in the directory you launched Claude from** —
your project, not the read-only plugin install. Each run writes:

```
data-dumps/<FOLDER_ID>/
  profile.json                       ← latest run (source of truth)
  runs/YYYY-MM-DD/
    research.json · news.json · transcript.json · data.json
    <FOLDER_ID>_brief_YYYY-MM-DD.html (+ .pdf)
```

Make that directory a git repo and your git history becomes the coverage database over time.

## What's bundled

| Piece | What it is |
|---|---|
| `/atlas`, `/setup` commands | The research pipeline + guided onboarding |
| `skills/atlas` | Auto-triggers the pipeline when you name a company |
| `agents/*.py` | The engine: live data, deliverable rendering, source + metric QA |
| `.mcp.json` (`ramp-data`) | B2B demand signals (HTTP MCP, no key) |
| `hooks/hooks.json` | Auto-installs the Python deps on session start |
| `ATLAS_SPEC.md` | The authoritative operating protocol the commands follow |

## Out of scope (clone-based, not in the plugin)

Publishing a **coverage website** (the Vercel dashboard + password gate) and the auto-merge workflow
assume the repo-as-database model. They ship in the full
[alfred-tools](https://github.com/Agrimd15/alfred-tools) repo, not in this plugin. The plugin is the
research **engine**; you supply the database.

## Reminder

Public info only. Every output is **DRAFT** until a human reviews it.
