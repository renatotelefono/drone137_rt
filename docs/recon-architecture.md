# Recon lab implementation

The Python aiohttp application (`--mode recon`, the default) owns `ModelManager`
and `Recon`. Plain JavaScript renders the scene with vendored Three.js and sends
camera JPEGs and bounded MediaRecorder chunks to loopback HTTP endpoints. A
separate launcher process monitors app health and owns shutdown. All control POSTs
require a custom local header; Host must be localhost/127.0.0.1, and CORS is not
enabled. The app does not expose a physical drone transport in recon mode.

## Model manager

One supported public Qwen3-VL-2B GGUF and matching projector, one immutable
manifest, one operation at a time, one owned llama-server and one inference request.
`ModelStore` resolves official metadata, enforces fixed filenames, uses advisory
installation locking, preserves resumable partials, validates response ranges,
checks exact byte sizes/SHA256, and renames verified files atomically. It refuses
missing hashes, incompatible manifests and corrupt installed files. The manifest
pins the first resolved commit; upstream changes do not silently replace it.

The pinned llama.cpp runtime runs on loopback with context 2048, one parallel slot,
two CPU threads, and Metal offload on Apple Silicon. Requests are capped at 128
output tokens, six seconds and 64 KiB response data. Timeout/cancellation
quarantines the client because closing HTTP does not prove backend cancellation.
A stop/start creates a fresh owned server. Model operations are blocked during
missions; no automatic scripted fallback occurs.

## Simulator and planner

The seed chooses static boxes in a bounded 12 × 10 × 3 m room. Flight is 2.5D:
fixed 1.4 m altitude, ideal pose, ideal planar range scans. The range simulator
samples 72 rays to 3 m with 4 cm increments. Mapping records unknown/free/occupied
0.5 m cells. The planner uses only that observed grid, inflates observed obstacles
by neighboring cells, and uses breadth-first search over four-connected cells to
prefer unvisited frontiers. Ground-truth geometry belongs to the renderer, sensor
simulator, and last-resort collision check, not the route planner.

Motion is limited to 0.6 m/s and uses 1 m/s² acceleration/braking. Forward ranges
must exceed radius + clearance margin + reaction travel + braking distance.
Stale/unavailable ranges stop the mission; the simulator also rejects proposed
positions violating clearance. This check covers small bounded kinematic steps,
not a general continuous collision proof for arbitrary dynamics. More than 20
obstacle stops ends the run. Motion pauses every five seconds for camera inspection.

A fresh episode/ticket-bound camera image is recorded before inference. The model
may continue, request one additional left/right view per stop, hold, or finish.
It does not receive ground-truth boxes/map labels or command coordinates. Twelve
observations request a return via observed space. Failure to find a return route
or the 180-second mission deadline stops motion and records failure.

Range supervision runs while inference waits. Browser/camera loss stops within
the two-second lease; sensors older than 350 ms stop motion. Operator pause/end
cancels pending inference. No automatic continuation follows pause. The global
launcher watchdog detects a stalled app independently. These bounded stop actions
are virtual; they are not validated physical landing/recovery behavior.

## Evidence and limits

The browser renders at most 20 fps and records the 320 × 240 onboard canvas at a
requested 10 fps / 400 kbit/s. Encoding is browser-dependent. At most three upload
chunks are queued; each chunk is limited to 1 MiB and must arrive in sequence.
Overflow or upload failure ends the mission and does not mark the recording
complete. Finalization happens only after encoder flush and all uploads finish.

Evidence includes world seed/geometry, selected images, model outputs, pose/event
records, video chunk receipt timestamps and summary. The shared recorder enforces
a 1 GiB cap across runs without deleting old evidence. Process logs are bounded
separately at 8 MiB. No bulk decoded-video queue is retained in Python.

Observed-map fraction is a range-sensor mapping metric. It is not visible-surface
camera coverage, object recognition accuracy or a claim that the space is fully
surveyed. Position uncertainty, noisy sensors, dynamic obstacles, exact video/pose
clock alignment, realistic aircraft dynamics and native Mac resource acceptance
remain future validation work. Tests using local HTTP stubs prove contracts, not
Qwen perception. Native Gazebo/PX4 remains a separate legacy gate integration.
