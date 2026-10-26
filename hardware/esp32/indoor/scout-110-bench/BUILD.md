# Drone137 prototype build brief

Scout 110-B aircraft, dock A, and the bench. For the person who orders the parts and builds
the first unit. Every link in the parts table was opened on 26 October 2026 and showed the
stock stated; the same table is in `parts-ch.csv` for a spreadsheet. Prices are CHF including
VAT unless marked.

## 1. What Drone137 is

Drone137 is an autonomous indoor reconnaissance system: a small aircraft flies inside a
building, maps it, looks for what it was asked to find, and brings back evidence, with a
local vision model as the brain and no connection to the Internet. The product is defined by
four mission clusters an operator picks from a wizard:

| Cluster | Question | Today |
| --- | --- | --- |
| Map | What is the layout of this place? | Flies in simulation |
| Audit | Are the listed items where they should be? | Flies in simulation for the qualified target |
| Watch | What changed since the last visit? | Planned |
| Find | Where is this thing, in an unknown layout? | Planned |

The design decision that shapes the hardware: all intelligence is on the ground computer. The
aircraft carries a camera, an IMU, a Wi-Fi link and an attitude loop, nothing else. The ground
computer runs navigation, mapping, the model, the mission and the docking approach, and sends
roll, pitch, yaw rate and collective over a pinned link; if the link stops, the aircraft lands
on its own. That is why the aircraft is cheap and light, why no pilot is needed, and why
nothing leaves the site.

The dock turns it into a product. With dock A the aircraft lands in a funnel, charges through
two copper strips and a spring pin, and takes off again on schedule, so the Watch cluster
becomes unattended sorties. The dock pose is also the origin of the place map: every landing
closes the navigation loop.

The software side of all of this exists and is gated in simulation: 24 of 24 missions, 11 of
13 blind exploration flights, 20 of 20 dockings on the physics plant, every mission plan with a
memory estimate, and a manual stick mode for commissioning. What does not exist is a flown
airframe. This brief is the step from software to hardware.

## 2. What the prototype consists of

| Part of the system | What it is | Why it is built this way |
| --- | --- | --- |
| Scout 110-B | A 148 mm guarded quadcopter, brushed 1S, one forward camera | Smallest airframe that carries the camera board, flies 5 to 7 minutes and survives indoor contact; brushed motors need no speed controllers, so the carrier is four transistors |
| Dock A | A printed funnel base with contact charging and a tag stand | Contact charging adds under 1 g to the aircraft; the funnel takes a 25 mm landing error; the tag column is what the forward camera steers by in the last metre |
| Bench | Charger, scale, multimeter, iron | The first unit is commissioned on the bench: measured masses go into the registry and the physics model before any hover |
| Ground computer | The Mac already in use | Runs everything; 16 GB today, 8 GB reachable, see the memory page in the docs |

## 3. Scout 110-B specification

| Item | Value |
| --- | --- |
| Size | 110 mm motor to motor, 148 mm over the guards, 64 mm tall |
| Mass | 63 g all-up in the simulation profile; printed parts about 25 g; measure before the first hover |
| Frame | Five printed PETG parts: frame with guards, electronics bridge, camera cradle, IMU tray, battery cradle (`mechanics/*.stl`) |
| Motors | Four 8520 coreless, 1.0 mm shafts, PWM 24 kHz on GPIO 1, 2, 4, 7; direction set by wiring |
| Props | 65 mm two-blade, 1.0 mm hub |
| Power | BETAFPV Lava II 480 mAh 1S, BT2.0 plug, charged to 4.20 V; about 5 to 7 minutes of flight |
| Board | XIAO ESP32-S3 Sense: camera forward pitched 10° down, Wi-Fi, onboard attitude loop |
| IMU | MPU-6050 on GPIO 5 and 6, mounted rigid with the camera |
| Carrier PCB | 42 × 40 mm, two layers, 2 oz copper: four AO3400A motor drivers with SS34 diodes, 470 µF and 47 µF bulk capacitors, 100 nF across each motor, battery divider to GPIO 9; prototype B adds the charge path: PTC 0.5 A, MCP73831 at 500 mA, STAT on GPIO 3 |
| Dock contacts | Copper disc under the battery cradle at (0, +9 mm); copper caps on the two feet at x = +14 mm |
| Link | Pinned HTTPS on the private Wi-Fi, per-aircraft certificate and credential, separate camera, control and emergency ports; VGA JPEG at 2.5 Hz, IMU at 25 Hz or better |
| Control contract | Roll and pitch ±0.26 rad, yaw rate ±1 rad/s, collective 0.8, each valid 250 ms; missing setpoints start the landing ramp |

