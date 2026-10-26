# Dock A for the Scout 110-B

A landing base that recharges the Scout without anyone touching it. Prototype A uses
contact charging: the aircraft lands, slides to the centre of a funnel, and two copper
foot strips plus one spring pin under the battery cradle connect it to 5 V. An
inductive (Qi) variant is the planned version 2 and changes nothing on the aircraft
except the source of the 5 V. The flight procedure that brings the aircraft onto the
dock is specified in [`docs/docking.md`](../../../../../docs/docking.md).

Status: geometry generated and checked, nothing printed, nothing measured.

## Files

| File | What it is |
| --- | --- |
| `generate_dock.py` | Writes `dock-body-a.stl` and `dock-backboard-a.stl` (ASCII) and `clearance-checks.json` with numpy only |
| `dock-a.scad` | The same geometry as OpenSCAD for anyone editing it there |
| `render_dock.py` | Renders `dock-a-views.png` (docked three-quarter, top, side, empty dock) through `../mechanics/render_views.py` |
| `clearance-checks.json` | Pocket clearance, pin compression, tag visibility over the descent, solid volumes |
| `../mechanics/mesh-checks.json` | Manifold check for the dock meshes, written by `../check_mechanics.py` |

## Geometry

Table at Z = 0, pocket floor at Z = 25, +Y toward the tag stand, which is the Scout's
forward (camera) side when docked. The dock frame used by the software has its origin at
the pocket centre on the floor.

| Item | Value | Why |
| --- | ---: | --- |
| Pocket | 150 × 150 mm square | 0.9 mm per side around the 148.2 mm guard envelope; fixes the final position and yaw to 0 / 90 / 180 / 270 |
| Funnel | 25 mm run per side at 30° | Captures a touchdown error of ±25 mm; 30° is above the PETG-on-PETG friction angle, so the aircraft slides |
| Body | 206 × 206 × 39 mm | Fits a 220 mm print bed. The bay under the floor (200 × 200 × 22 mm, open below) holds the electronics |
| Floor | 3 mm, 25 mm above the table | Room for the pin, the controller and the USB-C socket |
| Contact boss | ⌀ 8 mm, 4 mm tall at (0, +9) | Under the solid part of the cradle floor, forward of the strap slot; a ⌀ 2 mm hole takes the spring pin |
| Spring pin | protrudes 2.5 mm at rest, compressed 1.5 mm | The cradle underside sits 5 mm above the feet; the boss top is 1 mm below it |
| Foot strips | copper tape 6 × 28 mm at x = ±14 | The feet stand at (±14, ±9); margin 3 mm in x and 5 mm in y |
| Tag stand | L plate 140 × 240 mm, foot 100 mm | Butts against the dock's +Y wall; the tag plane is 203 mm from the pocket centre, 191 mm from the docked camera |
| Tag column | tag36h11: 40 mm at 82 and 142 mm, 80 mm at 195 mm above the table | The lowest is at camera height when docked; with the profile camera (960 × 540, fx 722, pitched down 10°) one tag is always fully in view from below the docked height to about 200 mm above it, no gaps. The 80 mm tag is 58 px wide at 1 m for acquisition |

All of these are parameters at the top of `generate_dock.py`; the checks in
`clearance-checks.json` fail the script if a change breaks the fit.

## Electrical

```
PD supply 5 V ──USB-C socket──┬── INA219 (charge current, voltage) ── MOSFET switch ── spring pin (+5 V)
                              │                                                       foot strips (GND)
                              └── XIAO ESP32-C3: switch, INA219, pad NTC, status API
```

- The dock supplies 5 V only. Charging happens on the aircraft (carrier prototype B:
  PTC 0.5 A, MCP73831-2 at up to 500 mA with thermal fold-back, STAT to the XIAO).
  Any 5 V source works, so the Qi receiver of version 2 plugs into the same two pads.
- The controller measures current and voltage with the INA219, reads an NTC under the
  pocket floor, and switches the 5 V with a logic-level P-MOSFET. It cuts the 5 V at
  more than 0.7 A, above 45 °C on the pad, or after 3 h of charging, and serves the
  status API described in `docs/docking.md`.
- The pin and strips cannot be connected the wrong way round: the strips are at x = ±14
  and the pin at (0, +9), and a foot can never reach the pin. At yaw 180° the pin
  touches bare plastic, which is an open circuit, and the software re-docks.
- USB-C: the socket breakout must carry the 5.1 kΩ CC pull-downs, or a PD supply keeps
  its output off.

## Aircraft side

- Carrier prototype B adds J18 `CHG+`, J19 `CHG-` and J20 `D2 STAT`
  (`../generate_carrier.py`). Regenerate the KiCad files before ordering; the committed
  `../carrier/` outputs are still prototype A.
- A 10 mm copper-tape disc on the cradle underside at (0, +9), wired to J18. Copper tape
  caps on the lower 3 mm of the two feet at x = +14 (the other two optional), wired to
  J19. Mass added: under 1 g.
- Firmware: D2 / GPIO3 with pull-up reads STAT (low while charging). While STAT is low
  the motors stay locked. Docked and idle, the XIAO deep-sleeps and wakes every ten
  minutes to report the cell voltage.

## Printing and assembly

1. Print the body as modelled, pocket up, 0.2 mm layers, 3 walls, 15 % infill, PETG.
   The solid volume is 349 cm³; at 15 % infill expect roughly 150 g. The stand prints
   flat on its plate face; 240 mm fits a 250 mm bed, or diagonally on a 220 mm bed.
2. Ream the pin hole to the barrel of the chosen spring contact; press the pin in from
   above and solder its wire inside the bay.
3. Lay the two copper strips on the floor at x = ±14, centred on y = 0, and bring both
   to GND inside the bay through two 1.5 mm holes drilled beside the strips.
4. Fit the USB-C socket, INA219, MOSFET switch, NTC and XIAO in the bay; close it with a
   flat 199 × 199 × 2 mm lid or leave it open on a table.
5. Print the three tags (tag36h11, ids 3k, 3k+1, 3k+2 for dock k; 40, 40 and 80 mm
   outer black border) on matte paper and glue them centred at 82, 142 and 195 mm
   above the table.
6. Put the stand's foot against the dock's +Y wall and tape it down.
7. Place the Scout in the pocket by hand, feet on the strips, and confirm 5 V at J18
   and a charge current on the INA219 before any flight test.

## Not verified

Print fit, the slide on the funnel with real props stopping, contact wear, charge
heating on the carrier, and every number in the software procedure. The checks in
this folder are geometry only.
