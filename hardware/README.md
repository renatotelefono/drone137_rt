# Hardware scope retained; construction blocked

## Five indoor candidates — 22 October 2026

The [indoor comparison and build catalog](esp32/indoor/report.html) defines five
camera-equipped designs: Micro 90 ($34.58), Scout 110 ($41.58), Guard 110 ($45.08),
Height 110 ($47.98), and Split 110 ($49.57). Budgets include one battery and guards,
use the higher listed 8520 motor/prop set price, and retain explicitly unquoted
allowances for other parts. They exclude shipping, tax, labour and shared ground
equipment. These are unbuilt candidates, not verified under-$50 purchases.

Each has a complete BOM, frame entry point and a row in the separate
[SQLite design catalog](esp32/indoor/catalog.sqlite3). Edit
[catalog.json](esp32/indoor/catalog.json) and regenerate with
`python hardware/esp32/indoor/build_catalog.py`. The generator checks costs,
nominal rotor/guard spacing and database integrity. It does not modify operational
airframe assignments or claim calibrated micro-drone flight simulation.

Start with Scout 110 for procurement and propulsion qualification. Height adds
downward ranging, while Split puts flight control on a second XIAO. All variants
reuse the ground-computer camera path; stabilization firmware, positioning and
the control transport remain integration work. Prepared indoor trials come first.

## ESP32 build requested — 22 October 2026

The latest target is a very light camera-equipped aircraft, possibly below $50
in parts. The [ESP32 build package](esp32/README.md) now defines a brushed micro
quad with a XIAO ESP32-S3 Sense, camera, motor-driver carrier and optional
flow/range sensor. Its [piece-by-piece BOM](esp32/bom.json) is $48.50 basic or
$69.00 with the navigation sensor pack, mostly unquoted allowances. These are
not verified purchase totals or flight-ready capabilities.

The package includes [a printable guide](esp32/drone137-esp32-build.docx), proposed
connections, an unprinted frame design, camera-only firmware and a Python
camera/model bench interface. All AI stays on the ground computer. The camera
firmware holds motor gates low; flight firmware, carrier PCB layout, positioning
and a non-PX4 vehicle adapter still require development and validation. See the
package validation record for the actual software checks. Physical vehicle
operation remains disabled. The earlier PX4/Pi design below is retained as an
alternative, not the current cost target.

## Cost-first ground computer architecture — 21 October 2026

All mission planning, model inference and reporting run on the ground computer.
The user rejected an onboard Jetson design. A small onboard Pi Zero 2 W remains
a proposed camera encoder and MAVLink bridge only; PX4 performs stabilization
and configured failsafes on the flight controller.

The user selected **cost first, aiming below $200 in aircraft parts**. The revised
[ground computer project](drone137-ground-computer-project.docx) specifies a
3.5-inch quad with an integrated MicoAir743v2-AIO-35A controller/ESC board,
IMX219 camera, Pi Zero 2 W and downward optical flow/range sensor. Its provisional
mass range is 230–280 g including one battery and guards; no assembly was weighed.

The [costed BOM](ground-computer-bom.json) separates a **$256.48 prototype
allowance** from **$184.99 in unquoted procurement targets**. The under-$200 goal
is not yet achieved. Frame and motor reference offers were out of stock; several
other items remain allowances. The first prototype system totals $459.98 with
shared ground equipment and initial spares, excluding the existing computer,
tax, shipping, labour and contingency. Parts targets are not finished production
costs. Reproduce the document with `hardware/build_ground_computer_project.py`
using a Python environment containing `python-docx`.

The first proposed operating area is a prepared, cleared indoor test bay with
measured localization markers and adequate lighting/floor texture. Marker pose
estimation, real sensor fusion and physical transport are required integration
work. A downward flow/range sensor does not provide wall sensing or global room
position. Unfamiliar-room missions remain unqualified.

This is an engineering proposal, not a matched or flight-tested build. No
physical transport was enabled and no existing SQLite profile was changed.
The current registry limits and scaled x500 geometry cannot faithfully represent
the proposed micro quad; add suitable geometry, ranges and measured parameters
before claiming a corresponding simulation.

The original plan is preserved in `docs/project-brief.md`, sections 4 and 11–14.
Its 450–500 mm frame, MicoAir743-Lite and Camera Module 3 direction is historical;
the current cost-first proposal above supersedes it for new hardware selection.

No matched BOM, wiring validation, purchases, assembly, calibration, camera-link
test or physical flight is claimed. Supplier prices and compatibility statements
in the brief require fresh verification before a purchase decision.

The next hardware documentation task is A08. Physical work stays blocked until
the actual Mac passes virtual acceptance and the lean memory budget. Aircraft
construction and physical tests are performed by a human operator.
