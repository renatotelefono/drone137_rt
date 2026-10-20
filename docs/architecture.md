# Architecture and invariants

This page describes the implemented gate-inspection fixture. The
[current reconnaissance objective](recon-objective.md) requires additional mapping,
exploration, local navigation and video recording; those components are planned,
not implemented. The authored waypoint graph below is not an autonomous
obstacle-avoidance planner.

`scripts.launch` is the parent process. It starts the app in its own process group,
accepts stop requests over a local Unix socket, and cleans recorded native process
groups if the app exits. `ProcessSupervisor` owns only processes it launches.
The SDK is disconnected before PX4/Gazebo cleanup; a five-second observation window
does not by itself prove the autopilot's loss response.

The app runs an asyncio HTTP API, camera producer, mission task and independent
telemetry supervisor. Only `MissionExecutor` sends drone commands. Its command
lock serializes requests; acknowledgement and arrival are distinct events.
Arrival requires position tolerance, speed below the limit and a settling period.
Named waypoints are joined only by explicit graph edges. Configuration validation
rejects points outside the flight volume before any command is sent.

State path: `idle → moving → observing → moving → landing → complete`.
Pause invalidates the request generation, cancels inference, holds finitely and
lands. Operator landing preempts the mission at the current location. A failure
lands after a finite hold; telemetry/process failure requests immediate landing.
Landing confirmation may be unavailable on lost telemetry and is reported as such.
No app-level action proves PX4 recovery after a broken command connection.

## Inference and freshness

- One inference request at a time. HTTP cancellation is not server cancellation.
  A timed-out/cancelled llama client is quarantined. Restart the owned model process
  before subsequent inference; there is no hidden retry.
- The decision has exactly four fields. Unknown/duplicate fields, extra coordinates,
  invalid enums, wrong views and excessive output are rejected.
- Episode, frame and request IDs originate in the app, never the model.
- A frame must be received after arrival and within the dispatch-age budget.
  Responses must meet the request deadline, generation, mission state, target view,
  fresh telemetry and position/velocity checks.
- A target permits at most one alternate viewpoint. The model cannot take off,
  arm, invent coordinates, execute code or select arbitrary transport.
- Camera buffers hold one frame. Inference history does not grow across requests.

## Coordinates and clocks

Mission and Gazebo world coordinates use ENU metres: east, north, up.
MAVSDK local telemetry uses NED, converted as `(east, north, -down)`.
Navigation yaw is clockwise degrees from north; observations face north.
`goto_location` receives degrees latitude/longitude and altitude AMSL calculated
from a fixed home reference. The local tangent approximation is intended only for
the small courtyard, not large-area navigation.

Native bridge frames preserve sensor simulation time and host monotonic receipt
time separately. Their mapping has not been calibrated. Reports therefore expose
receipt age and set capture age to unknown. RTP fallback likewise reports receipt
time only. No subtraction across the two clocks is permitted.

## Native integration status

The llama HTTP adapter sends actual JPEG image content and a JSON schema to a
loopback server. Its protocol tests use an HTTP stub, not a real model.
MAVSDK 3.17.4 is intentionally pinned to its external-server API; version 4 of the
`mavsdk` package is a different native API. Future maintenance can evaluate
`mavsdk-grpc` explicitly.

The selected PX4 mono camera publishes Gazebo images, not RTP by default.
`sim/bridge` subscribes to that topic, keeps one RGB8 320×240 frame, encodes JPEG,
and transmits a bounded length-framed stream to Python. Native compilation and
camera correctness remain pending. The optional RTP receiver is implemented but
not selected by the native launcher.

The staged installer makes local copies of pinned upstream camera models, reducing
the sensor to 320×240 at 2 Hz and setting `/drone137/camera`. It does not edit PX4
source. Native startup relies on PX4's pinned macOS environment and local assets.
Validate resource search precedence, model name, spawn origin, camera orientation,
home altitude, GStreamer/bridge libraries and actual arrival on the target Mac.

## Remaining engineering limits

The native scripts are candidate integration paths, not a validated Mac release.
Full simulator executor/app-death recovery, simulator clock mapping, latency/accuracy scoring,
held-out scenario orchestration and physical-memory accounting still require
implementation/validation during A05–A07. The resource runner currently records
system pressure/swap signals and repeated routes, and deliberately does not grade
the 5 GiB budget. Native logs are capped at 8 MiB each, visibly report discarded
output, and block reuse until explicitly archived. Evaluation reports share the
1 GiB evidence budget using a cross-process file lock.

The parent detects app exit and missed HTTP heartbeats independently. It disconnects
the owned SDK on failure. HTTP-stall and owned-process cleanup are tested in the cloud;
actual vehicle recovery with tested PX4 loss parameters still requires the simulator.
Simulation and physical acceptance remain blocked.
