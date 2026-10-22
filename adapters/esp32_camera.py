"""Bounded HTTP JPEG camera source for ESP32 bench bring-up.

This is a FrameSource, not a vehicle adapter. Device capture timestamps are
retained but are never compared with the host clock without clock mapping.
"""
import asyncio
import ipaddress
import math
import time
import uuid
from urllib.parse import urlsplit

import aiohttp

from adapters.fixtures import LatestFrameBuffer
from app.contracts import Frame


def jpeg_dimensions(data):
    """Read baseline/progressive JPEG geometry without decoding a pixel array."""
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise ValueError("incomplete JPEG")
    pos = 2
    while pos + 3 < len(data):
        if data[pos] != 255:
            raise ValueError("invalid JPEG marker")
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos >= len(data):
            break
        marker = data[pos]
        pos += 1
        if marker in (0xd9, 0xda):
            break
        size = int.from_bytes(data[pos:pos+2], "big")
        if size < 2 or pos + size > len(data):
            raise ValueError("invalid JPEG segment")
        if marker in (0xc0, 0xc2):
            if size < 8:
                raise ValueError("invalid JPEG geometry")
            height = int.from_bytes(data[pos+3:pos+5], "big")
            width = int.from_bytes(data[pos+5:pos+7], "big")
            if not 1 <= width <= 1280 or not 1 <= height <= 960:
                raise ValueError("camera geometry exceeds 1280 x 960 limit")
            return width, height
        pos += size
    raise ValueError("JPEG has no supported frame header")


def camera_url(value):
    url = urlsplit(value)
    try:
        host = ipaddress.ip_address(url.hostname or "")
        valid = host.is_loopback or host in ipaddress.ip_network("10.0.0.0/8") or host in ipaddress.ip_network("172.16.0.0/12") or host in ipaddress.ip_network("192.168.0.0/16")
        port = url.port
    except ValueError:
        valid = False
    if (not valid or url.scheme != "http" or url.username or url.password
            or url.query or url.fragment or url.path != "/capture"):
        raise ValueError("camera URL must be a literal loopback/private IPv4 HTTP /capture endpoint")
    return value


class Esp32Camera(LatestFrameBuffer):
    def __init__(self, url, *, fps=5, timeout=2, stale_after=1,
                 require_metadata=True):
        super().__init__()
        self.url = camera_url(url)
        for value in (fps, timeout, stale_after):
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("camera timing values must be positive and finite")
        if fps > 10:
            raise ValueError("camera sampling is limited to 10 fps")
        self.interval, self.timeout, self.stale_after = 1/fps, timeout, stale_after
        self.require_metadata = require_metadata
        self.episode = ""
        self.session = self.task = None
        self.error = None
        self.frames_received = self.errors = 0
        self.last_identity = None
        self.last_capture = None
        self.last_request_s = None

    def begin_episode(self, episode):
        self.episode = episode
        self.clear()

    def latest(self):
        frame = super().latest()
        if frame and time.monotonic() - frame.received_monotonic <= self.stale_after:
            return frame
        return None

    async def start(self):
        if self.task:
            raise RuntimeError("camera is already started")
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout), trust_env=False,
            auto_decompress=False, read_bufsize=16384)
        self.task = asyncio.create_task(self._read())

    async def _capture(self):
        episode = self.episode
        started = time.monotonic()
        async with self.session.get(self.url, allow_redirects=False,
                                    headers={"Cache-Control":"no-cache"}) as response:
            if response.status != 200 or response.content_type != "image/jpeg":
                raise ValueError("camera must return HTTP 200 image/jpeg")
            if response.content_length is not None and response.content_length > 200_000:
                raise ValueError("camera JPEG exceeds model's 200 KB bound")
            data = bytearray()
            async for chunk in response.content.iter_chunked(8192):
                data.extend(chunk)
                if len(data) > 200_000:
                    raise ValueError("camera JPEG exceeds model's 200 KB bound")
            jpeg = bytes(data)
            width, height = jpeg_dimensions(jpeg)
            headers = response.headers
            boot, sequence, captured = (headers.get(key) for key in
                                       ("X-Boot-Id", "X-Frame-Id", "X-Capture-Time-Us"))
            sensor_time = None
            identity = None
            if any(x is not None for x in (boot, sequence, captured)) or self.require_metadata:
                if not boot or len(boot) > 32 or not boot.isalnum():
                    raise ValueError("missing/invalid camera boot identity")
                if not sequence or not sequence.isdecimal() or len(sequence) > 20:
                    raise ValueError("missing/invalid camera frame identity")
                if not captured or not captured.isdecimal() or len(captured) > 20:
                    raise ValueError("missing/invalid camera capture clock")
                identity = (boot, int(sequence))
                sensor_time = int(captured)/1_000_000
                if self.last_identity and self.last_identity[0] == boot:
                    if identity[1] <= self.last_identity[1] or sensor_time <= self.last_capture:
                        raise ValueError("repeated or out-of-order camera frame")
                if headers.get("X-Width") != str(width) or headers.get("X-Height") != str(height):
                    raise ValueError("JPEG and camera metadata dimensions disagree")
            self.last_request_s = time.monotonic() - started
            self.last_identity, self.last_capture = identity, sensor_time
            if self.episode != episode:
                return  # never retag an old request as a new episode
            self.put(Frame(uuid.uuid4().hex, episode, jpeg, time.monotonic(), width, height,
                           "esp32-http-camera", sensor_time,
                           "device_monotonic_unmapped" if sensor_time is not None else "host_receipt_only"))
            self.frames_received += 1
            self.error = None

    async def _read(self):
        while True:
            started = time.monotonic()
            try:
                await self._capture()
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
                self.errors += 1
                self.error = str(exc)
                self.clear()
            await asyncio.sleep(max(.01, self.interval - (time.monotonic()-started)))

    def status(self):
        frame = self.latest()
        return {"camera_id":"esp32-http-camera", "frames_received":self.frames_received,
                "errors":self.errors, "error":self.error, "live":frame is not None,
                "request_duration_s":self.last_request_s,
                "receipt_age_s":None if frame is None else time.monotonic()-frame.received_monotonic,
                "capture_age_s":None, "clock_mapping_verified":False,
                "frame":None if frame is None else frame.metadata()}

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        if self.session:
            await self.session.close()
            self.session = None
        self.clear()
