import fs from 'node:fs';
import readline from 'node:readline';
import {BlindFlight,initialize} from '../app/ui/blind-physics.mjs';
await initialize();
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const sim=new BlindFlight(input.assembly,input.scene,{seed:input.seed});
let started=performance.now(),elapsed=0;
const timer=setInterval(()=>{try{const now=(performance.now()-started)/1000;if(now-elapsed>.5)throw Error('Physics deadline');while(elapsed+sim.dt<=now){sim.step();elapsed+=sim.dt;}}catch(e){console.error(e);process.exit(1);}},10);
for await(const line of readline.createInterface({input:process.stdin})){
 try{const c=JSON.parse(line);
  if(c.op==='imu'){console.log(JSON.stringify(sim.imuPacket(c.after)));continue;}
  if(c.op==='load-collision-mesh'){
   const began=performance.now();sim.installVisibleCollisionMesh(JSON.parse(fs.readFileSync(c.path,'utf8')));
   // Setup is unarmed and can take longer than a flight control deadline.
   started+=performance.now()-began;
  }
  else if(c.op==='command')sim.command(c.target);
  else if(c.op==='visual')sim.visual(c);
  else if(!['status','close'].includes(c.op))throw Error('Unknown command');
  // This stream is private to the simulator service. Public HTTP filters it.
  console.log(JSON.stringify({sensor:sim.publicPacket(),truth:sim.packet()}));
  if(c.op==='close')break;
 }catch(e){console.log(JSON.stringify({error:String(e)}));}
}
clearInterval(timer);sim.dispose();
