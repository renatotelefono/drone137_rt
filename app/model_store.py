"""Verified, resumable installation of the single supported vision model."""
import fcntl
from contextlib import contextmanager
import hashlib
import json
import re
import shutil
import threading
import urllib.request
import urllib.error
from pathlib import Path

REPOSITORY = "Qwen/Qwen3-VL-2B-Instruct-GGUF"
FILES = ("Qwen3VL-2B-Instruct-Q4_K_M.gguf", "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf")


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def validate_manifest(manifest):
    if manifest.get("repository") != REPOSITORY:
        raise ValueError("Unexpected model repository")
    if not re.fullmatch(r"[0-9a-f]{40,64}", str(manifest.get("revision", ""))):
        raise ValueError("An immutable model revision is required")
    items = manifest.get("files", [])
    if [item.get("name") for item in items] != list(FILES):
        raise ValueError("Model manifest must contain exactly the supported model/projector pair")
    for item in items:
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
            raise ValueError("Official SHA256 is required")
        if type(item.get("size")) is not int or not 0 < item["size"] <= 4*1024**3:
            raise ValueError("Invalid model file size")
    return manifest


class ModelStore:
    def __init__(self, directory, *, base_url="https://huggingface.co", reserve_bytes=10*1024**3):
        self.directory = Path(directory)
        self.base_url = base_url.rstrip("/")
        self.reserve = reserve_bytes
        self.cancel = threading.Event()
        self.progress = {"stage": "idle", "file": None, "downloaded": 0, "total": 0}
        self.verified = False

    @property
    def manifest_path(self):
        return self.directory / "manifest.json"

    def manifest(self):
        return validate_manifest(json.loads(self.manifest_path.read_text()))

    def status(self):
        sizes = {}
        for name in FILES:
            path = self.directory / name
            sizes[name] = path.stat().st_size if path.is_file() else 0
        return {"repository": REPOSITORY, "files": sizes, "verified_this_session": self.verified,
                "manifest_present": self.manifest_path.exists(), **self.progress}

    def _open(self, url, headers=None):
        return urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=30)

    def resolve(self):
        if self.manifest_path.exists():
            return self.manifest()
        self.progress["stage"] = "resolving official metadata"
        with self._open(f"{self.base_url}/api/models/{REPOSITORY}?blobs=true") as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("Oversized model metadata")
        metadata = json.loads(data)
        siblings = {item["rfilename"]: item for item in metadata["siblings"]}
        items = []
        for name in FILES:
            lfs = siblings[name]["lfs"]
            items.append({"name": name, "sha256": lfs["sha256"], "size": lfs["size"]})
        manifest = validate_manifest({"repository": REPOSITORY, "revision": metadata["sha"], "files": items})
        atomic_json(self.manifest_path, manifest)
        return manifest

    def _check_space(self, required):
        parent = self.directory
        while not parent.exists():
            parent = parent.parent
        for path, allowance in ((Path("/"), self.reserve), (parent, self.reserve + required)):
            if shutil.disk_usage(path).free < allowance:
                raise RuntimeError(f"Insufficient free space at {path}; preserve 10 GiB reserve plus remaining download")

    def verify(self):
        self.verified = False
        manifest = self.manifest()
        for item in manifest["files"]:
            self.progress.update(stage="verifying SHA256", file=item["name"])
            path = self.directory / item["name"]
            if not path.is_file() or path.stat().st_size != item["size"] or sha256(path) != item["sha256"]:
                raise RuntimeError(f"Missing or corrupt model file: {item['name']}")
        if not (self.directory / "LICENSE").is_file():
            raise RuntimeError("Model licence missing; run Download / resume")
        provenance = self.directory/'license-source.json'
        if provenance.exists():
            source = json.loads(provenance.read_text())
            if source.get('revision') != manifest['revision'] or source.get('sha256') != sha256(self.directory/'LICENSE'):
                raise RuntimeError('Model licence provenance or checksum mismatch')
        self.verified = True
        self.progress.update(stage="verified", file=None)
        return [self.directory / name for name in FILES]

    @contextmanager
    def lock(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / ".install.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("Another model installation is running") from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def download(self):
        with self.lock():
            return self._download()

    def _download(self):
        self.cancel.clear()
        self.verified = False
        self.directory.mkdir(parents=True, exist_ok=True)
        manifest = self.resolve()
        remaining = sum(max(0, item["size"] - min(item["size"],
                        (self.directory / (item["name"] + ".part")).stat().st_size))
                        if (self.directory / (item["name"] + ".part")).exists()
                        else (0 if (self.directory/item["name"]).exists() else item["size"])
                        for item in manifest["files"])
        self._check_space(remaining + 1024**2)
        for item in manifest["files"]:
            target = self.directory / item["name"]
            if target.exists():
                if target.stat().st_size == item["size"] and sha256(target) == item["sha256"]:
                    continue
                raise RuntimeError(f"Existing file failed verification: {target.name}. Preserve/inspect it before replacement.")
            partial = self.directory / (item["name"] + ".part")
            offset = partial.stat().st_size if partial.exists() else 0
            if offset > item["size"]:
                raise RuntimeError("Partial download is oversized; explicitly reset partial downloads")
            if offset < item["size"]:
                self.progress.update(stage="downloading", file=item["name"], downloaded=offset, total=item["size"])
                url = f"{self.base_url}/{REPOSITORY}/resolve/{manifest['revision']}/{item['name']}"
                with self._open(url, {"Range": f"bytes={offset}-"} if offset else {}) as response:
                    if response.status == 206:
                        expected = f"bytes {offset}-{item['size']-1}/{item['size']}"
                        if response.headers.get("Content-Range") != expected:
                            raise RuntimeError("Server returned an inconsistent resume range")
                        mode = "ab" if offset else "wb"
                    elif response.status == 200:
                        mode, offset = "wb", 0
                    else:
                        raise RuntimeError(f"Unexpected download status {response.status}")
                    with partial.open(mode) as output:
                        while True:
                            if self.cancel.is_set():
                                self.progress["stage"] = "cancelled; partial retained"
                                return
                            chunk = response.read(1024*1024)
                            if not chunk:
                                break
                            if offset + len(chunk) > item["size"]:
                                raise RuntimeError("Download exceeds the official file size")
                            output.write(chunk)
                            offset += len(chunk)
                            self.progress["downloaded"] = offset
            self.progress["stage"] = "verifying SHA256"
            if partial.stat().st_size != item["size"] or sha256(partial) != item["sha256"]:
                raise RuntimeError("Partial file failed SHA256/size verification; reset partials before retrying")
            partial.replace(target)
        licence = self.directory / "LICENSE"
        if not licence.exists():
            url = f"{self.base_url}/{REPOSITORY}/resolve/{manifest['revision']}/LICENSE"
            source = {'revision': manifest['revision'], 'source': url}
            try:
                with self._open(url) as response:
                    content = response.read(100_001)
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                # Official GGUF repos may declare an SPDX licence in their model
                # card without shipping a LICENSE. Check the pinned revision,
                # never infer a licence from a different model or a moving branch.
                url = f"{self.base_url}/api/models/{REPOSITORY}/revision/{manifest['revision']}"
                with self._open(url) as response:
                    metadata = json.loads(response.read(2_000_001))
                if metadata.get('sha') != manifest['revision'] or metadata.get('cardData', {}).get('license') != 'apache-2.0':
                    raise RuntimeError('Missing LICENSE and no pinned Apache-2.0 model-card declaration')
                content = (Path(__file__).resolve().parents[1]/'LICENSE').read_bytes()
                source.update(source=url, declaration='apache-2.0', text_source='bundled standard Apache-2.0 text')
            if not 100 <= len(content) <= 100_000:
                raise RuntimeError("Unexpected model licence response")
            temporary = licence.with_suffix(".tmp")
            temporary.write_bytes(content)
            temporary.replace(licence)
            atomic_json(self.directory/'license-source.json', {**source, 'sha256': hashlib.sha256(content).hexdigest()})
        return self.verify()

    def reset_partials(self):
        """Explicit user action; preserves installed files and the pinned manifest."""
        with self.lock():
            for name in FILES:
                (self.directory / (name + ".part")).unlink(missing_ok=True)
        self.progress.update(stage="idle", file=None, downloaded=0, total=0)
