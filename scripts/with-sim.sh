#!/usr/bin/env bash
# Run a command in PX4's project-local, locked Gazebo environment.
set -e
cd "$(dirname "$0")/.."
drone137_px4="${DRONE137_BUILD_DIR:-$PWD/.local/build}/PX4-Autopilot"
drone137_sim_prefix="$drone137_px4/Tools/setup/macos/.pixi/envs/default"
[[ -x "$drone137_px4/.venv/bin/python" && -d "$drone137_sim_prefix" ]] || {
  echo 'Install the local PX4 Python and locked Gazebo environments first.' >&2; exit 2;
}
source "$drone137_px4/.venv/bin/activate"
export CONDA_PREFIX="$drone137_sim_prefix"
export PATH="$VIRTUAL_ENV/bin:$CONDA_PREFIX/bin:$PATH"
export CMAKE_PREFIX_PATH="$CONDA_PREFIX${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
for drone137_activation in "$CONDA_PREFIX"/etc/conda/activate.d/*.sh; do
  source "$drone137_activation"
done
exec "$@"
