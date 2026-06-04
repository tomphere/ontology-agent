#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
EXPORT_DIR="${1:-$(dirname "$PROJECT_ROOT")/ontology-agent-github-export}"

if [ -e "$EXPORT_DIR" ]; then
  echo "Export directory already exists: $EXPORT_DIR" >&2
  exit 1
fi

mkdir -p "$EXPORT_DIR"

rsync -a \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --include '.env.example' \
  --exclude 'datasources.yaml' \
  --exclude 'data/' \
  --exclude 'ontology_workspace/' \
  --exclude 'node_modules/' \
  --exclude 'frontend/node_modules/' \
  --exclude 'frontend/dist/' \
  --exclude '.venv/' \
  --exclude 'venv/' \
  --exclude 'env/' \
  --exclude '.pytest_cache/' \
  --exclude '.gemini/' \
  --exclude '.DS_Store' \
  --exclude '*.db' \
  --exclude '*.db-shm' \
  --exclude '*.db-wal' \
  --exclude '*.sqlite3' \
  "$PROJECT_ROOT/" "$EXPORT_DIR/"

cd "$EXPORT_DIR"

echo "Created clean export: $EXPORT_DIR"
echo
echo "Run this scan before publishing:"
echo '  rg -n -i "(api[_-]?key|secret|password|passwd|pwd|token|authorization|bearer|jwt|private key|sk-|pk-|gpustack_|ark-|172\\.16\\.|/Users/)" .'
echo
echo "Then initialize a fresh repository:"
echo "  git init"
echo "  git add ."
echo "  git commit -m 'Initial public release'"
