// GY-521 clearance envelope 22 x 17 mm; rigid attachment plus nonconductive strap.
// Keep module horizontal. Verify printed sensor axis marks before commissioning.
difference(){
  union(){
    translate([-12,-9.5,0])cube([24,19,1.2]);
    for(x=[-12,11])translate([x,-9.5,0])cube([1,19,3]);
  }
  for(x=[-10.5,8.5])translate([x,-3,-.1])cube([2,6,1.4]);
}
