// Privileged plant + synthetic IMU. Controller feedback below uses ONLY the
// integrated IMU state and accepted camera corrections, never plant pose/vel.
import {MissionFlight,initialize} from './mission-physics.mjs';
import {rotate} from './micro-physics.mjs';
import RAPIER from './vendor/rapier/rapier.mjs';
export {initialize};
const v=(x=0,y=0,z=0)=>({x,y,z});
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const mul=(a,b)=>({x:a.w*b.x+a.x*b.w+a.y*b.z-a.z*b.y,y:a.w*b.y-a.x*b.z+a.y*b.w+a.z*b.x,z:a.w*b.z+a.x*b.y-a.y*b.x+a.z*b.w,w:a.w*b.w-a.x*b.x-a.y*b.y-a.z*b.z});
const inv=q=>({x:-q.x,y:-q.y,z:-q.z,w:q.w});
const norm=q=>{const n=Math.hypot(q.x,q.y,q.z,q.w);return {x:q.x/n,y:q.y/n,z:q.z/n,w:q.w/n};};
export class BlindFlight extends MissionFlight {
 installVisibleCollisionMesh(mesh){
  if(this.armed)throw Error('Cannot replace collision geometry after arming');
  const {vertices,indices}=mesh;
  if(mesh.version!=='rendered-static-triangle-mesh-v1'||!Array.isArray(vertices)||!Array.isArray(indices)||
     !vertices.length||vertices.length%3||!indices.length||indices.length%3||indices.length>3000000||
     vertices.some(v=>!Number.isFinite(v)||Math.abs(v)>100)||
     indices.some(i=>!Number.isInteger(i)||i<0||i>=vertices.length/3))throw Error('Invalid rendered collision mesh');
  const descriptor=RAPIER.ColliderDesc.trimesh(new Float32Array(vertices),new Uint32Array(indices),
   RAPIER.TriMeshFlags.FIX_INTERNAL_EDGES_TWO_SIDED|RAPIER.TriMeshFlags.DELETE_DEGENERATE_TRIANGLES|RAPIER.TriMeshFlags.DELETE_DUPLICATE_TRIANGLES);
  const replacement=this.world.createCollider(descriptor);
  const remove=[];
  this.world.forEachCollider(c=>{if(!c.parent()&&c.handle!==this.floor.handle&&c.handle!==this.cart.handle&&c.handle!==replacement.handle)remove.push(c);});
  for(const c of remove){this.obstacles.delete(c.handle);this.world.removeCollider(c,true);}
  this.obstacles.add(replacement.handle);this.visibleMeshCollider=replacement;
 }
 constructor(assembly,scene,options={}){
  super(assembly,scene,options);
  this.groundHeight=this.p.frame.body_height_m/2+.013;
  this.estimate={position:v(0,this.groundHeight,0),velocity:v(),rotation:{x:0,y:Math.SQRT1_2,z:0,w:Math.SQRT1_2}};
  this.previousSensorVelocity=this.body.linvel();this.lastSensorTime=0;
  this.setpoint=v(0,this.groundHeight,0);this.target=[0,0,this.groundHeight,0];
  this.imu=[];this.history=[];this.visualAt=0;this.visionUpdates=0;
  this.bias=v();this.calibrationSamples=0;this.calibrationWindow=[];this.gravityWindow=[];
 }
 sensor(dt){
  // The measurement generator alone accesses plant truth, as a real IMU would.
  const vel=this.body.linvel(),q=this.body.rotation();
  const elapsed=this.t-this.lastSensorTime||dt;
  const acc=v((vel.x-this.previousSensorVelocity.x)/elapsed,(vel.y-this.previousSensorVelocity.y)/elapsed+9.81,(vel.z-this.previousSensorVelocity.z)/elapsed);
  const force=rotate(inv(q),acc),rates=rotate(inv(q),this.body.angvel());
  this.previousSensorVelocity={...vel};this.lastSensorTime=this.t;
  const noise=()=>this.random()-.5;
  const gyro=v(rates.x+noise()*.001+.00002,rates.y+noise()*.001-.00002,rates.z+noise()*.001+.00001);
  const specific=v(force.x+noise()*.02+.0001,force.y+noise()*.02-.0001,force.z+noise()*.02+.0001);
  return {time_s:this.t,gyro,specific};
 }
 controller(dt){
  const m=this.sensor(dt),e=this.estimate;
  if(!e)return;
  if(!this.armed){
   // Calibrate stationary gyro bias and gravity direction before liftoff.
   // No plant attitude, position or velocity is used by this calibration.
   const stationary=Math.hypot(m.gyro.x,m.gyro.y,m.gyro.z)<.003&&Math.abs(Math.hypot(m.specific.x,m.specific.y,m.specific.z)-9.81)<.05;
   if(!stationary){this.calibrationWindow=[];this.gravityWindow=[];this.calibrationSamples=0;}
   else{
   this.calibrationWindow.push({...m.gyro});if(this.calibrationWindow.length>2500)this.calibrationWindow.shift();
   this.calibrationSamples=this.calibrationWindow.length;
   for(const k of ['x','y','z'])this.bias[k]=this.calibrationWindow.reduce((a,b)=>a+b[k],0)/this.calibrationSamples;
   // Average stationary gravity before arming. Using the last noisy sample
   // left a small tilt bias, which integrates into large position drift even
   // during the short open-loop visual-estimator initialization maneuver.
   this.gravityWindow.push({...m.specific});if(this.gravityWindow.length>2500)this.gravityWindow.shift();
   const mean=v();for(const k of ['x','y','z'])mean[k]=this.gravityWindow.reduce((a,b)=>a+b[k],0)/this.gravityWindow.length;
   const g=rotate(e.rotation,mean),n=Math.hypot(g.x,g.y,g.z);
   e.rotation=norm(mul({x:-g.z/n*.02,y:0,z:g.x/n*.02,w:1},e.rotation));
   }
  }
  for(const k of ['x','y','z'])m.gyro[k]-=this.bias[k];
  const dq=mul(e.rotation,{...m.gyro,w:0});
  e.rotation=norm({x:e.rotation.x+dq.x*dt/2,y:e.rotation.y+dq.y*dt/2,z:e.rotation.z+dq.z*dt/2,w:e.rotation.w+dq.w*dt/2});
  const acc=rotate(e.rotation,m.specific);acc.y-=9.81;
  for(const k of ['x','y','z']){e.position[k]+=e.velocity[k]*dt+.5*acc[k]*dt*dt;e.velocity[k]+=acc[k]*dt;}
  if(!this.armed){e.position=v(0,this.groundHeight,0);e.velocity=v();}
  this.imu.push(m);if(this.imu.length>2500)this.imu.shift();
  this.history.push({time_s:this.t,position:{...e.position},velocity:{...e.velocity},rotation:{...e.rotation}});if(this.history.length>500)this.history.shift();
  if(this.armed&&this.t-this.commandAt>this.p.avionics.link_timeout_s){this.failsafe=true;this.target=[e.position.x,-e.position.z,0,this.target[3]];}
  const target=v(this.target[0],this.target[2],-this.target[1]),dx=target.x-this.setpoint.x,dz=target.z-this.setpoint.z,d=Math.hypot(dx,dz);
  const travel=Math.min(d,.55*dt);if(d){this.setpoint.x+=travel*dx/d;this.setpoint.z+=travel*dz/d;}
  this.setpoint.y+=clamp(target.y-this.setpoint.y,-.15*dt,.2*dt);
  this.heading+=clamp(Math.atan2(Math.sin(this.target[3]+Math.PI/2-this.heading),Math.cos(this.target[3]+Math.PI/2-this.heading)),-.65*dt,.65*dt);
  this.gyro=m.gyro;
  this.forceRequest=this.armed?this.flightController.update({...e,gyro:m.gyro,voltage:this.voltage,tripped:this.tripped},{...this.setpoint,heading:this.heading},dt):[0,0,0,0];
 }
 command(target){
  if(!Array.isArray(target)||target.length!==4||target.some(x=>!Number.isFinite(x))||Math.hypot(target[0],target[1])>15||target[2]<0||target[2]>1.8)throw Error('Invalid blind command');
  if(this.failsafe)throw Error('Failsafe latched');
  // A stop at the current estimated location must cancel the old trajectory
  // immediately; otherwise the slew limiter can keep pulling toward its goal.
  const e=this.estimate.position;
  if(Math.hypot(target[0]-e.x,target[1]+e.z)<.08&&Math.hypot(target[0]-this.target[0],target[1]-this.target[1])>.15){
   this.setpoint.x=e.x;this.setpoint.z=e.z;
  }
  this.target=[...target];this.commandAt=this.t;this.armed=true;
 }
 visual(c){
  const e=this.estimate,old=this.history.findLast(h=>h.time_s<=c.time_s);
  if(!old||c.time_s>this.t||this.t-c.time_s>1||c.time_s<=this.visualAt||c.inliers<25)throw Error('Stale/unsupported visual correction');
  const p=v(c.position[0],c.position[2],-c.position[1]);
  if(Object.values(p).some(x=>!Number.isFinite(x))||Math.hypot(p.x-old.position.x,p.y-old.position.y,p.z-old.position.z)>.25)throw Error('Visual correction jump');
  const vel=v(c.velocity[0],c.velocity[2],-c.velocity[1]);
  if(Object.values(vel).some(x=>!Number.isFinite(x))||Math.hypot(vel.x,vel.y,vel.z)>1)throw Error('Invalid visual velocity');
  let correction;
  if(c.quaternion){
   const a=c.quaternion;
   if(!Array.isArray(a)||a.length!==4||a.some(x=>!Number.isFinite(x))||Math.abs(Math.hypot(...a)-1)>.01)throw Error('Invalid visual orientation');
   const h=Math.SQRT1_2,q=mul(mul({x:-h,y:0,z:0,w:h},{x:a[0],y:a[1],z:a[2],w:a[3]}),{x:.5,y:.5,z:.5,w:.5});
   // Gravity/roll/pitch stay with the calibrated IMU attitude. A weak visual
   // depth solution must not tilt the flight controller's gravity reference.
   const observed=rotate(q,v(0,0,1)),previous=rotate(old.rotation,v(0,0,1));
   const difference=Math.atan2(observed.x,observed.z)-Math.atan2(previous.x,previous.z);
   const angle=Math.atan2(Math.sin(difference),Math.cos(difference));
   if(Math.abs(angle)>.06)throw Error('Visual orientation jump');
   correction={x:0,y:Math.sin(angle/2),z:0,w:Math.cos(angle/2)};
  }
  const dp={},dv={};
  for(const k of ['x','y','z']){dp[k]=.5*(p[k]-old.position[k]);dv[k]=.5*(vel[k]-old.velocity[k]);}
  const correctedAt=old.time_s;
  const yawCorrection=correction?norm({x:correction.x*.1,y:correction.y*.1,z:correction.z*.1,w:1+(correction.w-1)*.1}):null;
  const apply=(state,time)=>{
   for(const k of ['x','y','z']){
    state.position[k]+=dp[k]+dv[k]*(time-correctedAt);
    state.velocity[k]+=dv[k];
   }
   if(yawCorrection)state.rotation=norm(mul(yawCorrection,state.rotation));
  };
  // Reconcile the delayed state and propagate its velocity correction forward.
  // Otherwise overlapping delayed frames repeatedly apply an innovation that
  // has already changed the live estimate but not the stale history sample.
  for(const state of this.history)if(state.time_s>=correctedAt)apply(state,state.time_s);
  apply(e,this.t);
  this.visualAt=c.time_s;this.visionUpdates++;
 }
 imuPacket(after){
  if(!Number.isFinite(after))throw Error('Invalid IMU cursor');
  return {frame:'body FLU',gyro_bias_calibrated:true,
   oldest_time_s:this.imu[0]?.time_s??this.t,newest_time_s:this.imu.at(-1)?.time_s??this.t,
   imu:this.imu.filter(m=>m.time_s>after).map(m=>({time_s:m.time_s,
    gyro_flu:[m.gyro.z,m.gyro.x,m.gyro.y],specific_force_flu:[m.specific.z,m.specific.x,m.specific.y]}))};
 }
 publicPacket(){
  const e=this.estimate,q=e.rotation,h=Math.SQRT1_2,enuQ=mul(mul({x:h,y:0,z:0,w:h},q),{x:-.5,y:-.5,z:-.5,w:.5});
  const f=rotate(q,v(0,0,1));
  return {time_s:this.t,position:[e.position.x,-e.position.z,e.position.y],quaternion:[enuQ.x,enuQ.y,enuQ.z,enuQ.w],yaw:Math.atan2(-f.z,f.x),
   velocity:[e.velocity.x,-e.velocity.z,e.velocity.y],voltage_v:this.voltage,imu:this.imu.slice(-5),vision_updates:this.visionUpdates,
   imu_calibration:{stationary_samples:this.calibrationSamples,ready:this.calibrationSamples>=2250},
   failsafe:this.failsafe,tripped:this.tripped,pose_source:'synthetic IMU integration + gated image odometry',goal:[...this.target]};
 }
}
