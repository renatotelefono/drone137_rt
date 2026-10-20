#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  ./scripts/bootstrap-macos.sh --minimal
fi
exec ./scripts/run-local.sh --mode recon --open-browser
