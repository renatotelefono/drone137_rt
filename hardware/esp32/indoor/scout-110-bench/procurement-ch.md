# Scout 110-B procurement from Switzerland — checked 24 October 2026

Prices in CHF include VAT; stock was read from the shop pages on the date above
and changes daily. The official parts list is [README.md](README.md); where this
sheet substitutes a part, the substitution is named and must be recorded as a
component revision before the simulation is rerun with measured values.

## Aircraft parts

| Part | Qty | Swiss source | Price | Stock on 24 Oct | If out of stock |
| --- | ---: | --- | ---: | --- | --- |
| XIAO ESP32-S3 **Sense** (SKU 113991115) | 1 | Galaxus 35506126; Bastelgarage | 19.90 | Out of stock at both | Mouser.ch or Digikey.ch (about CHF 11–12 plus shipping), or Seeed direct |
| GY-521 MPU-6050 | 1 | Bastelgarage 420350 (also Galaxus 36359715 at 18.90) | 10.90 | In stock | — |
| 8520 coreless motors, 1 mm shaft, 4 pcs | 1 pack | Galaxus/Bastelgarage DFRobot FIT0796 | — | Out of stock | Unmanned Tech UK pack 41C-069-230, GBP 6.49, the README's choice; direction is set by wiring on a brushed motor, so CW/CCW packs are not required |
| 65 mm two-blade propellers, **1.0 mm hub**, 2 CW + 2 CCW | 1 set | None in Switzerland | — | — | Gemfan 65MMS 1.0 mm 8-pack (4 CW + 4 CCW), EU shops about EUR 3; HQProp 65 mm ultralight 1 mm when stocked. Record the heavier Gemfan blade in the registry |
| 1S BT2.0 battery pack | 1 four-pack | fpvracing.ch SKU 174009 **Lava II 480 mAh 95C** | 28.90 | In stock, 1–2 days | The README's 450 mAh 30C pack is discontinued at fpvracing.ch; the Lava II is a substitution: record capacity, measured mass and resistance in the registry. Charge to 4.20 V |
| BT2.0 pigtail, 22 AWG, 6 pcs | 1 pack | fpvracing.ch SKU 152017 (U-pigtail) | 7.90 | In stock | — |
| Carrier PCB, 2 oz copper, assembled | 5 (minimum) | JLCPCB with SMT assembly from `carrier/` gerbers and netlist | about 60 | Order | AO3400A, SMA-packaged SS34, 0805 resistors and capacitors are all library parts there; the two radial electrolytics are hand-soldered |
| 470 µF 10 V radial, 6.3 mm body, 2.5 mm pitch | 1 | Distrelec or Mouser | about 1 | — | Galaxus sells reel quantities only |
| 47 µF 10 V radial, 5 mm body, 2 mm pitch | 1 | Distrelec or Mouser | about 1 | — | — |
| 100 nF ceramic, leaded, across each motor | 4 | Distrelec, Mouser or Bastelgarage | about 1 | — | — |
| M2 × 6 screws (A2) and M2 nuts; nylon M2 for the IMU tray | 1 each | Galaxus Toolcraft 8520452, EP 6052932; Bastelgarage nylon | about 15 | In stock | — |
| 26 AWG silicone wire, red and black | 1 m each | Bastelgarage or Galaxus RS PRO 9905591 | about 10 | In stock | — |

If the carrier is bought bare instead of assembled, the SMD parts are: 4 × AO3400A
(SOT-23; Reichelt, Mouser or Digikey), 4 × 3 A/40 V Schottky in **SMA (DO-214AC)**,
which is MDD's SS34 or onsemi MBRA340T3G (Distrelec 30443734), 4 × 100 Ω, 4 × 10 kΩ
and 2 × 100 kΩ 1 % in 0805, 2 × 100 nF 0805. The common SS34 from onsemi or Vishay
is the larger SMC package and does not fit the carrier.

## Bench equipment

| Item | Swiss source | Price | Stock on 24 Oct |
| --- | --- | ---: | --- |
| VIFLY WhoopStor 3 charger (4.20 V selectable, BT2.0 ports, storage mode) | fpvracing.ch SKU 302005 | 34.90 | Out of stock in every colour; FlyingTech UK GBP 27.90 as the alternative |
| USB-C PD supply, 45 W or more (the charger needs 9 or 12 V PD) | any | about 25 | — |
| Precision scale 0.01 g / 500 g, Purecrea MH-500 | Galaxus 54993706 | 25.90 | In stock |
| Multimeter with 10 A DC range, Uni-T UT139C | Galaxus 34370475 | 45.50 | In stock |
| USB-C data cable, soldering iron and solder | any | — | — |

## Not available from Galaxus

Propellers, the BT2.0 battery and pigtail, the charger and every SMD component.
Galaxus lists the resistors and ceramic capacitors only as full reels at over
CHF 100 each. fpvracing.ch (Swiss warehouse, CHF 5 flat shipping) covers the
battery and pigtail; the carrier is best ordered assembled from JLCPCB.
