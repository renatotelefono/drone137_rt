# drone137

Local visual reconnaissance development for a confined space. The first runnable
product is a browser recon lab with a Python controller, a small local model
manager, and repeatable Three.js environments. No TypeScript or hosted inference is used.

**Microquad component lab:** `/components` stores swappable parts and pinned
assemblies in SQLite, with Rapier rigid-body physics rendered by Three.js.
Run it alone with `python -m scripts.component_lab --port 8152`. The five indoor
designs and two reference variants have completed a 42-case simulation study;
unmeasured component assumptions and failed gates remain explicit. See
[data sources, engine choice, results and limitations](docs/component-physics.md).
The revised controller and explicitly revised battery hypotheses complete 40/42
flight cases (95.2%), also 400/420 across additional noise seeds. The original
assemblies remain available; hardware, camera recognition and the revised
under-$50 parts budget are not qualified by this physics benchmark.

**Mission control:** `/control` now connects the SQLite aircraft assembly to
Rapier flight, a service-owned Three.js camera, local Qwen plus Florence image
verification, two-view localization, return/landing and video evidence. Write a
red fire extinguisher search brief, choose an inspection area and aircraft, review
the plan and launch. Flight/recording continue when the operator dashboard closes.
One aircraft flies at a time. The rectangle selects inspection stations; transit
can leave it. Known map geometry and ideal external positioning remain assumptions.
See [mission setup, API, tests and limitations](docs/mission-runtime.md).
The Scout 110-B completed **24/24 full missions** across eight known synthetic
cases repeated three times, with zero false confirmations, decodable video and
a 4.26 GiB peak application-memory measurement on a 16 GiB host. This is separate
from the component-only physics benchmark above. See the
[full mission qualification and retained failures](docs/mission-integration-validation.md).

The earlier sequential two-aircraft, kinematic mission console remains at
`/control-legacy`. It supports inventory, doorway and view-comparison experiments.
Concurrent flight and physical control are not enabled by either dashboard.

**Unknown-place experiment:** `/places` displays environments reconstructed from
onboard RGB images and synthetic IMU data, with named places, individual visits,
maps and image-backed model observations saved in SQLite. The experimental
OpenVINS mapper starts without a room map or true-position feedback. Development
flights now pass all gates, but the latest fresh-layout suite passed only **2/3**:
one layout failed coverage and boundary recall. Reliable unfamiliar-environment
exploration remains open; the earlier 24/24 known-map result does not qualify it.
See [the test and current architecture](docs/blind-exploration.md) and
[preserved result summaries](docs/blind-exploration-validation.json).

**Aircraft connection:** Mission Control's **Connect a drone** panel supports
pinned HTTPS pairing, telemetry and camera preview using the local protocol
emulator. The host adapter, ownership/deadline checks and sensor monitor pass
25 distinct automated tests. The emulator has no flight dynamics; matching
onboard flight firmware and physical navigation integration remain unfinished.
See [protocol and local setup](hardware/esp32/link-protocol.md) and the
[current handoff and remaining work](docs/agent-handoff.md).

For the first hardware prototype, use the
[Scout 110-B parts and bench build](hardware/esp32/indoor/scout-110-bench/README.md).
Its $45.09 consumed-parts allowance is not a delivered checkout quote. This
commercial-parts configuration is stored separately from the hypothetical
power-v2 aircraft used by earlier experiments. The final 24-mission qualification
uses the Scout 110-B assembly itself. Flight firmware, measured
component data and real indoor positioning remain hardware work.

**Object-location experiment:** compare the current Qwen model with Qwen plus
local Laya on a search for a red fire extinguisher. Both use camera images and
two-view bearing triangulation, with a sampled 5 GiB application-memory guard.
See [setup, protocol and limitations](docs/localization-experiment.md). This is
a separate camera-station experiment; it does not add physical flight control.

