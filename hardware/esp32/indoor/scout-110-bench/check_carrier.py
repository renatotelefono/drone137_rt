"""Compare the actual PCB pads with KiCad's independently exported schematic netlist."""
from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
import pcbnew
root=Path(__file__).parent/'carrier'
board=pcbnew.LoadBoard(str(root/'scout-carrier.kicad_pcb'))
actual={}
for f in board.GetFootprints():
 for pad in f.Pads():
  if pad.GetNetname():actual[(f.GetReference(),pad.GetNumber())]=pad.GetNetname()
exported={}
for net in ET.parse(root/'schematic.net').findall('.//nets/net'):
 for node in net.findall('node'):exported[(node.get('ref'),node.get('pin'))]=net.get('name').lstrip('/')
assert actual==exported, {'pcb_only':sorted(set(actual.items())-set(exported.items())),'schematic_only':sorted(set(exported.items())-set(actual.items()))}
result={'passed':True,'electrical_pins_compared':len(actual),'method':'Actual loaded PCB pad nets versus KiCad schematic export XML; exact pin/net equality','sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('scout-carrier.kicad_pcb','scout-carrier.kicad_sch','schematic.net')}}
(root/'connectivity-check.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
