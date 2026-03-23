#!/usr/bin/env bash
# dev_server.sh — Reset, seed, and launch Comply for local testing.
#
# Uses an ISOLATED data directory (~/.comply-dev) and port (9001) so it
# never touches the real ~/.comply data or the default port 8001.
#
# Usage:
#   ./dev_server.sh              # interactive persona picker
#   ./dev_server.sh journey      # seed and start directly
#   ./dev_server.sh stop         # stop the dev server
#   ./dev_server.sh status       # check if dev server is running

set -euo pipefail

# Dev defaults: different port and data dir from production
PORT="${COMPLY_DEV_PORT:-9001}"
DATA_DIR="${COMPLY_DEV_DIR:-$HOME/.comply-dev}"
LOG_FILE="${DATA_DIR}/server.log"
PID_FILE="${DATA_DIR}/server.pid"

PERSONAS=(new_user single_repo multi_repo power_user journey)
DESCRIPTIONS=(
  "Empty DB — first-time user, no data"
  "1 repo, 3 frameworks, 6 scans, 1 gate, 1 monitor"
  "5 repos, mixed frameworks, gates, monitors, 2 programs"
  "12 repos, all frameworks, heavy usage (enterprise)"
  "Single repo full compliance journey (scan > remediate > gate > monitor)"
)

# ── Kill any existing dev server on this port ──────────────────────────
kill_server() {
  local pids
  pids=$(lsof -ti :"$PORT" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "Stopping dev server on port $PORT..."
    echo "$pids" | xargs kill 2>/dev/null || true
    sleep 2
    # Force-kill any stragglers
    pids=$(lsof -ti :"$PORT" 2>/dev/null || true)
    if [ -n "$pids" ]; then
      echo "$pids" | xargs kill -9 2>/dev/null || true
      sleep 1
    fi
    echo "Stopped."
  else
    echo "No dev server running on port $PORT."
  fi
  rm -f "$PID_FILE" 2>/dev/null
}

# ── Status check ───────────────────────────────────────────────────────
show_status() {
  local pids
  pids=$(lsof -ti :"$PORT" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "Comply dev server running on port $PORT (PID: $(echo $pids | tr '\n' ' '))"
    echo "  http://localhost:$PORT"
    echo "  Data: $DATA_DIR"
    echo "  Log:  $LOG_FILE"
  else
    echo "No dev server running on port $PORT."
  fi
}

# ── Pick persona ───────────────────────────────────────────────────────
pick_persona() {
  if [ $# -gt 0 ]; then
    PERSONA="$1"
    for p in "${PERSONAS[@]}"; do
      [ "$p" = "$PERSONA" ] && return 0
    done
    echo "Unknown persona: $PERSONA"
    echo "Available: ${PERSONAS[*]}"
    exit 1
  fi

  echo ""
  echo "=== Comply Dev Server (port $PORT, data: $DATA_DIR) ==="
  echo ""
  for i in "${!PERSONAS[@]}"; do
    printf "  %d) %-14s  %s\n" "$((i+1))" "${PERSONAS[$i]}" "${DESCRIPTIONS[$i]}"
  done
  echo ""
  read -rp "Pick a persona [1-${#PERSONAS[@]}]: " choice

  if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le "${#PERSONAS[@]}" ]; then
    PERSONA="${PERSONAS[$((choice-1))]}"
  else
    echo "Invalid choice."
    exit 1
  fi
}

# ── Reset and seed ─────────────────────────────────────────────────────
reset_and_seed() {
  echo ""
  echo "Resetting $DATA_DIR..."
  rm -rf "$DATA_DIR"
  mkdir -p "$DATA_DIR"

  if [ "$PERSONA" = "new_user" ]; then
    echo "Persona: new_user (empty DB, nothing to seed)"
  else
    echo "Seeding persona: $PERSONA..."
    COMPLY_DATA_DIR="$DATA_DIR" python3 -c "
import sqlite3, os
from comply.store import _ensure_schema
from comply.test_seed import seed_${PERSONA}

db_path = os.path.join(os.environ['COMPLY_DATA_DIR'], 'scans.db')
os.makedirs(os.path.dirname(db_path), exist_ok=True)
conn = sqlite3.connect(db_path)
_ensure_schema(conn)
seed_${PERSONA}(conn)
conn.close()
print('  Done.')
"
  fi
}

# ── Start server (backgrounded) ───────────────────────────────────────
start_server() {
  local version
  version=$(python3 -c 'from comply import __version__; print(__version__)')

  COMPLY_DATA_DIR="$DATA_DIR" bespoketracker-comply serve --port "$PORT" \
    > "$LOG_FILE" 2>&1 &
  local pid=$!
  echo "$pid" > "$PID_FILE"

  # Wait for it to be ready
  for i in $(seq 1 10); do
    if curl -sf "http://localhost:$PORT/health" > /dev/null 2>&1; then
      echo ""
      echo "Comply v$version dev server running (PID $pid)"
      echo "  http://localhost:$PORT"
      echo "  http://localhost:$PORT?seed=clear  (clear browser localStorage)"
      echo "  Data: $DATA_DIR"
      echo "  Log:  tail -f $LOG_FILE"
      echo ""
      echo "  ./dev_server.sh stop       stop the dev server"
      echo "  ./dev_server.sh journey    swap persona (stops, reseeds, restarts)"
      return 0
    fi
    sleep 0.5
  done

  echo "Warning: server started (PID $pid) but health check not responding yet."
  echo "  Check log: $LOG_FILE"
}

# ── Main ───────────────────────────────────────────────────────────────
case "${1:-}" in
  stop)
    kill_server
    exit 0
    ;;
  status)
    show_status
    exit 0
    ;;
  *)
    kill_server
    pick_persona "$@"
    reset_and_seed
    start_server
    ;;
esac
