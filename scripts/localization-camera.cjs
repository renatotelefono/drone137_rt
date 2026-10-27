// A single production Three.js camera. JSON-lines IPC carries renderer data, never model input.
const {chromium}=require('../.local/browser-test/node_modules/playwright');
const readline=require('node:readline'),fs=require('node:fs'),path=require('node:path');
let browser,page,state,folder,currentScene,frames=0;
async function command(c){
 if(c.op==='open'){
  folder=path.resolve(c.folder);fs.mkdirSync(folder,{recursive:true});
  browser=await chromium.launch({executablePath:require('./browser-path.cjs').browserPath(),headless:true});
  page=await browser.newPage({viewport:{width:1280,height:860}});
  page.on('pageerror',e=>process.stderr.write(e.message+'\n'));
  const original=await(await page.request.get('http://127.0.0.1:8137/api/status')).json();
  if(['exploring','observing','returning','paused'].includes(original.state)||original.model.busy)throw Error('Simulator/model busy');
  state={...original,state:'idle',episode:null,ticket:null,observations:[],report:null,report_page:null,video_complete:false};
  await page.route('**/api/status',r=>r.fulfill({json:state}));
  await page.route('**/api/runs',r=>r.fulfill({json:[]}));
  await page.goto('http://127.0.0.1:8137');
  return {ready:true};
 }
 if(c.op==='capture'){
  if(c.scene)currentScene=c.scene;
  state={...state,scene:currentScene,pose:c.pose};
  await page.waitForFunction(({scene,pose})=>{const c=document.querySelector('#camera');return c.dataset.ready==='true'&&c.dataset.sceneKey===JSON.stringify(scene)&&c.dataset.pose===JSON.stringify(pose);},{scene:currentScene,pose:c.pose},{timeout:30000});
  const jpeg=await page.locator('#camera').evaluate(canvas=>{
   const c=document.createElement('canvas');c.width=960;c.height=540;c.getContext('2d').drawImage(canvas,0,0,960,540);
   return c.toDataURL('image/jpeg',.82).split(',')[1];
  });
  const name=`frame-${String(++frames).padStart(4,'0')}.jpg`,bytes=Buffer.from(jpeg,'base64');
  if(bytes.length>200000)throw Error('Image exceeds inference cap');
  fs.writeFileSync(path.join(folder,name),bytes);
  return {image:name,bytes:bytes.length};
 }
 if(c.op==='screenshot'){await page.screenshot({path:path.join(folder,c.name),fullPage:true});return {saved:true};}
 if(c.op==='close'){await browser.close();return {closed:true};}
 throw Error('Unknown camera command');
}
(async()=>{
 for await(const line of readline.createInterface({input:process.stdin})){
  try{const c=JSON.parse(line);console.log(JSON.stringify(await command(c)));if(c.op==='close')break;}
  catch(e){console.log(JSON.stringify({error:e.message}));}
 }
 if(browser)await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1;});
