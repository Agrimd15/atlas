#!/usr/bin/env bash
# SessionStart: tell the user when their installed plugin is behind its origin, so a
# field-reported fix actually reaches them. Prompts by default; set
# ATLAS_PLUGIN_AUTOUPDATE=1 to fast-forward automatically instead (clean tree only).
# Always exits 0 — an update check must never break a session (offline, no upstream,
# detached HEAD, or a non-git install all just skip silently).
set -u

ROOT=$(git -C "${CLAUDE_PLUGIN_ROOT:-.}" rev-parse --show-toplevel 2>/dev/null) || exit 0
git -C "$ROOT" fetch --quiet origin 2>/dev/null || exit 0
UPSTREAM=$(git -C "$ROOT" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null) || exit 0
BEHIND=$(git -C "$ROOT" rev-list --count "HEAD..$UPSTREAM" 2>/dev/null) || exit 0
[ "${BEHIND:-0}" -gt 0 ] || exit 0

if [ "${ATLAS_PLUGIN_AUTOUPDATE:-0}" = "1" ] && [ -z "$(git -C "$ROOT" status --porcelain 2>/dev/null)" ] \
   && git -C "$ROOT" pull --ff-only --quiet 2>/dev/null; then
    echo "[atlas-research] Plugin auto-updated: pulled $BEHIND new commit(s) from $UPSTREAM."
else
    echo "[atlas-research] Plugin update available ($BEHIND commit(s) behind $UPSTREAM). Pull it with: git -C \"$ROOT\" pull — or ask Claude to update the plugin now. (Set ATLAS_PLUGIN_AUTOUPDATE=1 to do this automatically.)"
fi
exit 0
