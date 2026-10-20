import * as THREE from './vendor/three.module.js';
const $ = id => document.getElementById(id);
const client = crypto.randomUUID();
let snapshot, recording, recordingEpisode, pendingUploads = Promise.resolve(), uploadCount = 0, sequence = 0, recordingError = false, stopping = false, renderReady = false;
const active = s => ['exploring','observing','returning'].includes(s);
function error(e){ $('error').textContent = e.message || String(e); $('error').hidden = false; }
async function post(path, body={}, binary=false){
 const response = await fetch(path, {method:'POST', headers:{'X-Drone137-Control':'local',...(binary?{}:{'Content-Type':'application/json'})}, body:binary?body:JSON.stringify(body)});
 if(!response.ok){let message=await response.text();try{message=JSON.parse(message).error||message;}catch{}throw new Error(message);}
 return response.json();
}
function query(values){return new URLSearchParams(values).toString();}
const scene = new THREE.Scene(); scene.background = new THREE.Color('#162126');
scene.add(new THREE.HemisphereLight(0xe5f7ff, 0x77725c, 2.5));
const sun = new THREE.DirectionalLight(0xfff1db, 3);sun.position.set(5,9,4);scene.add(sun);
const overhead = new THREE.PerspectiveCamera(48,1,.1,100);overhead.position.set(14,15,16);overhead.lookAt(6,0,5);
const onboard = new THREE.PerspectiveCamera(75,4/3,.05,30);
let view, cameraView, renderedFrame;
try{
 view = new THREE.WebGLRenderer({canvas:$('world'),antialias:true}); view.setPixelRatio(1);
 cameraView = new THREE.WebGLRenderer({canvas:$('camera'),antialias:true,preserveDrawingBuffer:true}); cameraView.setSize(320,240,false);
 renderReady = true;
}catch(e){error(new Error('WebGL is unavailable. Enable browser graphics acceleration to run the virtual camera. '+e.message));}
let roomGroup = new THREE.Group();scene.add(roomGroup);
const drone = new THREE.Group();
const hull = new THREE.Mesh(new THREE.BoxGeometry(.32,.12,.22),new THREE.MeshStandardMaterial({color:0xb4e99d}));drone.add(hull);
for(const x of [-.22,.22])for(const z of [-.22,.22]){const ring=new THREE.Mesh(new THREE.TorusGeometry(.13,.025,8,20),new THREE.MeshStandardMaterial({color:0xc9d6d2}));ring.rotation.x=Math.PI/2;ring.position.set(x,0,z);drone.add(ring);}scene.add(drone);
let sceneKey;
function buildRoom(world){
 const key=JSON.stringify(world);if(key===sceneKey)return;sceneKey=key;
 roomGroup.traverse(o=>{o.geometry?.dispose();if(o.material)o.material.dispose();});scene.remove(roomGroup);roomGroup=new THREE.Group();scene.add(roomGroup);
 function box(x,y,z,sx,sy,sz,color){const mesh=new THREE.Mesh(new THREE.BoxGeometry(sx,sy,sz),new THREE.MeshStandardMaterial({color}));mesh.position.set(x,y,z);roomGroup.add(mesh);}
 box(6,-.08,5,12,.16,10,0x677675);
 // Low translucent-looking perimeter in overhead, full-height walls in camera.
 const wallMaterial=new THREE.MeshStandardMaterial({color:0xa7b5ac,side:THREE.DoubleSide});
 for(const [x,z,sx,sz] of [[6,0,12,.12],[6,10,12,.12],[0,5,.12,10],[12,5,.12,10]]){const wall=new THREE.Mesh(new THREE.BoxGeometry(sx,3,sz),wallMaterial.clone());wall.position.set(x,1.5,z);wall.userData.wall=true;roomGroup.add(wall);}wallMaterial.dispose();
 world.obstacles.forEach((b,i)=>box(b.x,b.height/2,b.y,b.sx,b.height,b.sy,[0xb89767,0x748e9e,0xb07864,0x7d967c][i%4]));
 const grid = new THREE.GridHelper(12,24,0x93a29b,0x778985);grid.position.set(6,.015,5);grid.scale.z=10/12;roomGroup.add(grid);
 const home = new THREE.Mesh(new THREE.RingGeometry(.25,.36,32),new THREE.MeshBasicMaterial({color:0xb4e99d,side:THREE.DoubleSide}));home.rotation.x=-Math.PI/2;home.position.set(1.25,.025,1.25);roomGroup.add(home);
}
let lastRenderTime = 0;
function render(now=0){
 requestAnimationFrame(render);if(!renderReady||!snapshot||now-lastRenderTime<50)return;lastRenderTime=now;
 const [x,y,z,yaw]=snapshot.pose;drone.position.set(x,z,y);drone.rotation.y=-yaw;
 onboard.position.set(x,z,y);onboard.lookAt(x+Math.cos(yaw),z-.08,y+Math.sin(yaw));
 const w=$('world').clientWidth,h=$('world').clientHeight; if(view.domElement.width!==Math.round(w*view.getPixelRatio())||view.domElement.height!==Math.round(h*view.getPixelRatio())){view.setSize(w,h,false);overhead.aspect=w/h;overhead.updateProjectionMatrix();}
 roomGroup.children.filter(o=>o.userData.wall).forEach(o=>{o.visible=false;});view.render(scene,overhead);
 roomGroup.children.filter(o=>o.userData.wall).forEach(o=>{o.visible=true;});drone.visible=false;cameraView.render(scene,onboard);drone.visible=true;renderedFrame={episode:snapshot.episode,ticket:snapshot.ticket};
}
render();
function map(s){const c=$('map').getContext('2d');s.grid.forEach((v,i)=>{c.fillStyle=['#344044','#b6c3ba','#c99a64'][v];c.fillRect(i%24*20,Math.floor(i/24)*20,19,19);});c.fillStyle='#f6f8f7';c.beginPath();c.arc(s.pose[0]*40,s.pose[1]*40,5,0,2*Math.PI);c.fill();}
function evidence(s){
 $('observations').replaceChildren(...s.observations.map(o=>{const li=document.createElement('li');const link=document.createElement('a');link.href=`/reports/${s.episode}/${o.image}`;link.target='_blank';link.textContent=o.action;li.append(link,document.createTextNode(' — '+o.observation));return li;}));
 $('evidence').replaceChildren();if(s.report){const link=document.createElement('a');link.href=s.report;link.target='_blank';link.textContent='Mission report';$('evidence').append(link);if(s.video_chunks){const v=document.createElement('a');v.href=`/reports/${s.episode}/onboard.${s.video_type==='video/mp4'?'mp4':'webm'}`;v.textContent=s.video_complete?' · Download video':' · Video still finalizing';v.download='';$('evidence').append(v);}}
}
function update(s){
 snapshot=s;buildRoom(s.scene);map(s);$('state').textContent=s.state.toUpperCase();$('reason').textContent=s.reason;
 $('coverage').textContent=Math.round(s.observed_fraction*100)+'%';$('distance').textContent=s.distance_m.toFixed(1)+' m';$('speed').textContent=s.speed.toFixed(1)+' m/s';
 const running=active(s.state)||s.state==='paused',m=s.model;
 $('start').disabled=running||stopping||!renderReady||($('policy').value==='qwen'&&(!m.ready||m.busy));
 $('generate').disabled=running||stopping;$('policy').disabled=running;$('pause').disabled=!active(s.state);$('land').disabled=!running;$('freeze').disabled=!active(s.state);
 $('model-state').textContent=m.state.toUpperCase();$('model-detail').textContent=m.error||`${m.busy?m.job+' · ':''}${m.store.stage}${m.store.file?' · '+m.store.file:''}`;
 $('download-progress').value=m.store.total?m.store.downloaded/m.store.total:0;
 $('host').textContent=`Host: ${m.host.os} / ${m.host.architecture}. Runtime ${m.runtime_installed?'installed':'missing'}. CMake ${m.host.cmake?'found':'missing'}, compiler ${m.host.compiler?'found':'missing'}. Mac acceptance: ${m.acceptance}.`;
 if(m.vision_check)$('vision-check').textContent=`Real-model paired-image check: ${m.vision_check.passed?'passed':'failed'}. This does not establish flight or memory acceptance.`;
 document.querySelectorAll('[data-model]').forEach(b=>{b.disabled=running||(m.busy&&b.dataset.model!=='cancel');});evidence(s);
 if(recording && !active(s.state) && s.state!=='paused')stopRecording();
 if(recording && s.state==='paused')stopRecording();
}
let polling=false, generation=0;
async function poll(){if(polling)return;polling=true;const requestedGeneration=generation;try{const r=await fetch('/api/status',{cache:'no-store'});if(!r.ok)throw new Error('Controller unavailable');const result=await r.json();if(requestedGeneration===generation)update(result);}catch(e){error(e);$('start').disabled=true;}finally{polling=false;}}
setInterval(poll,250);poll();$('policy').onchange=()=>snapshot&&update(snapshot);
$('generate').onclick=()=>post('/api/room',{seed:Number($('seed').value)}).then(update).catch(error);
for(const [id,path] of [['pause','pause'],['land','land'],['freeze','freeze-sensors']])$(id).onclick=()=>post('/api/'+path).then(update).catch(error);
document.querySelectorAll('[data-model]').forEach(b=>b.onclick=()=>post('/api/model/'+b.dataset.model).then(poll).catch(error));
let recordingMime='video/webm';
function recordingSupport(){
 if(!window.MediaRecorder||!$('camera').captureStream)throw new Error('This browser cannot record canvas video. Use a current Chrome or Safari with MediaRecorder support.');
 const mime=['video/webm;codecs=vp8','video/webm','video/mp4'].find(t=>MediaRecorder.isTypeSupported(t));if(!mime)throw new Error('No supported browser video encoder.');return mime;
}
function startRecording(mime){
 const stream=$('camera').captureStream(10);recording=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:400000});
 recordingMime=mime.split(';')[0];recordingEpisode=snapshot.episode;sequence=0;recordingError=false;pendingUploads=Promise.resolve();uploadCount=0;
 const episode=recordingEpisode;
 recording.ondataavailable=event=>{
  if(!event.data.size||recordingError)return;
  if(uploadCount>=3||event.data.size>1024*1024){recordingError=true;error(new Error('Video recording cannot keep up; ending mission.'));post('/api/land').catch(error);return;}
  uploadCount++;const seq=sequence++;
  pendingUploads=pendingUploads.then(async()=>{if(recordingError)return;await post('/api/video?'+query({episode,client,sequence:seq,mime:recordingMime}),event.data,true);}).catch(e=>{recordingError=true;error(e);post('/api/land').catch(error);}).finally(()=>{uploadCount--;});
 };
 recording.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());await pendingUploads;if(!recordingError)await post('/api/video-finalize',{episode,client}).catch(error);$('recording').textContent=recordingError?'RECORDING FAILED':'VIDEO SAVED';stopping=false;await poll();};
 recording.onerror=e=>{recordingError=true;error(new Error('Browser video encoder failed'));post('/api/land').catch(error);};
 recording.start(1000);$('recording').textContent='● RECORDING';
}
function stopRecording(){if(recording){stopping=true;$('start').disabled=true;$('generate').disabled=true;const r=recording;recording=null;if(r.state!=='inactive')r.stop();}}
$('start').onclick=async()=>{try{$('error').hidden=true;$('start').disabled=true;generation++;const mime=recordingSupport();const result=await post('/api/start',{policy:$('policy').value,client});generation++;update(result);startRecording(mime);}catch(e){error(e);if(snapshot&&active(snapshot.state))await post('/api/land').catch(error);}};
let sending=false;
setInterval(async()=>{
 if(sending||!snapshot||!active(snapshot.state)||!recording||!renderReady)return;
 sending=true;const {episode,ticket}=renderedFrame||snapshot;
 try{const jpeg=await new Promise(resolve=>$('camera').toBlob(resolve,'image/jpeg',.8));if(!jpeg)throw new Error('Camera encoding failed');await post('/api/camera?'+query({episode,client,ticket:ticket||''}),jpeg,true);}catch(e){if(snapshot&&active(snapshot.state))error(e);}finally{sending=false;}
},500);