**Dense native-flight experiment:** a 120-prop workshop now runs actual PX4/Gazebo
rotor dynamics beneath the Three.js camera. Qwen and Qwen+Laya search during
continuous takeoff, transit, inspection, return and landing, with estimated-pose
triangulation, draft disturbance, telemetry and video evidence. See
[the flight-test protocol](docs/native-flight-experiment.md). The original kinematic product remains at `/control-legacy`; this native PX4 backend is an evaluation lab. The newer `/control` uses the component-based Rapier backend described above.
The [identity improvement experiment](docs/identity-improvement.md) separates
visible-part checks from triangulation and compares the 2B and 4B vision models
without loading both together. Its saved-frame diagnostic is not a real-world
qualification score.
The revised 2B full-flight batch completed 3/4 jobs with no false location
claims; 4B completed 1/4 under the same checks. A later 2B low-light repeat
passed, but the earlier miss remains evidence of inconsistent recognition.

The [real-room qualification plan](docs/real-room-qualification.md) adds a frozen
eight-mission challenge for Qwen 2B plus Laya: unfamiliar furniture arrangements,
paired present/absent targets, partial occlusion, glare/dim/blur conditions and
delayed/dropped camera frames. It also documents where offline Glob3R room
reconstruction can help, what remains unimplemented, and why a finite all-pass
test does not establish universal 100% accuracy.
Its first hard-suite Qwen + Laya run scored **5/8**, including one wrong-object
claim; all eight flights landed. Peak application guard memory was 3.48 GiB on
the 16 GiB host. The target-present success rate was 1/4, so reliable object
verification remains unresolved despite successful flight execution.

The [imported asset experiment](docs/online-assets-experiment.md) adds CC0
extinguisher, cart, shelving and crate models plus photographed workshop HDR
lighting, all bundled locally with verified hashes and aligned collision bounds.
The same Qwen 2B + Laya hard suite scored **6/8**, with two target-present
successes, one miss and one wrong-object claim. All eight flights landed;
peak application guard memory was **3.54 GiB** on the 16 GiB host. Use
`--assets polyhaven` with `scripts.evaluate_flight` to reproduce this variant.
The scene is assembled from assets, not a reconstructed real building.

The [efficiency audit](docs/efficiency.md) makes route planning 8.25× faster in
a 40-route CPU benchmark with identical paths. Fixed-input repeats reproduced
16/16 vision outputs and 22/22 Laya choices; 133 tests and a native flight smoke
test passed. This is a behavior-preserving planner optimization, not a new full
mission accuracy result or an end-to-end speedup claim.

## Start on a Mac

Requires Python 3.11–3.14 and a current browser with WebGL and MediaRecorder.
The model runtime installer targets **Apple Silicon**; Intel Macs and actual
8 GiB performance have not been validated. Local Qwen/Metal runs on the tested M4
with 16 GiB; recognition accuracy still needs improvement.

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

For model installation and the earlier single-aircraft smoke test, open
`http://127.0.0.1:8137/`:

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

- Generates repeatable random rooms, warehouse aisles and connected rooms.
- Runs inspection-point patrols with baseline and obstructed-passage variants;
  returns with a partial report when an inspection point cannot be reached.
- Simulates ideal pose and planar range sensing; builds an observed occupancy map.
- Plans clearance-aware routes through observed free cells, explores new areas,
  and returns home after up to 12 observations. Mission deadline: 180 seconds.
- Provides overhead and onboard cameras. The local model sees selected fresh
  320 × 240 JPEGs and can continue, request one additional left/right view, hold,
  or finish an exploration. Patrols restrict it to continue, extra views or hold;
  one blank view cannot finish the whole patrol. The model cannot issue arbitrary
  coordinates or motor commands.
- Runs range supervision independently of inference; sensor loss, browser/camera
  loss, inference errors and operator intervention stop motion.
- Records browser video (WebM or MP4), selected images, pose/event timestamps,
  scene seed and observations. Saved missions open an HTML report with video
  seek links, images, observed map, route and unreached points. Matching local-model
  patrols compare independently classified images at aligned viewpoints and flag
  a new obstruction when open space becomes a solid surface. Evidence shares a 1 GiB cap.

