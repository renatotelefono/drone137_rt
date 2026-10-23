import * as THREE from './vendor/three.module.js';
import {initialize,MicroFlight,rotate} from './micro-physics.mjs';
const $=id=>document.getElementById(id);
let library,assembly,sim,trial,running=false,last=0,accumulator=0,lastCamera=-1,dirty=false,rotors=[];
const failure=e=>{$('error').textContent=e.message||String(e);};
async function post(op,body){const r=await fetch('/api/components/'+op,{method:'POST',headers:{'Content-Type':'application/json','X-Drone137-Control':'local'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error||'Request failed');return data;}
async function loadValidation(){
  const response=await fetch('/api/components/validation');if(!response.ok)return;
  const data=await response.json(),score=data.revised,extra=data.additional_seeds;
  $('validation').hidden=false;
  $('validation-score').textContent=`Original ${data.baseline.passed}/${data.baseline.total} → controller only ${data.controller_only.passed}/${data.controller_only.total} → revised designs ${score.passed}/${score.total} (${(100*score.passed/score.total).toFixed(1)}%). Additional noise seeds: ${extra.passed}/${extra.total} (${(100*extra.passed/extra.total).toFixed(1)}%).`;
  $('validation-rows').replaceChildren();
  for(const row of data.models){const tr=document.createElement('tr');
    for(const value of [row.name,row.baseline+'/6',row.controller_only+'/6',row.revised+'/6',row.additional_passed+'/'+row.additional_total]){const td=document.createElement('td');td.textContent=value;tr.append(td);}
    $('validation-rows').append(tr);
  }
  $('validation-limits').textContent=data.scope_note;
}
function option(parent,value,label){const o=new Option(label,value);parent.add(o);}
function populateComponent(id){const c=library.components.find(c=>c.content.id===id);$('component-json').value=JSON.stringify(c.content,null,2);}
async function load(selected){
  const r=await fetch('/api/components');if(!r.ok)throw Error('Cannot load component registry');library=await r.json();
  $('configuration').replaceChildren();
  for(const a of library.assemblies)option($('configuration'),a.configuration.content.id,a.configuration.content.name);
  $('configuration').value=selected||'scout-110-power-v2';select();
  const componentId=$('component').value;$('component').replaceChildren();
  for(const c of library.components)option($('component'),c.content.id,`${c.content.name} · r${c.revision}`);
  $('component').value=componentId||library.components[0].content.id;populateComponent($('component').value);
  renderHistory();
}
function select(){
  dirty=false;$('run').disabled=false;
  assembly=library.assemblies.find(a=>a.configuration.content.id===$('configuration').value);
  const counts=assembly.evidence_counts;
  $('assembly-summary').textContent=`${(assembly.mass_kg*1000).toFixed(1)} g assembled · propulsion: ${assembly.propulsion_evidence}. ${counts.specified} specified / ${counts.derived} derived / ${counts.estimated} estimated parameters. ${assembly.configuration.content.notes}`;
  $('slots').replaceChildren();
  for(const [slot,p] of Object.entries(assembly.components)){
    const label=document.createElement('label');label.textContent=slot==='propulsion'?'Motor + matched propeller (×4)':slot;
    const select=document.createElement('select');select.dataset.slot=slot;select.setAttribute('aria-label',slot+' component');
    const ref=assembly.configuration.content.components[slot];
    for(const c of library.components.filter(c=>c.content.kind===slot))option(select,c.content.id+'@'+c.revision,`${c.content.name} · r${c.revision}`);
    if(![...select.options].some(o=>o.value===ref))option(select,ref,`${p.content.name} · pinned r${p.revision}`);
    select.value=ref;select.onchange=()=>{dirty=true;$('run').disabled=true;$('saved').textContent='Save these component swaps before running.';};label.append(select);$('slots').append(label);
  }
  if(sim)sim.dispose();sim=new MicroFlight(assembly,$('scenario').value);buildDrone();renderState(sim.state());
}
function renderHistory(){
  $('history').replaceChildren();
  for(const h of library.history){const r=h.result;if(!r)continue;const tr=document.createElement('tr');
    for(const [value,style] of [[r.configuration+(r.configuration_revision?' @'+r.configuration_revision:''),''],[r.scenario,''],[r.seed??137,''],[r.propulsion_evidence,''],[r.flight_passed?'PASS':'FAIL',r.flight_passed?'pass':'fail'],[r.engineering_passed?'PASS':'FAIL',r.engineering_passed?'pass':'fail'],[(r.hover_rmse_m*100).toFixed(2)+' cm',''],[r.static_reserve.thrust_weight.toFixed(2)+'×',''],[(r.model_sha256||'legacy').slice(0,8),'']]){const td=document.createElement('td');td.textContent=value;td.className=style;tr.append(td);}
    $('history').append(tr);
  }
}
const scene=new THREE.Scene();scene.background=new THREE.Color('#17262b');scene.fog=new THREE.Fog('#17262b',5,12);
scene.add(new THREE.HemisphereLight(0xdaf2ff,0x354138,3));const light=new THREE.DirectionalLight(0xfff0d0,3);light.position.set(1,4,2);scene.add(light);
const box=(x,y,z,w,h,d,color)=>{const m=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),new THREE.MeshStandardMaterial({color,roughness:.8}));m.position.set(x,y,z);scene.add(m);return m;};
box(0,-.05,0,4,.1,4,'#35444a');scene.add(new THREE.GridHelper(4,20,0x73928e,0x43595d));
box(-2,1,0,.1,2,4,'#4c5d63');box(0,1,-2,4,2,.1,'#52666b');
box(-.9,.35,.8,.5,.7,.6,'#ae8a53');box(.9,.45,-.8,.4,.9,.6,'#647b88');
const pad=new THREE.Mesh(new THREE.RingGeometry(.13,.15,48),new THREE.MeshBasicMaterial({color:0xb9e9a2,side:THREE.DoubleSide}));pad.rotation.x=-Math.PI/2;pad.position.y=.002;scene.add(pad);
const target=box(.5,.02,.35,.12,.035,.12,'#b9e9a2');
const drone=new THREE.Group();scene.add(drone);
const cameras={world:new THREE.PerspectiveCamera(48,1,.01,30),detail:new THREE.PerspectiveCamera(45,4/3,.005,30),camera:new THREE.PerspectiveCamera(60,4/3,.01,20)};
cameras.world.position.set(1.65,1.65,2.4);cameras.world.lookAt(0,.35,0);
const renderers={};for(const name of ['world','detail','camera']){const r=new THREE.WebGLRenderer({canvas:$(name),antialias:true});r.setPixelRatio(1);r.setSize(name==='world'?800:640,name==='world'?410:480,false);renderers[name]=r;}
function buildDrone(){
  for(const child of [...drone.children]){drone.remove(child);child.geometry?.dispose();child.material?.dispose();}rotors=[];
  const p=sim.p;
  lastCamera=-1;renderers.camera.setSize(p.avionics.camera_width,p.avionics.camera_height,false);
  cameras.camera.aspect=p.avionics.camera_width/p.avionics.camera_height;cameras.camera.updateProjectionMatrix();
  $('camera-label').textContent=`Forward camera · ${p.avionics.camera_width} × ${p.avionics.camera_height} / ${p.avionics.camera_fps} fps / ${p.avionics.camera_latency_ms} ms simulated delay`;
  function mesh(geometry,color,pos){const m=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color,roughness:.5,metalness:.2}));m.position.set(pos.x,pos.y,pos.z);drone.add(m);return m;}
  mesh(new THREE.BoxGeometry(.042,p.frame.body_height_m/2,.035),'#31454d',{x:0,y:0,z:0});
  mesh(new THREE.BoxGeometry(.025,.012,.02),'#c1c7c8',{x:0,y:-.016,z:0});
  mesh(new THREE.BoxGeometry(.012,.012,.01),'#dcae6a',{x:0,y:.014,z:.02});
  for(const [i,at] of sim.mass.motors.entries()){
    mesh(new THREE.CylinderGeometry(.004,.004,.02,12),'#aaaeb5',at);
    const ring=mesh(new THREE.TorusGeometry(p.propulsion.prop_diameter_m/2+p.frame.guard_clearance_m,.001,6,36),i%2?'#b5dfb6':'#ebd9a6',at);ring.rotation.x=Math.PI/2;
    const arm=mesh(new THREE.BoxGeometry(.004,.004,Math.hypot(at.x,at.z)),'#455e64',{x:at.x/2,y:0,z:at.z/2});arm.rotation.y=Math.atan2(at.x,at.z);
    const prop=mesh(new THREE.BoxGeometry(p.propulsion.prop_diameter_m,.001,.006),i%2?'#bbf0a7':'#e8bc72',{...at,y:.02});rotors.push(prop);
  }
}
function renderState(s){
  drone.position.set(s.position.x,s.position.y,s.position.z);drone.quaternion.set(s.rotation.x,s.rotation.y,s.rotation.z,s.rotation.w);
  for(let i=0;i<4;i++)rotors[i].rotation.y=s.time_s*s.rpm[i]*Math.PI/30*(i%2?-1:1);
  cameras.detail.position.copy(drone.position).add(new THREE.Vector3(.2,.14,.25));cameras.detail.lookAt(drone.position);
  const frame=sim.deliveredCamera||s;
  const ahead=rotate(frame.rotation,{x:0,y:0,z:1}),up=rotate(frame.rotation,{x:0,y:1,z:0});
  cameras.camera.position.set(frame.position.x,frame.position.y,frame.position.z).addScaledVector(new THREE.Vector3(ahead.x,ahead.y,ahead.z),.06);
  cameras.camera.up.set(up.x,up.y,up.z);cameras.camera.lookAt(cameras.camera.position.clone().add(new THREE.Vector3(ahead.x,ahead.y,ahead.z)));
  $('height').textContent=s.position.y.toFixed(2)+' m';$('voltage').textContent=s.voltage_v.toFixed(2)+' V';$('current').textContent=s.current_a.toFixed(2)+' A';$('time').textContent=s.time_s.toFixed(1)+' s';
  renderers.world.render(scene,cameras.world);renderers.detail.render(scene,cameras.detail);
  if((sim.deliveredCamera&&frame.capture_time_s!==lastCamera)||s.time_s===0){drone.visible=false;renderers.camera.render(scene,cameras.camera);drone.visible=true;lastCamera=frame.capture_time_s??0;}
}
function controls(disabled){for(const id of ['run','configuration','scenario','save-variant','save-component'])$(id).disabled=disabled;$('run').disabled=disabled||dirty;for(const s of $('slots').querySelectorAll('select'))s.disabled=disabled;$('stop').disabled=!disabled;}
function showResult(r){$('result').replaceChildren();const p=document.createElement('p');p.className=r.engineering_passed?'pass':'fail';p.textContent=`Flight ${r.flight_passed?'PASS':'FAIL'} · engineering ${r.engineering_passed?'PASS':'FAIL'} · ${r.static_reserve.thrust_weight.toFixed(2)}× thrust reserve`;const detail=document.createElement('p');detail.textContent=Object.entries(r.gates).map(([k,v])=>`${k.replaceAll('_',' ')}: ${v?'pass':'fail'}`).join(' · ');$('result').append(p,detail);}
async function finish(){running=false;controls(false);const result=sim.result();result.trial_sha256=trial.sha256;showResult(result);$('state').textContent='Test complete';await post('record',{id:trial.id,result});const r=await fetch('/api/components');library=await r.json();renderHistory();}
function loop(now){
  const elapsed=last?Math.min((now-last)/1000,.1):0;last=now;
  if(running){accumulator+=elapsed;try{while(accumulator>=sim.dt&&sim.t<20-sim.dt/2){sim.step();accumulator-=sim.dt;}renderState(sim.state());if(sim.t>=20-sim.dt/2)finish().catch(failure);}catch(e){running=false;controls(false);failure(e);}}
  requestAnimationFrame(loop);
}
$('configuration').onchange=select;$('scenario').onchange=select;$('component').onchange=()=>populateComponent($('component').value);
$('save-variant').onclick=async()=>{try{const c=structuredClone(assembly.configuration.content);c.id=$('variant-id').value;c.name=c.id;c.components=Object.fromEntries([...$('slots').querySelectorAll('select')].map(s=>[s.dataset.slot,s.value]));const saved=await post('save',{kind:'configuration',content:c,expected_revision:0});await load(saved.content.id);$('saved').textContent='Saved variant; component revisions pinned.';}catch(e){failure(e);}};
$('save-component').onclick=async()=>{try{const current=library.components.find(c=>c.content.id===$('component').value);const content=JSON.parse($('component-json').value);const saved=await post('save',{kind:'component',content,expected_revision:content.id===current.content.id?current.revision:0});await load($('configuration').value);$('component').value=saved.content.id;populateComponent(saved.content.id);$('component-saved').textContent=`Saved r${saved.revision}. Select it in an assembly and save a variant to use it.`;}catch(e){failure(e);}};
$('run').onclick=async()=>{controls(true);$('error').textContent='';try{const c=assembly.configuration;trial=await post('freeze',{reference:c.content.id+'@'+c.revision,scenario:$('scenario').value});if(sim)sim.dispose();sim=new MicroFlight(trial.snapshot.assembly,trial.snapshot.scenario);buildDrone();lastCamera=-1;accumulator=0;running=true;$('state').textContent='Flying · fixed 250 Hz physics';}catch(e){controls(false);failure(e);}};
$('stop').onclick=()=>{running=false;controls(false);$('state').textContent='Stopped · incomplete trial';};
new ResizeObserver(()=>{const width=$('world').clientWidth,height=$('world').clientHeight;renderers.world.setSize(width,height,false);cameras.world.aspect=width/height;cameras.world.updateProjectionMatrix();if(sim)renderState(sim.state());}).observe($('world'));
await initialize();await load();await loadValidation();$('state').textContent='Ready';requestAnimationFrame(loop);
// Read-only hook for verifying that the rendered pose is the physics pose.
window.componentLab={state:()=>sim?.state(),rendered:()=>({position:drone.position.toArray(),quaternion:drone.quaternion.toArray()}),get running(){return running;}};
