#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v python3 >/dev/null || { echo 'Install Python 3.11+ first.'; exit 1; }
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/geofolio init
exec .venv/bin/geofolio serve "$@"
