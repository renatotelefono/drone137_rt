# Simulation and real-drone test comparison

This is the reference section for comparing Drone137's existing tests with the
first physical Scout 110-B. **No real-drone measurements have been recorded.**
The 23 October baseline is frozen. The separate 24 October update below adds
new software builds and synthetic flights, while retaining the earlier failures.

The [frozen pre-hardware JSON snapshot](test-data/pre-hardware-2026-10-23.json)
contains exact values, individual outcomes, gates, configuration/model/source
identities and SHA-256 hashes of six original evidence files. The source-evidence
commit identifies where the records were copied from; historical tests can have
different source hashes. Preserve this snapshot when adding future results.

The [physical-run template](test-data/hardware-run-template.json) provides the
matching measurement fields. Its `not_run` state and `null` measurements are
intentional. A missing measurement is not zero, and a template is not a test pass.

## Six-item preparation update — 24 October

[Implementation and build package](pre-hardware-six.md) ·
[Machine-readable new evidence](test-data/pre-hardware-six-2026-10-24.json).

- **318/318 Python tests** pass, including the shared onboard controller and host
  connection/fault/recording contracts. These are test cases, not flight counts.
- **19/19 blind/component JavaScript tests and 6/6 mission-physics checks** pass.
  The first combined runner invocation missed the mission input argument;
  that error is retained separately from the corrected passing mission run.
- Safe and restrained ESP32 builds compile. The shared C++ controller has its
  own attitude-plant/TLS tests; the exploration flights below use the existing
  Rapier controller. Neither path is a physical flight.
- Carrier DRC/ERC have zero violations; 65 schematic/PCB pins match. Five
  printable meshes are closed/connected. Actual fit, mass, temperature, supply
  performance and MCU control/camera timing remain unmeasured.
- Qualification-04 finished **1/3** (including a disk-full failure).
  Qualification-05 finished **2/3**. Those layouts became development data;
  subsequent fixes do not replace their original results.

Qualification-06 finished **2/3** on predeclared layouts **17551, 17552, 17553**.
Coverage was 83.07%, 84.01% and 81.34%; the third failed after a model caption
connection error, landing away from launch and missing a journal entry. That
run remains failed. Development-76 passed after the transport/journal changes;
qualification-07 finished **2/3** on frozen seeds 18661/18662/18663. Its third
flight failed only false-free space (5.02197% versus a 5% maximum); all three
returned and landed without contact. That failure is retained. The new
mechanical stack and the physical VGA camera are not matched to these historical
simulation assumptions; measured component and sensor revisions are still needed.

The subsequent suites retain their original gates and complete denominators:

| Suite | Fresh layouts | Result | Failure retained |
| --- | --- | --- | --- |
| Qualification-08 | 19771 / 19772 / 19773 | 2/3 | First room: 63.39% coverage; all landed without contact |
| Qualification-09 | 20881 / 20882 / 20883 | 2/3 | First room: link watchdog latched, off-launch landing; no contact |
| Qualification-10 | 21991 / 21992 / 21993 | 1/3 | First room: 56.81% coverage, 59.22% boundary recall; flight band through the partition opening never cleared; all landed without contact |
| Qualification-11 | 23101 / 23102 / 23103 | 2/3 | Second room: 75.04% coverage only (first room 77% mapped); all crossed the opening and landed without contact |
| Qualification-12 | 24211 / 24212 / 24213 | **3/3** | Coverage 82.06% / 81.99% / 83.75%; all crossed the opening, landed without contact; source verified unchanged |
| Qualification-13 | 25321 – 25330 (ten) | 8/10 | 25321: 78.06% coverage; 25328: 51.88% coverage, opening never navigable; all ten landed without contact |

Development-78 passed the exposed coverage failure after exact voxel-ray
traversal replaced fixed-distance sampling. Development-79 passed the exposed
watchdog room after diagnostic I/O moved outside the control event loop:
83.19% coverage, 1.95% false free, 2.99 cm pose RMSE, 4.88 cm return error,
zero contacts, landed/persisted. Its maximum command acknowledgement interval
was 255 ms. The old watchdog's precise cause was not captured; a passing rerun
is not proof of causation. Development runs are excluded from qualification rates.
Qualification-10's failed room reached the partition opening twice but its
repeated-view discount, inflated by transit frames, left the unresolved doorway
at about 1/30 of its information value; the discount is now bounded at two
attempts. Occupancy, clearance and every gate are unchanged. Development-80
passed that exposed room with the bound: 80.57% coverage, 1.09% false free,
3.38 cm pose RMSE, 7.72 cm return error, zero contacts, landed/persisted.
Qualification-11's failed room then exposed the bound's cost, thirteen
fruitless views of a blank wall strip, so view attempts are now progress-aware:
they count only while a view adds no flight-band evidence and reset on
progress. Development-81 (83.53%) and development-82 (81.95%) pass both exposed
rooms with that rule; both are development results. Qualification-12 then
passed 3/3 on fresh predeclared layouts with frozen source: the first complete
suite pass. Qualification-13 then passed 8/10 on ten fresh layouts, 11 of 13
under the current rule; the two coverage failures are retained and the 25328
mechanism, slow flight-band clearance through an open doorway, is recorded as
the remaining software item for exploration.
No room difficulty, flight deadline, battery reserve or acceptance gate changed.

