# drone137

Local visual reconnaissance development for a confined space. The first runnable
product is a browser recon lab with a Python controller, a small local model
manager, and a Three.js virtual room. No TypeScript or hosted inference is used.

## Start on a Mac

Requires Python 3.11–3.14 and a current browser with WebGL and MediaRecorder.
The model runtime installer targets **Apple Silicon**; Intel/Metal and actual
8 GiB performance have not been validated.

```bash
git clone https://github.com/bitfent/drone137.git
cd drone137
./scripts/bootstrap-macos.sh --minimal
./scripts/run-local.sh --mode recon --open-browser
```

Alternatively, open **Start drone137.command** in the extracted project. The
launcher bootstraps the small Python environment if missing and opens the local
console. If Finder blocks execution, run the shell commands above in Terminal.
The service binds only to `127.0.0.1:8137`; Ctrl-C stops its owned processes.

In the GUI:

1. Choose **Scripted demo · no AI**, generate a room seed, and **Start recon** to
   test rendering, navigation, recording and failure handling without model weights.
2. For local vision, install Xcode command-line tools (`xcode-select --install`),
   Git and CMake (`brew install cmake`, assuming Homebrew is already installed).
3. Click **Install runtime**, then **Download / resume model**. The manager builds
   pinned llama.cpp and retrieves Qwen3-VL-2B-Instruct Q4_K_M plus its Q8_0 vision
   projector. It pins the official model commit and verifies both SHA256 hashes.
4. **Start model**, **Test vision**, then select **Local Qwen vision** and start a
   mission. A failed vision check needs investigation before relying on observations.

The GUI exposes progress, errors, cancellation, file verification, bounded logs,
and model stop/restart. Interrupted downloads retain resumable partials. Corrupt
installed files are preserved for inspection; they are never silently used.
Keep 10 GiB free **in addition** to remaining model downloads or the 4 GiB runtime
build allowance. Actual combined resource use still needs measurement on the Mac.

## What the virtual product does

- Generates repeatable 12 × 10 m rooms containing randomized static obstacles.
- Simulates ideal pose and planar range sensing; builds an observed occupancy map.
- Plans clearance-aware routes through observed free cells, explores new areas,
  and returns home after up to 12 observations. Mission deadline: 180 seconds.
- Provides overhead and onboard cameras. The local model sees selected fresh
  320 × 240 JPEGs and can continue, request one additional left/right view, hold,
  or finish. The model cannot issue arbitrary coordinates or motor commands.
- Runs range supervision independently of inference; sensor loss, browser/camera
  loss, inference errors and operator intervention stop motion.
- Records browser video (WebM or MP4), selected images, pose/event timestamps,
  scene seed, observations and a downloadable report. Evidence shares a 1 GiB cap.

This is a **fixed-altitude kinematic sandbox**, not a validated flight simulator.
Map-observed percentage is geometric sensor coverage, not camera visibility or
semantic recognition accuracy. Sensors/pose are ideal; there is no SLAM, sensor
noise, dynamic-obstacle prediction, full 3D planning or physical drone connection.
Video chunk timestamps represent host receipt, not exact camera exposure alignment.
Pause ends autonomous progress; end the mission before starting another. Keep the
browser tab active: camera/browser loss stops the virtual mission after 2 seconds.

## Validation and current limits

Linux browser and automated test evidence is in [docs/validation.md](docs/validation.md).
The old gate fixture is retained as a separate regression workflow.
**Actual Qwen inference and native Mac/Metal execution remain unverified here:**
Hugging Face downloads are blocked by this cloud network's HTTP 403 response.
Local HTTP download/inference contract tests are not real-model inference tests.
The GUI reports failures explicitly and never switches to scripted decisions itself.

The [Mac handoff](docs/handoff.md) contains transfer, startup and acceptance steps.
[Recon objective](docs/recon-objective.md) separates implemented workflow from the
remaining localization, camera-coverage and flight-dynamics work.

## Development

```bash
# Linux/cloud, or a development machine with Python 3.11–3.14:
./scripts/bootstrap-cloud.sh --minimal
./scripts/test-portable.sh
./scripts/run-local.sh --mode recon
# A second terminal can stop this app:
./scripts/stop-local.sh
```

Three.js 0.180.0 is vendored with its MIT licence and verified npm integrity
metadata, so the GUI does not require Node, npm or a CDN at runtime. Python
packages are installed from hash-locked requirements. Source export:

```bash
./scripts/export-handoff.sh
```

`dist/drone137-source.tar.gz` and its checksum sidecar exclude model weights,
virtual environments, native builds, caches and bulk run evidence. Configurable
paths: `DRONE137_DATA_DIR` (default `.local/data`) and `DRONE137_BUILD_DIR`
(default `.local/build`). Completed runs remain under `.local/data/runs/<episode>`;
no automatic evidence deletion occurs.

Optional browser integration test, using an installed Chromium:

```bash
npm install --prefix .local/browser-test playwright@1.58.2
# With the recon app running; default CHROMIUM_PATH=/usr/bin/chromium:
node scripts/check-browser.cjs
```

The scripted browser check exercises a full mission, decodes its video, runs a
sensor failure mission. Set `DRONE137_EXPECT_MODEL_NETWORK_BLOCK=1` only on this
restricted cloud network to also exercise its expected HTTP 403 download error. It is an optional developer check, not a product dependency.

Legacy gate fixture:

```bash
./scripts/run-local.sh --mode fixture --profile cloud-dev --policy scripted
./scripts/evaluate.sh --suite smoke --mode fixture --episodes 2
```

Native Gazebo/PX4 gate integration remains experimental and requires separate
large installations. See `docs/handoff.md`; it does not yet implement indoor recon.
