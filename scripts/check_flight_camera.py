"""Real-browser recorder shutdown check; static poses, not a flight test."""
import argparse
import asyncio,time,json,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from scripts.evaluate_flight import FlightCamera,serve
from sim.flight_world import scene
from sim.hard_flight import cases,build
from adapters.native_flight import quaternion
class CameraScene:
 def __init__(self,hard=False):self.scene=build(cases()[-2]) if hard else scene();self.started=time.time();self.frozen=None
 def snapshot(self):
  now=time.time();stamp=self.frozen or now;p=[4.35,5.8,1.5];q=quaternion(0,0,1.6);pose={'position':p,'quaternion':q}
  return {'truth':{**pose,'sim_time':stamp-self.started},'estimated':pose,'wall_time':stamp,'phase':'landed','speed':0,'angular_speed':0,'message':'Recorder lifecycle regression check','trail':[]}
async def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 root=args.output.resolve();root.mkdir(parents=True,exist_ok=False);results=[]
 for mode in ('live','stale','live-repeat','delayed-dropped'):
  folder=(root/mode).resolve();folder.mkdir();flight=CameraScene(mode=='delayed-dropped');runner=await serve(flight,folder);camera=FlightCamera()
  try:
   await camera.open(folder);await asyncio.sleep(2);frame=await camera.call(op='capture')
   if mode=='delayed-dropped':
    sensor=frame['metadata']['sensor']
    assert 220<=sensor['frame_age_ms']<700,sensor
    assert sensor['dropped_frames']>0,sensor
    assert sensor['jpeg_quality']==.64,sensor
    assert frame['metadata']['estimated']['position']==frame['metadata']['truth']['position']
   if mode=='stale':flight.frozen=time.time();await asyncio.sleep(2)
   began=time.monotonic();await camera.close();result={'mode':mode,'frame':frame['metadata'],'close_seconds':time.monotonic()-began,'stats':camera.stats,'video_bytes':(folder/'onboard.webm').stat().st_size};results.append(result);print(json.dumps(result),flush=True)
  finally:await camera.close();await runner.cleanup()
 (root/'results.json').write_text(json.dumps(results,indent=2))
if __name__=='__main__':asyncio.run(main())
