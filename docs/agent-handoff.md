# Development agent handoff

## Current work — 23 October 2026

The active request is to finish blind visual exploration first, then complete
the eight software/build-preparation items recorded in `docs/tasks.md`. The
aircraft starts without a room map or true pose; the ground computer builds
and saves a named place from RGB images and synthetic IMU measurements. The
user requires simple mission control, secure external integration, local
operation and an eventual 8 GB target. Physical hardware is not available.

Read `docs/blind-exploration.md` before the historical sections below. The
handoff branch is `codex/indoor-vision-platform` in `bitfent/drone137`. Use this
branch to continue; do not assume `main` contains this handoff. Preserve any
later local changes and never print Git remote credentials. Use `git log -1`
to identify the handoff commit. Source and compact validation summaries are in
Git; local model weights, device credentials, runtime builds and full camera
recordings are deliberately excluded.

Current functional checkpoint: **development-70 passed** the full blind mission
on layout 9992 after ground-phase VIO initialization and a shorter two-axis
maneuver. Coverage 82.19%, false free 3.80%, position RMSE 8.42 cm, return error
13.94 cm, zero contacts, landed and persisted evidence. Preparation items 1–8
are authorized to proceed; broad reliability remains open.

Qualification-03 has finished with **2/3 passes**, unchanged source for all three
flights. Seed 13191 failed coverage (52.55%) and boundary recall (56.99%).
13192 passed with 83.45% coverage and 13193 with 80.72%. All three returned,
landed and had zero contacts; all passed pose, false-free and memory gates.
Prior suites remain recorded: qualification-01 1/3, qualification-02 2/3.
Do not combine development reruns into a reliability rate or claim 95% success.
The next exploration diagnosis is the planner's inefficient coverage on 13191.
Its saved decisions are under `qualification-03/seed-13191/explorer/planning-audit`.
No mapping trial is currently running and the source freeze has ended.
`docs/blind-exploration-validation.json` retains compact summaries for every
development attempt and all three qualification suites for a fresh checkout.
Raw camera/IMU traces, maps, source archives and planning-audit arrays remain
local under `.local/validation/blind-mapping`; the JSON summary does not replace
those diagnostic inputs. Reproduce a new trial if the original local evidence
is unavailable; never describe missing evidence as a fresh validation.

Item 1 host protocol/adapter/emulator is implemented and verified by **25 distinct
tests** in `tests/test_aircraft_{protocol,link,connection,connection_api}.py`.
The implementation lives under `hardware/esp32/`: `link_protocol.py`,
`link_client.py`, `link_emulator.py`, `device_store.py`, `connection.py`,
`connection_api.py`; read `link-protocol.md`. Pinned HTTPS, unique pairing secrets,
exclusive control, command expiry/idempotency, emergency revocation, bounded
camera/IMU streams and SQLite pairing are covered. The monitor never arms or
emits thrust. It renews clock mapping every three seconds. Incoming stale camera
and IMU data are rejected; queue overflow is explicit to pose consumers.

Mission Control has a **Connect a drone** panel, pairing-file upload, local
address/name, connection status and camera preview. Browser verification used
only the local protocol emulator (static fixture, stationary synthetic IMU,
no physics). Test evidence is `.local/validation/aircraft-link-tests.log` and
`mission-control-connection.png`. The current emulator is paired as
`Scout connection demo` and is explicitly labelled as an emulator in the UI.
The UI has no physical launch route. Onboard matching firmware is item 2.

Pairing uses owner-only `.local/data/aircraft.sqlite3`; never expose its
credentials or package it in source exports. The public registry/API omits
secrets. The API is loopback-only and is **not** the future scoped remote API/MCP.
It allows at most four active sensor monitors, not four qualified flying drones.
Items 3 and 4 are partly implemented; items 2, 5, 6 and 7 remain unfinished.
Build files in item 8 remain partly implemented. See the top of `docs/tasks.md`.

Relevant source changes preceding this milestone:
- `frontier_planner.choose_frontier` adds bounded nearby-view commitment.
- `Link.fly` keeps yaw rate 0.65 rad/s and permits settled speed below 0.2 m/s
  for 0.15 s, with position/height/yaw gates unchanged.
