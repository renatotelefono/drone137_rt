import * as THREE from './vendor/three.module.js';
import {stressAssets} from './scene-stress.js';
import {cameraEffects} from './camera-effects.js';
import {importedLighting} from './scene-imported.js';
import {GLTFLoader} from './vendor/addons/loaders/GLTFLoader.js';
import {visibleCollisionMesh} from './visible-colliders.mjs';
const $=id=>document.getElementById(id),canvas=$('camera');
const world=await(await fetch('/scene.json')).json();
if(world.navigation_mode==='observed-range')$('limitations').textContent='GPS disabled · observed range map · synthetic noisy odometry. Map below is evaluator truth and is not supplied to the planner. Physical hardware remains unqualified.';
if(world.real_assets)$('asset-credit').hidden=false;
const scene=new THREE.Scene();scene.background=new THREE.Color('#28363e');
const group=new THREE.Group();group.scale.z=-1;scene.add(group); // ENU north -> Three.js -Z, up -> Y.
const ambient=new THREE.HemisphereLight('#c3d7e4','#5e5646',1.5);scene.add(ambient);
const light=new THREE.DirectionalLight('#ffeed7',2.2);light.position.set(4,8,-3);light.target.position.set(6,0,-5);
light.castShadow=true;light.shadow.mapSize.set(1024,1024);Object.assign(light.shadow.camera,{left:-9,right:9,top:9,bottom:-9});light.shadow.normalBias=.025;scene.add(light,light.target);
const wallMaterial=new THREE.MeshStandardMaterial({color:'#bdc0b6',roughness:.95});
for(const [x,z,w,d] of (world.room_asset?[]:[[6,0,12,.12],[6,10,12,.12],[0,5,.12,10],[12,5,.12,10]])){
 const m=new THREE.Mesh(new THREE.BoxGeometry(w,3,d),wallMaterial);m.position.set(x,1.5,z);m.receiveShadow=true;group.add(m);
}
const {actor,assetAudit}=await stressAssets(group,world);
if(world.room_asset){const room=await new GLTFLoader().loadAsync(world.room_asset.url);scene.add(room.scene);}
// Existing workshop labels were authored in the old north=+Z display frame.
// Preserve readable physical text when converting the scene into ENU.
const labels=new Set();group.traverse(o=>{for(const m of (Array.isArray(o.material)?o.material:[o.material]))if(m?.map?.isCanvasTexture)labels.add(m.map);});
for(const t of labels){t.wrapS=THREE.RepeatWrapping;t.repeat.x=-1;t.needsUpdate=true;}
const renderer=new THREE.WebGLRenderer({canvas,antialias:true,preserveDrawingBuffer:true});renderer.setPixelRatio(1);renderer.setSize(world.camera.width,world.camera.height,false);
renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
await importedLighting(renderer,scene,world);
renderer.info.autoReset=false;
const camera=new THREE.PerspectiveCamera(world.camera.vertical_fov,16/9,.04,35),effects=cameraEffects(renderer);
const optics=world.camera.optics;
if(optics){
 const n=camera.near;
 camera.projectionMatrix.makePerspective(-optics.cx*n/optics.fx,(optics.width-optics.cx)*n/optics.fx,
  optics.cy*n/optics.fy,-(optics.height-optics.cy)*n/optics.fy,n,camera.far);
 camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
}
const pitch=world.camera_mount.pitch_degrees*Math.PI/180;
let last=0,sequence=0,recording,queue=Promise.resolve(),pending=0,videoError=null,videoStop,attempts=0;
const history=[],latency=(world.camera.latency_ms||0)/1000;
window.flight={ready:true,capture:null,errors:[],frameCount:0,droppedFrames:0,jpegQuality:world.camera.jpeg_quality??.82,assetAudit,
 renderStats:()=>({memory:{...renderer.info.memory},render:{...renderer.info.render}})};
