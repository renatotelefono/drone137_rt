import * as THREE from './vendor/three.module.js';
import {workshopAssets} from './scene-detail.js';

// Metre-scaled, local procedural objects. The scene is never an inference input.
// Mesh silhouettes and materials carry the recognition task, not class-name labels.
export function realismAssets(parent,world) {
 const special=new Set(['lab-bench','bottle-table','office-chair','safety-cones']);
 // Reuse the detailed bench, then add physical clutter.
 workshopAssets(parent,{...world,obstacles:world.obstacles.filter(b=>!special.has(b.kind)||b.kind==='lab-bench').map(b=>b.kind==='lab-bench'?{...b,kind:'workbench'}:b)});
 let randomState=world.seed>>>0;
 const random=()=>{randomState=(Math.imul(1664525,randomState)+1013904223)>>>0;return randomState/4294967296;};
 const mats=new Map();
 const material=(color,metalness=0)=>{
  const key=`${color}/${metalness}`;
  if(!mats.has(key))mats.set(key,new THREE.MeshStandardMaterial({color,metalness,roughness:metalness?.38:.76}));
  return mats.get(key);
 };
 const mesh=(g,geo,mat,x,y,z)=>{const m=new THREE.Mesh(geo,mat);m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;g.add(m);return m;};
 const box=(g,x,y,z,w,h,d,c,metal=0)=>mesh(g,new THREE.BoxGeometry(w,h,d),material(c,metal),x,y,z);
 const cyl=(g,x,y,z,r,h,c,metal=0)=>mesh(g,new THREE.CylinderGeometry(r,r,h,24),material(c,metal),x,y,z);
 function tube(g,points,r,c){mesh(g,new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(...p))),24,r,8,false),material(c),0,0,0);}
 function bottle(g,x,y,z,height,color,cap){
  const b=new THREE.Group();b.position.set(x,y,z);b.rotation.y=random()*6.28;g.add(b);
  const scale=height/.32;b.scale.setScalar(scale);
  const profile=[[.0,0],[.035,0],[.044,.015],[.045,.04],[.043,.20],[.038,.235],[.018,.27],[.016,.30],[0,.30]];
  mesh(b,new THREE.LatheGeometry(profile.map(([r,h])=>new THREE.Vector2(r,h)),32),new THREE.MeshPhysicalMaterial({color,roughness:.2,metalness:0,transparent:true,opacity:.7,clearcoat:1}),0,0,0);
  // Liquid and moulded ribs preserve a readable PET silhouette at a few dozen pixels.
  cyl(b,0,.085,0,.039,.15,'#5a8f98');
  for(const h of [.035,.055,.075,.19,.21]){const rib=mesh(b,new THREE.TorusGeometry(.043,.0025,5,32),material('#a1bdba',.2),0,h,0);rib.rotation.x=Math.PI/2;}
  cyl(b,0,.315,0,.02,.03,cap);
  cyl(b,0,.139,0,.0445,.065,color);
 }
 function mug(g,x,y,z){
  const points=[[.045,0],[.049,.008],[.049,.09],[.044,.095],[.040,.09],[.040,.01],[.045,0]];
  mesh(g,new THREE.LatheGeometry(points.map(p=>new THREE.Vector2(...p)),24),material('#e0d9c5'),x,y,z);
  const handle=mesh(g,new THREE.TorusGeometry(.027,.007,8,20),material('#e0d9c5'),x+.055,y+.05,z);handle.rotation.y=Math.PI/2;
 }
 for(const b of world.obstacles.filter(b=>special.has(b.kind))){
  const g=new THREE.Group();g.position.set(b.x,0,b.y);parent.add(g);
  if(b.kind==='bottle-table'){
   box(g,0,.94,0,1.7,.07,.8,'#9e805c');
   for(const x of [-.74,.74])for(const z of [-.3,.3])box(g,x,.46,z,.045,.92,.045,'#474d50',.65);
   for(let i=0;i<5;i++)bottle(g,-.65+i*.28,.975,(i%2?-.1:.12),.25+random()*.1,['#b6cfcc','#c3d3b0','#a2c7d5'][i%3],['#295d9b','#29784b','#e1dcd1'][i%3]);
   mug(g,.65,.975,-.12);
   box(g,.25,.982,.23,.25,.008,.19,'#c2b89c');
  }else if(b.kind==='lab-bench'){
   bottle(g,-1.,.98,.30,.28,'#b1c7d1','#294f99');
   mug(g,.17,.98,-.32);
   // Screwdriver, pliers, paper and wire create small, partially occluded distractors.
   const driver=box(g,-.91,1.01,-.33,.10,.035,.04,'#b9422d');driver.rotation.y=.3;
   const shaft=box(g,-.79,1.01,-.365,.15,.01,.01,'#b1b9b7',.85);shaft.rotation.y=.3;
   box(g,.25,.983,.28,.2,.004,.26,'#e0dfce');
   tube(g,[[.02,.997,.36],[.12,1.01,.08],[.3,1.008,.15],[.36,.997,.36]],.007,'#2c3d4d');
  }else if(b.kind==='office-chair'){
   const fabric=['#303e49','#45404d','#32474b'][Math.floor(random()*3)];
   cyl(g,0,.3,0,.035,.4,'#aeb2b0',.8);
   for(let i=0;i<5;i++){
    const a=i*Math.PI*2/5,x=Math.cos(a)*.28,z=Math.sin(a)*.28;
    tube(g,[[0,.17,0],[x*.7,.13,z*.7],[x,.08,z]],.025,'#343b3c');
    const wheel=cyl(g,x,.045,z,.043,.04,'#222729');wheel.rotation.z=Math.PI/2;
   }
   const seat=mesh(g,new THREE.SphereGeometry(1,24,12),material(fabric),0,.51,0);seat.scale.set(.30,.065,.28);
   box(g,0,.76,.23,.06,.52,.05,'#31393b',.3);
   const back=mesh(g,new THREE.SphereGeometry(1,24,12),material(fabric),0,.94,.21);back.scale.set(.28,.28,.065);back.rotation.x=-.12;
   for(const x of [-.30,.30]){box(g,x,.62,0,.025,.21,.03,'#30383b');box(g,x,.73,-.015,.06,.035,.31,'#252e34');}
  }else if(b.kind==='safety-cones'){
   box(g,0,.035,0,.48,.07,.48,'#303638');
   mesh(g,new THREE.CylinderGeometry(.04,.18,.65,32),material('#e46f27'),0,.395,0);
   for(const [h,r] of [[.29,.151],[.51,.104]])mesh(g,new THREE.CylinderGeometry(r-.014,r+.014,.12,32),material('#e1dfcd'),0,h,0);
  }
 }
 // Scanned CC0 2 m concrete tile, kept local with its provenance and hashes.
 const loader=new THREE.TextureLoader();
 return Promise.all(['diff','nor_gl','rough'].map(async name=>{
  const t=await loader.loadAsync(`/assets/textures/concrete_floor_02_${name}_1k.jpg`);
  t.wrapS=t.wrapT=THREE.RepeatWrapping;t.repeat.set(6,5);t.anisotropy=4;
  if(name==='diff')t.colorSpace=THREE.SRGBColorSpace;
  return t;
 })).then(([map,normalMap,roughnessMap])=>{
  const floor=mesh(parent,new THREE.PlaneGeometry(12,10),new THREE.MeshStandardMaterial({map,normalMap,roughnessMap,roughness:.9,normalScale:new THREE.Vector2(.45,.45)}),6,.004,5);floor.rotation.x=-Math.PI/2;
 });
}
