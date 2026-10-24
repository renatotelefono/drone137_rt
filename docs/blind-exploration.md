# Unknown-place exploration experiment

## Current preparation checkpoint — 24 October 2026

The six-item firmware/build milestone and current flight evidence are tracked in
[pre-hardware preparation](pre-hardware-six.md) and the
[comparison section](test-comparison.md). Qualification-07 finished 2/3, with
one false-free-space failure. Development-77 passes after keeping a one-cell
uncertain band around observed surfaces; qualification-08 finished 2/3. Continuous ray traversal repaired its failed
room in development-78. Qualification-09 finished 2/3 after an early watchdog
failure; development-79 passes after diagnostic I/O isolation. Qualification-10
finished 1/3 on fresh layouts 21991/21992/21993; the 24 October continuation at the end of this
file records its diagnosis and the bounded repeated-view discount. The original acceptance gates and room difficulty are
unchanged. This update supersedes the dated progress entries below.

Completed flights now share byte-identical JPEGs with hardlinks, retaining every
path and content. A recording marker prevents compaction during capture. Each
flight writes `recording-storage.json` and a per-file audit; unique images,
videos and failed results stay available. A new flight requires 3 GiB free.
For a completed recording only, run `python -m scripts.compact_recording PATH`.
Older completed recordings also have gzip archives of their raw diagnostic
JSONL logs, verified by full decompression and SHA-256. Reports, videos, scores
and review images remain directly accessible. Per-trial `recording-archives.json`
records both original and compressed hashes. Read the `.jsonl.gz` directly, or
run `python -m scripts.archive_recording_logs restore RECORDING_FOLDER` before
using historical tools that expect the raw paths. Run the same tool with
`archive` after diagnosis to release the restored copy. Active recordings are
refused; corruption never overwrites existing data.

Do not edit hardlinked historical images in place: write any derived image to a
new path. Local models and full recordings remain excluded from Git.


This is a separate experiment from the existing known-map mission benchmark. It is **not qualified for hardware flight**. A good landing or a passing software test is not a successful mapping mission: all gates in `config/blind-exploration-v1.json` must pass.

## Information boundary

The privileged simulator owns the generated workshop, physical bodies, rendered camera and evaluator trace. The exploration process receives calibrated RGB images, timestamps and local pose integrated from synthetic accelerometer/gyro measurements. It receives no room dimensions, object coordinates, renderer segmentation, depth buffer, true pose or authored route. The pose controller also uses the integrated estimate, not the plant's true pose. Renderer truth is available only to the renderer and post-flight scorer.

The current experiment assumes a level launch floor and a clear 0.5 m launch patch. The original floor-appearance mapper failed because raised and occluded surfaces were sometimes projected onto the floor. Its failed trial records and code remain available for diagnosis; it is no longer the active explorer.

The simulator now exports the renderer's transformed static triangle geometry directly to Rapier before arming. Earlier trials used enclosing boxes: the bottle-table box reached 1.5 m although the visible objects reached only about 1.34 m, producing contacts in visually empty air. The original failed records remain intact. The new collider source, triangle count and geometry hash are recorded in each trial. Floor contact retains the existing physical floor, and the moving actor still uses its separate conservative collider. Floor-plan scoring still uses conservative reference boxes and unchanged thresholds; the collision representation change is explicit in the report.

The replacement uses OpenVINS to estimate motion and triangulated landmarks from actual rendered RGB frames and synthetic IMU samples. It now initializes while grounded, latches ground stationarity updates off before liftoff, and uses a small two-axis maneuver at low hover to provide parallax before visual feedback. There is no supplied true pose, map or landmark identity. Its local frame is aligned with the launch heading; it has no loop closure or qualified cross-visit relocalization. Synthetic sensor noise is provisional and substantially more controlled than an uncalibrated low-cost physical IMU. Camera intrinsics, distortion and mounting are explicitly provisional too.

## Local model roles

