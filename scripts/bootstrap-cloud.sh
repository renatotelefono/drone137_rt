#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "${1:---minimal}" == "--minimal" ]] || { echo "Usage: $0 --minimal" >&2; exit 2; }
python3 -c 'import sys; assert (3,11) <= sys.version_info < (3,15), "Python 3.11–3.14 required"'
python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check --require-hashes -r requirements.lock