- `initialization_ready` validates finite/fresh independent VIO/IMU agreement.
- Native `stationary_phase` permits sensor-gated ground ZUPT, then latches off
  permanently before liftoff. Ground replay and 32 focused regressions pass.
- Initialization visits (-0.25,0), (0,0.25), (0,0) after vertical takeoff;
  original fusion checks and all independent scoring thresholds remain.
- Failed development-68 and -69 and all earlier attempts remain in the report.
Details and native build/replay evidence are in `docs/blind-exploration.md` and
`.local/validation/blind-mapping/startup-diagnostics/`.

Services started in this continuation:
- localhost:8081 existing Qwen server (PID was 9376; verify before reuse).
- localhost:8137 `scripts.mission_control`, using that already-running model.
- localhost:8160 HTTPS protocol emulator, identity in
  `.local/devices/mission-control-emulator` (contains secrets; ignored).
No hardware is connected. Do not spawn a second model server on 8081.

The OpenVINS bridge and multiview mapper, place persistence and `/places`
viewer/grounded question API exist. Reusing a saved map for navigation on a new
visit still needs relocalization/freshness work. Each blind test starts empty.
The old 24/24 known-map result is a different test. Actual 8 GB qualification
and physical flight testing are outstanding.

Latest local recovery checkpoint before this handoff commit:
`.local/checkpoints/connection-milestone-20261023-115456` (116 changed/new files
and consistent SQLite backups). Large camera/video/model files remain at their
original ignored paths. Pairing databases contain secrets and must not be
included in a source export.

Pre-handoff verification: **264/264 Python regressions, 8/8 blind-controller regressions, 11/11 component-physics regressions and 6/6 mission-physics checks passed**. These are software checks, separate from full model-driven flights. See `docs/handoff-validation.json` for log hashes and scope.

## Resume this milestone

1. Read the current table in `docs/tasks.md`; item 1 is host-verified, not an
   aircraft flight qualification. The next implementation is item 2, onboard
   ESP32 firmware matching `hardware/esp32/link-protocol.md`. Existing
   `camera_bench.ino` is camera-only and keeps motors disabled.
2. Use the Scout 110-B commercial-parts assembly, separate from historical
   power-v2 battery hypotheses. Pin component revisions in SQLite and retain
   provisional/measured evidence labels. Hardware is not yet available.
3. Alongside the preparation sequence, diagnose 13191's coverage failure
   from its recorded planning decisions. Keep all acceptance thresholds and
   truth isolation unchanged; evaluated layouts become development data.
4. The configured workstation has `.local/vision-env`, `.local/laya-env`,
   `.local/browser-test`, the Qwen server and the OpenVINS build. A fresh clone
   does not. Follow `docs/mission-runtime.md` and `docs/blind-exploration.md` for
   dependency/build steps; offline packaging is still preparation item 6.

Useful commands on the configured workstation:

```sh
# Run regressions; this does not fly a physical drone.
.local/vision-env/bin/python -m unittest discover -s tests -v

# Use an already-running local model on port 8081; avoid a second model server.
.local/vision-env/bin/python -m scripts.mission_control --port 8137

# Create a NEW test-only identity, then omit --provision on later starts.
.local/vision-env/bin/python -m hardware.esp32.link_emulator \
  --identity .local/devices/new-test-aircraft --provision --port 8160

# Show retained local flight reports, if their evidence directories exist.
.local/vision-env/bin/python -m scripts.serve_flight_reports \
  --directory .local/validation --port 8142
```

Check which ports/processes are already active before starting services. Never
commit the generated pairing JSON/private key or the `.local/data` databases.

## Start here

Continue the existing drone137 implementation; do not rebuild it from scratch.
The user's current objective is autonomous visual reconnaissance in a confined
space, initially using a local model and virtual testing on a Mac. The user
prefers Python and does not want TypeScript for this project. The current stack
is Python/aiohttp, plain JavaScript/Three.js, and a thin llama.cpp model manager.

Read these files in order:

1. `README.md`: current product, startup and limitations.
2. `docs/handoff.md`: Mac installation and acceptance procedure.
3. `docs/recon-architecture.md`: current recon implementation and contracts.
4. `docs/validation.md`: actual test evidence and unverified claims.
5. `docs/tasks.md`: remaining work.
6. `docs/recon-objective.md`: mission requirements beyond this first sandbox.
7. `docs/vision-flight-comparison.md` and `docs/vision-flight-validation.json`:
   native rotor preflight and live Qwen/Florence/SmolVLM2 comparison, including
   resource failures and subsequent inspection-policy experiments.

