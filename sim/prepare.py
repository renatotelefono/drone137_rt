"""Copy the pinned upstream model to generated project assets; preserve source."""
import argparse
import shutil
import xml.etree.ElementTree as ET
import hashlib
import json
from pathlib import Path
from scripts.tools import DATA


def prepare(px4):
    models = px4 / "Tools/simulation/gz/models"
    destination = DATA / "sim/models"
    destination.mkdir(parents=True, exist_ok=True)
    # Local copies preserve upstream notices; the PX4 checkout is untouched.
    for name in ("mono_cam", "x500_mono_cam"):
        target = destination / name
        source = models / name
        source_hashes = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in source.rglob("*") if p.is_file()}
        marker = target / ".drone137-generated.json"
        if target.exists():
            current = {str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in target.rglob("*") if p.is_file() and p != marker}
            saved = json.loads(marker.read_text()) if marker.exists() else {}
            if saved.get("source") == source_hashes and saved.get("generated") == current:
                continue
            raise RuntimeError(f"{target} contains different/local assets; preserve them before regenerating")
        shutil.copytree(source, target)
        if name == "mono_cam":
            path = target / "model.sdf"
            tree = ET.parse(path)
            tree.find(".//image/width").text = "320"
            tree.find(".//image/height").text = "240"
            tree.find(".//sensor/update_rate").text = "2"
            tree.find(".//sensor/visualize").text = "false"
            ET.SubElement(tree.find(".//sensor"), "topic").text = "/drone137/camera"
            tree.write(path)
        generated = {str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in target.rglob("*") if p.is_file()}
        marker.write_text(json.dumps({"source": source_hashes, "generated": generated}, indent=2))
    worlds = DATA / "sim/worlds"
    worlds.mkdir(exist_ok=True)
    original = Path(__file__).parent / "courtyard.sdf"
    target = worlds / "courtyard.sdf"
    if target.exists() and target.read_bytes() != original.read_bytes():
        raise RuntimeError("Preserve the locally edited courtyard before replacing it")
    if not target.exists():
        shutil.copyfile(original, target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--px4", type=Path, required=True)
    prepare(parser.parse_args().px4)
