#!/usr/bin/env bash
# Source this file from a bootstrap script. Finder often selects Apple's Python 3.9.
drone137_python=""
for candidate in "${DRONE137_PYTHON:-}" python3 python3.14 python3.13 python3.12 python3.11 \
  /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 \
  /opt/homebrew/bin/python3.11 /usr/local/bin/python3; do
  [[ -n "$candidate" ]] || continue
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c \
    'import sys; raise SystemExit(not ((3, 11) <= sys.version_info < (3, 15)))' 2>/dev/null; then
    drone137_python="$(command -v "$candidate")"
    break
  fi
done
if [[ -z "$drone137_python" ]]; then
  echo 'Python 3.11–3.14 is required. Install it or set DRONE137_PYTHON to its executable.' >&2
  exit 2
fi
