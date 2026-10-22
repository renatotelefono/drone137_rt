# Local Qwen + Laya object-localization experiment

The experiment asks the existing Qwen3-VL-2B vision model to find a **red fire
extinguisher with a black hose and operating handle** in the authored Three.js
workshop. A second camera viewpoint must support a geometric position before
the executor accepts a location. Red toolboxes/cabinets, shelves, small objects,
occlusion, low light, blur and a target-absent room provide distractors.

This is an active visual-search experiment at predefined, clearance-checked
camera stations. It does **not** simulate transit between stations, flight
dynamics, SLAM, real camera calibration, battery use or concurrent aircraft.
Positions are 2D room coordinates in metres. Physical transport remains disabled.

## Comparison

- **Qwen:** Qwen image inference, followed by Qwen selecting a bounded action.
- **Qwen + Laya:** the same Qwen image inference, followed by Laya selecting that
  action. One shared Laya instance, one checkpoint, FP16, batch size one.
- Both arms receive the same task, state format and action descriptions. Shared
  views use byte-identical JPEGs, but vision inference runs separately for both.
- Models see pixels and text evidence. Scene geometry and expected object
  coordinates stay in the renderer/evaluator and never enter an inference prompt.
- The common executor limits actions to scan, confirm, found or unresolved.
  It rejects unknown actions and disallows found without two usable image rays.
  Two rays verify geometry; they do not independently prove object identity.
- Bearing triangulation uses Qwen's image boxes, ideal camera poses and a known
  pinhole projection. Duplicate poses, inadequate parallax, backward intersections
  and intersections outside the room are rejected. Scoring tolerance is 0.75 m.
- An exhausted absent-target search is scored as an honest unresolved outcome,
  **not** proof of absence. A location claim in an absent-target room is a failure.

One development scene was used to correct the action contract. Five further
fixed cases compare both arms. This small authored test suite is not a measured
generalization rate. Retain unsuccessful and interrupted runs alongside the final
report; do not select only successful images.

## Measured result, 21 October 2026

The cache-bounded paired run completed 72 real vision observations across ten
searches (five cases per arm). Both arms localized all four present targets,
with errors of 0.004, 0.122, 0.044 and 0.045 m under ideal pose/intrinsics. Both
also falsely localized a **red toolbox** as the extinguisher in the absent-target
room: **4/5 correct outcomes for each arm**, with no accuracy gain from Laya.

| Measurement | Qwen | Qwen + Laya |
| --- | ---: | ---: |
| Mean decision latency | 318 ms | 59 ms |
| Total time for five searches | 95.5 s | 87.7 s |
| Sampled application peak | 1.89 GiB | 3.00 GiB |
| False location claims | 1 | 1 |

Decision latency improved about 5.4x; total search time improved about 8.2%.
Vision remains the dominant cost. Host swap did not grow during either measured
arm, but existing host swap and a 16 GiB machine prevent an 8 GiB qualification.
Qwen startup is outside the measurement window; Laya loading is included.

The original cache-enabled run was retained: Qwen reached 4.46 GiB combined
application footprint, and loading Laya tripped the guard at 5.29 GiB. Disabling
the server prompt cache allowed the same paired test to complete below budget.

A post-evaluation check reversed choice ordering and added explicit JSON answer
instructions. Reordering alone did not repair either supervisor's main errors.
One Qwen probe changed with both formatting and ordering, demonstrating prompt
sensitivity. These diagnostic probes are not counted as additional mission
successes. The next reliability change needs to separate **object identity**
from **geometric consistency**: two boxes can triangulate a wrong object.

Compact measurements: [localization-validation.json](localization-validation.json).
The full local evidence is under
`.local/validation/localization-evaluation-cache-bounded/`.

## Memory constraint

The available host is an M4 Mac with **16 GiB**, not an 8 GiB test machine.
`scripts/memory_watch.py` samples process physical footprints every 200 ms for
Qwen, the simulator server, evaluator/Laya, Node and the browser camera including
its GPU/helper processes. The evaluator stops further work if the sampled sum
exceeds **5 GiB**, leaving an intended OS reserve on an 8 GiB computer.

This is a sampled, cooperative guard, not an OS-enforced memory sandbox. It
excludes unrelated applications/user browser tabs and does not emulate an 8 GiB
host. Short peaks can be missed. Host swap is recorded but is not attributable
solely to the experiment. A complete 8 GiB device test remains required.

The initial longer run hit the guard when Laya loaded: Qwen's server had grown
with repeated inspections. The pinned llama.cpp version defaults to an 8 GiB
server prompt cache. `ModelManager.start` now passes `--cache-ram 0` and
`--no-cache-prompt` for stateless camera inspections. Model weights, image size,
context length, prompts and output budget are unchanged by this memory fix.

## Local runtime and reproduction

Use the existing app with Qwen started and all missions finished. The experiment
uses its loopback model server and local browser assets. The extra dependencies
are isolated from the application's existing `.venv`:

```bash
.venv/bin/python -m venv .local/laya-env
.local/laya-env/bin/python -m pip install -r requirements-localization.txt
.local/laya-env/bin/python -m scripts.download_laya
.local/laya-env/bin/python -m scripts.evaluate_localization \
  --split development --output .local/validation/localization-development-new
.local/laya-env/bin/python -m scripts.evaluate_localization \
  --split evaluation --output .local/validation/localization-evaluation-new
```

Output directories must be new. A process lock prevents two benchmark runs from
overlapping. Allow the process to exit before starting another. Do not launch a
dashboard mission during the experiment. After an interrupted inference, restart
the owned Qwen server before another run, as required by the normal backend.

The camera runner uses the existing Playwright install under
`.local/browser-test/node_modules` and Google Chrome. `CHROMIUM_PATH` can select
another locally installed compatible Chromium. Rendering uses the production
camera/scene code; no synthetic captions or mocked model responses are used.

The Laya checkpoint is the community MLX FP16 conversion
`aac6fef/laya-mlx@20aed815fc6acde75733882e7ec0e3f28aeb9717`, converted from
`convaiinnovations/laya@c5d78730f3493e4fe16d61507ef4b78eef7318cf`.
The runtime is `laya-mlx==0.5.0`; downloads are hash-checked against the pinned
manifest, and inference uses local files only. It does not use Jev's hosted API.
The confidence values are **not calibrated on these drone tasks**. The runtime
also warns about an upstream temperature bucket for 11+ options; this experiment
uses fewer options and never treats a confidence score as proof of correctness.

Each output contains `results.json`, evaluator-only `scenarios.json`, actual input
JPEGs, predicted boxes, camera poses, timings, memory samples, package versions,
model provenance and source hashes. `report.html` shows the observations and
post-run localization map. Coral crosses are scoring truth revealed only in the
report; amber circles/boxes are estimates. No flight path is implied by the
sequence of camera stations.

Sources: [Laya](https://huggingface.co/convaiinnovations/laya),
[MLX conversion](https://huggingface.co/aac6fef/laya-mlx),
[MLX runtime](https://github.com/mizorewww/laya-mlx).
