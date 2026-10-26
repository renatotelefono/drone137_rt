# Task ledger

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

## Historical eight-item preparation sequence — 23 October 2026

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
5. Docking (`docs/docking.md`): implemented on 25 October 2026 (tag detector and pose,
   the `dock` phase, dock registry and controller API, the simulated dock around the
   Rapier plant). Gate results are in `docs/docking-validation.json` and
   `docs/docking-validation-kinematic.json`. Open: the dock controller firmware, the
   carrier STAT input, the Three.js renderer does not draw the tags (the simulated dock
   camera does), and the Watch cluster's sortie scheduler.
