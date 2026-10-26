# Building the Drone137 prototype: Scout 110-B, dock A and the bench

One page for the person who orders the parts and builds the first unit. The detailed
documents stay where they are: `builder-brief.md` (what the aircraft is for),
`assembly.md` (step by step, carrier wiring), `dock/README.md` (the dock),
`procurement-ch.md` (every link checked on 25 October 2026), `../../../../docs/docking.md`
(how the aircraft lands on the dock). Prices are CHF unless marked; links were opened on
25 October 2026 and stock changes daily.

## What the prototype is

| Part of the system | What it is | Made of |
| --- | --- | --- |
| Scout 110-B | A 148 mm guarded quadcopter with one forward camera that flies indoor reconnaissance missions commanded by the ground computer | Printed PETG frame, four 8520 brushed motors, 65 mm props, one 1S 480 mAh cell, a 42 × 40 mm carrier PCB, a XIAO ESP32-S3 Sense (camera, Wi-Fi), an MPU-6050 IMU |
| Dock A | A landing base: the aircraft lands in a funnel, slides to the centre, and charges through two copper foot strips and one spring pin | Printed PETG body and tag stand, three AprilTags, a XIAO ESP32-C3, a current sensor, a 5 V switch, a thermistor, a USB-C 5 V supply |
| Ground computer | Runs everything else: navigation, mapping, the local vision model, the mission console, the docking controller | The Apple-silicon Mac already in use (16 GB); nothing leaves the site |

## Specification

| Item | Scout 110-B | Dock A |
| --- | --- | --- |
| Size | 110 mm motor to motor, 148 mm over the guards, 64 mm tall | Body 206 × 206 × 39 mm; pocket 150 mm square; tag stand 140 × 240 mm standing 100 mm in front of the body |
| Mass | 63 g all-up in the simulation profile; printed parts about 25 g; measure before the first hover | About 150 g body and 60 g stand at 15 % infill |
| Power | 1S Li-Po 480 mAh, BT2.0, charged to 4.20 V; about 5 to 7 minutes of flight | 5 V from a USB-C PD supply; charge current up to 500 mA on the aircraft, about 1.5 h for a full charge |
| Propulsion | Four 8520 coreless motors, 1.0 mm shafts, PWM 24 kHz on GPIO 1, 2, 4, 7; 65 mm two-blade props | — |
| Sensors | OV2640 camera forward, pitched 10° down, VGA JPEG at 2.5 Hz; MPU-6050 on GPIO 5 and 6 at 25 Hz or better; battery voltage on GPIO 9 | INA219 current and voltage on the 5 V line; NTC 10 kΩ under the floor |
| Control board | XIAO ESP32-S3 Sense; onboard attitude loop; ground sends roll, pitch, yaw rate, collective, each valid 250 ms | XIAO ESP32-C3 switching the 5 V, serving `/status` and `/mode` |
| Charging | Carrier prototype B: PTC 0.5 A, MCP73831-2 at 500 mA, STAT to GPIO 3; copper disc under the cradle at (0, +9 mm) and copper caps on the two feet at x = +14 mm | Spring pin at (0, +9 mm) on a 4 mm boss; copper strips 6 × 28 mm at x = ±14 mm; cuts 5 V above 0.7 A, 45 °C or 3 h |
| Capture | Lands within ±20 mm and 5° by the tags; the funnel takes the rest | 30° funnel walls capture ±25 mm; yaw locks to multiples of 90° |
| Tags | — | tag36h11, ids 3k, 3k+1, 3k+2 for dock k: 40 mm at 82 and 142 mm, 60 mm at 205 mm above the table |
| Link | Pinned HTTPS on a private Wi-Fi, per-device certificate and pairing credential, separate camera, control and emergency ports | Same scheme, status and mode only |
| Software gates met in simulation | Blind exploration 11 of 13 flights; missions 24 of 24; docking 20 of 20 on the Rapier plant (worst 12 mm) | — |

## Build sequence

