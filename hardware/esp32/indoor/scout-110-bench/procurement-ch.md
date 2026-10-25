# Scout 110-B procurement from Switzerland — checked 24 October 2026

Prices in CHF include VAT; stock was read from the shop pages on the date above
and changes daily. The official parts list is [README.md](README.md); where this
sheet substitutes a part, the substitution is named and must be recorded as a
component revision before the simulation is rerun with measured values.

## Aircraft parts — Swiss buy links, checked 25 October 2026

| Part | Qty | Buy | Price | Stock | If out of stock |
| --- | ---: | --- | ---: | --- | --- |
| XIAO ESP32-S3 Sense, SKU 113991115 | 1 | [Digikey.ch](https://www.digikey.ch/en/products/result?keywords=113991115), ships to CH in about 48 h | about 12 | Listed | [Bastelgarage](https://www.bastelgarage.ch/seeed-studio-xiao-esp32-s3-sense-with-camera) 19.90 and [Galaxus](https://www.galaxus.ch/en/s1/product/seeed-studio-xiao-esp32-s3-sense-mit-kamera-single-board-computer-kits-35506126) were out of stock; [Pi-Shop](https://www.pi-shop.ch/seeed-studio-xiao-esp32-s3-sense) too; Distrelec no longer lists it |
| GY-521 MPU-6050 | 1 | [Bastelgarage](https://www.bastelgarage.ch/mpu-6050-3-axis-accelerometer-with-gyroscope) | 10.90 | In stock | [Galaxus](https://www.galaxus.ch/en/s1/product/purecrea-mpu-6050-3-axis-accelerometer-with-gyroscope-single-board-computer-kits-36359715) 18.90 |
| 8520 coreless motors, 1 mm shaft, 4 pcs | 1 pack | [Unmanned Tech UK](https://www.unmannedtechshop.co.uk/products/8520-coreless-brushed-motor-pack-2-x-cw-2-x-ccw), ships to CH | GBP 6.49 | Listed | [Bastelgarage DFRobot pack](https://www.bastelgarage.ch/8-5x20mm-coreless-micro-motor-4pcs) and [Galaxus](https://www.galaxus.ch/en/s5/product/dfrobot-85x20mm-coreless-micro-motor-4pcs-rc-motors-43699838) when restocked; direction is set by wiring |
| 65 mm two-blade props, 1.0 mm hub, 4 CW + 4 CCW | 1 set | [GetFPV, Gemfan 65MMS 1 mm](https://www.getfpv.com/propellers/micro-quad-propellers/gemfan-65mm-micro-propellers-1mm-shaft-set-of-8.html) | USD 3.99 | Listed | No Swiss shop found; [HQProp 65 mm 1.2 mm at Unmanned Tech](https://www.unmannedtechshop.co.uk/products/hqprop-ultralight-65mm-2cw-2ccw-polycarbonate-1-2mm-shaft) when restocked. Record the Gemfan blade mass in the registry |
| 1S BT2.0 battery pack | 1 four-pack | [fpvracing.ch, BETAFPV Lava II 480 mAh 95C](https://fpvracing.ch/en/1s/4197-betafpv-lava-ii-480mah-1s-95c-bt20-4-pcs.html) | 28.90 | In stock | Substitution for the discontinued 450 mAh 30C pack; charge to 4.20 V; record mass and resistance |
| BT2.0 pigtail, 6 pcs | 1 pack | [fpvracing.ch U-pigtail](https://fpvracing.ch/en/connectivity/4261-bt20-u-pigtail.html) | 7.90 | In stock | [BT2.0 to PH2.0 adapter](https://fpvracing.ch/en/connectivity/2912-bt20-ph20-adapter-cable.html) if a PH2.0 charger is used |
| Carrier PCB, 2 oz copper, assembled | 5 min. | [JLCPCB](https://jlcpcb.com/) from `carrier/` gerbers with SMT assembly | about 60 | Order | AO3400A, SMA-packaged SS34, 0805 parts are library parts; radial electrolytics hand-soldered |
| 470 µF 10 V radial, 6.3 mm body, 2.5 mm pitch (C1) | 1 | [Distrelec search](https://www.distrelec.ch/en/search?q=470uF%2010V%20radial%206.3mm) | about 1 | — | Match the 6.3 mm body and 2.5 mm pitch; the 8 mm/3.5 mm parts do not fit the footprint |
| 47 µF radial, 5 mm body, 2 mm pitch (C2) | 1 | [Distrelec, Panasonic EEUFC1C470, 16 V](https://www.distrelec.ch/en/radial-electrolytic-capacitor-47uf-52ua-16v-175ma-panasonic-eeufc1c470/p/30013731) | about 1 | Listed | 16 V is fine on a 1S supply |
| 100 nF ceramic, leaded, across each motor | 4 | [Distrelec, KEMET C320C104K1R5TA](https://www.distrelec.ch/de/keramikkondensator-100nf-100v-10-kemet-c320c104k1r5ta/p/30110850) | about 1 | Listed | [Bastelgarage ceramic set](https://www.bastelgarage.ch/keramik-kondensator-set-300-stuck-assortiert) |
| M2 nylon screws, nuts and spacers (IMU tray, nonconductive) | 1 set | [Bastelgarage 260-piece M2 nylon set](https://www.bastelgarage.ch/sechskant-m2-distanzbolzen-abstandhalter-nylon-260-stuck) | about 10 | In stock | — |
| M2 × 6 steel screws (camera cradle) and M2 nuts | 1 each | [Galaxus Toolcraft M2 × 6 A2](https://www.galaxus.ch/de/s4/product/toolcraft-zylinderschrauben-m2-6-mm-inne-100stk-schrauben-8520452), [EP M2 nuts](https://www.galaxus.ch/de/s4/product/ep-m2-mutter-schwarz-m2-muttern-unterlegscheiben-6052932) | about 15 | In stock | — |
| Flexible wire, red and black, 24 to 26 AWG | 1 m each | [Bastelgarage LifY wire](https://www.bastelgarage.ch/kabel-litzen/litzen-drahte) | about 8 | In stock | [Galaxus RS PRO 26 AWG](https://www.galaxus.ch/de/s4/product/rs-pro-ul3266-hook-up-wire-26awg-black-100m-100-m-kabelleitung-9905591) |

## Bench equipment — Swiss buy links

| Item | Buy | Price | Stock |
| --- | --- | ---: | --- |
| VIFLY WhoopStor 3 charger, 4.20 V selectable, BT2.0 ports | [fpvracing.ch](https://fpvracing.ch/en/charger/3799-vifly-whoopstor-v3-charger-bt20-ph20.html) | 34.90 | Out of stock in all colours on 25 Oct; [FlyingTech UK](https://www.flyingtech.co.uk/product/vifly-whoopstor-v3-1s-lipo-battery-charger-discharger-ph2-bt2-0/) GBP 27.90, or [BETAFPV 6-port BT2.0 charger at fpvframe.ch](https://fpvframe.ch/product/betafpv-6-ports-1s-battery-charger-bt2-0/) if it offers a 4.20 V mode |
| USB-C PD supply, 45 W or more | [Galaxus InLine 65 W GaN](https://www.galaxus.ch/de/s1/product/inline-usb-pd-netzteil-65-w-usb-ladegeraet-37345173) or [45 W single port](https://www.galaxus.ch/de/s1/product/45w-usb-c-wandladegeraet-45-w-1-port-usb-ladegeraet-47506670) | 28.70 / 13.40 | In stock |
| Precision scale 0.01 g / 500 g | [Galaxus Purecrea MH-500](https://www.galaxus.ch/en/s12/product/purecrea-mh-500-precision-scales-54993706) | 25.90 | In stock |
| Multimeter, 10 A DC, true RMS | [Galaxus Uni-T UT139C](https://www.galaxus.ch/de/s4/product/uni-t-ut139c-cat-iii-600v-hand-multimeter-multimeter-34370475) | 45.50 | In stock |
| USB-C data cable, soldering iron, 0.5 mm solder | Any Galaxus listing | about 40 | — |

## Bench platform while the Scout parts ship

| Item | Buy | Price |
| --- | --- | ---: |
| Seeed ESP-FLY kit, XIAO ESP32-S3 based micro drone | [Seeed Studio](https://www.seeedstudio.com/ESP-FLY-co-create-p-6744.html), ships to CH | USD 59.99 |
| Plus one XIAO ESP32-S3 Sense from the first table | | about 12 |

## Not available from Galaxus

Propellers, the BT2.0 battery and pigtail, the charger and every SMD component.
Galaxus lists the resistors and ceramic capacitors only as full reels at over
CHF 100 each. fpvracing.ch (Swiss warehouse, CHF 5 flat shipping) covers the
battery and pigtail; the carrier is best ordered assembled from JLCPCB.
