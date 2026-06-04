# Rename: public repo `atlas` → `alfred-tools`

**Goal:** Reposition the public repo as `alfred-tools` — the home for *all* Alfred analyst
tools — while keeping **Atlas** as the (first) tool inside it. This is a repo-identity reframe,
**not** a rename of the Atlas tool.

**Branch:** `claude/atlas-plugin-research`

---

## The single most important rule

**"Atlas" the tool keeps its name everywhere. Only the repo identity becomes `alfred-tools`.**

A find-and-replace of `atlas` → `alfred-tools` would break the product. These MUST stay "Atlas":

- the `/atlas` slash command and `.claude/commands/atlas.md`
- `viewer/atlas.html`, `viewer/atlas.json.example`, viewer UI
- `CLAUDE.md` (the Atlas tool's operating spec — title stays "Atlas - Company Research Tool")
- `agents/*.py` references to Atlas, brief filenames (`SNOW_brief_*.html`)
- the coverage **site UI branding** (`site/template/`, `middleware.js`) — that's the Atlas
  product brand on the published site; rebranding the site to "Alfred" is a separate product
  decision, out of scope here.

Only **repo-identity** references change. There are very few:

| Reference | File | Change |
|---|---|---|
| Public repo name on GitHub | (GitHub) | `Agrimd15/atlas` → `Agrimd15/alfred-tools` |
| Sync target repo | `.github/workflows/sync-to-public.yml` | `Agrimd15/atlas` → `Agrimd15/alfred-tools` |
| Workflow display name / comments | `.github/workflows/sync-to-public.yml` | "Public Atlas" → "Public alfred-tools" |
| Top-of-README positioning | `README.md` | reframe repo as `alfred-tools`, Atlas = first tool |
| Local git remote `upstream` | (your machine) | point at the renamed repo |

The two `.github/workflows/*.yml` files are what the request means by "across all workflows."
`auto-merge-coverage.yml` uses `context.repo` (dynamic) — it needs **no change** and survives the
rename automatically.

---

## What I changed on this branch (safe — no external effect until merged to `main`)

1. **`README.md`** — reframed the top so the repo reads as `alfred-tools` (the Alfred toolkit),
   with Atlas presented as the first tool under it. All Atlas content preserved.
2. **`.github/workflows/sync-to-public.yml`** — retargeted the sync to `Agrimd15/alfred-tools`
   and updated the display name + comments.
   - ⚠️ **Sequencing:** this edit references `Agrimd15/alfred-tools`, which only exists *after*
     the GitHub rename. **Do the GitHub rename (Phase B) before this branch merges to `main`.**
     If merged first, the next sync run fails the "Checkout public alfred-tools" step.
   - The `ATLAS_PUBLIC_PAT` secret name was **left unchanged** on purpose (secret names are
     arbitrary; renaming it means recreating the secret in GitHub and breaks the run until you do).

---

## Cutover checklist (the external steps — do these at rename time)

### Phase B — GitHub rename
1. Rename the public repo: GitHub → `Agrimd15/atlas` → **Settings → General → Rename** →
   `alfred-tools`. (Or `gh repo rename alfred-tools -R Agrimd15/atlas`.)
   GitHub auto-creates redirects, so old `github.com/Agrimd15/atlas` URLs keep resolving.
2. *(Recommended, optional)* rename the private repo too for coherence:
   `Agrimd15/atlas-private` → `Agrimd15/alfred-tools-private`.
3. Update local remotes:
   ```bash
   git remote set-url upstream https://github.com/Agrimd15/alfred-tools.git
   # if you also renamed the private repo:
   git remote set-url origin  https://github.com/Agrimd15/alfred-tools-private.git
   ```

### Phase C — Vercel
- Vercel's GitHub integration **follows the repo rename automatically** (it's tied to repo ID),
  so deploys keep working with no reconnect.
- But the **Vercel project name** and any `*.vercel.app` URL still say "atlas". Rename the project
  under **Vercel → Project → Settings → General → Project Name** if you want the URL to match.
  Custom domains are unaffected.
- Confirm the `SITE_PASSWORD` env var is still set after any project rename.

### Phase D — Secrets / PAT
- The `ATLAS_PUBLIC_PAT` secret keeps working — fine-grained PATs are scoped by repo **ID**, not
  name, so the rename doesn't invalidate it. No action required.
- *(Optional cosmetic)* rename the secret to `ALFRED_PUBLIC_PAT`: recreate it in
  **private repo → Settings → Secrets → Actions**, then update the `secrets.ATLAS_PUBLIC_PAT`
  reference in `sync-to-public.yml`. Skip unless you want the cleaner name.

### Phase E — Verify
1. Merge this branch to `main` (after Phase B).
2. Confirm the **Sync to Public alfred-tools** workflow runs green and pushes to
   `Agrimd15/alfred-tools`.
3. Confirm the Vercel production deploy is green.
4. Hit `github.com/Agrimd15/atlas` and confirm it redirects to `…/alfred-tools`.

---

## Deliberately NOT changing
- The Atlas tool, its command, viewer, brief output, and `CLAUDE.md` spec (see rule above).
- Site UI branding (`site/`, `middleware.js`) — product-brand decision, separate from the rename.
- `auto-merge-coverage.yml` — repo-name-agnostic, survives the rename as-is.

## Future (ties into the plugin/marketplace work)
When `alfred-tools` grows past Atlas, each tool gets its own command/skill + spec under this repo,
and `alfred-tools` doubles as the plugin marketplace. See [PLUGIN_RESEARCH.md](PLUGIN_RESEARCH.md).
