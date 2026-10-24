// Bottom rests on insulated PCB spacers at assembly Z=7; deck top is Z=23.
// Same asymmetric four-hole pattern as the carrier. +Y toward battery-edge/front.
$fn=32;
mounts=[[-18,-17.5],[18,-17.5],[-18,17],[18,17]];
difference(){
 union(){
  translate([0,0,15])linear_extrude(1)polygon([[-10,-13],[10,-13],[13,-10],[13,10],[10,13],[-10,13],[-13,10],[-13,-10]]);
  for(p=mounts){
   hull(){translate([p[0],p[1],0])cylinder(h=2,r=2.5);translate([p[0]*.5,p[1]*.5,0])cylinder(h=2,r=2.5);}
   translate([p[0]*.5,p[1]*.5,0])cylinder(h=16,r=2.5);
  }
 }
 for(p=mounts)translate([p[0],p[1],-.1])cylinder(h=2.2,d=2.2);
 for(x=[-10,10])translate([x,10,14.9])cylinder(h=1.2,d=2.2);
 for(x=[-8,6])translate([x,-10,14.9])cube([2,6,1.2]);
}
