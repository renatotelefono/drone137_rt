# Hardware-independent realism workbench

The application now has a local aircraft library at `/airframes`, backed by
`.local/data/airframes.sqlite3`. It stores immutable revisions of quad-X aircraft,
camera, sensing and operating-limit parameters. Assignments point to exact
revisions. Saving new parameters never changes an already frozen mission.

The starter aircraft are **provisional reference, light and payload quadcopters**.
They are engineering hypotheses, not specifications for commercial products.
No physical drone/camera or room capture was supplied for this implementation.
Hardware calibration and real-world qualification remain pending actual evidence.

The subsequent [live vision comparison](vision-flight-comparison.md) adds measured
rotor-joint, lift-off, hover and landing checks, then flies Qwen, Qwen + Florence-2
and Qwen + SmolVLM2 through matched conditions. It separates physical flight
success from object-recognition success and retains failed controller revisions.

## What changes in native simulation

- Total mass, body inertia, horizontal geometry, rotor radius, thrust coefficient,
  torque coefficient, motor rise/fall response, maximum rotor speed and rotor drag
  are applied to generated Gazebo models. The pinned upstream model is unchanged.
- The supported geometry is a horizontally scaled quad-X family, retaining the
  upstream vertical body/landing-gear arrangement. Arbitrary airframe CAD, propwash,
  ground/wall effect, battery voltage sag and flexible contact dynamics are not modeled.
- Camera resolution, focal lengths, principal point, Brown–Conrady distortion,
  mounting pitch/offset, exposure, rolling-shutter time, delivery delay/jitter,
  burst frame drops and JPEG quality are configurable.
- Lens projection/undistortion uses matching mathematical conventions in Three.js
  and Python triangulation. Exposure and rolling shutter use first-order rotational
  image warps and five exposure samples. Translation, disocclusion, moving-object
  exposure integration, auto-exposure/ISP and measured sensor noise remain gaps.
- GPS-disabled mode removes the Gazebo GNSS sensor, disables PX4 GPS fusion and
  enables external-vision position/height/yaw fusion. A simulator-only adapter
  generates delayed, noisy odometry with drift and covariance from physics truth.
  **This is sensor emulation, not image-derived VIO/SLAM.** The mission controller
  receives PX4 estimates, not simulator pose.
- The native planner starts with unknown space. It builds a 5 cm grid from synthetic
  column-range returns, inflates obstacles/unknowns by the configured rotor envelope,
  clearance and tracking reserve, and advances through observed free space. It has
  no reference to the obstacle manifest. Range coverage is reported separately from
  camera/object coverage. The sensor approximates depth/multilayer lidar over a
  vertical column, not a single planar range scanner.
- Freshness/uncertainty/clearance failures cause a hold, bounded recovery wait, or
  failed mission with landing cleanup. Scheduled range/odometry outages are part of
  the new finite challenge. Limits and failures stay in the saved records.

The operator supplies the operating boundary, launch pad and inspection stations.
The hardware test pad is (4.4, 1.25) m so the rotor envelope has adequate initial
clearance. It differs from the earlier small-vehicle pad. Search stations remain
operator-authored; autonomous selection of complete visual coverage is not yet
qualified. The operator display may show truth; the navigation policy does not
receive that displayed map.

## Profile management and comparison

Open `http://127.0.0.1:8137/airframes` to create a variant, edit the complete JSON
parameters, save a revision and assign profiles to Scout 01 / Scout 02. The JSON
editor exposes explicit units and validates finite values, thrust reserve, inertia
and rotor envelope. Conflicting saves are rejected instead of silently overwriting.

The mission-control fleet pins the selected profiles in its plan and evidence.
That existing dashboard still runs **sequential kinematic aircraft missions**;
it does not apply native airframe dynamics. Native comparisons below apply the
physical profiles. Simultaneous native aircraft in shared airspace are not enabled.

```sh
.local/laya-env/bin/python -m scripts.airframes list
.local/laya-env/bin/python -m scripts.airframes show reference-quad@1
.local/laya-env/bin/python -m scripts.airframes save my-quad.json --expected-revision 0
.local/laya-env/bin/python -m scripts.airframes assign drone-02 light-quad@1

# One aircraft, complete new challenge. Keep each output directory new.
.local/laya-env/bin/python -m scripts.evaluate_flight \
  --suite realism --assets polyhaven --model-size 2b --arms qwen+laya \
  --airframes reference-quad@1 --navigation observed --keep-going \
  --output .local/validation/my-realism-run

# Several profiles in one comparison, executed sequentially to share one model.
.local/laya-env/bin/python -m scripts.evaluate_flight \
  --suite realism --assets polyhaven --model-size 2b --arms qwen+laya \
  --airframes reference-quad@1 light-quad@1 payload-quad@1 \
  --navigation observed --keep-going --output .local/validation/my-comparison
```

