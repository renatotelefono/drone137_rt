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
from app.portability import IS_WINDOWS, install_stop_handlers, kill_tree, spawn_kwargs, terminate_tree

SOCKET = ROOT / ".local/control.sock"
PORT_FILE = ROOT / ".local/control.port"     # Windows has no Unix sockets: the launcher listens on a loopback port it writes here


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
            terminate_tree(owned["mavsdk"])


async def control_server(handler):
    """The launcher's stop channel: a Unix socket where there is one, a loopback TCP port on Windows."""
    if IS_WINDOWS:
        server = await asyncio.start_server(handler, '127.0.0.1', 0)
        PORT_FILE.write_text(str(server.sockets[0].getsockname()[1]))
        return server
    server = await asyncio.start_unix_server(handler, path=SOCKET)
    os.chmod(SOCKET, 0o600)
    return server


async def control_connect():
    if IS_WINDOWS:
        if not PORT_FILE.exists():
            raise RuntimeError("No running launcher: control port file missing")
        return await asyncio.open_connection('127.0.0.1', int(PORT_FILE.read_text()))
    return await asyncio.open_unix_connection(path=SOCKET)


def control_present():
    return PORT_FILE.exists() if IS_WINDOWS else SOCKET.exists()


def control_remove():
    (PORT_FILE if IS_WINDOWS else SOCKET).unlink(missing_ok=True)


async def launch(args):
    SOCKET.parent.mkdir(exist_ok=True)
    if control_present():
        raise RuntimeError("Control socket already exists. Stop the existing launcher; inspect a stale socket before removal.")
    stopping = asyncio.Event()

    async def control(reader, writer):
        data = await reader.read(16)
        if data == b"stop":
            stopping.set()
        writer.close()
        await writer.wait_closed()

    server = await control_server(control)
    registry = ROOT / ".local" / f"owned-{uuid.uuid4().hex}.json"
    environment = dict(os.environ, DRONE137_OWNERSHIP_FILE=str(registry))
    process = None
    monitor_task = None
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.server", *args, env=environment,
            cwd=ROOT, **spawn_kwargs())
        loop = asyncio.get_running_loop()
        install_stop_handlers(loop, stopping.set)
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
            if IS_WINDOWS:
                process.terminate()
            else:
                process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(asyncio.shield(exit_task), 45)
            except TimeoutError:
                kill_tree(process.pid)
                await exit_task
        stop_task.cancel()
        await asyncio.gather(stop_task, return_exceptions=True)
    finally:
        if monitor_task:
            monitor_task.cancel()
            await asyncio.gather(monitor_task, return_exceptions=True)
        if process:
            # Camera bridge shares the app's process group.
            terminate_tree(process.pid)
        # If app exited before cleanup, terminate its native groups. Keep the
        # simulator alive briefly after stopping SDK to permit recovery observation.
        if registry.exists():
            owned = json.loads(registry.read_text())
            for name in sorted(owned, key=lambda n: n != "mavsdk"):
                terminate_tree(owned[name])
                if name == "mavsdk":
                    print("App exited: SDK disconnected; leaving simulation alive for 5s. Recovery is NOT validated.", flush=True)
                    await asyncio.sleep(5)
                kill_tree(owned[name])
            registry.unlink()
        server.close()
        await server.wait_closed()
        control_remove()
    return process.returncode if process else 1


async def stop():
    reader, writer = await control_connect()
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
