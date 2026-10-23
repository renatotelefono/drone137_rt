# Drone137 full-mission qualification

The frozen **qualification-04** batch passed **24/24 complete missions**, with **0 false confirmations**. All 24 planned missions were executed. This is observed repeatability on eight known synthetic cases, not proof of 95% reliability in unfamiliar real rooms.

The tested aircraft is **scout-110-bench-b@1**, frozen assembly SHA-256 `4cd39ed4426bbdac53ce29a71692b7a3936b471f3ead0facdac330dbcded3f58`. Qwen3-VL-2B Q4_K_M and Florence-2 base-ft run locally. The mission starts through the same API used by `/control`; its camera and physics belong to the local service.

| Case | Full missions passed | Largest location error | Longest mission |
|---|---:|---:|---:|
| hard-west-dim-present | 3/3 | 0.108 m | 76.7 s |
| hard-west-dim-absent | 3/3 | No location claimed | 216.2 s |
| hard-east-glare-present | 3/3 | 0.070 m | 227.6 s |
| hard-east-glare-absent | 3/3 | No location claimed | 287.0 s |
| hard-west-occluded-present | 3/3 | 0.662 m | 152.9 s |
| hard-west-occluded-absent | 3/3 | No location claimed | 174.2 s |
| hard-east-motion-present | 3/3 | 0.337 m | 190.1 s |
| hard-east-motion-absent | 3/3 | No location claimed | 180.6 s |

Acceptance requires at least 95% complete missions, zero false confirmations, location error at most 0.75 m for present targets, full search coverage for absent controls, a clean landing, no contacts/envelope violations, bounded attitude and battery operation, decodable video and a 300-second deadline. Peak measured application memory was **4.26 GiB** against a 5 GiB guard. The test host has **16 GiB**; actual 8 GB hardware remains untested.

The batch recorded 44,415 decoded video frames and 207 inspected images. Median inspection latency, including verification when requested, was 4.30 s. Qwen made 94 target proposals on absent controls; none became a verified location. A complete-mission pass is not perfect raw image classification.

## Integration and fault checks

- **200/200 Python regression tests passed.**
- The operator dashboard generated and launched a mission, was closed during flight, and reconnected to the continuing mission; the aircraft found the target and landed.
- Dashboard `Return and land` and `Land here` checks both ended landed with zero contacts. These intentional interruptions remain cancelled missions.
- The initial 20-second local-landing test wait expired while video/browser finalization continued. Telemetry confirms landing; final state and video completed successfully.
- A reproduced invalid altitude command now fails before publication. Injecting a radio-pump rejection triggers an observed aircraft-watchdog landing while preserving the original error.

## What changed

The flight uses height-aware routes instead of treating low clutter as full-height columns. Planning clearance remains 0.58 m, inspection clearance 0.61 m, and the monitored envelope 0.35 m, measured against three-dimensional obstacle boxes. Scene geometry, camera impairments, mission deadline and scoring tolerance were retained. This metric migration is explicit in the protocol; the Rapier microquad also differs from the earlier generic PX4 backend.

Measured hover overshoot is retained for clearance checks but is not copied into a new command. Command altitude stays at or below 1.8 m. Planner commands are validated before publication; transport faults have a latched watchdog-landing recovery. Neither recovery nor a later retry turns the original failed mission into a pass.

## Earlier attempts remain visible

| Attempt | Passed / planned | Executed failures | Not run | False confirmations | Acceptance |
|---|---:|---:|---:|---:|---|
| qualification-04 | 24/24 | 0 | 0 | 0 | PASS |
| qualification-03 | 15/24 | 1 | 8 | 0 | NOT MET |
| qualification-02 | 7/24 | 1 | 16 | 0 | NOT MET |
| qualification-01 | 7/24 | 1 | 16 | 0 | NOT MET |
| full-suite-01 | 6/8 | 2 | 0 | 2 | NOT MET |
| development-11 | 2/2 | 0 | 0 | 0 | PASS |
| development-10 | 0/3 | 2 | 1 | 0 | NOT MET |
| development-09 | 1/2 | 1 | 0 | 0 | NOT MET |
| development-08 | 1/1 | 0 | 0 | 0 | PASS |
| development-07 | 0/2 | 1 | 1 | 0 | NOT MET |
| development-06 | 1/2 | 1 | 0 | 0 | NOT MET |
| development-05 | 1/2 | 1 | 0 | 0 | NOT MET |
| development-04 | 2/2 | 0 | 0 | 0 | PASS |
| development-03 | 1/2 | 1 | 0 | 0 | NOT MET |
| development-02 | 0/1 | 1 | 0 | 0 | NOT MET |
| development-01 | 0/1 | 0 | 1 | 0 | NOT MET |

Small development attempts can pass their selected cases without constituting the final 24-mission qualification. Aborted runs retain their full planned denominator. Qualification-03 stopped after a rejected 1.800006 m command: 15 passes, 1 failure and 8 not run. Its failure did not establish a landing and remains a failure.

## Hardware handoff

Build the [Scout 110-B bench prototype](../hardware/esp32/indoor/scout-110-bench/README.md). Its consumed-parts allowance is $45.09; the battery seller’s four-pack makes the initial purchase allowance $56.33 before shipping/tax and other minimums. Estimated mass is 63.26 g, not measured.

The separate component stress study passed **5/6 flight scenarios** and **4/6 thrust-reserve engineering checks**. Low battery failed. The 24 mission runs start with a full modeled battery and do not supersede this stress result. The flight-controller firmware, measured motor/battery data, carrier design and real indoor position reference must be completed before physical flight. Start with the camera and frame bench work.

## Reproduction and evidence

```sh
.local/laya-env/bin/python -m app.server --mode recon --port 8137
# Start the installed local model through /control, then:
.local/laya-env/bin/python -m scripts.evaluate_missions \
  --port 8137 --assembly scout-110-bench-b --repeats 3 \
  --output .local/validation/mission-integration/new-attempt
```

[Machine-readable validation](mission-integration-validation.json) contains source/model/aircraft identities, all latest run scores, memory scope, limitations and earlier attempt counts. Large images/videos remain in ignored `.local/data/mission-runs/`; they are not bundled with the repository summary. The local [evidence report](http://127.0.0.1:8142/mission-integration/report.html) opens every retained mission through the main service.
