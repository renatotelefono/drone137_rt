import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path

from adapters.fixtures import FakeDrone, ReplayCamera, ScriptedPolicy
from app.contracts import State
from app.executor import MissionExecutor
from app.recorder import RunRecorder, StorageFull

ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = {"profile":"cloud-dev", "real_inference":False, "real_camera":False,
              "real_flight_dynamics":False, "physical_transport":False}


async def eventually(predicate, timeout=4):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(.01)


class BlockingPolicy(ScriptedPolicy):
    def __init__(self):
        self.entered = asyncio.Event()
        self.cancelled = False

    async def infer(self, observation):
        self.entered.set()
        try:
            await asyncio.sleep(20)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class Missions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = json.loads((ROOT/"config/lean-8gb.json").read_text())
        self.config.update(settle_duration_s=.01, hold_timeout_s=.08,
                           inference_timeout_s=.25, command_timeout_s=1, mission_timeout_s=5)
        self.camera = ReplayCamera([ROOT/"sim/assets/fixture-01.jpg"],fps=100)
        await self.camera.start()
        self.drone = FakeDrone(speed=100)
        self.executor = MissionExecutor(self.drone,self.camera,ScriptedPolicy(),self.config,
                                        Path(self.temp.name),PROVENANCE)

    async def asyncTearDown(self):
        await self.executor.close()
        self.temp.cleanup()

    def events(self):
        return [json.loads(line) for line in self.executor.recorder.events.read_text().splitlines()]

    async def test_complete_route_rechecks_recording_and_repeatability(self):
        # This checks route/evidence semantics, not subsecond scheduler timing.
        # Dedicated tests below retain short deadlines to verify timeout handling.
        self.config.update(inference_timeout_s=2, command_timeout_s=3, mission_timeout_s=15)
        for _ in range(2):
            await self.executor.start()
            await eventually(lambda:self.executor.state in (State.COMPLETE,State.FAILED), timeout=20)
            self.assertEqual(self.executor.state,State.COMPLETE,self.executor.error)
            summary = json.loads((self.executor.recorder.directory/"summary.json").read_text())
            self.assertFalse(summary["autonomous_success"])
            events = self.events()
            self.assertEqual(len([e for e in events if e["event"]=="decision_accepted"]),4)
            self.assertEqual(len([e for e in events if e["event"]=="frame"]),4)
            self.assertEqual(self.drone.position,(0,0,0))
        moves = [command for command in self.drone.commands if command[0]=="goto"]
        self.assertIn(("goto",(-5,3,2)),moves)
        self.assertIn(("goto",(5,3,2)),moves)

    async def test_operator_land_cancels_inference_and_lands_here(self):
        policy = BlockingPolicy()
        self.executor.policy = policy
        await self.executor.start()
        await asyncio.wait_for(policy.entered.wait(),2)
        position = self.drone.position
        before = len(self.drone.commands)
        await self.executor.land()
        self.assertTrue(policy.cancelled)
        self.assertEqual(self.drone.commands[before:],[("land",)])
        self.assertEqual(self.drone.position[:2],position[:2])
        self.assertFalse(self.drone.in_air)
        self.assertEqual(self.executor.state,State.FAILED)

    async def test_pause_expires_and_never_accepts_late_decision(self):
        policy = BlockingPolicy()
        self.executor.policy = policy
        await self.executor.start()
        await asyncio.wait_for(policy.entered.wait(),2)
        await self.executor.pause()
        self.assertEqual(self.executor.state,State.PAUSED)
        await eventually(lambda:self.executor.state==State.FAILED)
        self.assertTrue(policy.cancelled)
        self.assertFalse(any(e["event"]=="decision_accepted" for e in self.events()))

    async def test_inference_timeout_recovers_and_records_failure(self):
        self.executor.policy = BlockingPolicy()
        await self.executor.start()
        await eventually(lambda:self.executor.state==State.FAILED)
        self.assertIn("TimeoutError",self.executor.error)
        self.assertFalse(self.drone.in_air)
        self.assertTrue(any(e["event"]=="decision_rejected" for e in self.events()))

    async def test_malformed_decision_rejected(self):
        class Invalid(ScriptedPolicy):
            async def infer(self, obs):
                return '{"action":"arm"}'
        self.executor.policy = Invalid()
        await self.executor.start()
        await eventually(lambda:self.executor.state==State.FAILED)
        self.assertIn("ValueError",self.executor.error)
        self.assertFalse(self.drone.in_air)

    async def test_stale_camera_blocks_takeoff(self):
        await self.camera.close()
        self.camera.begin_episode = lambda _:None
        self.camera.clear()
        await self.executor.start()
        await eventually(lambda:self.executor.state==State.FAILED)
        self.assertNotIn("takeoff",[c[0] for c in self.drone.commands])

    async def test_camera_loss_during_route_cannot_authorize_decisions(self):
        await self.executor.start()
        await eventually(lambda:self.drone.in_air)
        await self.camera.close()
        await eventually(lambda:self.executor.state==State.FAILED)
        self.assertFalse(any(e["event"]=="decision_accepted" for e in self.events()))
        self.assertFalse(self.drone.in_air)

    async def test_drift_during_inference_rejects_an_otherwise_valid_decision(self):
        drone=self.drone
        class Drift(ScriptedPolicy):
            async def infer(self,obs):
                drone.position=(obs.telemetry.position[0]+1,*obs.telemetry.position[1:])
                return '{"observation":"open","action":"continue","target_view":null,"reason":"Clear"}'
        self.executor.policy=Drift()
        await self.executor.start()
        await eventually(lambda:self.executor.state==State.FAILED)
        self.assertIn("left observation position",self.executor.error)
        self.assertFalse(any(e["event"]=="decision_accepted" for e in self.events()))

    async def test_health_failure_preempts_model(self):
        policy=BlockingPolicy()
        self.executor.policy=policy
        await self.executor.start()
        await asyncio.wait_for(policy.entered.wait(),2)
        self.drone.healthy=False
        await eventually(lambda:self.executor.state==State.FAILED)
        self.assertTrue(policy.cancelled)
        self.assertIn("health",self.executor.error)

    async def test_double_start_rejected(self):
        await self.executor.start()
        with self.assertRaises(ValueError):
            await self.executor.start()

    async def test_disk_full_does_not_prevent_landing(self):
        await self.executor.start()
        await eventually(lambda:self.drone.in_air)
        self.executor.recorder.limit=self.executor.recorder.used+32768
        await eventually(lambda:self.executor.state==State.FAILED)
        self.assertFalse(self.drone.in_air)
        await self.executor.task
        self.assertIsNone(self.executor.task.exception())

    async def test_command_acknowledgement_is_not_arrival(self):
        async def no_move(height):
            self.drone.in_air=True
        self.drone.takeoff=no_move
        self.config["command_timeout_s"]=.1
        await self.executor.start()
        await eventually(lambda:self.executor.state==State.FAILED)
        self.assertFalse(any(e["event"]=="movement_completed" for e in self.events()))

    async def test_model_finish_returns_to_pad(self):
        class Finish(ScriptedPolicy):
            async def infer(self,obs):
                return '{"observation":"open","action":"finish","target_view":null,"reason":"Done"}'
        self.executor.policy=Finish()
        await self.executor.start()
        await eventually(lambda:self.executor.state==State.COMPLETE)
        self.assertEqual(self.drone.position,(0,0,0))
        self.assertEqual(self.drone.commands[-2],("goto",(0,0,2)))


class Storage(unittest.TestCase):
    def test_existing_evidence_counts_towards_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            (path/"previous").write_bytes(b"x"*100)
            with self.assertRaises(StorageFull):
                RunRecorder(path,"e",65550,PROVENANCE)
            self.assertEqual((path/"previous").stat().st_size,100)
