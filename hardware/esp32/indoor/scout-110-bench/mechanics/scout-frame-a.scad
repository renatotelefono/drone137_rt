// Prototype A. +Y forward, +Z up. Four 8520 bores; nominal prop plane Z=12.
// STL geometry is checked, but printing, fit, stiffness and mass remain unmeasured.
use <../../frames/common.scad>
$fn=48;
mounts=[[-18,-17.5],[18,-17.5],[-18,17],[18,17]];
difference(){
  union(){
    difference(){
      indoor_frame(wheelbase=110,prop_diameter=65,bore=8.6,upper_hoops=false);
      // Replace the original close-set feet so the 20 mm battery cradle fits.
      for(x=[-10,10])for(y=[-9,9])translate([x-1.1,y-1.1,-14.1])cube([2.2,2.2,14.1]);
    }
    for(p=mounts)translate([p[0],p[1],1.5])cylinder(h=3.5,r=2.5);
    // Extend the existing feet to clear the strapped battery cradle.
    for(x=[-14,14])for(y=[-9,9])translate([x-1,y-1,-17])cube([2,2,18]);
  }
  for(p=mounts)translate([p[0],p[1],-1])cylinder(h=7,d=2.2);
}
