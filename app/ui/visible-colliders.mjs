// Privileged renderer/physics bridge. Never sent to mission or vision clients.
import * as THREE from './vendor/three.module.js';

export function visibleCollisionMesh(scene,movingRoot){
 scene.updateMatrixWorld(true);
 const vertices=[],indices=[],items=[];
 scene.traverse(mesh=>{
  if(!mesh.isMesh)return;
  let excluded=false;
  for(let parent=mesh;parent;parent=parent.parent)if(!parent.visible||parent===movingRoot)excluded=true;
  if(excluded)return;
  if(mesh.isSkinnedMesh)throw Error('Animated collision geometry requires an explicit physics adapter');
  const position=mesh.geometry?.attributes?.position;if(!position)return;
  const transformed=[],point=new THREE.Vector3();let low=Infinity,high=-Infinity;
  for(let i=0;i<position.count;i++){
   point.fromBufferAttribute(position,i).applyMatrix4(mesh.matrixWorld);
   transformed.push(point.x,point.y,point.z);low=Math.min(low,point.y);high=Math.max(high,point.y);
  }
  // The existing physical floor remains the ground contact surface. Flat
  // floor textures/paint are decorative and must not become extra obstacles.
  if(low>=-.02&&high<=.025&&high-low<.005)return;
  const base=vertices.length/3,start=indices.length;
  for(let i=0;i<transformed.length;i+=8192)vertices.push(...transformed.slice(i,i+8192));
  const index=mesh.geometry.index,count=index?index.count:position.count;
  const reflected=mesh.matrixWorld.determinant()<0;
  for(let i=0;i+2<count;i+=3){
   const a=index?index.getX(i):i,b=index?index.getX(i+1):i+1,c=index?index.getX(i+2):i+2;
   indices.push(base+a,base+(reflected?c:b),base+(reflected?b:c));
  }
  items.push({name:mesh.name||'mesh',vertices:position.count,triangles:(indices.length-start)/3,min_height_m:low,max_height_m:high});
 });
 return {version:'rendered-static-triangle-mesh-v1',vertices,indices,items,
         exclusions:['Moving actor retains its separately updated collider','Flat floor textures and paint; existing floor collider retained']};
}
