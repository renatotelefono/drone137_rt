# Virtual mission control

The new `/control` interface is documented in [mission-runtime.md](mission-runtime.md).
This document describes the earlier kinematic dashboard at `/control-legacy`.
`/` retains the single-aircraft lab.
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

## Mission wizard

The console opens with a **Start here** panel that proposes the four mission
clusters from `config/mission-templates.json` and ranks them by what the place
memory and the mission state make sensible:

| Cluster | Capability | Proposed when | Launch today |
| --- | --- | --- | --- |
| Map an unknown space | explore | First whenever no mapped place exists; always offered for a new layout | Simulated exploration flight started from the console through `scripts.run_blind_test`; one at a time, same gates as a qualification flight |
| Audit a known space | seek | First once a mapped place exists; needs the local model | Composes the brief for the qualified target and hands it to the reviewed plan and launch |
| Watch for changes | seek | When a place has a completed mapped visit as baseline | Proposed and recorded only; needs map reuse on a later visit |
| Find something in an unknown space | explore + seek | Always last | Proposed and recorded only; not implemented |

A free-text line is classified deterministically to open the matching template;
the model's intent step still decides what is flown. Each template carries the
gate its flight is scored against, and the chosen template id travels with the
plan into the run record (`plan.template`) and the history list, so results can
be read per mission type. Unsupported targets in an audit list are recorded as
warnings, never silently relabelled.

## Ask the console

Above the Start-here panel, an ask box accepts a typed or dictated request such
as "connect to the workshop scout", "what drones are paired", "check the
extinguishers" or "map a new layout". The local model maps the request to one
action from a fixed list (`app/mission_assistant.py`): connect, disconnect, show
camera, list aircraft, status, start model, suggest mission, compose an audit
brief, start an exploration flight, stop, return home, reduce thrust, cut motors,
or unknown. The service resolves the spoken aircraft name against the pairing
registry and refuses ambiguity by listing what is paired. Reads, connections and
everything that stops motion run at once; starting an exploration flight is
proposed and waits for a click; launching a mission is not an action here and
always goes through the reviewed plan. The model never sees an address,
certificate or credential; it sees aircraft names, kinds and connection states.
Dictation uses the browser's own speech recognition, which may send audio off
the computer; typing stays local. Verified live on 25 October against the paired
protocol emulator: "please connect to the scout demo drone" connected it.

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
| `GET /api/wizard/templates` | The mission template catalogue |
| `GET /api/wizard/suggestions?brief=` | Ranked proposals from place memory, model and mission state; optional brief classification |
| `POST /api/wizard/compose` | Turn a template and its fields into the brief, area and template tag the planner accepts |
| `POST /api/wizard/explore` | Start one simulated exploration flight (`place`, `seed`); refused while a mission or flight is active |
| `GET /api/wizard/explore/status` | State, observations, score and last log line of that flight |
| `POST /api/assistant/ask` | Interpret a typed or dictated request as one console action and run it if it is immediate |
| `POST /api/assistant/confirm` | Start the proposed exploration flight, or the docking approach, after the operator's click |
| `GET /api/docks` | Registered docks (poses, tag ids, charge policy; link credentials never included) |
| `POST /api/docks/register` | Register or re-pose a dock from the aircraft's current estimate, or from an explicit `pose` |
| `GET /api/docks/{id}/status` | The dock controller's status (mode, 5 V, pin current, pad temperature, contact, fault) and recent landings |
| `POST /api/docks/{id}/mode` | Set the dock to `off`, `charge` or `storage` |
| `POST /api/mission/dock` | End the active mission by landing on the dock named in its plan (`docs/docking.md`) |
| `POST /api/aircraft/{id}/manual/start` | Take manual control of a connected aircraft: claims the exclusive session and arms; refused while a mission is active |
| `POST /api/aircraft/{id}/manual/input` | One stick sample (roll, pitch, yaw rate, thrust), clamped to the manual envelope; the service streams setpoints at 20 Hz |
| `POST /api/aircraft/{id}/manual/land` | Land through the aircraft's bounded ramp and end the session |
| `GET /api/aircraft/{id}/manual` | Manual session state, last setpoint, input age and limits |
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

## Fly by hand

The **Fly by hand** panel in the console turns the keyboard (W/S pitch, A/D roll, Q/E yaw,
R/F thrust trim, Space lands) or a gamepad into attitude setpoints over the paired link, for
commissioning and for moving an aircraft by hand. The manual envelope is half the aircraft's
tilt limit (0.13 rad), yaw rate 0.5 rad/s and thrust 0.6. The service streams at 20 Hz over a pinned link of its own, so a sensor-monitor fault does not take the sticks away;
releasing the sticks levels the aircraft at the current thrust trim after 0.3 s, and no input
at all for 1.5 s lands it. Underneath, the aircraft's own 250 ms setpoint expiry and two-second
lease still apply, so a stalled browser also ends in the landing ramp. Manual control is refused
while a mission is active and while another aircraft is under manual control; the emergency
land and cut-motors buttons work throughout. The default board builds cannot arm, so on
hardware this needs the restrained-rig build; the protocol emulator accepts it and the tests
in `tests/test_manual_control.py` run against that emulator.
