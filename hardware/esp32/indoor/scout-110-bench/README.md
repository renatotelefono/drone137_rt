# Build choice: D137 Scout 110-B

Build one **Scout 110-B bench prototype** first: a guarded 110 mm quadcopter,
four brushed 8520 motors, a forward-facing XIAO ESP32-S3 Sense camera, and a
single commercial 1S battery. The local computer runs Drone137, Qwen and Florence.
The aircraft must eventually run its own stabilization and command-loss handling.
No Jetson, onboard language model, Internet connection or mesh network is required.

This is a specific parts choice for camera, electrical and mechanical development.
It is **not a flight-ready kit**: the carrier layout, flight firmware port and
real indoor positioning still need to be implemented and validated. The supplied
camera firmware intentionally cannot arm motors. Start with camera streaming
and frame fit while those flight-control tasks are completed.

## Parts to obtain

Core vendor listings rechecked 23 October 2026. USD except where explicitly stated. The
machine-readable [bill of materials](bom.json) records quantities and price bases.

| Part | Quantity | Cost per aircraft | Purchase reference / basis |
|---|---:|---:|---|
| XIAO ESP32-S3 Sense, supplied camera and antenna | 1 | $13.90 | [Seeed SKU 113991115](https://www.seeedstudio.com/XIAO-ESP32S3-Sense-p-5639.html) |
| GY-521 MPU-6050, 3–5 V module input | 1 | $4.95 | [Qkits SKU MPU-6050](https://store.qkits.com/electronics/3-axis-gyroscope-accelerometer-gy-521.html), USD listing |
| 8520 motors, 1 mm shafts, 2 CW + 2 CCW | 4 | $9.00 allowance | [Unmanned Tech 41C-069-230](https://www.unmannedtechshop.co.uk/products/8520-coreless-brushed-motor-pack-2-x-cw-2-x-ccw), actual listing £6.49 per four-pack |
| HQProp 65 mm ultralight, 1 mm shaft, 2 CW + 2 CCW | 4 | $2.39 | [SpeedyFPV TR21](https://speedyfpv.com/products/hqprop-65mm-ultralight-propeller-set-2x-cw-2x-ccw-gray) |
| BETAFPV 450 mAh 1S BT2.0 pack, SKU 01030002 | 1 | $3.75 allocated | [BETAFPV four-pack $14.99](https://betafpv.com/collections/batt-1s/products/bt2-0-450mah-1s-30c-battery-4pcs) |
| Scout 110 printed frame with guards | 1 | $4.00 allowance | [Frame source](../frames/scout-110.scad), [shared geometry](../frames/common.scad) |
| AO3400A MOSFETs | 4 | $1.00 allowance | SOT-23, low-side motor switches |
| SS34 Schottky diodes | 4 | $0.60 allowance | One flyback diode per motor |
| 100 ohm gate resistors + 10 kohm pulldowns | 4 + 4 | $0.20 allowance | One of each per MOSFET |
| Motor suppression and supply capacitors | Set | $0.70 allowance | 4 × 100 nF; 470 uF ≥6.3 V; 47 uF; 100 nF |
| Battery measurement divider/filter | Set | $0.10 allowance | 2 × 100 kohm and 100 nF |
| Carrier, IMU mount and connections | Set | $3.00 allowance | Material only; PCB layout/tooling not included |
| BT2.0 aircraft pigtail, wire, camera mount, strap and fasteners | Set | $1.50 allowance | Short motor-current paths; strain relief |
| **Total consumed parts allowance** | | **$45.09** | **A budget, not a complete retail checkout quote** |

The battery seller requires a four-pack. Buying that pack adds $11.24 of spare
battery inventory, making the listed first-build purchase allowance **$56.33
before shipping, taxes and other order minimums**. A delivered single prototype
under $50 has not been established. The $45.09 figure is per aircraft consumed
parts and includes some unquoted allowances. The motor USD allowance is not a
currency conversion guarantee. Charger, tools, ground computer, Wi-Fi access
point, positioning equipment, labour, PCB engineering and spares are excluded.

The original SpeedyFPV $4.49 motor/propeller kit is sold out in its live product
inventory. Do not base this build on that sale price. The replacement motor pack
and HQProp set were available when checked; their combined loaded thrust/current
has not been published or measured here.

## First-prototype order — 23 October 2026

Order **one prototype**, with spare batteries from the required multipack. Buy the
unsoldered **Sense** camera version of the XIAO; the plain ESP32-S3 board does not
include the camera. The camera streams over local Wi-Fi to the ground computer.

| Order now | Purchase quantity | Listed order price |
| --- | ---: | ---: |
| [Seeed XIAO ESP32-S3 Sense](https://www.seeedstudio.com/XIAO-ESP32S3-Sense-p-5639.html) | 1 | $13.90 |
| [Qkits GY-521 MPU-6050](https://store.qkits.com/electronics/3-axis-gyroscope-accelerometer-gy-521.html) | 1 | $4.95 |
| [Unmanned Tech 8520 motor pack, 2 CW + 2 CCW, 1 mm shafts](https://www.unmannedtechshop.co.uk/products/8520-coreless-brushed-motor-pack-2-x-cw-2-x-ccw) | 1 four-pack | GBP 6.49 |
| [HQProp 65 mm, 1 mm hub, 2 CW + 2 CCW](https://speedyfpv.com/products/hqprop-65mm-ultralight-propeller-set-2x-cw-2x-ccw-gray) | 1 four-pack | $2.39 |
| [BETAFPV 450 mAh 1S BT2.0 batteries](https://betafpv.com/collections/batt-1s/products/bt2-0-450mah-1s-30c-battery-4pcs) | 1 four-pack; fit one battery | $14.99 |
| [BETAFPV BT2.0 Whoop Cable Pigtail](https://betafpv.com/collections/accessories/products/bt2-0-1s-whoop-cable-pigtail) — select **BT2.0 Cable Pigtail**, SKU 00313631 | 1 six-pack; fit one pigtail | $5.99 |

This core order totals **$42.22 plus GBP 6.49**, before frame, carrier, small
electronics, shipping and taxes. This is not the complete aircraft checkout.
The motor, propeller and charger stock/price were also checked against their
retailers' public product-variant data; all were available at the time of checking.
An extra propeller set is useful but is not included in the subtotal.

The remaining electrical parts are listed below so they can be sourced together.
They are **bench component candidates**, not a released carrier assembly BOM:
package fit, supply ripple, current handling and assembled mass still require
the finished schematic/layout and physical measurements. Small-component prices
and minimum quantities must be reconfirmed in the cart.

| Component reference | Quantity used on one aircraft | Ordering note |
| --- | ---: | --- |
| [AOS AO3400A, SOT-23, LCSC C20917](https://www.lcsc.com/product-detail/MOSFETs_Alpha-Omega-Semicon_C20917.html) | 4 | Listed minimum 5, about $0.43 per five |
| [MDD SS34, SMA, LCSC C8678](https://www.lcsc.com/product-detail/C8678.html) | 4 | Listed minimum 20, about $0.70 per twenty |
| [100 ohm, 0805, 1%, C17408](https://www.lcsc.com/product-detail/C17408.html) | 4 | MOSFET gate resistors |
| [10 kohm, 0805, 1%, C17414](https://www.lcsc.com/product-detail/C17414.html) | 4 | MOSFET gate pulldowns |
| [100 kohm, 0805, 1%, C149504](https://www.lcsc.com/product-detail/C149504.html) | 2 | Battery measurement divider |
| [100 nF, 50 V X7R, 0805, C1711](https://www.lcsc.com/product-detail/C1711.html) | 6 | Four motor suppression, one electronics decoupling, one ADC filter |
| [470 uF, 10 V, SAMYOUNG KMG, C349987](https://www.lcsc.com/product-detail/Aluminum-Electrolytic-Capacitors-Leaded_SamYoung-Electronics_C349987.html) | 1 | Provisional motor-supply bulk capacitor; validate ripple/ESR under motor load |
| [47 uF, 10 V, SAMYOUNG CLZ, C41428003](https://www.lcsc.com/product-detail/C41428003.html) | 1 | Provisional electronics supply capacitor |
| [26 AWG silicone wire](https://www.adafruit.com/category/product/1970) | Short signal/individual motor leads as needed | Reuse supplied motor leads; keep the main battery lead at the pigtail's 22 AWG |

Print one [Scout 110 frame](../frames/scout-110.scad) with
[common.scad](../frames/common.scad) alongside it for **dry fitting**. The frame
and camera/battery mounting are not mechanically qualified. **Do not order a
custom carrier PCB yet**: fabrication files and a released assembly drawing do
not exist. Strap, strain relief and fastening details depend on that final fit.

Shared bench equipment, separate from aircraft cost:

- [VIFLY WhoopStor 3](https://viflydrone.com/collections/lipro-battery-charger/products/vifly-whoopstor-6-ports-1s-battery-storage-charger-discharger),
  $32.99: BT2.0 charging with selectable 4.20 V. Start at **4.20 V / 0.3 A** for
  this 450 mAh pack. It needs a suitable power source; use a compatible USB-C PD
  supply meeting the manufacturer's 40 W input specification, not a plain 5 V
  USB port. Reuse a suitable supply if already owned. The manufacturer charger
  plus 65 W US supply bundle was unavailable when checked.
- USB-C **data** cable for flashing, soldering equipment, a multimeter, and a
  scale for assembled mass/thrust measurements. Reuse existing tools. Initial
  camera/IMU checks and motor-output checks are performed without propellers.

The earlier $45.09 consumed-parts estimate is retained above for traceability.
It is not a promise of a delivered build below $50; charger, spare inventory and
multiple sellers' shipping alone make that an inappropriate first-order budget.

## Work required before the first flight

1. Finish/review the schematic and carrier, dry-fit the frame, and document the
   as-built power wiring, motor order and sensor orientation.
2. Implement onboard IMU estimation, stabilization, mixer, arming, battery
   monitoring and watchdog/command-loss handling. Verify timing while camera
   streaming is active. **Current camera-only firmware holds motor outputs low.**
3. Connect physical timestamped camera/IMU telemetry to Drone137; validate stale
   data rejection, exclusive control, operator stop and link-loss behaviour on
   the actual board. Host tests against the protocol emulator do not do this.
4. Measure mass, propulsion/current, battery sag and vibration; update the SQLite
   component revisions and repeat the relevant simulations. Complete restrained
   motor/control checks before a brief guarded hover in a protected test space.
5. Demonstrate real indoor position/height feedback and recovery before enabling
   room navigation or mapping. The MPU-6050 is not an indoor position sensor.
   Additional navigation hardware is not yet specified or included in this order.

Current readiness: **parts procurement and camera bench work can begin; physical
flight remains disabled and unqualified**. There has been no hardware flight.

Use the [simulation/real-drone comparison section](../../../../docs/test-comparison.md)
to retain the existing baseline and record the physical measurements. It includes
exact historical results, configuration/source hashes and a blank physical-run
template. Do not overwrite earlier results when measured components are added.

## Battery and mass

Use **one purchased 1S pack**, not a home-built parallel pack. Limit charging to
**4.20 V** for the initial aircraft electronics/motor design. Although this cell
is sold for 4.35 V charging, the current component model limits propulsion to
4.20 V; a 4.35 V fully charged pack is outside this build configuration.
Use a suitable external BT2.0 1S charger set to 4.20 V. Disconnect the flight
battery during initial USB camera setup.

The manufacturer lists 12.7 g for the pack. The registry adds a provisional 1 g
pigtail, estimates usable capacity at 400 mAh under the lower charge limit, and
assumes 0.10 ohm pack resistance. **Capacity and resistance are hypotheses**, not
manufacturer specifications. The assembled mass hypothesis is **63.26 g**;
weigh the real frame, wires, boards and pack before replacing the SQLite values.

The tested `scout-110-power-v2` simulation uses a different, hypothetical 1S2P
480 mAh pack. Its mission result must not be transferred to this purchase build.
`scout-110-bench-b@1` is registered separately in SQLite with frozen component
references and explicit evidence labels. Both configurations remain disabled for
physical operation.

The final **qualification-04** batch tested this Scout 110-B assembly directly:
**24/24 complete simulated missions passed**, with zero false confirmations and
zero missed targets. Peak application memory was 4.26 GiB on a 16 GiB host;
actual 8 GB hardware remains untested. Largest location error was 0.662 m against
the unchanged 0.75 m tolerance; the longest mission took 287 seconds against a
300-second deadline. See the [full qualification](../../../../docs/mission-integration-validation.md).
These are three repeats of eight known synthetic cases with an ideal external
position reference and full modeled batteries, not real-world flight validation.

The initial component-only run completed six 20-second scenarios: **5/6 flight
checks passed**. Nominal, gust, link loss, weak motor and pessimistic assumptions
completed; low battery failed. Only **4/6** met the separate 2:1 thrust-reserve
engineering gate. See [the complete results](simulation-checks.json). These use
estimated propulsion and battery parameters, test no image recognition, and do
not establish readiness for physical flight.

## Assemble and bring up in this order

1. **Camera first, motors disconnected.** Order the Sense version with its camera
   and antenna. Use [camera_bench.ino](../../camera_bench/camera_bench.ino) and the
   existing [bench instructions](../../README.md#vision-path-that-can-be-tested-now).
   The actual shipped camera can be OV3660 or OV5640 during Seeed's transition;
   record its sensor ID, verify focus and orientation, then measure frame latency.
   Camera-only firmware prints the sensor ID and holds all four motor gates low.
2. **Print and dry-fit the frame.** Motor diagonal 110 mm, nominal 8.6 mm bores,
   65 mm propellers with 1 mm hubs. Adjust bores to the actual print and motor.
   Check propeller/guard clearance, shaft engagement and guard stiffness. The
   CAD is an unprinted dimensional prototype. Centre the battery beneath the
   plate and keep the camera and antenna clear of props and motor wiring.
3. **Build the electrical carrier with the propellers removed.** Follow the
   [connection schedule](../../connections.json) and
   [electrical instructions](../../README.md#electrical-connections). The ESP32
   GPIO drives a MOSFET gate, never a motor directly. Verify the actual IMU board
   input regulator and 3.3 V I2C levels; confirm its chip identity and orientation.
4. **Measure the exact propulsion and pack.** Record per-motor thrust/current/RPM
   versus duty and loaded voltage, pack sag/capacity, assembled mass and geometry.
   Save new component revisions in `/components`, preserving the original data.
   Repeat the simulation with those revisions. A different motor winding or prop
   pitch is a new propulsion measurement, even when its dimensions are identical.
5. **Flight-control bench testing precedes flight.** The firmware still needs
   IMU sampling/estimation, the onboard rate loop and mixer, bounded commands,
   telemetry, battery monitoring and command-loss behaviour under simultaneous
   Wi-Fi camera load. Real position feedback must replace the simulator's ideal
   reference before room navigation. Begin subsequent flight tests in a protected
   test space after these checks; simulation success alone is not that validation.

## What the simulation proves and what it assumes

The software test flies a component model through a detailed rendered room and
uses local models to inspect its camera images. Known room geometry and an ideal
external position reference remain inputs. It does not prove that an MPU-6050
alone supplies room coordinates, that the selected Wi-Fi camera maintains the
simulated quality, or that a cheap quad can fly autonomously without additional
positioning work. The benchmark images are 960 × 540; current camera bench code
uses 640 × 480. Re-run recognition at the measured real camera settings.

The hardware path is camera → local Wi-Fi → Drone137 on the ground PC → bounded
flight commands → onboard flight controller. The rapid stabilization loop belongs
on the drone, and the language models inspect images and propose mission actions
on the computer. The present camera bench implements the first part of that path.
