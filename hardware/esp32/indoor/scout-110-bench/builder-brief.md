# Brief for the drone builder

What Drone137 is, what you are building, and what to send back.

## What Drone137 is

Drone137 is an autonomous indoor reconnaissance system. A small quadcopter flies
into a room it has never seen, with no map and no external positioning, and a
ground computer builds a map of the space from the drone's single camera and its
IMU, decides where to look next, and brings the drone back to its launch point.
The intelligence is on the ground: a Mac runs perception, mapping, planning and a
local vision-language model. The aircraft only stabilises itself, streams camera
and IMU data, and executes bounded setpoints. If the link drops, it stops on its own.

The software side is finished and tested in simulation; twelve predeclared
qualification suites have flown in a physics simulator and no simulated flight
has recorded a contact. What does not exist yet is the physical aircraft. That is
your part, and everything you need is designed, checked and committed.

## Where everything is

Repository `bitfent/drone137`, branch `codex/indoor-vision-platform`. Read in order:

1. [README.md](README.md): parts list with prices and suppliers; readiness.
2. [assembly.md](assembly.md): carrier board, wiring, motor orientation, printed parts, dry-fit sequence.
3. [Flight firmware](../../flight/README.md): build modes, pin assignments, flashing, commissioning stages.
4. [Pre-hardware preparation](../../../../docs/pre-hardware-six.md): what was verified before hardware and what hardware must establish.
5. [Measurement template](../../../../docs/test-data/hardware-run-template.json): the empty record you fill in.
6. [Supported aircraft](../../../../docs/supported-aircraft.md): the contract any aircraft must meet.

## The aircraft: Scout 110-B

A 110 mm guarded quadcopter: four brushed 8520 coreless motors with 65 mm HQProp
propellers, a Seeed XIAO ESP32-S3 Sense as flight controller and camera, a GY-521
MPU-6050 IMU, one BETAFPV 450 mAh 1S BT2.0 battery, and a custom carrier PCB with
four AO3400A low-side MOSFETs, four SS34 flyback diodes, gate resistors and
pull-downs, bulk and suppression capacitors and the battery divider. The frame is a
printed five-part package: frame with guards, electronics bridge, camera cradle,
IMU tray and battery cradle. Gerbers, schematic, STL and SCAD files are in
`carrier/` and `mechanics/`. Order the carrier from the gerbers with 2 oz copper.

Do not substitute a perfboard driver, a bought frame or a soft IMU mount. The
carrier geometry, the rigid camera-to-IMU relationship and the diode rating are
design decisions, not suggestions.

## Firmware

Build target `esp32:esp32:XIAO_ESP32S3:PSRAM=opi`. Motor PWM on GPIO 1, 2, 4
and 7 at 24 kHz; IMU on GPIO 5 and 6 at address 0x68; battery ADC on GPIO 9
through a 100k/100k divider. Three builds: **safe** with motors disabled,
**propeller-free** for individual motor pulses, and **restrained-rig**, which runs
the attitude loop at limited collective and disarms itself after five seconds.
The default is safe. Charge the battery to 4.20 V, not 4.35 V.

## Commissioning order

Do not skip steps.

1. Carrier populated and inspected, printed parts dry-fitted, as-built wiring and
   motor order documented. No propellers.
2. Flash the safe build. Verify camera stream, IMU axes, battery reading and the
   control-loop timing while the camera is streaming.
3. Pair the board with Mission Control over the pinned HTTPS link and confirm the
   emergency stop path.
4. Propeller-free build: confirm each motor's direction and order.
5. Measure and record: assembled mass, thrust and current versus duty on a
   restrained rig, battery sag under load, vibration, camera and control timing.
   These go into the measurement template and the component registry; the
   simulation is rerun with them before anyone talks about a hover.
6. Restrained attitude tuning, then one short guarded hover in a protected space.

## What to send back

The completed measurement template, photos of the as-built wiring and motor
orientation, the firmware build hashes you flashed, and anything that did not
fit, did not match the drawings or ran hot. A missing measurement is recorded
as missing, never as zero, and a rule-check pass on the ground is not a flight pass.
