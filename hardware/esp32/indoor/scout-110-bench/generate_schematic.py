"""Create a self-contained KiCad schematic from the carrier connection table."""
import json
from pathlib import Path
import uuid

HERE=Path(__file__).resolve().parent/'carrier'
ROOT_UUID=str(uuid.uuid5(uuid.NAMESPACE_URL,'drone137/scout-carrier/prototype-a'))


def uid(value):return str(uuid.uuid5(uuid.UUID(ROOT_UUID),value))
def quote(value):return json.dumps(str(value),ensure_ascii=False)
def effects(size=1,extra=''):return f'(effects (font (size {size} {size})) {extra})'


def make_symbol(kind,pins,drawing):
    names={'R':'R','Q':'Q','D':'D','C':'C','J':'J','U':'U','F':'F'}
    result=f'''(symbol "D137:{kind}" (pin_names (offset 0)) (in_bom yes) (on_board yes)
      (property "Reference" "{names[kind]}" (at 0 4 0) {effects()})
      (property "Value" "{kind}" (at 0 -4 0) {effects()})
      (symbol "{kind}_0_1" {drawing})
      (symbol "{kind}_1_1" '''
    for n,(x,y,angle,length,label) in pins.items():
        result+=f'(pin passive line (at {x} {y} {angle}) (length {length}) (name "{label}" {effects(.8)}) (number "{n}" {effects(.8)}))'
    return result+'))'


