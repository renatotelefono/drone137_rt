from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Protocol


class State(StrEnum):
    IDLE = "idle"
    MOVING = "moving"
    OBSERVING = "observing"
    PAUSED = "paused"
    LANDING = "landing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class Frame:
    frame_id: str
    episode_id: str
    jpeg: bytes
    received_monotonic: float
    width: int = 320
    height: int = 240
    camera_id: str = "unknown"
    sensor_time_s: float | None = None
    timestamp_basis: str = "host_receipt_only"

    def metadata(self):
        return {k: v for k, v in asdict(self).items() if k != "jpeg"}


@dataclass(frozen=True)
class Telemetry:
    position: tuple[float, float, float]
    speed: float
    received_monotonic: float
    healthy: bool = True
    in_air: bool = False


@dataclass(frozen=True)
class Observation:
    episode_id: str
    request_id: str
    frame: Frame
    deadline: float
    generation: int
    target: str
    view: str
    allowed_views: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    telemetry: Telemetry
    mission_state: str = "observing"

    def envelope(self, image_file):
        return {
            "episode_id": self.episode_id, "request_id": self.request_id,
            "frame": self.frame.metadata(), "image_file": image_file,
            "deadline": self.deadline, "generation": self.generation,
            "target": self.target, "view": self.view,
            "allowed_views": list(self.allowed_views),
            "allowed_actions": list(self.allowed_actions),
            "telemetry": asdict(self.telemetry), "mission_state": self.mission_state,
            "receipt_age_s": time.monotonic() - self.frame.received_monotonic,
            "capture_age_s": None,
        }


@dataclass(frozen=True)
class Decision:
    observation: str
    action: str
    target_view: str | None
    reason: str

    @classmethod
    def parse(cls, raw: str):
        if len(raw.encode()) > 4096:
            raise ValueError("oversized decision")

        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON field")
                result[key] = value
            return result

        obj = json.loads(raw, object_pairs_hook=unique_pairs)
        if not isinstance(obj, dict) or set(obj) != {
            "observation", "action", "target_view", "reason"
        }:
            raise ValueError("decision fields must match contract exactly")
        if obj["observation"] not in ("open", "closed", "uncertain"):
            raise ValueError("invalid observation")
        if obj["action"] not in ("continue", "recheck", "hold", "finish"):
            raise ValueError("invalid action")
        if not isinstance(obj["reason"], str) or len(obj["reason"]) > 300:
            raise ValueError("reason must be a string of at most 300 characters")
        if obj["target_view"] is not None and not isinstance(obj["target_view"], str):
            raise ValueError("invalid target_view")
        if obj["action"] != "recheck" and obj["target_view"] is not None:
            raise ValueError("only recheck can select a view")
        return cls(**obj)


def validate_decision(decision, observation, *, episode, request, generation, state,
                      view, telemetry, telemetry_max_age=2.0, now=None):
    now = time.monotonic() if now is None else now
    if observation.episode_id != episode or observation.frame.episode_id != episode:
        raise ValueError("wrong episode")
    if observation.request_id != request or observation.generation != generation:
        raise ValueError("superseded request")
    if now > observation.deadline:
        raise ValueError("expired decision")
    if state != State.OBSERVING or view != observation.view:
        raise ValueError("vehicle is no longer observing this view")
    if not telemetry.healthy or now - telemetry.received_monotonic > telemetry_max_age:
        raise ValueError("position estimate unavailable")
    if decision.action not in observation.allowed_actions:
        raise ValueError("action unavailable")
    if decision.action == "recheck" and decision.target_view not in observation.allowed_views:
        raise ValueError("view unavailable")


def enu_to_global(position, home):
    """Small local ENU frame to WGS84 approximation; altitude is AMSL.

    Intended for this <20 m scene, not long-range navigation.
    home = (latitude degrees, longitude degrees, AMSL metres).
    """
    east, north, up = position
    lat, lon, amsl = home
    if not all(math.isfinite(x) for x in (*position, *home)) or abs(lat) > 85:
        raise ValueError("invalid local origin/position")
    radius = 6378137.0
    return (
        lat + math.degrees(north / radius),
        lon + math.degrees(east / (radius * math.cos(math.radians(lat)))),
        amsl + up,
    )


def validate_mission(config):
    if config.get("physical_enabled") is not False:
        raise ValueError("physical operation is disabled")
    positive = ("frame_max_age_s", "inference_timeout_s", "hold_timeout_s",
                "mission_timeout_s", "telemetry_max_age_s", "command_timeout_s",
                "horizontal_tolerance_m", "vertical_tolerance_m", "settle_speed_m_s",
                "settle_duration_s", "speed_limit_m_s", "run_data_limit_bytes")
    for key in positive:
        if not isinstance(config.get(key), (float, int)) or not math.isfinite(config[key]) or config[key] <= 0:
            raise ValueError(f"invalid positive mission limit: {key}")
    points = config["waypoints"]
    if "pad" not in points:
        raise ValueError("pad waypoint required")
    for name, position in points.items():
        if len(position) != 3 or not all(math.isfinite(n) for n in position):
            raise ValueError(f"invalid waypoint: {name}")
        if not all(config["volume"][axis][0] <= n <= config["volume"][axis][1]
                   for axis, n in zip(("x", "y", "z"), position)):
            raise ValueError(f"waypoint outside flight volume: {name}")
    graph = {name: set() for name in points}
    for a, b in config["edges"]:
        if a not in points or b not in points or a == b:
            raise ValueError("invalid route edge")
        graph[a].add(b)
        graph[b].add(a)
    reachable = {"pad"}
    for _ in points:
        reachable |= set().union(*(graph[n] for n in reachable))
    if reachable != set(points):
        raise ValueError("route has unreachable waypoints")
    for target in config["targets"]:
        if not 1 <= len(target["views"]) <= 2 or any(v not in points for v in target["views"]):
            raise ValueError("target must have one primary and at most one alternative view")


class DroneAdapter(Protocol):
    async def connect(self): ...
    def telemetry(self) -> Telemetry: ...
    async def takeoff(self, height: float): ...
    async def goto(self, position: tuple, yaw: float): ...
    async def hold(self): ...
    async def land(self): ...
    async def close(self): ...


class FrameSource(Protocol):
    def begin_episode(self, episode: str): ...
    async def start(self): ...
    def latest(self) -> Frame | None: ...
    async def close(self): ...


class InferenceBackend(Protocol):
    async def infer(self, observation: Observation) -> str: ...
    async def close(self): ...
