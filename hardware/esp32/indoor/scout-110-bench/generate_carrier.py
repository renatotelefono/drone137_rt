"""Reproducible Scout carrier. Run with KiCad's Python (pcbnew), not system Python.

Two-layer 42 x 40 mm hand-assembled prototype, 1.0 mm FR4, 2 oz copper.
The XIAO and GY-521 are wired modules; this board is not their footprint.

Prototype B adds the dock charge path: 5 V from the dock contacts (J18 cradle pin,
J19 foot strips) through a 0.5 A PTC into an MCP73831-2 1S charger onto VBAT, with
STAT brought out to J20 for the XIAO (D2 / GPIO3, pull-up: low while charging).
Regenerate with KiCad 10 after any edit: this file, generate_schematic.py, kicad-cli
ERC/DRC, check_carrier.py, then refresh carrier/provenance.json.
"""
import argparse
import json
from pathlib import Path
import uuid
import subprocess
import shutil
import pcbnew as k

HERE=Path(__file__).resolve().parent


def generate(library):
    out=HERE/'carrier';out.mkdir(exist_ok=True)
    footprints=out/'footprints';footprints.mkdir(exist_ok=True)
    (footprints/'D137.pretty').mkdir(exist_ok=True)
    board=k.BOARD();board.SetCopperLayerCount(2)
    board.GetDesignSettings().SetBoardThickness(k.FromMM(1.0))
    nets={};parts=[]
    def net(name):
        if name not in nets:
            nets[name]=k.NETINFO_ITEM(board,name);board.Add(nets[name])
        return nets[name]
    def xy(p):return k.VECTOR2I(k.FromMM(p[0]),k.FromMM(p[1]))
    def point(p):return (k.ToMM(p.x),k.ToMM(p.y))
    def pads_of(package,pos,angle):
        lib,name=package.split(':')
        f=k.FootprintLoad(str(Path(library)/(lib+'.pretty')),name)
        if not f:raise RuntimeError('Missing '+package)
        f.SetOrientationDegrees(angle);f.SetPosition(xy(pos))
        return {pad.GetNumber():point(pad.GetPosition()) for pad in f.Pads()}
    def oriented(ref,value,package,pos,connections,angles,want):
        """Place with the first angle whose pad layout satisfies want(pads), so routing never depends on a library convention."""
        for angle in angles:
            if want(pads_of(package,pos,angle)):return fp(ref,value,package,pos,connections,angle)
        raise RuntimeError(f'{ref}: no angle in {angles} gives the expected pad layout')
    def fp(ref,value,package,pos,connections,angle=0):
        lib,name=package.split(':')
        local=footprints/(lib+'.pretty');local.mkdir(exist_ok=True)
        shutil.copyfile(Path(library)/(lib+'.pretty')/(name+'.kicad_mod'),local/(name+'.kicad_mod'))
        f=k.FootprintLoad(str(Path(library)/(lib+'.pretty')),name)
        if not f:raise RuntimeError('Missing '+package)
        f.SetReference(ref);f.SetValue(value);f.SetOrientationDegrees(angle);f.SetPosition(xy(pos));board.Add(f)
        f.Reference().SetTextSize(xy((.8,.8)));f.Reference().SetTextThickness(k.FromMM(.12));f.Reference().SetPosition(xy((pos[0],pos[1]-2.1)))
        if ref.startswith('H'):f.Reference().SetVisible(False)
        if ref=='C1':f.Reference().SetPosition(xy((30,31.5)))
        if ref=='C2':f.Reference().SetPosition(xy((30,20)))
        if ref=='C3':f.Reference().SetPosition(xy((30,14)))
        if ref=='C4':f.Reference().SetPosition(xy((38.5,9)))
        f.Value().SetVisible(False)
        if ref.startswith(('D','Q')):f.Reference().SetPosition(xy((pos[0],pos[1]-2.5)))
        if ref.startswith('D'):f.Reference().SetPosition(xy((24,pos[1])))
        if ref in ('R5','R6','R7','R8'):f.Reference().SetPosition(xy((pos[0],pos[1]+2)))
        pads={}
        for pad in f.Pads():
            number=pad.GetNumber()
            if number in connections:pad.SetNet(net(connections[number]))
            pads[number]=point(pad.GetPosition())
        parts.append(dict(ref=ref,value=value,package=package,position_mm=list(pos),rotation_deg=angle,nets=connections,pads=pads))
        return pads
    def terminal(ref,label,pos,name,diameter=2.1,drill=1.0):
        f=k.FOOTPRINT(board);f.SetReference(ref);f.SetValue(label);f.SetPosition(xy(pos))
        pad=k.PAD(f);pad.SetNumber('1');pad.SetShape(k.PAD_SHAPE_CIRCLE);pad.SetAttribute(k.PAD_ATTRIB_PTH)
        layers=k.LSET()
        for layer in (k.F_Cu,k.B_Cu,k.F_Mask,k.B_Mask):layers.AddLayer(layer)
        pad.SetSize(xy((diameter,diameter)));pad.SetDrillSize(xy((drill,drill)));pad.SetLayerSet(layers)
        pad.SetPosition(xy(pos));pad.SetNet(net(name));f.Add(pad);board.Add(f)
        f.Reference().SetVisible(False);f.Value().SetVisible(False)
        text=k.PCB_TEXT(board);text.SetText(label);text.SetPosition(xy((pos[0],pos[1]+(2.1 if diameter>2.5 else 1.7))))
        text.SetTextSize(xy((.8,.8)));text.SetTextThickness(k.FromMM(.12));text.SetLayer(k.F_SilkS);board.Add(text)
        if label=='M4-':text.SetPosition(xy((11.2,33.5)))
        if label=='M4+':text.SetPosition(xy((23,33.5)))
        footprint_name=f'WirePad_{diameter}_{drill}'
        f.SetFPID(k.LIB_ID('D137',footprint_name))
        (footprints/'D137.pretty'/(footprint_name+'.kicad_mod')).write_text(
            f'(footprint "{footprint_name}" (version 20241229) (generator "drone137") (layer "F.Cu") '
            f'(pad "1" thru_hole circle (at 0 0) (size {diameter} {diameter}) (drill {drill}) (layers "*.Cu" "*.Mask")))')
        parts.append(dict(ref=ref,value=label,package='D137:'+footprint_name,position_mm=list(pos),nets={'1':name},pads={'1':pos}))
        return pos
    def trace(name,*points,width=.3,layer=k.F_Cu):
        for a,b in zip(points,points[1:]):
            if a==b:continue
            t=k.PCB_TRACK(board);t.SetStart(xy(a));t.SetEnd(xy(b));t.SetWidth(k.FromMM(width));t.SetLayer(layer);t.SetNet(net(name));board.Add(t)
    def via(name,p):
        v=k.PCB_VIA(board);v.SetPosition(xy(p));v.SetWidth(k.FromMM(.9));v.SetDrill(k.FromMM(.45));v.SetViaType(k.VIATYPE_THROUGH);v.SetLayerPair(k.F_Cu,k.B_Cu);v.SetNet(net(name));board.Add(v)
    for i,y in enumerate((6.,14.,22.,30.),1):
        gate=f'GATE{i}';pwm=f'PWM{i}';drain=f'MOTOR{i}-'
        inp=terminal(f'J{i}',pwm,(2.2,y+1.2),pwm,1.6,.8)
        r=fp(f'R{i}','100R','Resistor_SMD:R_0805_2012Metric',(5,y),{'1':pwm,'2':gate})
        q=fp(f'Q{i}','AO3400A','Package_TO_SOT_SMD:SOT-23',(10.5,y),{'1':gate,'2':'GND','3':drain})
        pull=fp(f'R{i+4}','10k','Resistor_SMD:R_0805_2012Metric',(7,y+2.5),{'1':gate,'2':'GND'})
        diode=fp(f'D{i}','SS34','Diode_SMD:D_SMA',(16,y),{'1':'VBAT','2':drain},180)
        minus=terminal(f'J{i+4}',f'M{i}-',(14,y+3.5),drain)
        plus=terminal(f'J{i+8}',f'M{i}+', (20,y+3.5),'VBAT')
        trace(pwm,inp,r['1']);trace(gate,r['2'],(7.5,y-.95),q['1'])
        trace(gate,(7.5,y-.95),(7.5,y+1),(pull['1'][0],y+1),pull['1'])
        trace('GND',pull['2'],(8.8,y+2.5));via('GND',(8.8,y+2.5))
        trace('GND',q['2'],(10.5,y+1.8),(11.3,y+1.8),(11.3,y+2.8),width=.8)
        via('GND',(11.3,y+1.8));via('GND',(11.3,y+2.8))
        trace(drain,q['3'],diode['2'],width=.8);trace(drain,diode['2'],minus,width=1.1)
        trace('VBAT',diode['1'],(20,y),plus,width=1.5)
    trace('VBAT',(20,6),(20,37),width=2.4)
    terminal('J13','BAT+',(20,37),'VBAT',2.8,1.2)
    terminal('J14','BAT-',(14,37),'GND',2.8,1.2)
    bat=terminal('J15','XIAO BAT+',(35,26),'VBAT')
    terminal('J16','XIAO GND',(35,30),'GND')
    trace('VBAT',(20,26),bat,width=1)
    bulk=fp('C1','470uF 10V','Capacitor_THT:CP_Radial_D6.3mm_P2.50mm',(27,35.5),{'1':'VBAT','2':'GND'})
    trace('VBAT',(20,37),(24,37),(24,35.5),bulk['1'],width=1.5)
    cap=fp('C2','47uF 10V','Capacitor_THT:CP_Radial_D5.0mm_P2.00mm',(34,19),{'1':'VBAT','2':'GND'})
    trace('VBAT',bat,(32,26),(32,19),cap['1'],width=.8)
    dec=fp('C3','100nF','Capacitor_SMD:C_0805_2012Metric',(34,14),{'1':'VBAT','2':'GND'})
    trace('VBAT',(32,19),(32,14),dec['1'],width=.4);via('GND',dec['2'])
    top=fp('R9','100k 1%','Resistor_SMD:R_0805_2012Metric',(31,6),{'1':'VBAT','2':'VBAT_ADC'})
    low=fp('R10','100k 1%','Resistor_SMD:R_0805_2012Metric',(36,6),{'1':'VBAT_ADC','2':'GND'})
    filt=fp('C4','100nF','Capacitor_SMD:C_0805_2012Metric',(35,9),{'1':'VBAT_ADC','2':'GND'})
    adc=terminal('J17','D10 ADC',(38,12),'VBAT_ADC',1.6,.8)
    trace('VBAT',(20,6),top['1'],width=.4)
    trace('VBAT_ADC',top['2'],low['1']);trace('VBAT_ADC',(33,6),(33,9),filt['1'])
    trace('VBAT_ADC',(33,9),(33,12),adc);via('GND',low['2']);via('GND',filt['2'])
    # Dock charge path (prototype B). 5 V enters at J18 from the pogo pin under the cradle
    # contact; the foot strips return to GND at J19. F1 limits a shorted contact; U1 charges
    # VBAT at up to 500 mA (R11 = 2k0) with thermal fold-back; STAT goes to the XIAO on J20.
    left_first=lambda pads:pads['1'][0]<pads['2'][0]
    chg_in=terminal('J18','CHG+',(23,22),'CHG_IN')
    terminal('J19','CHG-',(31,9),'GND')
    fuse=oriented('F1','PTC 0.5A','Fuse:Fuse_1206_3216Metric',(27.5,22),{'1':'CHG_IN','2':'CHG5V'},(0,180),left_first)
    trace('CHG_IN',chg_in,fuse['1'],width=.8)
    cin=oriented('C5','4.7uF 10V','Capacitor_SMD:C_0805_2012Metric',(29.5,19.5),{'1':'CHG5V','2':'GND'},(0,180),left_first)
    trace('CHG5V',fuse['2'],cin['1'],width=.8);via('GND',cin['2'])
    charger=oriented('U1','MCP73831-2','Package_TO_SOT_SMD:SOT-23-5',(27.5,14),
                     {'1':'STAT','2':'GND','3':'VBAT','4':'CHG5V','5':'PROG'},(180,0),
                     lambda pads:pads['4'][1]>pads['1'][1] and pads['3'][0]<pads['2'][0]<pads['1'][0] and pads['4'][0]<pads['5'][0])
    trace('CHG5V',cin['1'],(charger['4'][0],19.5),charger['4'],width=.8)
    rprog=oriented('R11','2k0 1%','Resistor_SMD:R_0805_2012Metric',(30,16.5),{'1':'PROG','2':'GND'},(90,270),lambda pads:pads['1'][1]<pads['2'][1])
    trace('PROG',charger['5'],rprog['1']);via('GND',rprog['2'])
    cvb=oriented('C6','4.7uF 10V','Capacitor_SMD:C_0805_2012Metric',(24,18),{'1':'VBAT','2':'GND'},(0,180),left_first)
    trace('VBAT',(20,18),cvb['1'],width=.8);via('GND',cvb['2'])
    trace('VBAT',cvb['1'],(cvb['1'][0],charger['3'][1]),charger['3'],width=.8)
    stat=terminal('J20','D2 STAT',(31,11.5),'STAT',1.6,.8)
    trace('STAT',charger['1'],stat)
    trace('GND',charger['2'],(charger['2'][0],11.2));via('GND',(charger['2'][0],11.2))
    for i,p in enumerate(((3,2.5),(39,2.5),(3,37),(39,37)),1):
        fp(f'H{i}','M2','MountingHole:MountingHole_2.2mm_M2',p,{})
    for a,b in zip(((0,0),(42,0),(42,40),(0,40)),((42,0),(42,40),(0,40),(0,0))):
        edge=k.PCB_SHAPE();edge.SetShape(k.SHAPE_T_SEGMENT);edge.SetStart(xy(a));edge.SetEnd(xy(b));edge.SetLayer(k.Edge_Cuts);edge.SetWidth(k.FromMM(.05));board.Add(edge)
    zone=k.ZONE(board);zone.SetLayer(k.B_Cu);zone.SetNet(net('GND'));zone.SetLocalClearance(k.FromMM(.25));zone.SetThermalReliefGap(k.FromMM(.3));zone.SetThermalReliefSpokeWidth(k.FromMM(.6));zone.SetPadConnection(k.ZONE_CONNECTION_FULL)
    outline=zone.Outline();outline.NewOutline()
    for p in ((.5,.5),(41.5,.5),(41.5,39.5),(.5,39.5)):outline.Append(*xy(p))
    board.Add(zone)
    board.SetFileName(str(out/'scout-carrier.kicad_pcb'))
    k.ZONE_FILLER(board).Fill(board.Zones())
    k.SaveBoard(str(out/'scout-carrier.kicad_pcb'),board)
    (out/'netlist.json').write_text(json.dumps({'revision':'prototype-b','board_mm':[42,40,1.0],'copper_oz':2,'parts':parts},indent=2))
    libraries=sorted(p.name[:-7] for p in footprints.glob('*.pretty'))
    (out/'fp-lib-table').write_text('(fp_lib_table (version 7)\n'+''.join(
        f'(lib (name "{name}")(type "KiCad")(uri "${{KIPRJMOD}}/footprints/{name}.pretty")(options "")(descr "Pinned prototype footprints"))\n'
        for name in libraries)+')\n')
    project=out/'scout-carrier.kicad_pro'
    if not project.exists():project.write_text(json.dumps({'meta':{'filename':project.name,'version':1}}))
    # Explicit independent connectivity assertions, including diode polarity.
    for i in range(1,5):
        assert next(p for p in parts if p['ref']==f'Q{i}')['nets']=={'1':f'GATE{i}','2':'GND','3':f'MOTOR{i}-'}
        assert next(p for p in parts if p['ref']==f'D{i}')['nets']=={'1':'VBAT','2':f'MOTOR{i}-'}
    assert next(p for p in parts if p['ref']=='U1')['nets']=={'1':'STAT','2':'GND','3':'VBAT','4':'CHG5V','5':'PROG'}
    assert next(p for p in parts if p['ref']=='F1')['nets']=={'1':'CHG_IN','2':'CHG5V'}
    return board,out,parts


def export(board,out,cli):
    gerbers=out/'gerbers';gerbers.mkdir(exist_ok=True)
    path=str(out/'scout-carrier.kicad_pcb')
    subprocess.run([cli,'pcb','drc','--exit-code-violations','--refill-zones','--save-board','--all-track-errors','-o',str(out/'drc.txt'),path],check=True)
    subprocess.run([cli,'pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,Edge.Cuts','-o',str(gerbers)+'/',path],check=True)
    subprocess.run([cli,'pcb','export','drill','-o',str(gerbers)+'/',path],check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--footprints',required=True);parser.add_argument('--kicad-cli',default='kicad-cli')
    args=parser.parse_args();board,out,parts=generate(args.footprints);export(board,out,args.kicad_cli)
    print(out/'drc.txt')
