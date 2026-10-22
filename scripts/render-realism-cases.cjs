// Capture the production camera canvas; labels stay offline in the evaluator manifest.
const {chromium}=require('../.local/browser-test/node_modules/playwright');
const {spawnSync}=require('node:child_process');
const fs=require('node:fs'),crypto=require('node:crypto');
const folder=process.env.DRONE137_REALISM_CASES||`.local/validation/realism-cases-${Date.now()}`;
const conditions=(process.env.DRONE137_CAMERA_CONDITIONS||'nominal,dim,glare,motion').split(',');
const seed=Number(process.env.DRONE137_TEST_SEED||137);
const generated=spawnSync('.venv/bin/python',['-c',`
import json,math,sys
from sim.recon_world import world
views=[('bottles',[2.5,1.25,1.4,math.pi/2],[['bottle','bottles'],['table','desk','bench','workbench']]),
 ('bench',[8.5,5.3,1.4,math.pi/2],[['monitor','screen','computer'],['keyboard'],['table','bench','desk','workbench']]),
 ('chair',[9.25,5.25,1.4,math.atan2(2.35,1.25)],[['chair','seat']]),
 ('cone',[8.7,4.2,1.4,-math.pi/2],[['cone','cones']]),
 ('stock',[2.5,4.25,1.4,math.pi/2],[['shelf','shelves','shelving','rack'],['box','boxes','carton','cartons']]),
 ('passage',[3.25,4.25,1.4,0],[])]
cases=[]
for condition in json.loads(sys.argv[1]):
 for name,pose,terms in views:
  for variant in (['baseline','changed'] if name=='passage' else ['baseline']):
   scene=world(int(sys.argv[2]),'realism',variant,condition)
   cases.append(dict(id=f'{condition}-{name}-{variant}',scene=scene,pose=pose,terms=terms,
    center=('open_space' if variant=='baseline' else 'solid_surface') if name=='passage' else None))
print(json.dumps(cases))
`,JSON.stringify(conditions),String(seed)],{encoding:'utf8'});
if(generated.status)throw new Error(generated.stderr);
(async()=>{
 fs.mkdirSync(folder,{recursive:false});
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||(process.platform==='darwin'?'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome':'/usr/bin/chromium'),headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  const original=await(await page.request.get('http://127.0.0.1:8137/api/status')).json();
  let state={...original,state:'idle',episode:null,ticket:null,observations:[],report:null,report_page:null};
  await page.route('**/api/status',route=>route.fulfill({json:state}));
  await page.goto('http://127.0.0.1:8137');
  const manifest={version:1,dataset_id:`realism-${seed}-${Date.now()}`,scope:'Synthetic development stress test of one authored indoor bay; not unfamiliar real sites or hardware calibration.',cases:[]};
  const scenes=[];
  for(const test of JSON.parse(generated.stdout)){
   state={...state,scene:test.scene,pose:test.pose};
   await page.waitForFunction(({scene,pose})=>{const c=document.querySelector('#camera');return c.dataset.ready==='true'&&c.dataset.sceneKey===JSON.stringify(scene)&&c.dataset.pose===JSON.stringify(pose);},test,{timeout:30000});
   const frame=await page.locator('#camera').evaluate((canvas,quality)=>{
    const c=document.createElement('canvas');c.width=960;c.height=540;c.getContext('2d').drawImage(canvas,0,0,c.width,c.height);
    return {image:c.toDataURL('image/jpeg',quality).split(',')[1],full:canvas.toDataURL('image/jpeg',.9).split(',')[1],width:canvas.width,height:canvas.height};
   },test.scene.camera.jpeg_quality);
   if(frame.width!==1280||frame.height!==720)throw new Error('Wrong production camera resolution');
   const bytes=Buffer.from(frame.image,'base64'),path=`${test.id}.jpg`;
   if(bytes.length>200000)throw new Error('Inference image exceeds 200 kB');
   fs.writeFileSync(`${folder}/${path}`,bytes);fs.writeFileSync(`${folder}/${test.id}-720p.jpg`,Buffer.from(frame.full,'base64'));
   manifest.cases.push({id:test.id,path,image_sha256:crypto.createHash('sha256').update(bytes).digest('hex'),
    site_id:'virtual-inspection-bay-v1',encounter_id:test.scene.condition,camera_id:'inspection-720p',
    provenance:'Production Three.js camera canvas with procedural props and CC0 scanned concrete; see scenes.json for exact pose, seed and effects.',
    domain:'workshop',source_kind:'synthetic',split:'development',perception_profile:'detail',conditions:[test.scene.condition],
    inspection_task:test.id.includes('-passage-')?'passage':'center',
    annotation:{reviewer:'Codex authored-scene review',reviewer_kind:'agent',center:test.center,required_objects:test.terms,
     notes:'Reference classes from authored scene and camera pose. Required-name checks do not measure full caption precision; all views share one virtual site.'}});
   scenes.push({id:test.id,scene:test.scene,pose:test.pose});
  }
  fs.writeFileSync(`${folder}/manifest.json`,JSON.stringify(manifest,null,2));
  fs.writeFileSync(`${folder}/scenes.json`,JSON.stringify(scenes,null,2));
  fs.mkdirSync(`${folder}/renderer`);
  for(const p of ['app/ui/recon.js','app/ui/scene-realism.js','app/ui/scene-detail.js','app/ui/camera-effects.js','sim/recon_world.py','app/ui/textures/provenance.json'])fs.copyFileSync(p,`${folder}/renderer/${p.split('/').at(-1)}`);
  await page.screenshot({path:`${folder}/ui.png`,fullPage:true});
  if(errors.length)throw new Error(errors.join('\n'));
  console.log(JSON.stringify({folder,cases:manifest.cases.length,browser_errors:errors,synthetic:true}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
