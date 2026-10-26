// Dock A for the Scout 110-B. Table at Z=0, pocket floor at Z=floor_z, +Y toward the backboard
// (the Scout's forward, camera side). Same geometry as generate_dock.py, which writes the STL files.
$fn=64;
pocket=150;   // square pocket, about 0.9 mm per side around the 148.2 mm guard envelope
run=25;       // horizontal capture run of the funnel per side
slope=30;     // funnel wall angle from horizontal, above the PETG-on-PETG friction angle
wall=3; floor_z=25; floor_t=3;
boss_d=8; boss_h=4; pin_d=2; pin=[0,9];   // charge pin under the forward cradle contact
board_w=140; board_t=3; board_h=240; board_foot=100; tags=[[40,82],[40,142],[80,195]];   // [size, centre above table]; camera at Z=82 when docked
top=floor_z+run*tan(slope); opening=pocket+2*run; outer=opening+2*wall;
module body(){
  difference(){
    translate([-outer/2,-outer/2,0])cube([outer,outer,top]);
    hull(){
      translate([0,0,top+1])linear_extrude(.01)square(opening+2/tan(slope),center=true);
      translate([0,0,floor_z])linear_extrude(.01)square(pocket,center=true);
    }
    translate([-opening/2,-opening/2,-1])cube([opening,opening,floor_z-floor_t+1]);   // electronics bay, open below
    translate([pin[0],pin[1],floor_z-floor_t-1])cylinder(h=floor_t+boss_h+2,d=pin_d,$fn=24);
  }
  translate([pin[0],pin[1],floor_z-.01])difference(){
    cylinder(h=boss_h,d=boss_d);
    translate([0,0,-1])cylinder(h=boss_h+2,d=pin_d,$fn=24);
  }
}
module backboard(){   // L-shaped stand: the foot butts against the dock's +Y wall, the plate stands board_foot in front of it
  translate([-board_w/2,outer/2,0])cube([board_w,board_foot+board_t,board_t]);
  translate([-board_w/2,outer/2+board_foot,0])cube([board_w,board_t,board_h]);
}
body(); backboard();
// Tag outlines for reference only: tag36h11 ids 3k, 3k+1, 3k+2 for dock k, lowest at camera height, the 80 mm one for far acquisition.
for(t=tags)%translate([-t[0]/2,outer/2+board_foot-.1,t[1]-t[0]/2])cube([t[0],.1,t[0]]);
