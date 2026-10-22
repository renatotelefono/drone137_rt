// Real-model dashboard integration: interpreted brief, isolated dispatch, video.
const {chromium}=require('../.local/browser-test/node_modules/playwright');
const fs=require('node:fs');
const output='.local/validation/mission-control-live.json';
const result={real_inference:true,real_flight_dynamics:false,concurrent_flight:false,errors:[],intent_checks:[]};
let browser,page;
(async()=>{
 browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--no-sandbox']});
 result.browser=await browser.version();page=await browser.newPage({viewport:{width:1560,height:1100}});
 page.on('pageerror',e=>result.errors.push(e.message));
 const status=()=>page.evaluate(async()=>(await fetch('/api/fleet/status')).json());
 const post=(path,body={})=>page.evaluate(async({path,body})=>{const r=await fetch(path,{method:'POST',headers:{'X-Drone137-Control':'local','Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw new Error(data.error);return data;},{path,body});
 await page.goto('http://127.0.0.1:8137/control');
 await page.waitForFunction(()=>document.querySelector('#model-state').textContent!=='Connecting…');
 if(!(await status()).model.ready){await page.click('#model-start');await page.waitForFunction(async()=>(await(await fetch('/api/fleet/status')).json()).model.ready,null,{timeout:150000});}
 await page.waitForFunction(async()=>(await(await fetch('/api/fleet/status')).json()).drones.every(d=>d.camera_ready),null,{timeout:45000});
 await page.waitForFunction(()=>!document.querySelector('#plan').disabled,null,{timeout:150000});
 await page.screenshot({path:'.local/validation/mission-control-ready.png',fullPage:true});
 const body={area:[0,0,12,10],drones:['drone-01','drone-02']};
 for(const [instruction,objective] of [['Deliver a parcel to the hillside outside.','unsupported'],['Inspect the central doorway for obstructions.','passage']]){
  const draft=await post('/api/fleet/plan',{...body,instruction});result.intent_checks.push(draft);
  if(draft.objective!==objective)throw new Error(`Intent mismatch: expected ${objective}, got ${draft.objective}`);
  if(objective==='unsupported'&&draft.dispatchable)throw new Error('Unsupported mission was dispatchable');
  if(objective==='passage'&&draft.assignments.flatMap(a=>a.points).join()!=='passage')throw new Error('Doorway task was not constrained to doorway inspection');
 }
 // Check an operator stop before the first observation, then reset for a full run.
 await page.click('[data-area=west]');await page.click('[data-brief^="Inventory"]');await page.click('#plan');
 await page.waitForFunction(()=>!document.querySelector('#launch').disabled,{},{timeout:20000});
 await page.click('#launch');
 await page.waitForFunction(async()=>(await(await fetch('/api/fleet/status')).json()).mission?.jobs[0].state==='running');
 await page.click('#stop');
 await page.waitForFunction(async()=>!(await(await fetch('/api/fleet/status')).json()).busy,null,{timeout:20000});
 const stopped=await status();result.operator_stop=stopped.mission;
 if(!stopped.reset_required||stopped.mission.jobs[1].state!=='cancelled')throw new Error('Stop failed to cancel the queue and require site reset');
 await page.click('#site-load');
 await page.waitForFunction(async()=>{const s=await(await fetch('/api/fleet/status')).json();return !s.reset_required&&s.drones.every(d=>d.camera_ready);},null,{timeout:30000});
 const drag=await page.locator('#site-map').evaluate(svg=>[new DOMPoint(60,60),new DOMPoint(330,540)].map(p=>{const q=p.matrixTransform(svg.getScreenCTM());return{x:q.x,y:q.y};}));
 await page.mouse.move(drag[0].x,drag[0].y);await page.mouse.down();await page.mouse.move(drag[1].x,drag[1].y,{steps:8});await page.mouse.up();
 if(await page.inputValue('#x0')!=='1'||await page.inputValue('#x1')!=='5.5')throw new Error('Map drag did not update mission area coordinates');
 result.map_drag_passed=true;
 await page.click('[data-area=all]');await page.click('[data-brief^="Inventory"]');await page.click('#plan');
 await page.waitForFunction(()=>!document.querySelector('#launch').disabled,{},{timeout:20000});
 const plan=(await status()).draft;result.plan=plan;
 if(plan.objective!=='inventory'||plan.assignments.length!==2||new Set(plan.assignments.flatMap(a=>a.points)).size!==6)throw new Error('Full-site plan did not partition six views across two aircraft');
 await page.screenshot({path:'.local/validation/mission-control-plan.png',fullPage:true});
 await page.click('#launch');
 let state=await status(),previous='',peak=0,shot=false;const deadline=Date.now()+390000;
 while(state.busy&&Date.now()<deadline){
  const flying=state.drones.filter(d=>['exploring','observing','returning'].includes(d.state)).length;peak=Math.max(peak,flying);
  if(flying>1)throw new Error('Shared-airspace exclusion failed');
  const change=JSON.stringify(state.mission.jobs.map(j=>[j.drone_id,j.state,state.drones.find(d=>d.id===j.drone_id).observations.length]));
  if(change!==previous){console.log(JSON.stringify({event:'fleet_progress',jobs:JSON.parse(change)}));previous=change;}
  if(!shot&&state.drones[0].observations.length>=1){shot=true;await page.screenshot({path:'.local/validation/mission-control-running.png',fullPage:true});}
  await page.waitForTimeout(1000);state=await status();
 }
 result.mission=state.mission;result.peak_aircraft_in_flight=peak;
 if(state.mission.state!=='complete')throw new Error('Fleet mission did not complete: '+JSON.stringify(state.mission));
 result.runs=[];
 for(const job of state.mission.jobs){
  const report=await browser.newPage();report.on('pageerror',e=>result.errors.push(e.message));
  await report.goto('http://127.0.0.1:8137'+job.report_page);
  const summary=await report.evaluate(async()=>(await fetch('summary.json')).json());
  if(summary.state!=='complete'||!summary.video.complete||summary.task_context.drone_id!==job.drone_id)throw new Error('Aircraft evidence incomplete or assigned to wrong identity');
  if(!job.points.every(p=>summary.observations.some(o=>o.view===p)))throw new Error('Assigned inspection view missing');
  if(summary.observations.some(o=>!o.survey?.summary))throw new Error('Missing real-model object descriptions');
  await report.waitForFunction(()=>document.querySelector('video')?.readyState>=2);
  await report.locator('video').evaluate(async v=>{v.muted=true;await v.play();});
  await report.waitForFunction(()=>document.querySelector('video').currentTime>.2);
  await report.locator('video').evaluate((v,t)=>{v.pause();v.currentTime=t;},summary.observations[0].video_time_s);
  await report.waitForFunction(()=>{const v=document.querySelector('video');return !v.seeking&&v.readyState>=2;});
  const video=await report.locator('video').evaluate(v=>({width:v.videoWidth,height:v.videoHeight}));
  if(video.width!==1280||video.height!==720)throw new Error('Wrong video resolution');
  result.runs.push({episode:job.episode,...summary,decoded_video:video});await report.close();
 }
 await page.waitForTimeout(1000);await page.screenshot({path:'.local/validation/mission-control-complete.png',fullPage:true});
 const inlineErrors=await Promise.all(page.frames().filter(f=>f.url().includes('camera-worker')).map(f=>f.locator('#error').evaluate(e=>e.hidden?'':e.textContent)));
 for(const frame of page.frames().filter(f=>f.url().includes('camera-worker'))){
  await frame.waitForFunction(()=>{const i=document.getElementById('last-observation');return !i.hidden&&i.complete&&i.naturalWidth===960;});
 }
 result.last_observation_previews_passed=true;
 result.errors.push(...inlineErrors.filter(Boolean));
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'.local/validation/mission-control-mobile.png',fullPage:true});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw new Error('Mobile dashboard overflows viewport');
 if(result.errors.length)throw new Error(result.errors.join('; '));
 result.passed=true;fs.writeFileSync(output,JSON.stringify(result,null,2));await browser.close();
 console.log('PASS: local-model intent, operator stop, two sequential aircraft, six assigned views, isolated playable 720p videos. '+output);
})().catch(async e=>{result.failure=e.message;fs.writeFileSync(output,JSON.stringify(result,null,2));console.error(e);if(page)await page.screenshot({path:'.local/validation/mission-control-failure.png',fullPage:true}).catch(()=>{});if(browser)await browser.close();process.exitCode=1;});