- Qwen3-VL-2B describes selected actual onboard images, flags wall close-ups and visible opening directions, and answers questions from saved observations. Its bounded view classifications adjust the priority of geometry-approved viewpoints; they cannot create free space or command motors. It does not receive evaluator truth or independently generate reliable metric geometry.
- OpenVINS supplies visual-inertial motion and landmarks. Its native process receives camera files and time-ordered accelerometer/gyro data only.
- The active mapper triangulates bidirectional optical-flow correspondences using the estimated camera motion. It rejects untextured patches, inconsistent matches, insufficient parallax and uncertain range. Plane patches can fill textureless interiors only inside a triangulated support hull and with a second-image photometric check. Planarity is an explicit reconstruction assumption. Individual OpenVINS landmarks are not accepted as reliable range measurements. There is no rendered depth or object-label input.

Plane completion also checks measured depth on both sides of an edge: foreground observations protect objects, and farther observations protect openings inside a wall's support hull. From development-51, filled points must also lie within 0.35 m of triangulated support, measured on the plane, so separate wall sections cannot bridge an unobserved doorway simply because their convex hull encloses it. Photometric agreement alone cannot distinguish similarly coloured walls at different distances. The complete final observed voxel volume is retained as `explorer/map-grid.npz` for diagnosis, but is never supplied to another blind visit.