def generate():
    data=json.loads((HERE/'netlist.json').read_text())
    line=lambda a,b:f'(polyline (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})) (stroke (width .2) (type default)) (fill (type none)))'
    two={'1':(-5.08,0,0,3.08,''),'2':(5.08,0,180,3.08,'')}
    definitions={
        'R':(two,'(rectangle (start -2 -1) (end 2 1) (stroke (width .2) (type default)) (fill (type none)))'),
        'D':({'1':(-5.08,0,0,4.08,'K'),'2':(5.08,0,180,4.08,'A')},
             line((-1,-1.5),(-1,1.5))+line((-1,0),(1,1.5))+line((1,1.5),(1,-1.5))+line((1,-1.5),(-1,0))),
        'C':(two,line((-.6,-1.5),(-.6,1.5))+line((.6,-1.5),(.6,1.5))+line((-2,0),(-.6,0))+line((.6,0),(2,0))),
        'Q':({'1':(-5.08,0,0,3.08,'G'),'2':(5.08,-2.54,180,3.08,'S'),'3':(5.08,2.54,180,3.08,'D')},
             line((-2,-1.5),(-2,1.5))+line((-1,-1.5),(-1,1.5))+line((-1,1),(2,1))+line((2,1),(2,2.54))+
             line((-1,-1),(2,-1))+line((2,-1),(2,-2.54))),
        'J':({'1':(-5.08,0,0,4.08,'')},'(circle (center 0 0) (radius 1) (stroke (width .2) (type default)) (fill (type none)))'),
        'F':(two,'(rectangle (start -2 -1) (end 2 1) (stroke (width .2) (type default)) (fill (type none)))'+line((-2,0),(2,0))),
        'U':({'1':(-7.62,2.54,0,2.54,'STAT'),'2':(-7.62,0,0,2.54,'VSS'),'3':(-7.62,-2.54,0,2.54,'VBAT'),
              '4':(7.62,2.54,180,2.54,'VDD'),'5':(7.62,-2.54,180,2.54,'PROG')},
             '(rectangle (start -5.08 -4.5) (end 5.08 4.5) (stroke (width .2) (type default)) (fill (type none)))')}
    symbols=''.join(make_symbol(k,*v).replace('"D137:'+k+'"','"'+k+'"',1) for k,v in definitions.items())
    (HERE/'D137.kicad_sym').write_text('(kicad_symbol_lib (version 20250114) (generator "drone137")'+symbols+')')
    (HERE/'sym-lib-table').write_text('(sym_lib_table (version 7) (lib (name "D137") (type "KiCad") (uri "${KIPRJMOD}/D137.kicad_sym") (options "") (descr "Self-contained Scout schematic symbols")))')
    text=[f'(kicad_sch (version 20250114) (generator "drone137") (uuid "{ROOT_UUID}") (paper "A3")',
          '(title_block (title "Scout 110-B motor carrier — prototype B, dock charge path") (date "2026-10-25") (rev "B") (comment 1 "Wired XIAO ESP32-S3 Sense and GY-521; motor suppression capacitors fitted at motors"))',
          '(lib_symbols '+''.join(make_symbol(k,*v) for k,v in definitions.items())+')']
    layout={}
    for i,y in enumerate((35,85,135,185),1):
        layout.update({f'J{i}':(30,y),f'R{i}':(65,y),f'Q{i}':(110,y),f'R{i+4}':(110,y+20),
                       f'D{i}':(160,y),f'J{i+4}':(210,y),f'J{i+8}':(260,y)})
    layout.update(J13=(30,245),J14=(30,267),J15=(95,245),J16=(95,267),J17=(355,245),
                  C1=(155,245),C2=(155,267),C3=(215,267),C4=(295,267),R9=(245,245),R10=(295,245))
    layout.update(J18=(30,305),F1=(70,305),C5=(115,305),U1=(170,305),R11=(230,305),C6=(115,330),J19=(30,330),J20=(230,330))
    def note(value,x,y,size=1.2):
        text.append(f'(text {quote(value)} (at {x} {y} 0) {effects(size,"(justify left)")} (uuid "{uid(value)}"))')
    note('1S only: 3.2–4.20 V. All grounds common. No motor current through XIAO traces.',20,13,1.5)
    note('M1 front-right CW; M2 rear-right CCW; M3 rear-left CW; M4 front-left CCW (viewed from above).',20,19)
    for part in data['parts']:
        ref=part['ref']
        if ref.startswith('H'):continue
        kind=ref[0];x,y=layout[ref];pins=definitions[kind][0]
        x=round(x/1.27)*1.27;y=round(y/1.27)*1.27
        text.append(f'''(symbol (lib_id "D137:{kind}") (at {x} {y} 0) (unit 1) (in_bom yes) (on_board yes)
            (dnp no) (uuid "{uid(ref)}")
            (property "Reference" {quote(ref)} (at {x} {y-5} 0) {effects()})
            (property "Value" {quote(part['value'])} (at {x} {y+5} 0) {effects()})
            (property "Footprint" {quote(part['package'])} (at {x} {y} 0) (effects (font (size 1 1)) hide))
            '''+''.join(f'(pin "{n}" (uuid "{uid(ref+"/"+n)}"))' for n in pins)+
            f'(instances (project "scout-carrier" (path "/{ROOT_UUID}" (reference "{ref}") (unit 1)))))')
        for n,name in part['nets'].items():
            px,py,angle,_,_=pins[n];gx,gy=x+px,y-py
            align='(justify right bottom)' if px<0 else '(justify left bottom)'
            text.append(f'(label {quote(name)} (at {gx} {gy} 0) {effects(.9,align)} (uuid "{uid(ref+"/net/"+n)}"))')
    note('PWM1 = D0 / GPIO1; PWM2 = D1 / GPIO2; PWM3 = D3 / GPIO4; PWM4 = D8 / GPIO7.',20,221)
    note('J15 → XIAO underside BAT+; J16 → GND. J17 → D10 / GPIO9. Never connect motors to 3V3 or USB 5V.',20,227)
    note('GY-521: module VCC → XIAO 3V3, GND → GND, SDA → D4/GPIO5, SCL → D5/GPIO6; AD0 → GND.',20,233)
    note('Verify actual module regulator/logic levels. Fit one 100 nF directly across each motor. No SD card.',20,239)
    note('Dock charge (prototype B): J18 ← pogo pin on the cradle contact (+5 V); J19 ← foot strips (GND). F1 0.5 A PTC. U1 MCP73831-2: 4.20 V, 500 mA (R11 2k0), thermal fold-back.',20,350)
    note('STAT is open-drain: low while charging, high-Z when complete or without 5 V. J20 → XIAO D2 / GPIO3 with the internal pull-up. Never feed 5 V to the XIAO 5V pin from the dock.',20,356)
    text.append(')')
    (HERE/'scout-carrier.kicad_sch').write_text('\n'.join(text))


if __name__=='__main__':generate()
