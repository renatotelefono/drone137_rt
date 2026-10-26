# Docking: return, align, land, charge

Status: implemented in simulation on 25 October 2026. The hardware it targets is dock A in
`hardware/esp32/indoor/scout-110-bench/dock/` and carrier prototype B.

## Implementation and results

| Piece | Where |
| --- | --- |
| Tag detection, pose in the dock frame, synthetic tag renderer | `app/dock_tags.py` |
| The `dock` phase: return, acquire, align, descend, settle, docked | `app/docking.py` |
| Dock registry, dock controller client, API | `app/docks.py`, `app/dock_api.py` |
| Simulated dock: electronics, contact, tag camera, vehicles | `sim/dock_world.py` |
| Mission runtime: plan with a dock, `POST /api/mission/dock`, assistant actions | `app/mission_runtime.py`, `app/mission_assistant.py` |
| Gate | `scripts/qualify_docking.py`, results below |
| Geometry constants shared by all of the above | `config/dock-a.json` |

The dock frame in software is forward-left-up with the origin at the pocket centre; the
hardware drawings call the same axes +Y, −X, +Z.

Gate, first-order vehicle (`docs/docking-validation-kinematic.json`): 20 of 20 dockings
from the return gate's error distribution ended on the dock at the first attempt, worst
touchdown 0.8 mm and 0.22°, no stand contact, mean
27 s from the return gate to contact, estimate re-anchored within
9 mm of the truth.

Gate, Rapier plant (`docs/docking-validation.json`, the service-owned micro-physics in
real time, benchmark scene with its 0.8 m/s draft, camera latency 120 ms and every ninth
frame dropped): 20 of 20 dockings from the return gate's error distribution ended on the
dock at the first attempt, worst touchdown 12.0 mm and 0.18°, no stand
contact, mean 25 s from the return gate to contact, estimate re-anchored within
10 mm of the truth. Before the integral term the same plant touched down 6 to
16 mm short of the centre on each of six runs (`.local/validation/docking-rapier-before-integral.log`
on the development Mac).

