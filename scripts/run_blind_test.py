"""Run a complete physical blind-mapping trial and preserve every result."""
import argparse
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]


async def trial(args):
    folder=Path(args.output).resolve()
    folder.mkdir(parents=True,exist_ok=False)
    audit=folder/'evaluation-source';audit.mkdir()
    hashes={}
    for source in ('scripts/score_blind_exploration.py','scripts/run_blind_test.py','config/blind-exploration-v1.json'):
        data=(ROOT/source).read_bytes()
        (audit/Path(source).name).write_bytes(data)
        hashes[source]=hashlib.sha256(data).hexdigest()
    (audit/'sha256.json').write_text(json.dumps(hashes,indent=2))
    from scripts.memory_watch import MemoryWatch
    memory=MemoryWatch(args.memory_pid,budget_gib=5);memory.start()
    plant=None
    try:
        with (folder/'simulator-console.log').open('wb') as simlog, (folder/'explorer-console.log').open('wb') as clientlog:
            plant=await asyncio.create_subprocess_exec(str(ROOT/'.local/laya-env/bin/python'),'-m','scripts.blind_simulator',
                '--seed',str(args.seed),'--output',str(folder/'plant'),'--port',str(args.port),cwd=ROOT,
                stdout=asyncio.subprocess.PIPE,stderr=simlog)
            line=await asyncio.wait_for(plant.stdout.readline(),60)
            simlog.write(line);simlog.flush()
            if not line or not json.loads(line).get('ready'):raise RuntimeError('Simulator failed to become ready')
            memory.check()
            command=[sys.executable,'-m','scripts.explore_unknown','--endpoint',f'http://127.0.0.1:{args.port}',
                '--output',str(folder/'explorer'),'--place',args.place,'--name',args.name,'--memory-pid',str(plant.pid)]
            for pid in args.memory_pid:command.extend(['--memory-pid',str(pid)])
            client=await asyncio.create_subprocess_exec(*command,cwd=ROOT,stdout=clientlog,stderr=clientlog)
            try:
                async with asyncio.timeout(680):
                    while client.returncode is None:
                        await asyncio.sleep(10)
                        memory.check()
                        summary=folder/'explorer/summary.json'
                        if summary.exists():
                            s=json.loads(summary.read_text())
                            print(json.dumps({'state':s['state'],'observations':len(s['steps']),'elapsed_s':round(s['wall_time_s'])}),flush=True)
                await client.wait()
            finally:
                if client.returncode is None:
                    client.terminate();await client.wait()
            await asyncio.wait_for(plant.wait(),30)
        memory.stop()
        (folder/'startup-and-flight-memory.json').write_text(json.dumps(memory.report(),allow_nan=False))
        # Execute the scoring source frozen before liftoff, even if development
        # continues in another file while the flight is running.
        spec=importlib.util.spec_from_file_location('frozen_blind_score',audit/'score_blind_exploration.py')
        evaluator=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(evaluator)
        evaluator.ROOT=ROOT
        score=evaluator.evaluate(folder)
        print(json.dumps({'accepted':score['accepted'],'metrics':score['metrics'],'gates':score['gates']}),flush=True)
        return 0 if score['accepted'] else 1
    except Exception as exc:
        (folder/'termination.json').write_text(json.dumps({'error':f'{type(exc).__name__}: {exc}'}))
        raise
    finally:
        memory.stop()
        (folder/'startup-and-flight-memory.json').write_text(json.dumps(memory.report(),allow_nan=False))
        if plant is not None and plant.returncode is None:
            import aiohttp
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    async with session.post(f'http://127.0.0.1:{args.port}/finish',json={}) as response:await response.read()
                await asyncio.wait_for(plant.wait(),20)
            except Exception:
                # Terminate only children owned by this test invocation.
                import psutil
                try:children=psutil.Process(plant.pid).children(recursive=True)
                except psutil.NoSuchProcess:children=[]
                for child in reversed(children):
                    try:child.terminate()
                    except psutil.NoSuchProcess:pass
                if plant.returncode is None:plant.terminate()
                await plant.wait()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,required=True);p.add_argument('--output',required=True)
    p.add_argument('--port',type=int,default=8156);p.add_argument('--place',required=True);p.add_argument('--name',required=True)
    p.add_argument('--memory-pid',type=int,action='append',default=[])
    sys.exit(asyncio.run(trial(p.parse_args())))
