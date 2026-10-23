import fs from 'node:fs';
import assert from 'node:assert/strict';
import {initialize,MissionFlight} from '../app/ui/mission-physics.mjs';
import {rotate} from '../app/ui/micro-physics.mjs';
await initialize();
const input=JSON.parse(fs.readFileSync(process.argv[2]));
const advance=(s,target,seconds,heartbeat=true)=>{for(let k=0;k<seconds/s.dt;k++){if(heartbeat&&k%25===0)s.command(target);s.step();}};
let checks=0;
const sim=new MissionFlight(input.assembly,input.scene);
try{
 assert.ok(sim.packet().quaternion.slice(0,3).every(x=>Math.abs(x)<1e-6));checks++;
 advance(sim,[1.25,1.25,1.5,0],12);
 assert.ok(sim.packet().arrived);assert.ok(sim.packet().rpm.every(x=>x>1000));checks++;
 advance(sim,[1.25,1.25,1.5,1.5],7);
 const p=sim.packet(),[x,y,z,w]=p.quaternion,f=rotate({x,y,z,w},{x:1,y:0,z:0});
 assert.ok(Math.abs(Math.atan2(f.y,f.x)-p.yaw)<1e-5);assert.ok(p.arrived);checks++;
 advance(sim,[1.25,1.25,1.5,1.5],12,false);
 assert.ok(sim.packet().failsafe);assert.ok(sim.packet().position[2]<.05);assert.equal(sim.packet().contacts,0);checks++;
 assert.throws(()=>sim.command([1,1,10,0]));checks++;
}finally{sim.dispose();}
const hit=new MissionFlight(input.assembly,input.scene);
try{
 advance(hit,[1.25,1.25,1.5,0],10);
 // Deliberately bypass the route supervisor: wall collision must be observable.
 hit.body.setTranslation({x:.02,y:1,z:-1.25},true);hit.step();
 assert.ok(hit.contacts.length>0);checks++;
}finally{hit.dispose();}
console.log(`PASS: ${checks} mission physics checks (frame conversion, lift, heading, expiry landing, bounds, contact)`);