## Historical results frozen on 23 October

| Test | Recorded result | What the denominator means | Real drone |
| --- | --- | --- | --- |
| Scout 110-B component flight | **5/6 passed** | Six separate 20-second physics scenarios | Not measured |
| Scout 110-B engineering checks | **4/6 passed** | Flight pass plus at least 2:1 modeled thrust/weight reserve | Not measured |
| Scout 110-B known-map object-search missions | **24/24 passed** | Eight known cases, three repetitions each | Not measured |
| Blind mapping, qualification-03 | **2/3 passed** | Three reserved layouts, all attempted | Not measured |
| Host connection/protocol | **25/25 tests passed** | Distinct host tests against a protocol-only emulator | Not tested on MCU |
| Python regressions at handoff | **264/264 passed** | Software test cases; not flights | Not a hardware metric |
| JavaScript checks at handoff | **8/8 blind controller; 11/11 component physics; 6/6 mission physics** | Three independent software test groups | Not a hardware metric |

Do not add these counts into one success rate. Known-map navigation, blind
exploration, image recognition and software regressions answer different questions.
The historical blind suite failed overall. The 24/24 result does not override
the low-battery failure or establish 95% reliability in unfamiliar real rooms.

## Scout 110-B physical behavior baseline

Source: [six component trials](../hardware/esp32/indoor/scout-110-bench/simulation-checks.json).
Aircraft `scout-110-bench-b@1`; mass **63.26 g is estimated**; engine Rapier 0.21.0;
seed 137; each scenario lasts 20 simulated seconds. Assembly SHA-256:
`4cd39ed4426bbdac53ce29a71692b7a3936b471f3ead0facdac330dbcded3f58`.

| Scenario | Flight | Engineering | Hover RMSE (m) | Transit RMSE (m) | Maximum tilt (deg) | Landing speed (m/s) | Minimum loaded voltage (V) | Static thrust/weight |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Nominal | PASS | PASS | 0.00518 | 0.00139 | 11.674 | 0.17913 | 3.400 | 2.174 |
| Low battery | FAIL | FAIL | 0.67501 | 0.90999 | 0.218 | 0.00000 | 3.125 | 1.466 |
| Gust | PASS | PASS | 0.00518 | 0.04672 | 11.674 | 0.17912 | 3.400 | 2.174 |
| Link loss | PASS | PASS | 0.00518 | 0.00000 | 12.434 | 0.17901 | 3.400 | 2.174 |
| Weak motor | PASS | PASS | 0.00518 | 0.00285 | 11.674 | 0.17919 | 3.400 | 2.174 |
| Pessimistic assumptions | PASS | FAIL | 0.08442 | 0.01279 | 11.670 | 0.17934 | 3.400 | 1.522 |

Read zeros with the scenario gates: the low-battery case did not lift off, and
link loss deliberately interrupted transit. Neither zero is evidence of perfect
flight performance. Static thrust reserve is a separate full-output model
calculation, not the flight's peak measured current or voltage.

These trials use ideal external position/velocity/attitude reference, estimated
motor/battery curves and synthetic camera timing. They do not test recognition,
real Wi-Fi, MCU firmware timing, propeller flex or measured aerodynamics. Start
the physical comparison by measuring motor/propeller thrust versus duty and
loaded voltage, battery sag and assembled mass; save new SQLite component
revisions and run a second, calibrated simulation without replacing this baseline.

## Full object-search mission baseline

Source: [qualification-04 data](mission-integration-validation.json) and
[full report with earlier failed attempts](mission-integration-validation.md).
Qwen3-VL-2B Q4_K_M plus Florence-2 base-ft; Scout 110-B; ideal external positioning
and a known synthetic map. Raw Qwen proposals and verified location claims are
different outputs: 94 proposals occurred on absent controls, with none confirmed.

| Metric | Simulation result | Existing test gate / interpretation | Real drone |
| --- | ---: | --- | --- |
| Complete missions | 24/24 | At least 95% of all planned missions; eight cases repeated three times | Not measured |
| False confirmations | 0 | Zero permitted | Not measured |
| Missed targets | 0 | Present-target cases | Not measured |
| Location error, median / maximum | 0.07272 / 0.66184 m | Maximum 0.75 m | Not measured |
| Mission duration, median / maximum | 173.26 / 287.00 s | Maximum 300 s | Not measured |
| Inspection latency, median / maximum | 4.297 / 5.210 s | Includes visual verification when requested; not camera transport latency | Not measured |
| Maximum tilt | 4.519 deg | Full-mission profile; do not substitute the component scenario maximum | Not measured |
| Maximum landing speed | 0.19988 m/s | Full-mission profile | Not measured |
| Minimum 3D clearance | 0.56748 m | Measured against modeled obstacle geometry | Not measured |
| Inspected observations / decoded video frames | 207 / 44,415 | Evidence volume, not pass counts | Not measured |
| Peak application memory guard | 4.264 GiB | 5 GiB guard on a **16 GiB host** | Not measured |

