# Development agent handoff

## Active six-item build preparation — 24 October 2026

The latest request is to complete **1–6**: onboard firmware, build files, host
integration, fault tests, commissioning tools and blind exploration. This is
separate from the historical eight-item roadmap below. The user also requires
storage restraint: retain evidence, avoid duplicate recordings/model downloads.

All of this work is committed on `codex/indoor-vision-platform` and `main` is
fast-forwarded to the same commit (25 October 2026).
No hardware is connected, flashed or physically qualified. Read
[the six-item record](pre-hardware-six.md),
[firmware guide](../hardware/esp32/flight/README.md) and
[assembly package](../hardware/esp32/indoor/scout-110-bench/assembly.md).

Items **1–5** have implemented source/build artifacts and software verification.
Safe/propeller-free/rig ESP32 builds compile at 1,111,817 / 1,111,965 / 1,111,969
bytes flash and 73,848 bytes static RAM. Carrier DRC/ERC have zero violations,
65 pins match the schematic, and five mechanical meshes/nominal clearance pass.
The C++ controller is tested separately from the full Rapier exploration flights.
The new printed stack and VGA camera are not matched to the old synthetic
63.26 g / 960×540 aircraft. Actual mass, gains, thrust/current, calibration and MCU
control/camera timing remain unmeasured; no actual 8 GB host qualification.

The full Python suite passes **318/318**, including map boundaries, continuous
ray traversal, isolated recording and lossless archives (`preparation-full-tests-v5.log`). Their focused
regressions pass **46/46**. JavaScript passes 19/19 blind/component tests
and 6/6 mission-physics checks. The earlier incorrectly invoked mission script
and sandbox socket errors remain logged; corrected invocations pass.

Item **6** remains in progress. Every original failure stays recorded:

- Qualification-04: 1/3, including disk-full recording failure.
- Qualification-05: 2/3, one coverage failure; bounded route-cost tie-break added.
- Qualification-06: 2/3, one caption disconnect causing an off-launch landing
  and missing journal entry. Fresh HTTP sockets and failure-preserving image
  journaling added; no uncertain-request retry. Root disconnect cause unproven.
- Qualification-07: **2/3**. Seeds 18661/18662 passed at 85.20% / 81.73% coverage.
  Seed 18663 failed only false-free space: **5.02197%**, above the unchanged 5%
  gate; coverage 81.66%, pose 3.60 cm, return 7.83 cm, zero contacts, landed.
- Development-73/74/75/76 pass their exposed failed layouts. These are debugging
  runs and must never be pooled into an independent reliability rate.

Post-qualification-07 diagnosis places most false-clear cells near observed
surfaces. A one-cell uncertain band now remains unknown around occupied map
cells; it affects live navigation, not evaluation, and clears only when later
ray evidence clears the surface. **Development-77 passed** exposed seed 18663:
83.69% coverage, 1.27% false free, 4.19 cm pose, 3.84 cm return, zero contacts,
landed/persisted. Automatic compaction retained all evidence and released
319,369,216 bytes. **Qualification-08 finished 2/3**, frozen source verified unchanged. Results:
19771 FAIL (63.39% coverage only; 0.57% false free, zero contacts/landed),
19772 PASS (83.80%; 1.37% false free), 19773 PASS (82.54%; 1.42% false free).
All returned and landed without contact. No gate changed.
The failed room repeatedly viewed the passage without clearing enough flight-height
volume. A diagnostic reconstructed cloud exposed holes in fixed 0.1 m ray sampling:
1,102 visited voxels versus 1,207 from exact grid-plane traversal. The prototype
passed 46 independent segment/voxel intersection comparisons. An isolated
microbenchmark measured ~4.9 MB traced allocations versus 23.9 MB for sampling;
it is not total app memory and traversal took ~28 ms versus ~17 ms.
The correction is now integrated in **app/voxel_rays.py**, called by RaycastMap.
Near/surface exclusions, corroboration, endpoint hits and safety margins are
unchanged. `tests/test_voxel_rays.py` compares independent slab intersections;
46 mapping/ray test cases pass (`ray-traversal-regressions.log`). Source archives
now also include the new helper, model adapter and compactor.
**Development-78 passed** exposed failed room 19771: 83.10% coverage,
1.26% false free, 3.44 cm pose RMSE, 10.90 cm return error, zero contacts,
landed/persisted. This is development evidence, not a reliability sample.
**Qualification-09 finished 2/3**, with frozen source verified unchanged.
20881 failed early: `RuntimeError: Error: Failsafe latched`, 10.34% coverage,
1.93 m return error, zero contacts, landed/persisted. 20882 passed (81.65%),
20883 passed (83.14%). The failure is retained. HTTP command requests continued
until shortly before the gateway pump stopped; exact delay cause was not recorded.
Host swap grew from 8.75 GB to 9.70 GB during the failure, but causation is unproven.
A process audit found no additional abandoned project model/browser process to kill.
Do not stop user apps or the active model server.