`--smoke` performs one inspection flight per selected profile without inference.
It honors `--cases` and uses the first selected case. For example, add
`--smoke --suite realism --cases realism-east-motion-present` to exercise the
scheduled odometry outage with several profiles. The `speed_m_s` limit controls
horizontal cruise; the recorded peak 3D speed also includes vertical takeoff.
`--navigation operator-map` retains the prior navigation approach for comparison.
`--cases` selects diagnostic cases; it cannot qualify the complete suite.
Each output records the hardware content/revision/hash, generated SDF/audit,
source/asset hashes, parameters, estimated/true trajectories, observed map,
sensor recovery events, actual model responses, frames and video. Failed attempts
are retained. A failed test returns nonzero. Sequential trials have different
sensor/flight timing; do not claim paired accuracy from aggregate differences.

## Real camera and aircraft measurements, when available

Offline tools have a separate environment; no OpenCV dependency is added to the
operating application:

```sh
python3 -m venv .local/calibration-env
.local/calibration-env/bin/python -m pip install -r requirements-calibration.txt
.local/calibration-env/bin/python -m scripts.calibrate_camera \
  --manifest camera-capture.json --output calibration-result.json
.local/calibration-env/bin/python -m scripts.identify_airframe motor \
  --input motor-bench.json --output motor-fit.json
.local/calibration-env/bin/python -m scripts.identify_airframe trajectory \
  --input matched-trajectories.json --output flight-agreement.json
```

Camera manifest fields: `camera_id`, `source_kind`, `board_inner_corners` [columns,
rows], measured `square_size_m`, `maximum_reprojection_px`, and `images` entries
with `path` and `split` (`fit` or `check`). At least 10 fit and 3 reserved check
views are required. Files are hashed. Camera intrinsics are frozen before the
reserved-view evaluation; only each reserved view's board pose is solved.
Capture varied board angles/positions at the intended resolution/focus/settings.
This does not calibrate camera-to-IMU mounting, timestamp offset or exposure behavior.

Motor bench input: `source_kind`, `samples` with `time_s`, `command_rad_s`,
`rotor_rad_s`, `thrust_n`. Both spin-up and spin-down excitation are required.
Fit output estimates quadratic thrust constant and first-order motor response;
validate against separate recordings before saving measured values to a profile.
Mass and inertia still require independent measurement. Trajectory input contains
`reference` and `simulation` arrays with `time_s` and `position_m`. It compares
synchronized coordinates without fitting away position/time offsets.

## Reconstructed rooms

`reconstruct_room` accepts registered, rectified RGB/depth images, intrinsics,
metric depth scale and measured camera-to-ENU transforms. It builds bounded
colored triangle surfaces, rejects depth discontinuities, preserves source hashes
and emits an embedded GLB. It never fills unseen space or guesses metric scale.
Ordinary uncalibrated photos first require an external reconstruction pipeline.

```sh
.local/calibration-env/bin/python -m scripts.reconstruct_room \
  --manifest registered-rgbd.json --output captured-workshop
.local/laya-env/bin/python -m scripts.check_room_camera \
  --room captured-workshop/room.json --output .local/validation/room-import-check
# Add --room captured-workshop/room.json to a native flight command.
```

The input has `camera` (`rectified:true`, width/height/fx/fy/cx/cy),
`depth_scale_m`, `stride` (4–32), up to 64 `frames` (`rgb`, `depth`,
`camera_to_enu` 4×4 rigid transform), and `room` metadata. Room metadata declares
`source_kind` (`real-capture`, `public-reconstruction` or `synthetic-fixture`),
`provenance`, `dimensions_m`, `coordinate_frame` exactly
`ENU-metres; GLB is x=east,y=up,z=south`, surveyed `collision_boxes`,
`unknown_boxes`, and at least three `control_points` with `mesh_enu_m` and
`measured_enu_m`. Boxes use x/y/sx/sy/bottom/height in metres. Unknown boxes are
conservative simulator barriers; their sensing behavior is an approximation.
Control-point agreement is checked within 5 cm, but supplied coordinates do not
by themselves establish an independent survey. Reserve real images for manual
render agreement checks and real-video perception evaluation.

Existing reconstructed GLBs can use the same room package format: embedded
buffers/textures, static triangles, explicit metric frame, a `visual_glb` filename
and its `visual_sha256`. Budgets are 250,000 triangles and 128 MiB per GLB.
The native challenge currently requires a **12 × 10 × 3 m operating volume**; crop
and align a real-room package accordingly. Surveyed boxes and unknown barriers
feed collisions; the visual triangle mesh is not treated as complete physical
geometry. Movable targets must be removed from the static capture so they are
not baked into it twice. The package is copied and frozen before a run.