Memory is sampled across the application's process tree; the guard uses the
larger of summed RSS and macOS physical footprints. It is not total system RAM
and is not an OS-enforced cap. Actual 8 GB hardware remains untested. Preserve
the metric, process scope, sampling interval and host swap when comparing runs.

The synthetic camera records 960 × 540. The current physical camera bench uses
640 × 480; camera resolution, calibration, mounting, exposure, frame drops and
capture-to-arrival latency must be measured before treating its results as paired.

## Mapping without a supplied map

Source: [blind-exploration evidence](blind-exploration-validation.json).
The controller receives RGB and synthetic IMU data; scoring separately uses the
simulator's hidden ground truth. These are not the known-map Scout mission tests.

| Qualification-03 layout | Coverage | False-free fraction | Boundary recall | Pose RMSE | Return error | Contacts | Landed | Overall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 13191 | 52.55% | 2.32% | 56.99% | 0.05722 m | 0.04994 m | 0 | Yes | FAIL: coverage and boundary recall |
| 13192 | 83.45% | 3.58% | 91.35% | 0.04386 m | 0.14521 m | 0 | Yes | PASS |
| 13193 | 80.72% | 3.10% | 87.43% | 0.06042 m | 0.09205 m | 0 | Yes | PASS |

Original gates: coverage ≥80%, false-free fraction ≤5%, boundary recall ≥70%,
boundary p95 error ≤0.75 m, pose RMSE ≤0.40 m, return error ≤0.40 m, zero contacts,
landing and persisted evidence. Deadline 600 s; application budget 5 GiB.
All three layouts had boundary p95 error approximately 0.30 m. All gates, including
controller input isolation and navigation completion, remain in the JSON.

Development-70 passed with 82.19% coverage. The earlier reserved suites passed
1/3 and 2/3; all three suites remain in the snapshot. All 70 development attempts
remain in the original evidence file. Repeated development attempts must not be
pooled into an independent success-rate claim.

## Historical vision model comparison

Source: [live simulated-flight comparison](vision-flight-validation.json).
These four-case runs used a **generic PX4/Gazebo reference aircraft**, not Scout
110-B. They can inform model selection but are not a direct physics comparison
with the later 24-mission Rapier test. Each configuration completed 4/4 flight
physics checks; none passed the complete task suite.

| Model configuration | Tasks correct | False location claims | Missed/incorrect present targets | Mean camera-decision latency | Peak application memory |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen | 2/4 | 1 | 1/2 | 3.168 s | 3.409 GiB |
| Qwen + Florence-2 | 3/4 | 0 | 1/2 | 3.843 s | 4.469 GiB |
| Qwen + SmolVLM2 | 2/4 | 0 | 2/2 | 3.578 s | 4.898 GiB |

The earlier SmolVLM eager-attention attempt stopped after exceeding the 5 GiB
budget; it remains recorded in `attempts`. Later Florence development repeats
and their failures also remain recorded. Do not replace the original comparison
with the best selected rerun.

## Recording the real drone

1. Copy [hardware-run-template.json](test-data/hardware-run-template.json) into a
   new uniquely named result. Record every attempt, including aborts. Keep this
   frozen baseline unchanged; completed physical summaries belong in a separate
   `docs/test-data/hardware/` directory after review.
2. Record aircraft/assembly/component revisions, battery identity, firmware hash,
   Drone137 commit, model versions/hashes, computer specifications and camera/IMU
   settings. Export the sanitized component configuration, not the credential-
   containing aircraft pairing database.
3. Before execution, freeze the task, initial conditions, scoring windows and
   acceptance rules in a versioned protocol. First stages are camera/IMU bench,
   propellerless motor checks, restrained control and a brief controlled hover.
   Stress/fault cases initially belong on the bench or a restrained fixture;
   this historical table is not an instruction to inject faults in free flight.
4. Record synchronized video, command/response and sensor traces. Use an
   independent measured reference for pose/map accuracy, and record its
   uncertainty. Do not score the estimator against itself. For blind mapping,
   the measured room reference is available only to the scorer.
5. Compare matching units, windows, scenarios and definitions. For numeric
   measurements, report `physical - simulation` with measurement uncertainty.
   If camera, controller, aircraft or task differs, list the differences and
   label the result unpaired. Never average incompatible tests together.
6. Populate measured fields, gate results and evidence hashes. Leave unavailable
   fields null and explain why. Commit reviewed summaries; keep raw footage,
   model weights, certificates and credentials outside Git. Local evidence URLs
   in historical records will not work on GitHub or a fresh computer.

The [build guide](../hardware/esp32/indoor/scout-110-bench/README.md) records the
current order links and remaining work. Flight firmware, the carrier, physical
sensor integration and hardware commissioning remain unfinished. This comparison
section preserves evidence; it does not change physical flight readiness.
