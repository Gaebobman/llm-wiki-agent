#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${LLM_WIKI_DATA_DIR:-/home/standard/llm-wiki-data}"

required=(
  "$DATA_DIR/vault/raw/sources"
  "$DATA_DIR/vault/wiki/sources"
  "$DATA_DIR/agent-state"
  "$DATA_DIR/config"
  "$DATA_DIR/secrets"
)

for path in "${required[@]}"; do
  if [[ -e "$path" ]]; then
    echo "ok: $path"
  else
    echo "missing: $path"
  fi
done
