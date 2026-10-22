# Mac handoff: local model and virtual reconnaissance

Clone the source and follow the Mac startup steps:

```bash
git clone https://github.com/bitfent/drone137.git
cd drone137
./scripts/bootstrap-macos.sh --minimal
./scripts/run-local.sh --mode recon --open-browser
```

Alternatively, transfer `dist/drone137-source.tar.gz` and its `.sha256` sidecar
from an exported handoff. Generated archives are not Git-tracked. The
source-manifest sidecar lists individual source hashes. Identify a checkout with
`git rev-parse HEAD` and an archive with its checksum. Neither establishes
successful fresh-cloud restoration.

```bash
shasum -a 256 -c drone137-source.tar.gz.sha256
tar -xzf drone137-source.tar.gz
cd drone137
./scripts/doctor.sh --profile lean-8gb --preflight-only
./scripts/bootstrap-macos.sh --minimal
./scripts/run-local.sh --mode recon --open-browser
```

`Start drone137.command` performs minimal bootstrap if necessary and starts the
same console. Python 3.11–3.14 is required. The native model installer requires an
Apple Silicon Mac, Git, Xcode command-line tools and CMake. The minimal GUI and
scripted sandbox do not require llama.cpp, Gazebo, PX4, Ollama, Node or npm.

## First session

The launcher now opens **Mission control** at `/control`. Select **Recon lab** in
its header for the setup/smoke checks below. Once Qwen is ready, return to Mission
control, choose an inspection area, write a brief and assign Scout 01/02. Generate
and review the plan before launch. Each aircraft takes its turn in the same indoor
site and saves separate video evidence. See [mission-control.md](mission-control.md)
for area semantics, stop/return behavior and the limitations of sequential dispatch.

**Aircraft profiles & camera settings** opens the SQLite hardware library at
`/airframes`. Create variants and assign exact revisions to each scout. See
[hardware-realism.md](hardware-realism.md) for native profile comparisons,
GPS-disabled observed-map navigation, room imports and offline calibration tools.
These native comparisons are separate from the dashboard's kinematic flights.
The three bundled quadcopter profiles are provisional; no physical measurements
have been supplied. Preserve `.local/data/airframes.sqlite3` with your evidence.

1. In Recon lab, run a **Scripted demo** in room seed 137. Confirm the onboard view moves, the
   map grows, the drone returns, and the report/video can be opened.
2. Generate seed 42, start a new demo and press **Test sensor loss**. The mission
   must fail with stale ranges and speed zero. Start another run, then close the
   browser: the controller must stop motion after its camera lease expires.
3. Install model prerequisites, then use the four local-model buttons in order:
   **Install runtime → Download / resume model → Start model → Test vision**.
   Downloads require outbound HTTPS to huggingface.co and its redirected model
   storage (typically hf.co / xethub.hf.co). No Hugging Face account is required
   for this public model. A proxy rejection must be resolved at the network.
4. Record the paired-image vision result and actual latency. Select **Local Qwen
   vision** and run a room. Confirm the report says `policy=qwen`, selected images
   match the scene, and observations reflect the images. Scripted evidence does
   not satisfy this check. A 6-second inference timeout requires model restart.
5. Run Warehouse aisle / Baseline / Patrol inspection points, open the saved HTML
   report, then load Passage obstructed and repeat. The next matching Qwen patrol
   compares separately classified images with the previous completed patrol.
   The corrected model pipeline detects the inserted blocker; review the current
   and previous images and the new-obstruction finding. Misaligned viewpoints
   are marked not assessed.
6. Select **Detailed workshop · 720p**, run a baseline patrol, and inspect the
   report’s full-image object descriptions and 720p video. Use **Enlarge camera**
   for the live view. Repeat with Passage obstructed to check the box stack.
   The camera approximates the standard Camera Module 3 field of view; physical
   lens/stream fidelity and full caption accuracy remain unmeasured.
7. Run multiple held-out seeds, review missed regions and changed viewpoints, and
   measure combined browser/controller/model RAM and swap. Actual 8 GiB acceptance
   remains pending; `lean-8gb` is a target, not a measured result.

Camera snapshots are bound to episode and observation tickets. Planar range
supervision runs separately from model decisions. This initial browser environment
has ideal pose/range sensors, static boxes, 1.4 m fixed altitude and kinematic
motion. It does not validate flight dynamics or physical obstacle avoidance.

