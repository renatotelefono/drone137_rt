#!/usr/bin/env bash
# Read-only preflight works before Python/package managers are installed.
set -euo pipefail
cd "$(dirname "$0")/.."
printf 'Host and architecture:\n'
uname -sm
if [[ "$(uname -s)" == Darwin ]]; then
  sw_vers
  sysctl -n hw.memsize
  sysctl -n machdep.cpu.brand_string
  vm_stat
  sysctl vm.swapusage
else
  [[ ! -r /proc/meminfo ]] || head -5 /proc/meminfo
fi
printf 'System/source free space:\n'
df -Pk / .
for target in "${DRONE137_DATA_DIR:-$PWD/.local/data}" "${DRONE137_BUILD_DIR:-$PWD/.local/build}"; do
  printf 'Configured path: %s\n' "$target"
  ancestor="$target"
  while [[ ! -e "$ancestor" ]]; do ancestor="$(dirname "$ancestor")"; done
  df -Pk "$ancestor"
done
for arg in "$@"; do
  if [[ "$arg" == "--preflight-only" ]]; then
    printf 'Read-only preflight complete. Native components and all acceptance gates remain pending.\n'
    exit 0
  fi
done
[[ -x .venv/bin/python ]] || { echo "Run minimal bootstrap to enable application diagnostics." >&2; exit 2; }
exec .venv/bin/python -m scripts.tools doctor "$@"
