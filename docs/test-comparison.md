# Simulation and real-drone test comparison

This is the reference section for comparing Drone137's existing tests with the
first physical Scout 110-B. **No real-drone measurements have been recorded.**
All numbers below are historical simulation or host-software results, not new
flights performed while preparing this document.

The [frozen pre-hardware JSON snapshot](test-data/pre-hardware-2026-10-23.json)
contains exact values, individual outcomes, gates, configuration/model/source
identities and SHA-256 hashes of six original evidence files. The source-evidence
commit identifies where the records were copied from; historical tests can have
different source hashes. Preserve this snapshot when adding future results.

The [physical-run template](test-data/hardware-run-template.json) provides the
matching measurement fields. Its `not_run` state and `null` measurements are
intentional. A missing measurement is not zero, and a template is not a test pass.

## Results available now

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
The latest blind suite remains failed overall. The 24/24 result does not override
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
