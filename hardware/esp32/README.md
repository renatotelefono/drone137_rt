# drone137 ESP32 indoor vision quad build A

Build objective: a very cheap, lightweight quadcopter sends live camera images
over local Wi-Fi to drone137. The ground computer runs the vision models,
records evidence and plans bounded movements. Stabilization, motor timing and
loss-of-command handling must run on the aircraft. No onboard LLM is needed.

The newer [five-model indoor catalog](indoor/report.html) expands this single
design into five alternatives with individual BOMs and frame sources. It updates
the camera price and selects lower-cost matched motor/propeller sets. The prices
below remain the original revision A allowances; use the catalog for the latest
five candidates.

This package contains a **hardware development design**, a piece-by-piece BOM,
a proposed carrier connection schedule, an unprinted parametric frame, camera-only
firmware, and a working ground-side camera/model bench interface. It is **not a
flight-ready kit**: the carrier PCB layout and flight firmware port are outstanding.
No physical aircraft, camera focus, thrust or flight has been tested.

## Cost and weight

[bom.json](bom.json) has quantities, price bases, sources and exclusions.
The basic aircraft allowance is **$48.50**, including the camera, four motors,
one battery and guards. Adding MTF-02P flow/range, a 5 V sensor supply and mount
brings the allowance to **$69.00**. Only the camera board and flow sensor prices
are manufacturer listings; the remaining rows are unquoted allowances.
**A complete under-$50 purchase has not been established.**

The $48.50 configuration is for camera and stabilization development. It does
not include demonstrated position hold or autonomous room search. The $69 version
adds the sensing needed to develop local floor-relative motion estimation; it
still needs estimator software, a global room reference and obstacle handling.
A prepared, cleared room with measured markers is the initial operating proposal.
Do not count shared room-tracking equipment as free onboard capability.

Nominal component mass allowances total 67.3 g basic / 71.8 g with the sensor pack.
Target 60–85 g assembled, subject to actual selected parts and prints. This is
not a weighed build. The frame has a 100 mm motor diagonal and an approximately
131 mm square guard envelope; propellers are 55 mm. The printed mass and motor
thrust must determine whether the design can fly with adequate reserve.

## Pieces

| Piece | Quantity | USD row allowance |
|---|---:|---:|
| XIAO ESP32-S3 Sense, supplied camera and antenna | 1 | 13.90 |
| MPU6050 breakout with 3.3 V logic | 1 | 2.50 |
| 8520 3.7 V brushed motors, two CW and two CCW | 4 | 12.00 |
| Matched 55 mm propellers | 4 | 2.00 |
| Frame with 8.5 mm motor holders and guards | 1 | 5.00 |
| 1S 450–600 mAh high-discharge LiPo | 1 | 6.00 |
| AO3400A motor-driver MOSFETs | 4 | 1.00 |
| SS34 flyback diodes | 4 | 0.60 |
| 100 ohm gate resistors and 10 kohm pulldowns | 4 + 4 | 0.20 |
| Motor suppression and power decoupling capacitors | 1 set | 0.70 |
| Carrier PCB, IMU mount and low-profile connectors | 1 set | 3.00 |
| Wiring, battery connector, strap, camera mount and fasteners | 1 set | 1.50 |
| Battery divider resistors and filter capacitor | 1 set | 0.10 |
| **Basic camera aircraft allowance** | | **48.50** |
| MTF-02P flow and downward range sensor | 1 | 16.50 |
| 1S-to-5 V regulated sensor supply | 1 | 3.00 |
| Sensor mount and cable | 1 set | 1.00 |
| **With navigation sensor pack** | | **69.00** |

Excluded: tax, shipping, assembly/test labour, custom PCB design/tooling, software,
ground PC/network, USB cable, suitable 1S charger, independent RC equipment, room
markers/tracking, wall sensors and spares. The flight battery must be selected by
measured current/sag, connector rating and mass, not just its advertised C rating.
An independent RC link is not included in this budget and would add cost/mass.

## Mechanical assembly

1. Select the actual motor winding and 1 mm shaft/prop hub combination. “8520”
   describes dimensions, not a complete interchangeable propulsion specification.
2. Start from [frame.scad](frame.scad), which is an **unprinted dimensional
   prototype**, not qualified manufacturing CAD. Tune its 8.6 mm bores to the
   selected motor and printing process. Use retention rings/sleeves; do not rely
   on a loose fit. Check guard deflection and prop clearance physically.
3. In this geometry the motor can top is at z=8 mm, its bottom at z=-12 mm and
   the proposed propeller plane at z=12 mm. Confirm actual shaft/hub heights;
   guards span z=8–16 mm and feet reach z=-14 mm. Move these dimensions if needed.