Diagnostic JSON serialization/file writes now run through bounded `JsonlWriter`
queues outside the simulator control event loop. Overflow/writer errors are
explicit; failed recording cannot produce a finalization marker. Native RPC
queue/ack timing is saved to `plant/control-timing.jsonl`. Watchdog thresholds,
lease duration and physics remain unchanged. Ten recording/storage regressions
pass. Full regressions pass **318/318** in `preparation-full-tests-v5.log`.
**Development-79 passed** exposed room 20881: 83.19% coverage, 1.95% false
free, 2.99 cm pose RMSE, 4.88 cm return, zero contacts, landed/persisted,
3.50 GiB peak application memory. New native timing records show a maximum
255 ms command acknowledgement interval and no RPC errors. The I/O isolation
is a mitigation, not proof of the old failure's exact cause.
**Qualification-10 finished 1/3** on fresh predeclared seeds 21991/21992/21993 with
frozen source. 21991 failed coverage (56.81%) and boundary recall (59.22%);
false free 0.27%, pose 4.53 cm, return 7.41 cm, zero contacts, landed/persisted,
46 observations, battery return reserve at 283 s. 21992 passed (84.73% coverage,
1.02% false free) and 21993 passed (82.11%, 0.65%). All three returned and landed
without contact. No gate changed; the failure is retained.
Diagnosis from its saved planning records: every generated workshop is a 12 × 10 m
floor split by a partition at x = 6 m with one 2 m opening, and passing flights map
69–79% of the far room while 21991 mapped 16%. The aircraft stood in the opening
twice; observed floor continued through it, but the 1.35–1.65 m flight band beyond
never collected two rays per voxel, so no navigable viewpoint existed past about
4.3 m launch-local x. Its 67 unresolved doorway cells averaged 7.4 recorded view
attempts (transit frames and paired parallax stations both count), so the
1/(1+4n) discount cut their combined priority from 41.3 to 1.36. At planning
record 13 the planner chose a 7.4 m detour to the first room's far corner (score
1.04) over the 0.6 m doorway view (0.81); the remaining battery went to the first
room's south strip with four tracking recoveries near blank walls.
The discount is now bounded at two attempts, `1+4·min(n,2)`, in
`app/frontier_planner.py`. A replay of the recorded decisions (a counterfactual,
not a flight) turns records 9 and 13 toward the opening (5.23 vs 5.10; 2.14 vs
1.24) and leaves record 12 unchanged. Occupancy, clearance, sensors, battery
reserve and all gates are unchanged; a regression test fixes the bound.
**Development-80 passed** exposed room 21991 with the bounded discount: 80.57%
coverage, 1.09% false free, 3.38 cm pose RMSE, 7.72 cm return error, zero
contacts, landed/persisted, 56 observations, 67% of the far room mapped, one
tracking recovery, 3.44 GiB peak application memory. Full suite 319/319
(`preparation-full-tests-v6.log`). This is development evidence on an exposed
layout, not a reliability sample.
**Qualification-11 finished 2/3** on frozen predeclared seeds 23101/23102/23103.
23101 passed (82.83% coverage, 1.34% false free, 3.50 cm pose, 10.17 cm return);
23102 failed coverage only (75.04%; 1.90% false free, 85.75% boundary recall,
2.80 cm pose, 6.65 cm return, zero contacts, landed/persisted, 53 observations);
23103 passed (80.47%, 1.18% false free, 5.76 cm pose, 9.53 cm return). All three
returned and landed without contact; the source hash set was verified unchanged
after the batch. All three mapped 66–76% of the far room, so the opening is no
longer the limiting failure; 23102 mapped only 77% of its first room (passing
flights map 87–93%). That failure is retained.
Diagnosis of 23102 from its planning records: after three decisions in the far
room it returned to the first room and then chose thirteen consecutive short
views of the south wall strip (134 floor cells beside a blank wall, 55 of which
never received a single flight-band ray), each promising about ten units of
information that never materialised. The two-attempt bound had removed the
planner's escape from such fruitless local loops. The rule is now
progress-aware: `record_view_attempt` counts only consecutive attempts without
new flight-band ray evidence and resets to one when a view adds rays, while the
original unbounded `1/(1+4n)` decay applies to that stale count. The one-cell
uncertain ring around observed surfaces, which viewing cannot resolve, carries
no view priority. `RaycastMap` now keeps `band_evidence` and `attempt_evidence`
grids; both are frozen for planning, saved in every planning audit and in
`map-grid.npz`. Occupancy, clearance, sensors, battery reserve and gates are
unchanged. Full suite **321/321** (`preparation-full-tests-v7.log`).
**Development-81 passed** exposed room 23102: 83.53% coverage, 1.93% false free,
6.92 cm pose RMSE, 14.19 cm return, zero contacts, landed/persisted, 49
observations, 79% of the far room and 88% of the first room, no tracking
recovery, five south-wall views instead of thirteen. **Development-82 passed**
exposed room 21991 with the same rule: 81.95% coverage, 0.97% false free,
4.83 cm pose RMSE, 16.59 cm return, zero contacts, landed/persisted, 74% of the
far room. Both are development evidence.
**Qualification-12 finished 3/3** on frozen predeclared seeds 24211/24212/24213,
the first predeclared fresh-layout suite to pass completely. Coverage 82.06%,
81.99%, 83.75%; false free 1.66%, 1.38%, 1.65%; pose RMSE 7.4, 4.2, 4.1 cm; return
error 2.7, 7.0, 7.4 cm; zero contacts; all landed and persisted; far room mapped
80%, 71%, 74%; peak application memory 3.46–3.52 GiB. The source hash set was
verified unchanged after the batch. One suite of three is not a reliability
percentage; earlier failed suites remain recorded and no gate changed.
**Qualification-13 finished 8/10** on frozen predeclared seeds 25321–25330; source
verified unchanged after the tenth flight. Eight layouts passed every gate with
81.72–86.14% coverage and 0.92–1.92% false free space. 25321 failed coverage only
(78.06%; far room 73%, first room 83%). 25328 failed coverage (51.88%) and
boundary recall (62.3%): it reached the opening twice but the flight band through
it never became navigable and only 7% of the far room was mapped. All ten
returned and landed without contact. The suite is failed; both failures are
retained.
Diagnosis of 25328 from its planning audits, which now record flight-band
evidence: the opening was filling in on every visit (navigable cells in the
2 × 2.2 m doorway box rose 42 → 54 → 64 → 92 across the two approaches) but each
hover station clears the band only about 0.85 m ahead in open space, because
band cells farther ahead need near-horizontal rays ending on textured vertical
surfaces, and floor or ceiling rays cross the band only close to the camera.
The crawl therefore earned 3–13 units of information per step while fresh first-
room areas offered 24–63, so the planner left at 120 s, returned at 172 s and ran
out of battery crawling. A replay of its decisions under frontier-style values
for unknown space bordering observed floor (weights 0.1–0.5, reach 0.6–3 m)
changed none of the four decisive choices while altering 16–53% of the 319
recorded decisions in the eleven passing flights of qualifications 12–13, so
planner valuation is not the lever. The remaining software item for exploration
is faster flight-band clearance through open doorways, a perception/sensing-
motion change, not a planner weight. Over the two suites flown with the current
rule, **11 of 13** fresh predeclared layouts passed every gate, no flight in any
suite has recorded a contact, and every failure was coverage, never safety.
All previous failed suites remain recorded.
**Mission wizard (25 October):** `config/mission-templates.json`, `app/mission_wizard.py`,
`/api/wizard/*` routes in `app/mission_api.py`, the `template` tag on plans and
run records, and `app/ui/mission-wizard.js` in the console. Nine tests in
`tests/test_mission_wizard.py`; full suite 330/330 (`preparation-full-tests-v8.log`).
The console launches audits through the reviewed plan and simulated exploration
flights through the existing runner; watch and find are proposed and recorded only.
**Console assistant (25 October):** `app/mission_assistant.py` and `/api/assistant/*`
turn a typed or dictated request into one of a fixed set of console actions, with
aircraft names resolved against the registry and launches excluded. Seven tests in
`tests/test_mission_assistant.py`; full suite 337/337 (`preparation-full-tests-v10.log`).
Verified live against the paired emulator.
Local diagnostics remain `.local/maintenance/voxel-rays-prototype.py`,
`.local/maintenance/test-ray-traversal.py`, `.local/validation/ray-*.json`.
The three storage tests also pass after protecting pre-existing
maintenance artifacts (`recording-storage-regressions-v2.log`).

