# Mission-control dashboard validation — 20 October 2026

The new `/control` interface selects an inspection rectangle, accepts a natural
language brief, reviews Qwen's bounded task interpretation and assigns viewpoints
to Scout 01/02. Flights use separate camera clients, episodes and video streams.
One aircraft flies at a time in the shared indoor site; this is sequential fleet
dispatch, not simultaneous multi-aircraft simulation.

Actual Qwen3-VL-2B Q4_K_M + Q8_0 projector / llama.cpp Metal, M4 16 GiB, Chrome:

- **8/8 development mission briefs** interpreted as expected: inventory, doorway
  inspection, view comparison and unsupported tasks. The first prompt incorrectly
  classified a doorway request as general inventory; that failure is retained in
  `.local/validation/mission-control-intent-v1-failed.json`. Explicit task rules and
  examples corrected these test cases. Broader language understanding is unmeasured.
- **105 automated tests passed**, including fleet/lab startup exclusion, camera and
  video namespace rejection, area/draft validation, exclusive dispatch, evidence
  finalization before handoff, stale cameras, partial results, stop/reset and return
  requests. HTTP tests retain loopback host/header checks.
- Final actual-model mission **8045bdf41b654562ba395e34112fc1e2** completed in
  **156.4 seconds** on realism seed 619, nominal baseline. Scout 01 inspected
  entry/stock-rack/passage and returned in **62.0 s**; Scout 02 inspected
  equipment/far-room/seating and returned in **93.9 s**. **6/6 assigned viewpoints**
  produced model descriptions, separate images and finalized video. Peak active
  aircraft count was one. Both videos decoded at **1280×720**, played and sought to
  observation times. Reports preserve the original brief, area and aircraft IDs.
- The live operator-stop test ended the active aircraft, cancelled its queued peer,
  retained its video and required a virtual-site reset before another dispatch.
  Desktop area drawing updated the rectangle correctly. Desktop/mobile layouts,
  completed-observation image previews and no horizontal overflow at 390 px were
  checked; no JavaScript or camera-worker errors were reported.
- Full local evidence: `.local/validation/mission-control-live.json`. Portable
  summary, source hashes and episode IDs: `mission-control-validation.json`.
  Automated output: `mission-control-tests.txt`. Earlier successful fleet trial
  and the failed intent trial remain under `.local/validation`.

The area bounds authored camera viewpoints; transit may leave the rectangle.
Six visited viewpoints do not establish full camera coverage or caption precision.
These runs use a known synthetic site, ideal pose/ranges and kinematic motion.
Concurrent-flight separation, indoor PX4 integration and real-world qualification
remain open. The [mission-control contract](mission-control.md) describes queue
behavior and the path toward flight-dynamics testing.

# Camera realism bay validation — 20 October 2026

Added metre-scaled bottles with caps/ribs, a wheeled chair, a safety cone and
bench clutter to the existing workshop, with local CC0 scanned concrete maps.
The 1280×720 camera (requested 15 fps), 960×540 model snapshots and saved video
share a GPU pass for deterministic exposure, blur, noise, vignette, lens warp,
glare and image shift. Nominal, dim, glare and blur/shift conditions are saved
with the run; cross-condition baseline comparisons are excluded. These effects
are synthetic stress settings, not measured optics, rolling shutter or vibration.

Actual Qwen3-VL-2B Q4_K_M + Q8_0 projector / llama.cpp Metal, M4 16 GiB:

- Final frozen seed-619 development set: **28/28 image cases**, **36/36 required
  object-name checks**, **8/8 open/blocked doorway checks**, zero inference errors.
  p95 for evidence, bounded action and full-image object survey: **4.910 s**.
- Four camera conditions, seven views each. One virtual site with shared geometry
  and assets; a changed seed varies appearance, not site identity. This is not a
  held-out real-world test, and no deployment domain is qualified.
- Whole-image object surveys recognized bottles, table, monitor, keyboard, chair,
  cone, shelving and boxes. Selected captions were inspected against the images;
  comprehensive caption precision and instance localization remain unmeasured.
- **93 automated tests passed**. Existing accelerated navigation suite: **104/104
  returns**, zero clearance violations. The new baseline/blocked layouts both
  returned in accelerated route tests after the mapping fixes.
