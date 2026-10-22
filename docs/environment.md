# Environment record

## Current Mac validation, 20 October 2026

Apple M4, 16 GiB physical memory, macOS 15.6, arm64. Python 3.12.13
from Homebrew; the system Python 3.9 is bypassed by bootstrap's interpreter selection.
Approximately 81 GiB was free before native installs. This is not an 8 GiB test.

Installed and exercised locally: locked application dependencies, Chrome with
native WebGL, Playwright 1.58.2 in the ignored test directory, pinned llama.cpp
with Metal, official Qwen3-VL-2B Q4_K_M and its Q8_0 projector, PX4 SITL,
Gazebo Harmonic 8.10.0 from PX4's locked Pixi environment, MAVSDK 3.17.4 and the
native JPEG bridge. Homebrew Pixi/pkgconf were installed; no system compiler
symlinks or XQuartz installation were performed.

The actual local model ran patrols. Initial gate/blocker misses were reproduced
and corrected by separating visual evidence from action selection. The updated
pipeline passes the paired check and 30 labeled image cases. A real-Qwen
PX4/Gazebo takeoff/inspection/return/landing passed with both gate labels correct. Indoor recon still uses kinematics;
the native gate route uses global navigation. Physical transport remains disabled.

Model/build artifacts are local and ignored by Git. Exact revisions and model
SHA256 values are in `versions.json`. The model repository lacks a LICENSE file;
its pinned model card declares Apache-2.0. The installer saves that declaration,
a copy of the standard Apache licence and its checksum as provenance.

## Historical cloud host

Cloud inspection: Linux 6.18.55, x86_64, host `25eaecfa9f86`, Python 3.12.14.
Five logical CPUs were visible. `/proc/meminfo` reported about 33.3 GiB host RAM;
this is not a measured container allowance or a Mac memory benchmark.
Approximately 29.8 GiB filesystem space was available before setup.

Working profile: `cloud-dev`. Native Metal, Gazebo, PX4 and llama-server were absent.
No model weights or simulator stack were downloaded. GitHub read access succeeded.
The official Hugging Face model-metadata request returned proxy HTTP 403.

Minimal bootstrap uses a local `.venv` and hash-locked Python dependencies.
Optional MAVSDK 3.17.4 was installed on this Linux host to inspect its actual API.
Its native flight connection and server were not used as a flight test.

At the time of this cloud run, target Mac characteristics were unknown. The
current native observations are recorded above.

Every fixture report records `real_inference=false`, `real_camera=false`,
`real_flight_dynamics=false` and `physical_transport=false`.

The current default mode is the browser-kinematic recon lab. Three.js 0.180.0 is
vendored; Chromium 154.0.8037.57 with software WebGL exercised the GUI and recorded
video on Linux. Playwright 1.58.2 was installed only in an ignored developer-test
directory, not the application dependency set. See recon-browser-results.json.
