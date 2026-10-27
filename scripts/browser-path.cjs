// Where a Chromium-family browser is on this platform; CHROMIUM_PATH overrides. Shared by every script that opens one.
const fs=require('node:fs'),path=require('node:path');
function candidates(platform=process.platform){
 if(platform==='darwin')return['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','/Applications/Chromium.app/Contents/MacOS/Chromium','/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'];
 if(platform==='win32'){
  const roots=[process.env.ProgramFiles||'C:\\Program Files',process.env['ProgramFiles(x86)']||'C:\\Program Files (x86)',process.env.LocalAppData||'C:\\Users\\Default\\AppData\\Local'];
  return roots.flatMap(r=>[path.join(r,'Google','Chrome','Application','chrome.exe'),path.join(r,'Microsoft','Edge','Application','msedge.exe'),path.join(r,'Chromium','Application','chrome.exe')]);
 }
 return['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium','/usr/bin/chromium-browser','/snap/bin/chromium'];
}
function browserPath(){
 if(process.env.CHROMIUM_PATH)return process.env.CHROMIUM_PATH;
 const found=candidates().find(p=>fs.existsSync(p));
 if(!found)throw Error('No Chromium-family browser found; install Google Chrome, Chromium or Edge, or set CHROMIUM_PATH');
 return found;
}
module.exports={browserPath,candidates};
