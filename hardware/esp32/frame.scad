// drone137 revision A: UNPRINTED dimensional prototype, millimetres.
// Requires fit, prop clearance, stiffness, mass and thrust tests before use.
// Motors: 8.5 x 20 mm; top of can at z=8, bottom at z=-12.
// Proposed prop plane z=12; verify actual shaft/prop hub before assembly.
$fn = 64;
wheelbase = 100;             // diagonal motor centre distance
motor_bore = 8.6;            // tune for filament and selected motor; use retention rings
motor_wall = 1.0;
prop_radius = 27.5;
guard_inner = 29.0;
guard_wall = 1.2;
arm_width = 4.0;
plate = 2.0;
a = wheelbase / (2 * sqrt(2));
centres = [[a,a],[a,-a],[-a,-a],[-a,a]];
assert(guard_inner > prop_radius + 1);
assert(2*a > 2*(guard_inner+guard_wall));
module arm(p) { hull() { cylinder(h=plate,r=arm_width/2); translate([p[0],p[1],0]) cylinder(h=plate,r=arm_width/2); } }
module ring(ro,ri,h) { difference() { cylinder(h=h,r=ro); translate([0,0,-.1]) cylinder(h=h+.2,r=ri); } }
difference() {
  union() {
    translate([-15,-12,0]) cube([30,24,plate]);
    for(p=centres) {
      arm(p);
      translate([p[0],p[1],0]) {
        ring(motor_bore/2+motor_wall,motor_bore/2,8);
        translate([0,0,8]) ring(guard_inner+guard_wall,guard_inner,8);
        for(theta=[0,90,180,270]) rotate([0,0,theta]) {
          translate([guard_inner,-.8,0]) cube([guard_wall,1.6,8]);
          translate([motor_bore/2,-.8,0]) cube([guard_inner+guard_wall-motor_bore/2,1.6,plate]);
        }
      }
    }
    // Feet stop the motor bottoms contacting a flat bench; actual balance to verify.
    for(x=[-11,11]) for(y=[-8,8]) translate([x-1,y-1,-14]) cube([2,2,14]);
  }
  // Body strap slots; carrier and camera mounting are part of the assembly design.
  for(x=[-12,12]) translate([x-1,-7,-.1]) cube([2,14,plate+.2]);
  // Keep the full motor sleeve bore clear where arms cross it.
  for(p=centres) translate([p[0],p[1],-.1]) cylinder(h=8.2,r=motor_bore/2);
}
