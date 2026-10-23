const el=id=>document.getElementById(id);
let preview=null, refreshBusy=false, rendered=null;
async function request(path,body){
 const response=await fetch('/api/aircraft'+path,body===undefined?{}:{method:'POST',
  headers:{'Content-Type':'application/json','X-Drone137-Control':'local'},body:JSON.stringify(body)});
 const value=await response.json();if(!response.ok)throw Error(value.error||'Aircraft request failed');return value;
}
async function action(fn){el('aircraft-error').textContent='';try{await fn();}catch(e){el('aircraft-error').textContent=e.message;}await refresh();}
function button(label,fn){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=async()=>{b.disabled=true;try{await action(fn);}finally{b.disabled=false;}};return b;}
async function refresh(){
 if(refreshBusy)return;refreshBusy=true;
 try{
  const {aircraft}=await request('');const host=el('paired-aircraft');
  const signature=JSON.stringify(aircraft.map(d=>[d.id,d.name,d.kind,d.connection,d.voltage_v,d.error]));
  if(signature!==rendered){
   rendered=signature;host.replaceChildren();
   if(!aircraft.length)host.textContent='No aircraft paired yet.';
   for(const drone of aircraft){
   const card=document.createElement('div'),title=document.createElement('p'),state=document.createElement('p');
   title.textContent=drone.name+' · '+(drone.kind==='protocol-emulator'?'Protocol emulator':'Physical aircraft');
   state.textContent=drone.connection+(drone.voltage_v!=null?' · '+drone.voltage_v.toFixed(2)+' V':'')+(drone.error?' · '+drone.error:'');
   card.append(title,state);
   const connected=drone.connection==='connected';
   card.append(button(connected?'Disconnect':'Connect',async()=>{
    await request('/'+encodeURIComponent(drone.id)+'/'+(connected?'disconnect':'connect'),{});
    preview=connected?null:drone.id;
   }));
   if(connected)card.append(button('View camera',async()=>{preview=drone.id;}));
   // Available even after a sensor fault. Neither action depends on the LLM.
   card.append(button('Reduce thrust to stop',()=>request('/'+encodeURIComponent(drone.id)+'/land',{})));
   card.append(button('Cut motors',()=>request('/'+encodeURIComponent(drone.id)+'/disarm',{})));
   const note=document.createElement('small');note.textContent=drone.kind==='protocol-emulator'
    ?'Static test camera and synthetic IMU. This emulator does not fly.'
    :'Connection check only. Flight firmware and navigation integration are pending.';
    card.append(note);host.append(card);
   }
  }
  const selected=aircraft.find(d=>d.id===preview&&d.connection==='connected');
  el('paired-camera').hidden=!selected;
  el('paired-camera-label').textContent=selected?(selected.kind==='protocol-emulator'?'Emulator fixture · ':'Camera · ')+selected.name:'';
  if(selected)el('paired-camera').src='/api/aircraft/'+encodeURIComponent(preview)+'/frame?t='+Date.now();
 }catch(e){el('aircraft-error').textContent=e.message;el('paired-camera').hidden=true;}
 finally{refreshBusy=false;}
}
el('pair-aircraft').onclick=()=>action(async()=>{
 const file=el('pair-file').files[0];if(!file||file.size>4096)throw Error('Select a pairing JSON file smaller than 4 KB.');
 const assembly=el('assembly').value;if(!assembly)throw Error('Select an aircraft configuration first.');
 try{await request('/pair',{profile:JSON.parse(await file.text()),address:el('pair-address').value.trim(),
  name:el('pair-name').value.trim(),assembly});}
 finally{el('pair-file').value='';}
});
await refresh();setInterval(refresh,1500);
