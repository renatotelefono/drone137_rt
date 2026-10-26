# Service-owned mission control

The new `/control` dashboard connects a frozen SQLite component assembly to
Rapier flight dynamics, a service-owned Three.js camera, the local Qwen model,
two-view object localization, return/landing and a recorded evidence report.
Closing or reloading the operator dashboard does not own or terminate these
processes. The earlier kinematic fleet interface remains at `/control-legacy`.
There is one active aircraft; this change does not implement simultaneous flight.

The final Scout 110-B qualification completed **24/24 missions** with zero false
confirmations and a 4.26 GiB peak application-memory measurement on the 16 GiB
development host. See [results, earlier failures and hardware limits](mission-integration-validation.md).

The supported mission is currently an indoor search for a **red fire
extinguisher**. Other briefs are rejected before launch. The model interprets
the brief and proposes visual candidates from camera pixels. Deterministic
navigation and evidence gates constrain actions; the model never emits PWM.

## Runtime

Use the normal `app.server` recon launcher after installing the optional mission
dependencies from `requirements-mission.txt`. Camera rendering requires Node.js,
Playwright 1.58.2 in `.local/browser-test/node_modules`, and Chrome/Chromium.
`CHROMIUM_PATH` can select the executable; the current default is Google Chrome
on macOS. The existing `.local/laya-env` has the required Python dependencies.
Preinstall the runtime, model weights, reviewer weights when used, and local
assets before an offline deployment. No model or asset download happens at
mission launch. These dependency paths need packaging for a fresh deployment;
the developer workstation's installed environment is not a distributable bundle.

On the configured development workstation:

```sh
.local/laya-env/bin/python -m app.server --mode recon --port 8137
```

Open `http://127.0.0.1:8137/control`, start the local model, select an aircraft
and environment, enter the brief and inspection rectangle, then generate and
review the plan before launching. The default aircraft is the Scout 110-B
commercial-parts bench prototype. `Return and land` interrupts the task and
returns to the launch location; `Land here` interrupts it and lands locally.
These interventions are recorded as cancelled missions, not task successes.
They are handled at supervisor checkpoints: an in-progress model/reviewer
request can delay the start of the maneuver. They are not an independent
hardware emergency channel. Landing telemetry can reach the ground before the
mission becomes idle because video/browser finalization is still in progress.

For development with the existing local model already listening on port 8081:

```sh
.local/laya-env/bin/python -m scripts.mission_control --port 8153
```

That separate service shares the installed inference process. Keep the earlier
application idle during evaluation. The integrated recon server checks the
other mission owners before starting a mission.

The camera uses a hidden, service-owned Chromium process. This is independence
from the **operator browser**, not removal of the renderer. Physics runs in a
separate Node process at a fixed 4 ms timestep and advances during inference.
A dedicated ground-transport process sends radio commands at 20 Hz. The
aircraft retains its 0.5-second command watchdog. The transport requires a
renewed bounded-setpoint lease from the supervisor within two seconds; loss of
that lease latches radio silence, after which the aircraft watchdog lands. EOF
from the supervisor withholds commands immediately. This isolates short model/UI
process stalls without leaving an unbounded motor command active. Terminating
the whole computer is not a hardware failsafe test.

After CPU-heavy planning, the supervisor refreshes an old local telemetry cache
before changing its setpoint. A fresh transport reply containing an aircraft
sample older than 0.5 seconds is still rejected. Telemetry logs store each sample
once; the display trail is assembled on request instead of duplicated into every
stored sample.

## Memory

Every plan carries a memory estimate and every mission runs under the memory watch; see
"Memory before a flight" in `mission-control.md`. The run record's `memory` field holds the
estimate, the measured peak, the budget and whether it was exceeded; the full samples are in
`memory.json` next to the run's evidence.

## API

All endpoints bind to loopback. POST requires `X-Drone137-Control: local`; this
header is not authentication and must not be exposed directly to the Internet.

| Endpoint | Behaviour |
|---|---|
| `GET /api/mission/status` | Fleet capability, draft, active mission and live telemetry |
| `POST /api/mission/plan` | Interpret `instruction`, freeze `assembly`, choose `case`, validate `area` |
| `POST /api/mission/launch` | Consume `draft_id`; no browser/camera session is required |
| `POST /api/mission/return` | Interrupt search, return through the known floor plan, land |
| `POST /api/mission/stop` | Interrupt search and land at the current location |
| `GET /api/mission/frame` | Latest service-rendered image for the dashboard |
| `GET /api/mission/runs` | Retained mission history |
| `GET /api/mission/runs/{id}/report.html` | Images, video and complete JSON evidence |

