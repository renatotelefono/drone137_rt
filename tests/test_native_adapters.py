"""Isolated adapter contracts. No Gazebo, MAVSDK server or aircraft exercised."""
import asyncio
import json
import socket
import struct
import sys
import time
import types
import unittest
from unittest.mock import patch

from adapters.camera import GazeboCamera
from adapters.mavsdk_drone import MavsdkDrone
from app.contracts import enu_to_global
from app.native import unused_port
from test_executor import eventually


class LocalPortContract(unittest.TestCase):
    def test_live_listener_rejected_but_closed_connection_can_restart(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            listener.listen()
            with self.assertRaises(RuntimeError):
                unused_port(port)
            with socket.create_connection(('127.0.0.1', port)) as client:
                connection, _ = listener.accept()
                connection.close()
                self.assertEqual(client.recv(1), b'')
        unused_port(port)


class CameraProtocol(unittest.IsolatedAsyncioTestCase):
    async def test_sensor_clock_preserved_separately_from_receipt_clock(self):
        camera=GazeboCamera("unused","/test")
        camera.begin_episode("episode")
        stream=asyncio.StreamReader()
        camera.process=types.SimpleNamespace(stdout=stream)
        task=asyncio.create_task(camera._read())
        jpeg=b"\xff\xd8fixture\xff\xd9"
        header=json.dumps({"bytes":len(jpeg),"width":320,"height":240,"sensor_time_s":42.5}).encode()
        stream.feed_data(struct.pack("!I",len(header))+header+jpeg)
        await eventually(lambda:camera.latest() is not None)
        frame=camera.latest()
        self.assertEqual(frame.sensor_time_s,42.5)
        self.assertGreater(frame.received_monotonic,0)
        self.assertEqual(frame.timestamp_basis,"sensor_simulation_unmapped")
        self.assertEqual(frame.episode_id,"episode")
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)

    async def test_oversized_input_rejected_before_allocation(self):
        camera=GazeboCamera("unused","/test")
        stream=asyncio.StreamReader()
        camera.process=types.SimpleNamespace(stdout=stream)
        stream.feed_data(struct.pack("!I",900000))
        await camera._read()
        self.assertIn("oversized",camera.error)
        self.assertIsNone(camera.latest())


class MavsdkContract(unittest.IsolatedAsyncioTestCase):
    async def test_native_api_translation_and_stream_lifecycle_with_stub(self):
        value=types.SimpleNamespace
        calls=[]
        air=False

        class Action:
            async def set_current_speed(self,speed): calls.append(("speed",speed))
            async def goto_location(self,*position): calls.append(("goto",*position))
            async def set_takeoff_altitude(self,height): calls.append(("height",height))
            async def arm(self): calls.append(("arm",))
            async def takeoff(self): calls.append(("takeoff",))
            async def hold(self): calls.append(("hold",))
            async def land(self): calls.append(("land",))

        class Telemetry:
            async def home(self):
                while True:
                    yield value(latitude_deg=47.,longitude_deg=8.,absolute_altitude_m=488.)
                    await asyncio.sleep(.01)
            async def health(self):
                while True:
                    yield value(is_global_position_ok=True,is_home_position_ok=True)
                    await asyncio.sleep(.01)
            async def in_air(self):
                while True:
                    yield air
                    await asyncio.sleep(.01)
            async def position_velocity_ned(self):
                while True:
                    yield value(position=value(east_m=0.,north_m=0.,down_m=0.),
                                velocity=value(east_m_s=0.,north_m_s=0.,down_m_s=0.))
                    await asyncio.sleep(.01)

        class System:
            def __init__(self,**kwargs):
                self.action=Action()
                self.telemetry=Telemetry()
                calls.append(("system",kwargs))
            async def connect(self): pass

        with patch.dict(sys.modules,{"mavsdk":value(System=System)}):
            drone=MavsdkDrone()
        await drone.connect()
        try:
            self.assertEqual(calls[0][1]["mavsdk_server_address"],"127.0.0.1")
            await drone.goto((10,20,2),90)
            self.assertEqual(calls[-1],("goto",*enu_to_global((10,20,2),(47,8,488)),90))
            await drone.takeoff(2)
            self.assertEqual(calls[-3:],[("height",2),("arm",),("takeoff",)])
            self.assertTrue(drone.telemetry().healthy)
            drone.health_at=0
            self.assertFalse(drone.telemetry().healthy)
        finally:
            await drone.close()
        self.assertTrue(all(t.done() for t in drone.tasks))