Storage: historical exact-byte dedup reclaimed about 13.8 GiB. A second pass
on completed recent runs reclaimed **3,842,179,072 bytes (3.58 GiB)** and left
9.8 GiB free. Every path and byte remains. Audit:
`.local/maintenance/recording-dedup-20261024b-summary.json`. New trial runner
compacts duplicate JPEGs only after capture processes exit; it refuses active
recordings and retains unique images, video and failures. No model was removed.
Runs still require at least 3 GiB free before starting.

Additional lossless storage work: **294 raw JSONL diagnostic logs from 104
completed trials** were gzip archived with full decompression SHA-256 verification
before removing redundant raw copies. Reclaimed **5,269,876,736 bytes (4.91 GiB)**;
free space became ~11.0 GiB. Reports, scores, video and review images remain in
place. Per-trial `recording-archives.json` records original/compressed hashes.
Read `.jsonl.gz` directly or run `python -m scripts.archive_recording_logs restore
<recording-folder>` before using old scripts that expect raw JSONL paths.
Archive again after diagnosis to reclaim the restored copy. Archive tests cover
roundtrip bytes/mode/timestamps, active recordings, path escape and corruption.
Audit `.local/maintenance/recording-archive-20261024-summary.json` has zero errors.
An APFS-compression probe failed byte equality; it was NOT applied to evidence.
Only its temporary test files were removed. Do not attempt that path again.

