// Archived pre-improvement controller/plant, solely for regression comparison.
// Same fixed-step model runs headless and beneath Three.js. SI units, Y up.
import RAPIER from '../../app/ui/vendor/rapier/rapier.mjs';
export const ENGINE = 'rapier-0.21.0';
let ready;
export function initialize() { return ready ||= RAPIER.init(); }
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const vec=(x=0,y=0,z=0)=>({x,y,z});
const add=(a,b)=>vec(a.x+b.x,a.y+b.y,a.z+b.z);
const sub=(a,b)=>vec(a.x-b.x,a.y-b.y,a.z-b.z);
const mul=(v,k)=>vec(v.x*k,v.y*k,v.z*k);
const norm=v=>Math.hypot(v.x,v.y,v.z);
const unit=v=>mul(v,1/(norm(v)||1));
const cross=(a,b)=>vec(a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x);
const conjugate=q=>({x:-q.x,y:-q.y,z:-q.z,w:q.w});
const qm=(a,b)=>({x:a.w*b.x+a.x*b.w+a.y*b.z-a.z*b.y,y:a.w*b.y-a.x*b.z+a.y*b.w+a.z*b.x,z:a.w*b.z+a.x*b.y-a.y*b.x+a.z*b.w,w:a.w*b.w-a.x*b.x-a.y*b.y-a.z*b.z});
export const rotate=(q,v)=>{const p=qm(qm(q,{...v,w:0}),conjugate(q));return vec(p.x,p.y,p.z);};
export function interpolate(curve,volts) {
  if(volts<=0)return [0,0,0];
  if(volts>=curve.at(-1)[0])return curve.at(-1).slice(1);
  for(let i=1;i<curve.length;i++)if(volts<=curve[i][0]){
    const a=curve[i-1],b=curve[i],f=(volts-a[0])/(b[0]-a[0]);
    return a.slice(1).map((x,j)=>x+f*(b[j+1]-x));
  }
}
function inverse(curve,force) {
  if(force<=0)return 0;
  for(let i=1;i<curve.length;i++)if(force<=curve[i][1]){
    const a=curve[i-1],b=curve[i],f=(force-a[1])/(b[1]-a[1]||1);
    return a[0]+f*(b[0]-a[0]);
  }
  return curve.at(-1)[0];
}

export function massProperties(p) {
  const arm=p.frame.motor_diagonal_m/(2*Math.sqrt(2));
  const motors=[vec(arm,.008,arm),vec(-arm,.008,arm),vec(-arm,.008,-arm),vec(arm,.008,-arm)];
  const pieces=motors.map(at=>({mass:p.propulsion.mass_kg,at,size:[.008,.02,.008]}));
  // Quarter frame masses approximate the guard/arm distribution; unmeasured.
  for(const at of motors)pieces.push({mass:p.frame.mass_kg/4,at:vec(at.x*.6,0,at.z*.6),size:[.02,p.frame.body_height_m/4,.02]});
  for(const [key,y] of [['battery',-.012],['avionics',.008],['imu',.005],['driver',0],['range',-.018]])if(p[key])
    pieces.push({mass:p[key].mass_kg,at:vec(0,y,0),size:[.025,.008,.02]});
  const mass=pieces.reduce((s,c)=>s+c.mass,0);
  const com=mul(pieces.reduce((v,c)=>add(v,mul(c.at,c.mass)),vec()),1/mass);
  const inertia=vec();
  for(const c of pieces){const r=sub(c.at,com),[x,y,z]=c.size;
    inertia.x+=c.mass*((y*y+z*z)/12+r.y*r.y+r.z*r.z);
    inertia.y+=c.mass*((x*x+z*z)/12+r.x*r.x+r.z*r.z);
    inertia.z+=c.mass*((x*x+y*y)/12+r.x*r.x+r.y*r.y);
  }
  return {mass,com,inertia,motors,arm};
}