From development-50, OpenVINS tracks a calibrated rectified pinhole image with zero distortion in its input calibration. Raw sensor JPEGs remain the evidence. The simulated wide lens produced stretched border texels outside the underlying rendered pinhole view; feeding those as real feature bearings caused a severe estimator failure during development-49's ascent. Replaying its recorded RGB/IMU through rectification reduced position RMSE over 12–19.5 seconds from 1.294 m to 0.060 m (98 estimates). This is a diagnostic replay, not a successful flight or general reliability claim. The live flight must independently satisfy every acceptance gate.
- A voxel map records 3D visibility rays and surfaces before projecting an occupancy map. Its horizontal resolution is 0.15 m and vertical resolution is 0.15 m. Navigation currently requires both the conservative lower obstacle footprint and the observed 1.35–1.65 m clearance volume for flight at 1.5 m. The upper-corridor-only trial hit the invisible table proxy described above; that navigation change was reverted pending requalification. Floor visibility alone cannot clear the drone's volume. Measured ceiling endpoints above the map still contribute free rays through the mapped volume. Surfaces need corroboration from translated views; clearing them requires later rays through their volume.
- Navigation chooses reachable information viewpoints from the observed map, checks ongoing motion against new observations, reserves loaded battery voltage for return, and retains a return trajectory from this flight's estimated camera/IMU poses. Recorded-path return cannot create a new route through unknown space; fresh observed obstructions veto it. Planning and ray computation run outside the command/IMU event loop.
- View scoring starts visibility rays at the first grid cell, favors unresolved volume over observed ground, and discounts areas already inspected. None of these priorities changes occupancy or certifies navigation clearance. Qwen's image-coordinate opening guesses have produced false hints during development and remain advisory; contradictory wall-closeup/opening hints are ignored.
- From development-52, viewpoint selection accounts for the increasing uncertainty of distant monocular range and permits a closer observation more than 0.25 m from an earlier station. The previous area-only reward could favour backing away, while a 1.2 m exclusion radius suppressed incremental approach to a doorway. A regression checks forward progress through already-clear space without certifying the unknown passage.
- From development-57, transit can follow a straight observed-clear segment up to 2 m and switch intermediate waypoints without stopping at each one. Observation stations still require a settled hover. Continuous clearance checks, the 0.55 m/s speed limit and battery return reserve are unchanged. Development-56 reached 76.8% coverage with zero contacts and passed every gate except the 80% coverage gate; this transit change targets time spent on unnecessary braking.
- From development-58, view scoring uses occluders in the camera-height band instead of projecting every low and overhead surface into a wall. This affects viewpoint priority only; flight clearance still uses both required bands. From development-59, the initial panorama count is derived from horizontal field of view with at least 30% angular overlap (four directions for the provisional wide lens). Each frontier decision retains its observed grids, arguments, view history and ranked candidates under `explorer/planning-audit`, allowing exact diagnosis without a hidden reference map.
- From development-60, an interrupted route no longer records its unreached destination as an explored view. Completed views record the actual estimated camera stations before and after the sensing translation. Planning audits include sensor time, and interrupted routes retain their actual position, requested destination and reason. A development-59 audit exposed an incorrectly recorded viewpoint more than a metre from the camera trajectory.
- From development-61, a narrow wedge of observed floor retains a positive sensing reward. The previous hard 0.35 m interior-width cutoff gave such glimpses zero value, encouraging departure from incompletely observed openings. A gradual width score still favors broad floor patches without discarding narrow evidence. A regression verifies approach through observed clear space while the unresolved passage remains unavailable for flight.
- Development-61 stopped after a tracking retreat because its only frontier was temporarily rejected. From development-62, temporary rejection causes a bounded hold and fresh re-evaluation instead of falsely reporting no reachable frontier. The initial translated panorama again uses at least eight directions: angular overlap alone did not ensure sufficient triangulated volume in the four-direction experiments. The lens-based minimum overlap still applies to narrower cameras.
- From development-63, new geometry invalidating a sensing side step triggers another clearance-checked baseline at the reached station. It no longer rejects the entire observation station. A tracking retreat still triggers route replanning. Route and sensing interruptions are recorded separately so these distinct causes can be diagnosed.
- Development-63 reached 77.8% coverage and passed every gate except coverage. Its repeated second-room retreats occurred with 80–170 stable tracks because launch-relative position standard deviation crossed 0.15 m. From development-64, OpenVINS exports the joint covariance of the current and approximately one-second-old cloned positions. Tracking checks the largest-axis standard deviation of their difference, including cross-correlation, against 0.05 m. Common position drift is not discarded from the map-quality assessment: startup retains its 0.15 m gate, exploration requests return at 0.25 m accumulated axis uncertainty, and a 0.4 m hard bound rejects tracking updates. Feature, velocity, gravity, freshness and motion-innovation gates remain active. Recovery reports now retain the actual failed quality checks instead of always blaming feature count. These are provisional estimator policy thresholds; independent physical error and clearance acceptance gates are unchanged.
- From development-65, the initial translated panorama is included in view history and sensing-attempt discounts. Previously only later frontier views were recorded, so launch-area uncertainty could repeatedly look uninspected. Replaying development-64's late planning decision with the missing startup observations removed its long return-to-launch detour from the ranked candidates. This is a planning replay, not a flight pass.
- The provisional camera uses a 100-degree vertical field of view. Development-53 changes its mounting from -25 degrees to level forward: the downward view provided plentiful floor points but insufficient rays through the upper flight-clearance volume. This is an explicit camera design change with the same scene, aircraft physics and acceptance gates, not a specification or calibration of the purchased camera. Geometry retains the recorded 960 × 540 image resolution. Takeoff advances in stages and uses measured feature tracking to select viewing directions. Bad visual corrections are rejected; visual yaw correction cannot tilt the IMU roll/pitch reference. Each new visit archives the received sensor calibration.
- Depth Anything V2 Metric Indoor Small was tested as a dense geometry prior. Its scene-dependent scale caused false obstacles, so it is retained as an experimental alternative and is not loaded by the active explorer.

A SegFormer B0 probe was evaluated locally but misclassified close-up launch-floor imagery. It is not used by the active explorer. Its NVIDIA research/evaluation-only license also excludes it from a commercial deployment bundle. Downloaded weights remain ignored in `.local`.

## Persistent environments

`.local/data/places.sqlite3` stores named places, individual visits, the latest map per visit with a revision counter, and append-only image-hashed observations. It does not retain every intermediate map revision. Image evidence remains in the visit's validation directory. Failed and partial visits remain visible. The browser page at `/places` displays these records. Its local-model question endpoint retrieves bounded, diverse historical observations from the requested place, with cited camera evidence; it cannot issue flight commands. Retrieval uses lexical matching and novelty, without a second embedding model.

A new blind test begins with an empty map even when that place has earlier visits. Historical maps are retained, but navigation reuse needs visual relocalization and freshness checks; that capability is not yet qualified. Deleting the image directory preserves the journal but removes its viewable image evidence, so database and visit directories must be backed up together.

