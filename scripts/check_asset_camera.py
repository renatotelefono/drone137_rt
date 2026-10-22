"""Static render audit of every frozen room/view; no model requests or flight."""
import argparse
import asyncio
import json
import time
from adapters.native_flight import quaternion
from scripts.evaluate_flight import FlightCamera, serve
from sim.asset_world import build, verify_assets
from sim.hard_flight import cases
from sim.flight_world import VIEWS


class StaticRoom:
    def __init__(self, case):
        self.scene = build(case); self.view = VIEWS[0]

    def snapshot(self):
        now = time.time(); pose = {'position':self.view[:3], 'quaternion':quaternion(0,0,self.view[3])}
        return {'truth':{**pose,'sim_time':now}, 'estimated':pose, 'wall_time':now,
                'phase':'landed','speed':0,'angular_speed':0,'message':'Static asset alignment audit','trail':[]}


async def main():
    from pathlib import Path
    parser = argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(); root = args.output.resolve(); root.mkdir(parents=True,exist_ok=False)
    verify_assets(); results = []
    for case in cases():
        room = StaticRoom(case); folder = root/case['id']; folder.mkdir()
        runner = await serve(room,folder); camera = FlightCamera()
        try:
            await camera.open(folder); frames = []
            for view in VIEWS:
                room.view = view; await asyncio.sleep(.9)
                frames.append(await camera.call(op='capture'))
            await camera.call(op='screenshot',name='preview.png')
            await camera.close()
            audit = json.loads((folder/'asset-render-audit.json').read_text())
            assert len(audit['instances']) == room.scene['complexity']['imported_instances']
            results.append({'case':case['id'],'frames':frames,'asset_audit':audit,'camera':camera.stats})
            print(json.dumps({'case':case['id'],'frames':len(frames),'instances':len(audit['instances']),'render':audit['render']}),flush=True)
        finally:
            await camera.close(); await runner.cleanup()
    (root/'results.json').write_text(json.dumps(results,indent=2))


if __name__ == '__main__':
    asyncio.run(main())
