#!/usr/bin/env bash
# Atlas auto-publish hook.
#
# Fires as a PostToolUse hook on the Bash tool. When the tool call was an
# Atlas brief render (`deliverable_agent.py`), it commits any new/changed
# coverage under data-dumps/ and pushes to main so Vercel redeploys the site.
#
# Installed with explicit user authorization (full auto-push, no review gate).
#
# Scoped on purpose:
#   • only acts when the Bash command contained `deliverable_agent.py`
#   • only stages data-dumps/ (never agents/, site/, or other working changes)
#   • never blocks the session — every git step is best-effort (exit 0)
set -uo pipefail

# PostToolUse payload (JSON, incl. tool_response) arrives on stdin. Gate on the
# deliverable agent's success marker — "Brief saved" only appears in the OUTPUT of
# an actual successful render, so a mere mention of the script (grep/echo/commit
# message) won't trigger a publish. This is the precise signal of a real render.
payload="$(cat 2>/dev/null || true)"
case "$payload" in
  *"Brief saved"*) ;;
  *) exit 0 ;;
esac

repo="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$repo" ] && cd "$repo" 2>/dev/null || exit 0

# Nothing new under coverage → nothing to publish.
[ -z "$(git status --porcelain data-dumps/ 2>/dev/null)" ] && exit 0

git add data-dumps/ >/dev/null 2>&1 || exit 0

# Label the commit with the company folder(s) that changed.
ids="$(git diff --cached --name-only -- data-dumps/ 2>/dev/null \
        | sed -n 's#^data-dumps/\([^/]*\)/.*#\1#p' | sort -u | tr '\n' ' ' | sed 's/ *$//')"
[ -z "$ids" ] && ids="coverage"

git commit -q -m "Auto-publish Atlas coverage: ${ids}

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>" >/dev/null 2>&1 || exit 0

# Sync with remote (autostash any unrelated working changes) then push. Best-effort.
git pull --rebase --autostash origin main >/dev/null 2>&1
git push origin main >/dev/null 2>&1

exit 0
