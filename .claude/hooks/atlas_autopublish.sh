#!/usr/bin/env bash
# Atlas auto-publish hook.
#
# Fires as a PostToolUse hook on the Bash tool. When the tool call was a
# successful, QA-clean Atlas brief render (`deliverable_agent.py`), it commits
# the new/changed coverage under data-dumps/ and pushes THE CURRENT BRANCH so
# the run is preserved (on main that publishes directly; on a claude/* work
# branch the PR + auto-merge workflow lands it).
#
# Installed with explicit user authorization (auto-push of coverage, no review gate).
#
# Tamed on purpose — the previous version caused real damage mid-session:
#   • it ran `git pull --rebase` and pushed MAIN from whatever branch was active,
#     which rewrote in-progress branches and once left a detached, half-merged
#     state with conflict markers inside a published HTML brief;
#   • `git commit` without a pathspec swept up unrelated files other work had
#     staged.
# So now it: never rebases, never touches main from another branch, commits
# data-dumps/ by pathspec only, and refuses to act mid-merge/rebase or detached.
set -uo pipefail

# PostToolUse payload (JSON, incl. tool_response) arrives on stdin. Gate on the
# deliverable agent's success marker — "Brief saved" only appears in the OUTPUT of
# an actual successful render, so a mere mention of the script won't trigger.
payload="$(cat 2>/dev/null || true)"
case "$payload" in
  *"Brief saved"*) ;;
  *) exit 0 ;;
esac

# Never publish a brief that failed QA with a BLOCKING issue (contradicting
# metric, missing required explainer, etc.) — human review before publishing.
case "$payload" in
  *"blocking issue"*) exit 0 ;;
esac

repo="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$repo" ] && cd "$repo" 2>/dev/null || exit 0

# Refuse to act in a fragile repo state: mid-merge, mid-rebase, or detached HEAD.
gitdir="$(git rev-parse --git-dir 2>/dev/null)" || exit 0
if [ -e "$gitdir/MERGE_HEAD" ] || [ -d "$gitdir/rebase-merge" ] || [ -d "$gitdir/rebase-apply" ]; then
  exit 0
fi
branch="$(git symbolic-ref --short -q HEAD)" || exit 0   # detached HEAD → leave it alone

# Nothing new under coverage → nothing to publish.
[ -z "$(git status --porcelain data-dumps/ 2>/dev/null)" ] && exit 0

# Label the commit with the company folder(s) that changed.
ids="$(git status --porcelain data-dumps/ 2>/dev/null \
        | sed -n 's#^...data-dumps/\([^/]*\)/.*#\1#p' | sort -u | tr '\n' ' ' | sed 's/ *$//')"
[ -z "$ids" ] && ids="coverage"

# Pathspec-scoped commit: stages and commits ONLY data-dumps/, even if other
# files happen to be staged by in-flight work.
git commit -q -m "Auto-publish Atlas coverage: ${ids}" -- data-dumps/ >/dev/null 2>&1 || exit 0

# Push the CURRENT branch only. No rebase: if the push is rejected, leave it for
# the session (or a human) to reconcile — a hook must never rewrite history.
git push -q origin "$branch" >/dev/null 2>&1 || true

exit 0
