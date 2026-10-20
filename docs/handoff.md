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

1. Run a **Scripted demo** in room seed 137. Confirm the onboard view moves, the
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
5. Run multiple held-out seeds, review missed regions and changed viewpoints, and
   measure combined browser/controller/model RAM and swap. Actual 8 GiB acceptance
   remains pending; `lean-8gb` is a target, not a measured result.

Camera snapshots are bound to episode and observation tickets. Planar range
supervision runs separately from model decisions. This initial browser environment
has ideal pose/range sensors, static boxes, 1.4 m fixed altitude and kinematic
motion. It does not validate flight dynamics or physical obstacle avoidance.

## Models, evidence and shutdown

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
in cloud testing, while native Safari/MP4 remains unverified. Telemetry and video
chunk receipt timestamps aid review but do not provide exact exposure-time sync.
If a browser closes mid-run, partial footage remains and is marked incomplete.

Use Ctrl-C or `./scripts/stop-local.sh`. The parent launcher monitors app health
and terminates owned processes if it stalls. Model timeout/cancellation quarantines
that client; stop/start the model before retrying. Logs stop growing at 8 MiB and
require explicit archiving when full. No evidence is automatically removed.

## Optional native flight integration

Keep this separate from the first browser workflow. It remains unverified on Mac:

```bash
./scripts/install-sim.sh --profile lean-8gb
./scripts/run-local.sh --profile lean-8gb --mode sim --scenario courtyard --policy scripted
# Stop, then use --policy qwen only after native prerequisites and vision pass.
```

The installer invokes the pinned PX4 macOS setup (Homebrew packages/XQuartz),
uses its supplied lock, installs optional MAVSDK dependencies and compiles the
camera bridge. It plans for 25 GiB build space plus a 10 GiB reserve. The current
native route is the legacy outdoor gate scenario using global waypoints; indoor
recon requires a tested local positioning/control interface. Intel Macs need a
separate runtime configuration and validation.

## Cloud settings

The cloud-environment-onboarding setup skill saves installation/start instructions
as a configuration draft. Review and save the draft in environment settings, then
publish to retain the prepared environment. Saving a draft does not apply its
network changes or establish restoration. The source archive remains the explicit
handoff artifact alongside the Git source checkout.
