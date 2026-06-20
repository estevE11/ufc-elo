#!/usr/bin/env bash
# Full rebuild of static site data for GitHub Pages.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "==> Full Elo recompute"
python src/elo_engine.py

echo "==> Full site export"
python src/export_static_site.py

echo "==> Done. Site files are in docs/"
echo "    Enable GitHub Pages: Settings → Pages → Deploy from /docs on main"
