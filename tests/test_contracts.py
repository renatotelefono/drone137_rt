import json
import math
import time
import unittest
from pathlib import Path
from dataclasses import replace

from app.contracts import Decision, Frame, Observation, State, Telemetry, enu_to_global, validate_decision, validate_mission
from adapters.fixtures import LatestFrameBuffer


def observation():
    now = time.monotonic()
    return Observation("e", "r", Frame("f", "e", b"jpeg", now), now+5, 1, "gate_a",
                       "gate_a_front", ("gate_a_side",), ("continue","recheck","hold","finish"),
                       Telemetry((0,0,2), 0, now))


class Contracts(unittest.TestCase):
    def test_mission_rejects_physical_mode_and_out_of_volume_waypoints(self):
        config=json.loads((Path(__file__).resolve().parents[1]/"config/lean-8gb.json").read_text())
        validate_mission(config)
        with self.assertRaises(ValueError):
            validate_mission(config | {"physical_enabled":True})
        config["waypoints"]["gate_a_side"]=[999,0,2]
        with self.assertRaises(ValueError):
            validate_mission(config)

    def test_strict_json(self):
        valid = {"observation":"uncertain","action":"recheck","target_view":"gate_a_side","reason":"Obscured"}
        self.assertEqual(Decision.parse(json.dumps(valid)).action, "recheck")
        for change in ({"extra":True}, {"action":"takeoff"}, {"observation": "probably"},
                       {"reason":"x"*301}, {"target_view": 3}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                Decision.parse(json.dumps(valid | change))
        for raw in ('{"action":"hold","action":"land"}', "null", "[]", "x"*4097):
            with self.assertRaises(ValueError):
                Decision.parse(raw)

    def test_no_coordinate_payload(self):
        with self.assertRaises(ValueError):
            Decision.parse('{"observation":"open","action":"continue","target_view":"1,2,3","reason":""}')

    def test_envelope_validation(self):
        obs = observation()
        decision = Decision("uncertain","recheck","gate_a_side","")
        valid = dict(episode="e", request="r", generation=1, state=State.OBSERVING,
                     view="gate_a_front", telemetry=obs.telemetry)
        validate_decision(decision, obs, **valid)
        cases = [{"episode":"other"}, {"request":"old"}, {"generation":2}, {"state":State.PAUSED},
                 {"view":"pad"}, {"now":obs.deadline+1},
                 {"telemetry":replace(obs.telemetry, healthy=False)},
                 {"telemetry":replace(obs.telemetry, received_monotonic=0)}]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_decision(decision, obs, **(valid | change))
        with self.assertRaises(ValueError):
            validate_decision(replace(decision, target_view="gate_b_side"), obs, **valid)
        with self.assertRaises(ValueError):
            validate_decision(decision, replace(obs, allowed_actions=("continue",)), **valid)
        with self.assertRaises(ValueError):
            validate_decision(decision, replace(obs, frame=replace(obs.frame, episode_id="old")), **valid)

    def test_latest_slot_replaces_without_queue(self):
        slot = LatestFrameBuffer()
        for i in range(10000):
            slot.put(Frame(str(i),"e",b"x",float(i)))
        self.assertEqual(slot.latest().frame_id,"9999")
        self.assertEqual(len(vars(slot)),1)
        slot.clear()
        self.assertIsNone(slot.latest())

    def test_enu_global_axes_and_absolute_altitude(self):
        home = (47,8,488)
        lat, lon, alt = enu_to_global((10,20,2),home)
        self.assertAlmostEqual(math.radians(lat-47)*6378137,20,places=6)
        self.assertAlmostEqual(math.radians(lon-8)*6378137*math.cos(math.radians(47)),10,places=6)
        self.assertEqual(alt,490)
        with self.assertRaises(ValueError):
            enu_to_global((float("nan"),0,0),home)
