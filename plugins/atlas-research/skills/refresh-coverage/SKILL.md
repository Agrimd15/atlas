---
name: refresh-coverage
description: Refresh stale Atlas coverage — re-run every company whose latest brief is older than a threshold (default 1 week), updating ONLY what has changed since the last run to keep token cost low. Use whenever the user wants to update, refresh, re-run, or "freshen up" old briefs/coverage/runs — e.g. "update everything older than a week", "refresh my stale reports", "re-run the briefs that have gone out of date", "keep coverage current", or when they ask to bring a backlog of aging company briefs up to date. Triggers on staleness/freshness/"out of date"/"week old" phrasing even if they don't name a specific company.
---

# Refresh stale coverage

Re-running a whole Atlas brief from scratch every week is wasteful: a company's
business overview, SWOT, explainer, and product model barely move week-to-week,
while its **trading multiples move every day** and a **new headline or earnings
filing** appears only occasionally. This skill refreshes the things that actually
go stale and leaves the rest alone — so a weekly sweep costs a fraction of a full
re-run.

**The core principle — cheap always, expensive only on a real delta:**

| Signal | Cost | When to refresh |
|---|---|---|
| Trading multiples / price / comps | ~0 LLM tokens (deterministic `data_agent.py`) | **Always** — this is the whole point of freshness |
| News | one scoped search | **Only items dated after the last run** |
| Earnings takeaways | one scoped agent | **Only if a new earnings filing appeared** since the last run |
| Overview / product / SWOT / explainer | full synthesis | **Only if news reveals a structural change** (M&A, leadership, guidance reset) |

The expensive synthesis is gated behind a cheap, deterministic "did anything
actually change?" check. That gate is what makes a weekly refresh affordable.

---

## Step 0 — Find what's stale

```bash
python3 plugins/atlas-research/skills/refresh-coverage/scripts/find_stale.py --days N
```

`N` is the staleness threshold in days. Default to **7** (one week). If the user
named a window ("older than two weeks", "/refresh-coverage 14"), use that number.

The script prints a JSON array (oldest-first) of stale companies, each with:
`id`, `lastRunDate`, `ageDays`, `isPublic`, `ticker`, `compTickers`, and
`newestKnownFilingDate`. It is LLM-free — use it so you don't spend tokens just
deciding what to touch.

If the array is empty, report "all coverage is fresh (nothing older than N days)"
and stop. Otherwise process each stale company through Steps 1–4. The companies
are independent — when several are stale, run their news/earnings agents in
**parallel** to finish the sweep faster.

For every stale company, set `TODAY` = today's date (YYYY-MM-DD) and create a new
run folder `data-dumps/<id>/runs/TODAY/`. Per the data convention, never overwrite
an old run — write a new dated folder and overwrite `profile.json` at the end.

---

## Step 1 — Refresh the live data (cheap, do it every time)

**Public companies** (`isPublic: true`): re-pull live trading data with the
**same comp set** as the existing brief so the peer group stays consistent:

```bash
python3 agents/data_agent.py <ticker> <compTickers...>   # tickers from find_stale
```

Save its JSON stdout to `data-dumps/<id>/runs/TODAY/data.json`. This re-anchors
every multiple, price, market cap, and margin to one shared `marketCloseAsOf` and
returns the current SEC filings list — the numbers an MD scrutinizes most, for
essentially no synthesis cost. Surface the `freshnessNote` / `marketCloseAsOf`.

**Private companies** (`isPublic: false`): there is no live market data to pull;
their "freshness" is funding/news. Skip `data_agent.py` and rely on Step 2b. (You
may still pull the public `compTickers` for context if the brief shows a comp table.)

---

## Step 2 — Detect the delta (decide where to spend tokens)

### 2a — New earnings? (gate the earnings synthesis)

Compare the **newest `filingDate`** in the fresh `data.json` (`secFilings`)
against the company's `lastRunDate` / `newestKnownFilingDate`.

- **A new 8-K / 10-Q / 10-K appeared since the last run** → a new quarter was
  likely reported → the earnings section is stale. Dispatch **one** scoped
  transcript/earnings agent for *just that latest quarter* (headline metrics,
  guidance, AI/demand commentary, sources) — restricted to the trusted sources in
  `agents/sources.py`, deep URLs only. Update `earningsTakeaways`.
- **No new filing** → the earnings section is still accurate → **skip it.** Do not
  re-research a quarter that hasn't changed. This is the single biggest token saver.

### 2b — New news since the last run? (always check, scope tightly)

