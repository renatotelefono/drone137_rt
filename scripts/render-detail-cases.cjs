// Render actual production workshop views. Evaluator labels are never sent to Qwen.
const {chromium}=require('../.local/browser-test/node_modules/playwright');
const {spawnSync}=require('node:child_process');
const fs=require('node:fs');
const folder=process.env.DRONE137_DETAIL_CASES||`.local/validation/detail-cases-${Date.now()}`;
const generated=spawnSync('.venv/bin/python',['-c',`
import json,math
from sim.recon_world import world
cases=[]
views=[('stock-rack',[2.5,4.25,1.4,math.pi/2],[['shelf','shelv','rack'],['box','boxes','carton']]),
 ('workbench',[8.5,4.25,1.4,math.pi/2],[['monitor','screen','computer'],['table','bench','desk']]),
 ('drums',[10.5,4,1.4,-math.pi/2],[['barrel','drum']]),
 ('plant',[9.2,8.9,1.4,0],[['plant','leaves','foliage']]),
 ('extinguisher',[3.7,7.1,1.4,math.pi/2],[['extinguisher']]),
 ('passage',[3.25,4.25,1.4,0],[])]
for name,pose,terms in views:
 for variant in (['baseline','changed'] if name=='passage' else ['baseline']):
  scene=world(137,'workshop',variant)
  cases.append(dict(id=name+'-'+variant,scene=scene,pose=pose,expected_terms=terms,
   expected_center=('open_space' if variant=='baseline' else 'solid_surface') if name=='passage' else None))
print(json.dumps(cases))
`],{encoding:'utf8'});
if(generated.status)throw new Error(generated.stderr);
(async()=>{
 fs.mkdirSync(folder,{recursive:true});
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||(process.platform==='darwin'?'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome':'/usr/bin/chromium'),headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const original=await(await page.request.get('http://127.0.0.1:8137/api/status')).json();
  let state={...original,state:'idle',episode:null,ticket:null,observations:[],report:null,report_page:null};
  await page.route('**/api/status',route=>route.fulfill({json:state}));
  await page.goto('http://127.0.0.1:8137');await page.waitForFunction(()=>document.querySelector('#state').textContent==='IDLE');
  const manifest=[];
  for(const test of JSON.parse(generated.stdout)){
   state={...state,scene:test.scene,pose:test.pose};await page.waitForTimeout(900);
   const frame=await page.locator('#camera').evaluate(canvas=>{
    const c=document.createElement('canvas');c.width=960;c.height=540;c.getContext('2d').drawImage(canvas,0,0,c.width,c.height);
    return {image:c.toDataURL('image/jpeg',.85).split(',')[1],full:canvas.toDataURL('image/jpeg',.9).split(',')[1],width:canvas.width,height:canvas.height};
   });
   if(frame.width!==1280||frame.height!==720)throw new Error('Detail camera dimensions incorrect');
   const path=`${folder}/${test.id}.jpg`;fs.writeFileSync(path,Buffer.from(frame.image,'base64'));
   fs.writeFileSync(`${folder}/${test.id}-720p.jpg`,Buffer.from(frame.full,'base64'));
   if(fs.statSync(path).size>200000)throw new Error('Snapshot exceeds inference image budget');
   manifest.push({...test,path,width:960,height:540});
  }
  await page.screenshot({path:`${folder}/workshop-ui.png`,fullPage:true});
  fs.writeFileSync(`${folder}/manifest.json`,JSON.stringify(manifest,null,2));
  if(errors.length)throw new Error(errors.join('\n'));
  console.log(`Rendered ${manifest.length} workshop views at 720p; 960x540 inference images, zero browser exceptions. Manifest: ${folder}/manifest.json`);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
