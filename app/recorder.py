import json
import os
import platform
import time
import fcntl
from pathlib import Path


class StorageFull(RuntimeError):
    pass


class RunRecorder:
    """One writer, atomic evidence writes, hard project-wide byte budget.

    Never removes previous runs. Events are flushed synchronously to make failures
    inspectable. Reserve room for the final failure/summary record.
    """

    def __init__(self, root: Path, episode: str, limit: int, provenance: dict):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.used = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
        self.limit = limit
        self.directory = root / episode
        if self.used + 65536 >= limit:
            raise StorageFull("run-data budget full; select another data path or explicitly archive runs")
        self.directory.mkdir(exist_ok=False)
        self.events = self.directory / "events.jsonl"
        self.provenance = {
            "host": platform.node(), "os": platform.system(),
            "architecture": platform.machine(), **provenance,
        }
        self.record("run_started", **self.provenance)

    def _write(self, path, data, *, append=False, final=False):
        # App and evaluation runner may write concurrently. Share one advisory
        # lock and re-count actual retained evidence before each bounded write.
        with (self.root / ".budget.lock").open("a") as budget:
            fcntl.flock(budget, fcntl.LOCK_EX)
            self.used = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
            reserve = 0 if final else 32768
            if self.used + len(data) + reserve > self.limit:
                raise StorageFull("run-data budget exceeded; no evidence deleted")
            if append:
                with path.open("ab") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
            else:
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_bytes(data)
                temporary.replace(path)
            self.used += len(data)

    def record(self, kind, *, final=False, **fields):
        value = {"event": kind, "monotonic": time.monotonic(), **fields}
        self._write(self.events, (json.dumps(value, allow_nan=False) + "\n").encode(),
                    append=True, final=final)

    def image(self, frame):
        name = f"{frame.frame_id}.jpg"
        self._write(self.directory / name, frame.jpeg)
        self.record("frame", image=name, **frame.metadata())
        return name

    def finish(self, **outcome):
        value = {**self.provenance, **outcome}
        self._write(self.directory / "summary.json",
                    json.dumps(value, indent=2).encode(), final=True)
