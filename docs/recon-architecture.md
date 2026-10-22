# Recon lab implementation

The Python aiohttp application (`--mode recon`, the default) owns `ModelManager`
and `Recon`. Plain JavaScript renders the scene with vendored Three.js and sends
camera JPEGs and bounded MediaRecorder chunks to loopback HTTP endpoints. A
separate launcher process monitors app health and owns shutdown. All control POSTs
require a custom local header; Host must be localhost/127.0.0.1, and CORS is not
enabled. The app does not expose a physical drone transport in recon mode.

## Mission control and fleet dispatch

`/control` adds a mission composer, area-selection map, two live camera workers and
per-aircraft findings/reports. `app/fleet.py` owns two isolated `Recon` controllers
and a shared-airspace dispatch queue. Qwen interprets a brief into one bounded task;
the controller validates the area and partitions authored viewpoints. A reviewed
draft, current site generation and two matching browser camera leases are required
before a two-aircraft launch. Only one flies at a time. The original lab and fleet
also exclude each other's model operations. Detailed behavior and HTTP contracts
are in [mission-control.md](mission-control.md). The startup browser opens `/control`;
the original lab/API remain available for existing tests and setup.

## Model manager

One supported public Qwen3-VL-2B GGUF and matching projector, one immutable
manifest, one operation at a time, one owned llama-server and one inference request.
`ModelStore` resolves official metadata, enforces fixed filenames, uses advisory
installation locking, preserves resumable partials, validates response ranges,
checks exact byte sizes/SHA256, and renames verified files atomically. It refuses
missing hashes, incompatible manifests and corrupt installed files. The manifest
pins the first resolved commit; upstream changes do not silently replace it.

The pinned llama.cpp runtime runs on loopback with context 2048, one parallel slot,
two CPU threads, and Metal offload on Apple Silicon. Center classification and policy requests are capped at 128
output tokens; detailed object surveys allow 384. Every request keeps six seconds and 64 KiB response data. Timeout/cancellation
quarantines the client because closing HTTP does not prove backend cancellation.
A stop/start creates a fresh owned server. Model operations are blocked during
missions; no automatic scripted fallback occurs. Non-stop finish reasons (including
output-token exhaustion) are rejected. Image requests put pixels before the task
and explicitly disable prompt reuse; cache testing alone did not explain the old
classification failure.

`app/perception.py` separates two model tasks. First the VLM describes one image
and classifies its center as open space, solid surface or uncertain. The lean/native
profile uses `center-evidence-v2`; the detailed camera uses `center-objects-v1`.
Selection depends only on the configured camera profile, never expected labels.
The spatial instructions distinguish center objects from surrounding background; native-camera failures are retained as regressions. A second,
text-only model call selects an allowed inspection action from that observation.
The full inspection has a ten-second deadline; each request keeps its six-second
limit. Range supervision and operator cancellation remain independent.

Historical comparison uses separately classified, aligned images. It never asks
the small model to compare two images while simultaneously selecting flight actions.
Patrols reach the exact checkpoint before looking. Position must match within 2 cm
and yaw within 0.02 radians for comparison. A class transition from open space to
solid surface produces a new-obstruction finding. Equal classes only mean equal
center classifications; they do not assert that everything in the scene is unchanged.
These thresholds apply to ideal virtual pose, not real localization accuracy.
Baseline selection also requires matching visual revision and camera profile.

## Detailed workshop and camera

`app/ui/scene-detail.js` builds local compound meshes: shelf posts/braces and cartons,
a workbench with monitor, keyboard keys, toolbox, vise and coiled cable, drums,
a hand truck, a drawer cabinet, a plant and a fire extinguisher. Physical labels,
material differences, lights and shadows provide visible detail. Navigation markers
and the operator grid are hidden from this camera. Sensor/collision geometry uses
conservative bounding boxes, so open shelving and space under benches are not
navigable. High lights and the doorway lintel are above the fixed flight plane.

The workshop's `module3-720p` profile records 1280 × 720 at requested 15 fps and
2.5 Mbit/s, and resizes selected snapshots to 960 × 540 JPEG at quality .85. The
200 kB inference-image bound and 1 MiB video-chunk bound remain enforced. Its
41° vertical field of view approximates the standard Camera Module 3, with ideal
optics; lens distortion, autofocus, blur, exposure and physical stream quality are
not modeled. The doorway inspection stands farther back to preserve context with
the narrower view. Legacy scenes retain 320 × 240, 75° vertical FOV and 10 fps.

A third, independent image call produces `object-survey-v1`: a summary, up to four
visible-object descriptions and uncertainty. It has no environment names, object
catalog or expected labels in its prompt. The workshop's overall inspection deadline
is 18 seconds; every individual call remains limited to six seconds. Range updates
and operator cancellation run throughout. Descriptions are escaped in HTML and are
recorded observations, not verified object inventories. Bounded policy decisions
still use the separate center classification, not unrestricted survey prose.

## Simulator and planner

The seed chooses static boxes in a bounded 12 × 10 × 3 m room. Named warehouse
and connected-room environments add fixed inspection poses and an obstructed
passage variant. Checkpoints are operator-authored mission inputs, not discovered
obstacle positions. Flight is 2.5D:
fixed 1.4 m altitude, ideal pose, ideal planar range scans. The range simulator
intersects 72 rays with boxes/walls to 3 m and quantizes returns to 4 cm. Mapping records unknown/free/occupied
0.5 m cells. The planner uses only that observed grid, inflates observed obstacles
by requiring all neighboring cells to be observed free, and uses breadth-first search over four-connected cells to
prefer unvisited frontiers. Ground-truth geometry belongs to the renderer, sensor
simulator, and last-resort collision check, not the route planner.