1. **Order the long-lead parts today.** XIAO ESP32-S3 Sense (DigiKey, four-week lead; every Swiss shop was out), 8520 motors (UK), 65 mm 1.0 mm-hub props (US only), the spring contact (Distrelec, to order). Everything else is in Swiss stock.
2. **Regenerate the carrier for prototype B** with KiCad 10 on a machine that has it: `generate_carrier.py`, `generate_schematic.py`, ERC, DRC, `check_carrier.py`, then refresh `carrier/provenance.json`. Order five assembled boards at JLCPCB (two to three weeks). The committed Gerbers are still prototype A, without the charge path.
3. **Print** the five Scout parts (`mechanics/*.stl`, PETG, 0.2 mm layers, 3 walls, 25 % infill) and the dock body and stand (`dock/*.stl`, 15 % infill). The dock body needs a 220 mm bed; the stand prints flat.
4. **Bench first.** Charge the cells to 4.20 V, weigh every part on the 0.01 g scale, enter the measured masses in the component registry, and rerun the physics model before any hover. Meanwhile the Seeed ESP-FLY kit lets the firmware and the link be exercised on a flying board while the Scout parts ship.
5. **Assemble the Scout** per `assembly.md`: motors in the bores, carrier on the four M2 mounts, XIAO and IMU rigid on the bridge, battery cradle strapped under the plate, motor leads with a 100 nF across each motor, charge contacts wired to J18 and J19, STAT to J20.
6. **Flash and pair.** Build target `esp32:esp32:XIAO_ESP32S3:PSRAM=opi`; pair over the pinned link; check motor direction, IMU axes, camera frames and the battery reading from the console.
7. **Assemble the dock** per `dock/README.md`: ream the pin hole to the pin barrel, lay the copper strips, fit the electronics in the bay, glue the tags centred at 82, 142 and 205 mm, tape the stand's foot against the dock's front wall. Place the Scout by hand and confirm 5 V at J18 and a charge current on the INA219.
8. **Commission.** Restrained hover in the bench enclosure, then first flights, then docking: first by hand into the funnel from 50 mm off-centre, then the guided descent from the hover point, then the full approach. Keep every recording.

## Shopping list, Switzerland first

### Aircraft, about CHF 180 including the PCB run

