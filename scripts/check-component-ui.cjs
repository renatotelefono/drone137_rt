const {chromium}=require('../.local/browser-test/node_modules/playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
const folder='.local/validation/component-ui';fs.mkdirSync(folder,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:require('./browser-path.cjs').browserPath(),headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8152/components');await page.waitForFunction(()=>window.componentLab&&document.querySelector('#state').textContent==='Ready');
  // Swaps must be persisted before a run can use them.
  await page.selectOption('#configuration','scout-110');await page.selectOption('[data-slot="battery"]','pluto-600@1');
  assert.equal(await page.isDisabled('#run'),true);
  const variant='ui-scout-'+Date.now();await page.fill('#variant-id',variant);await page.click('#save-variant');
  await page.waitForFunction(id=>document.querySelector('#configuration').value===id,variant);
  await page.reload();await page.waitForFunction(()=>window.componentLab);await page.selectOption('#configuration',variant);
  assert.equal(await page.locator('[data-slot="battery"]').inputValue(),'pluto-600@1');
  await page.click('#run');await page.waitForFunction(()=>window.componentLab.state().time_s>3);
  const pose=await page.evaluate(()=>({physics:window.componentLab.state(),rendered:window.componentLab.rendered()}));
  assert.ok(pose.physics.position.y>.5);for(const [i,k] of ['x','y','z'].entries())assert.ok(Math.abs(pose.rendered.position[i]-pose.physics.position[k])<1e-10);
  await page.screenshot({path:folder+'/flight.png',fullPage:false});
  await page.waitForFunction(()=>document.querySelector('#state').textContent==='Test complete',null,{timeout:40000});
  await page.waitForFunction(()=>document.querySelector('#history tr')?.textContent.includes(document.querySelector('#configuration').value));
  assert.ok((await page.locator('#result').textContent()).includes('Flight PASS'));
  // The exact browser and headless module must agree on the same saved snapshot.
  const trial=await page.evaluate(async()=>{const d=await(await fetch('/api/components')).json();const r=d.history.find(h=>h.result?.configuration===document.querySelector('#configuration').value);return {result:r.result,assembly:d.assemblies.find(a=>a.configuration.content.id===r.result.configuration)};});
  fs.writeFileSync(folder+'/browser-trial.json',JSON.stringify(trial,null,2));
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await page.screenshot({path:folder+'/mobile.png',fullPage:false});
  assert.deepEqual(errors,[]);fs.writeFileSync(folder+'/checks.json',JSON.stringify({passed:true,errors,swap_persisted:true,physics_render_pose_equal:true,flight_passed:trial.result.flight_passed,mobile_overflow:false},null,2));
  console.log('PASS: persisted swap, actual browser flight, render/physics agreement, saved result, mobile layout.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
