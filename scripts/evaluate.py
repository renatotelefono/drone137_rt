"""Functional runs against the local API. Never promotes Mac/hardware gates."""
import argparse
import asyncio
import json
import platform
import subprocess
import time
import uuid

import aiohttp
from scripts.tools import DATA
from app.recorder import RunRecorder


def score_default_gates(events):
    """Evaluator-only labels for the default courtyard, never model context."""
    expected = {'gate_a': 'open', 'gate_b': 'closed'}
    observations = {e['request_id']: e for e in events if e['event'] == 'observation'}
    results = []
    for event in events:
        if event['event'] != 'decision_accepted':
            continue
        source = observations.get(event['request_id'], {})
        target = source.get('target')
        results.append({'target': target, 'view': source.get('view'),
                        'image': source.get('image_file'), 'expected': expected.get(target),
                        'observed': event['observation'], 'reason': event['reason'],
                        'correct': target in expected and event['observation'] == expected[target]})
    return {'passed': {r['target'] for r in results} == set(expected)
            and all(r['correct'] for r in results), 'observations': results}


async def evaluate(args):
    endpoint=f"http://127.0.0.1:{args.port}"
    report={"host":platform.node(),"architecture":platform.machine(),"os":platform.platform(),
            "suite":args.suite,"mode":args.mode,"episodes":[],
            "mac_virtual_acceptance":"unverified","lean_memory_budget":"unverified",
            "actual_8gb_validation":"unverified","hardware_gate":"blocked",
            "note":"Same-scene functional runs only; no held-out accuracy or failure-suite acceptance claim.",
            "resources":[]}
    started=time.monotonic()
    # Evaluation reports share the same 1 GiB run-evidence budget.
    recorder=RunRecorder(DATA/"runs",uuid.uuid4().hex,1024**3,{
        "profile":"cloud-dev" if args.mode=="fixture" else "lean-8gb",
        "test":"evaluation", "mode":args.mode})
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10),trust_env=False) as session:
        async def status():
            async with session.get(endpoint+"/api/status") as response:
                response.raise_for_status()
                return await response.json()
        initial=await status()
        if initial["mode"]!=args.mode:
            raise RuntimeError("Requested evaluation mode differs from running app")
        if args.mode=="sim" and not all(initial[k] for k in ("real_inference","real_camera","real_flight_dynamics")):
            raise RuntimeError("Native model smoke requires actual inference, rendered camera and flight dynamics")
        report["provenance"]=initial
        count=0
        while count<args.episodes or (args.suite=="resources" and time.monotonic()-started<args.duration_minutes*60):
            async with session.post(endpoint+"/api/start",headers={"X-Drone137-Control":"local"}) as response:
                response.raise_for_status()
            async with asyncio.timeout(220):
                while True:
                    current=await status()
                    if current["state"] in ("complete","failed"):
                        break
                    if args.suite=="resources":
                        sample={"elapsed_s":time.monotonic()-started}
                        # System pressure signals; do not equate summed RSS with physical footprint.
                        if platform.system()=="Darwin":
                            sample["vm_stat"]=subprocess.check_output(["vm_stat"],text=True)
                            sample["swap"]=subprocess.check_output(["sysctl","vm.swapusage"],text=True)
                        report["resources"].append(sample)
                        # Bounded to a configured 120-minute run at 1 Hz.
                    await asyncio.sleep(1)
            episode = {"episode":current["episode"],"state":current["state"],"error":current["error"]}
            if args.score_default_gates:
                events = [json.loads(line) for line in (DATA/'runs'/current['episode']/'events.jsonl').read_text().splitlines()]
                episode['perception'] = score_default_gates(events)
                episode['landed'] = not current['telemetry']['in_air']
            report["episodes"].append(episode)
            count+=1
            if (current["state"]!="complete" or args.score_default_gates
                and (not episode['perception']['passed'] or not episode['landed'])):
                break
    report["elapsed_s"]=time.monotonic()-started
    report["completed"]=sum(e["state"]=="complete" for e in report["episodes"])
    report['passed'] = (len(report['episodes']) >= args.episodes
                        and report['completed'] == len(report['episodes'])
                        and all(e.get('perception', {}).get('passed', True) and e.get('landed', True)
                                for e in report['episodes']))
    # The complete report is budget checked as a regular evidence object.
    recorder._write(recorder.directory/"evaluation.json",json.dumps(report,indent=2).encode())
    recorder.finish(completed=report["completed"],episodes=len(report["episodes"]),mode=args.mode)
    target=recorder.directory/"evaluation.json"
    print(target)
    if not report['passed']:
        raise SystemExit(1)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--suite",choices=["smoke","resources"],default="smoke")
    parser.add_argument("--mode",choices=["sim","fixture"],default="sim")
    parser.add_argument("--episodes",type=int,default=20)
    parser.add_argument("--port",type=int,default=8137)
    parser.add_argument("--score-default-gates",action="store_true",
                        help="Require correct gate_a=open/gate_b=closed observations and landing; use the default courtyard only")
    parser.add_argument("--duration-minutes",type=float,default=30)
    args=parser.parse_args()
    if not 1<=args.port<=65535 or not 1<=args.episodes<=1000 or not 0<args.duration_minutes<=120:
        parser.error("port must be 1–65535; episodes 1–1000; duration >0 and <=120 minutes")
    asyncio.run(evaluate(args))
