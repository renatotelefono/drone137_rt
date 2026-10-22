// Local, procedural workshop assets. Visual parts stay inside conservative sensor bounds.
import * as THREE from './vendor/three.module.js';

export function workshopAssets(parent, world) {
 const materials = new Map(), geometries = new Map(), textures = new Map();
 const mat = (color, metalness=0) => {
  const key=`${color}/${metalness}`;
  if(!materials.has(key))materials.set(key,new THREE.MeshStandardMaterial({color,metalness,roughness:metalness?.45:.85}));
  return materials.get(key);
 };
 const geometry = (key, make) => {if(!geometries.has(key))geometries.set(key,make());return geometries.get(key);};
 function mesh(group,shape,material,x,y,z){const m=new THREE.Mesh(shape,material);m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;group.add(m);return m;}
 const box=(g,x,y,z,w,h,d,c,metal=0)=>mesh(g,geometry(`b/${w}/${h}/${d}`,()=>new THREE.BoxGeometry(w,h,d)),mat(c,metal),x,y,z);
 function cylinder(g,x,y,z,r,h,c){return mesh(g,geometry(`c/${r}/${h}`,()=>new THREE.CylinderGeometry(r,r,h,24)),mat(c,.3),x,y,z);}
 function line(g,points,r,color){const curve=new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(...p)));return mesh(g,new THREE.TubeGeometry(curve,24,r,6,false),mat(color),0,0,0);}
 function label(g,x,y,z,w,h,title,background='#ead8b2',ink='#27302c',angle=0){
  const key=[title,background,ink].join('/');
  if(!textures.has(key)){
   const c=document.createElement('canvas');c.width=512;c.height=256;const ctx=c.getContext('2d');
   ctx.fillStyle=background;ctx.fillRect(0,0,512,256);ctx.strokeStyle=ink;ctx.lineWidth=8;ctx.strokeRect(14,14,484,228);
   ctx.fillStyle=ink;ctx.font='bold 56px sans-serif';ctx.textAlign='center';
   title.split('\n').forEach((s,i)=>ctx.fillText(s,256,100+i*68,460));
   const texture=new THREE.CanvasTexture(c);texture.colorSpace=THREE.SRGBColorSpace;textures.set(key,texture);
  }
  const m=mesh(g,new THREE.PlaneGeometry(w,h),new THREE.MeshStandardMaterial({map:textures.get(key),roughness:1}),x,y,z);m.rotation.y=angle;return m;
 }
 function carton(g,x,y,z,w,h,d,index=0){
  box(g,x,y,z,w,h,d,['#ad8152','#c19a6a','#9c7248'][index%3]);
  box(g,x,y+h/2+.001,z,w*.15,.003,d,'#d7bd87');
  box(g,x,y,z-d/2-.003,w*.15,h,.004,'#d7bd87');
  label(g,x+w*.18,y,z-d/2-.006,w*.37,h*.48,index%2?'PARTS\n↑ ↑':'HANDLE\nWITH CARE','#e8ddbf','#29332d',Math.PI);
 }
 function pallet(g,w,d){
  for(const x of [-w*.35,0,w*.35])box(g,x,.055,0,w*.16,.11,d,'#8a6949');
  for(let i=0;i<5;i++)box(g,-w*.4+i*w*.2,.14,0,w*.16,.07,d,'#b38e60');
 }
 function barrel(g,x,z,color){
  cylinder(g,x,.63,z,.29,1.14,color);
  for(const y of [.1,.35,.89,1.17])cylinder(g,x,y,z,.302,.035,'#39464a');
  cylinder(g,x,.055,z,.29,.025,'#2d3636');
  label(g,x,.65,z-.296,.32,.3,'OIL','#d6b74b','#26302c',Math.PI);
  cylinder(g,x+.1,1.205,z+.08,.035,.025,'#a0a3a0');
 }
 function rack(g,b){
  const w=b.sx,d=b.sy,h=b.height;
  for(const x of [-w/2+.05,w/2-.05])for(const z of [-d/2+.05,d/2-.05])box(g,x,h/2,z,.07,h,.07,'#32566a',.65);
  for(let level=0;level<3;level++){
   const y=.18+level*.74;box(g,0,y,0,w-.08,.065,d-.06,'#dd8a36',.45);
   for(let j=0;j<3;j++){
    const x=-w*.32+j*w*.32;
    if(level===1&&j===2){cylinder(g,x,y+.23,0,.18,.4,'#d9ddd9');cylinder(g,x,y+.45,0,.19,.035,'#333a3e');}
    else carton(g,x,y+.23+(j%2)*.06,0,w*.27,.4+(j%2)*.12,d*.8,j+level);
   }
  }
  // Rear diagonal braces and a shelf number are part of the physical fixture.
  line(g,[[-w*.46,.2,d*.43],[w*.46,h-.1,d*.43]],.018,'#72858c');
  line(g,[[w*.46,.2,d*.43],[-w*.46,h-.1,d*.43]],.018,'#72858c');
  label(g,0,h-.12,-d*.46,.6,.18,'A-04','#e2e8df','#24343c',Math.PI);
 }
 function bench(g,b){
  const w=b.sx,d=b.sy;
  for(const x of [-w*.43,w*.43])for(const z of [-d*.4,d*.4])box(g,x,.45,z,.08,.9,.08,'#48585e',.6);
  box(g,0,.92,0,w,.12,d,'#b38d5d');box(g,0,.24,0,w*.85,.05,d*.75,'#606a6b',.5);
  // Monitor, stand, keyboard, red toolbox, blue vise and a coiled cable.
  box(g,-.4,1.1,.3,.08,.3,.08,'#252f34');box(g,-.4,.995,.3,.4,.025,.23,'#252f34');
  box(g,-.4,1.48,.34,.88,.53,.06,'#222c32');
  box(g,-.4,1.48,.305,.79,.44,.008,'#437489');
  label(g,-.4,1.48,.298,.68,.32,'SYSTEM\nREADY','#284c61','#bbd6d9',Math.PI);
  box(g,-.4,1.005,-.18,.62,.025,.22,'#333c40');
  for(let i=0;i<12;i++)for(let j=0;j<3;j++)box(g,-.67+i*.047,1.022,-.25+j*.06,.035,.012,.04,'#8a9290');
  box(g,.62,1.16,.17,.65,.35,.4,'#b2362c',.4);box(g,.62,1.35,.17,.68,.04,.42,'#cf4935',.4);
  line(g,[[.44,1.38,.17],[.44,1.49,.17],[.79,1.49,.17],[.79,1.38,.17]],.025,'#272d30');
  for(const x of [.42,.82])box(g,x,1.22,-.035,.035,.12,.018,'#b7bec0',.7);
  box(g,.83,1.06,-.38,.25,.15,.26,'#375b77',.6);box(g,.83,1.16,-.38,.3,.1,.1,'#9da6a7',.7);
  const cable=[];for(let i=0;i<65;i++){const a=i*.3; cable.push([-.98+.14*Math.cos(a),1+.001*i,-.22+.14*Math.sin(a)]);}line(g,cable,.009,'#232c2b');
 }
 function cabinet(g,b){
  box(g,0,.64,0,b.sx*.93,1.15,b.sy*.9,'#a32e29',.5);
  for(let i=0;i<5;i++){box(g,0,.22+i*.2,-b.sy*.46,b.sx*.85,.17,.03,'#c64435',.4);box(g,0,.26+i*.2,-b.sy*.485,b.sx*.6,.025,.025,'#c1c5bd',.8);}
  box(g,0,1.24,0,b.sx,.07,b.sy,'#242d2f');
  for(const x of [-b.sx*.35,b.sx*.35])for(const z of [-b.sy*.35,b.sy*.35])cylinder(g,x,.055,z,.05,.1,'#242d2f');
 }
 function handTruck(g){
  for(const x of [-.23,.23])line(g,[[x,.2,0],[x,1.42,.18],[x,1.52,.03]],.025,'#e2ad2c');
  for(const y of [.35,.8,1.2])box(g,0,y,.12,.47,.04,.04,'#e2ad2c',.4);
  box(g,0,.15,-.15,.55,.045,.42,'#d49a20',.5);
  for(const x of [-.27,.27]){const wheel=cylinder(g,x,.16,.14,.14,.08,'#21292a');wheel.rotation.z=Math.PI/2;}
  carton(g,0,.43,-.09,.4,.5,.38);
 }
 function plant(g){
  cylinder(g,0,.19,0,.23,.38,'#b47a54');cylinder(g,0,.39,0,.22,.025,'#3b3028');
  for(let i=0;i<16;i++){
   const a=i*2.4,h=.6+(i%6)*.18,r=.17+(i%3)*.035;
   line(g,[[0,.4,0],[Math.cos(a)*r*.6,h-.1,Math.sin(a)*r*.6],[Math.cos(a)*r,h,Math.sin(a)*r]],.009,'#345134');
   const leaf=mesh(g,new THREE.SphereGeometry(1,10,6),mat(['#3a653d','#577c41','#27573a'][i%3]),Math.cos(a)*r,h,Math.sin(a)*r);leaf.scale.set(.08,.035,.18);leaf.rotation.set(.3,a,.3);
  }
 }
 function extinguisher(g){
  cylinder(g,0,.64,0,.14,.79,'#b52f27');cylinder(g,0,1.07,0,.055,.13,'#4e5653');
  box(g,0,1.16,0,.25,.05,.06,'#252c2b',.5);
  line(g,[[.05,1.1,0],[.2,.97,0],[.2,.5,0],[.14,.3,0]],.019,'#242a28');
  label(g,0,.68,-.142,.18,.3,'FIRE','#e4e6d9','#a42b26',Math.PI);
 }
 for(const b of world.obstacles){
  const g=new THREE.Group();g.position.set(b.x,0,b.y);g.rotation.y=b.yaw||0;parent.add(g);
  if(b.kind==='stock-rack')rack(g,b);
  else if(b.kind==='workbench')bench(g,b);
  else if(b.kind==='drums'){pallet(g,b.sx,b.sy);barrel(g,-.34,-.2,'#2f6486');barrel(g,.34,.2,'#2f6486');}
  else if(b.kind==='tool-cabinet')cabinet(g,b);
  else if(b.kind==='hand-truck')handTruck(g);
  else if(b.kind==='plant')plant(g);
  else if(b.kind==='extinguisher')extinguisher(g);
  else if(b.kind==='pallet-load'){
   pallet(g,b.sx,b.sy);
   for(let i=0;i<3;i++)carton(g,0,.46+i*.55,0,b.sx*.95,.53,b.sy*.95,i);
   for(const z of [-.42,.42])box(g,0,1.02,z,b.sx+.002,1.72,.022,'#303938');
  }else{
   box(g,0,b.height/2,0,b.sx,b.height,b.sy,'#c7c9bc');
   box(g,0,.11,0,b.sx+.015,.2,b.sy+.015,'#6d7775');
   for(let h=.7;h<b.height;h+=.6)box(g,0,h,0,b.sx+.002,.005,b.sy+.002,'#adb3a9');
  }
 }
 // Contrasting jamb paint and a lintel identify the actual partition opening.
 for(const z of [2.96,5.04])box(parent,6,1.5,z,.26,3,.07,'#536b71');
 box(parent,6,2.85,4,.25,.3,2,'#536b71');
 // Floor markings and inset panels create scale cues without invisible collision geometry.
 for(const x of [3.4,4.9])for(let z=1;z<9;z+=.7)box(parent,x,.009,z,.035,.008,.4,'#c9ad51');
 for(const x of [1.6,4.7,7.8,10.9])for(const z of [1.3,4.7,8.1]){
  const lamp=box(parent,x,2.97,z,1.3,.035,.25,'#e1e2d1');lamp.material=new THREE.MeshStandardMaterial({color:'#e1e2d1',emissive:'#fff4cb',emissiveIntensity:.6});
 }
 label(parent,6,2.5,9.92,2.4,.55,'WORKSHOP  /  03','#315562','#e6e7d9',Math.PI);
}
