// Dedicated ground transport. Model/UI work cannot delay its 20 Hz radio pump.
// The aircraft still has its original 0.5 s command watchdog. This process owns
// a bounded setpoint lease, never an indefinitely latched motor command.
const {spawn}=require('node:child_process');
const readline=require('node:readline');
const fs=require('node:fs'),path=require('node:path');
const input=process.argv[2],eventFile=path.join(path.dirname(input),'transport-events.jsonl');
const worker=spawn(process.execPath,['scripts/mission-physics.mjs',input],{stdio:['pipe','pipe','inherit']});
let packet,received=0,goal=null,renewed=0,closing=false,orphaned=false,expired=false,workerError=null;
let readyResolve;const ready=new Promise(r=>readyResolve=r);
const event=(stage)=>fs.appendFileSync(eventFile,JSON.stringify({time:Date.now()/1000,stage})+'\n');
const send=value=>{if(worker.exitCode===null&&!worker.stdin.destroyed)worker.stdin.write(JSON.stringify(value)+'\n');};
readline.createInterface({input:worker.stdout}).on('line',line=>{
 try{const x=JSON.parse(line);if(x.error)workerError=x.error;else{packet=x;received=performance.now();readyResolve();}}
 catch(e){workerError=String(e);readyResolve();}
});
worker.on('error',e=>{workerError=String(e);readyResolve();});
worker.stdin.on('error',e=>{workerError=String(e);readyResolve();});
const ended=new Promise(resolve=>worker.on('exit',code=>{if(!closing)workerError='Physics worker exited: '+code;readyResolve();resolve();}));
const timer=setInterval(()=>{
 if(closing)return;
 const valid=goal&&!orphaned&&!expired&&performance.now()-renewed<2000;
 if(goal&&!valid&&!expired){expired=true;event('supervisor-lease-expired; radio commands withheld');}
 send(valid?{op:'command',target:goal}:{op:'status'});
},50);
async function close(){
 if(closing)return;
 closing=true;clearInterval(timer);send({op:'close'});
 const timeout=setTimeout(()=>worker.kill('SIGKILL'),3000);
 await ended;clearTimeout(timeout);
}
let orphanTimer;
function orphan(){
 if(orphaned||closing)return;
 orphaned=true;event('supervisor-disconnected; radio commands withheld');
 const started=performance.now();
 orphanTimer=setInterval(async()=>{
  if((packet&&packet.position[2]<.05&&packet.speed<.15)||performance.now()-started>15000){
   clearInterval(orphanTimer);await close();process.exitCode=1;
  }
 },100);
}
process.on('SIGTERM',orphan);process.stdin.on('end',orphan);
// A supervisor crash can close stdout before stdin EOF is delivered. Keep the
// transport alive long enough for the aircraft watchdog to finish landing.
process.stdout.on('error',orphan);
function status(){
 if(workerError)throw Error(workerError);
 if(!packet)throw Error('No aircraft telemetry');
 return {...packet,transport:{heartbeat_hz:20,supervisor_lease_s:2,sample_age_s:(performance.now()-received)/1000,
   supervisor_lease_expired:expired}};
}
(async()=>{
 await ready;
 for await(const line of readline.createInterface({input:process.stdin})){
  try{
   const c=JSON.parse(line);
   if(c.op==='close'){await close();console.log(JSON.stringify(status()));process.stdin.destroy();break;}
   if(c.op==='command'){
    const p=c.target;
    if(!Array.isArray(p)||p.length!==4||p.some(x=>!Number.isFinite(x))||p[0]<.2||p[0]>11.8||p[1]<.2||p[1]>9.8||p[2]<0||p[2]>1.8)throw Error('Invalid bounded setpoint');
    goal=p;
   }else if(c.op==='failsafe'){
    expired=true;event('supervisor-requested-failsafe; radio commands withheld');
   }else if(c.op!=='status')throw Error('Unknown transport operation');
   renewed=performance.now();console.log(JSON.stringify(status()));
  }catch(e){console.log(JSON.stringify({error:String(e)}));}
 }
 if(!closing)orphan();
})().catch(async e=>{console.error(e);await close();process.exitCode=1;});
