# Task ledger

## Active preparation sequence — 23 October 2026

The user requires the blind exploration test to work before preparation items
1–8. Development-70 passed the complete requested test, including ground
initialization, movement checks, 82.19% mapping coverage, return and landing.
Preparation can now proceed. Broader reliability remains open: the earlier
reserved suites passed 1/3 and 2/3. Qualification-03 finished with 2/3 passes:
13191 failed coverage/boundary recall; 13192 and 13193 passed every gate.
All three returned and landed with zero contacts. These synthetic tests do not
qualify real hardware or an actual 8 GB computer. Read `docs/blind-exploration.md`.

| Item | Status | Required deliverable |
| --- | --- | --- |
| 0. Blind exploration and persistent environments | in_progress | Full development flight passes after startup fix; fresh-layout qualification remains open |
| 1. Drone protocol and emulator | verified | Host implementation: pinned HTTPS, exclusive control, bounded/idempotent commands, freshness checks, SQLite pairing and protocol-only emulator; 25 distinct automated tests pass. Mission Control connection/preview verified. Device firmware is item 2 |
| 2. Onboard firmware | not_started | Compiled stabilization/mixer, camera, telemetry, arming and command-loss implementation; simulation/host tests; physical tuning remains separate |
| 3. Position and image quality handling | in_progress | Visual-inertial estimator and mapping exist; integrate timestamp/uncertainty/freshness contracts across the real adapter |
| 4. Simple mission interface | in_progress | Connect/preview now work with the protocol emulator; unify blind exploration, area/task/review, live map/findings and physical navigation integration |
| 5. Secure API and MCP | not_started | Authentication, scoped permissions, revocation, control ownership, idempotency, audit, local-only default |
| 6. Offline installation | not_started | Reproducible installation/startup, local assets, resource limits, diagnostic checks and clean-copy offline verification |
| 7. End-to-end fault acceptance | not_started | Run the new integrated path through disconnects, stale sensors, inference stalls, conflicting control, restart and unauthorized requests |
| 8. Build and commissioning files | in_progress | Bench BOM/frame/wiring proposals exist; finish schematic/carrier, printable outputs, flashing and first-connection instructions |

Older task series below are historical milestones and do not replace these
deliverables. No physical flight should be described as qualified by a software
test result.

Status vocabulary: `not_started`, `in_progress`, `blocked`, `verified`.
Verified entries refer only to the host/profile/backend evidence named here.

The current first objective is [confined-space reconnaissance](recon-objective.md).
The A-series below records the original prototype/handoff work; its completed
fixture tests do not establish the new exploration or video capabilities.

| ID | Owner | Dependencies | Status | Output and evidence |
| --- | --- | --- | --- | --- |
| R01 | AI / development | Clarified objective | verified | Linux and M4/Chrome: seeded room, warehouse, connected-room and detailed workshop worlds, onboard/overhead views, playable video and saved HTML reports |
| R02 | AI / development | R01 | verified | Observed-map planner separated from kinematic vehicle; 104 accelerated geometry cases returned, zero clearance violations. Full 3D/noisy sensing remains pending |
| R03 | AI / development | R01–R02 | in_progress | Actual Qwen patrols returned with video/images, approximate seek links, detected obstructions and partial-route reporting; workshop adds whole-image object surveys. Broader semantic accuracy and exact exposure sync remain pending |
| R04 | AI + operator / Mac | R01, A05 | in_progress | Actual Qwen/Metal built and run on M4; official weights verified. Known gate/blocker failures corrected by separate evidence/action calls; 32/32 image cases passed across lean and detailed camera profiles. Broader perception acceptance remains open |
| R05 | AI + operator / Mac | R02–R04, native integration | in_progress | PX4/Gazebo/bridge compiled and real-Qwen native route with correctly classified gates and landing passed. Shared indoor local-position backend, noise/failure suite and sustained resources remain |
| R07 | AI / Mac | R01, R04 | verified | Detailed workshop with 720p video, 960 × 540 snapshots and object reports; 32 center checks, 7 object/view checks and two real-Qwen patrols passed on M4. Full caption accuracy and physical camera fidelity remain open |
| R09 | AI / Mac | R07–R08 | verified | Camera realism bay with bottles/chair/cone/clutter and synthetic camera stress; final 28/28 image cases, 36/36 required names and 8/8 doorway checks. 93 automated tests, navigation regression and two actual Qwen patrols passed; full evidence in realism-validation.json. Real-world qualification remains open |
| R10 | AI / Mac | R03, R09 | verified | Mission-control dashboard: area selection, Qwen task interpretation, reviewed assignments, two sequential aircraft, isolated camera/video reports, stop and return. Eight intent checks and two actual-model flights covering six views passed; 105 automated tests. Concurrent flight and outdoor/physical operation remain open; see mission-control-validation.json |
| R08 | AI + data reviewer | R03–R05, target camera/site data | in_progress | Frozen real-image/video evaluator, domain gates and exposure ledger implemented. Public indoor smoke baseline: 11/12 labelled names, 5/6 images; bottles omitted. Workshops, warehouses, perimeters, flat fields and hillsides all remain unqualified |
| R06 | AI + hardware lead | R05 | blocked | Aircraft/sensor suitability review and subsequent human build/test plan for confined spaces |

