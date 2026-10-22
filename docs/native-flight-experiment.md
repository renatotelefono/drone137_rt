# Dense workshop with native flight

This experiment replaces teleported camera stations with an actual PX4-controlled
Gazebo x500. Three.js renders the simulated rigid body's position, orientation,
and fixed camera mount. Qwen3-VL-2B sees JPEG pixels; either Qwen or local Laya
selects scan, confirm, found, or unresolved. A deterministic executor commands
bounded local-position setpoints; the language model never controls motors.

## What tenfold means

The original realism scene has 12 independent scene props. This scene has 120,
including stacked cartons, bins, paint tins, red canister lookalikes, tool cases,
and the original workshop equipment. Supporting shelves, building services and
wall framing add further geometry. This is a **10× prop count**, not a measured
10× increase in realism or reliability. Both rendering and physics use one
metre-scale scene manifest. Conservative boxes simplify prop collision geometry.

The initial three authored cases contain an extinguisher, an absent target replaced by a
red canister, or an extinguisher in low light. A fourth case relocates the target
to the far room and starts the search there, forcing a doorway transit. Four operator-defined search areas
allow one lateral confirmation each. Neither model receives target coordinates,
object lists, simulator truth, or the score. The operator map does inform the
executor's collision-aware route. This is not unknown-map autonomous navigation.

## Flight and camera

- Pinned PX4 SITL + Gazebo Harmonic; native x500 rigid body, four rotor thrust/drag
  models, motor rise/fall time constants, inherited IMU and barometer noise, and
  PX4 estimation/control. Physics step: 4 ms. No physical-aircraft transport.
- 0.6 m/s horizontal cruise; 0.65 m/s maximum horizontal velocity parameter;
  acceleration and jerk limits. These are controller parameters, not guarantees
  that measured speed never overshoots. Vertical takeoff is recorded separately.
- A conservative 0.58 m centre clearance is used for planning. The X500 is larger
  than the original kinematic drone. Near-obstacle and stale-telemetry guards hold
  flight; native arming checks remain enabled. Failure cleanup attempts landing.
- Synthetic draft: mean ENU wind [0.6, 0.15, 0] m/s, 25% sinusoidal magnitude
  fluctuation over 7 seconds, Gazebo force scale 0.25. This is an uncalibrated
  disturbance test, not indoor airflow CFD or measured aerodynamics.
- A joint-driven rolling cart has a physical collision body. Its measured native
  pose drives its rendered mesh; its swept volume is reserved in the route map.
- One 960×540 renderer at 15 fps, 1.4 Mbps WebM, shared procedural geometry and
  materials, existing local scanned concrete textures, 1024-pixel shadows.
  JPEGs use quality 0.82 and a 200 KB cap. No second Gazebo graphics renderer.
- Full body attitude changes the camera's view; a fixed mount points down 10°,
  12 cm forward and 2 cm above the body origin. Motion-dependent blur, lens
  distortion, exposure, vignette, jitter and noise are synthetic stress effects.
- Ground truth drives rendered pixels and evaluation only. Triangulation uses
  model-predicted boxes and PX4 estimated position/full attitude. Camera nominal
  intrinsics intentionally do not remove the synthetic lens distortion.
- A fresh-frame gate retains capture metadata and prohibits stale captures.
  Simulation timestamps, host receipt timestamps and rendered-frame timestamps
  are separate. This does not emulate hardware exposure synchronization.

## Reproduce

First install the existing pinned native simulator (`scripts/install-sim.sh`) and
start the recon app on port 8137 with the verified local Qwen model ready/idle.
Install Laya as described in `localization-experiment.md`, then:

```bash
.local/laya-env/bin/python -m pip install -r requirements-flight.txt
scripts/with-sim.sh cmake -S sim/bridge -B .local/build/image-bridge
scripts/with-sim.sh cmake --build .local/build/image-bridge -j 2
.local/laya-env/bin/python -m scripts.evaluate_flight \
  --output .local/validation/dense-native-new-run
```

Use `--smoke` for a flight-only integration check or `--arms qwen` for Qwen alone.
The output directory must be new. During each flight the live camera is served on
`http://127.0.0.1:8141`; the runner owns its simulator, bridge and browser processes
and closes them afterward. Port 50051 and MAVLink loopback 14540 are used by SITL.
The recon dashboard remains the existing kinematic application; this harness is
an explicitly separate native-flight evaluation path.

Each run saves scene/SDF, native process logs, PX4 flight logs, continuous video,
individual inference JPEGs, model responses, timestamps, estimated and true poses,
route samples and per-case scores. The top-level report includes memory samples.
Failed startup runs are retained; simulator integration fixes are not model wins.

