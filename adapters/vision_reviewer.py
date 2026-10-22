"""Optional independent camera-crop reviewer, in one bounded worker process."""
import asyncio
import json
import os
from pathlib import Path
import re
import time

ROOT=Path(__file__).resolve().parents[1]
SMOL_PROMPT='What is the central object in this image? Name the object and describe its visible components. If the object cannot be identified, say uncertain. Do not guess hidden parts.'
FLORENCE_PROMPT='<DETAILED_CAPTION>'


def accepts_caption(caption):
    """Conservative, explicit class evidence; negation/uncertainty fails closed."""
    text=caption.lower()
    return bool(re.search(r'\bfire[ -]extinguisher\b',text) and not re.search(
        r"\b(not|no|uncertain|unclear|possibly|maybe|might|could|cannot|can't|without)\b",text))


class VisionReviewer:
    def __init__(self,name,folder):
        if name not in ('florence','smolvlm'):raise ValueError('Unknown visual reviewer')
        self.name=name;self.folder=folder;self.process=None;self.log=None;self.metadata=None

    async def start(self):
        self.log=(self.folder/f'{self.name}-worker.log').open('wb')
        env={**os.environ,'HF_HOME':str(ROOT/'.local/huggingface'),'HF_HUB_OFFLINE':'1',
             'TOKENIZERS_PARALLELISM':'false','PYTORCH_ENABLE_MPS_FALLBACK':'1'}
        self.process=await asyncio.create_subprocess_exec(str(ROOT/'.local/vision-env/bin/python'),
            '-m','scripts.vision_reviewer_worker','--model',self.name,cwd=ROOT,env=env,
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=self.log)
        self.metadata=await self.read(120)
        if not self.metadata.get('ready'):raise RuntimeError(str(self.metadata))
        return self.metadata

    async def read(self,timeout):
        line=await asyncio.wait_for(self.process.stdout.readline(),timeout)
        if not line:raise RuntimeError('Vision reviewer exited; inspect worker log')
        result=json.loads(line)
        if result.get('error'):raise RuntimeError(result['error'])
        return result

    async def review(self,path):
        began=time.monotonic()
        self.process.stdin.write((json.dumps({'image':str(path.resolve())})+'\n').encode())
        await self.process.stdin.drain()
        response=await self.read(20)
        return {**response,'accepted':accepts_caption(response['caption']),
                'latency_s':time.monotonic()-began,'model':self.name}

    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.stdin.close()
            try:await asyncio.wait_for(self.process.wait(),5)
            except TimeoutError:
                self.process.terminate()
                try:await asyncio.wait_for(self.process.wait(),5)
                except TimeoutError:self.process.kill();await self.process.wait()
        if self.log:self.log.close()
