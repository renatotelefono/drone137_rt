# Live flight vision comparison

The comparison flies the simulated quadcopter through the task. It does not
score a replay of previously selected images. PX4 controls the Gazebo aircraft;
Three.js renders its measured body pose and camera mount. Qwen proposes objects,
checks visible parts and supervises search. In the paired configurations,
Florence-2 or SmolVLM2 independently captions the live candidate crop.

## Fixed conditions

- SQLite aircraft: `reference-quad@1`, a provisional quad-X profile.
- Navigation: observed range map and noisy synthetic odometry, GPS disabled.
- Scene: Poly Haven workshop assets, glare and occlusion conditions, each with
  a target-present and target-absent case.
- Success: all four missions correct, flight checks and landing passed, no
  vehicle-envelope violations, each mission within 300 seconds, no experiment
  errors and the full application within the 5 GiB memory guard.
- Identity: two geometrically valid views must each pass Qwen's visible-parts
  check and, when enabled, the companion's explicit object identification.
- Localization tolerance: 0.75 m. Scene truth is used only for evaluation.

These are four known development cases in one synthetic building, not the full
eight-case realism suite or a held-out real-world test. Flights share conditions
and policy; aircraft motion and model timing produce different camera pixels.
The computer has 16 GiB. A measured application budget is useful preparation for
an 8 GB computer, but does not validate that hardware's memory pressure or speed.

## Aircraft preflight

Evidence: `.local/validation/rotor-flight-check-v2/results.json`.

All physical checks passed: four connected rotor joints, measured rotation in
the specified directions, lift-off above one metre, stable hover and landing.
The 25 inspection samples gave 0.0266 m hover tracking RMSE and a maximum hover
tilt of 1.37 degrees. Equivalent measured motor speeds were approximately
767–773 rad/s. The aircraft travelled 17.1 m with no envelope violations.

This checks the simulated motor and rigid-body assembly. It does not establish
agreement with a measured real drone, propeller flex or propwash.

## Original live comparison

Evidence: `.local/validation/vision-flight-comparison-v1/`.

| Configuration | Tasks correct | Positive targets | Absent controls | False location claims | Mean vision + decision | Peak application |
|---|---:|---:|---:|---:|---:|---:|
| Qwen 2B alone | 2/4 | 1/2 | 1/2 | 1 | 3.17 s | 3.41 GiB |
| Qwen + Florence-2-base-ft | 3/4 | 1/2 | 2/2 | 0 | 3.84 s | 4.47 GiB |
| Qwen + SmolVLM2, optimized attention | 2/4 | 0/2 | 2/2 | 0 | 3.58 s | 4.90 GiB |
| Qwen + SmolVLM2, original eager attention | 0/4; 1 attempted | 0/2 | 0/2 | 0 before interruption | 4.85 s | 5.03 GiB |

Qwen, Florence and the optimized SmolVLM2 each completed all four flights and
passed their physical checks. None passed the whole task gate. SmolVLM2's original runtime exceeded
the 5 GiB guard during the first mission; cleanup confirmed landing. Its other
three cases were not executed. That row is a resource failure, not an estimate
of accuracy on the unexecuted cases.

The viewpoint correction prevents a third observation from returning too close
to the retained first observation. Qwen then localized the occluded target to
0.118 m. Qwen still made one false claim in the matching target-absent case.
Florence rejected the decoys and localized the glare target to 0.055 m, but
called the small occluded target a bottle. The search moved on when both
combined identity checks were unsupported, without acquiring a closer view.

SmolVLM2's follow-up uses optimized attention with the same weights, prompts,
single image tile, aircraft, scenes and gates. It completed all four missions
without a memory error; evidence is in
`.local/validation/smol-sdpa-flights-v1/`. Both actual targets were missed. The
companion correctly identified the glare target, but Qwen's second parts check
rejected the handle and the available extra viewpoint failed clearance/parallax
selection. On the occluded target, the combined unsupported checks again caused
the controller to move on without a closer observation.

## Bounded active inspection follow-up