The visual companion experiments use an optional isolated `.local/vision-env`;
dependencies are pinned in `requirements-vision-reviewers.txt`. They are invoked
through the native flight evaluator, not the mission-control model selector.
Do not describe a four-case development pass as full realism-suite qualification,
held-out accuracy or validation on actual 8 GB hardware. Source edits during a
flight evaluation invalidate its frozen-source integrity check.

The original uploaded project brief is reference material. Its outdoor gate
mission and aircraft assumptions do not override the user's later confined-space
recon objective. The older gate executor/native integration remains a separate
regression path; consult its architecture only when working on that path.

## Transfer and repository state

Earlier source was versioned on `main` in `bitfent/drone137`; this handoff is on
`codex/indoor-vision-platform`. Begin by inspecting
`git status` and `git log -1`; preserve any local changes before checkout/reset
or cleanup operations. The repository originally began empty, but the initial
implementation is now supplied as a source commit.

An agent in this same workspace can use `/workspace/drone137`. An agent elsewhere
can clone `https://github.com/bitfent/drone137.git`. Alternatively, use
`dist/drone137-source.tar.gz` and its `.sha256` sidecar from an exported handoff;
verify the checksum before extraction. Generated archives are not Git-tracked.
Models, native builds, environments and bulk run evidence are excluded; source,
lockfiles, tests and validation summaries are included.

The cloud setup draft has been saved, but saving does not apply/publish it.
Fresh-task restoration has not been verified. Do not assume this conversation,
running processes, untracked files or draft network changes exist in a new task.

## Current implementation and observed results

- Latest interface: `/control` mission dashboard, with selectable rectangle,
  actual-Qwen brief interpretation, reviewable viewpoint assignments and two
  isolated aircraft/camera workers. Shared indoor airspace is leased to one
  aircraft at a time; queued drones are docked outside the site. Both completed
  actual-model flights with six total observations and separate playable 720p
  videos. Local-model intent checks passed 8/8 development prompts after a retained
  doorway-task misclassification. 105 automated tests pass. See
  `mission-control.md` and `mission-control-validation.json`; these are dispatch
  and evidence tests, not concurrent-flight or real-world qualifications.

- Latest feature: `realism` camera bay, local scanned concrete, bottles/chair/cone
  and bench clutter. Camera conditions nominal/dim/glare/motion share processed
  display/video/JPEG pixels. Read the newest section of `docs/validation.md` and
  `realism-validation.json`. Frozen seed-619 tests passed 28/28 cases, 36/36 required
  object names and 8/8 doorway checks; p95 4.910 s. This is one synthetic site.
  Failed prompt/crop iterations and the original return-route failure are retained.
  Production uses an explicit passage task only where declared by the operator's
  checkpoint; the original general center and full-frame object survey remain.
  Do not resurrect the rejected crop pipeline or mistake a seed for a new site.

- The latest user scope is workshops, warehouses, building perimeters, flat fields
  and hillsides. All five remain unqualified. Read `docs/reliability-protocol.md`.
  The new frozen evaluator and image/video importer keep site/encounter identities,
  reject changed/duplicate inputs, track used held-out sites, and separate public
  proxy data from target-camera evidence. Six real TUM preview frames found 11/12
  labelled object names and 5/6 passing images; the missed bottles remain a failure.
  No prompt was tuned on these frames. Do not report this as general recognition,
  physical clearance, continuous video understanding or mission performance.
- Three.js random room, warehouse, connected-room and detailed workshop scenes, including a passage
  obstruction variant; explore and inspection-point patrol modes.
- Geometry-free observed-map navigation in `app/navigation.py`; ideal vehicle in
  `adapters/kinematic.py`; scene/range geometry in `sim/recon_world.py`. Recon still
  instantiates the kinematic backend. It is not yet a generic PX4 indoor controller.
- Saved run history and HTML reports with playable video, selected images,
  approximate video seek positions, route/map and unreached checkpoints.
