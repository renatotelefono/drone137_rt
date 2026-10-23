# Indoor component physics lab

The five proposed ESP32 camera drones now have a separate, runnable microquad
physics path. Components live in SQLite, assemblies pin component revisions,
and experiments freeze the full assembly plus the physics source checksum.
The same JavaScript model runs in Node and underneath the Three.js lab.
This does not replace the existing PX4/Gazebo tests or enable physical transport.

## Run and swap components

```sh
.venv/bin/python -m scripts.component_lab --port 8152
# Open http://127.0.0.1:8152/components
.venv/bin/python -m scripts.evaluate_components
DRONE137_PYTHON=.venv/bin/python node --test scripts/test-component-physics.mjs
.venv/bin/python -m unittest discover -s tests -p 'test_components.py' -v
```

The main recon app also exposes `/components`, linked from mission control and
the aircraft library. Restart an already running main server to load these routes.
The standalone lab needs no local LLM, native simulator, npm install or internet.
Its links to mission control/airframes are available when using the main app.

The default database is `.local/data/components.sqlite3`; `DRONE137_DATA_DIR`
changes its directory, and both commands accept `--db`. The main recon app keeps
the component database next to its runs directory. No operational x500 profile
or fleet assignment is modified. `sim/component_defaults.py` seeds a new database;
it never overwrites saved revisions. Clone/edit a component in the JSON editor,
then explicitly select that revision and save an assembly variant. Unsaved swaps
cannot be run. Existing experiments keep their original component versions.

Motor and matched propeller are one component because the available measurements
describe the combination. Four identical propulsion units are mounted at the
frame's motor locations. Other slots are frame, battery, avionics, motor drivers,
IMU and optional downward range sensor. Validation checks dimensions, motor voltage
compatibility, units/ranges, monotonic curves and per-parameter evidence. An
electrical/geometry-compatible swap is not automatically a viable aircraft.
Budgets are not recalculated by this simulation library.

## Physics engine choice