## Build the optional estimator

The pinned OpenVINS revision, license and local portability patch are recorded in `config/openvins-runtime.json`. The linked native bridge and upstream source are GPL-3.0-or-later; preserve those notices and source obligations when distributing them. Build dependencies are CMake, a C++17 compiler, Eigen, Boost, Ceres, OpenCV 4 and nlohmann-json. The application itself does not need ROS or a cloud service. On the current Apple Silicon development host:

```sh
.local/vision-env/bin/python -m scripts.build_openvins --fetch \
  --prefix /opt/homebrew \
  --opencv /opt/homebrew/opt/opencv@4/lib/cmake/opencv4
```

`--fetch` is needed only when the pinned source is absent. Compilation is separate from the runtime memory measurement. The build helper refuses to overwrite an unexpected upstream revision or incompatible local changes.

## Execute a virtual physical test

Start the main local model service first. Use its process ID so the memory guard includes its model children:

```sh
HF_HUB_OFFLINE=1 .local/vision-env/bin/python -m scripts.run_blind_test \
  --seed 7301 --output .local/validation/blind-mapping/my-new-trial \
  --place workshop-blind-7301 --name 'Unknown workshop 7301' \
  --memory-pid MAIN_SERVICE_PID
```

The output directory must be new. The wrapper starts the physical simulator, runs the real-time camera client, waits for flight completion, scores the result and exits nonzero for failed acceptance. No test process receives the reference map to plan its route. Model weights must already be installed; inference uses local files only.

Each trial retains onboard video, camera images, visual-inertial estimates, the model journal, estimated map, separate private telemetry, a source manifest, memory measurements and a report. From development-22 onward, a source/configuration archive is also saved with each trial. Runtime summaries are never allowed to self-award coverage. `report.html` shows the reconstructed map beside the **post-flight evaluator reference** and includes every acceptance gate. Camera and algorithm changes are recorded per development trial; acceptance thresholds remain unchanged. The frozen protocol's historical depth-model annotation describes the initial implementation; each trial's `geometry_method` records the actual geometry used.

The active mapper does not load PyTorch, Transformers or a learned depth model;
`requirements-mapping.txt` contains only its Python runtime dependencies. The
legacy learned-depth experiments need the separate vision-reviewer environment.
The native estimator still needs the build dependencies listed above.

The latest launcher also measures the complete startup and flight process tree, including collision-mesh preparation. It freezes and executes the evaluator source copied before liftoff. Delayed visual corrections update the retained IMU state history and propagate velocity corrections forward, so overlapping delayed observations cannot repeatedly apply the same stale-state error.

Startup now waits for at least nine seconds of stationary IMU calibration; motion or acceleration inconsistent with rest resets the sample window. Gravity and gyro bias use averaged samples, excluding the simulator's initial settling motion. A controller regression checks a twenty-second IMU-only hover across three noise seeds. Before visual feedback is enabled, a small two-axis maneuver inside the declared launch patch supplies parallax; the estimated position must agree with the short inertial trajectory and the gravity direction must agree within one degree. The gravity check remains active after startup. These checks are provisional synthetic-sensor checks, not measured calibration of a purchased IMU. The ascent routine no longer turns away from a valid view because of one low feature count.

The development seed is 7301. Seeds 8401–8403 are reserved for qualification after the development flight passes. Success on these synthetic scenes would still not establish real-world reliability or actual operation on an 8 GB machine. The current host has 16 GB; the experiment enforces a measured 5 GiB application budget to reserve room for an operating system.

## Resumption checkpoint — 23 October 2026

The interrupted work was recovered in `.local/checkpoints/recovered-work-20261023-101736`:
a working-source archive, a consistent SQLite backup and `status.json`. At that
checkpoint there were 65 visits, 1,556 observations and 64 scored development
attempts; none passed all gates. Development-65 landed without contacts and
passed all gates except coverage (76.4% against 80%), stopping on its battery
return reserve. Development-63 reached 77.8%, also failing coverage only.

