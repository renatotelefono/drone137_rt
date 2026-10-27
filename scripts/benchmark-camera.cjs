// Fixed-pose comparison worker. It never controls flight or supplies model inputs.
const {chromium}=require('../.local/browser-test/node_modules/playwright');
const readline=require('node:readline'),fs=require('node:fs'),crypto=require('node:crypto');
let browser,page;
async function command(c){
 if(c.op==='open'){
  browser=await chromium.launch({executablePath:require('./browser-path.cjs').browserPath(),headless:true});
  page=await browser.newPage({viewport:{width:1280,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(c.url);await page.waitForFunction(()=>window.flight?.capture);
  if(errors.length)throw Error(errors.join('; '));return {ready:true};
 }
 if(c.op==='sample'){
  await page.waitForFunction(t=>window.flight?.capture?.truth.sim_time===t,c.sim_time);
  await page.evaluate(()=>window.__benchSamples=[]);
  await page.waitForFunction(()=>window.__benchSamples.length>=6);
  const data=await page.evaluate(()=>({png:document.querySelector('#camera').toDataURL('image/png').split(',')[1],samples:window.__benchSamples,errors:window.flight.errors}));
  if(data.errors.length)throw Error(data.errors.join('; '));
  const bytes=Buffer.from(data.png,'base64');fs.writeFileSync(c.path,bytes);
  return {sha256:crypto.createHash('sha256').update(bytes).digest('hex'),samples:data.samples};
 }
 if(c.op==='close'){await browser.close();browser=null;return {closed:true};}
 throw Error('Unknown benchmark operation');
}
(async()=>{try{for await(const line of readline.createInterface({input:process.stdin})){
 try{console.log(JSON.stringify(await command(JSON.parse(line))));}catch(e){console.log(JSON.stringify({error:e.message}));}
}}finally{if(browser)await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
