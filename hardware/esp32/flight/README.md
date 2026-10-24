# Scout firmware and commissioning tools

This is the **prototype board firmware**, with a matching desktop runner of the
same C++ controller and command parser. A successful compile or desktop test is
not evidence of ESP32 timing, electrical performance or flight stability.
Default builds keep every motor output low. Mission Control cannot launch a
physical aircraft. The ground computer runs perception and mapping; the ESP32
runs attitude stabilization, bounded motor commands and camera/IMU streaming.

## Controller and interface

- Provisional 500 Hz MPU-6050 loop, stationary gyro/gravity initialization,
  quaternion attitude estimate, angle/rate control and X-quad mixer.
- PWM: GPIO 1, 2, 4, 7; timer 1/channels 1–4, 24 kHz. Camera uses timer/channel 0.
- IMU: GPIO 5/6, address 0x68, 400 kHz I2C; body axes **forward, left, up**.
- ADC: GPIO 9, 100k/100k battery divider; calibrate scale against a meter.
- Authenticated pinned HTTPS: control 443, camera 8444, emergency 8445. Each has
  its own server task. Same certificate and device identity on every channel.
- Exclusive control, boot/session identity, ordered commands, normalized exact
  retries and maximum 250 ms command validity. Heartbeats never prolong thrust.
- Missing IMU/control-loop overrun, excessive tilt and invalid voltage stop
  outputs. Command loss/low battery starts a bounded 1.5 s collective ramp.
  **That ramp is not height-controlled landing**; its physical behavior must be
  measured on a restrained rig. Reboot always clears ownership and disarms.
- Camera VGA JPEG with capture timestamps; ordered IMU ring with explicit
  overrun. Physical sensor throughput, clock alignment and rolling shutter
  effects remain to be measured while all three HTTPS services are active.

The transmitted `thrust` field currently means **normalized collective PWM**,
not newtons or a calibrated thrust curve. Motor order, gains, sensor axes,
supply sag and loaded timing are provisional. No altitude/position autopilot
is implemented on the aircraft. Physical navigation stays disabled until its
calibrated feedback and failure behavior are demonstrated.

## Install once, then build and operate locally

Use the project's Python environment and pinned dependencies in
[mission-runtime.md](../../../docs/mission-runtime.md). Install Arduino CLI and
Espressif Arduino core **3.3.12** while internet is available. On this workstation
those live under `.local/esp32-toolchain`; the helper also accepts `arduino-cli`
on PATH. Target: `esp32:esp32:XIAO_ESP32S3:PSRAM=opi`.

```sh
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@3.3.12 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
```

Compiler packages and model weights must be installed before offline deployment.
Build/flash, local Wi-Fi communication, inference and recorded-data replay do
not call a cloud service. This workstation's build is verified; a clean offline
installation on an actual 8 GB machine remains a separate qualification.

Create an owner-readable local JSON file containing `ssid` and `password` for
your private 2.4 GHz Wi-Fi network, then provision a unique identity per board:

```sh
.local/vision-env/bin/python -m scripts.esp32_firmware provision \
  --identity .local/devices/scout-one --device scout-one \
  --network-file .local/private-wifi.json
.local/vision-env/bin/python -m scripts.esp32_firmware build \
  --identity .local/devices/scout-one --output .local/firmware/scout-one-safe
```

Keep the identity, generated headers and **compiled binaries** private: binaries
contain the per-device key and Wi-Fi credentials. They are excluded from Git.
Every build uses a new directory and records hashes. Flash only after inspecting
power wiring, with propellers removed and motors electrically disconnected:

```sh
.local/vision-env/bin/python -m scripts.esp32_firmware flash \
  --build .local/firmware/scout-one-safe --port /dev/cu.REPLACE_WITH_BOARD_PORT
```

Select the actual board serial port; the tool checks binary hashes and never
arms during flashing. Boot on a level, still surface for at least nine seconds.
Read the board's local address from its serial output. Keep USB charging and
motor supply arrangements consistent with the assembly guide.

## Connect, diagnose and record without moving motors

In Drone137 `/control`, choose **Connect a drone**, upload that board's private
`pairing.json`, enter its local HTTPS address and connect. The preview and
sensor status are available, while physical mission launch remains unavailable.
The pairing file contains a credential; share it only with the controlling PC.

