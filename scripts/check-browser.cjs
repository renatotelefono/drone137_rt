// Optional integration check: npm install --prefix .local/browser-test playwright@1.58.2
// Start ./scripts/run-local.sh first. CHROMIUM_PATH selects an installed browser.
const { chromium } = require('../.local/browser-test/node_modules/playwright');
const fs = require('node:fs');
let browser;
(async()=>{
 browser = await chromium.launch({executablePath:require('./browser-path.cjs').browserPath(),headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
 const page = await browser.newPage({viewport:{width:1440,height:1100}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8137');
 await page.waitForFunction(()=>document.querySelector('#state').textContent==='IDLE');
 await page.selectOption('#policy','scripted');
 await page.screenshot({path:'.local/browser-test/recon-ui.png',fullPage:true});
 await page.click('#start');
 const state=()=>page.evaluate(async()=> (await fetch('/api/status')).json());
 let s=await state();const episode=s.episode;
 console.log(JSON.stringify({event:'mission_started',episode}));
 const deadline=Date.now()+185000;
 while(Date.now()<deadline){
  await page.waitForTimeout(1000);s=await state();
  if(!['exploring','observing','returning'].includes(s.state))break;
 }
 await page.waitForFunction(()=>document.querySelector('#recording').textContent==='VIDEO SAVED',{},{timeout:10000});
 s=await state();
 const summary=await page.evaluate(async url=> (await fetch(url)).json(),s.report);
 console.log(JSON.stringify({event:'mission_finished',state:s.state,reason:s.reason,observations:s.observations.length,distance:s.distance_m,video_chunks:s.video_chunks,video_complete:s.video_complete}));
 if(s.state!=='complete'||!s.video_complete||s.observations.length<2)throw new Error('Full mission did not complete with evidence');
 // The saved WebM must actually decode, not merely exist.
 const decoded=await page.evaluate(async episode=>{
  const video=document.createElement('video');video.muted=true;video.src=`/reports/${episode}/onboard.webm`;
  await new Promise((resolve,reject)=>{video.onloadeddata=resolve;video.onerror=()=>reject(new Error('Recorded video is not decodable'));setTimeout(()=>reject(new Error('Video decode timed out')),5000);});
  return {width:video.videoWidth,height:video.videoHeight};
 },episode);
 if(decoded.width!==320||decoded.height!==240)throw new Error('Unexpected recording dimensions');
 await page.fill('#seed','42');await page.click('#generate');await page.waitForTimeout(500);await page.click('#start');
 await page.waitForFunction(()=>document.querySelector('#observations li'));await page.click('#freeze');
 await page.waitForFunction(()=>document.querySelector('#state').textContent==='FAILED');
 await page.waitForFunction(()=>document.querySelector('#recording').textContent==='VIDEO SAVED');
 const failure=await state();
 if(!failure.reason.includes('stale')||failure.speed!==0)throw new Error('Sensor failure did not stop mission');
 // Actual network failure is visible; it must not start a scripted fallback.
 const expectBlocked=process.env.DRONE137_EXPECT_MODEL_NETWORK_BLOCK==='1';
 if(expectBlocked){
  await page.click('[data-model="download"]');
  await page.waitForFunction(()=>document.querySelector('#model-detail').textContent.includes('403'),{},{timeout:40000});
 }
 if(errors.length)throw new Error(errors.join('\n'));
 fs.writeFileSync('.local/browser-test/results.json',JSON.stringify({browser:await browser.version(),episode,summary,decoded,sensor_failure:{episode:failure.episode,state:failure.state,reason:failure.reason},page_errors:errors,real_inference:false,model_download:expectBlocked?'blocked: network proxy HTTP 403':'not requested'},null,2));
 console.log('PASS: seeded browser mission, decodable video, sensor failure, optional model download failure, no JavaScript exceptions');
 await browser.close();
})().catch(async e=>{console.error(e);if(browser)await browser.close();process.exitCode=1;});
