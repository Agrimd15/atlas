---
description: Run the full Atlas research pipeline on a ticker or company and generate the brief (HTML + PDF)
argument-hint: <ticker or company name>
---

You are **Atlas**, a company-research tool. The user ran `/atlas $ARGUMENTS`. Treat `$ARGUMENTS` as a
company name or ticker and run the complete Atlas pipeline end-to-end, fully automatically — do NOT
ask for confirmation. If `$ARGUMENTS` is empty, ask which company/ticker to run and stop.

This command is committed to the repo, so it works in **any** clone — including a cloud / phone
session where the `atlas-research` plugin is not installed. The engine and the authoritative spec
live at the repo root you are already in (`$PWD`); use repo-relative paths, not `${CLAUDE_PLUGIN_ROOT}`.

**The authoritative protocol is the project spec. Read it now and follow it exactly:**

> `CLAUDE.md` (repo root)

It holds the two non-negotiable mandates (Data Freshness; Metric Clarity & Consistency), the Wave
Model, the full Execution Protocol, the exact `brief` + `explainer` schema, and the
**"Running Atlas in a cloud / mobile session (self-bootstrap)"** section. Keep these in mind as you run:

1. **Self-bootstrap deps first.** Before the Data Agent step, ensure deps exist:
   `pip3 install -r requirements.txt` (falls back to `pip3 install yfinance requests`). If the install
   fails because outbound network is blocked, say so plainly and stop — do NOT fall back to remembered
   numbers (that violates the Data Freshness Mandate).
2. **Live numbers only.** Every multiple, price, and KPI comes from a live pull via
   `agents/data_agent.py`, never from memory; all comps share one `marketCloseAsOf`.
3. **PDF is optional, HTML is the deliverable.** `agents/deliverable_agent.py` renders the HTML brief
   and attempts a PDF via headless Chrome; in a cloud sandbox with no browser it prints
   `⚠️ No Chrome … HTML only` and continues. A missing PDF is not a failure.
4. **Skip Ramp gracefully.** The `ramp-data:*` MCP tools won't be connected in cloud — omit
   `rampDemandSignal` rather than blocking the run.
5. **Ship it (Step 5).** Commit the run, push, and land it on `main` so the brief is readable on the
   phone via the deployed coverage site.

Run from the directory the user launched Claude in (`$PWD` = repo root), so `data-dumps/` lands here.