Three source files had changed after development-65. Before resuming flights,
36 mapping/persistence regressions passed. The pending faster-yaw diagnostic
failed its 0.2 m absolute drift criterion after twenty seconds of IMU-only
turning. Replaying the same diagnostic at the previous 0.65 rad/s rate also
failed (up to 0.251 m), so this did not establish acceptable faster turning or
identify yaw rate as the sole cause. The candidate 0.9 rad/s controller/planner
changes were reverted, and the experimental diagnostic was archived at
`.local/validation/blind-mapping/faster-turn-diagnostic.test.mjs`; it is a
historical source copy, not a passing regression. Absolute position cannot be
maintained indefinitely by these uncorrected inertial measurements.

Development-66 tests only the remaining settling change: 0.2 m/s maximum
estimated speed and 0.15 seconds within the existing position/heading bounds,
instead of 0.12 m/s and 0.3 seconds. It passed every independent gate: 81.7% coverage, 4.25% false free space,
90.8% boundary recall, 3.3 cm position RMSE, 3.6 cm return error, zero contacts,
a successful landing and 3.54 GiB peak application memory. This is one
successful development flight after 65 earlier attempts, not a reliability
rate. Its 47 observations and final map were persisted under the existing
named workshop. No physical calibration or hardware readiness is implied.

The unchanged implementation is being evaluated on the three predeclared
seeds 8401–8403 by `scripts.qualify_blind_exploration`. The suite freezes the
source manifest and its full planned denominator before starting; any source
change prevents subsequent flights from being silently mixed into the same
qualification. Results are in `.local/validation/blind-mapping/qualification-01`.
No held-out success is claimed until those results are finalized.

## Current sequence

The requested functional blind test passed in development-70. Preparation items 1–8 can proceed while unfamiliar-layout reliability remains open. Item 1's host protocol/emulator is verified; onboard firmware, estimator/freshness integration, the unified mission interface, authenticated remote API/MCP, offline packaging, complete fault acceptance and build artifacts remain unfinished or partial. See the current table in `tasks.md`. Physical tuning and commissioning require hardware. Historical updates below describe each stage at the time; the latest suite is qualification-03 (2/3 passes).

## First reserved-layout suite and next correction

`qualification-01` finished with 1/3 passes: seed 8401 84.6% coverage, seed 8402
68.5%, seed 8403 79.3%. The latter two failed only the unchanged 80% coverage
gate. All three landed, returned within tolerance, avoided contact and passed
the remaining accuracy, persistence and memory checks. This is a failed suite.

Development-67 uses 8402 to investigate local-planning commitment. A replay
showed a 5.25 m detour winning score 4.31 over a nearby 0.45 m inspection scoring
3.96, abandoning a promising approach. Bounded hysteresis selects an already
cleared forward candidate within 1.5 m when it retains at least 80% of the
best distant candidate's score. Substantially better destinations, rejected
routes and exhausted local views still override it. Flight clearances, speed,
battery reserve and scoring thresholds are unchanged. Thirty focused
regressions passed; replay is not flight acceptance. The flight result must be
read from its finalized score. Layout 8402 is now development data, not held out.

Development-67 passed all gates: 82.46% coverage, 4.37% false free, 6.34 cm pose
RMSE, 9.45 cm return error, zero contacts and landing. It used the same scene,
aircraft, battery, camera, clearance policy and acceptance criteria as the failed
8402 qualification flight. Because this layout informed the change, this is a
development result. Thirty focused regressions also passed.

The unchanged implementation is now frozen for `qualification-02`, predeclared
with fresh layouts **9991, 9992, 9993** before observing their results. The
original protocol thresholds are retained; `planned_seeds` in the suite record
defines the fresh case set separately from the historical protocol metadata.
All three planned flights stay in the denominator, including failures or
unexecuted cases. No source changes are permitted during that suite.

Qualification-02 finished **2/3**: 9991 passed at 80.35%, 9993 passed at 80.73%,
and 9992 failed before mapping. Its visual/inertial estimate diverged during
the low-hover initialization maneuver. The quality gates rejected it before
visual feedback could reach the controller; the aircraft landed without
contact. The entire suite is failed, not two passes with the startup omitted.

