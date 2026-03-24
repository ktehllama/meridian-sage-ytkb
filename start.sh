#!/usr/bin/env bash
# Starts the API (port 8000) and frontend (port 3000).
# Usage: ./start.sh [--dev]

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NPM_CMD="start"
if [[ "${1:-}" == "--dev" ]]; then
  NPM_CMD="dev"
fi

export CHROMA_DB_PATH="$ROOT/yc_vectors"
export SQLITE_DB_PATH="$ROOT/knowledge.db"
export CHATS_DB_PATH="$ROOT/chats.db"
export CHROMA_COLLECTION="transcripts"
export GCP_PROJECT="YOUR_GCP_PROJECT_NUMBER"
export GCP_LOCATION="us-central1"
export GEMINI_MODEL="gemini-2.0-flash"

free_port() {
  local port=$1
  if command -v fuser &>/dev/null; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  else
    # Windows Git Bash fallback
    local pid
    pid=$(netstat -ano 2>/dev/null | grep ":${port} " | grep LISTENING | awk '{print $NF}' | head -1)
    if [[ -n "$pid" ]]; then
      taskkill //PID "$pid" //F &>/dev/null || true
    fi
  fi
}

echo "[start.sh] Freeing ports 8000 and 3000..."
free_port 8000
free_port 3000
sleep 1

# activate venv if present
if [[ -f "$ROOT/venv/bin/activate" ]]; then
  source "$ROOT/venv/bin/activate"
elif [[ -f "$ROOT/venv/Scripts/activate" ]]; then
  source "$ROOT/venv/Scripts/activate"
fi

cleanup() {
  echo ""
  echo "[start.sh] Shutting down..."
  kill "$API_PID" "$FRONTEND_PID" 2>/dev/null
  wait "$API_PID" "$FRONTEND_PID" 2>/dev/null
  echo "[start.sh] Done."
}
trap cleanup EXIT INT TERM

echo "[start.sh] Starting API (port 8000)..."
cd "$ROOT"
uvicorn api.main:app --port 8000 &
API_PID=$!

cd "$ROOT/sage_chat"
if [[ "$NPM_CMD" == "start" && ! -f ".next/BUILD_ID" ]]; then
  echo "[start.sh] No production build found — building now (this takes ~30s)..."
  npm run build
fi
echo "[start.sh] Starting frontend (npm $NPM_CMD)..."
npm "$NPM_CMD" &
FRONTEND_PID=$!

echo ""
echo "  API      → http://localhost:8000"
echo "  Frontend → http://localhost:3000"
echo ""
echo "  Press Ctrl+C to stop both."
echo ""

wait -n "$API_PID" "$FRONTEND_PID" 2>/dev/null || wait "$API_PID" "$FRONTEND_PID"
