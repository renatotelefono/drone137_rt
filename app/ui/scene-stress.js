import * as THREE from './vendor/three.module.js';
import {realismAssets} from './scene-realism.js';
import {importedAssets} from './scene-imported.js';
// Shared cached primitives keep tenfold scene density within a small GPU budget.
export async function stressAssets(parent, world){
 if(!world.room_asset)await realismAssets(parent,{...world,obstacles:world.obstacles.filter(b=>!b.asset && !b.detail && b.kind!=='red-canister')});
 const assetAudit=await importedAssets(parent,world);
 const boxes=new THREE.BoxGeometry(1,1,1), cylinders=new THREE.CylinderGeometry(1,1,1,16), mats=new Map();
 function part(g,x,y,z,w,h,d,color,cylinder=false){
  if(!mats.has(color))mats.set(color,new THREE.MeshStandardMaterial({color,roughness:.72,metalness:.15}));
  const m=new THREE.Mesh(cylinder?cylinders:boxes,mats.get(color));m.position.set(x,y,z);m.scale.set(w,h,d);m.castShadow=true;m.receiveShadow=true;g.add(m);return m;
 }
 for(const b of world.fixtures||[])part(parent,b.x,b.bottom+b.height/2,b.y,b.sx,b.height,b.sy,b.color);
 // A floor stand supports the raised extinguisher body used by the shared asset.
 for(const b of world.obstacles.filter(b=>!b.asset && b.kind==='extinguisher')){
  part(parent,b.x,.018,b.y,.4,.036,.4,'#313b3e');
  for(const dx of [-.12,.12])part(parent,b.x+dx,.13,b.y,.035,.23,.035,'#404d51');
  part(parent,b.x,.24,b.y,.31,.025,.31,'#404d51');
 }
 for(const b of world.obstacles.filter(b=>!b.asset && (b.detail||b.kind==='red-canister'))){
  const g=new THREE.Group();g.position.set(b.x,b.bottom,b.y);parent.add(g);const w=b.sx,h=b.height,d=b.sy,c=b.color||'#a9362b';
  if(['red-canister','paint-tin'].includes(b.kind)){
   part(g,0,h*.45,0,w*.43,h*.9,d*.43,c,true);part(g,0,h*.92,0,w*.43,.025,d*.43,'#606969',true);
   part(g,0,h*.98,0,w*.36,.025,.035,'#272d30');
   part(g,0,h*.48,-d*.435,w*.45,h*.38,.008,'#ded9ba');
  }else{
   part(g,0,h/2,0,w,h,d,c);part(g,0,h+.008,0,w+.02,.024,d+.02,c);
   if(b.kind==='carton'){
    part(g,0,h+.022,0,w*.18,.005,d,'#d5bc8a');part(g,0,h/2,-d/2-.003,w*.18,h,.006,'#d5bc8a');
   }else{
    part(g,0,h*.7,-d/2-.01,w*.36,.035,.025,'#30393b');
    part(g,-w*.3,h*.55,-d/2-.02,.025,h*.25,.025,'#aab3b1');
   }
   part(g,w*.22,h*.4,-d/2-.008,w*.25,h*.3,.006,'#d6d8cb');
  }
 }
 // Building services, conduit, high windows, worn trim and ceiling joists.
 for(const y of (world.room_asset?[]:[1.,3.4,6.2,8.8])){
  part(parent,6,2.93,y,11.8,.12,.13,'#424d51');
  for(const x of [.1,11.9])part(parent,x,1.5,y,.08,3,.16,'#7e8886');
 }
 for(const x of (world.room_asset?[]:[1.9,4.8,8.4,10.8])){
  part(parent,x,2.45,9.92,1.4,.7,.035,'#839eaa');
  part(parent,x,2.45,9.88,.035,.75,.04,'#47595f');
 }
 if(!world.room_asset){part(parent,1,2.72,5,.22,.22,9.8,'#798483');
 for(let i=0;i<22;i++)part(parent,1,2.72,.3+i*.44,.25,.25,.018,'#a1a8a4');}
 const actor=new THREE.Group();parent.add(actor);
 part(actor,0,.58,0,.55,1.12,.4,'#ba8654');part(actor,0,.12,0,.61,.08,.45,'#3f5054');
 for(const x of [-.22,.22])for(const z of [-.15,.15])part(actor,x,.055,z,.04,.1,.08,'#20282c');
 return {actor,assetAudit};
}
