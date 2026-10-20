import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from scripts.tools import space_guard
from sim.scenario import create
from sim.prepare import prepare


class Tooling(unittest.TestCase):
    def test_model_preparation_reuses_outputs_and_preserves_user_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            models=root/"px4/Tools/simulation/gz/models"
            for name in ("mono_cam","x500_mono_cam"):
                path=models/name
                path.mkdir(parents=True)
                (path/"model.sdf").write_text(
                    '<sdf><model><link><sensor><camera><image><width>1280</width><height>960</height></image>'
                    '</camera><update_rate>30</update_rate><visualize>true</visualize></sensor></link></model></sdf>')
            with patch("sim.prepare.DATA",root/"data"):
                prepare(root/"px4")
                prepare(root/"px4")
                target=root/"data/sim/models/mono_cam/model.sdf"
                self.assertEqual(ET.parse(target).find(".//image/width").text,"320")
                target.write_text("local edit")
                with self.assertRaises(RuntimeError):
                    prepare(root/"px4")
                self.assertEqual(target.read_text(),"local edit")

    def test_disk_guard_accounts_for_peak_and_system_reserve(self):
        with patch("scripts.tools.shutil.disk_usage",return_value=SimpleNamespace(free=12*1024**3)):
            space_guard(Path("."),1)
            with self.assertRaises(RuntimeError):
                space_guard(Path("."),4)

    def test_courtyard_is_local_and_scenarios_change_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            one=Path(directory)/"one.sdf"
            two=Path(directory)/"two.sdf"
            create(one,"open","closed")
            create(two,"closed","open",True)
            first=ET.parse(one)
            second=ET.parse(two)
            self.assertEqual(first.find(".//world").get("name"),"courtyard")
            self.assertNotEqual(first.find(".//model[@name='leaf_0']/pose").text,
                                second.find(".//model[@name='leaf_0']/pose").text)
            self.assertIsNotNone(second.find(".//model[@name='screen']"))
            self.assertNotIn("http",one.read_text())