| ID | Owner | Dependencies | Status | Output and evidence |
| --- | --- | --- | --- | --- |
| A01 | AI / cloud | Empty repository | verified | `README.md`, `pyproject.toml`, locks, `docs/environment.md`; Python bootstrap on Linux x86_64 / cloud-dev |
| A02 | AI / cloud | A01 | verified | Contracts, executor, recorder, local UI, fake/replay adapters, independent heartbeat and process cleanup; portable tests on Linux x86_64 / cloud-dev with fake inference/camera/dynamics |
| A03 | AI / cloud then Mac | A01–A02 | in_progress | `adapters/`, `sim/`, `config/`, staged scripts; isolated HTTP/MAVSDK/camera contracts tested; M4 native binaries/bridge compiled and real-model gate route passed with both labels correct and landing |
| A04 | AI / cloud | A01–A03 accessible work | in_progress | Source export, checksum, locks and clean-copy bootstrap verified (see current validation report); official model revision/hashes resolved and verified on Mac; refreshed source export excludes bulk local artifacts |
| A05 | AI + operator / Mac | Source handoff | verified | M4, 16 GiB, macOS 15.6 inspected; Python bootstrap, native installs and local operation exercised |
| A06 | AI + operator / Mac | A05 | in_progress | Real Qwen and native camera/control exercised together on the default gate route. Initial recognition regressions corrected; sustained combined resource acceptance pending |
| A07 | AI / Mac | A06 | not_started | M2–M4, failure suite, offline verification, held-out scenarios, physical-memory measurements |
| A08 | AI + hardware lead | Independent documentation | not_started | Original hardware scope retained in `docs/project-brief.md` and `hardware/README.md` |
| A09 | Human + AI | Mac virtual acceptance + lean budget | blocked | No construction or commissioning yet |
| A10 | Human + AI | A09 | blocked | No physical testing yet |
| A11 | AI + operator | A07 and pilot | not_started | Reproducible supported release and second-person installation |

The first handoff delivers a runnable portable implementation, not completion of
all A03–A04 integration/acceptance requirements. See `docs/validation.md` for exact
checks and the concrete remaining work.

Next acceptance work:

0. Collect intended-camera footage across separate workshop/warehouse sites, then
   perimeters, flat fields and hillsides. Use `reliability-protocol.md`; obtain
   independent labels and full-caption audits. Public TUM previews and repeated
   frames cannot satisfy the target-site gate. Preserve the missed-bottles case.
1. Build a held-out image/scene evaluation set for visible obstructions and changes;
   retain the known failures as passing regression cases and expand beyond centered
   synthetic obstructions. Improve model, image detail or prompts based on
   measured false-clear/missed-change rates, without putting it in the flight loop.
2. Implement indoor PX4 local-pose/range and velocity adapters for the shared
   navigation module, with explicit ENU/NED and yaw conversion. Demonstrate the same
   patrol and evidence report in flight dynamics before hardware selection.
3. Exercise pose drift, range noise/dropouts, camera lag, model timeout, link loss
   and operator takeover. Establish measured camera-visible coverage, timing and
   bounded recovery, then run repeated held-out and sustained offline missions.
4. Measure physical memory/swap under sustained combined load. Only then review a
   suitable protected aircraft/sensor stack and a controlled physical test plan.

The runnable patrol sandbox and one legacy native flight test do not close these
acceptance gates. Hardware remains disabled.
