import argparse
import hashlib
import gzip
import importlib.metadata
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("DRONE137_DATA_DIR", ROOT / ".local/data")).resolve()
BUILD = Path(os.environ.get("DRONE137_BUILD_DIR", ROOT / ".local/build")).resolve()
GIB = 1024**3


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def existing_parent(path):
    while not path.exists():
        path = path.parent
    return path


def space_guard(path, peak_gib, reserve_gib=10):
    paths = [Path("/"), existing_parent(path)]
    for target in paths:
        free = shutil.disk_usage(target).free
        required = reserve_gib * GIB + (peak_gib * GIB if target == paths[1] else 0)
        if free < required:
            raise RuntimeError(f"{target}: {free/GIB:.1f} GiB free, {required/GIB:.1f} GiB required "
                               f"(planning estimate including {reserve_gib} GiB reserve)")


def native_mac():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("Native stages currently target Apple Silicon macOS; Intel needs separate validation")


def run(argv, **kwargs):
    subprocess.run([str(x) for x in argv], check=True, **kwargs)


def pinned_checkout(component, destination):
    version = json.loads((ROOT / "docs/versions.json").read_text())[component]
    if not destination.exists():
        run(["git", "clone", "--no-checkout", version["repository"], destination])
        run(["git", "-C", destination, "checkout", "--detach", version["commit"]])
    actual = subprocess.check_output(["git", "-C", str(destination), "rev-parse", "HEAD"], text=True).strip()
    if actual != version["commit"]:
        raise RuntimeError(f"{destination}: existing checkout differs from pin; choose another build directory")
    if subprocess.check_output(["git", "-C", str(destination), "status", "--porcelain"], text=True):
        raise RuntimeError(f"{destination}: preserve local changes before reusing this build")


def installed_record(name, path):
    directory = DATA / "installed"
    directory.mkdir(parents=True, exist_ok=True)
    record = {
        "host": platform.node(), "architecture": platform.machine(),
        "os": platform.platform(), "created": time.time(), "path": str(path),
        "size_bytes": sum(p.stat().st_size for p in path.rglob("*") if p.is_file()),
        "versions": json.loads((ROOT / "docs/versions.json").read_text()),
        "acceptance": "unverified",
    }
    if (path / ".git").exists():
        record["submodules"] = subprocess.check_output(
            ["git", "-C", str(path), "submodule", "status", "--recursive"], text=True)
    (directory / f"{name}.json").write_text(json.dumps(record, indent=2))


def install_runtime():
    native_mac()
    space_guard(BUILD, 4)
    for command in ("git", "cmake", "clang"):
        if not shutil.which(command):
            raise RuntimeError(f"Missing {command}; install native Xcode command-line tools/CMake first")
    BUILD.mkdir(parents=True, exist_ok=True)
    path = BUILD / "llama.cpp"
    pinned_checkout("llama_cpp", path)
    run(["cmake", "-S", path, "-B", path / "build", "-DGGML_METAL=ON", "-DLLAMA_CURL=OFF"])
    run(["cmake", "--build", path / "build", "--config", "Release", "--target", "llama-server", "-j", "2"])
    run([path / "build/bin/llama-server", "--version"])
    installed_record("llama", path)


def install_sim():
    native_mac()
    space_guard(BUILD, 25)
    for command in ('pixi', 'pkg-config', 'cmake', 'ninja'):
        if not shutil.which(command):
            raise RuntimeError(f'Missing {command}; install Pixi, pkgconf, CMake and Ninja before native simulation')
    BUILD.mkdir(parents=True, exist_ok=True)
    path = BUILD / "PX4-Autopilot"
    pinned_checkout("px4", path)
    # Fetch the selected simulator assets. PX4's CMake targets initialize their
    # own pinned build submodules; unrelated hardware/legacy simulators are not needed.
    run(['git', '-C', path, 'submodule', 'update', '--init', '--recursive', 'Tools/simulation/gz'])
    run(['pixi', 'install', '--locked', '--manifest-path', path/'Tools/setup/macos/pixi.toml'])
    if not (path/'.venv/bin/python').is_file():
        run([sys.executable, '-m', 'venv', path/'.venv'])
    run([path/'.venv/bin/python', '-m', 'pip', 'install', '-r', path/'Tools/setup/requirements.txt'])
    run([sys.executable, "-m", "pip", "install", "--require-hashes", "-r", ROOT / "requirements-sim.lock"])
    # No simulator launch or system-wide compiler linking during installation.
    environment = ROOT/'scripts/with-sim.sh'
    target = path/'build/px4_sitl_default'
    run([environment, 'cmake', '-S', path, '-B', target, '-G', 'Ninja', '-DCONFIG=px4_sitl_default'])
    run([environment, 'cmake', '--build', target, '-j', '2'])
    run([environment, 'cmake', '-S', ROOT/'sim/bridge', '-B', BUILD/'image-bridge'])
    run([environment, 'cmake', '--build', BUILD/'image-bridge', '-j', '2'])
    run([sys.executable, "-m", "sim.prepare", "--px4", path])
    installed_record("px4", path)