4. Mount the XIAO/camera above the central plate, camera facing forward with a
   clear image. Secure its antenna away from motor wiring. Keep the IMU rigidly
   aligned with the body axes and the battery centred beneath the plate.
5. The navigation sensor faces down through clear space; measure its orientation
   and lever arm. Keep landing feet and wires outside the sensor view.
6. Weigh the complete build and measure thrust with the selected battery. Require
   a proposed 2:1 total maximum thrust-to-weight margin near the minimum operating
   voltage. No flight-duration or thrust claim is transferred from another drone.

## Electrical connections

[connections.json](connections.json) records the proposed pin allocation.
It is a connection specification, **not a routed PCB or verified netlist**.

| Function | XIAO pin / GPIO |
|---|---|
| M1 front-right gate, CW | D0 / GPIO1 |
| M2 rear-right gate, CCW | D1 / GPIO2 |
| M3 rear-left gate, CW | D3 / GPIO4 |
| M4 front-left gate, CCW | D8 / GPIO7 |
| IMU SDA / SCL | D4 GPIO5 / D5 GPIO6 |
| IMU interrupt | D9 / GPIO8 |
| Battery ADC through divider | D10 / GPIO9 |
| UART TX to flow sensor RX | D6 / GPIO43 |
| UART RX from flow sensor TX | D7 / GPIO44 |

Remove the microSD card; SD and microphone code stay disabled. GPIO7/8/9 are
shared with SD. Leave GPIO3 (strapping), GPIO21 and GPIO41/42 unused by the carrier.
The native camera retains Seeed's documented pin mapping.

Each motor uses a low-side driver: battery positive → motor positive; motor
negative → MOSFET drain; MOSFET source → ground. The assigned GPIO feeds the gate
through 100 ohm; 10 kohm holds the gate to ground. Fit the flyback diode across
the motor, cathode to battery positive and anode to motor negative. Add 100 nF
across each motor's terminals. AO3400A and SS34 are candidates: check actual
loaded/stall current, switching stress, PCB copper and temperature before finalizing.
Motor current never passes through an ESP32 pin or the XIAO regulator.

Split the battery into a motor branch and an electronics branch with common
ground and short high-current paths. Feed the XIAO's **BAT pads** from the 1S
battery according to the exact board revision; 1S is not connected to its 5 V pin.
Use a 470 uF >=6.3 V capacitor at the motor supply and local 47 uF/100 nF electronics
decoupling, subject to regulator stability checks. Verify all board labels/polarity.

Power the IMU at its documented 3.3 V-compatible input and use 3.3 V I2C pull-ups.
Battery sensing uses 100k from VBAT to GPIO9 and 100k plus 100 nF from GPIO9 to ground;
calibrate the ADC with a meter. The optional MTF-02P uses its **separate regulated
5 V supply**, with 3.3 V UART logic and common ground. Do not connect that 5 V rail
to BAT. Disconnect the battery and motors for initial USB camera bring-up.

## Vision path that can be tested now

```text
Camera -> ESP32-S3 JPEG capture -> local Wi-Fi HTTP /capture
       -> Esp32Camera latest-frame buffer -> drone137 Frame
       -> optional local llama-server vision request -> description / recording
```

The [camera sketch](camera_bench/camera_bench.ino) uses 640 x 480 JPEG, quality 14,
two PSRAM frame buffers and a 200 KB maximum. The PC samples at 5 fps by default
(configurable up to 10). This is a sequence of fresh JPEG images, not H.264.
The bench viewer shows the sequence and the model reads sampled frames; no cloud
service or onboard model is involved. Actual throughput, focus, blur and network
latency must be measured on hardware.

The exact camera supplied by Seeed can vary: record the sensor PID printed on
serial startup. Initialization does not prove focus, orientation or autofocus
operation. Use the vendor's camera bring-up procedures if the fitted sensor needs
additional setup. The driver must produce a readable image at the mission distance.

### Compile and flash the camera-only image

Use Arduino CLI with the official ESP32 board package pinned to `esp32:esp32@3.3.12`.
The sketch is for **XIAO_ESP32S3**, not generic ESP32-CAM. Enable OPI PSRAM.
Copy `camera_bench/config.example.h` to `camera_bench/config.h` and set the local
Wi-Fi name/password. `config.h` is ignored by Git and must not be distributed.

```sh
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3:PSRAM=opi hardware/esp32/camera_bench
arduino-cli upload --fqbn esp32:esp32:XIAO_ESP32S3:PSRAM=opi --port YOUR_SERIAL_PORT hardware/esp32/camera_bench
```

The supplied image holds all four proposed motor-gate pins LOW. It has no arming
endpoint, motor mixer or flight loop and **cannot fly**. Do not attach propellers
for this camera stage. The serial console gives the camera's `/capture` address.

