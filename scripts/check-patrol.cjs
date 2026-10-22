// End-to-end rendered patrol. Qwen mode requires the local model already running.
const { chromium } = require('../.local/browser-test/node_modules/playwright');
const fs = require('node:fs');
const policy = process.env.DRONE137_TEST_POLICY || 'scripted';
const scenario = process.env.DRONE137_TEST_SCENARIO || 'warehouse';
const seed = process.env.DRONE137_TEST_SEED || '137';
const condition = process.env.DRONE137_TEST_CONDITION || 'nominal';
const detailed = ['workshop','realism'].includes(scenario);
const tag = `${condition}-${policy}-${scenario}-${seed}-${Date.now()}`;
const output = `.local/browser-test/patrol-${tag}.json`;
const results = {policy, scenario, seed, condition, real_inference: policy === 'qwen', real_flight_dynamics: false, runs: [], errors: []};
let browser;
(async () => {
  browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || (process.platform === 'darwin' ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : '/usr/bin/chromium'),
    headless: true, args: ['--no-sandbox'],
  });
  results.browser = await browser.version();
  const page = await browser.newPage({viewport: {width: 1440, height: 1100}});
  page.on('pageerror', e => results.errors.push(e.message));
  const status = () => page.evaluate(async () => (await fetch('/api/status')).json());
  await page.goto('http://127.0.0.1:8137');
  await page.waitForFunction(() => !document.getElementById('generate').disabled);
  await page.selectOption('#policy', policy);
  await page.selectOption('#scenario', scenario);
  if(scenario==='realism')await page.selectOption('#condition',condition);
  await page.selectOption('#mission', 'patrol');
  await page.fill('#seed', seed);
  for (const variant of ['baseline', 'changed']) {
    await page.selectOption('#variant', variant);
    await page.click('#generate');
    await page.waitForFunction(v => window.document.querySelector('#state').textContent !== 'CONNECTING', variant);
    await page.waitForTimeout(500);
    await page.click('#start');
    let state = await status();
    console.log(JSON.stringify({event: 'patrol_started', policy, variant, episode: state.episode}));
    const deadline = Date.now()+190000;
    while (Date.now() < deadline && ['exploring', 'observing', 'returning'].includes(state.state)) {
      await page.waitForTimeout(1000);
      state = await status();
    }
    await page.waitForFunction(() => document.getElementById('recording').textContent === 'VIDEO SAVED', {}, {timeout: 15000});
    state = await status();
    const summary = await page.evaluate(async url => (await fetch(url)).json(), state.report);
    results.runs.push({episode: state.episode, ...summary});
    fs.writeFileSync(output, JSON.stringify(results, null, 2));
    console.log(JSON.stringify({event: 'patrol_finished', variant, state: state.state, reason: state.reason,
      observations: state.observations, unreached: summary.unreached}));
    if (!['complete', 'partial'].includes(state.state) || !state.video_complete) throw new Error('Patrol did not return with finalized evidence');
    if (variant === 'baseline' && (state.state !== 'complete' || state.observations.length < 3)) throw new Error('Baseline inspection points incomplete');
    if (policy === 'qwen') {
      const passage = summary.observations.find(o => o.view === 'passage');
      const expected = variant === 'baseline' ? 'open_space' : 'solid_surface';
      if (passage?.perception?.center !== expected) throw new Error(`Model missed ${variant} passage: expected ${expected}`);
      if (variant === 'baseline' && summary.observations.some(o=>o.change?.status==='new_obstruction')) throw new Error('False new-obstruction finding in unchanged baseline');
      if (variant === 'changed' && passage.change?.status !== 'new_obstruction') throw new Error('Model-derived report missed the new obstruction');
      if (variant === 'changed' && !summary.unreached.includes('far-room')) throw new Error('Blocked inspection point was not reported');
      if (detailed) {
        if (summary.observations.some(o=>!o.survey?.summary || !Array.isArray(o.survey.objects))) throw new Error('Detailed object survey missing');
        if (variant === 'baseline') {
          const descriptions=summary.observations.map(o=>o.survey.summary+' '+o.survey.objects.join(' ')).join(' ').toLowerCase();
          if(scenario==='realism'&&(!/bottle/.test(descriptions)||!/chair|seat/.test(descriptions)))throw new Error('Model missed bottles or chair in realism patrol');
          if (!/monitor|computer|screen/.test(descriptions) || !/box|carton/.test(descriptions)) throw new Error('Model missed expected workshop objects');
        }
      }
    }
    const report = await browser.newPage();
    await report.goto('http://127.0.0.1:8137'+state.report_page);
    await report.waitForFunction(() => document.querySelector('video')?.readyState >= 2);
    await report.locator('video').evaluate(async v=>{v.muted=true;await v.play();});
    await report.waitForFunction(()=>document.querySelector('video').currentTime>.2);
    await report.locator('video').evaluate((v,t)=>{v.pause();v.currentTime=t;},summary.observations[0].video_time_s);
    await report.waitForFunction(()=>{const v=document.querySelector('video');return !v.seeking&&v.readyState>=2;});
    const decoded=await report.locator('video').evaluate(v=>({width:v.videoWidth,height:v.videoHeight}));
    results.runs[results.runs.length-1].decoded_video=decoded;
    const dimensions=detailed?[1280,720]:[320,240];
    if(decoded.width!==dimensions[0]||decoded.height!==dimensions[1]) throw new Error('Recorded camera dimensions incorrect');
    if(detailed) {
      await report.waitForFunction(()=>[...document.querySelectorAll('article img')].every(i=>i.complete&&i.naturalWidth===960&&i.naturalHeight===540));
      if(policy==='qwen'&&await report.locator('.object-list').count()!==state.observations.length) throw new Error('Object descriptions missing from report');
    }
    if (await report.locator('[data-time]').count() !== state.observations.length) throw new Error('Missing video links');
    if (await report.locator('article img').count() !== state.observations.length) throw new Error('Missing image evidence');
    if (policy === 'qwen' && variant === 'changed' && !(await report.locator('.finding').allTextContents()).some(t=>t.includes('New obstruction'))) throw new Error('Obstruction finding missing from HTML report');
    await report.screenshot({path: `.local/browser-test/report-${tag}-${variant}.png`, fullPage: true});
    await report.close();
  }
  await page.screenshot({path: `.local/browser-test/lab-${tag}.png`, fullPage: true});
  if (results.errors.length) throw new Error(results.errors.join('\n'));
  results.integration_passed = true;
  results.perception_scoring = policy === 'qwen' ? 'Passed clear/blocked passage classification and new-obstruction report assertion; broader semantics not graded.' : 'No model perception in scripted mode.';
  fs.writeFileSync(output, JSON.stringify(results, null, 2));
  await browser.close();
  console.log(`PASS: two rendered patrols, return, playable video, evidence links and ${policy === 'qwen' ? 'model obstruction detection' : 'scripted integration'}. Results: ${output}`);
})().catch(async error => {
  results.failure = error.message;
  fs.writeFileSync(output, JSON.stringify(results, null, 2));
  console.error(error);
  if (browser) await browser.close();
  process.exitCode = 1;
});