## Resource accounting and limits

The same sampled 5 GiB application guard leaves roughly 3 GiB from an 8 GiB total
for the OS. It includes the evaluator, Laya when loaded, browser/GPU processes,
PX4, Gazebo, MAVSDK, bridges, the recon server and Qwen. It is a cooperative guard,
not an OS-enforced memory ceiling, and may miss short peaks. The current machine
has 16 GiB; success here does not qualify an 8 GiB machine or multiple drones.

Models run sequentially through independent physical flights. Camera images differ
because position estimates, sensor noise, cart motion and flight timing differ.
These results are a small stress experiment, not a statistically powered paired
comparison or proof of performance in unfamiliar environments.

Real-flight fidelity still needs the intended drone's mass/inertia, thrust curve,
motor response, drag and camera calibration, checked against real logged motion.
Indoor GNSS is currently simulated; GPS-denied VIO/SLAM, range sensing, estimator
outages, network loss, rolling shutter, battery sag, contact-force scoring,
propwash, wall/ground effect and detailed flexible collisions remain unqualified.
A visually denser workshop does not close these gaps. Before physical flight,
match recorded trajectories and sensor residuals, then qualify the same controller
with hardware-in-the-loop and a constrained test setup.

## Primary references

- [PX4 Gazebo simulation and lockstep](https://docs.px4.io/main/en/sim_gazebo_gz/)
- [Gazebo Harmonic multicopter motor model](https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1MulticopterMotorModel.html)
- [Gazebo Harmonic wind-force approximation](https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1WindEffects.html)

Implementation values come from the locally pinned PX4 model files and version
manifest, rather than assuming that latest online documentation matches the build.

## Results on 21 October 2026

The latest four cases per supervisor all returned and landed (8/8 flights), with
no violations of the conservative horizontal vehicle envelope. They flew 167.35 m
in total. Estimated-versus-simulator position RMSE ranged from 7.1 to 7.8 cm;
simulation ran at 0.989–0.990 times wall time. This measures agreement inside the
simulator, not accuracy against a real aircraft. Two runs crossed the partition.

Both Qwen and Qwen+Laya completed 2/4 search jobs correctly. Normal and low-light
target locations were within 6–35 cm. Both misidentified canisters in the absent
and far-room cases; the latter claims were about 5.5 m from the real target.
Laya therefore did not improve accuracy in this small sample. Mean supervisor
decision times were 0.312 s for Qwen and 0.095 s for Laya. Flight dominated total
time, and the images were not identical, so these are descriptive measurements.

Sampled physical-footprint peaks were 2.39 GiB for Qwen and 3.34 GiB for Qwen+Laya.
All runs stayed under the 5 GiB application guard. 117 automated tests passed.

Ten scored attempts are retained: the original six-run comparison, then four
follow-up flights for low light and the added far-room case. The first Laya
low-light run aborted on stale telemetry and landed locally. Dense-map A* had
blocked the telemetry event loop; planning now runs in a worker thread. The
freshness threshold remains unchanged. Follow-ups also added the extinguisher's
floor stand; source snapshots and independent per-run records preserve both
versions. Early startup and camera-helper shutdown diagnostic failures remain in
`.local/validation/native-flight-smoke-*` and `dense-native-evaluation-v1`.

Review at `http://127.0.0.1:8142/dense-native-review/report.html`. Restart the
range-capable viewer with:

```bash
.venv/bin/python -m scripts.serve_flight_reports --directory .local/validation --port 8142
```

The review includes latest results, all earlier attempts, actual trajectories,
model predictions, complete original video, and indexed copies for seeking.
See `native-flight-validation.json` for compact evidence. Physical deployment
remains unqualified: fix identity verification and calibrate the intended
airframe/camera plus indoor positioning before moving to real-drone trials.

The subsequent [identity improvement experiment](identity-improvement.md)
separates object evidence from triangulation, compares 2B/4B, and adds bounded
detail views. Its complete 2B batch improved to 3/4 with no false location
claims; all development and infrastructure failures are retained. A later
low-light pass does not establish reliable recognition or real-world readiness.

The [harder Qwen + Laya qualification experiment](real-room-qualification.md)
then scored 5/8 on frozen unfamiliar furniture arrangements with image delay,
frame drops, blur, glare and partial occlusion. It retained a wrong-object
claim and two misses. All eight flights landed, but only 1/4 target-present
missions succeeded. A reference-photo diagnostic was worse and was not adopted.
That document also assesses offline Glob3R reconstruction and the remaining
real-camera, indoor-positioning and target-verification work.
