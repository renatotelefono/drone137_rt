// Vertical XIAO Sense stack, camera facing +Y. A 6 mm strap retains the module.
// Clear envelope 23 x 19 x 14 mm; verify supplied module, lens and USB before use.
$fn=36;
board_width=23;
module cradle(){
  difference(){
    union(){
      translate([-14,-5,0])cube([28,10,2]);
      for(x=[-14,12])translate([x,-5,0])cube([2,10,24]);
      translate([-14,-5,0])cube([28,2,4]);
    }
    // Slots retain a strap without covering the center lens or antenna socket.
    for(x=[-14,12])translate([x-.1,-1,10])cube([2.2,3,6]);
    for(x=[-10,10])translate([x,2,-.1])cylinder(h=2.2,d=2.2);
  }
}
cradle();