export class MicroFlight {
  constructor(assembly,scenario='nominal',options={}) {
    this.assembly=assembly;this.scenario=scenario;this.dt=options.dt??.004;
    if(!['nominal','low-battery','gust','link-loss','weak-motor','pessimistic'].includes(scenario))throw Error('Unknown scenario');
    if(![.002,.004,.008].includes(this.dt))throw Error('Unsupported physics timestep');
    this.p=Object.fromEntries(Object.entries(assembly.components).map(([k,v])=>[k,structuredClone(v.content.parameters)]));
    this.mass=massProperties(this.p);this.world=new RAPIER.World(vec(0,-9.81,0));
    this.world.timestep=this.dt;
    this.world.integrationParameters.lengthUnit=.1;
    this.world.integrationParameters.numSolverIterations=8;
    this.events=new RAPIER.EventQueue(true);this.obstacles=new Set();this.contacts=[];
    const wall=(x,y,z,hx,hy,hz)=>{
      const c=this.world.createCollider(RAPIER.ColliderDesc.cuboid(hx,hy,hz).setTranslation(x,y,z));
      this.obstacles.add(c.handle);return c;
    };
    this.floor=wall(0,-.05,0,2,.05,2);this.obstacles.delete(this.floor.handle);
    wall(-2,1,0,.05,1,2);wall(2,1,0,.05,1,2);wall(0,1,-2,2,1,.05);wall(0,1,2,2,1,.05);
    wall(-.9,.35,.8,.25,.35,.3);wall(.9,.45,-.8,.2,.45,.3);
    const {mass,com,inertia}=this.mass;
    this.body=this.world.createRigidBody(RAPIER.RigidBodyDesc.dynamic().setTranslation(0,.045,0)
      .setAdditionalMassProperties(mass,com,inertia,{x:0,y:0,z:0,w:1}).setCanSleep(false).setCcdEnabled(true));
    const collider=d=>this.world.createCollider(d.setDensity(0).setFriction(.6).setRestitution(0).setActiveEvents(RAPIER.ActiveEvents.COLLISION_EVENTS),this.body);
    collider(RAPIER.ColliderDesc.cuboid(.022,this.p.frame.body_height_m/2+.013,.018));
    for(const at of this.mass.motors)collider(RAPIER.ColliderDesc.cylinder(.006,this.p.propulsion.prop_diameter_m/2+this.p.frame.guard_clearance_m).setTranslation(at.x,at.y,at.z));
    this.body.recomputeMassPropertiesFromColliders();
    this.t=0;this.motorV=[0,0,0,0];this.forces=[0,0,0,0];this.rpm=[0,0,0,0];
    this.soc=scenario==='low-battery'?.15:1;this.voltage=this.ocv();this.current=0;this.minVoltage=this.voltage;
    this.thrustScale=scenario==='pessimistic'?.7:1;this.motorScale=[1,1,1,1];this.tripped=false;this.failsafe=false;
    this.maxHeight=0;this.maxTilt=0;this.maxSpeed=0;this.saturated=0;this.steps=0;this.hovers=[];this.transits=[];
    this.frames=[];this.nextFrame=0;this.cameraDelivered=0;this.samples=[];this.seed=137;this.gyro=vec();
    this.deliveredCamera=null;this.rangeMeasurement=null;this.nextRange=0;
    this.landImpact=0;this.controlElapsed=1;this.lastCommand=0;this.forceRequest=[0,0,0,0];
    this.altitudeIntegral=0;
    this.preflight=this.reserve();this.lastSample=-1;
  }
  random(){this.seed=(1664525*this.seed+1013904223)>>>0;return this.seed/4294967296;}
  ocv(){const b=this.p.battery;return b.empty_v+(b.full_v-b.empty_v)*this.soc;}
  motorVoltage(supply,duty) {
    const target=supply*duty;
    const r=this.p.driver.resistance_ohm,curve=this.p.propulsion.curve;
    if(r===0)return target;
    for(let i=1;i<curve.length;i++){
      const a=curve[i-1],b=curve[i],s=(b[2]-a[2])/(b[0]-a[0]);
      const v=(target-duty*r*(a[2]-s*a[0]))/(1+duty*r*s);
      if(v<=b[0])return Math.max(0,v);
    }
    return Math.max(0,target-duty*r*curve.at(-1)[2]);
  }
  electrical(duties) {
    const b=this.p.battery,curve=this.p.propulsion.curve,ocv=this.ocv();
    // Monotonic load line solved by bisection, including PWM battery-side current.
    const amps=v=>this.p.avionics.idle_current_a+duties.reduce((a,d)=>a+d*interpolate(curve,this.motorVoltage(v,d))[1],0);
    let lo=0,hi=ocv;
    for(let i=0;i<24;i++){const v=(lo+hi)/2;if(v+b.resistance_ohm*amps(v)>ocv)hi=v;else lo=v;}
    const voltage=(lo+hi)/2;return {voltage,current:amps(voltage)};
  }
  reserve(){const e=this.electrical([1,1,1,1]);return {voltage_v:e.voltage,current_a:e.current,
    thrust_weight:4*interpolate(this.p.propulsion.curve,this.motorVoltage(e.voltage,1))[0]*this.thrustScale/(this.mass.mass*9.81)};}
  goal(){
    if(this.t<2)return vec(0,.7*Math.min(this.t/2,1),0);
    if(this.t<5)return vec(0,.7,0);
    if(this.t<10)return vec(.5,.7,.35);
    if(this.t<14)return vec(0,.7,0);
    return vec(0,Math.max(0,.7-(this.t-14)*.18),0);
  }
  controller(controlDt) {
    const pos=this.body.translation(),vel=this.body.linvel(),q=this.body.rotation();
    if(!(this.scenario==='link-loss'&&this.t>=7))this.lastCommand=this.t;
    if(this.t-this.lastCommand>this.p.avionics.link_timeout_s)this.failsafe=true;
    const goal=this.failsafe?vec(0,Math.max(0,.7-(this.t-7-this.p.avionics.link_timeout_s)*.18),0):this.goal();
    const e=sub(goal,pos);
    // Integral feedback rejects steady thrust/voltage-model error. Stop integrating
    // at actuator saturation, and reset on landing; do not alter the physical forces.
    if(goal.y===0||this.tripped)this.altitudeIntegral=0;
    else if(!this.lastSaturated||e.y<0)this.altitudeIntegral=clamp(this.altitudeIntegral+e.y*controlDt,-1,2.5);
    const acc=vec(clamp(3*e.x-2.8*vel.x,-1.8,1.8),clamp(6*e.y-4.2*vel.y+3*this.altitudeIntegral,-4,7),clamp(3*e.z-2.8*vel.z,-1.8,1.8));
    const up=unit(add(acc,vec(0,9.81,0))),axis=cross(vec(0,1,0),up),w=Math.sqrt((1+up.y)/2);
    const target={x:axis.x/(2*w),y:axis.y/(2*w),z:axis.z/(2*w),w};
    const qe=qm(conjugate(q),target),err=vec(qe.x*2*Math.sign(qe.w),qe.y*2*Math.sign(qe.w),qe.z*2*Math.sign(qe.w));
    const rates=rotate(conjugate(q),this.body.angvel()),noise=this.p.imu.gyro_noise_rad_s,bias=this.p.imu.gyro_bias_rad_s;
    this.gyro=vec(rates.x+(this.random()-.5)*noise+bias,rates.y+(this.random()-.5)*noise,rates.z+(this.random()-.5)*noise);
    const I=this.mass.inertia;
    const torque=vec(I.x*(144*err.x-24*this.gyro.x),I.y*(100*err.y-20*this.gyro.y),I.z*(144*err.z-24*this.gyro.z));
    const bodyUp=rotate(q,vec(0,1,0));
    let total=this.mass.mass*(9.81+acc.y)/Math.max(.5,bodyUp.y);
    if((this.t>17.5||this.failsafe)&&goal.y===0&&pos.y<.04)total=0;
    if(this.tripped)total=0;
    const a=this.mass.arm,k=this.p.propulsion.torque_per_thrust_m;
    this.forceRequest=this.mass.motors.map((m,i)=>Math.max(0,total/4-torque.x*Math.sign(m.z)/(4*a)+torque.z*Math.sign(m.x)/(4*a)+torque.y*(i%2?-1:1)/(4*k)));
  }
  step(rawDuty=null) {
    this.controlElapsed+=this.dt;
    if(this.controlElapsed>=1/this.p.avionics.control_hz){this.controller(Math.min(this.controlElapsed,1/this.p.avionics.control_hz));this.controlElapsed=0;}
    const p=this.p.propulsion;
    const duties=rawDuty??this.forceRequest.map(f=>clamp(inverse(p.curve,f)/(this.voltage||1),0,1));
    this.lastSaturated=duties.some(d=>d>=.995);
    if(this.tripped)duties.fill(0);
    const e=this.electrical(duties);this.voltage=e.voltage;this.current=e.current;
    this.minVoltage=Math.min(this.minVoltage,this.voltage);
    this.soc=Math.max(0,this.soc-this.current*this.dt/(this.p.battery.capacity_mah*3.6));
    if(this.voltage<this.p.battery.cutoff_v||this.soc===0)this.tripped=true;
    if(this.scenario==='weak-motor'&&this.t>=6)this.motorScale[0]=.45;
    const pos=this.body.translation(),q=this.body.rotation(),up=rotate(q,vec(0,1,0));
    this.body.resetForces(true);this.body.resetTorques(true);
    for(let i=0;i<4;i++){
      const target=this.motorVoltage(this.voltage,duties[i]),tau=target>this.motorV[i]?p.time_up_s:p.time_down_s;
      this.motorV[i]+=(target-this.motorV[i])*(1-Math.exp(-this.dt/tau));
      const [force,,rpm]=interpolate(p.curve,this.motorV[i]);
      this.forces[i]=force*this.motorScale[i]*this.thrustScale;this.rpm[i]=rpm*Math.sqrt(this.motorScale[i]);
      this.body.addForceAtPoint(mul(up,this.forces[i]),add(pos,rotate(q,this.mass.motors[i])),true);
      this.body.addTorque(mul(up,this.forces[i]*p.torque_per_thrust_m*(i%2?-1:1)),true);
    }
    const gust=this.scenario==='gust'&&this.t>6&&this.t<9?vec(2,0,1):vec();
    const relative=sub(this.body.linvel(),gust);
    this.body.addForce(mul(relative,-.5*1.225*this.p.frame.drag_area_m2*norm(relative)),true);
    this.world.step(this.events);
    this.events.drainCollisionEvents((a,b,started)=>{if(started){
      if(this.obstacles.has(a)||this.obstacles.has(b))this.contacts.push({time_s:this.t,kind:'obstacle'});
      else if(this.t>2&&(a===this.floor.handle||b===this.floor.handle))this.landImpact=Math.max(this.landImpact,Math.abs(relative.y));
    }});
    this.t+=this.dt;this.steps++;if(duties.some(d=>d>=.995))this.saturated++;
    const now=this.body.translation(),v=this.body.linvel();
    this.maxHeight=Math.max(this.maxHeight,now.y);this.maxTilt=Math.max(this.maxTilt,Math.acos(clamp(up.y,-1,1))*180/Math.PI);
    this.maxSpeed=Math.max(this.maxSpeed,norm(v));
    if(this.t>3&&this.t<5)this.hovers.push(Math.hypot(now.x,now.y-.7,now.z));
    if(this.t>8&&this.t<10&&!this.failsafe)this.transits.push(Math.hypot(now.x-.5,now.y-.7,now.z-.35));
    if(this.t>=this.nextFrame){this.nextFrame+=1/this.p.avionics.camera_fps;this.frames.push({
      capture_time_s:this.t,delivery_time_s:this.t+this.p.avionics.camera_latency_ms/1000,
      position:{...now},rotation:{...this.body.rotation()}});}
    while(this.frames.length&&this.frames[0].delivery_time_s<=this.t){this.deliveredCamera=this.frames.shift();this.cameraDelivered++;}
    if(this.p.range&&this.t>=this.nextRange){
      this.nextRange=this.t+.033;const distance=now.y/Math.max(.001,up.y);
      this.rangeMeasurement=up.y>.7&&distance<=this.p.range.max_range_m?
        Math.max(0,distance+(this.random()-.5)*Math.sqrt(12)*this.p.range.noise_m):null;
    }
    if(this.t-this.lastSample>=.05){this.lastSample=this.t;this.samples.push(this.state());}
    if(!Number.isFinite(now.x+now.y+now.z))throw Error('Nonfinite physics state');
    return this.state();
  }
  state(){return {time_s:this.t,position:{...this.body.translation()},rotation:{...this.body.rotation()},velocity:{...this.body.linvel()},
    thrust_n:[...this.forces],rpm:[...this.rpm],voltage_v:this.voltage,current_a:this.current,soc:this.soc,failsafe:this.failsafe,
    range_m:this.rangeMeasurement};}
  result(){
    const rms=xs=>Math.sqrt(xs.reduce((a,x)=>a+x*x,0)/(xs.length||1));
    const hover=rms(this.hovers),transit=rms(this.transits),p=this.body.translation();
    const gates={liftoff:this.maxHeight>.5,hover:this.hovers.length>0&&hover<.12,
      transit:this.transits.length>0&&transit<.15,landed:p.y<.05&&norm(this.body.linvel())<.15,
      controlled_attitude:this.maxTilt<35,no_obstacle_contact:!this.contacts.length,
      battery_valid:!this.tripped,landing_speed:this.landImpact<.5,thrust_reserve:this.preflight.thrust_weight>=2};
    const flightKeys=['liftoff','hover','landed','controlled_attitude','no_obstacle_contact','battery_valid','landing_speed'];
    if(this.scenario==='link-loss')gates.command_expiry=this.failsafe;else flightKeys.push('transit');
    const flightPassed=flightKeys.every(k=>gates[k])&&(this.scenario!=='link-loss'||gates.command_expiry);
    return {engine:ENGINE,scenario:this.scenario,configuration:this.assembly.configuration.content.id,
      assembly_sha256:this.assembly.sha256,mass_g:this.mass.mass*1000,simulation_seconds:this.t,
      propulsion_evidence:this.assembly.propulsion_evidence,evidence_counts:this.assembly.evidence_counts,
      gates,flight_passed:flightPassed,engineering_passed:flightPassed&&gates.thrust_reserve,
      hover_rmse_m:hover,transit_rmse_m:transit,max_height_m:this.maxHeight,max_tilt_deg:this.maxTilt,
      landing_speed_m_s:this.landImpact,min_voltage_v:this.minVoltage,soc_remaining:this.soc,
      saturated_fraction:this.saturated/this.steps,static_reserve:this.preflight,
      synthetic_frames_delivered:this.cameraDelivered,physical_enabled:false,recognition_tested:false,
      limitations:['Ideal external position/velocity/attitude reference; noisy gyro only. No implemented onboard ESP32 estimator/controller firmware.',
        'Static propulsion interpolation and first-order motor lag; no CFD, ground effect, rotor interference or structural flexibility.',
        'Linear OCV/SOC and resistive battery; camera timing is synthetic, not video recognition or real Wi-Fi.',
        'Component geometry/mass distribution and controller gains are provisional; source data coverage is not hardware qualification.']};
  }
  dispose(){this.events.free();this.world.free();}
}

export async function simulate(assembly,scenario='nominal',options={}) {
  await initialize();const sim=new MicroFlight(assembly,scenario,options);
  try{while(sim.t<20-sim.dt/2)sim.step();return {...sim.result(),trajectory:sim.samples};}finally{sim.dispose();}
}
