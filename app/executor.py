import asyncio
import math
import time
import uuid
from collections import deque
from dataclasses import asdict

from app.contracts import Decision, Observation, State, validate_decision, validate_mission
from app.recorder import RunRecorder


class MissionExecutor:
    """Sole command owner; independent telemetry supervision and operator priority."""
    def __init__(self, drone, camera, policy, config, runs, provenance, *, process_health=lambda: True):
        validate_mission(config)
        self.drone, self.camera, self.policy = drone, camera, policy
        self.config, self.runs, self.provenance = config, runs, provenance
        self.process_health = process_health
        self.state = State.IDLE
        self.view = "pad"
        self.episode = self.request = ""
        self.generation = 0
        self.task = self.supervisor = None
        self.recorder = None
        self.last_decision = None
        self.error = None
        self.operator_lock = asyncio.Lock()
        self.command_lock = asyncio.Lock()

    def snapshot(self):
        return {
            "state": self.state, "view": self.view, "episode": self.episode,
            "telemetry": asdict(self.drone.telemetry()), "decision": self.last_decision,
            "error": self.error, **self.provenance,
            "report": f"/reports/{self.episode}/summary.json" if self.episode else None,
        }

    def _event(self, kind, **fields):
        if self.recorder:
            self.recorder.record(kind, **fields)

    def _healthy(self):
        t = self.drone.telemetry()
        coordinates_ok = all(math.isfinite(x) for x in (*t.position, t.speed))
        volume = self.config["volume"]
        within = all(volume[k][0] - .2 <= v <= volume[k][1] + .2
                     for k, v in zip(("x", "y", "z"), t.position))
        return (coordinates_ok and within and t.healthy and
                time.monotonic() - t.received_monotonic <= self.config["telemetry_max_age_s"]
                and self.process_health())

    async def start(self):
        async with self.operator_lock:
            if self.state not in (State.IDLE, State.COMPLETE):
                raise ValueError("start requires idle/completed state; restart app after a failure")
            if not self._healthy() or self.drone.telemetry().in_air:
                raise ValueError("vehicle not ready")
            if math.dist(self.drone.telemetry().position, (0, 0, 0)) > .5:
                raise ValueError("start requires vehicle on the configured pad")
            self.episode = uuid.uuid4().hex
            self.camera.begin_episode(self.episode)
            self.recorder = RunRecorder(self.runs, self.episode,
                                        self.config["run_data_limit_bytes"], self.provenance)
            self.generation += 1
            self.view, self.error, self.last_decision = "pad", None, None
            self.state = State.MOVING
            self.task = asyncio.create_task(self._run())
            if self.supervisor:
                self.supervisor.cancel()
                await asyncio.gather(self.supervisor, return_exceptions=True)
            self.supervisor = asyncio.create_task(self._supervise())

    async def _command(self, name, operation, *, completes=True):
        async with self.command_lock:
            self._event("command_requested", command=name)
            async with asyncio.timeout(self.config["command_timeout_s"]):
                await operation()
            self._event("command_completed" if completes else "command_accepted", command=name)

    async def _settle(self, position):
        settled_since = None
        async with asyncio.timeout(self.config["command_timeout_s"]):
            while True:
                if not self._healthy():
                    raise RuntimeError("telemetry/process health or flight volume failure")
                telemetry = self.drone.telemetry()
                close = (math.dist(telemetry.position[:2], position[:2]) <= self.config["horizontal_tolerance_m"]
                         and abs(telemetry.position[2] - position[2]) <= self.config["vertical_tolerance_m"]
                         and telemetry.speed <= self.config["settle_speed_m_s"])
                if close:
                    settled_since = settled_since or time.monotonic()
                    if time.monotonic() - settled_since >= self.config["settle_duration_s"]:
                        return
                else:
                    settled_since = None
                await asyncio.sleep(.05)

    def _route(self, target):
        queue = deque([(self.view, [])])
        seen = {self.view}
        while queue:
            node, route = queue.popleft()
            if node == target:
                return route
            for a, b in self.config["edges"]:
                following = b if a == node else a if b == node else None
                if following and following not in seen:
                    seen.add(following)
                    queue.append((following, route + [following]))
        raise ValueError("no permitted route to target")

    async def _move(self, target):
        for view in self._route(target):
            position = self.config["waypoints"][view]
            self.state = State.MOVING
            await self._command("goto:" + view, lambda: self.drone.goto(position, 0), completes=False)
            await self._settle(position)
            self.view = view
            self._event("movement_completed", view=view, telemetry=asdict(self.drone.telemetry()))

    async def _observe(self, target, alternative):
        self.state = State.OBSERVING
        # A continuously received frame must be obtained after arrival/settling.
        arrived = time.monotonic()
        async with asyncio.timeout(self.config["hold_timeout_s"]):
            while True:
                frame = self.camera.latest()
                if (frame and frame.episode_id == self.episode
                        and frame.received_monotonic >= arrived
                        and 0 <= time.monotonic() - frame.received_monotonic <= self.config["frame_max_age_s"]):
                    break
                await asyncio.sleep(.02)
        self.request = uuid.uuid4().hex
        actions = ("continue", "hold", "finish") + (("recheck",) if alternative else ())
        observation = Observation(
            self.episode, self.request, frame,
            time.monotonic() + self.config["inference_timeout_s"],
            self.generation, target, self.view, tuple(alternative), actions,
            self.drone.telemetry())
        image_file = self.recorder.image(frame)
        self._event("observation", **observation.envelope(image_file))
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.config["inference_timeout_s"]):
                raw = await self.policy.infer(observation)
            self._event("model_response", request_id=self.request, raw=raw[:4096],
                        latency_s=time.monotonic()-started)
            decision = Decision.parse(raw)
            validate_decision(decision, observation, episode=self.episode, request=self.request,
                              generation=self.generation, state=self.state, view=self.view,
                              telemetry=self.drone.telemetry(),
                              telemetry_max_age=self.config["telemetry_max_age_s"])
            # A valid timestamp is insufficient if the vehicle drifted during inference.
            pose = self.drone.telemetry()
            expected = self.config["waypoints"][self.view]
            if (math.dist(pose.position[:2], expected[:2]) > self.config["horizontal_tolerance_m"]
                    or abs(pose.position[2]-expected[2]) > self.config["vertical_tolerance_m"]
                    or pose.speed > self.config["settle_speed_m_s"]):
                raise ValueError("vehicle left observation position")
        except Exception as exc:
            self._event("decision_rejected", request_id=self.request, reason=str(exc))
            raise
        self.last_decision = asdict(decision)
        self._event("decision_accepted", request_id=self.request, **self.last_decision)
        return decision

    async def _run(self):
        try:
            async with asyncio.timeout(self.config["mission_timeout_s"]):
                # Fresh camera is a pre-takeoff requirement.
                async with asyncio.timeout(self.config["hold_timeout_s"]):
                    while True:
                        frame = self.camera.latest()
                        if (frame and frame.episode_id == self.episode and
                                time.monotonic()-frame.received_monotonic <= self.config["frame_max_age_s"]):
                            break
                        await asyncio.sleep(.05)
                position = self.config["waypoints"]["pad"]
                await self._command("takeoff", lambda: self.drone.takeoff(position[2]), completes=False)
                await self._settle(position)
                self._event("movement_completed", view="pad")
                finish = False
                for target in self.config["targets"]:
                    await self._move(target["views"][0])
                    for attempt in range(2):
                        decision = await self._observe(target["name"], target["views"][1:] if attempt == 0 else [])
                        if decision.action == "recheck":
                            await self._move(decision.target_view)
                            continue
                        if decision.action == "hold":
                            await self._command("hold", self.drone.hold)
                            await asyncio.sleep(self.config["hold_timeout_s"])
                            raise TimeoutError("finite model hold expired")
                        finish = decision.action == "finish"
                        break
                    if finish:
                        break
                await self._move("pad")
                self.state = State.LANDING
                await self._command("land", self.drone.land)
                self.state = State.COMPLETE
                self.recorder.finish(state=self.state, route_completed=not finish,
                                     autonomous_success=not finish and all(self.provenance[k] for k in
                                         ("real_inference", "real_camera", "real_flight_dynamics")),
                                     error=None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            # Recovery holds finitely then lands at the current clear-ground location.
            self.generation += 1
            try:
                # Evidence storage must not gate recovery commands.
                async with self.command_lock:
                    async with asyncio.timeout(self.config["command_timeout_s"]):
                        await self.drone.hold()
            except Exception as hold_error:
                self.error += f"; hold unconfirmed: {hold_error}"
            await asyncio.sleep(self.config["hold_timeout_s"])
            await self._recover_land()

    async def _recover_land(self):
        self.state = State.LANDING
        try:
            # Recording failure must never prevent the recovery command.
            async with self.command_lock:
                async with asyncio.timeout(self.config["command_timeout_s"]):
                    await self.drone.land()
        except Exception as exc:
            self.error = (self.error or "") + f"; landing unconfirmed: {exc}"
        self.state = State.FAILED
        if self.recorder:
            try:
                self.recorder.finish(state=self.state, route_completed=False,
                                     autonomous_success=False, error=self.error)
            except OSError as exc:
                self.error += f"; report could not be persisted: {exc}"
            except RuntimeError as exc:
                self.error += f"; report budget exhausted: {exc}"

    async def _supervise(self):
        while self.state not in (State.COMPLETE, State.FAILED, State.IDLE):
            await asyncio.sleep(.1)
            if not self._healthy():
                await self.land("telemetry/process health or flight-volume failure")
                return

    async def _cancel_mission(self):
        self.generation += 1
        self.request = ""
        if self.task and self.task is not asyncio.current_task():
            if not self.task.done():
                self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    async def pause(self):
        async with self.operator_lock:
            if self.state not in (State.MOVING, State.OBSERVING):
                raise ValueError("pause requires an active inspection")
            await self._cancel_mission()
            self.state = State.PAUSED
            try:
                await self._command("operator_hold", self.drone.hold)
            except Exception as exc:
                self.error = f"operator hold failed: {exc}"
                await self._recover_land()
                return
            async def expire():
                await asyncio.sleep(self.config["hold_timeout_s"])
                await self.land("operator pause expired")
            self.task = asyncio.create_task(expire())

    async def land(self, reason="operator land"):
        async with self.operator_lock:
            await self._cancel_mission()
            self.error = reason
            await self._recover_land()

    async def close(self):
        if self.state not in (State.IDLE, State.COMPLETE, State.FAILED):
            await self.land("application shutdown")
        await self._cancel_mission()
        if self.supervisor:
            self.supervisor.cancel()
            await asyncio.gather(self.supervisor, return_exceptions=True)
        await self.drone.close()
        await self.camera.close()
        await self.policy.close()