Motion is limited to 0.6 m/s and uses 1 m/s² acceleration/braking. Forward ranges
must exceed radius + clearance margin + reaction travel + braking distance.
Side rays also protect the swept disc during turns, and routes are revalidated
after every scan. Stale/unavailable ranges stop the mission; the simulator also rejects proposed
positions violating clearance. This check covers small bounded kinematic steps,
not a general continuous collision proof for arbitrary dynamics. More than 20
obstacle stops ends the run. Motion pauses every five seconds for camera inspection.

A fresh episode/ticket-bound camera image is recorded before inference. The model
may continue, request one additional left/right view per stop, hold, or finish.
It does not receive ground-truth boxes/map labels or command coordinates. Patrols
visit three configured checkpoints (four in the workshop); the model cannot finish the whole patrol from
one view. Unreachable checkpoints yield a partial mission after return.

`app/navigation.py` owns the geometry-free observed map and velocity supervisor.
`adapters/kinematic.py` owns ideal vehicle pose/motion; `sim/recon_world.py` owns
sensor geometry. This separation prepares for another backend, but recon still
instantiates the kinematic adapter: a shared PX4 indoor adapter is not implemented. Twelve
observations request a return via observed space. Failure to find a return route
or the 180-second mission deadline stops motion and records failure.

Range supervision runs while inference waits. Browser/camera loss stops within
the two-second lease; sensors older than 350 ms stop motion. Operator pause/end
cancels pending inference. No automatic continuation follows pause. The global
launcher watchdog detects a stalled app independently. These bounded stop actions
are virtual; they are not validated physical landing/recovery behavior.

## Evidence and limits

The browser renders at most 20 fps. Legacy scenes record the 320 × 240 onboard canvas
at requested 10 fps / 400 kbit/s; the workshop uses the detailed profile above. Encoding is browser-dependent. At most three upload
chunks are queued; each chunk is limited to 1 MiB and must arrive in sequence.
Overflow or upload failure ends the mission and does not mark the recording
complete. Finalization happens only after encoder flush and all uploads finish.

Evidence includes world seed/geometry, selected images, model outputs, pose/event
records, video chunk receipt timestamps and summary. HTML reports combine video,
selected images, approximate browser-clock seek positions, map, trail and unreached
checkpoints. Run history survives app restarts. A matching completed local-Qwen
patrol supplies the previous viewpoint classification, or its saved image for
independent reclassification. Misaligned viewpoints are marked not assessed.
Comparison errors remain model errors, never permission to enter blocked space. The shared recorder enforces
a 1 GiB cap across runs without deleting old evidence. Process logs are bounded
separately at 8 MiB. No bulk decoded-video queue is retained in Python.

Observed-map fraction is a range-sensor mapping metric. It is not visible-surface
camera coverage, object recognition accuracy or a claim that the space is fully
surveyed. Position uncertainty, noisy sensors, dynamic obstacles, exact video/pose
clock alignment, recon aircraft dynamics and sustained native Mac resource acceptance
remain future validation work. Tests using local HTTP stubs prove contracts, not
Qwen perception. Native Gazebo/PX4 remains a separate legacy gate integration.

## Camera realism bay

`realism` extends the workshop with PET bottles, a wheeled chair, a safety cone
and physical bench clutter. Scanned CC0 concrete maps are loaded from local assets;
mission start is disabled until they finish. `scene-realism.js` owns the new mesh
assets; `camera-effects.js` applies a deterministic GPU pass before the camera
canvas is displayed, encoded as video or resized to a model JPEG. The profile
stores the 10-degree downward pitch, 720p video / 960×540 JPEG dimensions, quality
and named exposure/blur/noise/vignette/distortion/glare/shift settings. Effects
are synthetic image stress, with fixed seeded noise/shift, not measured shutter,
rolling-shutter, vibration or automatic exposure behaviour.

The model receives image bytes and generic perception/report prompts; authored
scene kinds, evaluation labels and expected objects are never prompt inputs.
`render-realism-cases.cjs` captures the production camera in a read-only status
fixture and records image hashes, world/pose inputs and renderer source snapshots.
Use the frozen reliability evaluator for actual inference. These cases are
explicitly development data from one virtual site. Condition changes cannot
reuse another condition's patrol baseline.

Observed-map inflation uses the vehicle radius plus margin and range quantization
against cell bounds. Distant diagonal cell corners do not close an otherwise
observed passage. Unknown and occupied adjacent cells still block planning, and
the independent fresh-range swept-disc check supervises every move.

The realism bay's passage checkpoint declares the operator's inspection task
`passage`. That task asks whether the central doorway is blocked, returns a
bounded boolean/null assessment and maps null to uncertainty. It does not receive
scene geometry, object names or the expected open/blocked answer. Other points
keep the existing center inspection and full-frame object survey. Task choice is
recorded before inference in camera-test manifests (`inspection_task`, default
`center`) and in the patrol world/checkpoint configuration. The full processed
JPEG remains the input; the experimental crop method was rejected after losing
doorway context. Previous baseline assessments are recomputed when the inspection
version differs.

Map evidence is bounded and reversible: each beam contributes one hit/free update
per cell, so later clear observations can remove an isolated quantized corner hit.
The planner completes the last approach when already inside the home cell. If a
coarse-map disconnection still prevents return, recon reverses the actual recorded
trajectory (only collinear segments are combined). Every recovery move uses the
same fresh-range swept-disc supervisor; a blocked recovery stops the mission.
`return_recovery_used` is saved in the summary. This depends on the sandbox's ideal
pose and does not establish recovery with localization drift or real sensors.
