# Aircraft that Drone137 expects to control

Drone137 is a ground-computer system. The Mac runs perception, mapping,
planning, the local vision-language model and Mission Control. The aircraft
keeps itself level, streams its camera and IMU, and executes short bounded
setpoints. Any aircraft that meets the contract below can be flown by the
program; aircraft that do not cannot, however capable they are on their own.

## The three ways an aircraft can be connected

| Path | Adapter | Aircraft class | Status |
| --- | --- | --- | --- |
| **Drone137 aircraft connection v1** | `hardware/esp32/connection.py`, `link_client.py` | Brushed micro quadcopters running the shared C++ controller on a XIAO ESP32-S3, or any board that implements [the link protocol](../hardware/esp32/link-protocol.md) | Primary path. Host side verified against the protocol emulator and the shared firmware; no physical aircraft flown yet |
| **PX4 over MAVSDK** | `adapters/mavsdk_drone.py`, `adapters/native_flight.py` | PX4 autopilot aircraft, used for the legacy outdoor gate mission with global waypoints on a Gazebo x500 | Experimental, simulation only. Indoor reconnaissance is not implemented on this path |
| **Virtual vehicles** | `adapters/kinematic.py`, `adapters/rapier_drone.py` | Ideal kinematic vehicle and the service-owned Rapier micro-quad physics model | Used for every qualification flight to date |

The reference aircraft for the primary path is the **Scout 110-B** bench
prototype in [the build package](../hardware/esp32/indoor/scout-110-bench/README.md):
a 110 mm guarded quadcopter, four brushed 8520 motors with 65 mm propellers,
one 1S 450 mAh pack, a XIAO ESP32-S3 Sense as flight controller and camera, and
an MPU-6050 on a rigid carrier. Its siblings in the
[indoor catalog](../hardware/README.md), Micro 90, Guard 110, Height 110 and
Split 110, share the same electronics and contract and differ in frame, guards,
an optional downward range sensor and a second controller board.

## What the aircraft must provide

- **Onboard stabilization.** The board's own estimator, rate loop and mixer
  keep the vehicle level. The ground never commands motors directly; it sends
  roll and pitch up to ±0.26 rad, yaw rate up to ±1 rad/s and a normalized
  collective up to 0.8, each valid for at most 250 ms on the aircraft clock.
- **Loss handling on the aircraft.** Missing setpoints start a bounded level
  attitude and throttle-reduction ramp and revoke control; an authenticated
  emergency server accepts `land` or `disarm` even when the control channel is
  stalled. Heartbeats never prolong thrust.
- **One forward-facing calibrated RGB camera**, JPEG frames up to 200 KB with
  verified capture metadata, polled at 2.5 Hz. VGA on the physical board,
  960 × 540 in simulation.
- **A six-axis IMU** with microsecond timestamps, gyro and specific force in
  forward-left-up body axes, continuous at 25 Hz or better with no gaps over
  20 ms, and a rigid, measured camera-to-IMU mounting.
- **Pinned HTTPS on a private network** with a per-aircraft certificate and
  pairing credential, separate camera, control and emergency ports, exclusive
  sessions with a two-second lease, and a battery voltage reading.

Nothing else is expected on board: no GPS, no depth sensor, no external
positioning, no map, no onboard model. Position comes from the camera and IMU on
the ground computer.

## The physical envelope the software assumes

The mapping and planning code carries explicit numbers that come from the
micro-quad class and are not parameters an operator changes in flight:

| Assumption | Value | Where it lives |
| --- | ---: | --- |
| Survey and transit height | 1.5 m | `scripts/explore_unknown.py` |
| Flight-volume clearance band | 1.35–1.65 m | `app/voxel_mapping.py` |
| Clearance radius around the guarded aircraft | 0.20 m plus half a grid cell | `app/voxel_mapping.py` |
| Map resolution | 0.15 m horizontal and vertical | `app/voxel_mapping.py` |
| Speed limit | 0.55 m/s | explorer and simulator |
| Mission deadline and battery return reserve | 600 s; loaded-voltage reserve for the observed return route | `scripts/explore_unknown.py` |

An aircraft larger than roughly 0.2 m in radius, flying at another height, or
unable to hover and translate slowly needs those values changed and every
qualification suite reflown. The current simulated airframe hypothesis is a
63 g aircraft; the Scout 110-B's as-built mass is still to be weighed.

## Where it is expected to fly

Confined indoor spaces: workshops, connected rooms and warehouses with static
obstacles, launched from a level floor with a clear 0.5 m patch. Building
perimeters, flat fields and hillsides are in the requested scope but are not
implemented by the simulator and have no qualification. Mission Control
dispatches aircraft one at a time into a leased airspace, so several aircraft
can be registered and docked, but this is sequential dispatch, not swarm flight.

## What is out of scope

- Closed commercial drones without an open control link. Drone137 needs either
  the link protocol or PX4 over MAVSDK; a vehicle that offers neither cannot be
  controlled.
- Fixed-wing or any aircraft that cannot hover.
- Onboard inference. An onboard computer was considered and rejected; all AI runs
  on the ground.
- Any physical flight at all until the commissioning sequence in
  [pre-hardware preparation](pre-hardware-six.md) has produced measured mass,
  thrust, current, calibration and timing for a specific airframe.
