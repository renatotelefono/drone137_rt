const $=id=>document.getElementById(id);
const session=crypto.randomUUID();
const names={'drone-01':'Scout 01','drone-02':'Scout 02'};
const colors={'drone-01':'#bbe5a4','drone-02':'#83bfe8'};
let state,area=[0,0,12,10],draft=null,pending=false,polling=false,drawing=null,siteGeneration,findingsKey='',historyKey='';
const active=s=>['exploring','observing','returning'].includes(s);
const element=(tag,text,className)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;};
function error(e){$('error').textContent=e.message||String(e);$('error').hidden=false;}
async function post(path,body={}){
 const response=await fetch(path,{method:'POST',headers:{'X-Drone137-Control':'local','Content-Type':'application/json'},body:JSON.stringify(body)});
 const value=await response.json();if(!response.ok)throw new Error(value.error||'Request failed');return value;
}
async function action(callback){if(pending)return;pending=true;$('error').hidden=true;controls();try{await callback();}catch(e){error(e);}finally{pending=false;await poll();controls();}}
function inputs(){return{instruction:$('instruction').value,area:[...area],drones:[...document.querySelectorAll('[name=drone]:checked')].map(e=>e.value)};}
function invalidate(){draft=null;$('plan-review').hidden=true;controls();}
function selectedPoints(){return(state?.scene.checkpoints||[]).filter(c=>c.position[0]>=area[0]&&c.position[0]<=area[2]&&c.position[1]>=area[1]&&c.position[1]<=area[3]);}
function setArea(value,preset){
 area=value;for(const [i,id] of ['x0','y0','x1','y1'].entries())$(id).value=area[i];
 document.querySelectorAll('[data-area]').forEach(b=>b.classList.toggle('selected',b.dataset.area===preset));
 invalidate();drawMap();
}
function controls(){
 const busy=!!state?.busy,locked=pending||busy,ready=state?.model.ready&&!state?.model.busy;
 const siteDirty=state&&['scenario','variant','seed','condition'].some(id=>String($(id).value)!==String(state.scene[id]));
 for(const id of ['scenario','variant','seed','instruction','x0','y0','x1','y1','site-load'])$(id).disabled=locked;
 $('condition').disabled=locked||$('scenario').value!=='realism';
 document.querySelectorAll('[data-area],[data-brief],[name=drone]').forEach(e=>e.disabled=locked);
 $('plan').disabled=locked||!ready||siteDirty||!!state?.reset_required||!selectedPoints().length||!inputs().drones.length;
 $('plan').textContent=pending?'Working with local controller…':'Generate plan with Qwen →';
 $('launch').disabled=locked||siteDirty||!draft?.dispatchable||!ready||!draft.assignments.every(a=>state?.drones.find(d=>d.id===a.drone_id)?.camera_ready);
 $('stop').disabled=!busy||pending||!!state?.planning;
 $('return').disabled=!busy||pending||!state?.drones.some(d=>active(d.state));
 $('model-start').hidden=!!ready;$('model-start').disabled=locked||!!state?.model.busy;
 $('model-start').textContent=state?.model.busy?'Starting…':state?.model.state==='restart_required'?'Restart model':'Start model';
 $('plan-hint').textContent=state?.reset_required?'Reset the virtual site to clear a stopped or failed aircraft.':siteDirty?'Load the selected virtual site before planning a mission.':!ready?'Start the local model to interpret your mission brief.':'Qwen interprets the brief. Review the task and assignments before dispatch.';
}
function svgNode(name,attributes,text){const e=document.createElementNS('http://www.w3.org/2000/svg',name);for(const [k,v] of Object.entries(attributes))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;return e;}
function drawMap(){
 if(!state)return;
 const g=$('map-content');g.replaceChildren();
 g.append(svgNode('rect',{x:0,y:0,width:720,height:600,fill:'#101b23'}));
 for(let x=0;x<=720;x+=30)g.append(svgNode('line',{x1:x,x2:x,y1:0,y2:600,stroke:x%60?'#1a2933':'#243641','stroke-width':1}));
 for(let y=0;y<=600;y+=30)g.append(svgNode('line',{y1:y,y2:y,x1:0,x2:720,stroke:y%60?'#1a2933':'#243641','stroke-width':1}));
 for(const b of state.scene.obstacles)g.append(svgNode('rect',{x:(b.x-b.sx/2)*60,y:(b.y-b.sy/2)*60,width:b.sx*60,height:b.sy*60,rx:2,fill:b.kind==='partition'||b.kind==='wall'?'#566873':'#334752',stroke:'#627681','stroke-width':1}));
 g.append(svgNode('rect',{x:area[0]*60,y:area[1]*60,width:Math.max(0,(area[2]-area[0])*60),height:Math.max(0,(area[3]-area[1])*60),fill:'#bbe5a40d',stroke:'#a0ca8a','stroke-width':2,'stroke-dasharray':'6 5'}));
 const selection=new Set(selectedPoints().map(c=>c.id));
 for(const [index,c] of state.scene.checkpoints.entries()){
  const selected=selection.has(c.id),[x,y]=c.position.map(v=>v*60);
  // Different yaw inspections may share a camera position; offset only the label.
  const duplicate=state.scene.checkpoints.slice(0,index).some(p=>p.position.toString()===c.position.toString());
  const dy=duplicate?36:0;
  if(duplicate)g.append(svgNode('line',{x1:x,y1:y,x2:x,y2:y+dy,stroke:'#91a2ad','stroke-dasharray':'3 3'}));
  g.append(svgNode('line',{x1:x,y1:y,x2:x+24*Math.cos(c.yaw),y2:y+24*Math.sin(c.yaw),stroke:selected?'#d7e7cf':'#667985','stroke-width':2}));
  g.append(svgNode('circle',{cx:x,cy:y+dy,r:11,fill:selected?'#c5d5bd':'#41545f',stroke:'#0e181f','stroke-width':3}));
  g.append(svgNode('text',{x,y:y+dy+4,'text-anchor':'middle',fill:'#102016','font-size':11,'font-family':'monospace'},index+1));
  const leftLabel=c.id==='stock-rack';
  g.append(svgNode('text',{x:x+(leftLabel?-17:17),y:y+dy+4,'text-anchor':leftLabel?'end':'start',fill:selected?'#d8e4db':'#708693','font-size':11,'font-family':'sans-serif'},c.id.replaceAll('-',' ')));
 }
 g.append(svgNode('rect',{x:48,y:48,width:54,height:54,rx:10,fill:'#223a30',stroke:'#7d9d76'}));
 g.append(svgNode('text',{x:75,y:79,'text-anchor':'middle',fill:'#b7d8ac','font-size':11,'font-family':'monospace'},'HOME'));
 for(const drone of state.drones){
  const job=state.mission?.jobs.find(j=>j.drone_id===drone.id);
  if(job&&['running','finalizing'].includes(job.state)){
   const [x,y,,yaw]=drone.pose;
   g.append(svgNode('circle',{cx:x*60,cy:y*60,r:17,fill:colors[drone.id]+'33'}));
   g.append(svgNode('path',{d:'M 13 0 L -8 -8 L -5 0 L -8 8 Z',transform:`translate(${x*60} ${y*60}) rotate(${yaw*180/Math.PI})`,fill:colors[drone.id],stroke:'#0c171c','stroke-width':2}));
  }
 }
 $('area-size').textContent=`${Math.max(0,(area[2]-area[0])*(area[3]-area[1])).toFixed(1)} m²`;
 $('view-count').textContent=`${selection.size} / ${state.scene.checkpoints.length} viewpoints`;
 $('selection-label').textContent=`Selection: (${area[0].toFixed(1)}, ${area[1].toFixed(1)}) → (${area[2].toFixed(1)}, ${area[3].toFixed(1)}) m`;
}
function renderFleet(){
 $('fleet-cards').replaceChildren(...state.drones.map((d,index)=>{
  const job=state.mission?.jobs.find(j=>j.drone_id===d.id),status=job?.state||'docked';
  const card=element('div',undefined,'drone-card'),title=element('div',undefined,'drone-title'),heading=element('h3');
  heading.append(element('span',undefined,`aircraft-color ${index?'scout-two':'scout-one'}`),document.createTextNode(d.name));
  title.append(heading,element('span',status==='running'?d.state:status,`drone-status ${status}`));card.append(title);
  card.append(element('p',job?job.points.map(p=>p.replaceAll('-',' ')).join(' · '):'Awaiting an assignment'));
  const ownFlight=job?.episode&&job.episode===d.episode;
  const metrics=element('div',undefined,'drone-metrics');metrics.append(element('span',`${(ownFlight?d.distance_m:0).toFixed(1)} m flown`),element('span',`${ownFlight?d.observations.length:0} views`));card.append(metrics);
  card.append(element('p',d.camera_ready?'● Camera connected':'○ Waiting for camera'));
  if(job?.report_page){const a=element('a','View flight report ↗');a.href=job.report_page;a.target='_blank';a.rel='noopener';card.append(a);}
  $('camera-0'+(index+1)+'-state').textContent=active(d.state)?d.state:state.reset_required?'STOPPED · RESET':d.video_complete&&d.observations.length?'LAST OBSERVATION':d.camera_ready?'LIVE · DOCKED':'CONNECTING';
  return card;
 }));
}
function renderFindings(){
 const observations=state.drones.flatMap(d=>state.mission?.jobs.some(j=>j.episode===d.episode)?d.observations.map(o=>({d,o})):[]).sort((a,b)=>b.o.received_monotonic-a.o.received_monotonic);
 const key=JSON.stringify(observations.map(({d,o})=>[d.episode,o.image,active(d.state)]));if(key===findingsKey)return;findingsKey=key;
 $('findings').replaceChildren(...observations.map(({d,o})=>{
  const row=element('div',undefined,'finding-row'),img=document.createElement('img');img.src=`/reports/${d.episode}/${o.image}`;img.alt=`${d.name} evidence at ${o.view}`;img.loading='lazy';
  const detail=element('div');detail.append(element('h3',`${d.name} / ${o.view?.replaceAll('-',' ')||'Observation'}`),element('p',o.survey?.summary||o.observation));
  if(o.survey?.uncertainty)detail.append(element('small',`Uncertain: ${o.survey.uncertainty}`));
  if(o.change?.status==='new_obstruction')detail.append(element('p','New obstruction reported against the previous matching view.'));
  if(!active(d.state)){const a=element('a','Open video & evidence ↗');a.href=`/reports/${d.episode}/report.html`;a.target='_blank';a.rel='noopener';detail.append(a);}
  row.append(img,detail);return row;
 }));
 if(!observations.length)$('findings').append(element('p','Camera observations will appear here during the mission.','empty'));
}
function review(plan){
 draft=plan;$('plan-review').hidden=false;
 const tasks={inventory:'Object inventory',passage:'Doorway inspection',changes:'Compare camera views',unsupported:'Unsupported task'};
 $('plan-summary').textContent=`${tasks[plan.objective]} — ${plan.summary}${plan.focus?' Focus: '+plan.focus+'.':''}`;
 $('plan-note').textContent=plan.note;
 $('assignments').replaceChildren(...plan.assignments.map((a,index)=>{const row=element('div',undefined,'assignment');row.append(element('b',`${index+1}. ${names[a.drone_id]}`),element('span',a.points.map(p=>p.replaceAll('-',' ')).join(' → ')));return row;}));
 $('launch').hidden=!plan.dispatchable;controls();$('plan-review').scrollIntoView({behavior:'smooth',block:'nearest'});
}
function update(value){
 state=value;
 if(siteGeneration!==value.generation){siteGeneration=value.generation;for(const id of ['scenario','variant','seed','condition'])$(id).value=value.scene[id];invalidate();}
 $('model-state').textContent=state.model.ready?'Local model ready':state.model.error||state.model.state.replaceAll('_',' ');
 $('model-dot').classList.toggle('ready',state.model.ready);
 const mission=state.mission;
 $('mission-state').textContent=state.planning?'Interpreting your brief':mission?({complete:'Mission complete',needs_review:'Review required',running:'Mission in progress',queued:'Dispatch queued',returning:'Returning to home',stopping:'Stopping the fleet',failed:'Dispatch failed'}[mission.state]||mission.state):state.reset_required?'Site reset required':'Ready to plan';
 $('mission-reason').textContent=state.error||mission?.reason||'Select an area and generate your first mission.';
 $('mission-report').hidden=!mission;if(mission)$('mission-report').href=`/reports/${mission.id}/report.html`;
 drawMap();renderFleet();renderFindings();controls();
 const key=mission?.id+':'+mission?.state;
 if(key!==historyKey){historyKey=key;history();}
}
async function poll(){if(polling)return;polling=true;try{const r=await fetch('/api/fleet/status',{cache:'no-store'});if(!r.ok)throw new Error('Mission controller unavailable');update(await r.json());}catch(e){error(e);}finally{polling=false;}}
async function history(){try{const r=await fetch('/api/runs',{cache:'no-store'});if(!r.ok)throw new Error('Report history unavailable');const runs=(await r.json()).filter(r=>r.task_context?.fleet_mission).slice(0,8);$('history').replaceChildren(...runs.map(run=>{const row=element('div',undefined,'history-row'),a=element('a',`${names[run.task_context.drone_id]||run.task_context.drone_id} · ${run.task_context.objective} · seed ${run.seed}`);a.href=run.report_page;a.target='_blank';a.rel='noopener';row.append(a,element('span',`${run.state} · ${run.distance_m?.toFixed(1)||0} m · ${run.video?.complete?'video saved':'video incomplete'}`));return row;}));if(!runs.length)$('history').append(element('p','Completed aircraft reports will be retained here.','empty'));}catch(e){error(e);}}
const presets={all:[0,0,12,10],west:[0,0,5.5,10],east:[6.5,0,12,10]};
document.querySelectorAll('[data-area]').forEach(b=>b.onclick=()=>setArea([...presets[b.dataset.area]],b.dataset.area));
document.querySelectorAll('[data-brief]').forEach(b=>b.onclick=()=>{$('instruction').value=b.dataset.brief;invalidate();});
for(const id of ['instruction'])$(id).oninput=invalidate;
document.querySelectorAll('[name=drone]').forEach(e=>e.onchange=invalidate);
for(const id of ['x0','y0','x1','y1'])$(id).onchange=()=>{const candidate=['x0','y0','x1','y1'].map(id=>Number($(id).value));if(candidate.every(Number.isFinite)&&candidate[0]>=0&&candidate[1]>=0&&candidate[2]<=12&&candidate[3]<=10&&candidate[2]-candidate[0]>=.5&&candidate[3]-candidate[1]>=.5)setArea(candidate);else{error(new Error('Select a valid rectangle inside the site, at least 0.5 m wide and deep.'));for(const [i,key] of ['x0','y0','x1','y1'].entries())$(key).value=area[i];}};
$('scenario').onchange=()=>{$('condition').value='nominal';invalidate();};
for(const id of ['variant','seed','condition'])$(id).onchange=invalidate;
$('site-load').onclick=()=>action(async()=>{const result=await post('/api/fleet/site',{seed:Number($('seed').value),scenario:$('scenario').value,variant:$('variant').value,condition:$('scenario').value==='realism'?$('condition').value:'nominal'});update(result);setArea([0,0,12,10],'all');});
$('plan').onclick=()=>action(async()=>review(await post('/api/fleet/plan',inputs())));
$('launch').onclick=()=>action(async()=>{if(!draft)throw new Error('Generate a mission plan first');const result=await post('/api/fleet/launch',{draft_id:draft.id,session});invalidate();update(result);$('mission-state').scrollIntoView({behavior:'smooth',block:'center'});});
$('stop').onclick=()=>action(async()=>update(await post('/api/fleet/stop')));
$('return').onclick=()=>action(async()=>update(await post('/api/fleet/return')));
$('model-start').onclick=()=>action(async()=>{await post('/api/model/start');});
$('refresh-history').onclick=history;
const map=$('site-map');
function position(event){const p=new DOMPoint(event.clientX,event.clientY).matrixTransform(map.getScreenCTM().inverse());return[Math.max(0,Math.min(12,Math.round(p.x/60*4)/4)),Math.max(0,Math.min(10,Math.round(p.y/60*4)/4))];}
map.onpointerdown=e=>{if(pending||state?.busy)return;drawing={start:position(e),old:[...area]};map.setPointerCapture(e.pointerId);};
map.onpointermove=e=>{if(!drawing)return;const end=position(e),start=drawing.start;setArea([Math.min(start[0],end[0]),Math.min(start[1],end[1]),Math.max(start[0],end[0]),Math.max(start[1],end[1])]);};
map.onpointerup=e=>{if(!drawing)return;const old=drawing.old;drawing=null;if(area[2]-area[0]<.5||area[3]-area[1]<.5)setArea(old);map.releasePointerCapture(e.pointerId);};
map.onpointercancel=()=>{if(drawing){const old=drawing.old;drawing=null;setArea(old);}};
for(const [index,id] of Object.keys(names).entries())$('camera-0'+(index+1)).src='/camera-worker?'+new URLSearchParams({drone:id,session});
setInterval(poll,500);poll();
