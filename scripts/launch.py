"""Separate parent watchdog: owns app lifetime and cleans native process groups."""
import asyncio
import json
import os
import signal
import sys
import uuid
from pathlib import Path
import aiohttp
import argparse

from scripts.tools import ROOT

SOCKET = ROOT / ".local/control.sock"


async def monitor_app(port, stopping, startup_timeout=180, health_timeout=3):
    """Independent parent heartbeat. No response after startup is a failure."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + startup_timeout
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1), trust_env=False) as client:
        while not stopping.is_set():
            try:
                async with client.get(f"http://127.0.0.1:{port}/api/status") as response:
                    response.raise_for_status()
                    body = await response.json()
                    if "state" not in body:
                        raise ValueError("invalid app heartbeat")
                deadline = loop.time() + health_timeout
            except (aiohttp.ClientError, TimeoutError, ValueError):
                if loop.time() >= deadline:
                    print("Application heartbeat expired; disconnecting owned SDK.", flush=True)
                    return False
            await asyncio.sleep(.25)
    return True


def disconnect_sdk(registry):
    if registry.exists():
        owned = json.loads(registry.read_text())
        if "mavsdk" in owned:
            try:
                os.killpg(owned["mavsdk"], signal.SIGTERM)
            except ProcessLookupError:
                pass


async def launch(args):
    SOCKET.parent.mkdir(exist_ok=True)
    if SOCKET.exists():
        raise RuntimeError("Control socket already exists. Stop the existing launcher; inspect a stale socket before removal.")
    stopping = asyncio.Event()

    async def control(reader, writer):
        data = await reader.read(16)
        if data == b"stop":
            stopping.set()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_unix_server(control, path=SOCKET)
    os.chmod(SOCKET, 0o600)
    registry = ROOT / ".local" / f"owned-{uuid.uuid4().hex}.json"
    environment = dict(os.environ, DRONE137_OWNERSHIP_FILE=str(registry))
    process = None
    monitor_task = None
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.server", *args, env=environment,
            cwd=ROOT, start_new_session=True)
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stopping.set)
        exit_task = asyncio.create_task(process.wait())
        stop_task = asyncio.create_task(stopping.wait())
        parser=argparse.ArgumentParser(add_help=False)
        parser.add_argument("--port",type=int,default=8137)
        port=parser.parse_known_args(args)[0].port
        monitor_task = asyncio.create_task(monitor_app(port, stopping))
        done, _ = await asyncio.wait([exit_task, stop_task, monitor_task], return_when=asyncio.FIRST_COMPLETED)
        if exit_task in done or (monitor_task in done and not monitor_task.result()):
            disconnect_sdk(registry)
        if process.returncode is None:
            process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(asyncio.shield(exit_task), 45)
            except TimeoutError:
                os.killpg(process.pid, signal.SIGKILL)
                await exit_task
        stop_task.cancel()
        await asyncio.gather(stop_task, return_exceptions=True)
    finally:
        if monitor_task:
            monitor_task.cancel()
            await asyncio.gather(monitor_task, return_exceptions=True)
        if process:
            # Camera bridge shares the app's process group.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        # If app exited before cleanup, terminate its native groups. Keep the
        # simulator alive briefly after stopping SDK to permit recovery observation.
        if registry.exists():
            owned = json.loads(registry.read_text())
            for name in sorted(owned, key=lambda n: n != "mavsdk"):
                try:
                    os.killpg(owned[name], signal.SIGTERM)
                except ProcessLookupError:
                    continue
                if name == "mavsdk":
                    print("App exited: SDK disconnected; leaving simulation alive for 5s. Recovery is NOT validated.", flush=True)
                    await asyncio.sleep(5)
                try:
                    os.killpg(owned[name], signal.SIGKILL)
                except ProcessLookupError:
                    pass
            registry.unlink()
        server.close()
        await server.wait_closed()
        SOCKET.unlink(missing_ok=True)
    return process.returncode if process else 1


async def stop():
    reader, writer = await asyncio.open_unix_connection(SOCKET)
    writer.write(b"stop")
    await writer.drain()
    writer.close()
    await writer.wait_closed()


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--stop"]:
            asyncio.run(stop())
        else:
            raise SystemExit(asyncio.run(launch(sys.argv[1:])))
    except (RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
