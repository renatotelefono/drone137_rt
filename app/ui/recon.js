import * as THREE from './vendor/three.module.js';
import {workshopAssets} from './scene-detail.js';
import {realismAssets} from './scene-realism.js';
import {cameraEffects} from './camera-effects.js';
const $ = id => document.getElementById(id);
const client = crypto.randomUUID();
const parameters = new URLSearchParams(location.search);
const fleetDrone = location.pathname === '/camera-worker' ? parameters.get('drone') : null;
const fleetSession = parameters.get('session');
if(fleetDrone){
 document.body.classList.add('camera-worker');
 const preview=document.createElement('section');preview.className='worker-preview';
 const last=document.createElement('img');last.id='last-observation';last.hidden=true;last.alt='Last recorded camera observation';
 preview.append($('camera'),last,$('recording'),$('error'));document.body.append(preview);
}
function endpoint(path){return fleetDrone && /^\/api\/(status|camera|video|video-finalize|land)(\?|$)/.test(path)?path.replace('/api/',`/api/fleet/drones/${encodeURIComponent(fleetDrone)}/`):path;}
let snapshot, recording, recordingEpisode, pendingUploads = Promise.resolve(), uploadCount = 0, sequence = 0, recordingError = false, stopping = false, renderReady = false, assetsReady = false;
const active = s => ['exploring','observing','returning'].includes(s);
function error(e){ $('error').textContent = e.message || String(e); $('error').hidden = false; }
async function post(path, body={}, binary=false){
 if(fleetDrone&&path==='/api/land')body={episode:snapshot?.episode,client};
 const response = await fetch(endpoint(path), {method:'POST', headers:{'X-Drone137-Control':'local',...(binary?{}:{'Content-Type':'application/json'})}, body:binary?body:JSON.stringify(body)});
 if(!response.ok){let message=await response.text();try{message=JSON.parse(message).error||message;}catch{}throw new Error(message);}
 return response.json();
}
function query(values){return new URLSearchParams(values).toString();}
const scene = new THREE.Scene(); scene.background = new THREE.Color('#162126');
const ambient=new THREE.HemisphereLight(0xe5f7ff, 0x77725c, 2.5);scene.add(ambient);
const sun = new THREE.DirectionalLight(0xfff1db, 3);sun.position.set(5,9,4);scene.add(sun);
sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);sun.shadow.camera.left=-10;sun.shadow.camera.right=10;sun.shadow.camera.top=10;sun.shadow.camera.bottom=-10;sun.shadow.normalBias=.03;sun.target.position.set(6,0,5);scene.add(sun.target);
const overhead = new THREE.PerspectiveCamera(48,1,.1,100);overhead.position.set(14,15,16);overhead.lookAt(6,0,5);
const onboard = new THREE.PerspectiveCamera(75,4/3,.05,30);
overhead.layers.enable(1);
let view, cameraView, effects, renderedFrame, cameraProfile;
const snapshotCanvas=document.createElement('canvas');
const snapshotContext=snapshotCanvas.getContext('2d');
try{
 if(!fleetDrone){view = new THREE.WebGLRenderer({canvas:$('world'),antialias:true}); view.setPixelRatio(1);}
 cameraView = new THREE.WebGLRenderer({canvas:$('camera'),antialias:true,preserveDrawingBuffer:true}); cameraView.setSize(320,240,false);
 effects=cameraEffects(cameraView);renderReady = true;
}catch(e){error(new Error('WebGL is unavailable. Enable browser graphics acceleration to run the virtual camera. '+e.message));}
let roomGroup = new THREE.Group();scene.add(roomGroup);
const drone = new THREE.Group();
const hull = new THREE.Mesh(new THREE.BoxGeometry(.32,.12,.22),new THREE.MeshStandardMaterial({color:0xb4e99d}));drone.add(hull);
for(const x of [-.22,.22])for(const z of [-.22,.22]){const ring=new THREE.Mesh(new THREE.TorusGeometry(.13,.025,8,20),new THREE.MeshStandardMaterial({color:0xc9d6d2}));ring.rotation.x=Math.PI/2;ring.position.set(x,0,z);drone.add(ring);}scene.add(drone);
let sceneKey;
function disposeRoom(group){
 const materials=new Set(),geometries=new Set(),textures=new Set();
 group.traverse(o=>{if(o.geometry)geometries.add(o.geometry);if(o.material)for(const m of Array.isArray(o.material)?o.material:[o.material])materials.add(m);});
 for(const m of materials){for(const value of Object.values(m))if(value?.isTexture)textures.add(value);m.dispose();}
 for(const t of textures)t.dispose();for(const g of geometries)g.dispose();
}
function buildRoom(world){
 if(!renderReady)return;
 const key=JSON.stringify(world);if(key===sceneKey)return;sceneKey=key;
 assetsReady=false;$('camera').dataset.ready='false';disposeRoom(roomGroup);scene.remove(roomGroup);roomGroup=new THREE.Group();scene.add(roomGroup);
 cameraProfile=world.camera||{width:320,height:240,snapshot_width:320,snapshot_height:240,vertical_fov:75,fps:10,bitrate:400000};
 onboard.fov=cameraProfile.vertical_fov;onboard.aspect=cameraProfile.width/cameraProfile.height;onboard.updateProjectionMatrix();
 cameraView.setSize(cameraProfile.width,cameraProfile.height,false);$('camera').style.aspectRatio=`${cameraProfile.width}/${cameraProfile.height}`;
 snapshotCanvas.width=cameraProfile.snapshot_width;snapshotCanvas.height=cameraProfile.snapshot_height;
 const detailed=['workshop','realism'].includes(world.scenario);cameraView.shadowMap.enabled=detailed;cameraView.shadowMap.type=THREE.PCFSoftShadowMap;
 sun.target.position.set(detailed?6:0,0,detailed?5:0);sun.target.updateMatrixWorld();
 $('camera-detail').textContent=`${cameraProfile.width} × ${cameraProfile.height} video · ${cameraProfile.snapshot_width} × ${cameraProfile.snapshot_height} model images · ${world.scenario==='realism'?`${world.condition} · synthetic optics (uncalibrated)`:detailed?'approximate Camera Module 3 view':'wide virtual view'}`;
 function box(x,y,z,sx,sy,sz,color){const mesh=new THREE.Mesh(new THREE.BoxGeometry(sx,sy,sz),new THREE.MeshStandardMaterial({color}));mesh.position.set(x,y,z);mesh.receiveShadow=detailed;roomGroup.add(mesh);}
 box(6,-.08,5,12,.16,10,0x677675);
 // Low translucent-looking perimeter in overhead, full-height walls in camera.
 const wallMaterial=new THREE.MeshStandardMaterial({color:0xa7b5ac,side:THREE.DoubleSide});
 for(const [x,z,sx,sz] of [[6,0,12,.12],[6,10,12,.12],[0,5,.12,10],[12,5,.12,10]]){const wall=new THREE.Mesh(new THREE.BoxGeometry(sx,3,sz),wallMaterial.clone());wall.position.set(x,1.5,z);wall.userData.wall=true;roomGroup.add(wall);}wallMaterial.dispose();
 sun.intensity = (world.scenario==='realism'?2.4:3)*(world.lighting || 1);ambient.intensity=world.scenario==='realism'?1.4:2.5;
 effects.configure(cameraProfile,world.seed);
 if(world.scenario==='realism'){
  const group=roomGroup;
  realismAssets(group,world).then(()=>{if(group!==roomGroup){disposeRoom(group);return;}assetsReady=true;}).catch(e=>{disposeRoom(group);if(group===roomGroup)error(new Error('Scene assets failed to load: '+e.message));});
 }else if(detailed)workshopAssets(roomGroup,world);
 else world.obstacles.forEach((b,i)=>{
  const color = b.kind === 'wall' ? 0xa7b5ac : [0xb89767,0x748e9e,0xb07864,0x7d967c][i%4];
  box(b.x,b.height/2,b.y,b.sx,b.height,b.sy,color);
  if(b.kind === 'shelf'){
   for(const h of [.15,.85,1.55]){box(b.x,h,b.y,b.sx+.04,.07,b.sy+.04,0x35494d);}
   for(const dx of [-b.sx/2,b.sx/2]){box(b.x+dx,b.height/2,b.y,.07,b.height,b.sy+.04,0x35494d);}
  }else if(b.kind === 'crate'){
   for(const dx of [-b.sx*.3,b.sx*.3])box(b.x+dx,b.height/2,b.y,.08,b.height+.02,b.sy+.02,0x584633);
   box(b.x,b.height*.5,b.y,b.sx+.02,.09,b.sy+.03,0x584633);
  }
 });
 (world.checkpoints||[]).forEach(p=>{
  const marker = new THREE.Mesh(new THREE.RingGeometry(.16,.22,24),new THREE.MeshBasicMaterial({color:0x7fc8e5,side:THREE.DoubleSide}));
  if(detailed)marker.layers.set(1);marker.rotation.x=-Math.PI/2;marker.position.set(p.position[0],.028,p.position[1]);roomGroup.add(marker);
 });
 const grid = new THREE.GridHelper(12,24,0x93a29b,0x778985);if(detailed)grid.layers.set(1);grid.position.set(6,.015,5);grid.scale.z=10/12;roomGroup.add(grid);
 if(world.scenario!=='realism')assetsReady=true;
 const home = new THREE.Mesh(new THREE.RingGeometry(.25,.36,32),new THREE.MeshBasicMaterial({color:0xb4e99d,side:THREE.DoubleSide}));if(detailed)home.layers.set(1);home.rotation.x=-Math.PI/2;home.position.set(1.25,.025,1.25);roomGroup.add(home);
}
let recordingStarted = 0;
let lastRenderTime = 0;
function render(now=0){
 requestAnimationFrame(render);if(!renderReady||!assetsReady||!snapshot||now-lastRenderTime<50)return;lastRenderTime=now;
 const [x,y,z,yaw]=snapshot.pose;drone.position.set(x,z,y);drone.rotation.y=-yaw;
 const pitch=cameraProfile.pitch_degrees===undefined?-.08:Math.tan(cameraProfile.pitch_degrees*Math.PI/180);
 onboard.position.set(x,z,y);onboard.lookAt(x+Math.cos(yaw),z+pitch,y+Math.sin(yaw));
 if(view){const w=$('world').clientWidth,h=$('world').clientHeight; if(view.domElement.width!==Math.round(w*view.getPixelRatio())||view.domElement.height!==Math.round(h*view.getPixelRatio())){view.setSize(w,h,false);overhead.aspect=w/h;overhead.updateProjectionMatrix();}
 roomGroup.children.filter(o=>o.userData.wall).forEach(o=>{o.visible=false;});view.render(scene,overhead);}
 roomGroup.children.filter(o=>o.userData.wall).forEach(o=>{o.visible=true;});drone.visible=false;if(cameraProfile.effects)effects.render(scene,onboard);else cameraView.render(scene,onboard);drone.visible=true;
 $('camera').dataset.ready='true';$('camera').dataset.sceneKey=sceneKey;$('camera').dataset.pose=JSON.stringify(snapshot.pose);renderedFrame={episode:snapshot.episode,ticket:snapshot.ticket};
}
render();
function map(s){const c=$('map').getContext('2d');s.grid.forEach((v,i)=>{c.fillStyle=['#344044','#b6c3ba','#c99a64'][v];c.fillRect(i%24*20,Math.floor(i/24)*20,19,19);});c.fillStyle='#f6f8f7';c.beginPath();c.arc(s.pose[0]*40,s.pose[1]*40,5,0,2*Math.PI);c.fill();}
function evidence(s){
 $('observations').replaceChildren(...s.observations.map(o=>{const li=document.createElement('li');const link=document.createElement('a');link.href=`/reports/${s.episode}/${o.image}`;link.target='_blank';link.textContent=o.action;const change=o.change?.status==='new_obstruction'?'New obstruction · ':'';li.append(link,document.createTextNode(' — '+change+(o.survey?.summary||o.observation)));return li;}));
 $('evidence').replaceChildren();if(s.report){const link=document.createElement('a');link.href=s.report_page||s.report;link.target='_blank';link.textContent='Mission report';$('evidence').append(link);if(s.video_chunks){const v=document.createElement('a');v.href=`/reports/${s.episode}/onboard.${s.video_type==='video/mp4'?'mp4':'webm'}`;v.textContent=s.video_complete?' · Download video':' · Video still finalizing';v.download='';$('evidence').append(v);}}
}
let formScene;
function update(s){
 const selection=JSON.stringify([s.scene.scenario,s.scene.variant,s.scene.seed,s.scene.condition]);
 if(selection!==formScene){
  formScene=selection;$('scenario').value=s.scene.scenario;$('variant').value=s.scene.variant;$('seed').value=s.scene.seed;$('condition').value=s.scene.condition||'nominal';
  $('mission').value=s.episode?s.mission:(s.scene.checkpoints?.length?'patrol':'explore');
 }
 snapshot=s;buildRoom(s.scene);map(s);$('state').textContent=s.state.toUpperCase();$('reason').textContent=s.reason;
 if(fleetDrone){
  const last=s.observations.at(-1),show=!!last&&s.video_complete&&!active(s.state);
  $('last-observation').hidden=!show;$('camera').hidden=show;
  if(show){$('last-observation').src=`/reports/${s.episode}/${last.image}`;$('recording').textContent='LAST OBSERVATION · VIDEO SAVED';}
 }
 $('coverage').textContent=Math.round(s.observed_fraction*100)+'%';$('distance').textContent=s.distance_m.toFixed(1)+' m';$('speed').textContent=s.speed.toFixed(1)+' m/s';
 const running=active(s.state)||s.state==='paused',m=s.model;
 $('start').disabled=running||stopping||!renderReady||!assetsReady||($('policy').value==='qwen'&&(!m.ready||m.busy));
 $('generate').disabled=running||stopping;for(const id of ['scenario','variant','mission','seed'])$(id).disabled=running||stopping;$('condition').disabled=running||stopping||$('scenario').value!=='realism';$('policy').disabled=running;$('pause').disabled=!active(s.state);$('land').disabled=!running;$('freeze').disabled=!active(s.state);
 $('model-state').textContent=m.state.toUpperCase();$('model-detail').textContent=m.error||`${m.busy?m.job+' · ':''}${m.store.stage}${m.store.file?' · '+m.store.file:''}`;
 $('download-progress').value=m.store.total?m.store.downloaded/m.store.total:0;
 $('host').textContent=`Host: ${m.host.os} / ${m.host.architecture}. Runtime ${m.runtime_installed?'installed':'missing'}. CMake ${m.host.cmake?'found':'missing'}, compiler ${m.host.compiler?'found':'missing'}. Mac acceptance: ${m.acceptance}.`;
 $('baseline').textContent=s.baseline_episode?'Comparing with the previous completed local-vision patrol.':'A completed local-vision patrol becomes the baseline for the next matching patrol.';
 $('vision-check').textContent=m.vision_check?`Vision check ${m.vision_check.passed?'passed':'failed'} · Review observations against the images. Flight readiness remains unverified.`:'Vision check has not run this session. Review model observations against the images.';
 document.querySelectorAll('[data-model]').forEach(b=>{b.disabled=running||(m.busy&&b.dataset.model!=='cancel');});evidence(s);
 if(recording && !active(s.state) && s.state!=='paused')stopRecording();
 if(recording && s.state==='paused')stopRecording();
}
let polling=false, generation=0;
$('camera-fullscreen').onclick=()=> $('camera').requestFullscreen?.().catch(error);
async function poll(){if(polling)return;polling=true;const requestedGeneration=generation;try{const r=await fetch(endpoint('/api/status'),{cache:'no-store'});if(!r.ok)throw new Error('Controller unavailable');const result=await r.json();if(requestedGeneration===generation){update(result);if(fleetDrone&&result.client===client&&active(result.state)&&!recording&&!stopping&&assetsReady){startRecording(recordingSupport());}}}catch(e){error(e);$('start').disabled=true;if(fleetDrone&&snapshot?.client===client&&active(snapshot?.state))post('/api/land').catch(error);}finally{polling=false;}}
setInterval(poll,250);poll();$('policy').onchange=()=>snapshot&&update(snapshot);
$('generate').onclick=()=>post('/api/room',{seed:Number($('seed').value),scenario:$('scenario').value,variant:$('variant').value,condition:$('scenario').value==='realism'?$('condition').value:'nominal'}).then(update).catch(error);
$('scenario').onchange=()=>{ $('mission').value=$('scenario').value==='room'?'explore':'patrol';$('condition').value='nominal';$('condition').disabled=$('scenario').value!=='realism'; };
async function history(){
 try{
 const response=await fetch('/api/runs',{cache:'no-store'});if(!response.ok)throw new Error('Could not load saved missions');
 const runs=await response.json();$('history').replaceChildren(...runs.map(run=>{
  const row=document.createElement('div');row.className='history-row';
  const link=document.createElement('a');link.href=run.report_page;link.target='_blank';link.textContent=`${run.scenario||'room'} · ${run.variant||'baseline'} · seed ${run.seed}${run.scenario==='realism'?' · '+(run.condition||'nominal'):''}`;
  const detail=document.createElement('span');detail.textContent=`${run.state} · ${run.policy} · ${(run.distance_m||0).toFixed(1)} m · ${run.video?.complete?'video saved':'incomplete video'}`;
  row.append(link,detail);return row;
 }));if(!runs.length)$('history').textContent='Your completed missions will appear here.';
 }catch(e){error(e);}
}
$('refresh-history').onclick=history;if(!fleetDrone)history();
for(const [id,path] of [['pause','pause'],['land','land'],['freeze','freeze-sensors']])$(id).onclick=()=>post('/api/'+path).then(update).catch(error);
document.querySelectorAll('[data-model]').forEach(b=>b.onclick=()=>post('/api/model/'+b.dataset.model).then(poll).catch(error));
let recordingMime='video/webm';
function recordingSupport(){
 if(!window.MediaRecorder||!$('camera').captureStream)throw new Error('This browser cannot record canvas video. Use a current Chrome or Safari with MediaRecorder support.');
 const mime=['video/webm;codecs=vp8','video/webm','video/mp4'].find(t=>MediaRecorder.isTypeSupported(t));if(!mime)throw new Error('No supported browser video encoder.');return mime;
}
function startRecording(mime){
 const stream=$('camera').captureStream(cameraProfile.fps);recording=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:cameraProfile.bitrate});
 recordingMime=mime.split(';')[0];recordingEpisode=snapshot.episode;sequence=0;recordingError=false;pendingUploads=Promise.resolve();uploadCount=0;
 const episode=recordingEpisode;
 recording.ondataavailable=event=>{
  if(!event.data.size||recordingError)return;
  if(uploadCount>=3||event.data.size>1024*1024){recordingError=true;error(new Error('Video recording cannot keep up; ending mission.'));post('/api/land').catch(error);return;}
  uploadCount++;const seq=sequence++;
  pendingUploads=pendingUploads.then(async()=>{if(recordingError)return;await post('/api/video?'+query({episode,client,sequence:seq,mime:recordingMime}),event.data,true);}).catch(e=>{recordingError=true;error(e);post('/api/land').catch(error);}).finally(()=>{uploadCount--;});
 };
 recording.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());await pendingUploads;if(!recordingError)await post('/api/video-finalize',{episode,client}).catch(e=>{recordingError=true;error(e);});$('recording').textContent=recordingError?'RECORDING FAILED':'VIDEO SAVED';stopping=false;await poll();if(!fleetDrone)await history();};
 recording.onerror=e=>{recordingError=true;error(new Error('Browser video encoder failed'));post('/api/land').catch(error);};
 recordingStarted=performance.now();recording.start(1000);$('recording').textContent='● RECORDING';
}
function stopRecording(){if(recording){stopping=true;$('start').disabled=true;$('generate').disabled=true;const r=recording;recording=null;if(r.state!=='inactive')r.stop();}}
$('start').onclick=async()=>{try{$('error').hidden=true;$('start').disabled=true;generation++;const mime=recordingSupport();const result=await post('/api/start',{policy:$('policy').value,client,mission:$('mission').value});generation++;update(result);startRecording(mime);}catch(e){error(e);if(snapshot&&active(snapshot.state))await post('/api/land').catch(error);}};
let sending=false;
setInterval(async()=>{
 if(sending||!snapshot||!active(snapshot.state)||!recording||!renderReady||!assetsReady)return;
 sending=true;const {episode,ticket}=renderedFrame||snapshot;
 try{const video_time_s=(performance.now()-recordingStarted)/1000;snapshotContext.drawImage($('camera'),0,0,snapshotCanvas.width,snapshotCanvas.height);const jpeg=await new Promise(resolve=>snapshotCanvas.toBlob(resolve,'image/jpeg',cameraProfile.jpeg_quality??(cameraProfile.id==='lean'?.8:.85)));if(!jpeg)throw new Error('Camera encoding failed');await post('/api/camera?'+query({episode,client,ticket:ticket||'',video_time_s}),jpeg,true);}catch(e){if(snapshot&&active(snapshot.state))error(e);}finally{sending=false;}
},500);
let readySending=false;
if(fleetDrone)setInterval(async()=>{
 if(readySending||!snapshot)return;readySending=true;
 try{
  const ready=renderReady&&assetsReady&&!stopping&&$('camera').dataset.ready==='true'&&$('camera').dataset.sceneKey===sceneKey;
  if(ready)recordingSupport();
  await post(`/api/fleet/drones/${encodeURIComponent(fleetDrone)}/ready`,{client,session:fleetSession,generation:snapshot.generation,ready});
 }catch(e){error(e);}finally{readySending=false;}
},500);