Development-68 moves the initial visual/inertial qualification before liftoff.
Previously only IMU calibration ran on the ground; OpenVINS started during a
hover. The new sequence requires a fresh, finite, geometrically consistent
estimate while stationary, then retains the two-axis maneuver and the original
post-motion checks before visual feedback. Future-dated observations are also
rejected. 31 focused regressions passed. This flight is still being evaluated.

Development-68 failed its new ground check before liftoff. Stationary covariance
still grew, so moving initialization earlier alone was insufficient. The
upstream beginning-only zero-velocity-update (ZUPT) lifecycle can turn off after
enough clone states even when no movement was commanded. Missing early shared
image tracks can therefore leave the static estimator without corrections.
A sensor-only replay of development-68 reproduced 26.4 m position standard
deviation at 18.9 s; allowing continued ground stationarity checks reduced it
to 0.103 m on the same inputs. This is estimated uncertainty, not independently
measured positioning accuracy or a successful flight.

Development-69 adds a ground-phase flag to the native integration. It preserves
the upstream image/IMU checks for each stationary update, permits retrying those
checks while unarmed, and permanently disables this mode when the explorer
ends the ground phase before its first liftoff command. It cannot be re-enabled
in flight. Existing motion, gravity and initialization acceptance checks remain.
The native bridge rebuilt successfully; 32 focused regressions passed, including
a native check that rejects re-enabling ground updates after liftoff. Replays
and build evidence are under `startup-diagnostics/`. The full flight is pending.

Development-69 passed ground initialization, but the post-motion comparison
timed out. The independent trace showed VIO remained about 1–2 cm from the
physical position during the maneuver, whereas unaided IMU disagreement grew
from 5.2 cm at 20.4 s to 16.8 cm at 25 s. Its return error was 0.52 m, so the
mission failed; no rejected visual estimate reached flight feedback.
Development-70 shortens the five-point circuit to three stations on both
horizontal axes and back to the origin after vertical takeoff. The 0.15 m
agreement gate and other quality checks are unchanged. The flight is pending.

Development-70 **passed every gate**: 82.19% coverage, 3.80% false free space,
8.42 cm pose RMSE, 13.94 cm return error, zero contacts, landing and persistence.
Its wall time was 336.3 seconds. The requested blind-mapping test now completes
with the repaired ground-phase lifecycle and shorter two-axis maneuver. This
is a development pass; it does not erase earlier failures or establish a
reliability percentage. The implementation is frozen for qualification-03 with
predeclared fresh seeds **13191, 13192, 13193**. Software preparation items 1–8
can now proceed alongside that broader verification.


Qualification-03 completed on 23 October 2026 with **2/3 passes**. The complete
predeclared set is retained:

| Seed | Coverage | False free | Position RMSE | Return error | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| 13191 | 52.55% | 2.32% | 5.72 cm | 4.99 cm | Failed coverage and 56.99% boundary recall |
| 13192 | 83.45% | 3.58% | 4.39 cm | 14.52 cm | Passed every gate |
| 13193 | 80.72% | 3.10% | 6.04 cm | 9.20 cm | Passed every gate |

All three returned, landed, persisted observations and recorded zero contacts.
Source stayed frozen for the three flights; no scoring threshold was changed.
The first layout remains a planning/coverage failure despite accurate tracking.
This suite is failed overall and does not establish 95% reliability. Host
connection work proceeds under the completed development-70 functional gate.

## 24 October continuation: qualification-10 and the bounded view discount

Qualification-04 to -09 and development-73 to -79 are summarised in
[pre-hardware preparation](pre-hardware-six.md). Qualification-10 finished **1/3**
on frozen predeclared layouts:

| Seed | Coverage | False free | Position RMSE | Return error | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| 21991 | 56.81% | 0.27% | 4.53 cm | 7.41 cm | Failed coverage and 59.22% boundary recall |
| 21992 | 84.73% | 1.02% | 3.37 cm | 6.64 cm | Passed every gate |
| 21993 | 82.11% | 0.65% | 5.20 cm | 8.31 cm | Passed every gate |

