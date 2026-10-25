const $=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let suggestions=null,selected=null,exploreTimer=null;
async function post(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Drone137-Control':'local'},body:JSON.stringify(body)});const x=await r.json();if(!r.ok)throw Error(x.error||r.status);return x;}
async function load(brief){
 try{const r=await fetch('/api/wizard/suggestions'+(brief?'?brief='+encodeURIComponent(brief):''),{cache:'no-store'});if(!r.ok)throw Error('Wizard unavailable');suggestions=await r.json();}catch(e){$('wizard-intro').textContent=e.message;return;}
 const s=suggestions;
 $('wizard-intro').textContent=s.mapped_places?`${s.mapped_places} mapped place${s.mapped_places>1?'s':''} in memory. ${s.classified?'Your words point to "'+s.classified+'".':'Pick a mission type.'}`:'No saved map yet. Mapping comes first; an audit can run on a test floor plan meanwhile.';
 $('wizard-cards').innerHTML=s.proposals.map(p=>`<div class="wizard-card${selected===p.id?' selected':''}" data-id="${esc(p.id)}"><span class="pill${p.status==='planned'?' planned':''}">${esc(p.ready?'READY':p.status.toUpperCase())}</span><small>${esc(p.capability.toUpperCase())}</small><b>${esc(p.name)}</b><p>${esc(p.question)} ${esc(p.reason)}</p></div>`).join('');
 document.querySelectorAll('.wizard-card').forEach(c=>c.onclick=()=>choose(c.dataset.id));
 if(s.exploration)renderExplore(s.exploration);
}
function choose(id){
 selected=id;const p=suggestions.proposals.find(p=>p.id===id);document.querySelectorAll('.wizard-card').forEach(c=>c.classList.toggle('selected',c.dataset.id===id));
 const form=$('wizard-form');form.hidden=false;document.body.dataset.template=id;
 const gate=Object.entries(p.gate).map(([k,v])=>`${k.replaceAll('_',' ')}: ${v}`).join(' · ');
 if(id==='audit'){form.innerHTML=`<label>Items to find (comma separated)<input id="w-targets" value="${esc((p.prefill.targets||[]).join(', '))}"></label><p class="note">Gate: ${esc(gate)}</p><button id="w-compose">Write the brief</button><span id="w-result"></span>`;
  $('w-compose').onclick=async()=>{try{const out=await post('/api/wizard/compose',{template:'audit',fields:{targets:$('w-targets').value,area:['west','south','east','north'].map(k=>Number($(k).value))}});$('instruction').value=out.instruction;$('w-result').textContent=out.warnings.join(' ')||'Brief written below. Generate the plan, review it, launch.';$('instruction').scrollIntoView({behavior:'smooth',block:'center'});}catch(e){$('w-result').textContent=e.message;}};}
 else if(id==='map'){form.innerHTML=`<label>Place name<input id="w-place" value="${esc(p.prefill.place||'')}"></label><label>Simulated layout seed<input id="w-seed" type="number" min="0" value="${esc(p.prefill.seed??'')}"></label><p class="note">Gate: ${esc(gate)}</p><button id="w-explore" ${p.ready?'':'disabled'}>Start exploration flight (simulation)</button><span id="w-result"></span>`;
  $('w-explore').onclick=async()=>{try{$('w-explore').disabled=true;const st=await post('/api/wizard/explore',{place:$('w-place').value,seed:Number($('w-seed').value)});renderExplore(st);$('w-result').textContent='Exploration started; progress below.';}catch(e){$('w-result').textContent=e.message;$('w-explore').disabled=false;}};}
 else{form.innerHTML=`<p class="note">${esc(p.note)}</p><p class="note">Gate it will be scored against: ${esc(gate)}</p>`;}
 $('wizard-note').textContent=p.status==='planned'?'Proposed and recorded; this mission type cannot be flown yet.':p.note;
}
function renderExplore(st){
 if(!st){$('wizard-explore').textContent='';return;}
 const score=st.score?` · ${st.score.accepted?'PASSED':'FAILED'}${st.score.failed_gates?.length?' ('+st.score.failed_gates.join(', ')+')':''}`:'';
 $('wizard-explore').textContent=`Exploration ${st.active?'running':'finished'}: ${st.state||'starting'}${st.observations!=null?' · '+st.observations+' observations':''}${st.elapsed_s!=null?' · '+Math.round(st.elapsed_s)+' s':''}${score}${st.error?' · '+st.error:''}`;
 if(st.active&&!exploreTimer)exploreTimer=setInterval(async()=>{try{const r=await fetch('/api/wizard/explore/status',{cache:'no-store'});if(r.ok)renderExplore(await r.json());}catch{}},5000);
 if(!st.active&&exploreTimer){clearInterval(exploreTimer);exploreTimer=null;load();}
}
let briefTimer=null;$('wizard-brief').oninput=()=>{clearTimeout(briefTimer);briefTimer=setTimeout(()=>load($('wizard-brief').value),400);};
load();
