#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${LLM_WIKI_DATA_DIR:-/home/standard/llm-wiki-data}"
VAULT="$DATA_DIR/vault"
REMOTE="${RCLONE_REMOTE:-gdrive:llm_wiki}"
FILTER_FILE="$DATA_DIR/config/rclone-filter"
LOG_DIR="$DATA_DIR/agent-state/logs"
LOCK_DIR="$DATA_DIR/agent-state/locks"
LOG_FILE="$LOG_DIR/rclone-bisync.log"
LOCK_FILE="$LOCK_DIR/drive-sync.lock"
CONTAINER="${LLM_WIKI_CONTAINER:-llm-wiki-agent}"

mkdir -p "$LOG_DIR" "$LOCK_DIR"

exec 9>"$LOCK_FILE"

if ! flock -n 9; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] sync skipped: lock exists" >> "$LOG_FILE"
  exit 0
fi

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') bisync start ====="

  rclone bisync "$REMOTE" "$VAULT" \
    --filter-from "$FILTER_FILE" \
    --create-empty-src-dirs \
    --verbose

  echo "===== $(date '+%Y-%m-%d %H:%M:%S') bisync done ====="

  echo "===== raw scan trigger ====="
  docker exec "$CONTAINER" python -m agent.raw_scanner || true

  echo "===== qmd refresh trigger ====="
  docker exec "$CONTAINER" python -m agent.qmd_client || true
} >> "$LOG_FILE" 2>&1