All three returned, landed, persisted evidence and recorded zero contacts.
Every generated workshop shares a 12 × 10 m floor divided by a partition at
x = 6 m with one 2 m opening. Passing flights in qualification-08 to -10 mapped
69–79% of the far room; 21991 mapped 16% and 19771 (qualification-08) 28%.
In 21991 the aircraft stood in the opening twice, around 100–117 s and
130–137 s. Floor beyond the opening was observed as a free strip, but the
1.35–1.65 m flight band through it never accumulated two free rays per voxel,
so no collision-clear viewpoint existed past about 4.3 m launch-local x. The
67 unresolved doorway cells had 7.4 recorded view attempts on average (maximum
16): transit frames and the two stations of every sensing translation all
count. The `1/(1+4n)` discount reduced their combined information value from
41.3 to 1.36. At planning record 13 the best candidate was a 7.4 m detour to the
first room's far corner (score 1.04) against the 0.6 m doorway view (0.81). The
flight spent its remaining battery in the first room's south strip, with four
tracking recoveries facing blank walls, and stopped on the battery return
reserve at 283 s.

The repeated-view discount in `app/frontier_planner.py` is now bounded:
`interest /= 1 + 4·min(n, 2)`, a floor of one ninth. Two failed attempts mark a
region as hard; further attempts no longer push a still-unresolved region below
other unresolved regions, so ranking stays information-driven. Station
suppression, travel cost and visit counts still deter re-sensing from the same
place, and nothing here grants clearance or changes occupancy, sensors, speed,
battery reserve or scoring. A counterfactual replay of 21991's recorded planning
grids (not a flight) selects the opening at records 9 and 13 (5.23 versus 5.10 and
2.14 versus 1.24) and leaves record 12 unchanged. Alternatives were compared on
the same records: removing the discount, capping it at one attempt, or using
square-root and linear forms all also select the opening at record 13 but change
more of the recorded decisions in passing flights. A regression test fixes the
bound. The exposed layout 21991 is development data from here on.

Development-80 reran 21991 with the bounded discount and **passed every gate**:
80.57% coverage, 1.09% false free space, 3.38 cm pose RMSE, 7.72 cm return
error, zero contacts, landing and persistence; 56 observations in 275 s, one
tracking recovery, 67% of the far room mapped. Same scene, aircraft, battery,
camera, clearance policy and acceptance criteria as the failed flight. Because
the layout informed the change, this is a development result. The unchanged
implementation is frozen for `qualification-11`, predeclared with fresh layouts
**23101, 23102, 23103** before observing their results; all three stay in the
denominator.

Qualification-11 finished **2/3**; the source hash set was verified unchanged
after the third flight:

| Seed | Coverage | False free | Position RMSE | Return error | Far room mapped | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 23101 | 82.83% | 1.34% | 3.50 cm | 10.17 cm | 76% | Passed every gate |
| 23102 | 75.04% | 1.90% | 2.80 cm | 6.65 cm | 73% | Failed coverage only; first room 77% |
| 23103 | 80.47% | 1.18% | 5.76 cm | 9.53 cm | 66% | Passed every gate |

All three returned, landed, persisted evidence and recorded zero contacts, each
stopping on the battery return reserve near 280 s. The partition opening was
crossed in every flight, so the bounded discount removed that failure mode in
this batch, but 23102 left 23% of its first room unmapped. This suite is failed
overall and does not establish a reliability percentage.

23102's planning records show the cost of the bound. After three decisions in
the far room it returned to the first room, then chose thirteen consecutive
short views of the south-wall strip between 153 s and 217 s: 134 floor cells
beside a blank wall, 55 of which never received a single flight-band ray and
whose attempt counts reached 27. Each view promised about ten units of
information at short range and delivered none. The unbounded discount had been
doing two jobs: discouraging redundant sensing and ending fruitless local
loops; the bound kept the first and removed the second.

