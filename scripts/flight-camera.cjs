const {chromium}=require('../.local/browser-test/node_modules/playwright');
const readline=require('node:readline'),fs=require('node:fs'),path=require('node:path');
let browser,page,folder,frames=0;
function event(stage,details={}){if(folder)fs.appendFileSync(path.join(folder,'camera-lifecycle.jsonl'),JSON.stringify({time:Date.now()/1000,stage,...details})+'\n');}
async function command(c){
 if(c.op==='open'){
  folder=path.resolve(c.folder);browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
  page=await browser.newPage({viewport:{width:1280,height:1000}});page.on('pageerror',e=>process.stderr.write(e.message+'\n'));
  await page.goto(c.url);await page.waitForFunction(()=>window.flight?.capture,{},{timeout:45000});
  const assets=await page.evaluate(()=>({instances:window.flight.assetAudit,render:window.flight.renderStats()}));
  fs.writeFileSync(path.join(folder,'asset-render-audit.json'),JSON.stringify(assets,null,2));
  await page.evaluate(()=>window.flight.startVideo());return {ready:true};
 }
 if(c.op==='capture'){
  const result=await page.evaluate(()=>{const f=window.flight;if(!f.capture||f.errors.length)throw Error('Camera unavailable: '+f.errors.join(','));if(Date.now()/1000-f.capture.wall_time>.7)throw Error('Stale frame');return {metadata:f.capture,jpeg:document.querySelector('#camera').toDataURL('image/jpeg',f.jpegQuality??.82).split(',')[1]};});
  const name=`frame-${String(++frames).padStart(4,'0')}.jpg`,bytes=Buffer.from(result.jpeg,'base64');if(bytes.length>200000)throw Error('Camera byte cap');fs.writeFileSync(path.join(folder,name),bytes);
  return {image:name,metadata:result.metadata};
 }
 if(c.op==='screenshot'){await page.screenshot({path:path.join(folder,c.name),fullPage:true});return {saved:true};}
 if(c.op==='close'){
  event('recorder-stop-start');
  const video=await page.evaluate(()=>window.flight.stopVideo());event('recorder-stopped',video);
  const stats=await page.evaluate(()=>({frames:window.flight.frameCount,errors:window.flight.errors}));
  event('browser-close-start');await browser.close();event('browser-closed');return {video,stats};
 }
 throw Error('Unknown command');
}
(async()=>{for await(const line of readline.createInterface({input:process.stdin})){try{const c=JSON.parse(line);console.log(JSON.stringify(await command(c)));if(c.op==='close')break;}catch(e){console.log(JSON.stringify({error:e.message}));}}if(browser)await browser.close();})().catch(e=>{console.error(e);process.exitCode=1;});