## 4. Dock A specification

| Item | Value |
| --- | --- |
| Body | 206 × 206 × 39 mm printed PETG, 150 mm square pocket, 30° funnel walls capturing ±25 mm, electronics bay underneath |
| Contacts | Spring pin at (0, +9 mm) on a 4 mm boss; copper strips 6 × 28 mm at x = ±14 mm |
| Tag stand | L-shaped plate 140 × 240 mm standing 100 mm in front of the body; tag36h11 tags of 40, 40 and 60 mm at 82, 142 and 205 mm above the table |
| Electronics | XIAO ESP32-C3 serving `/status` and `/mode`; INA219 on the 5 V line; IRF520 switch; NTC under the floor; USB-C 5 V in |
| Rules | Cuts 5 V above 0.7 A, 45 °C or 3 h; charge, storage and off modes; the ground computer sets the mode |

## 5. Why each component

- **XIAO ESP32-S3 Sense.** Camera, Wi-Fi and the microcontroller on one 21 × 17 mm board with 8 MB of PSRAM for frames. The ground computer needs only JPEG frames and IMU samples over Wi-Fi, so this one board is the whole avionics.
- **MPU-6050.** A six-axis IMU for the onboard attitude loop and the ground estimator. At this stage the rigid mount shared with the camera matters more than sensor grade.
- **8520 motors and 65 mm props.** Brushed 1S propulsion: no speed controllers, the lowest mass and cost, and a modelled thrust-to-weight of 2.2. The 1.0 mm shafts and hubs must match.
- **Carrier PCB.** Four low-side transistors drive the motors, flyback diodes and bulk capacitors keep the board's supply stable under motor current, 100 nF across each motor tames brush noise, and a divider reads the cell. Prototype B adds the charger so the dock only has to supply 5 V.
- **Lava II 480 mAh.** A 1S cell with the low-resistance BT2.0 plug, charged to 4.20 V rather than its 4.35 V rating for longevity and safety.
- **Printed PETG parts.** The geometry will change with measurements; printing keeps the loop short, and PETG tolerates contact.
- **Nylon M2 hardware.** Non-conductive fasteners around the IMU and the board; steel M2 × 5 only where the camera cradle needs stiffness.
- **Copper tape, Velcro, cable, heat-shrink.** The dock contacts, the battery strap, the motor and charge leads.
- **Dock electronics.** The C3 is the cheapest board with Wi-Fi for the status API; the USB-C breakout with its CC resistors makes a PD supply deliver 5 V; the INA219 measures charge current, which is also how the dock knows the aircraft has made contact; the spring pin and the strips are the contacts; the NTC and the MOSFET switch are the safety cut-off.
- **Bench.** The charger sets 4.20 V; the 0.01 g scale puts measured masses into the component registry before the physics model clears a hover; the multimeter checks the carrier before power; the iron and cable are for the hand-soldered leads and for flashing.
- **ESP-FLY kit, optional.** A ready-made drone on the same board: firmware, link, console and manual flight can be exercised the week it arrives while the Scout parts ship. No guards, no dock contacts, different motor pins, so it stays a bench tool.

## 6. Build sequence

1. Order the long-lead parts today: the XIAO Sense (DigiKey), motors (UK), props (US), and the charger (one left at fpvframe).
2. Regenerate the carrier for prototype B with KiCad 10 on a machine that has it: `generate_carrier.py`, `generate_schematic.py`, ERC, DRC, `check_carrier.py`, refresh `carrier/provenance.json`. Order five assembled boards at JLCPCB. The committed Gerbers are still prototype A.
3. Print the five Scout parts (0.2 mm layers, 3 walls, 25 % infill) and the dock body and stand (15 % infill). The dock body needs a 220 mm bed.
4. Bench first: charge the cells to 4.20 V, weigh every part, enter the masses in the component registry, rerun the physics model before any hover.
5. Assemble the Scout per `assembly.md`, including the copper charge contacts wired to J18 and J19 and STAT to J20.
6. Flash the firmware, pair over the pinned link, check motor direction, IMU axes, camera and battery reading from the console, then fly by hand in the restrained enclosure.
7. Assemble the dock per `dock/README.md`; place the Scout by hand and confirm 5 V and a charge current.
8. Commission: restrained hover, first flights, then docking by hand, then guided.

## 7. Parts, by shop

Seven orders is the practical minimum: three Swiss shops, the charger, and three abroad. No single shop carries everything; Galaxus resells most Bastelgarage items at a few francs more if you prefer one Swiss basket.

