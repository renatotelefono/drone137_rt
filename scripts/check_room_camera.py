"""Render a frozen room package through the actual camera; no inference or flight."""
import argparse
import asyncio
import json
from pathlib import Path
import time
from adapters.native_flight import quaternion
from scripts.evaluate_flight import FlightCamera,serve
from sim.asset_world import build
from sim.hard_flight import cases
from sim.hardware import apply_profile
from sim.room_assets import attach_room
from app.airframes import Airframes
import shutil


async def main(args):
    folder=args.output.resolve();folder.mkdir(parents=True,exist_ok=False)
    class Room:
        scene=attach_room(apply_profile(build(cases()[0]),Airframes().resolve(args.airframe)),args.room)
        def snapshot(self):
            now=time.time();pose={'position':[6,2,1.5],'quaternion':quaternion(0,0,1.57079632679)}
            return {'truth':{**pose,'sim_time':now},'estimated':pose,'wall_time':now,'phase':'room-render-audit','message':'Reconstruction import check, no flight','speed':0,'angular_speed':0,'trail':[]}
    room=Room();shutil.copyfile(room.scene['room_asset']['path'],folder/'room.glb');(folder/'scene.json').write_text(json.dumps(room.scene,indent=2))
    runner=await serve(room,folder);camera=FlightCamera()
    try:
        await camera.open(folder);await asyncio.sleep(.5);frame=await camera.call(op='capture');await camera.call(op='screenshot',name='preview.png');await camera.close()
        result={'source_kind':room.scene['room_asset']['source_kind'],'frame':frame,'camera':camera.stats,'physical_agreement_verified':False}
        (folder/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    finally:
        await camera.close();await runner.cleanup()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--room',type=Path,required=True);p.add_argument('--airframe',default='reference-quad');p.add_argument('--output',type=Path,required=True)
    asyncio.run(main(p.parse_args()))
