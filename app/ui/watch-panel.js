// Perched watch: start a watch on a docked aircraft, show events, acknowledge alerts.
const el=id=>document.getElementById(id);
const HEADERS={'Content-Type':'application/json','X-Drone137-Control':'local'};
let rendered='',alerted=new Set(),audio=null;
async function api(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:HEADERS,body:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(v.error||'Watch request failed');return v;}
function beep(){try{audio=audio||new (window.AudioContext||window.webkitAudioContext)();const o=audio.createOscillator(),g=audio.createGain();o.frequency.value=880;g.gain.value=.08;o.connect(g);g.connect(audio.destination);o.start();o.stop(audio.currentTime+.25);}catch(e){}}
function when(t){return new Date(t*1000).toLocaleTimeString();}
async function refreshAircraft(){
 try{const {aircraft}=await api('/api/aircraft');const s=el('watch-aircraft'),current=s.value;s.replaceChildren();
  for(const d of aircraft.filter(d=>d.connection==='connected')){const o=document.createElement('option');o.value=d.id;o.textContent=d.name;s.append(o);}
  if([...s.options].some(o=>o.value===current))s.value=current;}catch(e){}
}
async function refresh(){
 try{
  const status=await api('/api/watch');const events=await api('/api/watch/events?limit=20');
  el('watch-status').textContent=status.watches.length?status.watches.map(w=>`${w.aircraft}: ${w.state}, ${w.frames} frames, ${w.events} events${w.error?' · '+w.error:''}`).join(' · '):'No watch running.';
  const banner=el('watch-alert');banner.hidden=!status.alerts.length;
  if(status.alerts.length){banner.textContent=`ALERT · ${status.alerts[0].summary} · ${when(status.alerts[0].at)} · ${status.alerts.length} unacknowledged`;
   for(const a of status.alerts)if(!alerted.has(a.id)){alerted.add(a.id);beep();}}
  const sig=JSON.stringify(events.map(e=>[e.id,e.acknowledged_at]));   // the feed is rebuilt only when the events change, so its buttons stay put
  if(sig===rendered)return;rendered=sig;
  const feed=el('watch-events');feed.replaceChildren();
  for(const e of events){
   const card=document.createElement('article');card.className=e.matters&&!e.acknowledged_at?'event alert':'event';
   const img=document.createElement('img');img.src=`/api/watch/events/${e.id}/composite.jpg`;img.alt='before and after';
   const text=document.createElement('p');text.textContent=`${when(e.at)} · ${e.category||e.kind} · ${e.summary}`;
   card.append(img,text);
   if(e.matters&&!e.acknowledged_at){const b=document.createElement('button');b.textContent='Acknowledge';b.onclick=async()=>{b.disabled=true;try{await api(`/api/watch/events/${e.id}/ack`,{});rendered='';await refresh();}catch(x){el('watch-status').textContent=x.message;}};card.append(b);}
   feed.append(card);
  }
 }catch(e){el('watch-status').textContent=e.message;}
}
el('watch-start').onclick=async()=>{const id=el('watch-aircraft').value;if(!id){el('watch-status').textContent='Connect an aircraft first.';return;}try{await api(`/api/watch/${encodeURIComponent(id)}/start`,{});rendered='';await refresh();}catch(e){el('watch-status').textContent=e.message;}};
el('watch-stop').onclick=async()=>{const id=el('watch-aircraft').value;try{await api(`/api/watch/${encodeURIComponent(id)}/stop`,{});rendered='';await refresh();}catch(e){el('watch-status').textContent=e.message;}};
el('watch-panel').addEventListener('toggle',()=>{if(el('watch-panel').open)refreshAircraft();});
refreshAircraft();refresh();setInterval(refresh,2000);setInterval(()=>{if(el('watch-panel').open)refreshAircraft();},5000);
