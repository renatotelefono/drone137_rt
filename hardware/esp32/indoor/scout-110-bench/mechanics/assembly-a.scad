// Visual fit reference only; colored boxes are nominal component envelopes.
// +Y forward, +Z up. Millimetres. No wire, tolerancing or material strength model.
color("darkslategray") import("scout-frame-a.stl");
color("seagreen")translate([-21,-20,5])cube([42,40,1]);
color("silver")translate([0,0,7])import("electronics-bridge-a.stl");
color("orange")translate([0,8,23])import("camera-cradle-a.stl");
color("teal")translate([-11.5,5,25])cube([23,7,19]);
color("orange")translate([0,-7,23])import("imu-tray-a.stl");
color("blue")translate([-11,-15.5,24.2])cube([22,17,1.6]);
color("orange")translate([0,0,-12])import("battery-cradle-a.stl");
color("gold")translate([-9,-31,-10.8])cube([18,62,8]);
for(p=[[38.8909,38.8909],[38.8909,-38.8909],[-38.8909,-38.8909],[-38.8909,38.8909]]){
 color("silver")translate([p[0],p[1],-9])cylinder(h=20,d=8.5,$fn=48);
 color([.4,.5,.9,.3])translate([p[0],p[1],12])cylinder(h=.3,d=65,$fn=72);
}
// Carrier capacitor envelopes: verify purchased lead pitch, body diameter/height.
color("black")translate([6,15.5,6])cylinder(h=12,d=6.3,$fn=32);
color("black")translate([13,-1,6])cylinder(h=11,d=5,$fn=32);