### Bastelgarage, about CHF 170, free shipping from CHF 50

| Item | Part of | Qty | CHF | Stock | Link |
| --- | --- | ---: | ---: | --- | --- |
| MPU-6050 (GY-521) | Aircraft | 1 | 10.90 | In stock | https://www.bastelgarage.ch/mpu-6050-3-axis-accelerometer-with-gyroscope |
| M2 nylon screws, nuts, spacers, 260 pcs | Aircraft | 1 | 14.90 | In stock | https://www.bastelgarage.ch/sechskant-m2-distanzbolzen-abstandhalter-nylon-260-stuck |
| M2 × 5 stainless screws, 10 pcs | Aircraft | 1 | 3.90 | In stock | https://www.bastelgarage.ch/10-stuck-m2x5mm-linsenkopfschrauben-set-rostfrei |
| M2 stainless nuts, 10 pcs | Aircraft | 1 | 2.90 | In stock | https://www.bastelgarage.ch/10-stuck-m2-mutter-set-rostfrei |
| Two-core 0.25 mm² cable, per metre | Aircraft | 3 | 0.95 | In stock | https://www.bastelgarage.ch/kabel-2x0-25mm-awg24-grau-liyy |
| Heat-shrink set, 140 pcs | Aircraft | 1 | 14.90 | In stock | https://www.bastelgarage.ch/schrumpfschlauch-set-schwarz-140-stuck-total-7-6m |
| Copper tape 20 mm, 10 m | Aircraft and dock | 1 | 14.90 | In stock | https://www.bastelgarage.ch/20mm-kupferklebeband-10m |
| PETG 1.75 mm, 1 kg, grey | Aircraft and dock | 1 | 13.90 | In stock | https://www.bastelgarage.ch/petg-grau-filament-1-75mm-1kg-esun |
| XIAO ESP32-C3 | Dock | 1 | 9.90 | In stock | https://www.bastelgarage.ch/seeed-studio-xiao-esp32-c3 |
| USB-C socket breakout, 6-pin with CC resistors | Dock | 1 | 4.90 | In stock | https://www.bastelgarage.ch/usb-typ-c-buchse-breakout-board |
| INA219 current and voltage sensor | Dock | 1 | 12.90 | In stock | https://www.bastelgarage.ch/gravity-ina219-i2c-digitales-wattmeter |
| IRF520 MOSFET module | Dock | 1 | 3.90 | In stock | https://www.bastelgarage.ch/irf520-mosfet-treiber-modul |
| USB-C soldering iron 60 W, Yihua 928D-IV | Bench | 1 | 34.90 | In stock | https://www.bastelgarage.ch/yihua-928d-iv-usb-c-lotkolben-60w |
| Solder 0.5 mm lead-free, 50 g | Bench | 1 | 14.90 | In stock | https://www.bastelgarage.ch/atten-lotzinn-bleifrei-0-5mm-50g |
| USB-C data cable 1 m | Bench | 1 | 8.90 | In stock | https://www.bastelgarage.ch/usb-3-0-typ-c-kabel-1m-schwarz |

### Distrelec, about CHF 38

| Item | Part of | Qty | CHF | Stock | Link |
| --- | --- | ---: | ---: | --- | --- |
| C1 470 µF 10 V, Panasonic EEUEB1A471, pack of 5 | Aircraft | 1 | 3.68 | 195 | https://www.distrelec.ch/en/p/30429110 |
| C2 47 µF 16 V, Panasonic EEUFC1C470, pack of 5 | Aircraft | 1 | 1.83 | 1190 | https://www.distrelec.ch/en/p/30429714 |
| 100 nF 50 V leaded ceramic, KEMET C320C104M5U5TA7301 | Aircraft | 10 | 0.41 | 12916 | https://www.distrelec.ch/en/p/16572671 |
| Spring contact PTR 1060/G-A6X-3.0N-AU-3.0C | Dock | 1 | 6.49 | 23 | https://www.distrelec.ch/en/p/30019746 |
| NTC 10 kΩ, Vishay NTCLE413E2103F520L, pack of 25 | Dock | 1 | 25.81 | 4125 | https://www.distrelec.ch/en/p/30438838 |

### Galaxus, about CHF 130

