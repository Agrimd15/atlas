---
description: Run the full Atlas research pipeline on a ticker or company and generate the brief (HTML + PDF)
argument-hint: <ticker or company name>
---

You are running **Atlas**, a company-research tool installed as a Claude Code plugin. The user ran
`/atlas $ARGUMENTS`. Treat `$ARGUMENTS` as a company name or ticker and run the **complete Atlas
Execution Protocol** end-to-end, fully automatically — do NOT ask for confirmation.

If `$ARGUMENTS` is empty, ask which company/ticker to run and stop.

**Read the operating spec first.** The full protocol, the non-negotiable mandates (Data Freshness,
Metric Clarity & Consistency), and the exact `brief` / `explainer` schema live in the bundled spec.
Read it now and follow it exactly:

> `${CLAUDE_PLUGIN_ROOT}/ATLAS_SPEC.md`

## Runtime rules for the plugin (these differ from a cloned repo)

- **The plugin code is read-only.** Bundled Python agents live under `${CLAUDE_PLUGIN_ROOT}/agents/`.
  Always invoke them by that absolute path, e.g.
  `python3 "${CLAUDE_PLUGIN_ROOT}/agents/deliverable_agent.py" FOLDER_ID`.
- **Output goes to the user's project, not the plugin.** The coverage database is written to
  `data-dumps/` in the directory the user launched Claude from. The agents honour the
  `ATLAS_DATA_ROOT` env var for this — **set it to the current working directory on every Python
  call**:
  `ATLAS_DATA_ROOT="$PWD" python3 "${CLAUDE_PLUGIN_ROOT}/agents/data_agent.py" FOLDER_ID COMP1 COMP2 ...`
  So `data-dumps/FOLDER_ID/...` is created in the user's project, and `profile.json` + the dated
  `runs/` folder land there.

## The loop (full detail in ATLAS_SPEC.md)

1. **Resolve** — canonical name; PUBLIC → exchange ticker as `FOLDER_ID`, PRIVATE → kebab-case slug
   (no invented ticker). Today's date (YYYY-MM-DD). Create `data-dumps/FOLDER_ID/runs/YYYY-MM-DD/`.
2. **Wave 1 (parallel)** — Research, News, Transcript, Data agents. Citations restricted to the tiers
   in `${CLAUDE_PLUGIN_ROOT}/agents/sources.py`; every item carries `source` + `sourceUrl`. Pull ALL
   trading multiples/prices/margins LIVE via
   `ATLAS_DATA_ROOT="$PWD" python3 "${CLAUDE_PLUGIN_ROOT}/agents/data_agent.py" FOLDER_ID COMP1 COMP2 ...`
   (pass comp tickers so all comps share one `marketCloseAsOf`). Never write a multiple from memory.
3. **Wave 2 synthesis** — build the `brief` object, the REQUIRED top-level `explainer` block
   (`plain` / `technical` / `simple` — all three mandatory), `brief.swot`, and `profile.gartnerMap`
   if a current Gartner MQ exists. Set `earningsTakeaways.quarter` + `reportDate`; give every metric
   its period.
4. **Write** `data-dumps/FOLDER_ID/profile.json` (all fields, incl. the `explainer` block).
5. **Generate** — `ATLAS_DATA_ROOT="$PWD" python3 "${CLAUDE_PLUGIN_ROOT}/agents/deliverable_agent.py" FOLDER_ID`
   writes the self-contained HTML brief + a print-faithful PDF (headless Chrome) and runs the QA
   passes. Read the `🔗 QA sources` and `🧮 QA metrics` lines; a metric contradiction or a missing
   `explainer` block BLOCKS.
6. **Report** — confirm `FOLDER_ID`, public/private, the run date, the `marketCloseAsOf` close all
   multiples reflect (or note a private co with no market close), and the local **PDF + HTML paths**.
