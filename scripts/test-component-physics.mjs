import assert from 'node:assert/strict';
import fs from 'node:fs';
import {spawnSync} from 'node:child_process';
import test from 'node:test';
import {initialize,MicroFlight,simulate,interpolate} from '../app/ui/micro-physics.mjs';
const python=process.env.DRONE137_PYTHON||'.venv/bin/python';
const exported=spawnSync(python,['-c',`import tempfile,json
from pathlib import Path
from app.components import Components
with tempfile.TemporaryDirectory() as t:
 r=Components(Path(t)/'parts.sqlite3')
 print(json.dumps([r.assemble(c['content']['id']) for c in r.list('configuration')]))
`],{encoding:'utf8'});
assert.equal(exported.status,0,exported.stderr);const assemblies=JSON.parse(exported.stdout);
const a=assemblies.find(a=>a.configuration.content.id==='scout-110');await initialize();

test('No duplicate collider mass; analytical free fall and per-rotor moment signs',()=>{
  const s=new MicroFlight(a);try{
    assert.ok(Math.abs(s.body.mass()-a.mass_kg)<1e-7);
    s.body.setTranslation({x:0,y:1,z:0},true);
    for(let i=0;i<25;i++)s.step([0,0,0,0]);
    assert.ok(Math.abs(s.body.translation().y-(1-.5*9.81*.1**2))<.003);
    assert.ok(Math.abs(s.body.linvel().y+9.81*.1)<.002);
    s.body.setTranslation({x:0,y:1,z:0},true);s.body.setLinvel({x:0,y:0,z:0},true);
    for(let i=0;i<10;i++)s.step([1,0,0,0]);
    assert.ok(s.body.angvel().x<0);assert.ok(s.body.angvel().z>0);assert.ok(s.body.angvel().y>0);
  }finally{s.dispose();}
});
test('Static data preserve four-motor units and never extrapolate measured thrust',()=>{
  const cf=assemblies.find(a=>a.configuration.content.id==='cf2-reference'),curve=cf.components.propulsion.content.parameters.curve;
  assert.ok(Math.abs(interpolate(curve,5)[0]*4-.567999)<1e-6);
  assert.deepEqual(interpolate(curve,-1),[0,0,0]);assert.equal(cf.propulsion_evidence,'derived');
  assert.equal(a.propulsion_evidence,'estimated');
});
test('Battery sag, discharge and finite motor response are active',()=>{
  const s=new MicroFlight(a);try{
    const idle=s.electrical([0,0,0,0]),load=s.electrical([1,1,1,1]);
    assert.ok(load.voltage<idle.voltage);assert.ok(load.current>idle.current);
    s.body.setTranslation({x:0,y:1,z:0},true);s.step([1,1,1,1]);
    const first=s.forces[0];assert.ok(first>0&&first<interpolate(s.p.propulsion.curve,load.voltage)[0]);
    for(let i=0;i<15;i++)s.step([1,1,1,1]);assert.ok(s.forces[0]>first);assert.ok(s.soc<1);
    assert.ok(s.motorVoltage(3.7,1)<3.7);
  }finally{s.dispose();}
});
test('Collision body stops at workshop wall with CCD',()=>{
  const s=new MicroFlight(a);try{
    s.body.setTranslation({x:1.7,y:.6,z:0},true);s.body.setLinvel({x:8,y:0,z:0},true);
    for(let i=0;i<40;i++)s.step([0,0,0,0]);assert.ok(s.contacts.length>0);assert.ok(s.body.translation().x<2);
  }finally{s.dispose();}
});
test('Camera delivery is delayed and the optional range sensor has a bounded view',()=>{
  const height=assemblies.find(a=>a.configuration.content.id==='height-110');
  const s=new MicroFlight(height);try{
    s.body.setTranslation({x:0,y:.7,z:0},true);
    for(let i=0;i<20;i++)s.step([0,0,0,0]);assert.equal(s.deliveredCamera,null);
    for(let i=0;i<20;i++)s.step([0,0,0,0]);assert.ok(s.deliveredCamera);
    assert.ok(s.t-s.deliveredCamera.capture_time_s>=.12);assert.ok(s.rangeMeasurement>0&&s.rangeMeasurement<1.2);
    s.body.setTranslation({x:0,y:2,z:0},true);
    for(let i=0;i<10;i++)s.step([0,0,0,0]);assert.equal(s.rangeMeasurement,null);
  }finally{s.dispose();}
});
test('Nominal takeoff/hover/transit/land is repeatable; halved timestep converges',async()=>{
  const first=await simulate(a),again=await simulate(a),fine=await simulate(a,'nominal',{dt:.002});
  assert.equal(first.flight_passed,true);assert.deepEqual(first.trajectory,again.trajectory);
  assert.equal(fine.flight_passed,true);assert.ok(Math.abs(fine.max_height_m-first.max_height_m)<.01);
  assert.ok(Math.abs(fine.hover_rmse_m-first.hover_rmse_m)<.005);
});
test('Insufficient lift fails instead of being patched into a passing trajectory',()=>{
  const s=new MicroFlight(a);try{s.thrustScale=.1;for(let i=0;i<1500;i++)s.step();
    assert.equal(s.result().gates.liftoff,false);assert.equal(s.result().flight_passed,false);
  }finally{s.dispose();}
});
test('Link timeout lands; observed motor degradation is compensated without removing the fault',async()=>{
  const loss=await simulate(a,'link-loss'),weak=await simulate(a,'weak-motor');
  assert.equal(loss.gates.command_expiry,true);assert.equal(loss.gates.landed,true);
  assert.equal(weak.flight_passed,true);
  assert.ok(weak.controller.minimum_estimated_gain<.5);
  const damaged=new MicroFlight(a,'weak-motor');
  try{
    while(damaged.t<6.2)damaged.step();
    assert.equal(damaged.motorScale[0],.45);
    assert.ok(Math.abs(damaged.forces[0]/interpolate(damaged.p.propulsion.curve,damaged.motorV[0])[0]-.45)<1e-12);
  }finally{damaged.dispose();}
});


