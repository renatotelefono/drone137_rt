#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin ]] || { echo "This stage requires the target Mac." >&2; exit 2; }
./scripts/doctor.sh --profile lean-8gb --preflight-only
command -v python3 >/dev/null || { echo "Install native Python 3.11–3.14 before minimal bootstrap." >&2; exit 2; }
python3 - <<'PY'
import shutil
for path in ("/", "."):
    if shutil.disk_usage(path).free < 10.5*1024**3:
        raise SystemExit(f"{path}: minimal setup needs 0.5 GiB working allowance plus 10 GiB reserve")
PY
exec ./scripts/bootstrap-cloud.sh "${1:---minimal}"
