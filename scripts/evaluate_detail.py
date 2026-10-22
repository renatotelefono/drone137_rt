"""Score real local-model object descriptions on rendered workshop images."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time

import aiohttp
from adapters.llama import LlamaBackend
from app.perception import inspect, survey, choose_action
from scripts.tools import DATA


async def evaluate(args):
    async with aiohttp.ClientSession() as session:
        async with session.get('http://127.0.0.1:8137/api/status') as response:
            response.raise_for_status(); state = await response.json()
    if state['state'] in ('exploring','observing','returning','paused') or state['model']['busy']:
        raise RuntimeError('End the mission/model operation before evaluating images')
    backend = LlamaBackend()
    async def image(jpeg,prompt,schema,**kwargs):
        return await backend.image(jpeg,prompt,schema,time.monotonic()+6,**kwargs)
    async def text(prompt,schema):
        return await backend.text(prompt,schema,time.monotonic()+6)
    report = {'real_inference':True, 'physical_transport':False, 'cases':[], 'passed':False,
              'model':json.loads((DATA/'models/manifest.json').read_text()),
              'scope':'Expected visible object names and two passage classifications; not exhaustive caption accuracy'}
    manifest = args.manifest
    if manifest is None:
        candidates = sorted(Path('.local/validation').glob('detail-cases*/manifest.json'),
                            key=lambda p:p.stat().st_mtime,reverse=True)
        if not candidates:
            raise RuntimeError('Render workshop cases first: node scripts/render-detail-cases.cjs')
        manifest = candidates[0]
    report['manifest'] = str(manifest)
    cases = json.loads(manifest.read_text())
    try:
        await backend.health()
        for case in cases:
            jpeg = Path(case['path']).read_bytes(); started = time.monotonic()
            result = {k:case[k] for k in ('id','path','expected_terms','expected_center')}
            result['image_sha256'] = hashlib.sha256(jpeg).hexdigest()
            try:
                visual = await inspect(image,jpeg,detailed=True)
                action = await choose_action(text,visual,('continue','look_left','look_right','hold'))
                details = await survey(image,jpeg)
                description = ' '.join([details['summary'],*details['objects']]).lower()
                terms_match = all(any(term in description for term in alternatives) for alternatives in case['expected_terms'])
                center_match = case['expected_center'] is None or case['expected_center']==visual['center']
                result.update(perception=visual,survey=details,action=action,
                              terms_match=terms_match,center_match=center_match,passed=terms_match and center_match)
            except Exception as exc:
                result.update(error=str(exc),passed=False)
            result['latency_s'] = time.monotonic()-started
            report['cases'].append(result);print(json.dumps(result),flush=True)
            if backend.quarantined:break
        report['passed'] = len(report['cases'])==len(cases) and all(c['passed'] for c in report['cases'])
    finally:
        await backend.close();args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'correct':sum(c['passed'] for c in report['cases']),'total':len(cases)}))
    return report['passed']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,help='Defaults to the newest completed workshop render set')
    p.add_argument('--output',type=Path,default=Path(f'.local/validation/detail-{time.time_ns()}.json'))
    raise SystemExit(0 if asyncio.run(evaluate(p.parse_args())) else 1)
