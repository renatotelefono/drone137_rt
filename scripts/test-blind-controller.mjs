import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import test from 'node:test';
import {BlindFlight,initialize} from '../app/ui/blind-physics.mjs';
import * as THREE from '../app/ui/vendor/three.module.js';
import RAPIER from '../app/ui/vendor/rapier/rapier.mjs';
import {visibleCollisionMesh} from '../app/ui/visible-colliders.mjs';

const python=process.env.DRONE137_PYTHON||'.local/vision-env/bin/python';
const exported=spawnSync(python,['-c',`import tempfile,json
from pathlib import Path
from app.components import Components
from sim.blind_world import scene
with tempfile.TemporaryDirectory() as t:
 print(json.dumps({'assembly':Components(Path(t)/'parts.sqlite3').assemble('scout-110-bench-b@1'),'scene':scene(7301)}))
`],{encoding:'utf8'});
assert.equal(exported.status,0,exported.stderr);
const fixture=JSON.parse(exported.stdout);await initialize();
function aircraft(){const s=new BlindFlight(fixture.assembly,fixture.scene);for(let i=0;i<500;i++)s.step();return s;}

test('Rendered table geometry collides at its surfaces, not the empty space in its old bounding box',()=>{
 const s=aircraft();try{
  const scene=new THREE.Scene(),group=new THREE.Group();group.scale.z=-1;scene.add(group);
  const box=(x,y,z,w,h,d)=>{const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d));m.position.set(x,y,z);group.add(m);return m;};
  box(2.5,.94,2.8,1.7,.07,.8);
  for(const x of [-.74,.74])for(const z of [-.3,.3])box(2.5+x,.46,2.8+z,.045,.92,.045);
  const bottle=new THREE.Mesh(new THREE.CylinderGeometry(.045,.045,.35,24));bottle.position.set(1.85,1.15,2.92);group.add(bottle);
  const moving=box(2.5,1.45,2.8,1,.1,1),hidden=box(2.5,1.45,2.8,1,.1,1);hidden.visible=false;
  box(6,.004,5,12,.001,10); // decorative floor excluded
  const mesh=visibleCollisionMesh(scene,moving);assert.equal(mesh.items.length,6);
  s.installVisibleCollisionMesh(mesh);
  const hits=(y,z)=>s.visibleMeshCollider.intersectsRay(new RAPIER.Ray({x:1,y,z},{x:1,y:0,z:0}),5);
  assert.equal(hits(1.45,-2.8),false);
  assert.equal(hits(.94,-2.8),true);
  assert.equal(hits(1.1,-2.92),true);
  assert.equal(hits(.4,-3.1),true);
  assert.equal(hits(.4,-2.8),false);
  s.command([0,0,.3,0]);assert.throws(()=>s.installVisibleCollisionMesh(mesh));
 }finally{s.dispose();}
});

test('An unobservable visual roll cannot tilt the IMU gravity reference',()=>{
 const s=aircraft();try{
  const before={...s.estimate.rotation},p=s.publicPacket();
  s.visual({time_s:p.time_s,position:p.position,velocity:[0,0,0],inliers:100,quaternion:[Math.sin(.15),0,0,Math.cos(.15)]});
  assert.ok(Math.abs(s.estimate.rotation.x-before.x)<1e-6);
  assert.ok(Math.abs(s.estimate.rotation.z-before.z)<1e-6);
  assert.equal(s.visionUpdates,1);
 }finally{s.dispose();}
});

test('Impossible velocity, position jumps, stale frames and weak tracking cannot change feedback',()=>{
 const s=aircraft();try{
  const p=s.publicPacket(),original=JSON.stringify(s.estimate);
  const valid={time_s:p.time_s,position:p.position,velocity:[0,0,0],inliers:100};
  for(const update of [{velocity:[2,0,0]},{position:[1,0,.3]},{time_s:p.time_s-2},{inliers:20}]){
   assert.throws(()=>s.visual({...valid,...update}));
   assert.equal(JSON.stringify(s.estimate),original);
  }
 }finally{s.dispose();}
});

test('Overlapping delayed observations cannot repeatedly apply the same historical error',()=>{
 const s=aircraft();try{
  s.estimate.position.x=.1;
  for(const h of s.history){h.position.x=.1;h.velocity.x=0;}
  s.estimate.velocity.x=0;
  let previous=.1;
  for(let i=0;i<6;i++){
   const h=s.history[400+i];
   s.visual({time_s:h.time_s,position:[0,0,s.groundHeight],velocity:[0,0,0],inliers:100});
   assert.ok(s.estimate.position.x>=0&&s.estimate.position.x<previous);
   previous=s.estimate.position.x;
  }
  assert.ok(previous<.002);
 }finally{s.dispose();}
});

test('A delayed velocity correction is propagated to the current position',()=>{
 const s=aircraft();try{
  const h=s.history[400],age=s.t-h.time_s;
  s.estimate.position.x=0;s.estimate.velocity.x=0;
  for(const state of s.history){state.position.x=0;state.velocity.x=0;}
  s.visual({time_s:h.time_s,position:[0,0,s.groundHeight],velocity:[.1,0,0],inliers:100});
  assert.ok(Math.abs(s.estimate.position.x-.05*age)<1e-9);
  assert.ok(Math.abs(s.estimate.velocity.x-.05)<1e-9);
 }finally{s.dispose();}
});

test('Stopping cancels the old trajectory instead of continuing toward its prior waypoint',()=>{
 const s=aircraft();try{
  const p=s.publicPacket();s.target=[1,0,.3,0];s.setpoint.x=.5;
  s.command([p.position[0],p.position[1],.3,0]);
  assert.equal(s.setpoint.x,s.estimate.position.x);
  assert.equal(s.setpoint.z,s.estimate.position.z);
 }finally{s.dispose();}
});

test('Short IMU-only takeoff stays near the launch patch without true-pose feedback',()=>{
 const s=aircraft();try{
  for(let i=0;i<1000;i++){if(i%10===0)s.command([0,0,.3,0]);s.step();}
  const actual=s.packet(),estimated=s.publicPacket();
  assert.ok(actual.position[2]>.2&&actual.position[2]<.4);
  assert.ok(Math.hypot(actual.position[0]-fixture.scene.home[0],actual.position[1]-fixture.scene.home[1])<.12);
  assert.ok(Math.abs(estimated.position[2]-actual.position[2])<.05);
  assert.equal(actual.contacts,0);
 }finally{s.dispose();}
});

test('Stationary calibration bounds drift during a twenty-second visual initialization window',()=>{
 for(const seed of [7301,21,81]){
  const s=new BlindFlight(fixture.assembly,fixture.scene,{seed});try{
   for(let i=0;i<2500;i++)s.step();
   assert.equal(s.publicPacket().imu_calibration.ready,true);
   for(let i=0;i<5000;i++){if(i%10===0)s.command([0,0,.3,0]);s.step();}
   const actual=s.packet();
   assert.ok(Math.hypot(actual.position[0]-fixture.scene.home[0],actual.position[1]-fixture.scene.home[1])<.15,`seed ${seed}: launch drift`);
   assert.equal(actual.contacts,0);
  }finally{s.dispose();}
 }
});
