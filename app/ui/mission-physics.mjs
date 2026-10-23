// Mission adapter for the unchanged component-test plant. Coordinates exposed to
// callers are ENU/FLU; Rapier remains right-handed Y-up. No target labels here.
import RAPIER from './vendor/rapier/rapier.mjs';
import {MicroFlight,AdaptiveController,rotate,initialize} from './micro-physics.mjs';
export {initialize};
const v=(x=0,y=0,z=0)=>({x,y,z});
const mul=(a,b)=>({x:a.w*b.x+a.x*b.w+a.y*b.z-a.z*b.y,y:a.w*b.y-a.x*b.z+a.y*b.w+a.z*b.x,z:a.w*b.z+a.x*b.y-a.y*b.x+a.z*b.w,w:a.w*b.w-a.x*b.x-a.y*b.y-a.z*b.z});
const yaw=q=>({x:0,y:Math.sin(q/2),z:0,w:Math.cos(q/2)});
const wrap=a=>Math.atan2(Math.sin(a),Math.cos(a));
const norm=a=>Math.hypot(a.x,a.y,a.z);
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
class HeadingController extends AdaptiveController {
  update(s,g,dt){
    const angle=-(g.heading??0),q=yaw(angle),delta=yaw(angle-(this.frameAngle??angle));
    if(this.previous){this.previous.position=rotate(delta,this.previous.position);this.previous.velocity=rotate(delta,this.previous.velocity);}
    this.frameAngle=angle;
    return super.update({...s,position:rotate(q,s.position),velocity:rotate(q,s.velocity),rotation:mul(q,s.rotation)},rotate(q,g),dt);
  }
}
export class MissionFlight extends MicroFlight {
  constructor(assembly,scene,options={}){
    super(assembly,options.fault??'nominal',options);this.scene=scene;
    const remove=[];this.world.forEachCollider(c=>{if(!c.parent())remove.push(c);});
    for(const c of remove)this.world.removeCollider(c,true);
    this.obstacles.clear();
    const box=(x,y,z,sx,sy,sz)=>{const c=this.world.createCollider(RAPIER.ColliderDesc.cuboid(sx/2,sy/2,sz/2).setTranslation(x,y,z));this.obstacles.add(c.handle);return c;};
    this.floor=box(6,-.05,-5,12,.1,10);this.obstacles.delete(this.floor.handle);
    box(0,1.5,-5,.12,3,10);box(12,1.5,-5,.12,3,10);box(6,1.5,0,12,3,.12);box(6,1.5,-10,12,3,.12);
    for(const b of [...scene.obstacles,...(scene.fixtures||[])])box(b.x,(b.bottom||0)+b.height/2,-b.y,b.sx,b.height,b.sy);
    const a=scene.moving_actor;
    this.cart=box(a.center[0],a.size[2]/2,-a.center[1],a.size[0],a.size[2],a.size[1]);
    const start=scene.home;this.body.setTranslation(v(start[0],.045,-start[1]),true);
    this.body.setRotation(yaw(Math.PI/2),true);
    this.target=[start[0],start[1],.045,0];this.setpoint=v(start[0],.045,-start[1]);this.heading=Math.PI/2;
    this.flightController=new HeadingController(this.p,this.mass);this.commandAt=0;this.armed=false;this.settled=0;this.lastError=0;this.maxTracking=0;
    const step=this.world.step.bind(this.world);
    this.world.step=(events)=>{
      const wind=scene.wind,scale=1+wind.gust_fraction*Math.sin(this.t*2*Math.PI/wind.period_s);
      const w=v(wind.mean_enu_m_s[0]*scale,wind.mean_enu_m_s[2]*scale,-wind.mean_enu_m_s[1]*scale);
      const vel=this.body.linvel(),relative=v(vel.x-w.x,vel.y-w.y,vel.z-w.z),k=.5*1.225*this.p.frame.drag_area_m2;
      this.body.addForce(v(k*(vel.x*norm(vel)-relative.x*norm(relative)),k*(vel.y*norm(vel)-relative.y*norm(relative)),k*(vel.z*norm(vel)-relative.z*norm(relative))),true);
      this.cart.setTranslation(v(a.center[0]+a.amplitude_m*Math.sin(this.t*2*Math.PI/a.period_s),a.size[2]/2,-a.center[1]));
      step(events);
    };
  }
  command(target){
    if(!Array.isArray(target)||target.length!==4||target.some(x=>!Number.isFinite(x))||target[0]<.2||target[0]>11.8||target[1]<.2||target[1]>9.8||target[2]<0||target[2]>1.8)throw Error('Invalid bounded mission setpoint');
    this.target=[...target];this.commandAt=this.t;this.armed=true;
  }
  controller(dt){
    const pos=this.body.translation(),vel=this.body.linvel(),q=this.body.rotation();
    if(this.armed&&this.t-this.commandAt>this.p.avionics.link_timeout_s){
      if(!this.failsafe)this.target=[pos.x,-pos.z,0,this.heading-Math.PI/2];
      this.failsafe=true;
    }
    const target=v(this.target[0],this.target[2],-this.target[1]),dx=target.x-this.setpoint.x,dz=target.z-this.setpoint.z,d=Math.hypot(dx,dz);
    const travel=Math.min(d,.6*dt);if(d){this.setpoint.x+=travel*dx/d;this.setpoint.z+=travel*dz/d;}
    this.setpoint.y+=clamp(target.y-this.setpoint.y,-.2*dt,.3*dt);
    if(target.y===0&&this.setpoint.y<.001)this.setpoint.y=0;
    this.heading+=clamp(wrap(this.target[3]+Math.PI/2-this.heading),-.8*dt,.8*dt);
    const rates=rotate({x:-q.x,y:-q.y,z:-q.z,w:q.w},this.body.angvel()),noise=this.p.imu.gyro_noise_rad_s,bias=this.p.imu.gyro_bias_rad_s;
    this.gyro=v(rates.x+(this.random()-.5)*noise+bias,rates.y+(this.random()-.5)*noise,rates.z+(this.random()-.5)*noise);
    this.forceRequest=this.armed?this.flightController.update({position:pos,velocity:vel,rotation:q,gyro:this.gyro,voltage:this.voltage,tripped:this.tripped},{...this.setpoint,heading:this.heading},dt):[0,0,0,0];
  }
  packet(){
    const s=this.state(),p=s.position,q=s.rotation;
    // C maps Rapier world to ENU; B maps FLU body axes to the model's body axes.
    const h=Math.SQRT1_2,enuQ=mul(mul({x:h,y:0,z:0,w:h},q),{x:-.5,y:-.5,z:-.5,w:.5});
    const forward=rotate(q,v(0,0,1)),heading=Math.atan2(-forward.z,forward.x);
    const error=Math.hypot(p.x-this.target[0],-p.z-this.target[1],p.y-this.target[2]);
    return {position:[p.x,-p.z,p.y],quaternion:[enuQ.x,enuQ.y,enuQ.z,enuQ.w],yaw:heading,
      speed:norm(s.velocity),time_s:this.t,voltage_v:s.voltage_v,soc:s.soc,rpm:s.rpm,thrust_n:s.thrust_n,
      angular_speed:norm(this.body.angvel()),goal:[...this.target],error_m:error,
      arrived:error<.12&&norm(s.velocity)<.15&&Math.abs(wrap(heading-this.target[3]))<.12,
      contacts:this.contacts.length,tripped:this.tripped,failsafe:this.failsafe,
      max_tilt_deg:this.maxTilt,max_height_m:this.maxHeight,landing_speed_m_s:this.landImpact,
      mass_g:this.mass.mass*1000,static_reserve:this.preflight,
      cart_position:[this.cart.translation().x,-this.cart.translation().z,0]};
  }
}