- Two actual Qwen patrols passed: baseline visited all six inspection points and
  returned in 118.4 s; the obstructed run returned in 119.7 s, detected the new
  obstruction and listed equipment/far-room/seating as unreachable. Both videos
  decoded at 1280×720 and were separately checked for playback and observation seek.
  Full results are recorded in `realism-validation.json`.

The first 28-image run found all labelled objects but called three clear openings
blocked. Wording-only revisions introduced false-clear errors (one in the second
28-image run, two in a 40-image regression run). A central crop lost doorway
context (35/40 correct, no false-clears). Those approaches were rejected; all
reports remain under `.local/validation/realism-*`. The final production path
retains the existing general center inspection and declares an explicit passage
inspection task at the passage checkpoint. It asks whether the doorway is blocked
and permits null/uncertain. No expected answer, object list, seed or geometry is
sent to the model. The full image remains the input for every vision call.

The first new-layout exploration also exposed an overly conservative occupancy
inflation rule that closed a return route. Inflation now measures distance from
the cell center to neighboring cell bounds using vehicle radius, margin and range
quantization. Adjacent unknown/occupied cells still block the planner; fresh-range
swept-disc supervision remains active. A first live run reached all six points but could not return because occupied
cells remained permanent. Bounded per-beam hit/free evidence now lets subsequent
free readings correct isolated quantized hits; replanning inside the home cell
finishes the approach. A remaining coarse-grid disconnection in random room seed 7
is handled by reversing the recorded flight segments, with fresh swept-disc
checks on every step and an immediate stop if that path is blocked. The recovery
is tested without granting motion through unknown geometry or bypassing sensors.

The original failure is retained in
`realism-geometry-v1.json`, with passing results in `realism-geometry-v2.json`.

Evidence: `realism-validation.json`, `realism-tests.txt`; complete images, frozen
inputs/model/pipeline and outputs: `.local/validation/realism-qwen-final/report.html`.
The final renderer uses `scripts/render-realism-cases.cjs`; inference uses
`scripts/evaluate_reliability.py`; live patrols use `scripts/check-patrol.cjs`.

Limits: fixed 1.4 m kinematic flight, ideal pose/ranges, procedural object meshes,
no calibrated sensor, no real-world transfer claim, no PX4 indoor dynamics test,
no physical drone. Prior real-photo bottle omissions remain unresolved evidence;
recognition of these simulated bottles does not close that gap.

# Real-environment reliability baseline — 20 October 2026

The requested domains are workshops, warehouses, building perimeters, flat fields
and hillsides. **None is qualified.** The new offline evaluator freezes inputs,
model and pipeline, tracks held-out site exposure, groups frames by encounter and
keeps all failures. Numeric targets and collection steps are in
[reliability-protocol.md](reliability-protocol.md). This is evaluation tooling and
a real-image diagnostic baseline, not completed flight acceptance.

- Six real RGB preview frames from the official TUM RGB-D benchmark were inspected
  and annotated before inference. Attribution and source hashes are retained.
  Reference labels are agent-authored salient-object names, not independent human
  ground truth. The images are development proxies; model pretraining exposure is
  unknown. No prompt was changed during or after this evaluation.
- **11/12 labelled object names found; 5/6 images passed both name checks.** The
  household/office image omitted bottles. The failure is preserved. The final
  grouped replay reproduced it: inspections took approximately 3–4 seconds, with
  p95 3.631 seconds. A repeated run does not increase the six-image sample size.
- Initial metadata used acquisition-series IDs as sites. Those are not verified
  independent physical sites. The preserved final replay conservatively groups
  all six images as one unverified location and is excluded from qualification.
- **No center/clearance labels were graded.** False-clear accuracy is unmeasured,
  not zero. Full-caption precision, target-camera performance, mission coverage
  and flight/recovery behavior also remain unmeasured by this suite.
- **86 automated tests passed in 16.424 seconds**, including twelve new checks for
  data leakage, duplicate/mutated inputs, encounter denominators, missing results,
  uncertainty behavior, report escaping and exclusion of proxy/agent-labelled data.
  The first sandboxed attempt could not bind local HTTP test sockets; the complete
  run with localhost access passed. Both logs remain in `.local/validation`.
- PNG/JPEG import exercised with six real frames. WebM import exercised at 55 s
  in the existing workshop patrol, yielding a visually verified 960 × 540 JPEG.
  Initial missing WebM duration metadata exposed an importer defect; bounded end
  decoding fixed it. No model or mission accuracy is attributed to this import test.
