# Sync model: alfred-private ⇄ alfred-tools

Two repos, one boundary. Code flows both ways; **private coverage data never leaves private.**

```
  alfred-private  (private)                         alfred-tools  (public)
  ─────────────────────────                         ──────────────────────
  • ALL coverage (data-dumps/)                       • canonical published tool
  • your working source                              • demo data only (DEMO_IDS)
                                                      • what others fork / install

      │                                                        │
      │  ── private → public (AUTOMATED) ──────────────▶       │
      │     sync-to-public.yml on every push to main           │
      │     copies CODE (excl data-dumps) + DEMO data only     │
      │                                                        │
      │  ◀────────────── public → private (MANUAL) ───         │
      │     git fetch upstream && git merge upstream/main      │
      │     pulls CODE only — data-dumps is never touched      │
```

## The one firm rule

**`data-dumps/` is the boundary and is never part of the two-way sync.**
- private → public sends **code + demo companies only** (never full coverage).
- public → private pulls **code only** — your private `data-dumps/` is never overwritten or
  deleted by a sync.

This boundary has been breached once before (public PR #2: `Revert: remove researched companies
(MRVL, PL, amdahl-ai) from public repo`). Keep it sacred.

## Direction 1 — private → public (automated)

Workflow: `.github/workflows/sync-to-public.yml`, runs on every push to `main`.
- rsyncs code, excluding `data-dumps/`, `.env`, `site/dist/`, etc.
- then copies *only* the demo companies' data-dumps (parsed from `DEMO_IDS` in `site/build.mjs`).
- skips the commit if nothing changed (this is also what makes the loop impossible).

**Requires** the `ATLAS_PUBLIC_PAT` secret in alfred-private — a fine-grained PAT with
**Contents: Read & Write** scoped to `Agrimd15/alfred-tools`. Without it the job fails at checkout.

## Direction 2 — public → private (manual, git-native)

When you've edited code directly in the public repo, pull it into private:

```bash
cd ~/Documents/GitHub/atlas-private      # (folder name unchanged; repo is alfred-private)
git fetch upstream
git merge upstream/main                   # or: git rebase upstream/main
```

`upstream` points at `https://github.com/Agrimd15/alfred-tools.git`. Because the two repos share
history, this merges cleanly. You control the merge, so `data-dumps/` can't be silently clobbered —
resolve any conflict the normal way and commit.

Why manual instead of a workflow: a public→private *automation* would need a token that can write
to your private repo living in the public repo, and would lean entirely on one `--exclude=data-dumps/`
line staying correct. A hand-run `git merge` removes both risks for the cost of one command. If
editing-in-public ever becomes routine, revisit automating this (with a tested data-dumps guard).

## Why your repo is the publisher, not a consumer

Other people fork **public alfred-tools** and pull updates from it (or install it as a plugin).
*Your* alfred-private is upstream of public — it feeds public. So you publish down (Direction 1) and
occasionally pull code back up (Direction 2); you don't "fork from" public the way consumers do.