Model server PID 9376 stays running; do not duplicate/restart routinely.
Mission Control 8137 was refreshed (PID 43355); /control, /places, mission status
and aircraft registry return HTTP 200. Only the disconnected emulator is paired,
with mission_ready=false. No physical arm/launch is authorized by a test.
After final qualification, export evidence and reports with the maintenance
scripts, verify source hashes and frozen baseline, then preserve/publish work.
Raw evidence stays `.local/validation/`; credentials/binaries stay ignored under
`.local/firmware/`. Never print Git remote credentials. The frozen 23 October
comparison JSON must remain unchanged. Historical material below is not current
readiness or the current six-item numbering.

## Perched watch — 26 October 2026

`app/watch_detector.py` (motion, change, lighting on every frame), `app/watch_events.py`
(event store, fixed model question, evidence, cooldown), `app/watch_api.py` and the console's
Watch panel; `sim/watch_scenes.py` stages events on a real photo; `scripts/qualify_watch.py`
is the gate (`docs/watch-validation.json`); the emulator plays scripted frames with `--frames`.
`sim/watch_render.py` renders staged object events in the CC0 workshop from table-height dock
poses (perch clearance and line of sight checked); `scripts/record_watch_clip.py` records real
clips with labels; the gate plays either with `--set <folder>`. `app/watch_classify.py` decides
added, taken away or moved from the pixels (surround and move tests); the model names the thing
and says person; `app/person_detector.py` (Apple Vision on macOS, `pyobjc-framework-Vision` in
the vision env) makes a person the detector's call and skips the model; the event category is
gated at 90 % on every set; several watches queue on one model lock (`--parallel N --only-sets`
plays a set as N watches at once). Tests: `tests/test_watch.py`, `tests/test_watch_classify.py`,
`tests/test_person_detector.py`, `tests/test_watch_emulator.py`, `tests/test_watch_render.py`.
Spec and limits: `docs/watch.md`. Two docks in one place: `scripts/qualify_docking.py --docks 2`
(`sim/dock_world.py` draws every dock's column; the registry refuses a second dock with the same
tags in a place); results in `docs/docking-validation-two-docks-*.json`, test in `tests/test_docking.py`.