| Item | Part of | Qty | CHF | Stock | Link |
| --- | --- | ---: | ---: | --- | --- |
| InLine USB-C PD supply 65 W, 3 ports | Bench and dock | 2 | 53.00 | 8 | https://www.galaxus.ch/de/s1/product/inline-usb-pd-netzteil-65-w-usb-ladegeraet-37345173 |
| Purecrea MH-500 precision scale 0.01 g | Bench | 1 | 25.90 | In stock | https://www.galaxus.ch/en/s12/product/purecrea-mh-500-precision-scales-54993706 |
| Uni-T UT139C multimeter | Bench | 1 | 45.50 | 9 | https://www.galaxus.ch/de/s4/product/uni-t-ut139c-cat-iii-600v-hand-multimeter-multimeter-34370475 |
| Velcro cable ties 200 mm, 6 pcs | Aircraft | 1 | 5.25 | 5 | https://www.galaxus.ch/de/s4/product/velcro-brand-klettband-klettkabelbinder-200-mm-6-stk-kabelbinder-14958774 |

### fpvracing.ch, about CHF 42, flat CHF 5 shipping

| Item | Part of | Qty | CHF | Stock | Link |
| --- | --- | ---: | ---: | --- | --- |
| BETAFPV Lava II 480 mAh 1S 95C BT2.0, 4-pack | Aircraft | 1 | 28.90 | In stock | https://fpvracing.ch/en/1s/4197-betafpv-lava-ii-480mah-1s-95c-bt20-4-pcs.html |
| BT2.0 U-pigtails, 6 pcs | Aircraft | 1 | 7.90 | In stock | https://fpvracing.ch/en/connectivity/4261-bt20-u-pigtail.html |

### fpvframe.ch, the charger, order first

| Item | Part of | Qty | CHF | Stock | Link |
| --- | --- | ---: | ---: | --- | --- |
| VIFLY WhoopStor 3 charger, BT2.0, 4.20 V | Bench | 1 | 28 to 32 | 1 left | https://fpvframe.ch/product/vifly-whoopstor-3/ |
| Alternative: FlyingTech UK, GBP 27.90, in stock | | | | | https://www.flyingtech.co.uk/product/vifly-whoopstor-v3-1s-lipo-battery-charger-discharger-ph2-bt2-0/ |

### Abroad, because no Swiss shop has them

| Shop | Item | Qty | Price | Stock | Link |
| --- | --- | ---: | ---: | --- | --- |
| DigiKey.ch | XIAO ESP32-S3 Sense, Seeed 113991115 | 1 | CHF 12.44 | 3117 | https://www.digikey.ch/en/products/detail/seeed-technology-co-ltd/113991115/18724504 |
| Unmanned Tech UK | 8520 coreless motors, 2 CW + 2 CCW, 1.0 mm shaft | 1 pack | GBP 6.49 | Available | https://www.unmannedtechshop.co.uk/products/8520-coreless-brushed-motor-pack-2-x-cw-2-x-ccw |
| RaceDayQuads US | Gemfan 65 mm bi-blade props, 1.0 mm shaft, 8-pack, grey | 2 | USD 3.49 each | Available | https://www.racedayquads.com/products/gemfan-65mm-bi-blade-2-5-prop-8-pack-1mm-shaft-choose-your-color |
| JLCPCB | Carrier PCB prototype B, assembled | 5 | about CHF 60 | After step 2 | https://jlcpcb.com/ |
| AprilRobotics | AprilTags tag36h11, 40, 40 and 60 mm, printed on paper | 3 | 0 | Print | https://github.com/AprilRobotics/apriltag-imgs/tree/master/tag36h11 |
| Seeed Studio, optional | ESP-FLY bench kit | 1 | USD 59.99 | Not verified, bot check | https://www.seeedstudio.com/ESP-FLY-co-create-p-6744.html |

### Totals

| | CHF |
| --- | ---: |
| Aircraft, first unit: parts, filament, tape, heat-shrink and the five-board PCB run | about 215 |
| Dock A, first unit, with its supply | about 90 |
| Bench, with its supply and the charger | about 185 |
| One aircraft, one dock and the bench | about 490 |
| Optional ESP-FLY kit | about 55 |
| Each further aircraft | about 65 |
| Each further dock | about 60 |

The CSV sums to CHF 476.56 for the CHF-priced lines, GBP 6.49 and USD 66.97 including the optional kit.

## 8. What is not yet verified

Nothing has been printed, soldered or flown. Masses, the slide in the funnel, contact
resistance, charger temperature and the camera mount angle are design values until measured.
The carrier Gerbers must be regenerated before the PCB order. The dock controller firmware is
not written; the dock's electronics are a wiring plan with a status API specified in
`docs/docking.md`. Seeed Studio could not be re-read for stock.
