import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from mavsdk.param import ParamError, ParamResult
from adapters.native_flight import NativeFlight
from app.observed_navigation import ObservedNavigation


class HardwareControls(unittest.IsolatedAsyncioTestCase):
    async def test_parameter_ack_timeout_requires_matching_readback(self):
        from adapters.native_flight import configure_float_parameters
        timeout = ParamError(ParamResult(ParamResult.Result.TIMEOUT, 'Timeout'), 'set_param_float')
        param = SimpleNamespace(set_param_float=AsyncMock(side_effect=timeout),
                                get_param_float=AsyncMock(return_value=.6))
        actual = await configure_float_parameters(param, {'MPC_XY_CRUISE': .6}, lambda: None)
        self.assertEqual(actual, {'MPC_XY_CRUISE': .6})
        self.assertEqual(param.set_param_float.await_count, 1)

    async def test_parameter_mismatch_and_permanent_rejection_fail_closed(self):
        from adapters.native_flight import configure_float_parameters
        param = SimpleNamespace(set_param_float=AsyncMock(), get_param_float=AsyncMock(return_value=5.))
        with self.assertRaisesRegex(RuntimeError, 'readback'):
            await configure_float_parameters(param, {'MPC_XY_CRUISE': .6}, lambda: None)
        self.assertEqual(param.set_param_float.await_count, 3)
        rejected = ParamError(ParamResult(ParamResult.Result.VALUE_OUT_OF_RANGE, 'Rejected'), 'set_param_float')
        param.set_param_float = AsyncMock(side_effect=rejected)
        with self.assertRaises(ParamError):
            await configure_float_parameters(param, {'MPC_XY_CRUISE': .6}, lambda: None)
        self.assertEqual(param.set_param_float.await_count, 1)

    async def test_position_loss_near_waypoint_still_holds_before_resuming(self):
        flight = NativeFlight.__new__(NativeFlight)
        flight.phase = 'transit'; flight.sensor_events = []
        flight.profile = {'sensors': {'max_position_sigma_m': .15}}
        flight.odometry_at = time.monotonic()-1; flight.odometry_sigma = .02
        flight.check = lambda: None
        flight.estimated = lambda: {'position': [2., 2., 1.5], 'quaternion': [0, 0, 0, 1]}
        flight.drone = SimpleNamespace(telemetry=lambda: SimpleNamespace(speed=0.))
        flight.setpoint = AsyncMock()
        flight.nav = SimpleNamespace(last=time.monotonic(), motion_clear=lambda *a: True)
        async def recover():
            for _ in range(15):
                await asyncio.sleep(.05)
                flight.nav.last = time.monotonic()
                if _ >= 3: flight.odometry_at = time.monotonic()
        recovery = asyncio.create_task(recover())
        try: await flight.reach([2.1, 2., 1.5], 0)
        finally: await recovery
        self.assertEqual([e['event'] for e in flight.sensor_events], ['hold', 'resume'])

    def test_braking_distance_respects_airframe_acceleration(self):
        fast = ObservedNavigation(12, 10, [4.4, 1.25], .38, .26, braking_acceleration=.8)
        slow = ObservedNavigation(12, 10, [4.4, 1.25], .38, .26, braking_acceleration=.2)
        for nav in (fast, slow):
            nav.last = 1.; nav.ranges = [{'angle': 0., 'distance': 1.4}]
        self.assertTrue(fast.motion_clear([4, 2], [5, 2], .6, 1.))
        self.assertFalse(slow.motion_clear([4, 2], [5, 2], .6, 1.))
