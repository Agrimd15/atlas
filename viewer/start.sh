#!/usr/bin/env bash
# Atlas v0.3 — start the backend and open the browser
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check for Python 3
if ! command -v python3 &>/dev/null; then
  echo "❌  Python 3 is required. Install via Homebrew: brew install python"
  exit 1
fi

# Check for claude CLI
if ! command -v claude &>/dev/null; then
  echo "❌  'claude' CLI not found."
  echo "    Install Claude Code: https://claude.ai/code"
  exit 1
fi

# Install/upgrade dependencies quietly
echo "📦  Checking dependencies..."
python3 -m pip install -q -r backend/requirements.txt 2>/dev/null || \
  python3 -m pip install -q --break-system-packages -r backend/requirements.txt

# Open browser after a short delay
(sleep 1.5 && open http://localhost:8000 2>/dev/null || xdg-open http://localhost:8000 2>/dev/null || true) &

echo ""
echo "🧭  Atlas v0.3 starting at http://localhost:8000"
echo "    Uses your Claude Code login — no API key needed."
echo "    Press Ctrl+C to stop."
echo ""

python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
