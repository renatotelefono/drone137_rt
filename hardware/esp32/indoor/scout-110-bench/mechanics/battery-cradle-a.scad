// Clearance envelope, not a claim about a shipped cell: 62 x 18 x 8 mm.
// Cradle is strapped beneath the center plate; pack and pigtail remain removable.
$fn=24;
difference(){
  union(){
    translate([-10,-32,0])cube([20,64,1.2]);
    for(x=[-10,9])translate([x,-32,0])cube([1,64,4]);
    for(y=[-32,31])translate([-10,y,0])cube([20,1,3]);
  }
  for(x=[-9,7])translate([x,-4,-.1])cube([2,8,1.4]);
  // Keep material around strap/edges while reducing mass.
  for(y=[-22,14])translate([-6,y,-.1])cube([12,10,1.4]);
}