Not done: the dock controller firmware and the carrier STAT input are hardware work;
the Three.js mission renderer does not draw the tag column (the dock phase in simulation
renders its own frames from the plant's pose); the Watch cluster's sortie scheduler is
not written.

## Why a dock

A dock removes the only manual step left in a mission, the battery swap, and gives the
software a fixed point to come home to. The facts that shape it, from the Scout's own
files: 63 g all-up in the simulation profile, a 480 mAh 1S cell, a forward camera at
960 × 540 pitched down 10°, a return-to-start gate of 0.4 m. Flight per charge is about
5 to 7 minutes; a charge at 500 mA takes about 1.2 h, nearer 1.5 h with the charger's
thermal fold-back. One Scout on one dock therefore gives about 5 minutes of flight per
hour. The Watch cluster becomes scheduled sorties from the dock; continuous presence in
a site needs three or four aircraft sharing docks.

## Frames and constants

- **Dock frame.** Origin at the pocket centre on the pocket floor, +Y toward the tag
  stand, +Z up. The docked aircraft is at the origin with yaw 0: its camera faces the
  tags.
- **Tag stand.** The tag plane is at Y = +203 mm. Three tag36h11 tags on one vertical
  column: 40 mm with centres 57 and 117 mm above the pocket floor, and 60 mm centred
  180 mm above it, all centred on X = 0; the quiet zones are 5 mm apart. The lowest tag centre is at the docked camera
  height. Tag ids are 3k, 3k+1, 3k+2 for dock k, lowest first, so a detection names
  its dock.
- **Camera in the aircraft.** 12 mm forward of the aircraft centre and 57 mm above the
  feet, pitched down 10°. Docked, the tag plane is 191 mm from the lens.
- **Visibility,** from `dock/clearance-checks.json`: with the profile's 41° vertical
  field of view, at least one tag is fully in view for every camera height from 16 mm
  below the docked height to 175 mm above it, with no gap. At 1 m a 40 mm tag is 29 px
  wide and the 60 mm tag 43 px. Acquisition is therefore reliable from about 1.2 m for
  the big tag and 0.8 m for the small ones.
- **Capture.** The funnel takes a touchdown error of ±25 mm in X and Y and sets the
  final yaw to the nearest multiple of 90°. The software's job is to arrive within
  ±20 mm facing the tags.

## Registry

A dock is a site object, versioned like an airframe profile.

```
docks(id, place_id, revision, pose_place {x, y, yaw}, tag_ids [3], tag_sizes_m [3],
      tag_plane_y_m 0.203, geometry 'dock-a@1', charge_policy {storage_v 3.80,
      full_v 4.20, max_current_a 0.7, max_pad_c 45, max_charge_s 10800},
      link {host, port, certificate_sha256, pairing_credential_ref}, created_at)
```

- **Registration** happens with the aircraft placed in the dock by hand: `POST
  /api/docks/register` stores the current place-frame pose of the aircraft as the dock
  pose. From then on every landing on the dock closes the loop: when the dock reports
  contact, the VIO pose is reset to the dock pose, and the dock pose is the origin of
  the place map for later visits.
- The dock controller is reached like an aircraft: pinned HTTPS on the private network,
  one certificate and pairing credential per dock, local only. Addresses and
  credentials never reach the model, as for aircraft.

## Dock controller

A XIAO ESP32-C3 in the bay with an INA219, an NTC under the floor and a P-MOSFET on
the 5 V line.

| Endpoint | Returns or does |
| --- | --- |
| `GET /status` | `{mode, supply_v, pin_current_ma, pad_temp_c, contact: bool, fault: null or text, uptime_s}`; `contact` is true when pin current exceeds 20 mA with 5 V on, or when the aircraft reports STAT low |
| `POST /mode {mode}` | `charge`, `storage`, `off`. The ground computer sets it; the dock never decides on its own except for faults |

Dock-side rules, enforced without the ground computer:

- 5 V off when pin current exceeds 0.7 A, pad temperature exceeds 45 °C, or a charge
  has run for 3 h; `fault` names the cause and stays until `POST /mode` clears it.
- `storage`: 5 V on only while the last reported cell voltage is below 3.75 V, off once
  it reaches 3.85 V. `charge`: 5 V on until the aircraft reports STAT high after at
  least ten minutes of charging, or the timeout. `off`: 5 V off.

## Aircraft firmware

- D2 / GPIO3 with the internal pull-up reads STAT: low while charging. The status
  message gains `charge: {stat: 'charging' | 'idle', cell_v}`. `idle` covers both
  complete and no 5 V; the ground computer knows which from the dock's mode.
- Arming is refused while STAT is low.
- Docked and idle, the aircraft enters deep sleep and wakes every ten minutes for
  twenty seconds to report the cell voltage and accept a `prepare` command, which keeps
  it awake. The ground computer sends `prepare` fifteen minutes before a scheduled
  sortie, after switching the dock to `charge`.

## Flight procedure

A new mission phase `dock`, after the existing return. All setpoints go through the
existing control channel: roll and pitch up to ±0.26 rad, yaw rate up to ±1 rad/s,
collective up to 0.8, each valid 250 ms. The camera runs at 2.5 Hz, so every loop below
issues one small move per frame and waits for the next frame before the next move.

| State | Does | Leaves when | Abort |
| --- | --- | --- | --- |
| **return** | Existing return navigation to the approach point: dock frame (0, −0.60 m, +0.30 m), yaw 0 | Within the 0.4 m return gate | As today |
| **acquire** | Detect tag36h11 in each frame; accept a detection whose id belongs to this dock | A tag seen in 2 consecutive frames | No tag in 10 s: look 30° left, then right; back away 0.3 m and down to hover height, look left and right again; then land in place and report `dock not found` |
| **align** | From the tag corners and the calibrated intrinsics, solve the camera pose in the dock frame (PnP; the tag column's layout is known). Command lateral and height moves toward hover point (0, 0, +0.15 m), yaw toward 0, at most 0.10 m/s, 0.4 rad/s | Error below 20 mm in X and Y, 30 mm in Z, 5° in yaw, held for 3 frames | Tag lost 3 frames: back to acquire. 60 s without converging: land in place, report |
| **descend** | Descend at 0.05 m/s keeping X, Y, yaw servoed on the tag | Dock reports `contact`, or height estimate below 0 | Tag lost above 60 mm: climb to the hover point, back to align. Tag lost below 60 mm: continue; the funnel captures ±25 mm |
| **settle** | Collective to zero, disarm, wait 2 s | Dock `contact` true and pin current above 20 mA | No contact within 5 s: the aircraft is probably at yaw 180° or outside the pocket; arm, climb to the hover point, back to align, at most twice, then report `docked without contact` |
| **docked** | Reset VIO to the dock pose; dock to `charge` or `storage` per schedule; aircraft to docked idle | — | — |

Height during descend comes from the tag solution, not from VIO, because VIO drift is
the reason the return gate is 0.4 m. Lateral and yaw errors likewise. VIO only bridges
frames. A bounded integral of the lateral error (0.6 per second, limited to ±40 mm)
cancels a steady plant offset: against the benchmark scene's 0.8 m/s draft the Rapier
plant otherwise touched down 6 to 16 mm short of the centre on every run.

### Tag detection

- Detector on the ground computer, CPU only, run on every frame while the phase is
  `dock`: tag36h11 with quad decimation 1 at this resolution. `cv2.aruco` with the
  `DICT_APRILTAG_36h11` dictionary is already available in the vision environment
  (OpenCV 4); `pupil-apriltags` is the alternative if its corners prove steadier.
- Pose from `cv2.solvePnP` on all visible tags' corners at once, with the profile's
  intrinsics and distortion. Reject a solution whose reprojection error exceeds 2 px.
- The model never sees these frames for this purpose; the detector is deterministic.

### Numbers to carry into the implementation

| Quantity | Value | Source |
| --- | ---: | --- |
| Approach point | (0, −0.60, +0.30) m, yaw 0 | With a 0.4 m arrival error the aircraft is 0.2 to 1.0 m from the column; the whole column stays in view at the near end and the tags stay above 29 px at the far end |
| Hover point | (0, 0, +0.15) m above the pocket floor | 150 mm of guided descent, three seconds at 0.05 m/s, about seven frames |
| Touchdown tolerance | ±20 mm, 5° | Funnel capture ±25 mm |
| Frame rate | 2.5 Hz | Aircraft camera poll |
| Contact threshold | 20 mA at 5 V | Below the charger's trickle current, above leakage |

## Scheduling and the wizard

- The Watch cluster gains fields `sortie_every_min` and `dock_id`; a mission with a dock
  ends in the `dock` phase instead of return-and-land, and the next sortie is created
  when the dock reports STAT high or the storage policy is satisfied and the schedule
  says so.
- Assistant actions: `dock status` (immediate), `return to dock` (confirmation gate,
  like every launch).
- API: `GET /api/docks`, `POST /api/docks/register`, `GET /api/docks/{id}/status`,
  `POST /api/docks/{id}/mode`, `POST /api/missions/{id}/dock`.

## Verification before hardware

1. **Geometry:** `dock/generate_dock.py` and `check_mechanics.py` pass; they do today.
2. **Emulator:** add dock A and its tag column to the simulated site with the real
   geometry; render tags into the 960 × 540 frames. Gate: from 20 starts drawn from the
   return gate's error distribution, 20 end inside ±20 mm and 5° before contact, with no
   contact with the stand, and the VIO reset after `docked` leaves a pose error under
   20 mm against the simulation truth.
3. **Detector:** tag pose error under 5 mm and 1° at 0.2 to 0.6 m on synthetic frames
   with the profile's distortion and JPEG quality; detection rate above 95 % per frame
   at the hover point.
4. **Bench, with hardware:** pin and strip contact resistance under 100 mΩ, charge
   current and carrier temperature over a full charge, dock fault cut-offs tripped on
   purpose.
5. **First physical docking:** aircraft placed by hand, then lowered by hand into the
   funnel from 50 mm off-centre, then the guided descent from the hover point only, then
   the full procedure. Each step keeps its recordings as evidence.

## Out of scope for dock A

Charging more than one aircraft per dock, inductive charging (version 2 changes only
the dock's 5 V source and adds a receiver under the cradle), outdoor use, and any dock
without the tag stand: the forward camera cannot see a floor marking.
