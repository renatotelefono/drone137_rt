// Offline image/video importer. Same browser JPEG encoding and image bound as recon.
// Input labels remain evaluator metadata and never enter model prompts.
const {chromium}=require('../.local/browser-test/node_modules/playwright');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const [collectionFile,outputFolder]=process.argv.slice(2);
if(!collectionFile||!outputFolder)throw new Error('Usage: node scripts/prepare-reliability.cjs collection.json NEW_OUTPUT_FOLDER');
const sha=data=>crypto.createHash('sha256').update(data).digest('hex');
(async()=>{
 const input=JSON.parse(fs.readFileSync(collectionFile,'utf8'));
 if(input.version!==1||!Array.isArray(input.cases)||!input.cases.length)throw new Error('Expected version 1 collection with cases');
 const out=path.resolve(outputFolder);fs.mkdirSync(out,{recursive:false});fs.mkdirSync(path.join(out,'images'));
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||(process.platform==='darwin'?'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome':'/usr/bin/chromium'),headless:true});
 try{
  const page=await browser.newPage();const cases=[];const hashes=new Set();const ids=new Set();
  for(const row of input.cases){
   if(!/^[A-Za-z0-9_-]{1,80}$/.test(row.id)||ids.has(row.id))throw new Error('Invalid or duplicate case ID');ids.add(row.id);
   const file=path.resolve(path.dirname(collectionFile),row.input);
   if(!['.jpg','.jpeg','.png','.webm','.mp4'].includes(path.extname(file).toLowerCase()))throw new Error('Use PNG, JPEG, WebM or MP4');
   const isVideo=['.webm','.mp4'].includes(path.extname(file).toLowerCase());
   if(isVideo&&(!Number.isFinite(row.time_s)||row.time_s<0))throw new Error('Video needs a nonnegative time_s');
   if(fs.statSync(file).size>64*1024*1024)throw new Error('Use a source image or short clip under 64 MiB');
   const source=fs.readFileSync(file),ext=path.extname(file).toLowerCase();
   const mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.mp4':'video/mp4','.webm':'video/webm'}[ext];
   // Data URLs avoid network access and preserve an origin-clean canvas.
   await page.goto('about:blank');
   const frame=await page.evaluate(async({url,isVideo,time})=>{
    const media=document.createElement(isVideo?'video':'img');
    await new Promise((resolve,reject)=>{
     const timer=setTimeout(()=>reject(new Error('Media decode timeout')),10000);
     media.onerror=()=>{clearTimeout(timer);reject(new Error('Could not decode input media'));};
     media[isVideo?'onloadeddata':'onload']=()=>{clearTimeout(timer);resolve();};
     if(isVideo){media.muted=true;media.preload='auto';}media.src=url;
    });
    if(isVideo){
     const seek=async position=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Video seek timeout')),10000);media.onseeked=()=>{clearTimeout(timer);resolve();};media.currentTime=position;});
     // Browser MediaRecorder WebM often omits duration metadata. Decode the end
     // once before validating a timestamp; never silently clamp an invalid time.
     if(!Number.isFinite(media.duration))await seek(1e10);
     if(!Number.isFinite(media.duration)||time>=media.duration)throw new Error('Sample timestamp is outside video');
     if(Math.abs(media.currentTime-time)>.001)await seek(time);
    }
    const w=isVideo?media.videoWidth:media.naturalWidth,h=isVideo?media.videoHeight:media.naturalHeight;
    if(!w||!h||w*h>40000000)throw new Error('Unsupported source dimensions');
    const scale=Math.min(1,960/w,540/h),canvas=document.createElement('canvas');canvas.width=Math.round(w*scale);canvas.height=Math.round(h*scale);
    canvas.getContext('2d').drawImage(media,0,0,canvas.width,canvas.height);
    return {jpeg:canvas.toDataURL('image/jpeg',.85).split(',')[1],width:canvas.width,height:canvas.height,source_width:w,source_height:h,decoded_time_s:isVideo?media.currentTime:null};
   },{url:`data:${mime};base64,${source.toString('base64')}`,isVideo,time:row.time_s});
   const jpeg=Buffer.from(frame.jpeg,'base64'),hash=sha(jpeg);
   if(jpeg.length>200000)throw new Error('Image exceeds model bound; explicitly choose a lower-resolution collection');
   if(hashes.has(hash))throw new Error('Duplicate image; choose distinct encounters instead of repeating frames');hashes.add(hash);
   const imagePath=`images/${row.id}.jpg`;fs.writeFileSync(path.join(out,imagePath),jpeg,{flag:'wx'});
   const {input:unused,...metadata}=row;
   cases.push({...metadata,path:imagePath,image_sha256:hash,source_sha256:sha(source),width:frame.width,height:frame.height,source_width:frame.source_width,source_height:frame.source_height,decoded_time_s:frame.decoded_time_s});
  }
  fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify({...input,cases},null,2)+'\n',{flag:'wx'});
  console.log(`Prepared ${cases.length} distinct images: ${out}/manifest.json`);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
