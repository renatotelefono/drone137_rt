"""What differs between macOS, Linux and Windows, in one place: process groups, stop signals, the browser, the runtime binary.

Everything else in the service is plain Python, Node and OpenCV and runs the same on all three. This module is where a
platform question is answered once; the callers never test the platform themselves.
"""
import asyncio
import os
import platform
import shutil
import signal
import subprocess
import sys
from pathlib import Path

SYSTEM = platform.system()           # 'Darwin', 'Linux', 'Windows'
IS_WINDOWS = SYSTEM == 'Windows'
IS_MAC = SYSTEM == 'Darwin'
IS_APPLE_SILICON = IS_MAC and platform.machine() == 'arm64'


def spawn_kwargs():
    """How to start an owned native process so that it and its children can be stopped as one."""
    if IS_WINDOWS:
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}


def _tree(pid):
    import psutil
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return []
    return [*root.children(recursive=True), root]


def terminate_tree(pid):
    """Ask a process and everything it spawned to stop (SIGTERM on POSIX groups, terminate() on Windows trees)."""
    if IS_WINDOWS:
        for p in _tree(pid):
            try:
                p.terminate()
            except Exception:
                pass
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def kill_tree(pid):
    """Stop a process and everything it spawned without asking."""
    if IS_WINDOWS:
        for p in _tree(pid):
            try:
                p.kill()
            except Exception:
                pass
        return
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def install_stop_handlers(loop, callback):
    """Run callback on Ctrl-C or a termination request; the asyncio handlers where the loop supports them, signal.signal elsewhere."""
    signals = [signal.SIGINT, signal.SIGTERM] + ([signal.SIGBREAK] if hasattr(signal, 'SIGBREAK') else [])
    for sig in signals:
        try:
            loop.add_signal_handler(sig, callback)
        except (NotImplementedError, RuntimeError, ValueError):
            try:
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(callback))
            except (ValueError, OSError):
                pass


def browser_candidates(system=None):
    """Where a Chromium-family browser usually is, by platform; CHROMIUM_PATH overrides all of them."""
    system = system or SYSTEM
    if system == 'Darwin':
        return ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium',
                '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge']
    if system == 'Windows':
        roots = [os.environ.get('ProgramFiles', r'C:\Program Files'), os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
                 os.path.join(os.environ.get('LocalAppData', r'C:\Users\Default\AppData\Local'))]
        out = []
        for root in roots:
            out += [os.path.join(root, r'Google\Chrome\Application\chrome.exe'), os.path.join(root, r'Microsoft\Edge\Application\msedge.exe'),
                    os.path.join(root, r'Chromium\Application\chrome.exe')]
        return out
    return ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/snap/bin/chromium']


def browser_executable():
    override = os.environ.get('CHROMIUM_PATH')
    if override:
        return override
    for candidate in browser_candidates():
        if Path(candidate).is_file():
            return candidate
    for name in ('google-chrome', 'chromium', 'chromium-browser', 'msedge'):
        found = shutil.which(name)
        if found:
            return found
    return None


def runtime_binary(build_root):
    """Where the installed llama-server is: built from source on macOS and Linux, unpacked from a pinned release on Windows."""
    build_root = Path(build_root)
    if IS_WINDOWS:
        return build_root/'llama.cpp/bin/llama-server.exe'
    return build_root/'llama.cpp/build/bin/llama-server'


def python_in_venv(root):
    root = Path(root)
    return root/'.venv/Scripts/python.exe' if IS_WINDOWS else root/'.venv/bin/python'
