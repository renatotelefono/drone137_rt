const $=id=>document.getElementById(id);
async function post(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Drone137-Control':'local'},body:JSON.stringify(body)});const x=await r.json();if(!r.ok)throw Error(x.error||r.status);return x;}
function show(reply,proposal){
 $('ask-reply').textContent=reply||'';const box=$('ask-confirm');box.replaceChildren();box.hidden=!proposal;
 if(proposal){const b=document.createElement('button');b.textContent=`Confirm: map seed ${proposal.seed} as ${proposal.place}`;b.onclick=async()=>{b.disabled=true;try{const st=await post('/api/assistant/confirm',{proposal:{kind:'start_exploration',...proposal}});show('Exploration started; progress is shown in Start here.');document.dispatchEvent(new CustomEvent('drone137-exploration',{detail:st}));}catch(e){show(e.message);}};const c=document.createElement('button');c.textContent='Cancel';c.onclick=()=>show('');box.append(b,c);}
}
async function ask(){
 const text=$('ask-text').value.trim();if(!text)return;$('ask-send').disabled=true;show('Interpreting…');
 try{const out=await post('/api/assistant/ask',{text});show(out.reply,out.needs_confirmation?out.proposal:null);
  if(out.executed&&out.action==='compose_audit'){$('instruction').value=out.result.instruction;document.body.dataset.template='audit';}
  if(out.executed&&(out.action==='connect'||out.action==='show_camera')&&out.aircraft){window.dispatchEvent(new CustomEvent('drone137-preview',{detail:out.aircraft.id}));$('aircraft-panel').open=true;}
 }catch(e){show(e.message);}finally{$('ask-send').disabled=false;}
}
$('ask-send').onclick=ask;$('ask-text').onkeydown=e=>{if(e.key==='Enter')ask();};
const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
if(Recognition){const mic=$('ask-mic');mic.hidden=false;mic.onclick=()=>{const r=new Recognition();r.lang='en-US';r.interimResults=false;r.onresult=e=>{$('ask-text').value=e.results[0][0].transcript;ask();};r.onerror=e=>show('Dictation failed: '+e.error);mic.disabled=true;r.onend=()=>{mic.disabled=false;};r.start();};}
