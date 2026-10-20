"""Generate a compact, offline SDF courtyard; ground truth is evaluation-only."""
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def box(world, name, xyz, size, color):
    model = ET.SubElement(world, "model", name=name)
    ET.SubElement(model, "static").text = "true"
    ET.SubElement(model, "pose").text = " ".join(map(str, (*xyz, 0, 0, 0)))
    link = ET.SubElement(model, "link", name="body")
    for kind in ("collision", "visual"):
        element = ET.SubElement(link, kind, name=kind)
        geometry = ET.SubElement(element, "geometry")
        ET.SubElement(ET.SubElement(geometry, "box"), "size").text = " ".join(map(str, size))
        if kind == "visual":
            material = ET.SubElement(element, "material")
            ET.SubElement(material, "ambient").text = color
            ET.SubElement(material, "diffuse").text = color


def create(path, gate_a="open", gate_b="closed", obscured=False):
    sdf = ET.Element("sdf", version="1.9")
    world = ET.SubElement(sdf, "world", name="courtyard")
    physics = ET.SubElement(world, "physics", name="1ms", type="ignored")
    ET.SubElement(physics, "max_step_size").text = "0.004"
    ET.SubElement(physics, "real_time_factor").text = "1"
    for name, file in (("Physics", "physics"), ("UserCommands", "user-commands"),
                       ("SceneBroadcaster", "scene-broadcaster"), ("Imu", "imu"),
                       ("AirPressure", "air-pressure"), ("NavSat", "navsat"),
                       ("Magnetometer", "magnetometer"),
                       ("Sensors", "sensors")):
        plugin = ET.SubElement(world, "plugin", filename=f"gz-sim-{file}-system",
                               name=f"gz::sim::systems::{name}")
        if name == "Sensors":
            ET.SubElement(plugin, "render_engine").text = "ogre2"
    coords = ET.SubElement(world, "spherical_coordinates")
    for name, value in (("surface_model","EARTH_WGS84"),("latitude_deg","47.397742"),
                        ("longitude_deg","8.545594"),("elevation","488"),("heading_deg","0")):
        ET.SubElement(coords,name).text = value
    ET.SubElement(world, "gravity").text = "0 0 -9.81"
    light = ET.SubElement(world, "light", type="directional", name="sun")
    ET.SubElement(light, "pose").text = "0 0 10 0 0 0"
    ET.SubElement(light, "diffuse").text = "0.9 0.9 0.9 1"
    ET.SubElement(light, "direction").text = "-0.3 -0.4 -1"
    box(world, "ground", (0,0,-.1), (30,30,.2), ".45 .55 .4 1")
    box(world, "pad_marker", (0,0,.015), (1.5,1.5,.03), ".9 .85 .4 1")
    for index, (x, state) in enumerate(((-3,gate_a),(3,gate_b))):
        box(world, f"post_{index}_l", (x-1.1,6,1.5), (.15,.2,3), ".3 .3 .3 1")
        box(world, f"post_{index}_r", (x+1.1,6,1.5), (.15,.2,3), ".3 .3 .3 1")
        box(world, f"lintel_{index}", (x,6,3), (2.3,.2,.15), ".3 .3 .3 1")
        # Open leaf sits outside the opening. All geometry remains north of corridors.
        leaf_x = x if state == "closed" else x-2.15
        box(world, f"leaf_{index}", (leaf_x,6,1.4), (2,.12,2.7), ".45 .28 .15 1")
    if obscured:
        box(world, "screen", (-3,4.8,1.8), (1.3,.1,2.5), ".2 .3 .25 1")
    ET.indent(sdf)
    Path(path).write_text(ET.tostring(sdf, encoding="unicode") + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="sim/courtyard.sdf")
    parser.add_argument("--gate-a", choices=["open","closed"], default="open")
    parser.add_argument("--gate-b", choices=["open","closed"], default="closed")
    parser.add_argument("--obscured", action="store_true")
    args = parser.parse_args()
    create(args.output, args.gate_a, args.gate_b, args.obscured)
