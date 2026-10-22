# Reliability qualification

The requested operating domains are **indoor workshops, warehouses, building
perimeters, flat fields and hillsides**. They qualify separately. All five are
currently **unqualified**. Public real-image tests have started; the indoor
controller still uses ideal kinematics and the outdoor domains have no flight
implementation. Successful rendering, model inference and route completion are
different measurements.

## What is now executable

`config/reliability.json` records domain conditions and proposed engineering
thresholds before testing. `scripts/evaluate_reliability.py` freezes and checks
image, model, prompt, scorer and configuration hashes, runs the production local
perception/action/survey functions, and saves every output and error. Reports
include the input images, reference annotations, source snapshots and missing
evidence for each domain. No labels, site names or expected objects enter Qwen's
prompts. No flight is started and no inference is sent to a hosted model.

The first six-image public-camera smoke test found **11/12 required object names,
5/6 images passing both name checks**. The model omitted bottles on a cluttered
table. This is a diagnostic result, not a general accuracy estimate. References
were visually annotated by Codex before Qwen ran, not by an independent human.
Full-caption precision, clearance, change detection and mission completion were
not graded. See `reliability-validation.json` for preserved evidence.

## Operating envelope and evidence

| Domain | Required perception conditions | Flight validation still required |
| --- | --- | --- |
| Workshop | Clutter, low light, glare, blur, occlusion, moving people | Local positioning without GPS, confined clearance, loss/recovery |
| Warehouse | Repetitive aisles, lighting variation, occlusion, moving traffic | Localization drift, traffic response, link loss and return routes |
| Perimeter | Backlight, shadows, reflective surfaces, thin obstacles | Wind around structures, degraded positioning, clearance |
| Flat field | Low texture, distant objects, moving vegetation, blur | Wind, communications, height above ground, return energy |
| Hillside | Slopes, hidden areas beyond crests, shadows, distant objects | Terrain following, crest clearance, wind, terrain-aware return |

Specify a camera/lens, encoding, speed/altitude envelope, lighting/weather range,
minimum reportable object size and mission objective for each domain. Those
values have not been selected yet. A hillside cannot inherit the flat-field
acceptance, and a simulated workshop cannot qualify a physical warehouse.

## Capture and label before changing the model

1. Start with handheld or fixed-camera recordings from the intended camera. No
   drone flight is needed to test perception. Keep source files, frame timestamps,
   camera identity/settings, site/session IDs, conditions and collection dates.
2. Separate development and held-out data by **physical site**, including all
   recordings and visits to that site. Adjacent frames and image variants stay in
   the same encounter. Do not treat different frames of one encounter as independent
   trials. Public data may already have been in model pretraining; never claim
   otherwise. Exact-hash detection cannot identify every near-duplicate.
3. Have a human annotate visible facts before inference: salient objects, the
   center's visual appearance where unambiguous, and cases that require abstention
   or another view. Record disagreements as uncertain. Label actual geometric
   clearance from independent sensing/measurement, never from an RGB caption.
4. Review every generated report for unsupported statements and omitted important
   information. Object-name recall does not measure false claims, material/color
   accuracy, completeness or useful coverage. The current scorer deliberately
   leaves `caption_precision` unmeasured.
5. Freeze the manifest and model/pipeline before opening a held-out set. Any used
   site becomes development evidence for subsequent model/prompt changes. Retain
   failed attempts. `--replay` explicitly excludes repeated runs from qualification.

The evaluator rejects duplicate IDs/images, changed hashes, missing labels and
sites assigned to both splits. A persistent local exposure ledger prevents a used
held-out site from silently being tested again as new evidence. This ledger is
local to the checkout/data directory; it is not an audit of other computers or
model pretraining. Share the ledger with the data custodian when moving machines.

## Proposed acceptance targets

These are starting engineering gates, **not a certification or physical-flight
permission**. Freeze changes to the targets before the next held-out evaluation.

- At least three independently collected target sites, with complete condition
  coverage (at least ten encounters per required condition).
- At least 300 obstructed encounters, 60 clear encounters and 60 genuinely
  ambiguous encounters. A series of adjacent video frames counts as one encounter.
