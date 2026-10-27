# Windows: what is ported, what is not yet verified

Status: ported on 27 October 2026 on a Mac, without a Windows machine. Every Mac-only refusal in
the code has a Windows path, each path is unit-tested on macOS where the same code runs, and
nothing has been executed on Windows. This page is the hand-over to the developer who will.

## What is in place

| Piece | Where | Windows path |
| --- | --- | --- |
| Launcher | `Start drone137.bat`, `scripts/run-local.ps1`, `scripts/launch.py` | Bootstraps the environment if missing, starts the console; the launcher's stop channel is a loopback TCP port written to `.local/control.port` instead of a Unix socket |
| Bootstrap | `scripts/bootstrap-windows.ps1` | Python 3.11 to 3.14 through the `py` launcher, the virtual environment from the hash-locked `requirements.lock` plus `requirements-mission.txt`, Node and Playwright 1.58.2 for the simulated camera, a Chrome, Chromium or Edge found or `CHROMIUM_PATH` asked for |
| Owned processes | `app/portability.py`, `app/watchdog.py` | New process group on spawn; stops go to the whole process tree through psutil instead of `killpg` |
| Ctrl-C and stop | `app/portability.py` | asyncio signal handlers where the loop has them, `signal.signal` with SIGINT, SIGTERM and SIGBREAK on Windows |
| Model runtime | `config/runtime-windows.json`, `scripts/tools.py`, `app/model_manager.py` | The console's "Install runtime" unpacks a pinned llama.cpp release (b11763, the same source the Mac build is pinned to) instead of building: `vulkan` by default, `cpu` or `cuda` with `DRONE137_RUNTIME_BACKEND`; every archive is refused unless its SHA-256 matches the pinned digest from the GitHub release; the server starts with all layers on the GPU for Vulkan and CUDA, none for CPU |
| Person detector | `app/person_detector.py`, `config/person-detector.json`, `scripts/fetch_person_model.py` | MobileNet-SSD through OpenCV's DNN (MIT licence), the two files fetched and verified by size and git blob SHA-1, their SHA-256 recorded with `--record`; Apple's framework stays the macOS backend |
| Browser for the simulated camera | `scripts/browser-path.cjs` | Program Files and per-user Chrome, Edge and Chromium looked up; `CHROMIUM_PATH` overrides |
| Memory check | `app/memory_budget.py` | The macOS physical-footprint call is guarded; elsewhere resident memory is used |
| Linux | `scripts/tools.py` | The runtime builds from the pinned source without Metal; the rest is the same as Windows |

Tests: `tests/test_portability.py` (process trees, stop handlers, the loopback control channel,
the runtime plan and digest pins, browser candidates, the detector's backend choice, the blob
hash). They run on macOS against the same code the Windows branches use.

## What the Windows developer has to do, in order

1. **Fresh clone on a Windows 11 x64 machine with a GPU.** Run `Start drone137.bat`. It calls
   `scripts\bootstrap-windows.ps1`. Expect the first problems here: `requirements.lock` was
   exported on macOS and must contain Windows wheel hashes for every package; a missing hash
   fails the install and the fix is to re-export the lock with Windows wheels included.
2. **Scripted demo without AI.** In the console choose "Scripted demo, no AI" and start a recon.
   This exercises Node, Playwright, the browser and the physics worker. The physics worker has a
   0.5 s wall-clock deadline; check it holds on the machine.
3. **Runtime and model.** "Install runtime" then "Download model". Check `.local\data\installed\llama.json`
   says the backend you meant. If the GPU is NVIDIA and Vulkan is slow, set
   `DRONE137_RUNTIME_BACKEND=cuda` and install again. Then "Start model", "Test vision".
4. **Person detector.** `python -m scripts.fetch_person_model --record`, then
   `python -m unittest tests.test_person_detector`. The Apple tests skip; add a MobileNet-SSD test
   on `tests/fixtures/person-public-domain.jpg` once the files are present, and measure it on the
   rendered watch set (`python -m scripts.qualify_watch --model --set .local\validation\watch-rendered`
   after rendering it with `python -m sim.watch_render`).
5. **The gates.** `scripts.qualify_docking`, `scripts.qualify_watch`, `scripts.qualify_swarm`
   with both plants. Their numbers are Mac numbers; record the Windows ones beside them.
6. **Memory.** The baselines in `config/memory-baselines.json` were measured on a Mac. Run the
   measured preflight from the console and let it learn the Windows figures; then re-read the
   8 GB arithmetic in `docs/airspace.md` against them.
7. **Signals.** Ctrl-C in the console window and `scripts\run-local.ps1 --stop` must both leave no
   `node.exe` or `llama-server.exe` behind. That is the process-tree stop in
   `app/portability.py`; check Task Manager after each.

## Known differences that stay

- The person detector on Windows is MobileNet-SSD, not Apple's framework. It is a weaker
  detector; its miss rate on this project's frames is unmeasured.
- A CPU-only machine runs the vision model in tens of seconds per answer. The product needs a
  GPU with a Vulkan or CUDA driver.
- The hardware tools for the carrier board and the dock (OpenSCAD, the ESP32 toolchain) have
  their own installers and were not part of this port.