- Reports retain image/model/source hashes, copied input images, JSON outputs,
  errors and missing-domain evidence. Existing output directories are never reused.
  `caption_precision` remains null; a matching object name cannot establish it.

Compact evidence: `reliability-validation.json`, `reliability-tests.txt`.
Complete diagnostic report: `.local/validation/reliability-real-grouped-v1/report.html`.
A clearer presentation is saved alongside it as `review.html`, with separate
renderer provenance; frozen observations and scores remain unchanged. Both report
views rendered six images and five domain rows without browser exceptions.
First attempt: `.local/validation/reliability-real-v1/report.json`.
Models, raw camera images and full reports remain local and outside source exports.
The existing simulator, patrol controls and perception prompts were not changed.

---

# Detailed workshop acceptance — 20 October 2026

Apple M4, 16 GiB, macOS 15.6. Real local Qwen/Metal inference; Three.js rendering
and kinematic navigation. Physical transport disabled. See `workshop-validation.json`
for model outputs, image hashes, camera profiles and episode records, and
`workshop-tests.txt` for the automated test log.

- Added a compound-object workshop: stocked shelving, labeled cartons, workbench,
  monitor/keyboard/toolbox/vise/cable, palletized drums, hand truck, drawer cabinet,
  plant and fire extinguisher. No runtime asset downloads. The simple scenes remain
  available with their original camera profile.
