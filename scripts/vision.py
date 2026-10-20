import argparse
import asyncio
import json
import time
import uuid
from dataclasses import asdict

from adapters.llama import LlamaBackend
from app.contracts import Decision, Frame, Observation, Telemetry
from app.native import start_model
from app.recorder import RunRecorder
from app.watchdog import ProcessSupervisor
from scripts.tools import ROOT, DATA


async def check():
    owned = ProcessSupervisor()
    backend = LlamaBackend()
    episode = uuid.uuid4().hex
    recorder = RunRecorder(DATA/"runs", episode, 1024**3, {
        "profile":"lean-8gb", "real_inference":True, "real_camera":False,
        "real_flight_dynamics":False, "test":"paired synthetic-image inference"})
    results=[]
    try:
        await start_model(owned)
        for index, expected in [(1,"open"),(2,"closed")]:
            frame=Frame(uuid.uuid4().hex,episode,
                        (ROOT/f"sim/assets/fixture-{index:02d}.jpg").read_bytes(),time.monotonic(),
                        camera_id="synthetic-test-image")
            recorder.image(frame)
            observation=Observation(episode,uuid.uuid4().hex,frame,time.monotonic()+6,1,
                                    "gate","front",("side",),("continue","recheck","hold","finish"),
                                    Telemetry((0,0,2),0,time.monotonic()))
            start=time.monotonic()
            raw=await backend.infer(observation)
            decision=Decision.parse(raw)
            recorder.record("vision_result",frame_id=frame.frame_id,raw=raw,expected=expected,
                            latency_s=time.monotonic()-start)
            results.append(decision.observation==expected)
        recorder.finish(paired_image_check=all(results),correct=sum(results),total=2,
                        mac_virtual_acceptance="unverified")
        print(recorder.directory)
        if not all(results):
            raise RuntimeError("Actual model failed paired-image check; inspect saved responses")
    finally:
        await backend.close()
        await owned.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--profile",choices=["lean-8gb"],default="lean-8gb")
    parser.parse_args()
    asyncio.run(check())