```sh
.local/vision-env/bin/python -m scripts.esp32_firmware diagnose \
  --identity .local/devices/scout-one --address https://192.168.1.50 \
  --output .local/bench/scout-one-first-power
.local/vision-env/bin/python -m scripts.esp32_firmware record \
  --identity .local/devices/scout-one --address https://192.168.1.50 \
  --seconds 30 --output .local/bench/scout-one-sensors
```

Neither command claims control or arms. Recording retains device-clock camera
and IMU data, content hashes, gaps and measured throughput. Start with the
motors disconnected. Hand-carried recordings can test the visual pipeline
before any flight; they do not establish airborne accuracy.

## Motor order and restrained tuning

There are three explicit output modes, separate from the safe build:

| Build option | Permitted behavior | Required record |
| --- | --- | --- |
| `--propeller-free-bench` | One motor, duty ≤0.20, pulse ≤200 ms; flight arming disabled | Operator removes all propellers and inspects wiring |
| `--restrained-rig` | Attitude loop, collective ≤0.65; board disarms within 5 seconds even if commands continue | Initial electrical/motor/IMU/ADC checks plus verified restraint |
| `--enable-commissioned-motors` | Normal bounded attitude-command protocol | All physical checks in commissioning record; still no autonomous-navigation qualification |

Copy [commissioning-template.json](commissioning-template.json) into the private
identity directory as `commissioning.json`. Fill each check only from physical
measurements; retain the evidence directory and operator. Restrained tuning is
not required to build the restrained mode, but is required for the later
commissioned mode. No completed physical record is supplied in this repository.

Build the propeller-free image into a new directory and flash it using the same
procedure. Then test each motor separately, viewed from above: **1 front-right
CW; 2 rear-right CCW; 3 rear-left CW; 4 front-left CCW**.

```sh
.local/vision-env/bin/python -m scripts.esp32_firmware motor-test \
  --identity .local/devices/scout-one --address https://192.168.1.50 \
  --motor 1 --duty .1 --milliseconds 100 --propellers-removed \
  --output .local/bench/scout-one-motor1
```

The restrained build is for a mechanical test rig that prevents takeoff and
contains the rotors. After its prerequisite measurements, the explicit
`rig-test` command accepts `--seconds` (0.2–4), `--collective` (0–0.65),
`--roll-deg`/`--pitch-deg` (±8) and `--restraint-confirmed`, along with identity,
address and a new output directory. It logs telemetry and disarms in cleanup;
its default collective is zero. An operator must select measured test settings.
Provisional gains live in `flight_core.h`; rebuild and retain each revision
when tuning. Do not use this command for an unrestrained hover.

## Calibrate and replay

Use `scripts.calibrate_camera` on at least 10 measured checkerboard fit views
and 3 preselected check views at the exact streaming settings. It fits camera
intrinsics only. Measure camera-to-IMU mounting and timing separately; do not
copy simulated optics or assume a zero timing offset. Complete
[sensor-calibration-template.json](sensor-calibration-template.json), using the
camera result's `intrinsics` as `optics`. Current replay supports a forward,
zero-roll camera with a measured pitch and body offset.

```sh
.local/vision-env/bin/python -m hardware.esp32.sensor_recording \
  --recording .local/bench/scout-one-sensors \
  --calibration .local/devices/scout-one/sensor-calibration.json \
  --output .local/bench/scout-one-replay
```

Replay rejects provisional/wrong-device calibration, changed evidence, reboot,
unordered/gapped IMU and invalid mount data. It writes an estimated map without
receiving a reference room map. Ground truth is required separately to score
physical accuracy. Save physical measurements with the
[test-comparison templates](../../../docs/test-comparison.md), then create
measured SQLite component revisions before rerunning simulations.

## Software validation

`tests.test_firmware` runs the same C++ controller as the board, including an
independent attitude plant. `tests.test_firmware_integration` exercises that
controller over localhost pinned HTTPS, including Mission Control and the
operator tools. Its camera/IMU are synthetic; it is labeled a software test.
`tests.test_sensor_recording` verifies replay provenance and sensor continuity.
No test result here claims MCU deadlines, calibrated thrust or real flight.