## Pre-flight memory — 26 October 2026

`app/memory_budget.py`: estimate per component from the GGUF header, the allocated grids and
measured baselines (`config/memory-baselines.json`); a measured preflight (`scripts/preflight_memory.py`,
`/api/preflight/memory`); the memory watch now covers missions with a host-based budget
(5 GiB above 10 GiB hosts, 3.5 GiB below). Validation: `docs/memory-preflight-validation.json`.
Tests: `tests/test_memory_budget.py`.

## Manual control — 26 October 2026

`hardware/esp32/manual_control.py` and `manual_api.py` add a console stick mode:
keyboard or gamepad to bounded attitude setpoints at 20 Hz over the pinned link, half the
tilt envelope, level on release, land after 1.5 s of silence, refused during missions,
tested against the protocol emulator (`tests/test_manual_control.py`). Panel: `app/ui/manual-control.js`.

## Docking — 25 October 2026

The product gained a landing base. Hardware: dock A in
`hardware/esp32/indoor/scout-110-bench/dock/` (printed funnel body, tag stand, contact
charging, carrier prototype B charge path, Swiss parts in `procurement-ch.md`).
Software, all local and deterministic:

- `app/dock_tags.py`: tag36h11 detection with OpenCV's ArUco module, pose of the
  aircraft in the dock frame from the tag column, and a renderer that draws the
  column into synthetic frames with the profile's optics and distortion.
- `app/docking.py`: the `dock` mission phase (return, acquire, align, descend, settle,
  docked) as specified in `docs/docking.md`; it sees frames, estimate, dock status
  and a setpoint interface only.
- `app/docks.py` and `app/dock_api.py`: versioned dock registry, pinned-HTTPS dock
  controller client, `/api/docks/...` and `POST /api/mission/dock`.
- `sim/dock_world.py`: the simulated dock (electronics, contact, faults), the tag camera
  with the benchmark latency and frame drops, a first-order vehicle for tests and the
  Rapier plant wrapper for the gate.
- `app/mission_runtime.py`: a plan may name a registered dock; the mission then ends
  on it, and the console assistant offers `dock status` and `return to dock`.
- Gate: `scripts/qualify_docking.py` (`--vehicle kinematic|rapier`). Results in
  `docs/docking-validation.json` (Rapier plant) and
  `docs/docking-validation-kinematic.json`. Tests: `tests/test_dock_tags.py`,
  `tests/test_docks.py`, `tests/test_docking.py`, `tests/test_docking_runtime.py`.

Not done: dock controller firmware and the carrier STAT input (hardware), the Three.js
renderer does not draw the tags (the simulated dock camera renders them for the dock
phase), and the Watch cluster's sortie scheduler. The dock frame in software is
forward-left-up; the hardware drawings call the same axes +Y, −X, +Z.

## Historical checkpoint — 23 October 2026

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

The latest procurement refresh is in the Scout 110-B build guide (23 October).
`docs/test-comparison.md` is the entry point for simulation versus hardware
comparison. `docs/test-data/pre-hardware-2026-10-23.json` freezes historical
records and their source hashes; `hardware-run-template.json` has no measurements
and must not be counted as a physical test. No new flight was performed to create
this documentation, and the carrier/firmware/physical readiness status is unchanged.

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
8. `docs/supported-aircraft.md`: the contract any aircraft must meet, the three
   connection paths and the physical envelope the software assumes.
9. `hardware/esp32/indoor/scout-110-bench/builder-brief.md`: the brief handed to
   whoever builds the physical Scout 110-B.

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