- Actual Qwen/Metal on the M4: the original closed-gate and changed-passage misses
  are corrected by separate image-evidence and action-selection calls. The shared
  camera profiles pass 32 image cases, including 24 rendered viewpoints and eight regressions.
  The workshop has 720p video, 960 × 540 model frames and a separate object-survey call. The
  browser test now requires actual obstruction detection and a report finding;
  recording/navigation success alone cannot pass it. Broader semantics remain open.
- 105 automated tests pass on Mac; 104 accelerated navigation geometry cases return
  with zero clearance violations. These tests use ideal pose/ranges, not dynamics.
- PX4 SITL, locked Gazebo and the JPEG bridge compiled on M4/macOS 15.6. One
  real-Qwen legacy gate route completed takeoff, correctly classified both gates
  from native frames, returned and landed. Indoor PX4 recon remains unimplemented.

Exact current evidence and episode IDs are in `docs/validation.md` and the compact
`docs/workshop-validation.json` and `docs/perception-validation.json` (with earlier failures in `docs/mac-validation.json`). Older Linux records are retained as historical evidence.
Models/builds/run media live under `.local` in this checkout and are not exported.
`app/perception.py` owns the vision schema and separate bounded text policy.
Compare only aligned camera poses, and preserve uncertainty; identical center
classes do not establish that the whole scene is unchanged. Evaluation scripts:
`render-vision-cases.cjs`, `evaluate_perception.py`, `render-detail-cases.cjs`,
`evaluate_detail.py`, and `check-patrol.cjs`. The detail renderer preserves uniquely
named sets; its evaluator defaults to the newest completed set. Object checks
grade expected names, not every caption detail. Review images for hallucinated details.
The model, browser and simulator run on a 16 GiB M4; actual 8 GiB and sustained
physical memory/offline acceptance remain pending. Physical transport is disabled.

## Next development session

Inspect `git status`, preserve current work, and use the existing environments:

```bash
./scripts/bootstrap-macos.sh --minimal
./scripts/test-portable.sh
./scripts/run-local.sh --mode recon --open-browser
```

On Linux use `bootstrap-cloud.sh --minimal`. Use `.venv/bin/python` for Python.
The bootstrap finds supported Python even when Finder defaults to Apple's 3.9.
The GUI starts/stops the owned local model; no Ollama service is required.

1. Keep the corrected perception failures as regressions and expand held-out tests
   beyond centered static surfaces. Score missed obstructions, false-clear
   classifications, uncertain cases and changes. Improve image detail,
   prompt or local model choice based on measured accuracy. Keep range supervision
   independent of model descriptions; never hide uncertain/incorrect observations.
   Use `scripts/prepare-reliability.cjs` and `scripts/evaluate_reliability.py` for
   new physical-camera recordings. Freeze before inference; use fresh sites for
   holdout, label with an independent human, and keep exposed sites in development.
   Public preview images are grouped conservatively as one unverified location.
2. Connect indoor navigation to a PX4 adapter with local pose/ranges and bounded
   velocity commands, explicit coordinate/yaw conversions and autopilot failsafes.
   The existing native path is a separate global-waypoint gate mission.
3. Test localization drift, sensor delay/loss, inference timeout, camera coverage,
   operator takeover and return/landing in flight dynamics. Establish repeated
   held-out, offline and sustained memory evidence before a real-drone test plan.

Native installation uses `scripts/install-sim.sh`, PX4's pinned Pixi lock and
`scripts/with-sim.sh`. It avoids the broad upstream macOS installer. Native fixes:
explicit local world/model launch, PX4 daemon mode, MAVSDK `set_current_speed`,
and a loopback `GZ_IP` shared by Gazebo and the camera bridge. The bundled SDK's
gRPC server still listens on all interfaces; restrict it before distributed use.
Use Ctrl-C or `./scripts/stop-local.sh`; terminate only this app's owned processes.

Inference timeout/cancellation quarantines the local model client and requires
server restart. Keep range supervision independent of inference and preserve
operator overrides. Run evidence shares a 1 GiB cap; native logs are bounded.
Do not automatically delete evidence to make a test pass.

After changes, run relevant tests and `./scripts/export-handoff.sh` to refresh
the transfer artifact and checksum. Documentation-only changes do not require
rerunning the full flight/browser suite.
