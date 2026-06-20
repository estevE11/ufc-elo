#!/usr/bin/env bash
# Incremental data update: scrape new events, recompute Elo, refresh site stats.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "==> Incremental scrape"
python src/scrape_ufcstats.py --mode incremental --data-dir data

echo "==> Incremental Elo update"
python src/elo_engine.py --incremental

echo "==> Incremental site export"
python src/export_static_site.py --incremental

echo "==> Done."
