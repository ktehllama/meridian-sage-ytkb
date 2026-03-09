#!/usr/bin/env bash
# Meridian — unified startup script
# Works on Windows (Git Bash) and Linux/Raspberry Pi
#
# Usage:
#   ./start.sh          — production (npm start)
#   ./start.sh --dev    — development (npm run dev)

set -e

# ── Resolve project root (directory this script lives in) ────────────────────
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Mode ─────────────────────────────────────────────────────────────────────
NPM_CMD="start"
if [[ "${1:-}" == "--dev" ]]; then
  NPM_CMD="dev"
fi

# ── Environment ──────────────────────────────────────────────────────────────
export CHROMA_DB_PATH="$ROOT/yc_vectors"
export SQLITE_DB_PATH="$ROOT/knowledge.db"
export CHROMA_COLLECTION="transcripts"
export GCP_PROJECT="YOUR_GCP_PROJECT_NUMBER"
export GCP_LOCATION="us-central1"
export GEMINI_MODEL="gemini-2.0-flash"

# ── Activate venv if present (Raspberry Pi / local venv) ────────────────────
if [[ -f "$ROOT/venv/bin/activate" ]]; then
  source "$ROOT/venv/bin/activate"
elif [[ -f "$ROOT/venv/Scripts/activate" ]]; then
  # Windows Git Bash path
  source "$ROOT/venv/Scripts/activate"
fi

# ── Cleanup on exit — kill both child processes ──────────────────────────────
cleanup() {
  echo ""
  echo "[start.sh] Shutting down..."
  kill "$API_PID" "$FRONTEND_PID" 2>/dev/null
  wait "$API_PID" "$FRONTEND_PID" 2>/dev/null
  echo "[start.sh] Done."
}
trap cleanup EXIT INT TERM

# ── Start API ────────────────────────────────────────────────────────────────
echo "[start.sh] Starting API (port 8000)..."
cd "$ROOT"
uvicorn api.main:app --port 8000 &
API_PID=$!

# ── Start frontend ───────────────────────────────────────────────────────────
echo "[start.sh] Starting frontend (npm $NPM_CMD)..."
cd "$ROOT/sage_chat"
npm "$NPM_CMD" &
FRONTEND_PID=$!

echo ""
echo "  API      → http://localhost:8000"
echo "  Frontend → http://localhost:3000"
echo ""
echo "  Press Ctrl+C to stop both."
echo ""

# ── Wait for either process to exit ─────────────────────────────────────────
wait -n "$API_PID" "$FRONTEND_PID" 2>/dev/null || wait "$API_PID" "$FRONTEND_PID"
