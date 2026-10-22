# Real-room qualification and the Glob3R boundary

The target is **every planned mission passing a frozen, difficult test**, with
zero false location claims. This is an acceptance criterion for a finite test;
it is not a claim of 100% accuracy in arbitrary real environments. Failures,
aborts, memory overruns, and unexecuted cases remain in the denominator. A
development retry cannot replace the original result.

## Observed results — October 21, 2026

A later [online asset variant](online-assets-experiment.md) scored **6/8** with
the same Qwen 2B + Laya policy, including two target-present successes and one
wrong-object claim. It uses metre-scale CC0 models and photographed lighting.
The original procedural results below are preserved for comparison.

Qwen 2B + Laya completed the first hard-suite attempt at **5/8 (62.5%)**:
one of four target-present missions succeeded; all four absent-target searches
finished without a location claim. There were two missed targets and one
wrong-object claim, 5.93 m from the actual target. All eight flights landed,
with zero conservative horizontal envelope violations and no runtime errors.
Peak guard memory was **3.48 GiB**, measured on the 16 GiB host. This does not
qualify real-world autonomy or establish behavior on 8 GiB hardware.

| Hard condition | Target present | Target absent |
| --- | --- | --- |
| Dim, rearranged west room | Missed | Completed without claim |
| Glare, rearranged east room | Missed | Completed without claim |
| Partial occlusion | Found, 0.055 m error | Completed without claim |
| Blur, 220 ms delay, stronger JPEG degradation | Wrong object, 5.93 m error | Completed without claim |

The preceding baseline attempt is retained separately: one correct mission,
one false location claim, one takeoff timeout and one unexecuted planned case.
It stopped before the readiness check changes below. The later hard-suite run
does not erase that failure. The eight-case acceptance target is **not met**.