- Zero false-clear visual classifications; the one-sided 95% upper bound must be
  below 1%. With zero failures in 300 independent representative encounters the
  exact bound is approximately 0.994%. With 32 it is approximately 8.94%.
  Independence and representativeness require review; site correlation can make
  these bounds optimistic. This measures visual classification, not flight safety.
- At least 95% center-class accuracy and appropriate relook/hold behavior on
  ambiguous encounters, plus at least 90% recall of labelled salient object names.
  Aggregate by encounter; report per-condition and per-site results for review.
- Complete inspection p95 below six seconds on the intended host, with all
  timeouts and missing observations retained as failures. This is a stopped
  inspection budget, not a collision-avoidance control frequency.
- Independent factual review of full captions, useful camera-visible mission
  coverage, and independent navigation/recovery evidence are still mandatory.

The current command cannot mark a domain real-world-qualified automatically,
even if numeric perception targets are met. A real-image replay cannot test
navigation, collision avoidance, return-home or recovery. The separate PX4 indoor
backend, outdoor terrain/navigation model and controlled physical validation
remain open work.

## Commands

The recon app and its local model must already be running, without an active
mission. Do not run another model client during evaluation. The evaluator refuses
active app missions and serializes other reliability evaluators; it cannot reserve
the server against arbitrary external clients or an operator starting a mission
mid-request. It checks app state before each case and retains interrupted runs.

Public sample reproduction (six small images, no model/data downloads beyond them):

```bash
.venv/bin/python -m scripts.fetch_real_samples --output .local/validation/tum-source-new
node scripts/prepare-reliability.cjs .local/validation/tum-source-new/collection.json .local/validation/tum-input-new
.venv/bin/python -m scripts.evaluate_reliability freeze \
  --manifest .local/validation/tum-input-new/manifest.json \
  --lock .local/validation/tum-input-new/frozen.json
.venv/bin/python -m scripts.evaluate_reliability run \
  --manifest .local/validation/tum-input-new/manifest.json \
  --lock .local/validation/tum-input-new/frozen.json \
  --output .local/validation/tum-result-new
```

Use a new output directory each time. A failing case exits nonzero **after saving
the full report**. Never delete failures to obtain a passing result. The initial
source checksums are pinned; an upstream change fails the fetch.

For your own data, copy `config/reliability-collection.example.json`, replace its
metadata and independently label the files, then use the same importer/freeze/run
commands. The importer accepts JPEG/PNG or short MP4/WebM clips under 64 MiB.
Video cases require `time_s`; sampled frames from the same encounter must retain
the same `encounter_id`. Images retain aspect ratio and are never upscaled; they
fit within 960 × 540, use JPEG quality .85 and retain the 200 kB model bound.
The importer requires the existing optional Playwright/Chrome developer setup.
The runtime gains no new dependency.

## Source and next evidence

The real smoke inputs are RGB preview images from the
[TUM RGB-D benchmark](https://cvg.cit.tum.de/data/datasets/rgbd-dataset),
[sequence index](https://webshare.cvg.cit.tum.de/g/rgbd/dataset/):
Sturm, Engelhard, Endres, Burgard and Cremers, *A Benchmark for the Evaluation of
RGB-D SLAM Systems*, IROS 2012. Data license: CC BY 4.0. Their acquisition-series
names do not establish independent deployment sites; all samples are conservatively
grouped under one unverified location. They have no outdoor or drone-camera claim.
Raw images/media stay under `.local` and are excluded from source exports.

Next inputs: intended camera model/settings and separate-site footage for the five
domains, beginning with workshop and warehouse. Next implementation: complete
indoor PX4 local-position/range control, then inject positioning/range/camera/link
failures and grade mission outcomes separately from model responses. Add 3D terrain
and wind before attempting field/hillside simulation acceptance.

### Declaring an inspection task

A manifest may set `inspection_task` to `center` (the default) or `passage`.
Choose it before freezing the dataset based on the operator's requested task,
without consulting the expected open/blocked answer or model result. `passage`
asks about a visible doorway; an unjudgeable view can return null/uncertain.
The simulator declares this task at its passage checkpoint. Both tasks receive
only the full camera JPEG and generic instructions, and object surveys always
use the full frame. Synthetic development iterations and repeated images never
establish held-out site reliability. Frozen fingerprints now also include the
minimal dependency lockfile.