## Models, evidence and shutdown

For real-environment qualification, use the separate
[reliability protocol](reliability-protocol.md). It covers all five requested
domains and imports labelled local clips/images into a frozen evaluation. Start
with recordings from the intended camera without drone flight. New output
directories preserve failures; a nonzero evaluation exit can mean a model miss,
with the complete report still saved. Public real-image smoke tests are not
deployment evidence. The local exposure ledger lives in `data/reliability` under
`DRONE137_DATA_DIR`; retain it when continuing held-out tests on another host.

`DRONE137_DATA_DIR` defaults to `.local/data`; models live in `models/`, evidence
in `runs/<episode>/`, and bounded runtime logs in `logs/`. Native builds default
to `.local/build`, configurable with `DRONE137_BUILD_DIR`.

The first model metadata fetch creates an immutable-revision manifest. Resume
uses that revision and checks range responses, exact size and SHA256. Complete
files are renamed atomically. Reset partials removes only known `.part` files;
corrupt installed models require explicit preservation/inspection before removal.
The runtime owns one llama-server process on loopback port 8081. No unrelated
Ollama or other model processes are killed.

Video, selected JPEGs, `world.json`, `events.jsonl` and `summary.json` share the
1 GiB evidence budget. Videos use the browser encoder; Chrome WebM was exercised
on both Linux and the M4 Mac; Safari/MP4 remains unverified. Reports link selected
images to approximate browser video positions. Telemetry
and video clocks do not provide exact exposure-time sync.
If a browser closes mid-run, partial footage remains and is marked incomplete.

Use Ctrl-C or `./scripts/stop-local.sh`. The parent launcher monitors app health
and terminates owned processes if it stalls. Model timeout/cancellation quarantines
that client; stop/start the model before retrying. Logs stop growing at 8 MiB and
require explicit archiving when full. No evidence is automatically removed.

## Optional native flight integration

Keep this separate from the browser patrol workflow. A real-Qwen native gate
route passed on M4/macOS 15.6: both gate labels correct, return and landing.
The newer hardware workbench also supports GPS-disabled PX4 local-position flight
using explicitly synthetic odometry; it does not yet derive VIO from real camera
images. Install Homebrew prerequisites first: `brew install pixi pkgconf cmake ninja`.

```bash
./scripts/install-sim.sh --profile lean-8gb
./scripts/stop-local.sh  # stop the recon app and its model before native startup
./scripts/run-local.sh --profile lean-8gb --mode sim --scenario courtyard --policy qwen
# In another terminal, grade observations as well as route completion:
./scripts/evaluate.sh --mode sim --episodes 1 --score-default-gates
```

The installer uses the pinned PX4 Pixi lock for Gazebo, a separate PX4 Python
environment, locked application MAVSDK dependencies, and compiles SITL/the camera
bridge. It does not invoke the broad upstream setup script or change system
compiler links. `scripts/with-sim.sh` supplies the locked runtime environment.
It plans for 25 GiB build space plus a 10 GiB reserve. The current
command above runs the legacy outdoor gate scenario using global waypoints. The
separate `scripts.evaluate_flight` workbench runs indoor local-position trials;
follow its profile and evidence requirements in the hardware guide. The bundled MAVSDK
server binds its unauthenticated gRPC service to `0.0.0.0:50051` even though MAVLink
and the app use loopback; restrict that service before any distributed deployment.
The native integration is for local simulation only. Intel Macs need a
separate runtime configuration and validation.

## Cloud settings

The cloud-environment-onboarding setup skill saves installation/start instructions
as a configuration draft. Review and save the draft in environment settings, then
publish to retain the prepared environment. Saving a draft does not apply its
network changes or establish restoration. The source archive remains the explicit
handoff artifact alongside the Git source checkout.

## Camera realism bay

Choose **Camera realism bay · 720p**, select a camera condition, load the
baseline and run a local-Qwen patrol. Repeat with **Passage obstructed** to review
change detection and unreached inspection points. Keep the seed and camera
condition the same when comparing runs. The report states the condition and saves
its exact settings. Object recognition stress evidence is in
`docs/realism-validation.json`; all five real deployment domains remain unqualified.
