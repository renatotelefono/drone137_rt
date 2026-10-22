"""Receive an ESP32 camera on the ground PC. Never connects to a vehicle.

Run from the repo root with python -m scripts.esp32_camera_bench --help.
"""
import argparse
import asyncio
import json
from pathlib import Path
import time
import uuid

from aiohttp import web

from adapters.esp32_camera import Esp32Camera
from adapters.llama import LlamaBackend
from app.perception import SURVEY_PROMPT, SURVEY_SCHEMA, parse_survey

PAGE = """<!doctype html><html><meta charset=utf-8><title>drone137 camera bench</title>
<style>body{font:16px system-ui;max-width:1000px;margin:30px auto;background:#111923;color:#eee}
img{max-width:100%;width:800px}pre{white-space:pre-wrap}b{color:#91daae}</style>
<h1>ESP32 camera → drone137</h1><p><b>Bench vision only.</b> No aircraft commands.</p>
<img id=frame alt='Waiting for a live camera frame'><pre id=status></pre><pre id=model></pre>
<script>async function update(){try{let s=await(await fetch('/status')).json();
document.querySelector('#status').textContent=JSON.stringify(s,null,2);
if(s.live)document.querySelector('#frame').src='/latest.jpg?t='+Date.now();
else document.querySelector('#frame').removeAttribute('src');
document.querySelector('#model').textContent=JSON.stringify(s.model,null,2);
}catch(e){document.querySelector('#status').textContent=String(e)}setTimeout(update,500)}update()</script></html>"""


async def run(args):
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    camera = Esp32Camera(args.camera, fps=args.fps,
                         require_metadata=not args.allow_receipt_only)
    episode = uuid.uuid4().hex
    camera.begin_episode(episode)
    backend = LlamaBackend(args.model, timeout=args.inference_timeout) if args.model else None
    model = {"enabled":backend is not None, "status":"idle", "result":None, "errors":0}
    observed = []
    last_frame = None
    next_inference = 0
    pending = None
    async def infer(frame):
        model.pop("error", None)
        model.update(status="running", frame_id=frame.frame_id)
        try:
            raw = await backend.image(frame.jpeg, SURVEY_PROMPT, SURVEY_SCHEMA,
                                      time.monotonic()+args.inference_timeout, max_tokens=384)
            result = parse_survey(raw)
            item = {"frame":frame.metadata(), "result":result,
                    "age_at_completion_s":time.monotonic()-frame.received_monotonic,
                    "use":"description only; never a flight authorization"}
            observed.append(item)
            # Retain one image per model observation, bounded by the duration/sample interval.
            (out/(frame.frame_id+'.jpg')).write_bytes(frame.jpeg)
            model.update(status="complete", result=result)
        except Exception as exc:
            model["errors"] += 1
            model.update(status="failed", error=str(exc))
    async def page(_):
        return web.Response(text=PAGE, content_type="text/html")
    async def status(_):
        return web.json_response({**camera.status(), "physical_enabled":False,
                                  "source":"external-camera-bench", "model":model})
    async def latest(_):
        frame = camera.latest()
        if frame is None:
            raise web.HTTPServiceUnavailable(text="No fresh frame")
        return web.Response(body=frame.jpeg, content_type="image/jpeg",
                            headers={"Cache-Control":"no-store"})
    app = web.Application()
    app.router.add_get('/', page)
    app.router.add_get('/status', status)
    app.router.add_get('/latest.jpg', latest)
    runner = web.AppRunner(app)
    try:
        if backend:
            await backend.health()
        await camera.start()
        await runner.setup()
        await web.TCPSite(runner, '127.0.0.1', args.port).start()
        print(f"Camera bench: http://127.0.0.1:{args.port} (no vehicle control)", flush=True)
        started = time.monotonic()
        while time.monotonic()-started < args.seconds:
            frame = camera.latest()
            if frame and frame.frame_id != last_frame:
                (out/'latest.jpg').write_bytes(frame.jpeg)
                last_frame = frame.frame_id
                if backend and time.monotonic() >= next_inference and not backend.quarantined:
                    if pending is None or pending.done():
                        pending = asyncio.create_task(infer(frame))
                        next_inference = time.monotonic()+args.inference_every
            await asyncio.sleep(.05)
        if pending:
            await pending
        report = {"source":"external-camera-bench", "physical_enabled":False,
                  "camera":camera.status(), "model":model, "observations":observed,
                  "hardware_flight_test":False,
                  "passed":camera.frames_received >= 2 and camera.errors == 0 and
                      camera.latest() is not None and (backend is None or (bool(observed) and model['errors'] == 0))}
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps({"report":str(out/'report.json'),"passed":report['passed'],
                          "frames":camera.frames_received,"model_observations":len(observed)}))
        return 0 if report['passed'] else 1
    finally:
        if pending and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await camera.close()
        if backend:
            await backend.close()
        await runner.cleanup()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--camera', required=True, help='http://PRIVATE_IP/capture')
    p.add_argument('--fps', type=float, default=5)
    p.add_argument('--seconds', type=float, default=30)
    p.add_argument('--port', type=int, default=8144)
    p.add_argument('--output', default='runs/esp32-camera-bench')
    p.add_argument('--model', help='Optional local llama-server URL, e.g. http://127.0.0.1:8081')
    p.add_argument('--inference-every', type=float, default=3)
    p.add_argument('--inference-timeout', type=float, default=30)
    p.add_argument('--allow-receipt-only', action='store_true', help='For stock CameraWebServer; capture freshness remains unknown')
    args=p.parse_args()
    import math
    if not all(math.isfinite(x) and x > 0 for x in (args.seconds,args.inference_every,args.inference_timeout)) or args.seconds > 3600:
        p.error('positive finite timing required; bench duration must not exceed 3600 s')
    if args.inference_every < 1 or not 1 <= args.port <= 65535:
        p.error('inference interval must be >= 1 s and port valid')
    raise SystemExit(asyncio.run(run(args)))


if __name__ == '__main__':
    main()
