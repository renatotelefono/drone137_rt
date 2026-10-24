# Six-item pre-hardware implementation — 24 October 2026

The six items in this milestone are firmware, build files, aircraft integration,
fault tests, installation/commissioning tools and improved blind exploration.
They are distinct from the earlier eight-item product roadmap. No hardware has
arrived, no aircraft has been flashed, and no physical flight has taken place.

| Item | Deliverable | Verification / remaining limit |
| --- | --- | --- |
| 1. Flight firmware | [Shared C++ controller and ESP32 sketch](../hardware/esp32/flight/README.md): estimator, mixer, stabilization, arming, battery and watchdogs | ESP32 safe and restrained builds compile; desktop controller tests pass. Physical gains, timing, power and sensor behavior await measurement |
| 2. Build files | [Carrier, schematic, fabrication archive, wiring and five printable parts](../hardware/esp32/indoor/scout-110-bench/assembly.md) | DRC/ ERC zero violations; 65 actual PCB/schematic pins match; five closed connected meshes and nominal rotor-clearance checks pass. Physical fit/current/temperature/mass remain unmeasured |
| 3. Aircraft integration | Pinned HTTPS control, camera, emergency and timestamped IMU; Mission Control monitor; sensor recording and calibrated VIO replay | Actual shared C++ protocol tested through the host client and monitor. Physical autonomous navigation remains disabled |
| 4. Fault tests | Shared-controller and HTTPS fault suite | Wi-Fi/control loss, inference/video delay, stale camera, missing IMU, command identity/replay, stop, reboot and arming gates covered. Synthetic sensors do not establish MCU deadlines |
| 5. Installation and commissioning | Unique provisioning, private build directories/manifests, hash-checked flash, diagnostics, bounded propeller-free/rig tests, calibration templates | Operator tools exercised against the shared-controller harness. Templates contain no fabricated physical measurements; clean-machine offline/actual 8 GB qualification remains separate |
| 6. Blind exploration | Recorded transit-view history; information-ranked next views; bounded travel tie-break instead of redundant panoramas/detours | Development-73/74/75 pass previously failed rooms. Qualification-05/06 finished 2/3; development-76 passes; qualification-07 finished 2/3; development-77 passes the boundary fix; qualification-08 finished 2/3; development-78 passes continuous-ray traversal; qualification-09 finished 2/3; development-79 passes after recording I/O isolation; qualification-10 finished 1/3 (doorway flight band never cleared); the repeated-view discount is now bounded and development-80 passes that room; qualification-11 finished 2/3 (one first-room coverage failure); progress-aware view attempts; development-81/82 pass both exposed rooms; qualification-12 finished 3/3 and qualification-13 8/10 (11 of 13 fresh layouts); remaining item: faster flight-band clearance through open doorways |

## Test evidence

The [compact result file](test-data/pre-hardware-six-2026-10-24.json) records this
milestone separately. The frozen
[23 October baseline](test-data/pre-hardware-2026-10-23.json) remains unchanged.
Raw logs, per-flight source manifests, camera/IMU traces and videos remain local
under `.local/validation/`; firmware binaries and credentials are deliberately
excluded from Git.

- Full Python suite after mapping, storage and continuous-ray fixes: **318/318 pass**, including
  firmware, connection, sensor replay, mapping and existing mission tests.
- JavaScript: **19/19 blind/component regressions** and **6/6 mission-physics
  checks** pass. An initial combined invocation lacked the mission input file;
  that invocation error remains logged. The corrected mission command passes.
- Latest safe ESP32 build: **1,111,817 bytes flash, 73,848 bytes static RAM**.
  Propeller-free build: **1,111,965 bytes flash, 73,848 bytes static RAM**.
  Restrained-rig build: **1,111,969 bytes flash, 73,848 bytes static RAM**.
  These are compile-time sizes, not runtime heap/PSRAM measurements.
- Development-73 (seed 13191): **82.58% coverage**, 4.40 cm pose RMSE,
  8.08 cm return error, zero contacts, landed, all gates passed.
- Development-74 (seed 15331): **82.92% coverage**, 3.41 cm pose RMSE,
  3.72 cm return error, zero contacts, landed, all gates passed.
- Qualification-04: **1/3 planned flights passed**. Seed 15331 failed coverage;
  seed 15332 failed during disk-full video recording; seed 15333 passed after
  storage recovery with the same frozen code. Both failures remain recorded.
