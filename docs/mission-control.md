# Virtual mission control

Open `/control` on the local recon service. `/` retains the single-aircraft lab.
The dashboard is plain JavaScript and SVG for the operational map, with two
Three.js onboard camera renderers. Both use the existing scene assets, synthetic
camera effects, MediaRecorder and image/video evidence path.

## Operator workflow

1. Start the local model. Initial model/runtime setup is available in Recon lab.
2. Load a realism bay, workshop, warehouse or connected-room site, including seed,
   variant and supported camera conditions.
3. Choose the whole site, a bay, or drag an inspection rectangle. Coordinate fields
   provide the same selection without dragging. At least one authored viewpoint
   must be inside the area.
4. Write a brief and choose one or both aircraft. Generate a plan with actual local
   Qwen inference. The model selects `inventory`, `passage`, `changes` or
   `unsupported`, supplies a visual focus and summarizes its interpretation.
5. Review the interpreted task and deterministic viewpoint assignments, then launch.
   Changes compares independently classified camera centers only. Without a matching
   completed baseline, that flight collects baseline evidence; it cannot assess change.
6. Review live findings and each aircraft's video/image report. The fleet report links
   both flights and preserves the brief, area, assignments and completion states.

This is a virtual indoor dispatch product. The selected area restricts viewpoint
locations, not every pixel viewed or the transit route. Drones use the existing
observed-range map for transit and return. The visual focus goes to the object
survey; it cannot change speed limits, route supervision or issue motor commands.
Outdoor missions, arbitrary positions and physical transport are not supported.

## Controller and evidence contracts

- `app/fleet.py` owns two distinct `Recon` instances, camera leases, one pending
  draft and one current fleet mission. The original lab shares its model manager.
- Only one aircraft occupies the site at a time. Other aircraft are logically
  docked outside it. This is sequential dispatch, not collision-aware swarm flight.
- A valid draft expires after ten minutes and is consumed on launch. Its generation
  must match the loaded site. Launch requires a fresh rendered/recordable camera for
  every assigned aircraft from the launching dashboard session.
- Each flight has a distinct browser camera client, episode UUID, observation
  tickets, image files, video sequence and report. Cross-aircraft camera/video
  uploads are rejected. The worker cannot directly start a flight.
- The scheduler waits for return and finalized video before dispatching the next
  aircraft. Failure, pause, partial completion, camera loss or missing final video
  cancels the remaining queue. The existing camera-loss motion deadline is 2 seconds;
  evidence finalization has a 10-second grace period.
- Return cancels the queue and requests observed-route return. It lets an ongoing
  bounded inference finish to avoid quarantining the model. Stop ends motion and
  cancels inference, which may require restarting the local model. Both controls
  are labelled in the dashboard; a stopped/failed aircraft requires a site reset.
- Reset clears the virtual aircraft and camera leases; it retains prior evidence.
  Browser reload does not silently take over an active camera stream. After a
  connection loss, stop/reset and launch a new reviewed mission.
- Per-flight summaries retain `inspection_points` and `task_context` with the fleet
  mission ID, drone ID, operator instruction, objective, focus and area. Baselines
  require the same assigned viewpoint set, scene/camera settings and aligned pose.
- Parent fleet summaries use `mode=virtual-fleet-mission` and link child episodes.
  Both share the existing 1 GiB evidence budget. No old evidence is auto-deleted.
- The queue is not resumed after application restart. Normal shutdown records an
  interrupted mission. A report left by a hard crash shows its last recorded state,
  not live telemetry. Individual completed reports remain in dashboard history.

## Local API

All mutations require the existing local host check and
`X-Drone137-Control: local`. No remote or physical transport is exposed.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/fleet/status` | Site, model, fleet mission and both aircraft |
| `POST /api/fleet/site` | Load/reset site while idle |
| `POST /api/fleet/plan` | Interpret `instruction`, validate `area` and `drones` |
| `POST /api/fleet/launch` | Dispatch reviewed `draft_id` for `session` |
| `POST /api/fleet/return` | Cancel queue and return active aircraft |
| `POST /api/fleet/stop` | Cancel queue and stop virtual motion |
| `GET /api/fleet/drones/{id}/status` | Isolated renderer/controller state |
| `POST /api/fleet/drones/{id}/ready` | Generation-bound camera heartbeat |
| `POST /api/fleet/drones/{id}/camera` | Episode/client/ticket-bound JPEG |
| `POST /api/fleet/drones/{id}/video` | Ordered episode/client-bound video chunks |
| `POST /api/fleet/drones/{id}/video-finalize` | Finalize that aircraft's stream |
| `POST /api/fleet/drones/{id}/land` | Camera encoder failure stop; requires owner |

Run `scripts/check-mission-control.cjs` with optional local Playwright/Chrome tooling
installed to exercise actual local-model intent, operator stop, two aircraft,
camera observations, video playback/seek and responsive dashboard layout. It
requires an idle service and the existing downloaded model/runtime. Unit/HTTP
tests are in `tests/test_fleet.py`. See `validation.md` for recorded results and
limitations; tests on this synthetic site do not establish real-world reliability.

Next flight-control work is local-pose/range integration with PX4 for one indoor
aircraft. Simultaneous flight then requires actual shared-world peer geometry,
separation supervision, conflicting-route handling and independent failsafe tests.
