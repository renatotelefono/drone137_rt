import asyncio
import uuid
import time
import json
import struct
import os

from adapters.fixtures import LatestFrameBuffer
from app.contracts import Frame


class GStreamerCamera(LatestFrameBuffer):
    """RTP/H264 receiver with a bounded JPEG parser and one latest-frame slot.

    Timestamps are host receipt only: sensor capture time and network delay are
    unknown, which must remain visible in acceptance reports.
    """
    def __init__(self, port=5600):
        super().__init__()
        self.port, self.episode = port, ""
        self.process = self.task = None
        self.error = None

    def begin_episode(self, episode):
        self.episode = episode
        self.clear()

    async def start(self):
        args = [
            "gst-launch-1.0", "-q", "udpsrc", "address=127.0.0.1", f"port={self.port}",
            "caps=application/x-rtp,media=video,clock-rate=90000,encoding-name=H264",
            "!", "rtph264depay", "!", "avdec_h264", "!", "videoconvert",
            "!", "videoscale", "!", "videorate",
            "!", "video/x-raw,width=320,height=240,framerate=2/1",
            "!", "jpegenc", "!", "fdsink", "fd=1",
        ]
        self.process = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        self.task = asyncio.create_task(self._read())

    async def _read(self):
        buffer = bytearray()
        try:
            while chunk := await self.process.stdout.read(65536):
                buffer.extend(chunk)
                if len(buffer) > 2_000_000:
                    raise RuntimeError("camera JPEG exceeds 2 MB bound")
                while True:
                    start = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9", max(0, start + 2))
                    if start < 0 or end < 0:
                        break
                    jpeg = bytes(buffer[start:end+2])
                    del buffer[:end+2]
                    self.put(Frame(uuid.uuid4().hex, self.episode, jpeg, time.monotonic(),
                                   camera_id="gazebo-rtp-receipt-clock"))
            raise RuntimeError("camera stream ended")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = str(exc)
            self.clear()

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()


class GazeboCamera(GStreamerCamera):
    """Length-framed JPEG stream from the native Gazebo bridge, with sensor time."""
    def __init__(self, binary, topic):
        super().__init__()
        self.binary, self.topic = binary, topic

    async def start(self):
        self.process = await asyncio.create_subprocess_exec(
            str(self.binary), self.topic, stdout=asyncio.subprocess.PIPE,
            env={**os.environ, 'GZ_IP': '127.0.0.1'})
        self.task = asyncio.create_task(self._read())

    async def _read(self):
        try:
            while True:
                size = struct.unpack("!I", await self.process.stdout.readexactly(4))[0]
                if size > 2048:
                    raise ValueError("oversized camera metadata")
                meta = json.loads(await self.process.stdout.readexactly(size))
                size = meta["bytes"]
                if not 0 < size <= 2_000_000:
                    raise ValueError("oversized camera frame")
                jpeg = await self.process.stdout.readexactly(size)
                self.put(Frame(uuid.uuid4().hex, self.episode, jpeg, time.monotonic(),
                               meta["width"], meta["height"], "gazebo-native",
                               meta["sensor_time_s"], "sensor_simulation_unmapped"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = str(exc)
            self.clear()