- Qualification-05: **2/3 passed**. Coverage: 78.60% (FAIL), 85.99% (PASS),
  81.58% (PASS). All three returned and landed without contact.
- Development-75 (seed 16441): **82.71% coverage**, 2.47 cm pose RMSE,
  5.93 cm return error, zero contacts, landed, all gates passed.
- Qualification-06: **2/3 passed** on frozen seeds 17551/17552/17553.
  Coverage was 83.07%, 84.01%, 81.34%. The third passed mapping gates but a model
  caption connection failed, causing an off-launch landing and missing journal
  entry. It remains failed for return, persistence and navigation completion.
- Development-76 passed exposed seed 17553: **83.89% coverage**, 5.65 cm pose
  RMSE, 5.37 cm return, zero contacts, landed/persisted. It uses fresh inference
  sockets and failure-preserving image journaling. Failed inference still fails
  the mission and is not retried; the original disconnect cause is unconfirmed.
- Qualification-07 finished **2/3** on frozen **18661/18662/18663**. Coverage
  was 85.20%, 81.73%, 81.66%. The third failed only false-free fraction
  (5.02197%, versus the unchanged 5% maximum); all returned and landed without
  contact. Development-77 passes after a live-map uncertainty band around observed
  surfaces: **83.69% coverage**, **1.27% false free**, 4.19 cm pose RMSE,
  3.84 cm return, zero contacts, landed and persisted. This development result
  does not replace the failed qualification.
- Qualification-08 finished **2/3** on frozen **19771/19772/19773**. Coverage
  was 63.39% (FAIL), 83.80% (PASS), 82.54% (PASS). All returned and landed
  without contact. The first room repeatedly viewed a passage without enough
  observed airspace to proceed. Development-78 tests exact grid-plane ray
  traversal, replacing fixed-distance samples that skipped crossed cells.
  Endpoint exclusions, corroboration, safety margins and scoring are unchanged.
- Development-78 passes exposed seed 19771: **83.10% coverage**, **1.26% false
  free**, 3.44 cm pose RMSE, 10.90 cm return, zero contacts, landed/persisted.
- Qualification-09 finished **2/3** on frozen **20881/20882/20883**. The first
  flight stopped on a latched link watchdog and landed away from launch; the
  other two passed at 81.65% and 83.14% coverage. That failure remains recorded.
  Exact timing of the old failure was unavailable, so its cause is unproven.
- Diagnostic serialization and file writes now use a bounded worker queue outside
  the control event loop, with explicit overflow/write errors and native command
  timing records. Watchdog durations and all flight gates are unchanged.
- Development-79 passes exposed room 20881: **83.19% coverage**, **1.95% false
  free**, 2.99 cm pose RMSE, 4.88 cm return, zero contacts, landed/persisted.
  Peak measured application memory was 3.50 GiB. Maximum native command
  acknowledgement interval was 255 ms; no RPC or recording errors were logged.
- Qualification-10 finished **1/3** on frozen **21991/21992/21993**. 21991 failed
  coverage (56.81%) and boundary recall (59.22%) with 0.27% false free, 4.53 cm
  pose RMSE, 7.41 cm return error, zero contacts, landed/persisted. 21992 passed
  (84.73%; 1.02% false free) and 21993 passed (82.11%; 0.65%). All returned and
  landed without contact. The failed room's planning records show the aircraft
  reached the partition opening twice but the flight band beyond it never
  cleared; its unresolved doorway cells averaged 7.4 recorded view attempts, and
  the unbounded 1/(1+4n) discount left them at about 1/30 of their information
  value, so the planner left for a 7.4 m detour. The discount is now bounded at
  two attempts (`1+4·min(n,2)`); occupancy, clearance and gates are unchanged.
- Development-80 passes exposed room 21991 with that bound: **80.57% coverage**,
  **1.09% false free**, 3.38 cm pose RMSE, 7.72 cm return error, zero contacts,
  landed/persisted, 56 observations, 67% of the far room mapped. Full Python
  suite **319/319** (`preparation-full-tests-v6.log`). Development evidence only.