The mission-control dashboard is a **fixed-altitude kinematic sandbox**. The
separate native-flight evaluation lab above uses PX4/Gazebo dynamics; neither
path has been qualified against a physical aircraft.
Map-observed percentage is geometric sensor coverage, not camera visibility or
semantic recognition accuracy. Sensors/pose are ideal; there is no SLAM, sensor
noise, dynamic-obstacle prediction, full 3D planning or physical drone connection.
Observation seek links use approximate browser video time; exact exposure/pose
alignment remains unverified.
Pause ends autonomous progress; end the mission before starting another. Keep the
browser tab active: camera/browser loss stops the virtual mission after 2 seconds.

## Validation and current limits

**Simulation versus real-drone comparison:** [test data and comparison tables](docs/test-comparison.md)
preserve Scout 110-B component/mission results, blind-mapping failures, the
historical vision-model comparison and separate software-test counts. A
[frozen JSON baseline](docs/test-data/pre-hardware-2026-10-23.json) retains exact
values and source hashes, and a [physical-run template](docs/test-data/hardware-run-template.json)
is ready for measured hardware results. No physical flight results exist yet;
unmeasured values stay empty rather than being presented as passes.

Real-world reliability is now tracked separately for **workshops, warehouses,
building perimeters, flat fields and hillsides**. All five remain unqualified.
The frozen real-camera smoke test found 11 of 12 labelled object names across six
public indoor images, with one missed object group. This is diagnostic evidence,
not a general accuracy or flight claim. The [reliability protocol](docs/reliability-protocol.md)
defines data collection, site separation, proposed thresholds and commands to
evaluate local camera clips without flying a drone. Full-caption precision and
site-specific data remain missing.

Current Mac and historical Linux evidence is in [docs/validation.md](docs/validation.md).
The M4 build ran actual Qwen/Metal patrols, recorded playable video and generated
reports. The original closed-gate and changed-passage misses are retained as
regressions. Separating image evidence from action selection, with settings for each camera
profile, passes all 32 center-classification cases (24 rendered views plus eight regressions), with
zero blocked views classified as open. Successful recording/navigation alone does
not prove perception accuracy; the patrol browser test also checks recognition.
104 accelerated geometry scenarios returned with zero clearance violations. A
separate real-Qwen PX4/Gazebo gate route correctly classified both gates and
returned to land; indoor patrol is not yet connected to that dynamics backend.
The GUI reports failures explicitly and never switches to scripted decisions itself.

For richer visual inspections, choose **Detailed workshop · 720p → Baseline →
Patrol inspection points**. The scene contains stocked shelving, labeled cartons,
a workbench with monitor/keyboard/toolbox/vise/cable, drums on a pallet, a hand
truck, tool drawers, a plant and a fire extinguisher. Geometry and canvas labels
are generated locally; there are no runtime asset downloads. The report adds a
whole-image object description and visible uncertainty beside each camera image.

