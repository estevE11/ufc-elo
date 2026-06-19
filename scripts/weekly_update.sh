#!/usr/bin/env bash
# Weekly UFC data update: incremental scrape, then commit and push CSVs.
#
# Cron example (Mondays at 6:00 AM):
#   0 6 * * 1 /path/to/ufc-elo/scripts/weekly_update.sh >> /path/to/ufc-elo/scrape.log 2>&1

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "error: .venv not found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

echo "[$(date -Iseconds)] Starting incremental scrape..."
"$PYTHON" "$ROOT/src/scrape_ufcstats.py" --mode incremental --data-dir "$ROOT/data"

git add data/fighters.csv data/fights.csv

if git diff --cached --quiet; then
  echo "[$(date -Iseconds)] No data changes; skipping commit and push."
  exit 0
fi

DATE="$(date +%Y-%m-%d)"
git commit -m "$(cat <<EOF
Update UFC data ($DATE).

Incremental scrape from ufcstats.com.
EOF
)"
git push origin main
echo "[$(date -Iseconds)] Committed and pushed."