| Part | Qty | Buy | Price | Stock on 25 Oct |
| --- | ---: | --- | ---: | --- |
| XIAO ESP32-S3 Sense, Seeed 113991115 | 1 | [DigiKey.ch](https://www.digikey.ch/en/products/result?keywords=113991115) | about 12 | Listed, 4-week lead; [Seeed direct](https://www.seeedstudio.com/XIAO-ESP32S3-Sense-p-5639.html) ships to CH; [Bastelgarage](https://www.bastelgarage.ch/seeed-studio-xiao-esp32-s3-sense-with-camera) 19.90 and [Pi-Shop](https://www.pi-shop.ch/seeed-studio-xiao-esp32-s3-sense) 15.30 were out |
| GY-521 MPU-6050 | 1 | [Bastelgarage](https://www.bastelgarage.ch/mpu-6050-3-axis-accelerometer-with-gyroscope) | 10.90 | In stock |
| 8520 motors, 2 CW + 2 CCW, 1.0 mm shaft | 1 pack | [Unmanned Tech UK](https://www.unmannedtechshop.co.uk/products/8520-coreless-brushed-motor-pack-2-x-cw-2-x-ccw) | GBP 6.49 | In stock; [Bastelgarage](https://www.bastelgarage.ch/8-5x20mm-coreless-micro-motor-4pcs) 14.90 when restocked |
| 65 mm props, 1.0 mm hub, set of 8 | 2 sets | [GetFPV, Gemfan](https://www.getfpv.com/propellers/micro-quad-propellers/gemfan-65mm-micro-propellers-1mm-shaft-set-of-8.html) | USD 3.99 | Listed; no Swiss or EU shop had a 1.0 mm hub |
| BETAFPV Lava II 480 mAh 1S, 4-pack | 1 | [fpvracing.ch](https://fpvracing.ch/en/1s/4197-betafpv-lava-ii-480mah-1s-95c-bt20-4-pcs.html) | 28.90 | In stock |
| BT2.0 pigtails, 6 pcs | 1 | [fpvracing.ch](https://fpvracing.ch/en/connectivity/4261-bt20-u-pigtail.html) | 7.90 | In stock |
| Carrier PCB prototype B, assembled | 5 | [JLCPCB](https://jlcpcb.com/) from the regenerated Gerbers | about 60 | After step 2 |
| C1 470 µF 10 V, 6.3 mm body | 1 | [Distrelec EEUEB1A471](https://www.distrelec.ch/en/p/30429110) | 3.40 | 195 in stock |
| C2 47 µF 16 V, 5 mm body | 1 | [Distrelec EEUFC1C470](https://www.distrelec.ch/en/p/30429714) | 1.69 | 1190 in stock |
| 100 nF ceramic set | 1 | [Bastelgarage](https://www.bastelgarage.ch/keramik-kondensator-set-300-stuck-assortiert) | 9.90 | In stock |
| M2 nylon screws, nuts, spacers | 1 set | [Bastelgarage](https://www.bastelgarage.ch/sechskant-m2-distanzbolzen-abstandhalter-nylon-260-stuck) | 14.90 | In stock |
| M2 × 5 stainless screws, M2 nuts | 1 each | [screws](https://www.bastelgarage.ch/10-stuck-m2x5mm-linsenkopfschrauben-set-rostfrei), [nuts](https://www.bastelgarage.ch/10-stuck-m2-mutter-set-rostfrei) | 3.90 + 2.90 | In stock |
| Wire 24 to 26 AWG, red and black | 1 m each | [Bastelgarage](https://www.bastelgarage.ch/kabel-litzen/litzen-drahte) | about 8 | In stock |
| PETG for the frame, cradles and dock, 1 kg | 1 | Any PETG; [Bastelgarage eSun](https://www.bastelgarage.ch/petg-schwarz-filament-1-75mm-1kg-esun) was out on 25 Oct | about 14 | — |

### Dock A, about CHF 90 for the first dock

| Part | Qty | Buy | Price | Stock on 25 Oct |
| --- | ---: | --- | ---: | --- |
| XIAO ESP32-C3 | 1 | [Bastelgarage](https://www.bastelgarage.ch/seeed-studio-xiao-esp32-c3) | 9.90 | In stock |
| USB-C socket breakout with CC pull-downs | 1 | [Bastelgarage](https://www.bastelgarage.ch/usb-typ-c-buchse-breakout-board) | 4.90 | In stock; not the 4-pin version |
| INA219 current and voltage sensor | 1 | [Bastelgarage, DFRobot Gravity](https://www.bastelgarage.ch/gravity-ina219-i2c-digitales-wattmeter) | 12.90 | In stock |
| Spring contact pin | 1 | [Distrelec PTR 5110/S-D-1.2N-AU-2.3C](https://www.distrelec.ch/en/p/14022290) | 3.59 | To order; [PTR 1060/G-A6X-3.0N-AU-3.0C](https://www.distrelec.ch/en/p/30019746) 6.50 in stock |
| Copper tape 20 mm, 10 m | 1 | [Bastelgarage](https://www.bastelgarage.ch/20mm-kupferklebeband-10m) | 14.90 | In stock; also the aircraft's disc and foot caps |
| NTC 10 kΩ, pack of 25 | 1 | [Distrelec Vishay NTCLE413E2103F520L](https://www.distrelec.ch/en/p/30438838) | 25.81 | 4125 in stock |
| Logic-level P-MOSFET for the 5 V switch | 1 | AO3401A or IRLML6402 in the JLCPCB order, or a Bastelgarage MOSFET module | about 2 | — |
| AprilTags, 40, 40 and 60 mm | 3 | Print from [apriltag-imgs tag36h11](https://github.com/AprilRobotics/apriltag-imgs/tree/master/tag36h11) | 0 | — |
| Version 2 only: Qi transmitter and receiver, 5 V 1 A | 1 | [Bastelgarage](https://www.bastelgarage.ch/wireless-charging-modul-5v-1a) | 10.90 | In stock |

### Bench, about CHF 170

| Item | Buy | Price | Stock on 25 Oct |
| --- | --- | ---: | --- |
| VIFLY WhoopStor 3 charger, 4.20 V, BT2.0 | [fpvframe.ch](https://fpvframe.ch/product/vifly-whoopstor-3/) | 28 to 32 | 2 left; [FlyingTech UK](https://www.flyingtech.co.uk/product/vifly-whoopstor-v3-1s-lipo-battery-charger-discharger-ph2-bt2-0/) GBP 27.90 |
| USB-C PD supply 65 W, 3 ports | [Galaxus InLine](https://www.galaxus.ch/de/s1/product/inline-usb-pd-netzteil-65-w-usb-ladegeraet-37345173) | 26.50 | 8 in stock; one per dock plus one for the bench |
| Precision scale 0.01 g | [Galaxus Purecrea MH-500](https://www.galaxus.ch/en/s12/product/purecrea-mh-500-precision-scales-54993706) | 25.90 | In stock |
| Multimeter, 10 A DC | [Galaxus Uni-T UT139C](https://www.galaxus.ch/de/s4/product/uni-t-ut139c-cat-iii-600v-hand-multimeter-multimeter-34370475) | 45.50 | 10 in stock |
| USB-C data cable, soldering iron, 0.5 mm solder | Any Galaxus listing | about 40 | — |
| Bench platform while the Scout parts ship: Seeed ESP-FLY kit | [Seeed Studio](https://www.seeedstudio.com/ESP-FLY-co-create-p-6744.html) | USD 59.99 | Ships to CH |

Total for one aircraft, one dock and the bench: about CHF 500, of which about CHF 55 is the
optional ESP-FLY kit. A second aircraft adds about CHF 120 (no bench, no new PCB run);
a second dock about CHF 60.

## What is not yet verified

Nothing has been printed, soldered or flown. The masses, the slide in the funnel, the
contact resistance, the charger temperature and the camera mount angle are design
values until measured on the bench. The carrier Gerbers must be regenerated before the
PCB order. The dock controller firmware is not written; the dock's electronics are a
wiring plan with a status API specified in `docs/docking.md`.
