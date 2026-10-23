"""Short sensor/estimator flight diagnostic; not the blind exploration test."""
import argparse
import asyncio
import base64
import json
from pathlib import Path
import time

from app.visual_inertial import VisualInertial
from scripts.explore_unknown import Link


async def run(args):
    link=Link(args.endpoint);vio=VisualInertial();task=None
    output=Path(args.output);output.mkdir(parents=True,exist_ok=False)
    latest=None;error=None
    try:
        await link.start()
        await link.fly([0,0,.3,0])
        await asyncio.sleep(2)
        first=await link.call('/frame')
        await vio.start(first['calibration'],output,link.latest['position'][2])
        async def camera_loop():
            nonlocal latest,error
            try:
                while True:
                    f=await link.call('/frame')
                    imu=await link.call('/imu?after='+str(vio.last_imu))
                    result=await vio.observe(f,base64.b64decode(f['jpeg']),imu)
                    if result:
                        latest=result
                        if result['initialized']:
                            # The probe records VIO independently before enabling
                            # its position corrections in the full explorer.
                            print(json.dumps({k:result[k] for k in ('time_s','position','velocity','position_std_m')}|
                                             {'features':len(result['landmarks'])}),flush=True)
                            if args.correct and len(result['landmarks'])>=25 and max(result['position_std_m'])<.3:
                                await link.call('/visual',{**{k:result[k] for k in ('time_s','position','velocity','quaternion')},'inliers':len(result['landmarks'])})
                    await asyncio.sleep(.03)
            except asyncio.CancelledError:raise
            except Exception as exc:error=repr(exc);raise
        task=asyncio.create_task(camera_loop())
        async with asyncio.timeout(20):
            while latest is None or not latest['initialized']:
                if error:raise RuntimeError(error)
                await asyncio.sleep(.1)
        await asyncio.sleep(1)
        for goal in ([.3,0,.3,0],[.3,0,1.1,0],[.5,.5,1.1,.4],[0,0,1.1,0]):
            if error:raise RuntimeError(error)
            await link.fly(goal)
            await asyncio.sleep(2)
        await link.land()
        print(json.dumps({'completed':True}),flush=True)
    finally:
        if link.latest and link.goal:
            await link.land()
        if task:
            task.cancel();await asyncio.gather(task,return_exceptions=True)
        await vio.close()
        if link.latest:await link.call('/finish',{})
        await link.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--endpoint',default='http://127.0.0.1:8156');p.add_argument('--output',required=True);p.add_argument('--correct',action='store_true')
    asyncio.run(run(p.parse_args()))
