// Fly by hand: keyboard or gamepad to bounded attitude setpoints at 20 Hz over the paired link.
const el=id=>document.getElementById(id);
const HEADERS={'Content-Type':'application/json','X-Drone137-Control':'local'};
let aircraft=null,active=false,limits=null,trim=0,timer=null,keys=new Set(),lastStatus=null;
async function api(path,body){
 const r=await fetch('/api/aircraft'+path,body===undefined?{}:{method:'POST',headers:HEADERS,body:JSON.stringify(body)});
 const v=await r.json();if(!r.ok)throw Error(v.error||'Manual control request failed');return v;
}
function status(text){el('manual-status').textContent=text;}
function dead(v){return Math.abs(v)<.12?0:Math.max(-1,Math.min(1,v));}
function axes(){
 let roll=0,pitch=0,yaw=0,trimStep=0;
 if(keys.has('KeyD'))roll+=1;if(keys.has('KeyA'))roll-=1;
 if(keys.has('KeyW'))pitch+=1;if(keys.has('KeyS'))pitch-=1;
 if(keys.has('KeyE'))yaw+=1;if(keys.has('KeyQ'))yaw-=1;
 if(keys.has('KeyR'))trimStep+=1;if(keys.has('KeyF'))trimStep-=1;
 const pads=navigator.getGamepads?navigator.getGamepads():[];
 for(const pad of pads){
  if(!pad)continue;
  roll+=dead(pad.axes[2]||0);pitch-=dead(pad.axes[3]||0);yaw+=dead(pad.axes[0]||0);trimStep-=dead(pad.axes[1]||0);
  if(pad.buttons[0]?.pressed)land('Gamepad button');
  el('manual-gamepad').textContent='Gamepad: '+pad.id.slice(0,40);
 }
 return {roll:Math.max(-1,Math.min(1,roll)),pitch:Math.max(-1,Math.min(1,pitch)),yaw:Math.max(-1,Math.min(1,yaw)),trimStep};
}
async function tick(){
 if(!active||!limits)return;
 const a=axes();
 trim=Math.max(0,Math.min(limits.thrust,trim+a.trimStep*.005));el('manual-trim').value=trim.toFixed(2);
 try{
  const s=await api('/'+encodeURIComponent(aircraft)+'/manual/input',{roll_rad:a.roll*limits.tilt_rad,pitch_rad:a.pitch*limits.tilt_rad,yaw_rate_rad_s:a.yaw*limits.yaw_rate_rad_s,thrust:trim});
  lastStatus=s;
  status(`${s.state} · aircraft ${s.aircraft_state} · roll ${s.setpoint.roll_rad.toFixed(2)} pitch ${s.setpoint.pitch_rad.toFixed(2)} yaw ${s.setpoint.yaw_rate_rad_s.toFixed(2)} thrust ${s.setpoint.thrust.toFixed(2)} · ${s.commands} setpoints sent`);
  if(s.state!=='armed')stop(s.error||'Session ended');
 }catch(e){stop(e.message);}
}
function stop(reason){active=false;if(timer){clearInterval(timer);timer=null;}el('manual-start').disabled=false;el('manual-land').disabled=true;if(reason)status(reason);}
async function land(reason){
 if(!active)return;
 active=false;if(timer){clearInterval(timer);timer=null;}   // stop the stick stream before the land request
 try{const s=await api('/'+encodeURIComponent(aircraft)+'/manual/land',{});stop((reason?reason+' · ':'')+s.state+' · aircraft '+s.aircraft_state);}
 catch(e){stop(e.message);}
}
async function start(){
 aircraft=el('manual-aircraft').value;if(!aircraft){status('Connect an aircraft first.');return;}
 try{
  const s=await api('/'+encodeURIComponent(aircraft)+'/manual/start',{});
  limits=s.limits;trim=0;el('manual-trim').max=limits.thrust;el('manual-trim').value='0';
  active=true;el('manual-start').disabled=true;el('manual-land').disabled=false;
  status('Armed. Sticks are live; release to level, Space or the Land button to land.');
  timer=setInterval(tick,1000/s.rate_hz);
 }catch(e){status(e.message);}
}
async function refreshAircraft(){
 try{
  const {aircraft:list}=await api('');const select=el('manual-aircraft');const current=select.value;
  select.replaceChildren();
  for(const d of list.filter(d=>d.connection==='connected')){const o=document.createElement('option');o.value=d.id;o.textContent=d.name+(d.kind==='protocol-emulator'?' (emulator)':'');select.append(o);}
  if([...select.options].some(o=>o.value===current))select.value=current;
 }catch(e){}
}
el('manual-start').onclick=start;
el('manual-land').onclick=()=>land('Land button');
el('manual-trim').oninput=e=>{trim=Number(e.target.value)||0;};
window.addEventListener('keydown',e=>{if(!active||e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;if(e.code==='Space'||e.code==='Escape'){e.preventDefault();land('Keyboard');return;}if(!e.repeat&&limits&&(e.code==='KeyR'||e.code==='KeyF')){trim=Math.max(0,Math.min(limits.thrust,trim+(e.code==='KeyR'?.01:-.01)));el('manual-trim').value=trim.toFixed(2);}keys.add(e.code);});
window.addEventListener('keyup',e=>keys.delete(e.code));
window.addEventListener('blur',()=>{keys.clear();if(active)land('Window lost focus');});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&active)land('Page hidden');});
el('manual-panel').addEventListener('toggle',()=>{if(el('manual-panel').open)refreshAircraft();});
setInterval(()=>{if(el('manual-panel').open&&!active)refreshAircraft();},2000);
refreshAircraft();
