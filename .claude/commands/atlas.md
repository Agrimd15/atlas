---
description: Run the full Atlas research pipeline on a ticker or company and generate the brief (HTML + PDF)
argument-hint: <ticker or company name>
---

You are running **Atlas**, a company-research tool. The user ran `/atlas $ARGUMENTS`. Treat
`$ARGUMENTS` as a company name or ticker and run the **complete Execution Protocol from `CLAUDE.md`**
end-to-end, fully automatically - do NOT ask for confirmation.

If `$ARGUMENTS` is empty, ask which company/ticker to run and stop.

## Step 0 - Resolve
- Identify the canonical company and whether it is **PUBLIC** or **PRIVATE**.
- Public → use the exchange ticker as `FOLDER_ID` (Snowflake → `SNOW`).
- Private → lowercase kebab-case slug, **no invented ticker** (Databricks → `databricks`).
- Determine today's date (YYYY-MM-DD). Create `data-dumps/FOLDER_ID/runs/YYYY-MM-DD/`.

## Step 1 - Wave 1 (run in parallel)
Dispatch the 4 Wave-1 agents simultaneously (Research, News, Transcript, Data). Each MUST restrict
citations to the tiers in `agents/sources.py` and attach `source` + `sourceUrl` to every item.

**Data Freshness Mandate (non-negotiable - see CLAUDE.md):**
- Pull ALL trading multiples, prices, market caps, growth, and margins LIVE via
  `python3 agents/data_agent.py FOLDER_ID COMP1 COMP2 ...` - pass the comp tickers so every comp
  shares ONE `marketCloseAsOf` anchor. NEVER write a multiple from memory.
- Surface the `marketCloseAsOf` / `freshnessNote` it returns; flag any lagging ticker.

## Step 2 - Wave 2 synthesis
Read all 4 JSON files and build the `brief` object (keys defined in CLAUDE.md). The `comps` multiples
must come only from the live `data.json` pull - the deliverable agent re-pulls them at render time.

## Step 3 - Write profile.json
Write/overwrite `data-dumps/FOLDER_ID/profile.json` with all fields including the full `brief`.

## Step 4 - Generate the brief (HTML + PDF)
Run `python3 agents/deliverable_agent.py FOLDER_ID` - writes a self-contained HTML brief AND a
print-faithful PDF (headless Chrome) to `data-dumps/FOLDER_ID/runs/YYYY-MM-DD/`. No email is sent.

## Step 5 - Report back
Confirm `FOLDER_ID`, public/private, the run date, the `marketCloseAsOf` date all multiples reflect
(or note a private co with no market close), and the local **PDF + HTML paths**.
