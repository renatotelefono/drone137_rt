import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from app.mission_runtime import MissionRuntime
from app.mission_api import install
from app.server import local_only
from adapters.rapier_drone import RapierDrone


class Model:
    def __init__(self):
        self.focus = 'red fire extinguisher'
        self.objective = 'inventory'

    async def text(self, *args):
        return json.dumps({'objective': self.objective, 'focus': self.focus, 'summary': 'Search the room'})


class MissionContracts(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.model = Model()
        self.runtime = MissionRuntime(self.model, Path(self.temp.name)/'runs')
        self.body = {'instruction': 'Find the red fire extinguisher', 'case': 'hard-west-dim-present',
                     'assembly': 'scout-110-power-v2', 'area': [0, 0, 12, 10]}

    async def asyncTearDown(self):
        await self.runtime.close()
        self.temp.cleanup()

    async def test_immutable_aircraft_and_consumed_draft_without_browser(self):
        draft = await self.runtime.plan(self.body)
        frozen = json.dumps(draft['assembly'], sort_keys=True)
        gate = asyncio.Event()
        async def run(plan):
            await gate.wait()
        self.runtime.execute = run
        launched = await self.runtime.launch(draft['id'])
        self.assertTrue(launched['busy'])
        self.assertFalse(launched['dashboard_required'])
        self.assertEqual(frozen, json.dumps(launched['mission']['plan']['assembly'], sort_keys=True))
        with self.assertRaises(ValueError):
            await self.runtime.launch(draft['id'])
        with self.assertRaises(RuntimeError):
            await self.runtime.plan(self.body)
        gate.set()
        await self.runtime.task

    async def test_different_target_and_physical_task_cannot_launch(self):
        self.model.focus = 'blue toolbox'
        draft = await self.runtime.plan(self.body)
        self.assertFalse(draft['dispatchable'])
        with self.assertRaises(ValueError):
            await self.runtime.launch(draft['id'])
        self.model.focus = 'red fire extinguisher'
        self.model.objective = 'unsupported'
        self.assertFalse((await self.runtime.plan(self.body))['dispatchable'])

    async def test_expiry_and_area_validation(self):
        draft = await self.runtime.plan(self.body)
        draft['created_at'] -= 601
        with self.assertRaises(ValueError):
            await self.runtime.launch(draft['id'])
        for area in ([0, 0, 13, 10], [0, 0, float('nan'), 10], [0, 0, .5, .5]):
            with self.assertRaises(ValueError):
                await self.runtime.plan({**self.body, 'area': area})

    async def test_http_guards_and_no_camera_session_required(self):
        app = web.Application(middlewares=[local_only])
        install(app, self.runtime)
        self.runtime.execute = AsyncMock()
        async with TestClient(TestServer(app)) as client:
            denied = await client.post('/api/mission/plan', json=self.body)
            self.assertEqual(denied.status, 403)
            headers = {'X-Drone137-Control': 'local'}
            draft = await (await client.post('/api/mission/plan', json=self.body, headers=headers)).json()
            response = await client.post('/api/mission/launch', json={'draft_id': draft['id']}, headers=headers)
            self.assertEqual(response.status, 200)
            await self.runtime.task
            self.runtime.execute.assert_awaited_once()
            self.assertEqual((await client.get('/api/mission/status', headers={'Host': 'external.example'})).status, 403)


class TelemetryHandoff(unittest.IsolatedAsyncioTestCase):
    def vehicle(self, age):
        v = RapierDrone({}, {'width': 12, 'depth': 10, 'moving_actor': {}}, Path('.'))
        v.last_received = 0
        v.call = AsyncMock(return_value={'transport': {'sample_age_s': age}, 'contacts': 0,
            'tripped': False, 'failsafe': False, 'max_tilt_deg': 0})
        return v

    async def test_old_supervisor_cache_refreshes_before_movement(self):
        v = self.vehicle(.02)
        await v.check_fresh()
        v.call.assert_awaited_once_with('status')

    async def test_fresh_reply_with_stale_aircraft_sample_is_rejected(self):
        v = self.vehicle(.8)
        with self.assertRaisesRegex(RuntimeError, 'stale aircraft telemetry'):
            await v.check_fresh()

    async def test_invalid_setpoint_is_rejected_before_changing_radio_goal(self):
        v=self.vehicle(.02)
        v.goal=[1.25,1.25,1.8,0]
        with self.assertRaisesRegex(ValueError,'bounded flight'):
            await v.settle([1.25,1.25,1.8000061511993408,0])
        self.assertEqual(v.goal,[1.25,1.25,1.8,0])
        v.call.assert_not_awaited()
