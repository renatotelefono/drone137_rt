// Evaluation-only fixture renderer. Labels/geometry never enter model requests.
const {chromium} = require('../.local/browser-test/node_modules/playwright');
const {spawnSync} = require('node:child_process');
const fs = require('node:fs');
const folder = '.local/validation/vision-cases';
const generated = spawnSync('.venv/bin/python', ['-c', `
import json,random
from sim.recon_world import world
cases=[]
for i in range(12):
 rng=random.Random(9100+i)
 pose=[rng.uniform(3.7,4.4),rng.uniform(3.9,4.3),rng.uniform(1.2,1.6),rng.uniform(-.06,.06)]
 for variant in ('baseline','changed'):
  scene=world(9100+i,'warehouse' if i%2 else 'rooms',variant)
  scene['lighting']=rng.uniform(.65,1.3)
  if i%3: scene['obstacles'].insert(0,dict(x=10.5,y=8.5,sx=.4,sy=.4,height=1.9))
  cases.append(dict(id=f'view-{i:02d}-{variant}',scene=scene,pose=pose,expected='open_space' if variant=='baseline' else 'solid_surface'))
print(json.dumps(cases))
`], {encoding:'utf8'});
if(generated.status) throw new Error(generated.stderr);
const cases = JSON.parse(generated.stdout);
(async()=>{
 fs.mkdirSync(folder,{recursive:true});
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 try{
  const page=await browser.newPage();
  const original=await (await page.request.get('http://127.0.0.1:8137/api/status')).json();
  let current={...original,state:'idle',episode:null,observations:[],ticket:null,report:null,report_page:null,baseline_episode:null};
  await page.route('**/api/status',route=>route.fulfill({json:current}));
  await page.goto('http://127.0.0.1:8137');
  await page.waitForFunction(()=>document.querySelector('#state').textContent==='IDLE');
  const manifest=[];
  for(const test of cases){
   current={...current,scene:test.scene,pose:test.pose};
   await page.waitForTimeout(650);
   const jpeg=await page.locator('#camera').evaluate(canvas=>canvas.toDataURL('image/jpeg',.9).split(',')[1]);
   const path=`${folder}/${test.id}.jpg`;
   fs.writeFileSync(path,Buffer.from(jpeg,'base64'));
   manifest.push({id:test.id,path,expected:test.expected,scene:test.scene,pose:test.pose});
  }
  fs.writeFileSync(`${folder}/manifest.json`,JSON.stringify(manifest,null,2));
  console.log(`Rendered ${manifest.length} held-out views with the production Three.js renderer`);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