window.flight.exportCollisionMesh=()=>visibleCollisionMesh(scene,actor);
function fail(e){window.flight.errors.push(String(e));$('error').textContent=String(e);}
let polling=false;
let dropBurst=0;
function randomAt(i){const n=Math.sin((world.seed+i*73.17)*12.9898)*43758.5453;return n-Math.floor(n);}
setInterval(async()=>{if(polling)return;polling=true;try{const r=await fetch('/state',{cache:'no-store'});if(r.ok){history.push(await r.json());if(history.length>32)history.shift();}}catch(e){fail(e);}finally{polling=false;}},50);
function vector(v){return new THREE.Vector3(...v);}
function enu(v){return new THREE.Vector3(v.x,v.z,-v.y);}
function draw(now){
 requestAnimationFrame(draw);if(now-last<1000/15)return;last=now;
 // Delay the entire exposure packet, including its matching estimated pose.
 // A delayed image paired with the current pose would corrupt triangulation.
 const jitter=optics?(randomAt(window.flight.frameCount+attempts)-.5)*2*optics.jitter_ms/1000:0;
 const cutoff=Date.now()/1000-Math.max(0,latency+jitter);
 const state=history.findLast(s=>s.wall_time<=cutoff);
 if(!state?.truth)return;
 if(Date.now()/1000-state.wall_time>1){$('readout').textContent='STALE TELEMETRY · CAPTURE BLOCKED';window.flight.capture=null;return;}
 if(world.camera.drop_every_n && ++attempts%world.camera.drop_every_n===0){window.flight.droppedFrames++;return;}
 if(optics){
  attempts++;
  if(dropBurst>0){dropBurst--;window.flight.droppedFrames++;return;}
  if(randomAt(attempts)<optics.drop_probability){dropBurst=Math.max(0,optics.burst_frames-1);window.flight.droppedFrames++;return;}
 }
 const t=state.truth,q=new THREE.Quaternion(...t.quaternion),p=vector(t.position);
 const mount=vector(world.camera_mount.body_offset_flu_m).applyQuaternion(q);p.add(mount);
 const forward=new THREE.Vector3(Math.cos(pitch),0,Math.sin(pitch)).applyQuaternion(q);
 const up=new THREE.Vector3(-Math.sin(pitch),0,Math.cos(pitch)).applyQuaternion(q);
 camera.position.copy(enu(p));camera.up.copy(enu(up));camera.lookAt(enu(p.clone().add(forward)));
 if(t.cart_position){const c=t.cart_position;actor.position.set(c[0],c[2],c[1]);}
 else actor.position.set(...[world.moving_actor.center[0],0,world.moving_actor.center[1]]);
 const profile=structuredClone(world.camera);profile.effects.blur=Math.min(4,profile.effects.blur+Math.abs(state.angular_speed||0)*1.8);
 if(optics){
  const omega=state.angular_velocity_flu||[0,0,0];
  profile.rotational_flow_px_s=[optics.fx*(omega[2]*Math.cos(pitch)-omega[0]*Math.sin(pitch)),optics.fy*omega[1]];
  // Measured exposure can replace this first-order rotational approximation.
  profile.effects.blur=world.camera.effects.blur;
 }
 const illumination=world.illumination||{},flicker=1+(illumination.flicker_fraction||0)*Math.sin(t.sim_time*2*Math.PI*3);
 ambient.intensity=1.5*(illumination.ambient??1)*flicker;light.intensity=2.2*(illumination.directional??1)*flicker;
 effects.configure(profile,world.seed+t.sim_time*15);renderer.info.reset();effects.render(scene,camera);
 window.flight.capture=structuredClone({truth:t,estimated:state.estimated,wall_time:state.wall_time,sequence:++sequence,render_wall_time:Date.now()/1000,
  sensor:{configured_latency_ms:latency*1000,frame_age_ms:(Date.now()/1000-state.wall_time)*1000,dropped_frames:window.flight.droppedFrames,jpeg_quality:window.flight.jpegQuality,
   optics:optics||null,shutter_model:optics?'First-order rotational rolling shutter and 5-sample exposure; no translational/depth or moving-object integration':'Legacy synthetic shader'}});window.flight.frameCount++;
 $('readout').textContent=`${state.phase} · ${t.sim_time.toFixed(1)} s · ${t.position.map(v=>v.toFixed(2)).join(' / ')} m · ${state.speed.toFixed(2)} m/s`;
 $('mission').textContent=`${world.title} · ${world.complexity.props} props (${world.complexity.ratio}× baseline) · ${world.condition}`;
 $('status').textContent=state.message||'Local mission controller active';
 const ctx=$('map').getContext('2d');ctx.fillStyle='#1d2a30';ctx.fillRect(0,0,360,300);
 ctx.fillStyle='#53646b';for(const b of world.obstacles)ctx.fillRect((b.x-b.sx/2)*30,(10-b.y-b.sy/2)*30,b.sx*30,b.sy*30);
 ctx.strokeStyle='#b4e1c6';ctx.beginPath();for(const [i,v] of (state.trail||[]).entries()){const x=v[0]*30,y=(10-v[1])*30;i?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.stroke();ctx.fillStyle='#e4f8ec';ctx.beginPath();ctx.arc(t.position[0]*30,(10-t.position[1])*30,4,0,Math.PI*2);ctx.fill();
}
draw(0);
window.flight.startVideo=()=>{
 let chunk=0;const stream=canvas.captureStream(15);recording=new MediaRecorder(stream,{mimeType:'video/webm;codecs=vp8',videoBitsPerSecond:1400000});
 recording.ondataavailable=e=>{if(!e.data.size)return;if(++pending>3){videoError='Video writer fell behind';return;}
 const index=chunk++;queue=queue.then(async()=>{const r=await fetch('/video?sequence='+index,{method:'POST',body:e.data});if(!r.ok)throw Error('Video write failed');}).catch(e=>{videoError=String(e);fail(e);}).finally(()=>pending--);};
 recording.start(1000);
};
window.flight.stopVideo=()=>videoStop ||= new Promise((resolve,reject)=>{
 if(!recording)return resolve({error:null});
 const timer=setTimeout(()=>{recording.stream.getTracks().forEach(t=>t.stop());reject(Error('Recorder finalization exceeded 10 seconds'));},10000);
 recording.onstop=async()=>{
  try{await queue;clearTimeout(timer);recording.stream.getTracks().forEach(t=>t.stop());resolve({error:videoError});}
  catch(e){clearTimeout(timer);reject(e);}
 };
 if(recording.state==='inactive'){clearTimeout(timer);return reject(Error('Recorder stopped before finalization was requested'));}
 recording.stop();
});