test('Physical dynamics and all six fault scenarios match the archived plant under identical PWM',async()=>{
  const baseline=await import('../tests/fixtures/component-physics-v1.mjs');await baseline.initialize();
  assert.equal(MicroFlight.prototype.goal.toString(),baseline.MicroFlight.prototype.goal.toString());
  const gateSource=fn=>fn.toString().split('const gates=')[1].split('return {engine:')[0];
  assert.equal(gateSource(MicroFlight.prototype.result),gateSource(baseline.MicroFlight.prototype.result));
  for(const scenario of ['nominal','low-battery','gust','link-loss','weak-motor','pessimistic']){
    const old=new baseline.MicroFlight(a,scenario),current=new MicroFlight(a,scenario);
    try{
      for(let i=0;i<5000;i++){
        const duty=[.68+.04*Math.sin(i/65),.67,.68,.69];
        old.step([...duty]);current.step([...duty]);
        if(i%100===0)assert.deepEqual(current.state(),old.state(),scenario+' step '+i);
      }
      assert.deepEqual(current.result().gates,old.result().gates);
    }finally{old.dispose();current.dispose();}
  }
});

test('Five original and five revised assemblies retain propulsion, frame, camera and sensors',()=>{
  for(const id of ['micro-90','scout-110','guard-110','height-110','split-110']){
    const old=assemblies.find(a=>a.configuration.content.id===id),revised=assemblies.find(a=>a.configuration.content.id===id+'-power-v2');
    for(const slot of Object.keys(old.components).filter(k=>k!=='battery'))assert.deepEqual(revised.components[slot],old.components[slot]);
    const count=['guard-110','height-110','split-110'].includes(id)?3:2;
    const pack=revised.components.battery.content.parameters;
    assert.ok(Math.abs(pack.mass_kg-(count*.0073+.001))<1e-12);
    assert.equal(pack.capacity_mah,240*count);assert.equal(pack.resistance_ohm,.12/count);
    assert.equal(pack.cutoff_v,old.components.battery.content.parameters.cutoff_v);
    assert.equal(revised.components.battery.content.evidence.resistance_ohm.status,'estimated');
  }
});

test('Complete revised 42-flight matrix clears 95 percent with failures retained',async()=>{
  let passes=0;const failures=[];
  const ids=['cf2-reference','micro-90-power-v2','scout-110-power-v2','guard-110-power-v2','height-110-power-v2','split-110-power-v2','scout-published-pack'];
  for(const id of ids)for(const scenario of ['nominal','low-battery','gust','link-loss','weak-motor','pessimistic']){
    const r=await simulate(assemblies.find(a=>a.configuration.content.id===id),scenario);
    if(r.flight_passed)passes++;else failures.push([id,scenario]);
  }
  assert.ok(passes/42>=.95,JSON.stringify({passes,failures}));
  assert.equal(passes+failures.length,42); // No case may be silently omitted.
});