### Run the ground harness

From the repository root, with its Python dependencies installed:

```sh
.venv/bin/python -m scripts.esp32_camera_bench \
  --camera http://192.168.1.50/capture \
  --seconds 30 --output runs/esp32-camera-bench
```

Replace the example address with the device's actual IP. Open
`http://127.0.0.1:8144` while the command runs. It writes `latest.jpg` and a
`report.json` with receipt timing, camera metadata and errors. To forward sampled
images to an already running local vision model, add:

```sh
--model http://127.0.0.1:8081 --inference-every 3 --inference-timeout 30
```

No more than one inference request runs at once. Raw pixels are passed to the
existing `LlamaBackend.image` interface; each successful model observation stores
its source image and description. No aircraft is connected by this script.

Headers identify the boot, frame sequence, dimensions and device capture time.
The adapter rejects repeated/out-of-order timestamps, mismatched geometry,
redirects, oversized JPEGs and incomplete images. A missing frame is cleared on
network failure; `latest()` never returns a frame older than the configured host
receipt threshold. Device and host clocks are not synchronized: capture age is
reported as unknown, never inferred from their unrelated timestamps. The
`--allow-receipt-only` option supports a stock CameraWebServer but weakens evidence
of freshness and is explicitly labeled in the report.

## Work required before flight

ESP-Drone is a candidate controller basis, derived from Crazyflie. It is **not a
ready-to-flash image for the XIAO carrier**. Required work includes this pin/IMU
port, motor/prop calibration and mixer mapping, bounded control timing under
camera/Wi-Fi load, arming/takeoff/land handling, battery monitoring and tested
command-loss behaviour. Camera and inference delays must never set flight-loop
cadence. If one MCU cannot meet timing deadlines under camera load, a separate
flight MCU is required and the cost/mass budget must be updated.

The MTF-02P UART data needs a tested driver and estimator integration; the
ESP-Drone reference flow deck uses different sensors. Optical flow/range is local
motion sensing, not a global room map. A ground-computer marker pose pipeline (or
another validated reference) and an appropriate obstacle strategy remain required.

The existing drone137 vehicle path is PX4/MAVSDK SITL. ESP-Drone uses a different
control stack, so its command/telemetry adapter must be implemented and exercised
in simulation before real motion. This package adds only the physical **camera**
source and a bench viewer/model path. `physical_enabled=False` remains unchanged.

First qualify a prepared room at slow speed. Unfamiliar cluttered rooms, building
perimeters, fields and hillsides remain the broader project objective, not a
capability established by this inexpensive revision.

## Validation and reproduction

Completed on 22 October 2026: **12 camera contract tests passed**, including
fixture JPEG forwarding to the model-interface stub. The camera sketch also
**compiled successfully** for `esp32:esp32:XIAO_ESP32S3:PSRAM=opi` with ESP32
Arduino core 3.3.12. The compiler reported 955,754 bytes of program storage and
56,336 bytes of static global memory. Those are compiler figures, not runtime
camera/Wi-Fi memory measurements. No physical camera or aircraft was connected.

Run the camera contract tests:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_esp32_camera.py' -v
```

They use HTTP fixture cameras and a model-interface stub. They exercise actual
network transport and pixel forwarding but do not establish real model accuracy,
ESP32 timing, wireless quality, flight control or physical thrust. See
[validation.json](validation.json) for the actual checks completed for this package.

Bench acceptance after parts arrive: verify rails/polarity without motors;
check readable live images for 30 minutes; measure frame age and Wi-Fi loss;
check IMU axes and low-voltage behaviour; verify all motor directions with props
removed; then measure propulsion and temperatures on suitable fixtures. Real
flight commissioning follows validated control firmware and the project's
simulation acceptance gates.

## Sources

- [Seeed XIAO ESP32-S3 Sense listing](https://www.seeedstudio.com/XIAO-ESP32S3-Sense-p-5639.html)
- [Seeed board, camera variants and pin mapping](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/)
- [Seeed camera examples](https://wiki.seeedstudio.com/xiao_esp32s3_camera_usage/)
- [Espressif ESP-Drone](https://github.com/espressif/esp-drone)
- [ESP-Drone reference hardware](https://docs.espressif.com/projects/espressif-esp-drone/en/latest/hardware.html)
- [Drona motor/propeller reference](https://www.dronaaviation.com/hardware/parts)
- [AO3400A manufacturer data](https://www.aosmd.com/products/mosfets/low-voltage-mosfets-12v-30v/ao3400a)
- [MTF-02P listing](https://store.micoair.com/product/mtf-02p/)
- [MTF-02P operating requirements](https://micoair.com/optical_range_sensor_mtf-02p/)
