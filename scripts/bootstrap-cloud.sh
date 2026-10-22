#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "${1:---minimal}" == "--minimal" ]] || { echo "Usage: $0 --minimal" >&2; exit 2; }
source ./scripts/select-python.sh
"$drone137_python" -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check --require-hashes -r requirements.lock
