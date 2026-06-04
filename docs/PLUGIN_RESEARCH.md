# Atlas as a Claude Code Plugin — Research & Feasibility

**Status:** ✅ Implemented — the plugin lives at [`plugins/atlas-research/`](../plugins/atlas-research)
and the marketplace manifest at [`.claude-plugin/marketplace.json`](../.claude-plugin/marketplace.json).
This doc is kept as the design record; the install names were finalized as
`/plugin marketplace add Agrimd15/alfred-tools` → `/plugin install atlas-research@alfred-tools`.
**Goal:** Let people install Atlas with `/plugin install ...` instead of cloning this repo.
**Branch:** `claude/atlas-plugin-research` → `feature/atlas-plugin`

**Decisions made (the doc's open questions, resolved):** briefs write to the user's project
(`ATLAS_DATA_ROOT="$PWD"` → `data-dumps/`); this repo (`alfred-tools`) doubles as the marketplace
(`name: alfred-tools`); v1 scope is the **research engine only** (the Vercel coverage site stays
clone-based). The CLAUDE.md execution protocol now travels with the plugin as
[`plugins/atlas-research/ATLAS_SPEC.md`](../plugins/atlas-research/ATLAS_SPEC.md), referenced by both
the `/atlas` command and the `atlas` skill.

---

## TL;DR

Packaging Atlas as a Claude Code plugin is **feasible and a good fit.** Atlas is mostly the
right shape already: it's a set of slash commands (`/atlas`, `/setup`) plus Python CLI agents
plus one HTTP MCP server (`ramp-data`). A plugin can bundle all three.

The main work is **re-pathing**: today the commands assume the repo lives at the project root
(`agents/data_agent.py`, `python3 agents/deliverable_agent.py`). In a plugin the code lives in
the plugin's install dir and must be referenced via `${CLAUDE_PLUGIN_ROOT}`. There are also a
few real blockers to clean up first (a committed merge conflict, the coverage-database model, and
Python/Chrome runtime deps).

A realistic effort estimate: **~1 focused day** to a working installable plugin, most of it spent
on path rewrites and testing the install flow end-to-end.

---

## How Claude Code plugins work (the parts that matter here)

A plugin is a self-contained directory. Everything except the manifest lives at the plugin root:

```
atlas-plugin/
├── .claude-plugin/
│   └── plugin.json          ← manifest (only `name` is strictly required)
├── commands/                ← slash commands (.md) — our /atlas, /setup
│   ├── atlas.md
│   └── setup.md
├── skills/                  ← optional richer skills (folder + SKILL.md)
├── agents/                  ← our Python CLI tools live here
│   ├── data_agent.py
│   ├── research_agent.py
│   ├── deliverable_agent.py
│   ├── sources.py
│   └── source_audit.py
├── .mcp.json                ← bundled MCP servers (ramp-data)
├── hooks/hooks.json         ← the SessionStart pip-install hook
├── CLAUDE.md  (see caveat)
└── README.md
```

### Manifest — `.claude-plugin/plugin.json`

```json
{
  "name": "atlas-research",
  "version": "1.0.0",
  "description": "Banker-grade company research briefs with live, sourced data.",
  "author": { "name": "Agrim Dhingra" },
  "homepage": "https://github.com/<owner>/atlas-plugin",
  "license": "MIT"
}
```

`name` becomes the namespace. A command file `atlas.md` is invoked as `/atlas-research:atlas`
(Claude Code also exposes the short `/atlas` form when unambiguous).

### Distribution — marketplace repo

Users don't install a plugin directly; they add a **marketplace** (a git repo with a catalog),
then install from it.

```
atlas-marketplace/                 (can be THIS repo)
├── .claude-plugin/
│   └── marketplace.json
└── plugins/
    └── atlas-research/             ← the plugin dir above
```

`marketplace.json`:

```json
{
  "name": "atlas-plugins",
  "owner": { "name": "Agrim Dhingra" },
  "plugins": [
    { "name": "atlas-research", "source": "./plugins/atlas-research" }
  ]
}
```

### End-user install flow

```
/plugin marketplace add <owner>/atlas-private        # point at the repo
/plugin install atlas-research@atlas-plugins          # install the plugin
# (Python deps + Chrome still required locally — see Runtime deps below)
/atlas SNOW                                           # use it
```

That replaces the current "git clone + read CLAUDE.md" onboarding.

### Path variables (the key to making this work)

| Variable | Meaning | Use for |
|---|---|---|
| `${CLAUDE_PLUGIN_ROOT}` | Absolute path to the installed plugin dir | Calling our Python agents, bundled files |
| `${CLAUDE_PLUGIN_DATA}` | Persistent dir that survives updates | Python venv, caches, **the coverage database** |
| `${CLAUDE_PROJECT_DIR}` | Where the user launched Claude | User's own working files |

So `python3 agents/data_agent.py SNOW` becomes
`python3 "${CLAUDE_PLUGIN_ROOT}/agents/data_agent.py" SNOW`.

---

## Atlas-specific findings

### What maps cleanly
- **`/atlas` and `/setup`** are plain Markdown command files in `.claude/commands/` → drop into
  the plugin's `commands/` unchanged except for path references.
- **Python agents** (`data_agent.py`, `research_agent.py`, `deliverable_agent.py`, `sources.py`,
  `source_audit.py`, ~3,500 lines) can be bundled verbatim and shelled out to. Plugins fully
  support bundling and executing arbitrary scripts/binaries.
- **`ramp-data` MCP** → moves from `.claude/settings.json` into the plugin's `.mcp.json`. It's an
  HTTP server (`https://mcp.ramp.com/ramp-data/anthropic/mcp`), no key, so it travels trivially.
- **SessionStart pip hook** → moves into `hooks/hooks.json`.

### Blockers / decisions to resolve first

1. **Committed merge conflict in `.claude/settings.json`** (both repo root and worktree). The file
   still has `<<<<<<< HEAD` / `=======` / `>>>>>>>` markers — the `hooks` block and the
   `mcpServers` block were never merged. This must be fixed regardless of the plugin (it's a live
   bug); the resolved version (both blocks present) is what feeds the plugin's `hooks.json` +
   `.mcp.json`.

2. **The repo IS the database.** CLAUDE.md's model is "this repo is the coverage database;
   `data-dumps/` + git history is the store; the site is the lens." A plugin is read-only,
   copied into `~/.claude/plugins/cache/...`, and updated out from under the user — it's a bad
   place to write `data-dumps/`. **Decision needed:** where does a plugin user's research output
   go? Options:
   - Write to `${CLAUDE_PROJECT_DIR}/data-dumps/` (the user's own project) — cleanest.
   - Write to `${CLAUDE_PLUGIN_DATA}/data-dumps/` (persistent, survives updates) — but then the
     git-history-as-database story and the Vercel site build don't come along.
   This is the biggest conceptual change: the plugin ships the **engine**, the user supplies the
   **database**.

3. **Runtime deps aren't bundleable.** Plugins distribute files, not a runtime. Users still need
   **Python 3.9+**, `yfinance`/`requests`, and **headless Chrome** (for PDF). The SessionStart
   hook can `pip install` the Python libs; Chrome must be pre-installed. The plugin README/`/setup`
   must state these prerequisites clearly. PDF generation will simply fail without Chrome.

4. **CLAUDE.md is the operating spec, and plugins don't inject a project CLAUDE.md.** Today the
   entire execution protocol lives in CLAUDE.md, loaded as project context. A plugin can't drop a
   CLAUDE.md into the user's project automatically. The protocol needs to move **into the command
   files / skills themselves** (or a skill that the `/atlas` command reads) so the behavior travels
   with the plugin. This is the largest content-refactor item.

5. **The Vercel coverage site is out of scope for v1.** `site/build.mjs`, `middleware.js`,
   `vercel.json`, and the auto-merge workflow assume the repo-as-database model and a user's own
   Vercel project. Ship the research engine as the plugin; treat "publish a coverage site" as a
   separate, documented, opt-in path (still via cloning, or a later plugin feature).

### Excluded from the plugin
`.env` (secrets), user `data-dumps/*/`, `.vercel/`, `__pycache__/`, `site/dist/`.

---

## Proposed phased plan

**Phase 0 — Cleanup (required anyway)**
- Resolve the `.claude/settings.json` merge conflict (keep both `hooks` and `mcpServers`).
- Add a `requirements.txt` (`yfinance`, `requests`) so deps are explicit.

**Phase 1 — Minimal installable plugin (research engine only)**
- Create `atlas-plugin/` with `plugin.json`, `commands/atlas.md` + `commands/setup.md`,
  `agents/*.py`, `.mcp.json` (ramp-data), `hooks/hooks.json` (pip install).
- Rewrite every `agents/...` path in the commands to `${CLAUDE_PLUGIN_ROOT}/agents/...`.
- Move the CLAUDE.md execution protocol into the command/skill content.
- Decide output location (recommend `${CLAUDE_PROJECT_DIR}/data-dumps/`).
- Test locally with `claude --plugin-dir ./atlas-plugin` before publishing.

**Phase 2 — Marketplace + distribution**
- Add `.claude-plugin/marketplace.json` (this repo can double as the marketplace).
- Write install docs; verify the full `/plugin marketplace add` → `/plugin install` → `/atlas`
  flow on a clean machine.

**Phase 3 — Site/publishing (optional, later)**
- Decide whether coverage-site publishing stays clone-only or becomes a plugin feature.

---

## Open questions for the user
1. **Output location:** should a plugin user's briefs land in their current project
   (`${CLAUDE_PROJECT_DIR}/data-dumps/`) or in plugin-persistent storage?
2. **Marketplace host:** use this repo (`atlas-private`) as the marketplace, or a new public
   `atlas-plugin` repo? (Public is better for "anyone can install.")
3. **Scope of v1:** research engine only, or must the coverage site / Vercel deploy ship too?
4. **Audience:** internal teammates, or fully public distribution? (Affects repo visibility and
   how much hand-holding the README needs around Python/Chrome prereqs.)

---

## References (official docs)
- Plugins guide — https://code.claude.com/docs/en/plugins.md
- Plugins reference (schemas, CLI) — https://code.claude.com/docs/en/plugins-reference.md
- Plugin marketplaces — https://code.claude.com/docs/en/plugin-marketplaces.md
- Discover / install plugins — https://code.claude.com/docs/en/discover-plugins.md
