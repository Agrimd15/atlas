# Sync model: how the Alfred repos stay in lockstep

Three repos, four automations, one firm boundary.

```
 alfred-private (private)                    alfred-tools (public)
 ────────────────────────                    ─────────────────────
 • your working source                       • canonical published toolkit
 • ALL coverage (data-dumps/)                • plugin marketplace
 • archive/ of retired coverage             • demo data only (DEMO_IDS)
                                             • what others clone / install
     │                                                  │
     │ ①  private → public  (AUTO, every push to main)  │
     │ ─────────────────────────────────────────────▶   │
     │    sync-to-public.yml: code (no archive/),       │
     │    demo data only, regenerated .gitignore        │
     │                                                  │
     │ ②  public → private  (AUTO, daily, lands as PR)  │
     │  ◀─────────────────────────────────────────────  │
     │    pull-from-public.yml: code only, and only     │
     │    when public has non-sync-bot commits          │
     │                                                  │
     │                                                  │ ③  upstream → private clones
     │                                                  │    (AUTO, daily, lands as PR)
     │                                                  ▼
     │                                       someone else's private clone
     │                                       (pull-upstream.yml ships in
     │                                        alfred-tools itself)
     │
     │ ④  tool surface → landing page  (AUTO, issue)
     ▼
 alfred-analyst (private) — alfred-analyst.com landing page
```

## The one firm rule

**`data-dumps/` is the boundary.** Private coverage never leaves alfred-private:
- ① sends code + the current `DEMO_IDS` companies only — and prunes ex-demo
  folders, so the public set always equals the demo set exactly.
- ② and ③ pull **code only** — a sync can never overwrite or delete anyone's
  `data-dumps/`, `archive/`, `.gitignore`, or workflows.
- `archive/` is private-instance-only: the public repo ships current demos, not
  retired coverage.

Two guards keep the boundary: the demo-only copy in ①, plus the public repo's
`.gitignore` (a demo allowlist, **generated from DEMO_IDS** on every sync so it
can't drift or be hand-overwritten — it was once, which is why it's generated now).

## ① private → public — `sync-to-public.yml` (here)

Runs on every push to `main`. rsyncs code (excluding `data-dumps/`, `archive/`,
`.github/workflows/`, `.gitignore`, `.env`, `site/dist/`), then mirrors exactly
the `DEMO_IDS` companies (parsed from `site/build.mjs`) into the public
`data-dumps/` — adding new demos, pruning ones that left the set — and finally
regenerates the public `.gitignore` allowlist. Skips the commit when nothing
changed, which is also what makes the ①/② loop impossible.

**Requires** the `ATLAS_PUBLIC_PAT` secret — a fine-grained PAT with
**Contents: Read & Write** on `Agrimd15/alfred-tools`.

## ② public → private — `pull-from-public.yml` (here)

Daily (and on demand via workflow_dispatch). If the public repo has commits in
the lookback window **not authored by the sync bot** (someone merged a community
PR or hotfixed the public clone), it rsyncs the public code over private —
same exclusions, both directions — and opens a **ready PR** for review. Three
loop-safeties: public is normally an exact mirror (no diff); the non-sync-bot
gate; and it lands as a PR, never a push. Needs no extra secret (the default
token opens PRs in this repo; the public repo is world-readable).

## ③ upstream → private clones — `pull-upstream.yml` (ships in alfred-tools)

Lives in the **public repo's** `.github/workflows/`, so anyone who clones
alfred-tools as their own private instance gets it for free: once a day it
pulls the latest upstream code and opens a PR in *their* repo. Guarded with
`if: github.repository != 'Agrimd15/alfred-tools'` so it never runs upstream.
Their `CLAUDE.md` can carry instance state (the auto-run budget block), so the
PR body says to review that before merging. Note GitHub pauses scheduled
workflows after ~60 days of repo inactivity.

The forward sync ① excludes `.github/workflows/` in both copy and delete, so
this file is owned and edited **in alfred-tools directly**, never overwritten
by a sync.

## ④ tool surface → landing page — `notify-landing-page.yml` (here)

alfred-analyst.com (the separate private `Agrimd15/alfred-analyst` repo) shows
the tool cards, install command, and command descriptions. On any push to
`main` that touches `plugins/**` or `.claude-plugin/**`, this files (or
refreshes — one open issue, never a pile) an issue on alfred-analyst listing
what changed, so the landing page is updated deliberately rather than drifting.
The page itself is marketing copy, so the update stays a human edit.

**Requires** the `ALFRED_ANALYST_PAT` secret — a fine-grained PAT with
**Issues: Read & Write** on `Agrimd15/alfred-analyst`. Without it the job
prints a notice and succeeds.

## Breach history (why the guards exist)

- Public PR #2 reverted researched companies (MRVL, PL, amdahl-ai) that leaked
  into the public repo.
- The public `.gitignore` was later overwritten with the private instance's
  "track ALL coverage" version, disabling the second guard — and 8 ex-demo
  folders plus `archive/` accumulated publicly until the 2026-06 cleanup
  (public PR #4). The allowlist is generated on every sync now, and the demo
  copy prunes.