Drafts expire after ten minutes and can be launched once. Code hashes are frozen
at service startup; changing mission code requires restarting the service before
a new plan. Aircraft/component revisions stay frozen inside each mission record.

## Evaluation boundary

`scripts/evaluate_missions.py` launches missions through this API without opening
an operator dashboard. It freezes the complete planned denominator before the
first inference. The existing eight `native-hard-v1` cases retain their object
placements, lookalikes, furniture, occlusion, lighting and camera impairments,
using the existing locally pinned Poly Haven assets. Failure and unexecuted
cases are retained; a later attempt does not overwrite an earlier one.

The scene/camera challenge is unchanged, but the flight backend has changed:
Rapier microquad component dynamics and ideal external positioning replace the
earlier generic PX4 quad and its estimator. This is not an isolated perception
comparison. Navigation uses the earlier known operator map, with object labels
removed from the planner, and a conservative 0.35 m swept envelope. It does not
qualify mapping or indoor positioning on a real drone.

Routing now measures clearance in three dimensions. Low boxes can be overflown
at a checked cruise height; full-height walls and overhead shelves still block
routes. Planning keeps 0.58 m clearance, inspection stations add 0.03 m tracking
reserve, and the flight monitor checks the original 0.35 m envelope against 3D
obstacle boxes and moving-cart bounds. The renderer and physical collision boxes
are unchanged. Earlier attempts treated every obstacle as a full-height column;
their 2D footprint-distance metric is recorded as a navigation limitation, not
silently equated with the new 3D metric. Takeoff/landing floor contact is handled
by the existing landing-speed/contact tests. Endpoint connectors also search
nearby visible grid cells instead of failing when the single rounded cell is
occupied.

Measured hover altitude can overshoot a commanded height slightly. The planner
keeps that actual measurement for clearance checks but bounds all new altitude
commands to 1.8 m. It never copies an out-of-bounds measured height into a command
or relaxes the aircraft limit. The supervisor validates a setpoint before
publishing it to the radio pump. If the pump fails, a latched radio-silence request
lets the aircraft watchdog land while telemetry and video continue. The original
mission remains failed even when recovery observes a successful landing.

The benchmark camera remains 960 × 540 to preserve the existing test. The
assembly's provisional 640 × 480 defaults are recorded as an explicit override,
not silently treated as the tested camera configuration. Real sensor optics,
Wi-Fi latency, onboard camera/control contention, measured motor thrust and
battery sag remain open hardware work.

A mission passes only if it finishes the correct task, lands without an envelope
violation/contact, remains within attitude/power/landing-speed limits, records
video, and finishes within 300 seconds. Present targets require a predicted
location within 0.75 m; absent controls require complete planned search coverage
and no location claim. An unresolved search is not proof of absence.

The evaluation samples the service, renderer, physics, local model and reviewer
processes against a 5 GiB application budget. This leaves nominal room for an
8 GB host, but the current workstation has 16 GiB. Actual 8 GB hardware behaviour
and real-world reliability must remain separately unverified.

```sh
.local/laya-env/bin/python -m scripts.evaluate_missions \
  --port 8137 --assembly scout-110-bench-b --repeats 3 \
  --output .local/validation/mission-integration/new-attempt
```

Results are written to a new directory. Use `scripts/report_missions.py` to render
multiple complete attempts together, keeping failed baselines visible.
Three repeats make 24 planned missions across the same eight known development
cases. This measures repeatability on those cases; it is not a held-out test or
a statistical demonstration of 95% reliability in unfamiliar real rooms.

## Visual verification and acquisition

Qwen proposes a box on the full camera frame. A neutral Qwen crop classifier and
the independently loaded Florence-2 base-ft captioner must both support the
object, in two views with valid triangulation. Native-resolution crops are never
upscaled to invent detail. The dashboard labels rejected proposals separately
from verified locations. Weak or obscured evidence triggers geometry-constrained
view acquisition, including elevated alternatives. No scene object identities or
evaluator target positions are supplied to either model or the planner.

The camera browser rejects external-origin requests. All scene assets and model
weights are local. The qualification runner verifies the installed Qwen hashes
and loaded model identity, freezes source/aircraft/reviewer provenance across
the batch, and decodes every saved video with ffprobe.

`tests.test_mission_transport` checks that a 1.6-second supervisor gap does not
starve radio commands and that exceeding the two-second supervisor lease still
triggers the original aircraft watchdog, with no automatic recovery into flight.
This is a software transport test, not a physical Wi-Fi link test.