- Qualification-11 finished **2/3** on frozen **23101/23102/23103**. Coverage was
  82.83% (PASS), 75.04% (FAIL, coverage only), 80.47% (PASS); false free 1.34%,
  1.90%, 1.18%. All returned and landed without contact; source verified unchanged
  after the batch. All three mapped 66–76% of the far room; the failed flight
  mapped only 77% of its first room. The failure is retained. Its records show
  thirteen consecutive fruitless views of a blank south-wall strip: the
  two-attempt bound had removed the planner's escape from such loops.
- The repeated-view rule is now progress-aware: attempts count only while a
  view adds no new flight-band ray evidence, resetting on progress, with the
  original unbounded decay on that stale count; the unresolvable one-cell ring
  around surfaces carries no view priority. Full suite **321/321**
  (`preparation-full-tests-v7.log`). Development-81 passes exposed room 23102
  (**83.53% coverage**, 1.93% false free, 6.92 cm pose, 14.19 cm return, zero
  contacts) and development-82 passes exposed room 21991 (**81.95%**, 0.97%
  false free, 4.83 cm pose, 16.59 cm return, zero contacts). Development only.
- Qualification-12 finished **3/3** on frozen **24211/24212/24213**: coverage
  82.06%, 81.99%, 83.75%; false free 1.66%, 1.38%, 1.65%; zero contacts; all
  landed and persisted; source verified unchanged after the batch. This is the
  first predeclared suite to pass completely. It is one suite of three flights,
  not a reliability percentage; earlier failed suites remain recorded.
- Qualification-13 finished **8/10** on ten fresh predeclared layouts
  **25321–25330** with frozen source: eight passed at 81.72–86.14% coverage;
  25321 failed coverage only (78.06%); 25328 failed coverage (51.88%) and boundary
  recall after the flight band through the opening never became navigable. All
  ten landed without contact. The suite is failed and both failures are retained.
- Over the two suites flown with the progress-aware rule, **11 of 13** fresh
  predeclared layouts passed every gate; no flight in any suite has recorded a
  contact. The 25328 mechanism is the slow clearance of the flight band through
  an open doorway (about 0.85 m per hover station), a sensing limit rather than a
  planner weight: replaying frontier-style valuations changed none of its
  decisive choices. Faster band clearance through openings is the remaining
  exploration item and needs no hardware.

Historical recording cleanup recovered about **13.8 GiB**, followed by another
**3.58 GiB** from completed recent trials, using exact-byte hardlinks: every image
filename and content was retained. The runner now compacts duplicate JPEGs after
capture ends; active recordings, unique images and videos are untouched. New flights refuse to
start with less than 3 GiB free. That is a storage admission check, not a change
to flight difficulty, sensors or scoring.

A further **4.91 GiB** was recovered by losslessly compressing 294 diagnostic
JSONL logs from 104 completed trials. Each archive was fully decompressed and
hash-checked before its redundant raw copy was removed. Reports, videos, scores
and review images remain accessible. Use `python -m scripts.archive_recording_logs
restore RECORDING_FOLDER` for historical tools that expect raw JSONL paths;
`archive` reclaims the restored copy after diagnosis. Active recordings are refused.

The blind test still uses a provisional synthetic aircraft and a 960 × 540
calibrated camera. The board uses VGA, and the new physical assembly has no
measured mass or calibration. Do not call those a matched simulation/physical
comparison. Qwen interprets images and supplies bounded semantic hints; OpenVINS
and multiview geometry estimate motion and space; the geometric planner chooses
clear routes. The LLM never receives hidden scene geometry or drives PWM.

The full exploration flights use the existing Rapier simulator/controller, not
the ESP32 sketch. The new C++ onboard controller has separate attitude-plant and
HTTPS integration tests; the HTTPS harness supplies stationary synthetic IMU and
fixture images. These two test paths do not establish a complete hardware flight
or a matched simulation of the new as-built mechanical stack.

## What hardware still has to establish

The first use is **USB/camera/IMU bench testing with motors disconnected**.
Then verify wiring, actual motor order, gyro axes and battery ADC before bounded
propeller-free pulses. Measure loaded thrust/current, battery sag, mass, vibration
and control/camera timing before restrained tuning. A flight-ready label requires
those measurements plus independently checked position/height feedback and a
protected short hover. Software tests and a circuit-rule pass cannot substitute
for them. The new printed stack's estimated mass is not the old simulation mass.

The earlier secure external API/MCP, broad multi-aircraft operation and final
clean-machine release remain product-roadmap work; this milestone does not
silently mark those unrelated items complete.
