const $=id=>document.getElementById(id);let state,lastRun,lastSteps=-1,trail=[],working=false,connectionError;
const identityLabel=s=>s.action==='found'?'Verified in two views':s.identity?.supported?'Both models support this view; location not yet verified':s.identity?`Rejected candidate · Qwen: ${s.identity.parts?.category||'uncertain'} · Florence: ${s.identity.independent_review?.accepted?'supports target':'does not confirm'}`:'No target proposed';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function post(op,body={}){const r=await fetch('/api/mission/'+op,{method:'POST',headers:{'Content-Type':'application/json','X-Drone137-Control':'local'},body:JSON.stringify(body)});const x=await r.json();if(!r.ok)throw Error(x.error||r.status);return x;}
async function action(fn){working=true;$('error').textContent='';try{await fn();}catch(e){$('error').textContent=e.message;}finally{working=false;await refresh();}}
$('plan').onclick=()=>action(async()=>{await post('plan',{instruction:$('instruction').value,assembly:$('assembly').value,case:$('case').value,area:['west','south','east','north'].map(k=>Number($(k).value)),template:document.body.dataset.template||null});});
$('launch').onclick=()=>action(()=>post('launch',{draft_id:state.draft.id}));
$('return').onclick=()=>action(()=>post('return'));$('stop').onclick=()=>action(()=>post('stop'));
$('model-start').onclick=()=>action(async()=>{const r=await fetch('/api/model/start',{method:'POST',headers:{'X-Drone137-Control':'local','Content-Type':'application/json'},body:'{}'});if(!r.ok)throw Error('Could not start model; check model setup in the Recon lab.');});
for(let x=50;x<600;x+=50)$('grid').innerHTML+=`<path d="M${x} 0V500" stroke="#29404a"/>`;
for(let y=50;y<500;y+=50)$('grid').innerHTML+=`<path d="M0 ${y}H600" stroke="#29404a"/>`;
async function refresh(){try{
 const r=await fetch('/api/mission/status');if(!r.ok)throw Error('Mission service unavailable');state=await r.json();
 if(connectionError&&$('error').textContent===connectionError)$('error').textContent='';connectionError=null;
 if(!$('assembly').options.length){$('assembly').innerHTML=state.assemblies.map(a=>`<option value="${esc(a.reference)}">${esc(a.name)}</option>`).join('');$('assembly').value=state.assemblies.find(a=>a.reference.startsWith('scout-110-bench-b@'))?.reference||state.assemblies[0].reference;$('case').innerHTML=state.cases.map(c=>`<option value="${esc(c.id)}">${esc(c.id)}</option>`).join('');}
 $('connection').textContent=state.busy?'Local service · mission active':'Local service · connected';
 if(state.model){$('model-status').textContent=state.model.name+' · '+state.model.state;$('model-start').hidden=state.model.ready||state.model.external;$('model-start').disabled=state.busy||state.model.busy;}
 $('plan').disabled=working||state.busy||state.model?.ready===false;$('launch').disabled=working||state.busy||!state.draft?.dispatchable;
 for(const id of ['assembly','case','instruction','west','south','east','north'])$(id).disabled=working||state.busy;
 $('return').disabled=$('stop').disabled=!state.busy||!state.mission;
 if(state.draft)$('draft').textContent=state.draft.dispatchable?`${state.draft.intent.summary} ${state.draft.views.length} inspection areas. Aircraft mass: ${(state.draft.assembly.mass_kg*1000).toFixed(1)} g.`:'This mission is not supported. Request an indoor red fire extinguisher search.';
 const run=state.mission,p=state.vehicle;if(run?.id!==lastRun){trail=[];lastRun=run?.id;lastSteps=-1;$('obstacles').innerHTML='';$('error').textContent='';
  if(run)$('draft').textContent=`${run.plan.intent.summary} ${run.plan.views.length} inspection areas. Aircraft mass: ${(run.plan.assembly.mass_kg*1000).toFixed(1)} g.`;
  if(run&&state.busy){const c=run.plan.assembly.configuration;$('assembly').value=`${c.content.id}@${c.revision}`;$('case').value=run.plan.case;$('instruction').value=run.plan.instruction;['west','south','east','north'].forEach((id,i)=>$(id).value=run.plan.area[i]);}}
 if(state.map&&!$('obstacles').children.length)$('obstacles').innerHTML=[...state.map.obstacles,...state.map.fixtures].map(b=>`<rect x="${(b.x-b.sx/2)*50}" y="${(10-b.y-b.sy/2)*50}" width="${b.sx*50}" height="${b.sy*50}" fill="#526b75" opacity=".75"/>`).join('');
 $('state').textContent=run?.state||'Ready';
 $('active-mission').textContent=run?`${run.plan.template?run.plan.template.toUpperCase()+' · ':''}${run.plan.case} · ${run.plan.assembly.configuration.content.name} · ${run.plan.instruction}`:'';
 const a=state.draft?.area||run?.plan.area||[0,0,12,10];Object.entries({x:a[0]*50,y:(10-a[3])*50,width:(a[2]-a[0])*50,height:(a[3]-a[1])*50}).forEach(([k,v])=>$('area').setAttribute(k,v));
 $('drone').style.visibility=p?'visible':'hidden';
 if(p){const [x,y,z]=p.position;if(state.busy)trail.push([x*50,(10-y)*50]);if(trail.length>1000)trail.shift();$('trail').setAttribute('points',trail.map(p=>p.join(',')).join(' '));$('drone').setAttribute('transform',`translate(${x*50},${(10-y)*50}) rotate(${-p.yaw*180/Math.PI})`);$('telemetry').textContent=`${x.toFixed(2)}, ${y.toFixed(2)} m · altitude ${z.toFixed(2)} m · ${p.voltage_v.toFixed(2)} V · ${p.speed.toFixed(2)} m/s`;}else $('telemetry').textContent='Waiting for telemetry';
 if(run){$('camera').hidden=false;$('camera-empty').hidden=true;$('camera-empty').style.display='none';$('camera').src='/api/mission/frame?t='+Date.now();$('outcome').textContent=run.location?`Verified visual candidate at ${run.location.xy_m.map(x=>x.toFixed(2)).join(', ')} m`:(run.outcome==='unresolved'&&run.state==='complete'?'Search completed without a verified target. This does not prove absence.':'');if(run.error)$('error').textContent=run.error;
 $('report').hidden=!['complete','failed','cancelled'].includes(run.state);$('report').href=run.report;
 if(run.steps.length!==lastSteps){lastSteps=run.steps.length;$('findings').innerHTML=run.steps.map(s=>`<article><img src="/api/mission/runs/${run.id}/${s.image}"><p><strong>${esc(identityLabel(s))}</strong></p><p>${esc(s.visual.evidence)}</p><small>${esc(s.action)} · ${s.latency_s.toFixed(1)} s</small></article>`).join('');}}
 }catch(e){$('connection').textContent='Disconnected — service state unknown';connectionError=e.message;$('error').textContent=e.message;}}
async function history(){try{const rows=await(await fetch('/api/mission/runs')).json();$('history').innerHTML=rows.slice(0,8).map(r=>`<p><a href="${esc(r.report)}">${esc(r.template?r.template+' · ':'')}${esc(r.state)} · ${esc(r.outcome)}</a> — ${new Date(r.started_at*1000).toLocaleString()}</p>`).join('');}catch{}}
await refresh();await history();setInterval(refresh,1000);setInterval(history,10000);