- Workshop camera: **1280 × 720 video**, requested 15 fps / 2.5 Mbit/s;
  **960 × 540 model snapshots**, JPEG quality .85. The 41° vertical FOV approximates
  the standard Camera Module 3 candidate ([manufacturer specifications](https://www.raspberrypi.com/documentation/accessories/camera.html)).
  This is ideal rendering, not a calibrated lens, sensor noise, autofocus, motion
  blur, physical encoder/link or photorealistic-camera benchmark.
- A separate `object-survey-v1` image call adds a scene summary, up to four object
  descriptions and uncertainty to every workshop report. Scene identifiers,
  object catalogs and expected labels are not sent to Qwen. Each call retains a
  six-second limit; the complete detailed inspection has an 18-second deadline.
- **74 automated tests passed** in 16.337 seconds, including cancellation during
  the object-survey call, bounded output, safe HTML and camera-compatible baselines.
- **32/32 center-appearance cases passed**, zero false-clear classifications in
  this set: the prior 30 cases plus the detailed clear/blocked doorway pair.
  Lean/native cameras use `center-evidence-v2`; the detailed camera uses
  `center-objects-v1`. The camera profile selects the instruction before inference;
  expected answers do not participate in selection.
- **7/7 detailed-view checks passed**: five object-name checks and two doorway
  classifications. These checks do not grade every sentence or attribute. For
  example, an extinguisher caption incorrectly described the floor as wooden.
  This is useful but imperfect visual reporting; inspect the saved images.
- **Two complete browser acceptance runs passed**. Baseline
  `e8924a1ca5ed49a1b2c38845f8240f1d` inspected all four points and returned complete.
  Obstructed run `2045391767fe44dda73f181a8b960e80` detected the new box stack,
  listed `far-room` as unreached and returned partial. Both videos decoded at
  1280 × 720, all evidence images decoded at 960 × 540, and the reports contained
  object descriptions and working image/video references. Zero browser exceptions.
  Actual full inspections took **4.56–5.13 seconds** across seven stops; sustained
  latency, physical memory and 8 GiB operation remain unverified.
- Two accelerated workshop geometry runs returned without clearance violations.
  The sensor/collision model uses conservative boxes around compound props; gaps
  inside racks and under benches are not navigable. This is not flight dynamics.
- Python compilation, JavaScript syntax and diff whitespace checks passed.

The initial narrow view mislabeled the distant wall as a passage blockage. Moving
its inspection point back by one metre exposed the doorway context. A subsequent
case described the box stack but called it open because background was visible
around it. Broad prompt replacements then regressed older low-resolution cases.
The final camera profiles retain their independently tested instructions. Initial
failures, aborted patrol evidence and prompt probes remain under `.local/validation`.
The historical native Qwen flight below used the unchanged lean/native instruction;
PX4/Gazebo dynamics were not rerun for this workshop rendering change.

Reproduce with the recon app and local Qwen ready, and no active mission:

```bash
node scripts/render-detail-cases.cjs
.venv/bin/python -m scripts.evaluate_detail
.venv/bin/python -m scripts.evaluate_perception --order-seed 901
DRONE137_TEST_POLICY=qwen DRONE137_TEST_SCENARIO=workshop node scripts/check-patrol.cjs
./scripts/test-portable.sh
```

The detail renderer preserves uniquely named image sets. Its evaluator uses the
newest completed set, or an explicit `--manifest`. The center evaluation also needs
the earlier lean render set (`node scripts/render-vision-cases.cjs` on a new checkout).
Small image regressions and validation records are included in the source export;
full videos, model weights and native builds remain local.

---

# Latest model acceptance — 20 October 2026

Host: Apple M4, 16 GiB, macOS 15.6, Python 3.12.13. Actual local
Qwen3-VL-2B Q4_K_M / Q8 projector inference ran through the pinned llama.cpp Metal
build. Physical transport remained disabled. Compact results, labels and image
hashes are in `perception-validation.json`; test output is `perception-tests.txt`.
The earlier failed runs below are retained as historical evidence.

## Changes that resolved the observed failures

The original combined description/action prompt mislabeled a closed gate and
missed a new passage obstruction. Testing image/text order and prompt caching
alone did not correct those errors. `app/perception.py` now separates image
evidence/classification from the bounded, text-only action request. The model
receives image bytes and generic instructions, never expected labels, scene names,
variant names or geometry. The range supervisor still owns clearance and motion.

The first native-camera flight exposed a further false obstruction: an open gate's
panel beside its frame was treated as blocking the center. `center-evidence-v2`
explicitly assesses the central third. Both native images are now retained as
regressions alongside the original gate and passage cases. Camera-pose alignment
is required for change comparisons. A class change produces a report finding;
matching classes do not establish that the whole scene is unchanged. Partial or
invalid JSON, duplicate fields, unavailable actions and truncated model responses
are rejected. Operator cancellation also interrupts the second model request.

A separate restart defect was corrected: the local-port availability probe now
allows recently closed connections in TIME_WAIT while still rejecting a live
listener. This permits immediate model handoff between browser and native tests.

## Passing evidence

- **69 automated tests passed**, zero failures/skips, in 16.558 seconds. Coverage
  includes cancellation during the policy step, strict response validation,
  viewpoint matching, native classification scoring and model-port restart.
- **30/30 image cases passed in each of two shuffled orders**, zero blocked views
  classified as clear. These are the same 30 images repeated, not 60 independent
  scenes: 24 varied Three.js views and six retained regression images, including
  native Gazebo camera images. The production pipeline uses one image call and one
  text-policy call. These labels measure central appearance, not physical clearance.
- The GUI's paired vision test passed using the production perception code.
- **Actual Qwen + PX4/Gazebo flight passed**, episode
  `63d67435d42149f9be59f10f8fedcd34`: takeoff, native camera observations with
  `gate_a=open` and `gate_b=closed`, return and landing in about 45 seconds after
  mission start. Final telemetry was healthy and `in_air=false`. The first attempt,
  `e2509f7fb7a94c4191735e6fcaf1134b`, completed its route but mislabeled gate A;
  it remains a failed perception run. The permanent evaluator rejects that run
  and accepts the corrected one. A route's `autonomous_success` field alone does
  not grade its descriptions.
- Python compilation, JavaScript syntax and diff whitespace checks passed.

**Four final real-Qwen browser patrols passed** across two layouts. Every run
returned with a finalized, decodable video, evidence images and seek links, and
zero browser exceptions. Baselines classified the passage as open and completed
all points; changed runs classified it as solid, reported a new obstruction and
listed `far-room` as unreached. Both changed runs correctly returned partial.

| Environment | Variant | Result | Episode |
| --- | --- | --- | --- |
| rooms / 9107 | baseline | complete | `68139c3132bb4646b8c5b5c2ffdaf439` |
| rooms / 9107 | changed | partial | `c553beeb1ed8460c8d78b6c18216d462` |
| warehouse / 137 | baseline | complete | `ecd9663bfd194191b370b7e26c54fb27` |
| warehouse / 137 | changed | partial | `3b263acec4e34dd18c685739686c17a7` |

## Reproduce

With the recon app and its local model running, and no active mission:

```bash
node scripts/render-vision-cases.cjs
.venv/bin/python -m scripts.evaluate_perception --order-seed 137
.venv/bin/python -m scripts.evaluate_perception --order-seed 901
DRONE137_TEST_POLICY=qwen DRONE137_TEST_SCENARIO=rooms DRONE137_TEST_SEED=9107 node scripts/check-patrol.cjs
DRONE137_TEST_POLICY=qwen DRONE137_TEST_SCENARIO=warehouse DRONE137_TEST_SEED=137 node scripts/check-patrol.cjs
./scripts/test-portable.sh
```

Native setup is in `handoff.md`. Stop the recon app/model before starting the
native app with `--mode sim --policy qwen`. In another terminal run:

```bash
./scripts/evaluate.sh --mode sim --episodes 1 --score-default-gates
```

The scorer's gate labels apply only to the default courtyard. Use `--port 8138`
if the native app was explicitly started on that port. Browser tests preserve
unique output names and retain videos, images and raw model text under `.local`.
The source export includes code, small regression images and validation summaries;
large media, installed model weights and native builds remain local.

## Remaining boundary

This is a working bounded virtual inspection workflow. It extracts words from
selected video frames, not continuous video understanding. Indoor patrol still
uses fixed-altitude kinematics with ideal pose/ranges; the successful native gate
flight uses a separate global-waypoint executor. General object recognition,
noncentral or moving obstructions, localization drift, noisy sensors, full 3D
indoor dynamics, failure recovery under dynamics, sustained offline/memory runs
and physical-aircraft testing remain open. The existing 104-case geometry result
is separate from perception and aircraft dynamics. No real-drone acceptance or
actual 8 GiB capability is claimed.

---

# Earlier Mac implementation validation — 20 October 2026

Current host: Apple M4, 16 GiB, macOS 15.6, arm64, Python 3.12.13.
These are local development results; physical transport is disabled. A compact
machine-readable record is in `mac-validation.json`; local raw logs/media are
under `.local/validation`, `.local/browser-test` and `.local/data/runs`.

## Working virtual product

- Three.js random rooms, warehouse aisles and connected rooms, with repeatable
  baseline/obstructed-passage scenes and operator-authored inspection points.
- Real local Qwen patrols, model-requested extra views, observed-map return routing,
  and partial reports for unreachable points. The controller owns collision
  supervision; the model requests bounded inspection actions.
- Saved mission history and HTML reports: playable onboard video, selected images,
  approximate video seek links, model text, previous-image references, observed map,
  route and unreached checkpoints. Video is not fed continuously into the model:
  the model receives selected fresh JPEGs captured at inspection stops.
- Official Qwen weights/projector were downloaded and verified at immutable revision
  `52d6c8ffea26cc873ac5ad116f8631268d7eb503`. The repository has no LICENSE file;
  the pinned model card's Apache-2.0 declaration and saved licence checksum are
  recorded by the installer. Native llama.cpp built with Metal and ran locally.

## Checks and explicit failures

- **59 automated tests passed**, zero failures/skips, in 16.369 seconds. Full output
  is `mac-portable-tests.txt`. Syntax/compilation, dependency consistency and diff
  whitespace checks also passed.
- **104 accelerated geometry cases returned**, zero clearance violations/failures:
  100 seeded rooms plus baseline/changed warehouse and connected-room layouts.
  This suite does not run vision, rendered cameras or aircraft dynamics. An earlier
  run returned 96/104 with eight failures. Requiring observed clearance around
  route cells, checking side ranges on turns and revalidating routes fixed those
  cases. Original failures remain in `.local/validation/recon-geometry.json`.
- Actual-Qwen warehouse baseline `11b53f34c6fd4314b7a6ef28d91e4eed` completed all
  three viewpoints and returned. Changed run `605cede6e9eb41748d9c7fde5b4e7e06`
  returned partial with `far-room` unreached. Both produced decodable video and
  complete report evidence. Integration success does not grade perception.
- Final rendered regression after navigation fixes also passed: baseline
  `0c1e9aa73dc6479c814860e6bf5d9a27` and obstructed passage
  `8e876049042946428ee80444a4f9d7ea`. Both recordings decoded in Chrome,
  image/seek links existed and there were zero browser exceptions. The full
  observations are retained in `mac-validation.json`.
- **Perception acceptance failed.** The simple closed-gate image was classified as
  open. The changed-passage comparison said no clear change despite a visible
  blocker. A single-image diagnostic described the blocker but still returned an
  uncertain classification. Repeating the paired-image check reproduced the
  closed-gate error. Model outputs/images and latency remain in the local evidence.
  No failed check was converted to a pass or scripted fallback.
- An initial patrol allowed the model's `finish` action at one empty wall and
  returned too early. Patrol-specific action validation now rejects that action;
  exploration retains it. The failed run is preserved.
- PX4 SITL and the native image bridge compiled using the pinned source and Gazebo
  Harmonic 8.10.0 environment. A **scripted native gate mission**
  `4ec072dfc7ec4bd3bef3100061968620` completed takeoff, camera observations, route,
  return and landing in about 61 seconds, finishing `in_air=false` with healthy
  telemetry. It records `real_inference=false`, `real_camera=true`,
  `real_flight_dynamics=true`, `autonomous_success=false`. It is a legacy global
  waypoint test, not indoor recon or model-controlled flight acceptance.
- The final native startup check received a fresh 320 × 240 JPEG before offering
  a mission, then shut down its owned simulator processes.
- Native issues corrected during testing: generated world discovery, PX4 console
  EOF/log flooding (daemon mode), missing MAVSDK `set_maximum_speed` API (replaced
  with supported `set_current_speed`), and mismatched Gazebo/bridge interfaces.
  The overflowing log was explicitly archived. Gazebo prints Ogre/plugin/material
  warnings, but actual camera frames reached the app and the scripted route passed.
- A short 12-sample resource snapshot while Qwen, Chrome patrol and idle PX4/Gazebo
  ran had peak summed process RSS around **2.80 GiB**. RSS is not physical footprint.
  System swap usage increased from about 1,822 to 2,031 MiB; attribution is unknown.
  This does not establish a sustained budget or actual 8 GiB operation.

## Gates still open before a real drone

1. Held-out perception/change tests with measured false-clear and missed-obstruction
   rates; improve current failures rather than relying on unverified descriptions.
2. Indoor PX4 local-position/range/velocity integration using the extracted planner,
   explicit coordinate/yaw transforms and autopilot failsafes. Current recon remains
   fixed-altitude kinematics with ideal pose/ranges and no dynamic obstacles.
3. Noise, delay, localization uncertainty, camera loss, model timeout, link loss,
   operator takeover, return/landing and camera-visible coverage in flight dynamics.
4. Repeated offline missions and sustained combined physical-memory/swap evidence.
   Safari/MP4, other Macs and actual 8 GiB hosts remain unverified.
5. Aircraft/sensor suitability and a controlled physical test procedure. No physical
   drone was connected, armed, commissioned or validated.

Reproduce with `./scripts/test-portable.sh`,
`.venv/bin/python -m scripts.evaluate_recon --episodes 100`, and, with the app/model
running, `DRONE137_TEST_POLICY=qwen node scripts/check-patrol.cjs`.
See `handoff.md` for native setup. The prior cloud network block below is historical;
Mac model downloads succeeded. Bulk run media/builds are excluded from source export.

---

# Historical Linux validation — 20 October 2026

Host: `25eaecfa9f86`, Linux 6.18.55 / x86_64, Python 3.12.14.
Browser: Chromium 154.0.8037.57, headless software WebGL; Playwright 1.58.2.
Actual model inference: **no**. Rendered Three.js camera: **yes**.
Realistic flight dynamics / native Mac / physical transport: **not validated**.

## Current recon lab evidence

- **52 automated tests passed**, zero failures/skips, in 31.438 seconds.
  Full output: `portable-tests.txt`. New coverage includes official-metadata
  contract/resumable HTTP downloads, range mismatch, corrupt hashes, insufficient
  disk, installation locking, stale sensors, browser loss, stale camera tickets,
  independent inference cancellation, observed-map-only planning, four seeded
  controller runs, forward-obstacle stops and video ordering/finalization.
- A real local HTTP exchange with a **stub vision server** sent image data and
  exercised `look_left` followed by `finish`. This verifies the image/action
  integration and bounded turn behavior, not Qwen recognition.
- Complete **scripted browser mission**, seed 137: 12 observations, **36.30 m**
  travelled, return home, **0.704 m** minimum simulator clearance, zero obstacle
  stop interventions, **84.375% map observed**. This percentage is simulated range
  coverage, not camera-view coverage or object-detection accuracy.
- **90 ordered video chunks**, finalized to WebM. Chromium successfully decoded
  the recorded file as **320 × 240**. Selected images and a JSON report persisted.
- A subsequent mission in seed 42, in the same browser session, stopped on injected
  stale range sensors with speed zero and a finalized recording. There were **zero
  JavaScript exceptions** in the passing browser test.
- The GUI's actual model download displayed the cloud proxy's **HTTP 403** failure;
  the model did not become ready and no scripted fallback was started.
- Browser results: `recon-browser-results.json`. GUI capture: `recon-ui.png`.
  Full run artifacts remain in `.local/data/runs/4df9f614a8ec45af93bd73d0e8873940`
  and sensor-failure episode `354e8de92fbc4290ba277bde2a6649d2`; bulk artifacts are
  excluded from the source archive.
- Python compilation, JavaScript syntax, shell syntax and Python dependency
  consistency checks passed. Vendored Three.js 0.180.0 was extracted only after
  verifying the npm tarball's SHA512 integrity.
- Orderly shutdown via the independent parent launcher's control socket succeeded.

During development, an early repeat-browser run lost its camera connection and
another hit the app heartbeat deadline under software rendering. The UI now
rejects stale poll responses across mission starts and limits rendering to 20 fps;
the complete repeated-session browser check passed after these changes. A legacy
happy-route test also exposed an overly tight 250 ms timing assumption; its
success-path budget was increased while dedicated deadline/failure tests retain
their short timeouts. Failures were not counted as successful missions.

## Earlier baseline retained

The original 35-test gate-fixture suite passed before recon work. Two HTTP-driven
fixture inspections completed in 28.23 seconds, with synthetic JPEGs, scripted
policies and kinematic FakeDrone movement (`fixture-smoke.json`). Optional MAVSDK
3.17.4 was installed to inspect/test its external-server API using stubs; no
native flight connection was exercised. Native camera byte-stream and SDF/model
preparation checks remain contract tests, not Gazebo rendering evidence.

## Unverified / blocked

- Hugging Face official metadata and weights: cloud proxy HTTP 403. Download logic
  is tested against a local server; real artifact retrieval, Qwen outputs and its
  paired-image check still need execution on an allowed network.
- Actual Mac/Metal, llama.cpp native compilation, Safari/MP4, local model latency,
  combined memory/swap and actual 8 GiB performance.
- Gazebo/PX4 native simulation, bridge compilation, realistic aircraft dynamics,
  local positioning, noisy/delayed sensors, full 3D navigation and dynamic obstacles.
- Camera-visible coverage, perception accuracy, exact camera/pose clock alignment,
  long-duration/offline operation and held-out model-driven mission acceptance.
- Physical flight, hardware suitability and recovery behavior. Virtual stop tests
  do not establish physical landing or autopilot recovery.

`docs/versions.json` contains candidate native commits, not Mac-validated release
pins. Cloud configuration is saved as a draft; publication and fresh-task
restoration are separate, unverified actions. Git publication does not change
the runtime validation results recorded here.

Reproduce automated checks with `./scripts/test-portable.sh`; browser checks and
Mac acceptance are documented in `README.md` and `handoff.md`.

## Clean source-package check

The source archive was extracted into a separate temporary directory and all
90 source hashes verified. A fresh virtual environment installed the locked
minimal dependencies; **all 52 tests passed again in 28.644 seconds**, with zero
failures/skips (`clean-copy-tests.txt`). The clean copy started recon mode through
the parent launcher, served the GUI and both offline Three.js modules, reported
an explicitly unavailable local model, and shut down with its control socket
removed. Documentation-only evidence additions followed this executable-source
check. The final export was generated twice with an identical SHA256; the exact
hash is in `dist/drone137-source.tar.gz.sha256`.

The updated cloud draft includes the official model metadata/storage domains
`huggingface.co`, `*.huggingface.co`, and `*.hf.co`. This preserves the package
manager preset. Saving did not change this running environment's network policy;
review/save and publish are still required before a new environment can use it.