The available room reconstruction test uses a generated RGB-D plane. It validates
geometry packaging/rendering, not the appearance or completeness of a real room.
For actual recorded-camera perception, retain the separate importer, site splits
and exposure ledger documented in `reliability-protocol.md`.

## Qualification boundaries

The new `realism` suite has eight predeclared synthetic cases, with changed
furniture/clutter, present/absent pairs, degraded imagery and scheduled sensor
outages. They are additional development cases, not independent real sites.
Finite challenge success never establishes 100% real-world reliability.

The application retains a sampled 5 GiB memory guard. This host has 16 GiB;
actual 8 GiB hardware, physical aircraft, real-camera VIO and simultaneous native
multi-drone flight remain unqualified. Offline calibration/reconstruction should
run separately from operation.

## Measured development result, 21 October 2026

The first complete GPS-disabled reference-profile challenge executed all eight
planned attempts: **4/8 passed**, with **one false location claim**. All four
target-absent cases completed without a claim. The target-present attempts had
one visual miss, one wrong-object report, one observed-clearance stop and one
PX4 parameter-transfer timeout before takeoff. No attempt recorded a rotor-envelope
violation. Peak sampled application guard measure was **3.718 GiB** on the 16 GiB
M4 host. This is not evidence of reliable target localization or 8 GiB qualification.

The complete frozen record is
`.local/validation/realism-hardware-v3/results.json`; the video review is
`.local/validation/realism-hardware-review-v2/report.html`. No failed attempt is
replaced by a later retry. Earlier startup-only attempts and flight bring-up
failures are retained alongside it.

After this batch, parameter writes gained bounded retries with matching readback,
navigation gained a preference for extra clearance from uncertain edges, and
stopping distance began using the profile's acceleration limit. Sensor injection
start/end events are now recorded and stale-position holds apply near waypoints.
These are control changes; the Qwen/Laya prompts and object-identity gate are
unchanged. Subsequent diagnostic flights are separate from the eight-case result.

The complete regression suite passes **150 tests**, including immutable hardware
pinning through mission launch, HTTP revision conflicts, failed parameter readback,
near-waypoint sensor loss and profile-dependent braking distance. Browser checks
verified profile creation/assignment persistence, mobile layout and 12 lens
projection markers (maximum discrepancy **0.403 px**). The video review passed
decode and mid-video seeking checks.

Offline fixtures yielded camera fit RMS **0.101 px**, four reserved-view RMS
values **0.045–0.189 px**, and motor rise/fall estimates **0.02500/0.04492 s** for
known **0.025/0.045 s** inputs. A known 5 cm trajectory offset remained 5 cm in
the agreement report. The RGB-D plane produced a 1,716-triangle embedded GLB and
rendered through the flight camera. All these calibration/reconstruction inputs
are synthetic fixtures, not measurements from a physical drone or workshop.

The subsequent two-profile native flight batch passed both smoke missions:

| Profile | Mass | Distance | Estimated-position RMSE | Envelope violations | Odometry outage |
| --- | ---: | ---: | ---: | ---: | --- |
| Light r1 | 1.25 kg | 17.55 m | 0.0266 m | 0 | Hold, recover, resume, land |
| Payload r1 | 2.70 kg | 17.58 m | 0.0248 m | 0 | Hold, recover, resume, land |

Both runs used different generated physical models, GPS-disabled PX4 and the
observed map. Their minimum centre clearances were 0.626/0.814 m against rotor
envelopes of 0.31/0.44 m. Each flight recorded the injected 0.6-second odometry
loss and an explicit hold/resume. They performed one inspection station without
model inference, so their task-correct fields are not recognition scores. The
batch record is `.local/validation/hardware-profile-flights-v1/results.json`.
The earlier reference-profile bring-up also completed takeoff, inspection,
return and landing with no envelope violation.

The two post-fix Qwen + Laya diagnostic reruns both completed their flight and
landing with no error or envelope violation. The prior glare clearance stop was
cleared (35.55 m flown, 0.762 m minimum centre clearance), and the occlusion case
passed startup and held/resumed through the 0.8-second scheduled range outage
(40.36 m flown, 0.744 m minimum clearance). **Neither passed recognition**:
glare accepted a decoy 6.15 m from the target; occlusion ended unresolved.
Their **0/2** diagnostic result and 3.612 GiB peak are saved in
`.local/validation/hardware-control-retest-v1/results.json`. They do not replace
or improve the original **4/8** score. Better physical testing has exposed a
perception bottleneck; this system is not qualified for autonomous real-drone work.

Portable summaries and regression output are in
`docs/hardware-realism-validation.json` and `docs/hardware-realism-tests.txt`.

Primary references: [OpenCV calibration](https://docs.opencv.org/4.x/dc/dbb/tutorial_py_calibration.html),
[PX4 external positioning](https://docs.px4.io/main/en/ros/external_position_estimation),
and the pinned PX4 model/parameter definitions used by the generated SDF.
