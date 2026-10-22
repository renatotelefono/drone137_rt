import * as THREE from './vendor/three.module.js';
import {GLTFLoader} from './vendor/addons/loaders/GLTFLoader.js';
import {HDRLoader} from './vendor/addons/loaders/HDRLoader.js';

// One load per asset; clones share geometry, materials and textures.
export async function importedAssets(parent, world){
 if(!world.real_assets)return [];
 const response=await fetch(world.real_assets.manifest);if(!response.ok)throw Error('Asset manifest unavailable');
 const manifest=await response.json(),loader=new GLTFLoader(),cache=new Map(),audit=[];
 for(const id of new Set(world.obstacles.filter(b=>b.asset).map(b=>b.asset))){
  const entry=manifest.assets[id],loaded=await loader.loadAsync('/assets/real-assets/'+entry.entry);
  const root=loaded.scene,box=new THREE.Box3().setFromObject(root),size=box.getSize(new THREE.Vector3());
  const expected=entry.raw_bounds_xyz;
  if(size.toArray().some((v,i)=>Math.abs(v-(expected.max[i]-expected.min[i]))>1e-4))throw Error('Asset bounds changed: '+id);
  root.position.set(-(box.min.x+box.max.x)/2,-box.min.y,-(box.min.z+box.max.z)/2);
  root.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;}});
  cache.set(id,root);
 }
 for(const b of world.obstacles.filter(b=>b.asset)){
  const entry=manifest.assets[b.asset],g=new THREE.Group(),model=cache.get(b.asset).clone(true);
  const s=entry.unit_scale_to_m*b.asset_scale;
  // Undo the ENU parent's reflection locally so text and mesh handedness survive.
  const units=new THREE.Group();units.scale.set(s,s,-s);units.add(model);g.add(units);
  g.position.set(b.x,b.bottom||0,b.y);g.rotation.y=b.yaw||0;parent.add(g);
  parent.updateWorldMatrix(true,true);
  const box=new THREE.Box3().setFromObject(g),size=box.getSize(new THREE.Vector3());
  const center=box.getCenter(new THREE.Vector3());
  if(Math.abs(size.x-b.sx)>1e-4||Math.abs(size.y-b.height)>1e-4||Math.abs(size.z-b.sy)>1e-4||
     Math.abs(center.x-b.x)>1e-4||Math.abs(center.z+b.y)>1e-4||Math.abs(box.min.y-(b.bottom||0))>1e-4)
   throw Error('Rendered asset and collision bounds disagree: '+b.id);
  audit.push({id:b.id,asset:b.asset,size_xyz_m:size.toArray(),center_xyz_m:center.toArray()});
 }
 return audit;
}

export async function importedLighting(renderer,scene,world){
 if(!world.real_assets)return;
 const manifest=await(await fetch(world.real_assets.manifest)).json();
 const entry=manifest.assets[world.real_assets.environment];
 const hdr=await new HDRLoader().loadAsync('/assets/real-assets/'+entry.entry);
 const generator=new THREE.PMREMGenerator(renderer),target=generator.fromEquirectangular(hdr);
 scene.environment=target.texture;scene.environmentIntensity=world.real_assets.environment_intensity;
 // Only illumination/reflections: the panorama never substitutes for room geometry.
 hdr.dispose();generator.dispose();
 return target;
}
