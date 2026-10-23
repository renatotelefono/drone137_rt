# Drone137 aircraft connection, version 1

Status: ground adapter, protocol-only HTTPS emulator, SQLite pairing and
Mission Control connection/preview implemented. ESP32 flight firmware and
physical mission navigation are pending. This is not a
physical flight qualification. `link_protocol.py` is the executable device
state-machine specification; `link_client.py` is the asynchronous ground adapter.
The emulator explicitly advertises `kind=protocol-emulator`, static camera
imagery and stationary synthetic IMU samples. It has no flight dynamics.

## Network and pairing

Aircraft and ground PC share a local Wi-Fi network. No Internet or cloud service
is required. Each aircraft has its own HTTPS certificate and at least 256 bits
of random pairing credential. Pair through a trusted local provisioning step
(USB for hardware), retaining the exact SHA-256 certificate fingerprint on the
ground computer. Do not use a fleet-wide default password or disable certificate
verification. The adapter accepts only literal private/loopback IPv4 HTTPS
addresses, pins the certificate, disables redirects and ignores proxy variables.
Provisioned private keys and pairing files stay in an ignored local directory,
with owner-only file permissions. They must not enter a source bundle or Git.

Every route requires `Authorization: Bearer <per-aircraft credential>`. The
mission-control API will have separate user/AI credentials and permissions;
never hand the low-level aircraft credential to an LLM. A paired ground service
is responsible for checking mission ownership and permission before sending
commands. Camera, ordinary control and emergency requests use separate network
connection pools so a blocked image request cannot occupy the stop channel.

## Endpoints

| Method and route | Data |
| --- | --- |
| GET `/v1/hello` | Protocol version, device ID, random boot ID, monotonic microsecond clock, state, owner, health and limits |
| POST `/v1/session` | `{client_id}` requests exclusive control while disarmed; returns a random session ID and two-second lease |
| POST `/v1/command` | Validated command envelope below |
| POST `/v1/emergency` | Boot ID, deadline and `land` or `disarm`; revokes the current session without waiting for its owner |
| GET `/v1/camera` | JPEG up to 200 KB and verified capture metadata |
| GET `/v1/imu?after_us=N` | Up to 256 ordered samples, boot ID, ring start and an explicit overrun flag |

Example envelope (identities and numbers are placeholders):

```json
{
  "boot_id": "<32 hex characters>",
  "session_id": "<32 hex characters>",
  "sequence": 12,
  "deadline_us": 10200000,
  "operation": "attitude",
  "setpoint": {
    "roll_rad": 0.05,
    "pitch_rad": 0.0,
    "yaw_rate_rad_s": 0.0,
    "thrust": 0.4
  }
}
```

Other operations are `arm`, `heartbeat`, `land`, `disarm`; they do not accept a
setpoint. Setpoints use radians and normalized thrust, with roll/pitch bounded
to ±0.26 rad, yaw rate ±1 rad/s, thrust 0–0.8. These are provisional indoor
limits. The ground flight controller generates these commands from navigation
targets; the onboard estimator, rate loop and mixer must stabilize the vehicle.
The LLM supplies mission intent and visual observations, not motor commands.

Sequences are strictly increasing within a boot and session. Exact retries
return an acknowledgement without repeating the action or extending a deadline.
Reusing a sequence with different content is rejected. A new owner cannot claim
an armed aircraft. Emergency stop revokes the session, so a late ordinary
setpoint cannot restart motors. A claim whose reply is lost currently requires
waiting for the two-second lease to expire; automatic takeover is not supported.

## Timing, sensor quality and loss handling

The ground adapter maps the device clock using four timed exchanges and the
smallest round-trip interval. Mapping uncertainty must be at most 20 ms and
the mapping expires after 10 seconds; the control service must refresh it while
operating. `connection.py` refreshes it every three seconds, polls IMU at 25 Hz
and camera at 2.5 Hz independently of inference. The service keeps at most one
image and 512 IMU samples per aircraft, explicitly reporting overflow to pose
consumers. It never arms or emits thrust. Commands expire on the aircraft clock, no later than 250 ms after
receipt. Boot IDs prevent reuse after clock reset. Host receipt time is never
substituted for camera exposure time.

Camera headers are `X-Boot-Id`, `X-Frame-Id`, `X-Capture-Time-Us`, `X-Width` and
`X-Height`. The adapter checks JPEG dimensions, monotonic identity/timestamp,
clock uncertainty and maximum 300 ms age before exposing an image to a consumer.
IMU samples have `time_us`, `gyro_flu_rad_s`, `specific_force_flu_m_s2`; vectors
are body forward-left-up. Packet order, finiteness, boot identity, ring overrun
and maximum 50 ms age are checked. Camera/IMU mounting, delay and calibration
still require measured hardware values; this transport cannot establish them.

Only fresh attitude setpoints keep an armed aircraft commanded. Heartbeats
renew ownership but never keep stale thrust alive. Missing setpoints initiate a
bounded level-attitude/throttle-reduction ramp and revoke control. IMU failure
disarms even during the ramp. This fallback is **not an altitude-aware physical
landing guarantee**: measured hardware and a qualified height source are still
needed. The emulator tests the command lifecycle, not descent aerodynamics.
Real firmware defaults must remain unable to arm until commissioned.

## Local test

```sh
.local/vision-env/bin/python -m hardware.esp32.link_emulator \
  --identity .local/devices/test-aircraft --provision --port 8160
.local/vision-env/bin/python -m unittest \
  tests.test_aircraft_protocol tests.test_aircraft_link \
  tests.test_aircraft_connection tests.test_aircraft_connection_api -v
```

Provisioning requires `openssl` and refuses to overwrite an existing identity.
Omit `--provision` on subsequent runs. The command prints the endpoint, device ID,
public fingerprint and pairing-file location, never the pairing secret. Tests
generate temporary identities and bind only to loopback. Keep these protocol
checks separate from the full Three.js/Rapier mapping and recognition tests.

Mission Control's **Connect a drone** panel accepts the generated pairing JSON,
the local HTTPS address, a name and the selected component assembly revision.
It verifies the pinned endpoint before saving the credential to
`.local/data/aircraft.sqlite3` (mode 0600). Public API responses omit the secret.
Pair/connect routes require a loopback peer, local Host, same Origin when
present, and the local-control header for mutations. They are not the remote
API; remote authentication and scoped MCP access are preparation item 5.

The current connection service limits active sensor streams to four and paired
records to 32. These are admission limits, not measured concurrent-flight or
8 GB capacity. The camera preview allows up to 600 ms between display refreshes;
the adapter still rejects incoming frames older than 300 ms. A future vision
controller must check age again when consuming a buffered frame.

On 23 October 2026, 25 distinct protocol/HTTPS/monitor/API tests passed. They
cover identity pinning, local-origin checks, exclusive ownership, command expiry,
replay, sensor failure, queue overflow, reconnect, pairing persistence and an
emergency request during a stalled camera request. The live dashboard was
verified against the local static-image emulator; no hardware was connected.
