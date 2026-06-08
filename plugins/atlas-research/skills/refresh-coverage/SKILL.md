---
name: refresh-coverage
description: Refresh stale Atlas coverage — re-run every company whose latest brief is older than a threshold (default 1 week), updating ONLY what has changed since the last run to keep token cost low. Use whenever the user wants to update, refresh, re-run, or "freshen up" old briefs/coverage/runs — e.g. "update everything older than a week", "refresh my stale reports", "re-run the briefs that have gone out of date", "keep coverage current", or when they ask to bring a backlog of aging company briefs up to date. Triggers on staleness/freshness/"out of date"/"week old" phrasing even if they don't name a specific company.
---

# Refresh stale coverage

A full re-run every week is wasteful: overview, SWOT, explainer, and product model barely move, while
**trading multiples move daily** and a **new headline or filing** appears only occasionally. Refresh
what actually goes stale; leave the rest. The expensive synthesis is gated behind a cheap,
deterministic "did anything change?" check — that gate is what makes a weekly sweep affordable.

| Signal | Cost | When to refresh |
|---|---|---|
| Multiples / price / comps | ~0 tokens (deterministic `data_agent.py`) | **Always** |
| News | one scoped search | **Only items dated after the last run** |
| Earnings takeaways | one scoped agent | **Only if a new filing appeared** since last run |
| Overview / product / SWOT / explainer | full synthesis | **Only on a structural change** (M&A, leadership, guidance reset) |

Engine paths are under `${CLAUDE_PLUGIN_ROOT}`; prefix every Python call with `ATLAS_DATA_ROOT="$PWD"`
so it reads/writes the user's project `data-dumps/`.

## Step 0 — Find what's stale

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/refresh-coverage/scripts/find_stale.py" --days N
```

`N` = staleness threshold (default **7**; honor a user-named window). It prints an LLM-free JSON array
(oldest-first) of stale companies with `id`, `lastRunDate`, `ageDays`, `isPublic`, `ticker`,
`compTickers`, `newestKnownFilingDate`. Empty → report "all coverage is fresh" and stop. Otherwise
process each through Steps 1–4 (independent companies → run their news/earnings agents in **parallel**).
For each, set `TODAY` (YYYY-MM-DD) and create `data-dumps/<id>/runs/TODAY/` — never overwrite an old run.

## Step 1 — Refresh live data (cheap, every time)

**Public** (`isPublic: true`): re-pull with the **same comp set** so the peer group stays consistent:

```bash
ATLAS_DATA_ROOT="$PWD" python3 "${CLAUDE_PLUGIN_ROOT}/agents/data_agent.py" <ticker> <compTickers...>
```

Save stdout to `data-dumps/<id>/runs/TODAY/data.json`. This re-anchors every multiple/price/margin to
one shared `marketCloseAsOf` and returns the current SEC filings — surface `freshnessNote` /
`marketCloseAsOf`. **Private** (`isPublic: false`): no market data — skip to 2b (you may still pull
the public `compTickers` if the brief shows a comp table).

## Step 2 — Detect the delta (decide where to spend tokens)

- **2a New earnings?** Compare the newest `filingDate` in the fresh `data.json` (`secFilings`) to
  `lastRunDate` / `newestKnownFilingDate`. New 8-K/10-Q/10-K → dispatch **one** scoped earnings agent
  for *just that quarter* (metrics, guidance, AI/demand commentary, sources; trusted tiers in
  `${CLAUDE_PLUGIN_ROOT}/agents/sources.py`, deep URLs) and update `earningsTakeaways`. No new filing →
  **skip it** (the single biggest token saver).
- **2b New news?** Dispatch **one** news agent restricted to items dated after `lastRunDate` — only
  genuinely new developments (M&A, funding, product, leadership, guidance, regulatory), each with a
  deep `sourceUrl` from the trusted tiers. Nothing new is a valid result.
- **2c Structural change?** Only if 2b changes the *thesis* (acquisition, leadership, guidance reset,
  new product line) do you edit the **affected sentences** in `businessOverview` / `productModel` /
  `keyRisks` / `swot`. Otherwise leave the slow-changing prose and explainer exactly as they are.

## Step 3 — Patch profile.json (surgically; don't regenerate)

Update **only** these in `data-dumps/<id>/profile.json`, leaving everything else byte-for-byte intact:
- `trading`, `comps`, `marketCloseAsOf`, `freshnessNote` ← fresh `data.json`.
- `brief.recentNews` ← **prepend** 2b's items; keep newest ~6–8, drop the oldest.
- `brief.earningsTakeaways` ← replace **only if** 2a fired (keep Metric Clarity: every figure
  period-tagged, `quarter`/`reportDate` set, numbers tie across the brief).
- `brief.businessOverview` / `productModel` / `keyRisks` / `swot` ← **only if** 2c flagged a change.
- `lastRunDate` and `brief.runDate` ← `TODAY`.

Leave `explainer`, `leadership`, `verticals` untouched unless a delta hit them. Then overwrite
`profile.json` and write the fresh `data.json` (and `news.json` if created) into `runs/TODAY/`.
**Respect the ATLAS_SPEC.md mandates:** refreshed multiples must be live + dated, and every figure
must still tie. A refresh that introduces a stale or self-contradicting number is worse than none.

## Step 4 — Re-render

```bash
ATLAS_DATA_ROOT="$PWD" python3 "${CLAUDE_PLUGIN_ROOT}/agents/deliverable_agent.py" <id>
```

Writes the new HTML + PDF into `runs/TODAY/` and runs QA. Read `✅ QA layout`, `🔗 QA sources`,
`🧮 QA metrics`; fix any **blocking** issue. **Legacy briefs** may lack the now-required `explainer`
(and `swot`) — QA blocks on that; backfill `plain`/`technical`/`simple` + a `swot` from material
already in the profile (no new research) and re-render. Don't leave a refreshed brief blocking.

The project's auto-publish hook commits + pushes the new run **only if QA didn't block** — so run the
render with normal output (don't pipe through `tail`/`grep`) so the hook sees `Brief saved` / the QA result.

## Step 5 — Report the deltas

One tight line per company — what actually changed, justifying the spend:

```
NTSK   multiples → 2026-06-12 close (EV/Rev 11.2x, was 10.8x) · +2 news · earnings unchanged
MU     multiples → 2026-06-12 close · no new news · earnings unchanged (no new filing)
ECPG   multiples → 2026-06-12 close · +1 news (acquisition) · overview updated · earnings unchanged
```

Then flag anything needing a human eye (a structural edit, a comp lagging the shared close, an
unresolved QA warning).

## Notes
- **Scope** — all stale companies by default; if the user names one, run Steps 1–4 for that id alone.
- **Threshold** — 7 days unless told otherwise; pass through to `find_stale.py --days`.
- **Scheduling** — one sweep per invocation; pair with the scheduling skill / a cron task for a cadence.
- **Why not just `/atlas`?** That rebuilds the whole brief — correct for a new company, wasteful for a
  weekly touch-up. This is the incremental counterpart: same freshness on the numbers, a fraction of the tokens.
