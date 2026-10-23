import fs from 'node:fs';
import {performance} from 'node:perf_hooks';
import {createHash} from 'node:crypto';
import {simulate} from '../app/ui/micro-physics.mjs';
const [input,output]=process.argv.slice(2);
if(!input||!output)throw Error('Usage: node scripts/run-component-physics.mjs input.json output.json');
const trials=JSON.parse(fs.readFileSync(input,'utf8')),results=[];
const modelHash=createHash('sha256').update(fs.readFileSync(new URL('../app/ui/micro-physics.mjs',import.meta.url))).digest('hex');
for(const trial of trials){
  if(trial.snapshot.model_sha256!==modelHash)throw Error('Physics code changed after the trial was frozen');
  const start=performance.now();
  const result=await simulate(trial.snapshot.assembly,trial.snapshot.scenario,{seed:trial.snapshot.seed,dt:trial.snapshot.dt_s});
  result.seed=trial.snapshot.seed;result.wall_seconds=(performance.now()-start)/1000;result.trial_sha256=trial.sha256;result.model_sha256=modelHash;
  results.push({id:trial.id,result});
  console.log(`${result.configuration} / ${result.scenario}: flight=${result.flight_passed?'PASS':'FAIL'}, reserve=${result.static_reserve.thrust_weight.toFixed(2)}x`);
}
fs.writeFileSync(output,JSON.stringify({results,physics_process_peak_rss_mib:process.resourceUsage().maxRSS/1024},null,2)+'\n');