| Library | Assessment for this task |
|---|---|
| [Rapier](https://rapier.rs/docs/user_guides/javascript/getting_started_js/) | Selected. Browser/Node WebAssembly, dynamic rigid bodies, contact solver, continuous collision detection and forces applied at rotor locations. Pinned to 0.21.0; vendored with Apache-2.0 license and npm integrity/hash manifest. |
| [cannon-es](https://pmndrs.github.io/cannon-es/) | Lightweight JavaScript alternative with Three.js examples. Considered, not integrated or performance-benchmarked. |
| [MuJoCo](https://mujoco.readthedocs.io/en/stable/computation/fluid.html) | Useful robotics reference and possible independent validation backend. Its fluid models are approximations, not full CFD. Considered, not installed for this lab. |
| Existing PX4/Gazebo path | Retained for flight-stack validation. The current x500-derived airframe profiles do not represent these microquads or ESP32 firmware. |

Three.js copies Rapier's position/quaternion; it does not interpolate a fabricated
flight path. Simulation uses metres, kilograms, seconds and Y-up coordinates at a
fixed 4 ms step, independent of rendering frame rate. Eight solver iterations and
a 0.1 m characteristic length support the small geometry. Rendering catches up
in bounded increments; a slow/hidden browser may run slower than wall time.
Component control rates are restricted to 125 or 250 Hz, which the 4 ms lab can
represent exactly; these are illustrative control schedules, not MCU timing measurements.

The application adds the domain models physics libraries do not supply:

- Four forces at rotor positions, alternating yaw reaction torque, motor lag,
  centre of mass and diagonal inertia derived from approximate component shapes.
- Static motor-voltage/thrust/current/RPM curves, clamped outside their supplied
  domain. A bisection load-line solve combines PWM battery current, driver
  conduction loss and battery internal resistance. Capacity discharges with
  current; OCV is a provisional linear function of charge.
- Quadratic air-relative drag and a repeatable gust; ground, walls and box
  collisions, including conservative solid propeller/guard envelopes.
- Adaptive position/tilt feedback, online rotor-effectiveness estimates, bounded
  motor allocation and lag compensation, battery-power limits, noisy gyro
  readings, command expiry and an illustrative landing response.
- Optional noisy floor-range readings, bounded range/FOV, and delayed camera
  poses. The Three.js camera renders those poses at the selected resolution/rate.

The controller receives ideal external position, velocity and attitude. This is
explicitly not a tested ESP32 estimator/firmware implementation. The extra MCU
currently changes mass/power, not measured scheduling performance. Range readings
do not supply XY positioning and are not fused into the controller. Camera optics,
exposure, compression, Wi-Fi contention and image recognition are not exercised in
this lab. The existing camera-effects/vision-flight experiments remain separate.
There is no ground effect, rotor interference, downwash between vehicles, flexible
frame/guard aerodynamics, thermal model or flight-duration qualification. Geometry
and mass distribution are approximations, not compiled manufacturing CAD.

## Data quality

Every numeric parameter has `estimated`, `specified`, `derived` or `measured`
evidence with a note and, except estimates, a source reference. These labels
describe evidence supplied by the author, not independent certification.

- [Bitcraze's 2015 measurements](https://www.bitcraze.io/documentation/repository/crazyflie-firmware/master/functional-areas/pwm-to-thrust/)
  provide the documented reference curve. The published thrust/current are for
  **four motors**. Per-rotor force is total grams-force × 0.00981 / 4; motor current
  is (total current − the recorded 0.24 A idle draw) / 4. Indexing by PWM × battery
  voltage assumes average-voltage equivalence and motor symmetry. These derived
  curves are not measurements of the proposed 720/8520 sets.
- The 27 g reference matches the nominal total in the
  [Crazyflie 2.0 datasheet](https://www.bitcraze.io/documentation/hardware/crazyflie_2_0/crazyflie_2_0-datasheet.pdf).
  Its component mass split, geometry, battery dynamics and controller remain
  provisional. It is a reference experiment, not another under-$50 camera build.
- [Drona's Pluto 600 table](https://www.dronaaviation.com/hardware/parts) supplies
  600 mAh, 16 g, 4.2/3.2 V and an internal resistance below 0.070 ohm. The model uses
  that resistance bound, with an estimated cutoff/OCV curve. The Scout variant
  with this pack has better battery documentation, not proven superior hardware.
- [AO3400A data](https://www.aosmd.com/products/mosfets/low-voltage-mosfets-12v-30v/ao3400a)
  supply a 48 milliohm maximum at 2.5 V gate drive; PCB heating and switching losses
  still need measurement. [Seeed](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/#resources),
  the [MPU6050 datasheet](https://files.seeedstudio.com/wiki/Xadow_IMU_6DOF/res/MPU6050.pdf)
  and [VL53L0X datasheet](https://www.st.com/resource/en/datasheet/vl53l0x.pdf) are
  references for electronics/sensing; effective sampled behaviour remains provisional.
- 720/55 mm and 8520/65 mm thrust/current curves are **hypotheses**. Their values
  are not attributed to supplier testing. The 70% thrust case probes sensitivity;
  that factor is an experiment setting, not a measured tolerance bound.

The library lists documented propulsion first, then source-backed parameter
counts. This is a transparent data-coverage preference, not a reliability ranking.


## Controller and power revisions — latest results

The flight-completion target is met **inside the current simulation model**:
**40/42 (95.2%)**, against **22/42 (52.4%)** originally. Updating only the
controller on the original seven assemblies gives **36/42 (85.7%)**. Reaching
95% also required explicit battery revisions for the five proposed designs.
No motor curves, masses of existing parts, environment, mission waypoints,
fault magnitudes/times, collision rules, voltage cutoffs or pass thresholds
were relaxed. Both original reference configurations remain in the comparison.

| Configuration | Original controller | New controller, original parts | New controller, revised parts | Additional seeds |
|---|---:|---:|---:|---:|
| Crazyflie-derived reference | 4/6 | 6/6 | 6/6 | 60/60 |
| Micro 90 / 1S2P | 3/6 | 5/6 | 5/6 | 50/60 |
| Scout 110 / 1S2P | 3/6 | 5/6 | 6/6 | 60/60 |
| Guard 110 / 1S3P | 3/6 | 5/6 | 6/6 | 60/60 |
| Height 110 / 1S3P | 3/6 | 5/6 | 6/6 | 60/60 |
| Split 110 / 1S3P | 3/6 | 5/6 | 6/6 | 60/60 |
| Scout / original Pluto pack | 3/6 | 5/6 | 5/6 | 50/60 |

Ten additional noise seeds, chosen after the final controller was fixed, passed
**400/420 (95.2%)**. A full rerun at half the timestep (2 ms rather than 4 ms)
passed **40/42** with the same two failures. These repetitions vary gyro/range
noise, not room geometry, battery chemistry or real-world manufacturing spread.
They are robustness checks on this model, not a confidence claim about deployment.
Earlier development runs that failed are retained in local SQLite/validation
history; they are not combined with final runs to inflate the percentage.

The remaining failures are Micro 90 power v2 with a weakened motor and the
unchanged Pluto-pack Scout at 15% charge. The **separate, unchanged 2:1 thrust
reserve screen passes only 27/42 (64.3%)**. A flight pass is therefore not an
engineering qualification, a vision-recognition result, or hardware approval.

### What changed

The controller estimates each rotor's effectiveness from velocity/gyro changes
and its own lagged actuator model. Its input packet contains navigation, gyro
and voltage telemetry; it cannot read the scenario, injected rotor gain, actual
rotor forces or true battery charge. The existing ideal external position,
velocity and attitude inputs remain an important limitation. No real estimator
or ESP32 flight firmware was implemented in this change.

It tracks climb/descent velocity as well as position, compensates known motor
lag and driver voltage loss, and bounds motor allocation so tilt and lift take
priority over heading. Under asymmetric rotor effectiveness it releases heading
tracking while continuing to damp yaw. A power limiter predicts voltage sag
from measured voltage/current and avoids demanding power below the unchanged
cutoff. It cannot make an undersized pack capable of hover.

The architecture draws on [PX4 control allocation](https://docs.px4.io/main/en/concept/control_allocation)
and [incremental feedback research](https://repository.tudelft.nl/record/uuid%3A3079ef6f-907b-4b55-b21f-4a3ad8b65401).
This is our provisional controller, not a port or validation of those flight stacks.

The new SQLite batteries are **design hypotheses**, not newly measured products:

| Battery component | Composition | Capacity | Installed model mass | Assumed resistance |
|---|---|---:|---:|---:|
| `battery-240-2p@1` | Two original 240 mAh cell surrogates in parallel + harness | 480 mAh | 15.6 g | 0.060 ohm |
| `battery-240-3p@1` | Three original 240 mAh cell surrogates in parallel + harness | 720 mAh | 22.9 g | 0.040 ohm |

The arithmetic is mass = cell count × 7.3 g + 1 g harness, capacity = count ×
240 mAh and ideal parallel resistance = 0.12 / count ohm. The parent cell
properties were already estimates. Interconnect losses/current sharing, actual
cell discharge curves and prices still need measurement. All new parameter
evidence remains `estimated`; no supplier data is fabricated. Additional mass
is included in body mass/inertia. Original assemblies are immutable.

Micro/Scout use 1S2P; Guard/Height/Split use 1S3P. Height's initial 1S2P revision
failed additional seeds and remains in history; the final run pins its revision
2. A fresh database seeds the final 1S3P content at revision 1, while the exported
frozen assemblies preserve exactly what was used in the recorded run.

**Scout 110 power v2 is the best next bench candidate in these results:** 65.2 g,
6/6 original scenarios and 60/60 additional runs. Its maximum observed yaw rate
was approximately 0.35 rad/s. The reference and Guard can pass flight gates while
spinning rapidly during fault recovery; those gates do not qualify camera
stability. Object-recognition tests still need to be rerun with realistic pose
estimation and video before this becomes a complete mission-success claim.

The original under-$50 bill of materials is not automatically valid after battery
swaps. To stay under that parts-only ceiling using the existing other allowances,
the entire replacement battery bank must cost at most $19.42 (Micro), $13.42
(Scout), $10.42 (Guard), $7.02 (Height), or $5.43 (Split). No quoted pack meeting
both these price and electrical targets has been established here.

### Verification and reproduction

The archived plant in `tests/fixtures/component-physics-v1.mjs` replays identical
PWM inputs under all six fault scenarios. Its physical states and resulting
gates match the new plant exactly. The mission function and gate implementation
are also compared directly. This distinguishes controller changes from changing
the environment or success definition.

**178 Python tests passed**, including **five registry/API tests**. **11 physics
checks passed**, covering the archived-plant replay, mass/forces, collisions,
battery/lag, sensor timing, repeatability, insufficient-lift rejection, fault
compensation, component revision isolation and the complete 42-flight threshold.
The five registry/API checks are part of the 178, not an additional count.

Use a fresh database or the explicitly recorded revisions to reproduce the
component definitions. The commands below use current saved versions; compare
the exported assembly checksums when using an existing edited database.

```sh
.venv/bin/python -m scripts.evaluate_components \
  --output .local/validation/controller-improvement/verified-revised \
  --configurations cf2-reference micro-90-power-v2 scout-110-power-v2 \
  guard-110-power-v2 height-110-power-v2 split-110-power-v2 scout-published-pack
# Repeat with --dt .002 to check numerical stability.
# Additional seeds used after final tuning:
# --seeds 21001 22003 23003 24001 25013 26003 27011 28001 29009 30011
node --test scripts/test-component-physics.mjs
# Full Python suite also needs the existing calibration environment's NumPy:
PYTHONPATH="$PWD/.local/calibration-env/lib/python3.12/site-packages:$PWD" \
  .venv/bin/python -m unittest discover -s tests -v
```

[Comparison summary](component-controller-comparison.json),
[all final trial results](component-controller-trials.json) and
[exact revised assembly inputs](component-controller-inputs.json) are portable.
Full trajectories remain under `.local/validation/controller-improvement/`.
`scripts.report_component_control` checks complete cohorts and matching code
hashes before publishing the comparison shown in `/components`.

The final additional-seed runner peaked at **425.1 MiB**. This excludes the browser, vision models and the rest of the application; the complete 8 GB stack was not tested.

## Original baseline — 22 October 2026

Seven configurations × six conditions = **42 simulations**, each 20 simulated
seconds. The mission takes off to 0.7 m, hovers, transits 0.5 × 0.35 m, returns and
lands. Conditions are nominal, 15% initial charge, gust, command loss after 7 s,
one motor reduced to 45% after 6 s, and all motors at 70% nominal thrust.

| Configuration | Model mass | Nominal flight | Nominal reserve | Flight passes / 6 | Engineering passes / 6 |
|---|---:|---|---:|---:|---:|
| Published-propulsion reference | 27.0 g | Pass | 2.14× | 4 | 3 |
| Micro 90 | 47.6 g | Pass | 1.99× | 3 | 0 |
| Scout 110 | 63.6 g | Pass | 2.24× | 3 | 3 |
| Guard 110 | 73.6 g | Pass | 1.97× | 3 | 0 |
| Height 110 | 65.6 g | Pass | 2.17× | 3 | 3 |
| Split 110 | 67.6 g | Pass | 2.10× | 3 | 3 |
| Scout / published Pluto pack | 65.6 g | Pass | 2.34× | 3 | 3 |

**22/42 flight passes; 15/42 engineering-screen passes.** This is not an estimate
of real-world success probability: the set includes deliberately injected faults,
uses one deterministic seed, and has no measured airframe calibration. All nominal,
gust and link-loss flights complete. Six low-battery candidates brown out in the
model. Motor degradation loses attitude control. The 70% cases miss the early
hover-error gate and the reserve gate, even where they later achieve altitude.
Micro/Guard miss the proposed 2:1 reserve threshold even at nominal charge. These
are design constraints to investigate, not grounds to approve a physical build.

Flight gates require liftoff >0.5 m, hover RMSE <0.12 m over seconds 3–5, transit
RMSE <0.15 m over seconds 8–10, final height <0.05 m and speed <0.15 m/s, attitude
tilt <35 degrees, no obstacle contact, no battery cutoff and landing impact speed
<0.5 m/s. Link-loss tests require command expiry and omit the transit gate because
the mission has been cancelled. The separate engineering screen additionally
requires at least 2:1 initial static thrust-to-weight. The gate is a design target,
not a universal law. Failed gates are retained in SQLite and displayed in the UI.

The existing Python regression suite passed **178 tests** including five new
registry/API tests. **Eight physics tests** check analytical free fall, mass,
torque direction, measured table units, interpolation limits, sag, motor lag,
collision/CCD, camera delay, range bounds, repeatability, timestep convergence,
insufficient lift and command/motor failures. Browser checks verified a saved
battery swap survived reload, a live flight passed, rendered and physical poses
matched, results persisted and mobile layout did not overflow.

Portable [results](component-physics-validation.json) and exact
[assembly inputs](component-physics-inputs.json) accompany this document. Raw
trajectories, timings and trial snapshots are in
`.local/validation/component-physics-final/`. The reported process peak is for the
headless physics runner only; no full application/model 8 GB claim is made.

Next calibration priority is the two actual propulsion sets on a thrust stand,
then battery load curves, measured assembly mass/inertia, controller timing and
camera/pose estimation. Those measurements can replace estimated component
revisions without changing historical experiments.
