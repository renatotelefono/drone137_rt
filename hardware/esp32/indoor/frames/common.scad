// Dimensional prototypes only: no printed-fit, stiffness, mass or flight validation.
// Coordinate convention: +Y forward; Z up. All dimensions are millimetres.
module indoor_frame(wheelbase=110, prop_diameter=65, bore=8.6, upper_hoops=false) {
  $fn=48;
  a=wheelbase/(2*sqrt(2));
  ri=prop_diameter/2+1.5;
  ro=ri+1.2;
  pts=[[a,a],[a,-a],[-a,-a],[-a,a]];
  assert(2*a>2*ro, "Adjacent guards intersect");
  module ring(outside,inside,height) {
    difference() {
      cylinder(h=height,r=outside);
      translate([0,0,-.1]) cylinder(h=height+.2,r=inside);
    }
  }
  module arm(p) {
    hull() {
      cylinder(h=2,r=2);
      translate([p[0],p[1],0]) cylinder(h=2,r=2);
    }
  }
  module hoop() {
    // Segmented upper half-circle entirely above the proposed z=12 prop plane.
    for(t=[0:10:170]) hull() {
      translate([ro*cos(t),0,16+ro*sin(t)]) sphere(r=.7);
      translate([ro*cos(t+10),0,16+ro*sin(t+10)]) sphere(r=.7);
    }
  }
  difference() {
    union() {
      translate([-15,-12,0]) cube([30,24,2]);
      for(p=pts) {
        arm(p);
        translate([p[0],p[1],0]) {
          ring(bore/2+1,bore/2,8);
          translate([0,0,8]) ring(ro,ri,8);
          for(t=[0,90,180,270]) rotate([0,0,t]) {
            translate([ri,-.8,0]) cube([1.2,1.6,8]);
            translate([bore/2,-.8,0]) cube([ro-bore/2,1.6,2]);
          }
          if(upper_hoops) { hoop(); rotate([0,0,90]) hoop(); }
        }
      }
      for(x=[-10,10]) for(y=[-9,9]) translate([x-1,y-1,-14]) cube([2,2,14]);
    }
    for(x=[-12,12]) translate([x-1,-6,-.1]) cube([2,12,2.2]);
    for(p=pts) translate([p[0],p[1],-.1]) cylinder(h=8.2,r=bore/2);
  }
}
