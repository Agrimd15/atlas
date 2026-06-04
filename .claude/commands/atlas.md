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
**Also build the REQUIRED top-level `explainer` block** (a sibling of `brief`) with all three levels —
`plain` (Plain English), `technical` (The technical version), and `simple` (Explained simply). These
render as the three explainer cards atop the Business Overview; the Step 4 QA raises a BLOCKING error
if `explainer` is missing or any level is empty.

**SWOT (required, sits next to the comps table).** Build `brief.swot` to show how the target stands
out from the comp set: `standoutSummary` (one-line thesis vs peers), plus `strengths`, `weaknesses`,
`opportunities`, `threats` - each a list of detailed items (use `"Label: detail"` strings or
`{point, detail}` objects). Tie strengths/weaknesses to specifics from the comps and differentiation
work (multiples, margins, moat, scale), not generic adjectives. Add `swot.sources` ({name, url}).

**Gartner Magic Quadrant (include if one exists).** If the company appears in a current Gartner Magic
Quadrant for its category, save the quadrant image into the run folder as
`data-dumps/FOLDER_ID/runs/YYYY-MM-DD/gartner_mq.png` and set `profile["gartnerMap"]` =
`{imageUrl: "gartner_mq.png", title, asOf, caption, source: "Gartner", sourceUrl}`. The deliverable
agent inlines the image (data URI) so the HTML/PDF stay self-contained. `imageUrl` may also be a
remote URL. Skip silently if no current MQ covers the company.

## Step 3 - Write profile.json
Write/overwrite `data-dumps/FOLDER_ID/profile.json` with all fields including the full `brief` and the
required top-level `explainer` block (`plain` / `technical` / `simple`).

## Step 4 - Generate the brief (HTML + PDF)
Run `python3 agents/deliverable_agent.py FOLDER_ID` - writes a self-contained HTML brief AND a
print-faithful PDF (headless Chrome) to `data-dumps/FOLDER_ID/runs/YYYY-MM-DD/`. No email is sent.

## Step 5 - Report back
Confirm `FOLDER_ID`, public/private, the run date, the `marketCloseAsOf` date all multiples reflect
(or note a private co with no market close), and the local **PDF + HTML paths**.
