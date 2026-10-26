# Scout 110-B procurement from Switzerland — checked 24 October 2026

Prices in CHF include VAT; stock was read from the shop pages on the date above
and changes daily. The official parts list is [README.md](README.md); where this
sheet substitutes a part, the substitution is named and must be recorded as a
component revision before the simulation is rerun with measured values.

## Aircraft parts — buy links, every link opened and checked on 25 October 2026

Prices in CHF unless marked. "Checked" means the page was opened on that day and showed the stated stock.

| Part | Qty | Buy | Price | Stock on 25 Oct | If out of stock |
| --- | ---: | --- | ---: | --- | --- |
| XIAO ESP32-S3 Sense, Seeed 113991115 | 1 | [DigiKey.ch](https://www.digikey.ch/en/products/result?keywords=113991115), ships to Switzerland, free over 70 | about 12 | Listed, no stock shown, lead time 4 weeks | [Seeed Studio direct](https://www.seeedstudio.com/XIAO-ESP32S3-Sense-p-5639.html) ships to CH; Swiss shops were all out: [Bastelgarage](https://www.bastelgarage.ch/seeed-studio-xiao-esp32-s3-sense-with-camera) 19.90, [Pi-Shop](https://www.pi-shop.ch/seeed-studio-xiao-esp32-s3-sense) 15.30, [Galaxus](https://www.galaxus.ch/en/s1/product/seeed-studio-xiao-esp32-s3-sense-mit-kamera-single-board-computer-kits-35506126); set a restock alert on one of them |
| GY-521 MPU-6050 | 1 | [Bastelgarage](https://www.bastelgarage.ch/mpu-6050-3-axis-accelerometer-with-gyroscope) | 10.90 | In stock | [Galaxus](https://www.galaxus.ch/en/s1/product/purecrea-mpu-6050-3-axis-accelerometer-with-gyroscope-single-board-computer-kits-36359715) 18.90, in stock |
| 8520 coreless motors, 1.0 mm shaft, 2 CW + 2 CCW | 1 pack | [Unmanned Tech UK](https://www.unmannedtechshop.co.uk/products/8520-coreless-brushed-motor-pack-2-x-cw-2-x-ccw), ships to CH | GBP 6.49 | In stock | Swiss stock was zero: [Bastelgarage DFRobot pack](https://www.bastelgarage.ch/8-5x20mm-coreless-micro-motor-4pcs) 14.90 and [Galaxus](https://www.galaxus.ch/en/s5/product/dfrobot-85x20mm-coreless-micro-motor-4pcs-rc-motors-43699838) both out; rotation direction is set by wiring, so any 8520 pack works |
| 65 mm two-blade props, 1.0 mm hub, 4 CW + 4 CCW | 1 set | [GetFPV, Gemfan 65 mm 1 mm shaft, set of 8](https://www.getfpv.com/propellers/micro-quad-propellers/gemfan-65mm-micro-propellers-1mm-shaft-set-of-8.html) (US) | USD 3.99 | Listed | No Swiss or EU shop had a 1.0 mm hub 65 mm prop on 25 Oct (OneDrone's listing is dead, fpvframe's HQProp 65 mm has 1.5 mm holes, Unmanned Tech's HQProp has 1.2 mm). [RaceDayQuads](https://www.racedayquads.com/products/gemfan-65mm-bi-blade-2-5-prop-8-pack-1mm-shaft-choose-your-color) (US) is the second source. Order two sets; record the blade mass in the registry |
| 1S BT2.0 battery pack | 1 four-pack | [fpvracing.ch, BETAFPV Lava II 480 mAh 95C](https://fpvracing.ch/en/1s/4197-betafpv-lava-ii-480mah-1s-95c-bt20-4-pcs.html) | 28.90 | In stock | Substitution for the discontinued 450 mAh 30C pack; charge to 4.20 V; record mass and resistance |
| BT2.0 pigtail, 6 pcs | 1 pack | [fpvracing.ch U-pigtail](https://fpvracing.ch/en/connectivity/4261-bt20-u-pigtail.html) | 7.90 | In stock | [BT2.0 to PH2.0 adapter](https://fpvracing.ch/en/connectivity/2912-bt20-ph20-adapter-cable.html) if a PH2.0 charger is used |
| Carrier PCB, 2 oz copper, assembled | 5 min. | [JLCPCB](https://jlcpcb.com/) from `carrier/` gerbers with SMT assembly | about 60 | Order | AO3400A, SMA-packaged SS34, 0805 parts are library parts; the two radial electrolytics are hand-soldered |
| C1: 470 µF 10 V radial, 6.3 mm body, 2.5 mm pitch | 1 | [Distrelec, Panasonic EEUEB1A471, art. 304-29-110](https://www.distrelec.ch/en/p/30429110) | 3.40 | 195 in stock | The 8 mm-body parts in the same search do not fit the footprint |
| C2: 47 µF radial, 5 mm body, 2 mm pitch | 1 | [Distrelec, Panasonic EEUFC1C470 16 V, art. 304-29-714](https://www.distrelec.ch/en/p/30429714) | 1.69 | 1190 in stock | 16 V is fine on a 1S supply; the older pack 300-13-731 is discontinued |
| 100 nF ceramic, leaded, one across each motor | 4 | [Bastelgarage ceramic set, 300 pcs](https://www.bastelgarage.ch/keramik-kondensator-set-300-stuck-assortiert) | 9.90 | In stock | — |
| M2 nylon screws, nuts and spacers (IMU tray, nonconductive) | 1 set | [Bastelgarage 260-piece M2 nylon set](https://www.bastelgarage.ch/sechskant-m2-distanzbolzen-abstandhalter-nylon-260-stuck) | 14.90 | In stock | — |
| M2 × 5 stainless screws and M2 nuts (camera cradle) | 1 pack each | [Bastelgarage M2 × 5, 10 pcs](https://www.bastelgarage.ch/10-stuck-m2x5mm-linsenkopfschrauben-set-rostfrei), [Bastelgarage M2 nuts, 10 pcs](https://www.bastelgarage.ch/10-stuck-m2-mutter-set-rostfrei) | 3.90 + 2.90 | In stock | M2 × 6 and × 10 packs were out at Bastelgarage and [Galaxus Toolcraft](https://www.galaxus.ch/de/s4/product/toolcraft-zylinderschrauben-m2-6-mm-inne-100stk-schrauben-8520452); × 5 reaches through the 2 mm cradle wall and the board |
| Flexible wire, red and black, 24 to 26 AWG | 1 m each | [Bastelgarage wire category](https://www.bastelgarage.ch/kabel-litzen/litzen-drahte) | about 8 | In stock | — |

Aircraft total, one airframe with spares in the packs: about CHF 180 including the PCB run.

## Bench equipment — buy links, checked 25 October 2026

| Item | Buy | Price | Stock on 25 Oct |
| --- | --- | ---: | --- |
| VIFLY WhoopStor 3 charger, 4.20 V selectable, BT2.0 ports | [fpvframe.ch](https://fpvframe.ch/product/vifly-whoopstor-3/) | 28 to 32 | 2 left; [fpvracing.ch](https://fpvracing.ch/en/charger/3799-vifly-whoopstor-v3-charger-bt20-ph20.html) 34.90 out of stock in all colours; [FlyingTech UK](https://www.flyingtech.co.uk/product/vifly-whoopstor-v3-1s-lipo-battery-charger-discharger-ph2-bt2-0/) GBP 27.90, 3 left |
| USB-C PD supply | [Galaxus InLine 65 W, 3 ports](https://www.galaxus.ch/de/s1/product/inline-usb-pd-netzteil-65-w-usb-ladegeraet-37345173) or [45 W single port](https://www.galaxus.ch/de/s1/product/45w-usb-c-wandladegeraet-45-w-1-port-usb-ladegeraet-47506670) | 26.50 / 14.10 | 8 in stock / more than 10 |
| Precision scale 0.01 g, 500 g | [Galaxus Purecrea MH-500](https://www.galaxus.ch/en/s12/product/purecrea-mh-500-precision-scales-54993706) | 25.90 | In stock |
| Multimeter, 10 A DC, true RMS | [Galaxus Uni-T UT139C](https://www.galaxus.ch/de/s4/product/uni-t-ut139c-cat-iii-600v-hand-multimeter-multimeter-34370475) | 45.50 | 10 in stock |
| USB-C data cable, soldering iron, 0.5 mm solder | Any Galaxus listing | about 40 | — |

Bench total: about CHF 170.

## Bench platform while the Scout parts ship

| Item | Buy | Price |
| --- | --- | ---: |
| Seeed ESP-FLY kit, XIAO ESP32-S3 based micro drone | [Seeed Studio](https://www.seeedstudio.com/ESP-FLY-co-create-p-6744.html), ships to CH | USD 59.99 |
| Plus one XIAO ESP32-S3 Sense from the first table if the kit variant ships without it | | about 12 |

## What the airframe looks like

`mechanics/scout-110b-views.png` (isometric, top, front, side with dimensions) and `mechanics/scout-110b-three-quarter-low.png` are rendered from the STL files by `mechanics/render_views.py` with numpy and Pillow only; no OpenSCAD needed. Envelope: 148 mm over the prop guards, 110 mm motor to motor, 64 mm from the battery underside to the top of the XIAO. Forward is the camera side.

## Not available from Galaxus

Propellers, the BT2.0 battery and pigtail, the charger and every SMD component.
Galaxus lists the resistors and ceramic capacitors only as full reels at over
CHF 100 each. fpvracing.ch (Swiss warehouse, CHF 5 flat shipping) covers the
battery and pigtail; the carrier is best ordered assembled from JLCPCB.
## Dock A parts — buy links, checked 25 October 2026

One dock per aircraft. Geometry and wiring are in `dock/README.md`.

| Part | Qty | Buy | Price | Stock on 25 Oct | Note |
| --- | ---: | --- | ---: | --- | --- |
| Dock controller, XIAO ESP32-C3 | 1 | [Bastelgarage](https://www.bastelgarage.ch/seeed-studio-xiao-esp32-c3) | 9.90 | In stock | [XIAO ESP32-S3](https://www.bastelgarage.ch/seeed-studio-xiao-esp32-s3) 11.90 also in stock if one board type is preferred |
| USB-C socket breakout with CC pull-downs | 1 | [Bastelgarage](https://www.bastelgarage.ch/usb-typ-c-buchse-breakout-board) | 4.90 | In stock | Not the 4-pin version; a PD supply needs the 5.1 kΩ CC resistors |
| INA219 current and voltage sensor | 1 | [Bastelgarage, DFRobot Gravity](https://www.bastelgarage.ch/gravity-ina219-i2c-digitales-wattmeter) | 12.90 | In stock | Charge current and 5 V telemetry |
| Spring contact pin | 1 | [Distrelec, PTR 5110/S-D-1.2N-AU-2.3C, 10 A, 15.2 mm](https://www.distrelec.ch/en/p/14022290) | 3.59 | To order | In stock alternative: [PTR 1060/G-A6X-3.0N-AU-3.0C](https://www.distrelec.ch/en/p/30019746) 6.50, 28.5 mm; set `pin_d` in `generate_dock.py` to the barrel diameter |
| Copper tape 20 mm, 10 m | 1 | [Bastelgarage](https://www.bastelgarage.ch/20mm-kupferklebeband-10m) | 14.90 | In stock | Foot strips, cradle disc and foot caps for every dock and aircraft |
| NTC 10 kΩ, insulated leads, pack of 25 | 1 | [Distrelec, Vishay NTCLE413E2103F520L](https://www.distrelec.ch/en/p/30438838) | 25.81 | 4125 in stock | One per dock; the pack lasts |
| Logic-level P-MOSFET, 5 V switch | 1 | Any AO3401A or IRLML6402 from the same JLCPCB run, or a Bastelgarage MOSFET module | about 2 | — | — |
| PETG, 1 kg | 1 | Bastelgarage eSun was out of stock in all colours on 25 Oct; any PETG | about 14 | — | About 150 g per dock at 15 % infill plus about 60 g for the stand |
| AprilTags | 3 | Print from [apriltag-imgs, tag36h11](https://github.com/AprilRobotics/apriltag-imgs/tree/master/tag36h11) at 40, 40 and 60 mm | 0 | — | ids 3k, 3k+1, 3k+2 for dock k |
| 5 V supply | 1 | The 45 W or 65 W PD supply from the bench list | — | — | One per dock |
| Version 2 only: Qi transmitter and receiver pair, 5 V 1 A | 1 | [Bastelgarage Wireless Charging Modul](https://www.bastelgarage.ch/wireless-charging-modul-5v-1a) | 10.90 | In stock | Receiver coil under the battery cradle feeds the same J18 / J19 pads; adds about 5 g to the aircraft |

Dock total: about CHF 75 in parts per dock plus a share of the thermistor pack and the tape roll; about CHF 90 for the first one.