The workshop records **1280 × 720 at a requested 15 fps**, with **960 × 540** model
snapshots. Its 41° vertical field of view approximates the standard Camera Module 3
candidate in the project brief ([manufacturer specifications](https://www.raspberrypi.com/documentation/accessories/camera.html)).
This is an ideal rendered camera, not a calibrated physical-camera or photorealism
benchmark. Use **Enlarge camera** to inspect the detail. Older simple scenes retain
their 320 × 240 profile.

Choose **Camera realism bay · 720p** for bottles, a wheeled chair and a safety cone
alongside the stocked workshop and cluttered bench. Its local scanned concrete
maps add surface detail. **Camera conditions** selects nominal, low light, glare,
or blur/shift stress. The camera points down 10°; exposure, noise, blur, lens warp
and vignetting are synthetic settings, not hardware calibration. The displayed
camera, recorded video and model snapshots share that processed image. Conditions
are saved in each report and must match when selecting a comparison baseline.
Geometry/range sensing and fixed-height motion still use the ideal sandbox.

To try the product: choose **Warehouse aisle → Baseline → Patrol inspection points**,
start a patrol, open its report, then load **Passage obstructed** and repeat. Use
Local Qwen for observations, or Scripted demo to test the pipeline without inference.

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
# With the recon app running; set CHROMIUM_PATH for your browser:
CHROMIUM_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" node scripts/check-browser.cjs
# Two rendered warehouse patrols; real Qwen must already be running:
DRONE137_TEST_POLICY=qwen node scripts/check-patrol.cjs
# Fresh rendered perception cases, scored with the same production model pipeline:
node scripts/render-vision-cases.cjs
.venv/bin/python -m scripts.evaluate_perception
# Detailed camera/object recognition and complete workshop patrols:
node scripts/render-detail-cases.cjs
.venv/bin/python -m scripts.evaluate_detail
DRONE137_TEST_POLICY=qwen DRONE137_TEST_SCENARIO=workshop node scripts/check-patrol.cjs
# Accelerated navigation-only suite, no browser/model/dynamics:
.venv/bin/python -m scripts.evaluate_recon --episodes 100
# Production camera stress set (local model ready, no active mission):
DRONE137_REALISM_CASES=.local/validation/my-realism-cases node scripts/render-realism-cases.cjs
.venv/bin/python -m scripts.evaluate_reliability freeze --manifest .local/validation/my-realism-cases/manifest.json --lock .local/validation/my-realism-cases/frozen.json
.venv/bin/python -m scripts.evaluate_reliability run --manifest .local/validation/my-realism-cases/manifest.json --lock .local/validation/my-realism-cases/frozen.json --output .local/validation/my-realism-results
DRONE137_TEST_POLICY=qwen DRONE137_TEST_SCENARIO=realism node scripts/check-patrol.cjs

# Frozen real-image/recorded-video evaluation: see docs/reliability-protocol.md
.venv/bin/python -m scripts.evaluate_reliability --help
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

The [hardware realism workbench](docs/hardware-realism.md) adds a SQLite aircraft
library, frozen quadcopter profiles, parameterized optics, GPS-disabled native
sensor emulation, observed-map routing and offline camera/room/motor calibration
tools. Open `/airframes` from mission control. Profiles are provisional until
measurements are supplied; native comparisons run sequentially.

The optional live vision comparison flies Qwen alone, Qwen + Florence-2-base-ft,
and Qwen + SmolVLM2-500M through the same four glare/occlusion missions, including
target-absent controls. Each companion receives live camera crops; Qwen supervises
search in all three arms. The aircraft must first pass measured rotor-joint,
lift-off, hover and landing checks. This is a synthetic development benchmark,
not physical-world qualification. The application guard is 5 GiB, leaving intended
headroom on an 8 GB host; actual 8 GB hardware still requires validation.

```bash
python3.12 -m venv .local/vision-env
.local/vision-env/bin/python -m pip install -r requirements-vision-reviewers.txt
.local/vision-env/bin/python scripts/download_vision_reviewers.py
# Requires the existing native simulator, camera runtime and idle local Qwen app.
.local/laya-env/bin/python -m scripts.evaluate_flight \
  --output .local/validation/my-aircraft-check --suite realism --assets polyhaven \
  --airframes reference-quad@1 --navigation observed --smoke \
  --cases realism-east-motion-present
.local/laya-env/bin/python -m scripts.compare_vision_flights \
  --output .local/validation/my-vision-flight-comparison \
  --preflight .local/validation/my-aircraft-check/results.json
```

Use new output directories for each attempt. Reports retain failed missions and
separate physical flight checks, targets found, false location claims, latency,
memory and full acceptance. Checkpoint revisions and file hashes are recorded.

Measured live results and their limits are in
[the flight comparison](docs/vision-flight-comparison.md). For a separate bounded
closer-view experiment, add `--inspection-policy active-v2` to `evaluate_flight`.
This changes evidence acquisition while retaining the original identity gates;
keep it separate from comparisons of models under the default inspection policy.
