// Real old-engine regression checks. Only the isolated, owned VM is controlled.
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),base=path.join(root,'.local/emulator'),{connect}=require('./emulator-cdp.cjs');
const pause=ms=>new Promise(r=>setTimeout(r,ms));
function control(...args){return cp.execFileSync('python3',[path.join(root,'fork/emulator'),...args],{encoding:'utf8'});}
function status(){return JSON.parse(control('status','--json'));}
function key(name){control('key',name);}
function rgb(h){return 'rgb('+[1,3,5].map(n=>parseInt(h.slice(n,n+2),16)).join(', ')+')';}
function assertRgba(actual,h,a,label){const parts=actual.match(/[0-9.]+/g).map(Number);assert.deepEqual(parts.slice(0,3),[1,3,5].map(n=>parseInt(h.slice(n,n+2),16)),label+' exact RGB');assert.ok(Math.abs(parts[3]-a)<=1/255+.000001,label+' 8-bit alpha');}
(async()=>{let c,initial,takeover=false,changed=false;const results=[];try{
 assert.equal(status().viewerClients,0,'Close the viewer before automated VM input');
 c=await connect();await c.call('Runtime.enable');await c.call('Console.enable');
 initial=await c.evaluate('(function(){var s={};for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i);s[k]=localStorage.getItem(k);}return {storage:s,cfg:window.__OMARCHY_CFG,state:window.__OMARCHY_STATE};})()');
 assert.equal(initial.state.ws,0,'Begin from Home');assert.equal(initial.state.zone,'dock','Begin from the dock');assert.equal(initial.state.modalOpen,false,'Close pending dialogs before testing');
 assert.equal(await c.evaluate('document.hidden'),false,'Launcher must be foreground in the VM');
 const engine=await c.evaluate('navigator.userAgent');assert.match(engine,/Chrome\/38\.0\.2125\.122/);
 const installed=JSON.parse(fs.readFileSync(path.join(base,'installed.json'),'utf8')),build=path.resolve(root,installed.build);
 if(!build.startsWith(path.join(root,'.local/builds')+path.sep))throw Error('Expected an owned source-build record');
 const resolver=require(path.join(build,'app/theme.js')),data=await c.evaluate('window.OMARCHY_DATA'),apps=data.homeProfile.apps;
 const order=initial.cfg.appOrder||[],expected=apps.filter(a=>!(initial.cfg.hiddenApps||[]).includes(a.id)&&(a.id!=='tv'||initial.cfg.tvEnabled)).slice().sort((a,b)=>{
  const index=x=>order.includes(x.id)?order.indexOf(x.id):order.length+apps.indexOf(x);return index(a)-index(b);
 });
 changed=true;await c.evaluate('__OMARCHY_STATE.dockIdx=0;__OMARCHY_STATE.dockScroll=0;OmarchyTestAPI.switchWorkspace(0);true');
 const names=[];for(let i=0;i<expected.length;i++){names.push(await c.evaluate('document.getElementById("dock-app-name").textContent'));if(i<expected.length-1){key('right');await pause(350);}}
 assert.deepEqual(names,expected.map(a=>a.name),'real guest keyboard reaches the authored catalog');
 for(let i=1;i<expected.length;i++){key('left');await pause(350);}
 for(const theme of Object.keys(data.themes)){
  if(status().viewerClients){takeover=true;throw Error('Operator attached the viewer; automation stopped without further preference writes');}
  await c.evaluate('OmarchyTestAPI.setTheme('+JSON.stringify(theme)+');OmarchyTestAPI.openAllSettingsModal();true');await pause(150);
  const actual=await c.evaluate('(function(){var item=document.querySelector(".modal-item.focused");return {theme:__OMARCHY_CFG.theme,open:__OMARCHY_STATE.modalOpen,selected:!!item,popup:getComputedStyle(document.getElementById("modal-box")).backgroundColor,heading:getComputedStyle(document.getElementById("modal-title")).color,bg:item?getComputedStyle(item).backgroundColor:null,fg:item?getComputedStyle(item).color:null,border:item?getComputedStyle(item).borderLeftColor:null,weather:getComputedStyle(document.getElementById("wx-box")).display};})()');
  const roles=resolver.resolve(data.themes[theme]);assert.equal(actual.theme,theme);assert.equal(actual.open,true);assert.equal(actual.selected,true);
  assertRgba(actual.popup,roles.bgAlt,.95,theme+' popup');assert.equal(actual.heading,rgb(roles.accent),theme+' heading');
  assert.equal(actual.bg,rgb(roles.selection),theme+' selection');assert.equal(actual.fg,rgb(roles.selectionFg),theme+' selected foreground');assert.equal(actual.border,rgb(roles.focus),theme+' border');
  assert.equal(actual.weather,'none',theme+' hidden weather');
  if(['miasma','catppuccin','vantablack'].includes(theme))control('screenshot','smoke-'+theme+'-settings.png');
  results.push({theme,rolesChecked:6,legacyDisplayPreserved:true});key('escape');
  let closed=false;for(let n=0;n<40;n++){await pause(100);if(!await c.evaluate('__OMARCHY_STATE.modalOpen')){closed=true;break;}}
  assert.equal(closed,true,theme+': native Escape closes only the modal');await pause(200);
 }
 const runtimeErrors=c.events.filter(e=>e.method==='Runtime.exceptionThrown'||(e.method==='Console.messageAdded'&&e.params.message.level==='error'));
 fs.writeFileSync(path.join(base,'evidence/runtime-events.json'),JSON.stringify(c.events,null,2)+'\n');assert.equal(runtimeErrors.length,0,JSON.stringify(runtimeErrors));
 fs.writeFileSync(path.join(base,'evidence/ui-verification.json'),JSON.stringify({engine,display:[1920,1080],sourceCommit:installed.sourceCommit,packageSha256:installed.sha256,themes:results,roleComparisons:results.length*6,popupAlphaTolerance:1/255,dockEntriesReached:names.length,realKeyboardNavigation:true,realEscapeModalClose:true,disabledWeatherHidden:true,runtimeErrors,realTVTouched:false},null,2)+'\n');
 console.log('Passed Chromium 38: '+results.length+' themes · '+results.length*6+' exact RGB role checks · '+names.length+' keyboard-reachable app entries · no runtime errors.');
 }finally{
  if(c&&initial&&changed&&!takeover){
   await c.evaluate('(function(){var s='+JSON.stringify(initial.storage)+';localStorage.clear();Object.keys(s).forEach(function(k){localStorage.setItem(k,s[k]);});location.reload();return true;})()');await pause(2000);
   if(initial.state.ws===0&&!initial.state.modalOpen)await c.evaluate('__OMARCHY_STATE.dockIdx='+initial.state.dockIdx+';__OMARCHY_STATE.dockScroll='+initial.state.dockScroll+';OmarchyTestAPI.switchWorkspace(0);true');
   const restored=await c.evaluate('(function(){var s={};for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i);s[k]=localStorage.getItem(k);}return s;})()');assert.deepEqual(restored,initial.storage,'exact stored preferences restored');
  }
  if(c)c.close();
 }
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