`--inspection-policy active-v2` is a separate policy experiment, not a change to
the recognition acceptance criteria. It allows up to three extra views when
the triangulated candidate crop is small or clipped, or when the required checks
disagree. Acquiring evidence does not require an initial identity confirmation.
The latest revision samples viewing stations around the estimated candidate,
within 3.5 m of the current position. A station must be reachable through the
connected component of inflated observed-free cells and have no known blocker
before the candidate along its viewing direction. Unknown sightline cells remain
uncertain; no vehicle route is authorized through unknown cells. Each planning
map is saved and hashed. Execution retains the existing range-based navigation,
motion guards and parallax requirements. No scene object manifest is supplied to
this planner. Vertical changes stay within 0.3 m, altitude within 0.9–1.8 m and
estimated camera standoff at least 1.4 m.

If no map-selected view passes the geometry checks, bounded local views remain
available: vertically clipped candidates get centring, while uncut candidates
get elevated lateral views. These fallback moves remain under 1 m horizontally.

Planning and subsequent localization use the same retained observation. Each
extra view has a unique ID. Two separately supported views are still required;
neither pixel-quality flags nor predicted geometry can authorize a found claim.
The original `parallax-v1` policy remains selectable and is the default.

The first four-case Florence follow-up is retained under
`.local/validation/florence-active-flights-v1/`: 3/4 task-correct, zero false
claims, all four physical flights passed, 4.50 GiB peak application memory.
Its glare target was recovered after closer views (0.174 m localization error),
but the initial trigger still required an identity hint before inspecting a tiny
candidate. That failed when both model readings were uncertain in the occluded
case. The corrected trigger was tested in a separate complete four-case run,
`.local/validation/florence-active-flights-v2/`: again 3/4, zero false claims,
all four physical flights passed, 4.55 GiB peak application memory. Its saved
frames exposed a different control error: centring the estimated visible
fragment lowered the camera from 1.50 to 1.20 to 0.90 m behind the foreground
box, hiding more of the target. That failure is preserved.

The elevated lateral-view correction was flown through the same complete set in
`.local/validation/florence-active-flights-v3/`: 3/4 again, zero false claims,
all physical flights passed, 4.55 GiB peak. Images show that local higher views
still left much of the extinguisher behind the box. The observed-map view
selector was tested separately in `.local/validation/florence-active-flights-v4/`:
3/4 again, zero false claims, all four physical flights passed, 4.53 GiB peak,
3.95 s mean vision-plus-decision latency and 254.6 s mean mission duration.
There were no runtime or source-integrity errors. The occluded target remained
unresolved, so the all-pass requirement was not met. None of these controller
revisions is promoted over the original default policy.

An offline geometric check of the saved observed map examined 4,097 reachable
camera positions within 5 m of both the candidate and the current aircraft.
Every line to the estimated candidate had a known occupied cell before the final
0.45 m candidate allowance. These are map queries, not additional flight or
recognition trials. The local fallback images continued to show only part of the
extinguisher behind the box. This identifies a remaining view-acquisition and
mapping limitation; swapping the image reviewer did not resolve it.

The next engineering experiment should address 3D occlusion and exploration to
new viewing regions, or explicitly test a different camera mounting/gimbal
profile. Those changes need new live positive and negative controls. Current
results do not justify a real-drone recognition reliability claim.

The first follow-up's successful glare mission took 295.1 seconds against a
300-second limit. That narrow margin is retained, not hidden by averaging.

## Reproduction and evidence

See the live comparison commands in `README.md`. Each invocation requires a new
output directory and records source hashes, checkpoint revisions, input image
hashes, prompts, SQLite profile snapshots, telemetry, videos, raw model replies,
latency and the application's process memory. Do not edit evaluated source files
while a run is active: source changes invalidate the experiment.

Software regression tests verify gates and geometry; they do not count as
recognition successes. Failed and unexecuted live missions remain visible.
The 39 relevant regression tests passed; see `docs/vision-flight-tests.txt`.
The combined review is served at
`http://127.0.0.1:8142/vision-flight-review-v2/report.html`.