The hard run used 52 full-frame observations and 42 candidate crops. All image
hashes, frozen source snapshots and protocol hashes passed an integrity audit.
Recorded hard-frame ages were 124–275 ms, including the configured delay and
sampling/render overhead. The main review decodes/indexes every retained video
and loads only one at a time:
[local review](http://127.0.0.1:8142/real-room-review/report.html).
Compact metrics are in `real-room-validation.json`; 127 regression tests passed
(`real-room-tests.txt`).

A subsequent development diagnostic compared the existing parts check with
reference-photo comparison on the **same 25 known, manually labeled crops**.
The parts check got 15/25 correct (4 false accepts, 6 false rejections).
Reference comparison got 13/25 and accepted all 12 negatives. It was **not
adopted**. Laya was resident for memory measurement but not invoked in this
vision-only comparison. These selected, correlated crops are not another
mission score or a held-out benchmark. Full results:
[reference diagnostic](http://127.0.0.1:8142/reference-diagnostic-v1/report.html).

The evidence points to a perception bottleneck: consistent language-model
hallucinations can pass repeated checks. A separate trained target verifier
needs real positive examples and lookalikes. View planning also needs to keep
the entire candidate in frame and inspect the missing mechanism from a useful
angle. The glare case triangulated near the target but could not see/support
its hose; simply getting closer sometimes clipped the lower object. Neither
extra reasoning nor a reference image solved these failures in the tests run.

## Implemented experiment

The default vision model remains the pinned Qwen3-VL 2B Q4 model. Laya is a
bounded text decision supervisor. PX4 closes the flight control loop. Laya does
not see the images and cannot independently correct a visual hallucination.
Only actions with more than one eligible choice invoke the supervisor; the
report records this count separately from deterministic actions.

`config/native-hard-v1.json` defines eight missions before inference: four new
furniture arrangements, each with a present target and a matched absent-target
case. The absent member substitutes a red canister. Added large canisters,
rotated targets, one partial occluder, dim/glare/blur conditions, oscillating
illumination, synthetic drafts, small camera-mount calibration errors,
120–220 ms image delay, deterministic dropped frames, and JPEG quality
0.64–0.72 make the observations less ideal. Delayed image packets retain the
estimated pose sampled with that packet; they are not paired with the latest
pose. Their actual age and dropped-frame count are recorded.

Furniture positions change in both the rendered scene and conservative Gazebo
collision boxes. The four search stations are identical across all eight
cases and do not depend on the target location. The route still uses a known
operator map. These are unfamiliar arrangements of one authored building
topology, **not independent real buildings or photorealistic reconstructions**.

Before inference, the evaluator saves the cases, prompts, source snapshot,
source hashes, protocol hash and pinned model identities. Source edits during
the experiment invalidate qualification. Positive cases require localization
within 0.75 m; every case requires landing, no horizontal envelope violation,
no runtime error, and completion within 300 s. Application memory must remain
below the sampled 5 GiB guard. An absent-case pass means the complete planned
search made no location claim. It does not prove the room was empty.

The baseline attempt exposed an estimator-height excursion while the vehicle
remained landed. Native takeoff now waits for five seconds of stable preflight
estimates and requires PX4's airborne flag as well as altitude before starting
offboard control. This prevents altitude alone from declaring takeoff complete;
it does not establish the root cause or elimination of all simulator faults.

```bash
.local/laya-env/bin/python -m scripts.evaluate_flight \
  --suite baseline --model-size 2b --arms qwen+laya \
  --output .local/validation/NEW-baseline-directory
.local/laya-env/bin/python -m scripts.evaluate_flight \
  --suite hard --model-size 2b --arms qwen+laya \
  --output .local/validation/NEW-hard-directory
```

The output directory must be new. Run serially: these trials share local model,
PX4 and camera ports. `--cases` selects a diagnostic subset; it cannot qualify
the full eight-case suite. Baseline cases are already used in development.
The hard suite is a first-use challenge, not a blinded or statistically
independent holdout. After its results are inspected, reserve different rooms
and cases for the next qualification attempt.

## What Glob3R can contribute

Inspected upstream revision:
`553096ef5a44d3c501fe70ae659e0eeb997f8e83`.

[Glob3R](https://github.com/aigc3d/Glob3R) reconstructs camera poses and scene
geometry from overlapping images. Its [tested installation](https://github.com/aigc3d/Glob3R/blob/553096ef5a44d3c501fe70ae659e0eeb997f8e83/docs/installation.md)
uses Ubuntu, NVIDIA H20, CUDA 12.8 and cuDSS. That is not a supported installation
on this Apple Metal host, and the documentation inspected does not establish an
8 GiB memory requirement. We did not install it, download its checkpoints, or
claim to have run it.

The pinned [reconstruction writer](https://github.com/aigc3d/Glob3R/blob/553096ef5a44d3c501fe70ae659e0eeb997f8e83/glob3r/optimization/reconstruction.py)
exports camera poses, intrinsics, radial distortion and sparse/dense PLY point
clouds. A point cloud is not automatically a complete textured collision mesh.
The upstream README also distinguishes the original BSD code from incorporated
components with other terms; review the relevant components before packaging
a commercial reconstruction tool.

Recommended separation:

1. Capture overlapping workshop/warehouse images or slow video, with the actual
   camera model, resolution, exposure settings and timestamps. Include scale
   references and measured room dimensions. Capture clutter, shiny surfaces,
   dark corners and target lookalikes, not just clean walls. Keep a separate
   set of camera viewpoints for checking the reconstruction.
2. Run pinned Glob3R **offline on a suitable CUDA machine**. Validate complete
   scene output and camera alignment. Preserve source image hashes and the
   reconstruction configuration. Align scale/up/floor to measured references;
   monocular reconstruction alone is not a measurement of absolute scale.
3. Build a render asset from the reconstruction: close verified structural
   gaps, produce a decimated textured GLB with baked lighting where appropriate,
   and create a separate simple collision mesh. Treat point-cloud holes as
   unknown space until measured. Do not let the flight route pass through a
   missing reconstructed wall. Capture the background without the search target
   as well: movable targets and distractors need separate assets, so relocating
   them does not leave a second copy baked into the static reconstruction.
4. Import the visual asset into Three.js and the aligned collision mesh into
   Gazebo. Check both against surveyed floor/wall distances and reserved camera
   images. Fix coordinate transforms once, without using target truth during
   the mission. This import is the next implementation step; it is not present
   in the current procedural renderer.
5. Keep only the optimized scene, Qwen 2B and Laya on the 8 GiB operating machine.
   Use one inference queue, one active render context, bounded image history,
   event-driven image checks and instanced assets. Start with a proposed
   250k-triangle/512 MiB GPU texture budget and measure it on the target machine;
   those are engineering budgets, not measured Glob3R output sizes.

No real-room photo/video path has been supplied in this session. Reconstruction
and real-image agreement remain untested; adding synthetic noise is not a
substitute for those measurements.

## Closing the remaining realism gaps

The current simulation uses a generic x500, upstream sensor noise, synthetic
GNSS indoors, known map navigation, approximate optics and conservative boxes.
Before a physical drone can validate the same mission, calibrate camera
intrinsics/extrinsics and timing; identify thrust, mass, drag and battery
response for that airframe; and implement indoor VIO/SLAM or the intended
position source with loss/recovery tests. More polygons will not close those
gaps. Add measured camera noise, motion blur and network latency distributions
only after capturing them from the chosen hardware.

For perception, the next improvement must address identity and coverage:
collect real positive examples and difficult lookalikes; train/evaluate a small
object verifier or detector; track candidates over time; request a closer or
opposite-side view when identity is uncertain; and score room coverage instead
of assuming four stations see every object. Laya can choose the next bounded
inspection action, but it must receive trustworthy observations.

Use separate development and qualification rooms. Freeze policy, model hashes,
thresholds, scene seeds and scoring before the qualification run. Score correct
positive localizations, false location claims, missed targets, explicit
abstentions, coverage, flight envelope, landing, time, memory and recovery
separately. Include absent targets and genuinely unobservable targets with an
explicit expected abstention; do not relabel ordinary misses as acceptable.

Once the finite challenge passes, repeat across independent real rooms and
hardware conditions. Even 300 successes out of 300 are only finite evidence:
under an independent identical-trial binomial model, the one-sided 95% upper
bound on failure probability is `1 - 0.05**(1/300)`, about 0.994%. Correlated
synthetic scenes do not satisfy that independence assumption. Universal 100%
accuracy cannot be established by this test.