Dispatch **one** news agent restricted to items **dated after `lastRunDate`**.
Instruct it to return *only genuinely new* developments (M&A, funding, product,
leadership, guidance, regulatory), each with a `source` + deep `sourceUrl` from the
`agents/sources.py` tiers. If it finds nothing new, that's a valid result — add
nothing and move on.

### 2c — Structural change? (gate the prose synthesis)

Only if Step 2b surfaces something that changes the *thesis* — an acquisition,
a leadership change, a guidance reset, a new product line — does the slower prose
need editing. In that case, update **just the affected sentences** in
`businessOverview` / `productModel` / `keyRisks` / `swot`, and note it in the
report. Otherwise leave the overview, product model, SWOT, and explainer **exactly
as they are** — re-synthesizing stable prose every week is precisely the waste this
skill exists to avoid.

---

## Step 3 — Patch profile.json (surgically, don't regenerate)

Read the existing `data-dumps/<id>/profile.json` and update **only** these fields,
leaving everything else byte-for-byte intact:

- `trading`, `comps`, `marketCloseAsOf`, `freshnessNote` ← from the fresh `data.json`.
  (The deliverable agent also re-pulls comps live at render, but patch them so
  `profile.json` is self-consistent.)
- `brief.recentNews` ← **prepend** the new items from 2b; keep the newest ~6–8,
  drop the oldest so the list doesn't grow unbounded.
- `brief.earningsTakeaways` ← replace **only if** 2a fired (new quarter). Keep the
  Metric Clarity mandate: every figure period-tagged, `quarter`/`reportDate` set,
  and every number ties to itself across the brief.
- `brief.businessOverview` / `productModel` / `keyRisks` / `swot` ← edit **only if**
  2c flagged a structural change.
- `lastRunDate` and `brief.runDate` ← set to `TODAY`.

Leave `explainer`, `leadership`, `verticals`, and the slow-changing prose untouched
unless a delta genuinely affected them. Then overwrite `profile.json` and write the
updated `data.json` (and `news.json` if you created one) into `runs/TODAY/`.

**Respect the mandates in CLAUDE.md:** the refreshed multiples must be live and
dated (Data Freshness), and every figure must still tie across the brief (Metric
Consistency). A refresh that introduces a stale or self-contradicting number is
worse than no refresh.

---

## Step 4 — Re-render the brief

```bash
python3 agents/deliverable_agent.py <id>
```

This writes the new HTML + PDF into `runs/TODAY/` and runs the QA passes. Read the
`✅ QA layout`, `🔗 QA sources`, and `🧮 QA metrics` lines and fix any **blocking**
issue before moving on.

**Legacy briefs (predating current requirements).** An older brief may be missing
the now-required `explainer` block (and `swot`), which QA flags as **blocking**. A
refresh is the natural moment to bring it up to standard: backfill a `plain` /
`technical` / `simple` explainer and a `swot` from the material already in the
profile (the overview, comps, and refreshed metrics — no new research needed), then
re-render. Don't leave a refreshed brief in a blocking state.

The project's auto-publish hook commits the new run and pushes it **only if QA did
not block** — so a brief you couldn't fully fix stays local for a human, and you
never need to commit manually. Run the render with its normal output (don't pipe it
through `tail`/`grep`) so the hook can see the `Brief saved` / QA result.

---

## Step 5 — Report the deltas

Give the user a tight, per-company summary of what actually changed — this is what
justifies the run and shows the token spend was targeted. One line each:

```
NTSK   multiples → 2026-06-12 close (EV/Rev 11.2x, was 10.8x) · +2 news · earnings unchanged
MU     multiples → 2026-06-12 close · no new news · earnings unchanged (no new filing)
ECPG   multiples → 2026-06-12 close · +1 news (acquisition) · overview updated · earnings unchanged
```

Then note anything that needs a human eye (a structural change you edited, a comp
that lagged the shared close, a QA warning you couldn't auto-resolve).

---

## Notes

- **Scope.** By default the sweep covers every stale company in `data-dumps/`. If
  the user names one ("just refresh Micron"), run Steps 1–4 for that id alone.
- **Threshold.** 7 days unless the user says otherwise; pass it through to
  `find_stale.py --days`.
- **Scheduling.** This skill performs one sweep when invoked. To run it on a
  cadence (e.g. every morning), pair it with the project's scheduling skill / a
  cron task that invokes `/refresh-coverage` — the skill itself stays stateless.
- **Why not just re-run `/atlas`?** `/atlas` rebuilds the entire brief (all four
  Wave-1 agents + full synthesis) — correct for a brand-new company, wasteful for a
  weekly touch-up. This skill is the incremental counterpart: same freshness
  guarantees on the numbers, a fraction of the tokens.
