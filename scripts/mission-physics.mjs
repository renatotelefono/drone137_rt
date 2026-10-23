import fs from 'node:fs';
import readline from 'node:readline';
import {MissionFlight,initialize} from '../app/ui/mission-physics.mjs';
await initialize();
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const sim=new MissionFlight(input.assembly,input.scene,{seed:input.seed??137,fault:input.fault??'nominal'});
let started=performance.now(),elapsed=0,closed=false;
const timer=setInterval(()=>{
  try{
    const now=(performance.now()-started)/1000;
    if(now-elapsed>.5)throw Error('Physics worker missed its wall-clock deadline');
    while(elapsed+sim.dt<=now){sim.step();elapsed+=sim.dt;}
  }catch(e){console.error(String(e));clearInterval(timer);process.exitCode=1;process.stdin.destroy();}
},10);
for await(const line of readline.createInterface({input:process.stdin})){
  try{
    const c=JSON.parse(line);
    if(c.op==='command')sim.command(c.target);
    else if(c.op!=='status'&&c.op!=='close')throw Error('Unknown physics operation');
    console.log(JSON.stringify(sim.packet()));
    if(c.op==='close'){closed=true;break;}
  }catch(e){console.log(JSON.stringify({error:String(e)}));}
}
clearInterval(timer);sim.dispose();