def download_model():
    from app.model_store import ModelStore
    store = ModelStore(DATA / "models")
    store.download()
    installed_record("model", DATA / "models")
    print("Verified model and projector installed")


def doctor(profile):
    report = {"host": platform.node(), "architecture": platform.machine(),
              "os": platform.platform(), "profile": profile, "python": platform.python_version(),
              "paths": {str(p): shutil.disk_usage(existing_parent(p)).free
                        for p in (Path("/"), DATA, BUILD)},
              "dependencies": {}, "ports_in_use": {}, "native": {},
              "camera_and_control": "not proven by diagnostics; run the native integration checks",
              "acceptance": "unverified"}
    for package in ("aiohttp", "mavsdk"):
        try:
            report["dependencies"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report["dependencies"][package] = None
    for port in (8137, 8081, 50051):
        with socket.socket() as sock:
            sock.settimeout(.1)
            report["ports_in_use"][port] = sock.connect_ex(("127.0.0.1", port)) == 0
    for name, path in {
        "llama": BUILD / "llama.cpp/build/bin/llama-server",
        "px4": BUILD / "PX4-Autopilot/build/px4_sitl_default/bin/px4",
        "camera_bridge": BUILD / "image-bridge/drone137-image-bridge",
    }.items():
        report["native"][name] = subprocess.check_output(["file", str(path)], text=True).strip() if path.exists() else "missing"
    report["model_manifest_present"] = (DATA / "models/manifest.json").exists()
    print(json.dumps(report, indent=2))
    return report


def export():
    # Explicit source allowlist; don't accidentally package credentials, models or venvs.
    selected = ["Start drone137.command", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", ".gitignore", "pyproject.toml",
                "uv.lock", "requirements.lock", "requirements-sim.lock",
                "app", "adapters", "config", "scripts", "schemas", "sim", "tests", "docs", "hardware"]
    files = []
    for name in selected:
        path = ROOT / name
        if not path.exists():
            raise RuntimeError(f"Missing source handoff input: {name}")
        files.extend([path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file()
                                                        and "__pycache__" not in p.parts and p.suffix != ".pyc"))
    for path in files:
        if path.is_symlink() or ROOT not in path.resolve().parents:
            raise RuntimeError(f"Refusing symlink or outside source: {path}")
    manifest = {str(p.relative_to(ROOT)): digest(p) for p in files}
    target = ROOT / "dist"
    target.mkdir(exist_ok=True)
    archive = target / "drone137-source.tar.gz"
    with archive.open("wb") as output, gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as tar:
            for path in files:
                info = tar.gettarinfo(str(path), arcname="drone137/" + str(path.relative_to(ROOT)))
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                with path.open("rb") as source:
                    tar.addfile(info, source)
    if archive.stat().st_size >= 250*1024*1024:
        raise RuntimeError("Source package exceeds 250 MB target")
    checksum = digest(archive)
    (target / "drone137-source.tar.gz.sha256").write_text(f"{checksum}  {archive.name}\n")
    (target / "source-manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"archive": str(archive.relative_to(ROOT)), "sha256": checksum,
                      "bytes": archive.stat().st_size, "files": len(files)}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["doctor", "export", "install-runtime", "install-sim", "download-model"])
    parser.add_argument("--profile", choices=["lean-8gb", "cloud-dev"], default="lean-8gb")
    args = parser.parse_args()
    operations = {"doctor": lambda: doctor(args.profile), "export": export,
                  "install-runtime": install_runtime, "install-sim": install_sim,
                  "download-model": download_model}
    try:
        operations[args.command]()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
