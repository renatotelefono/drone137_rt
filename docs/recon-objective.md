# Current objective: reliable autonomous visual reconnaissance

The requested deployment scope now includes **indoor workshops, warehouses,
building perimeters, flat fields and hillsides**. Establish reliability for each
domain independently using the [reliability protocol](reliability-protocol.md).
Indoor reconnaissance remains the first implementation path. None of the five
domains is qualified for physical deployment; outdoor terrain and flight behavior
are not implemented by the current room simulator.

The user's clarified first objective is to let one drone autonomously look around
a confined space, respond to objects and obstacles, and gather video information.
This replaces the fixed two-gate inspection as the product's first mission.
The original uploaded brief remains a historical planning reference.

## Desired operator experience

The operator defines the permitted space, recording budget and return point, then
starts a reconnaissance mission. The drone explores reachable areas, chooses useful
viewpoints, records video, and adjusts its route when it encounters objects or
blocked passages. It finishes with footage and an account of what was observed,
what remains unseen and why it stopped. Pause and land remain operator overrides.

"Respond to objects" initially means changing observation or navigation behavior:
stop and look, turn the camera/vehicle, inspect from another angle, keep clearance,
go around a blockage, or mark an area inaccessible. The objective is visual
information collection. Physical object interaction is outside this first scope.

Success is useful visual coverage, rather than merely completing a predefined route
or producing a classification for every object.

## Starting assumptions, not confirmed hardware requirements

- Begin virtually with one small room or connected room-like space and static
  obstacles. Randomize layouts, obstacles, lighting and mission seeds. Dynamic
  obstacles and larger spaces follow after the static case works.
- The vehicle initially knows its allowed operating boundary and return point.
  Treat the interior as incompletely observed during the exploration test.
- Keep inference local on the nearby computer and retain the lean resource target.
  Re-measure it with mapping, rendering and recording enabled.
- Use Python for mission/planning services and plain JavaScript/Three.js for the
  browser simulator. No TypeScript requirement is introduced.

## Required capabilities

| Capability | Required behavior | Current state |
| --- | --- | --- |
| Rendered environment | Seeded enclosed scenes, obstacles, onboard camera and operator view | Implemented: seeded rooms, warehouse, connected rooms and detailed workshop with 720p camera |
| Position and geometry | Estimate pose and nearby free/occupied space; track uncertainty and sensor freshness | Ideal pose and planar range sensing implemented; real estimation/noise/uncertainty missing |
| Exploration | Select reachable viewpoints that reveal unseen areas, with finite mission and return budgets | Observed-grid exploration and bounded return implemented in browser sandbox |
| Route planning | Clearance-aware paths, complete-segment collision checks and replanning when a passage is blocked | Observed-grid BFS, obstacle inflation and braking supervision implemented; full 3D planning missing |
| Object response | Use image observations to request useful additional views or adjust inspection priorities | Actual local Qwen tested; workshop adds whole-image object surveys, with broader accuracy still pending |
| Video recording | Bounded, timestamped video segments tied to pose, observations and mission events | Browser video, JPEG observations and receipt/pose events implemented; exact exposure sync missing |
| Flight execution | Follow validated local routes and handle navigation/link failure in confined conditions | Native Qwen gate flight passed; indoor planner still uses kinematics |

A vision-language model can interpret scenes and suggest what deserves another
look. Collision avoidance and position control need timely geometric sensing and
their own control loop; they cannot wait for a multi-second model response.
A single RGB camera and Qwen do not by themselves provide reliable obstacle
distance, localization or a complete navigation stack.

## Virtual development path

1. **Three.js reconnaissance sandbox.** Build seeded rooms/obstacles, a rendered
   onboard camera, simple bounded vehicle motion and mission playback. This tests
   exploration and information gathering; it is not a flight-dynamics validation.
2. **Sensor and map interface.** Begin with explicitly labelled ideal-pose and
   simulated depth/range sensors. Provide only their observations to the planner.
   Later introduce noise, occlusion, delay and loss. Keep hidden scene geometry,
   random seeds and ground-truth coverage in the evaluation harness.
3. **Autonomous exploration and recording.** Maintain a local occupancy/coverage
   map, select viewpoints at the boundary between observed and unobserved space,
   plan routes around obstacles, and record bounded video with synchronized events.
   Test blocked passages, dead ends, unreachable targets and returning to the pad.
4. **Actual local vision.** Prove the selected model can interpret rendered images
   and cause a useful change of viewpoint. Use the same geometric navigation
   checks for scripted and model-directed observation requests.
5. **Flight and sensor validation.** Run representative scenarios through
   PX4/Gazebo with rendered sensing, aircraft dynamics and the intended navigation
   interface. Demonstrate loss/recovery behavior and complete Mac resource tests.

Randomize worlds and mission conditions, while keeping navigation deliberate and
reproducible. Do not generate arbitrary motor commands or unconstrained flight
segments as a substitute for exploration.

## Confined-space implications

An indoor mission cannot assume GPS. The present global-coordinate
`goto_location` adapter is insufficient to establish indoor navigation support.
Select and test local positioning, likely using visual-inertial/depth sensing,
and the corresponding PX4 local-navigation interface. If Offboard control is
chosen, implement and test its independent setpoint/heartbeat-loss behavior.

The earlier outdoor 450–500 mm aircraft and camera shortlist are provisional
historical candidates. Confined-space dimensions, clearances, positioning sensors
and communication requirements must drive a fresh hardware suitability review.
Passing the old gate route does not open the new reconnaissance hardware gate.

Video recording also changes the resource requirements: inference still uses
selected fresh frames, while recording has a separate bounded stream. Choose and
measure encoding settings and storage limits instead of retaining every decoded
frame or claiming the existing JPEG recorder already records video.

## Acceptance evidence

The executable offline evaluator now freezes data/model/pipeline hashes, keeps
site-separated splits, groups adjacent frames into encounters, records errors and
tracks reused held-out sites. It grades labelled visual facts separately from
navigation. The initial public real-camera smoke test exposed a missing object;
it does not supply independent target-site or target-camera evidence. See
`reliability-validation.json` and the collection protocol for the remaining gates.

Use repeatable held-out seeds and report successful and failed episodes. Measure
reachable-space/view coverage, unseen regions, clearance violations/collisions,
route length, redundant revisits, interventions, recording continuity and
camera/pose timestamp alignment. Include changed routes caused by obstacles and
by actual image observations. Define coverage from the camera's view and occlusion,
not merely the vehicle's visited positions.

Test sensor loss, localization uncertainty, unavailable return paths, exhausted
mission/storage budgets and operator overrides. Distinguish ideal-sensor tests,
rendered-model tests, flight-dynamics tests and eventual physical evidence.
The initial scripted browser workflow is exercised on Linux (see validation.md).
Actual Qwen has passed bounded local tests (see validation.md). Sustained Mac
resources, localization, camera-coverage and physical-flight acceptance remain open. Map-observed fraction in the current GUI is
range-sensor coverage, not a camera coverage metric.