The rule is therefore progress-aware. `RaycastMap` accumulates `band_evidence`,
the free-ray magnitude through the 1.35–1.65 m band of each cell, and
`record_view_attempt` compares it with the value at the cell's previous attempt:
a view that added rays resets the count to one, a view that added nothing
increments it, and the original `1/(1+4n)` decay applies to that stale count.
A doorway that is still filling in keeps its information value; a blank strip is
deprioritised after a few fruitless views. The one-cell uncertain ring around
observed surfaces clears only when later rays clear the surface itself, so it
now carries no view priority. Both grids are frozen for planning, written to
every planning audit and to `map-grid.npz`. Nothing here changes occupancy,
clearance, sensors, speed, battery reserve or scoring; 321 regressions pass.

Development-81 reran 23102 with this rule and **passed every gate**: 83.53%
coverage, 1.93% false free space, 6.92 cm pose RMSE, 14.19 cm return error,
zero contacts, landing and persistence; 49 observations, 79% of the far room
and 88% of the first room, no tracking recovery, five south-wall views.
Development-82 reran 21991 and **passed**: 81.95% coverage, 0.97% false free,
4.83 cm pose RMSE, 16.59 cm return error, zero contacts, 74% of the far room.
Both layouts informed the change, so both are development results. The
unchanged implementation is frozen for `qualification-12`, predeclared with
fresh layouts **24211, 24212, 24213** before observing their results.

Qualification-12 finished **3/3**, with the source hash set verified unchanged
after the third flight:

| Seed | Coverage | False free | Position RMSE | Return error | Far room mapped | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 24211 | 82.06% | 1.66% | 7.38 cm | 2.71 cm | 80% | Passed every gate |
| 24212 | 81.99% | 1.38% | 4.21 cm | 6.97 cm | 71% | Passed every gate |
| 24213 | 83.75% | 1.65% | 4.12 cm | 7.37 cm | 74% | Passed every gate |

All three returned, landed, persisted evidence and recorded zero contacts,
stopping on the battery return reserve. This is the first predeclared suite to
pass completely. It is three flights on synthetic layouts with provisional
sensors; it does not establish a reliability percentage, physical readiness or
8 GB operation, and every earlier failed suite remains in the record.

The unchanged implementation is frozen for `qualification-13`, a ten-layout
reliability suite predeclared with fresh seeds **25321–25330** before observing
any result. It is accepted only if all ten flights pass every unchanged gate;
every planned flight stays in the denominator.

Qualification-13 finished **8/10**, source verified unchanged after the tenth
flight:

| Seed | Coverage | False free | Position RMSE | Return error | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| 25321 | 78.06% | 0.75% | 2.7 cm | 6.4 cm | Failed coverage only |
| 25322 | 85.88% | 1.17% | 5.1 cm | 12.3 cm | Passed |
| 25323 | 82.83% | 1.27% | 4.7 cm | 6.8 cm | Passed |
| 25324 | 84.41% | 1.38% | 3.1 cm | 5.9 cm | Passed |
| 25325 | 86.14% | 1.59% | 5.6 cm | 7.0 cm | Passed |
| 25326 | 81.72% | 1.92% | 3.6 cm | 5.2 cm | Passed |
| 25327 | 82.37% | 1.14% | 2.5 cm | 7.4 cm | Passed |
| 25328 | 51.88% | 0.41% | 3.0 cm | 9.8 cm | Failed coverage and 62.3% boundary recall |
| 25329 | 84.07% | 1.64% | 3.3 cm | 4.1 cm | Passed |
| 25330 | 82.53% | 0.92% | 3.9 cm | 5.6 cm | Passed |

All ten returned, landed, persisted evidence and recorded zero contacts. 25328
reached the opening twice without the flight band through it becoming
navigable and mapped 7% of the far room; 25321 mapped 73% of the far room and
83% of the first room. The suite is failed; both failures are retained.

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

Probe scripts for these replays are kept with the earlier ones under
`.local/maintenance/` (`attempt-discount-probe.py`, `interest-breakdown-probe.py`,
`frontier-valuation-probe.py`); the saved counterfactual record is
`.local/validation/attempt-discount-diagnostic.json`.
