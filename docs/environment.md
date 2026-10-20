# Environment record

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

The target Mac mini's 16 GB RAM and roughly 200 GB total storage come from the
supplied brief. They are not observations of this machine. CPU/chip, macOS,
free storage, Metal performance and simulator compatibility remain unknown.

Every fixture report records `real_inference=false`, `real_camera=false`,
`real_flight_dynamics=false` and `physical_transport=false`.

The current default mode is the browser-kinematic recon lab. Three.js 0.180.0 is
vendored; Chromium 154.0.8037.57 with software WebGL exercised the GUI and recorded
video on Linux. Playwright 1.58.2 was installed only in an ignored developer-test
directory, not the application dependency set. See recon-browser-results.json.
