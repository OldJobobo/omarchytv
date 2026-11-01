const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const Profile=require('../app/homeprofile.js');
// Reuse the existing fake-DOM boot without registering that file's test cases.
const source=fs.readFileSync(path.join(__dirname,'tizen-apps.test.js'),'utf8');
const marker=source.indexOf('const SAMSUNG = [');assert.ok(marker>0);
const harness={require,__dirname,console,module:{exports:{}}};
vm.runInNewContext(source.slice(0,marker)+'\nmodule.exports={boot,fakeTizen};',harness);
const {boot,fakeTizen}=harness.module.exports;
const profile={schema:1,apps:[{id:'player',name:'Local Player',appId:'org.example.player',brand:'netflix'},
  {id:'utility',name:'Utility',appId:'org.example.utility',bg:'#102030',fg:'#abcdef'}],
  inputs:[{id:'input-one',name:'Input One',appId:'com.example.input1'},{id:'input-two',name:'Input Two',appId:'com.example.input2'}],
  defaults:{theme:'miasma',randomTheme:false,randomWallpaper:false,textScale:1.15,widgets:{weather:false}},
  terminalSummary:'apps 2 local entries'};

test('missing/unknown profiles do not change factory behavior',()=>{
  assert.deepEqual(Profile.read(null),{});assert.deepEqual(Profile.read({schema:2}),{});
  assert.equal(Profile.read({apps:[]}).apps,null);
  const t=boot();assert.equal(t.focusedName(),'TV');
});
test('invalid catalogs fail closed rather than partially changing the dock',()=>{
  const duplicate=[profile.apps[0],profile.apps[0]];
  assert.equal(Profile.read({apps:duplicate}).apps,null);
  assert.equal(Profile.read({apps:[{id:'x',name:'X',appId:'bad;command'}]}).apps,null);
  assert.equal(Profile.read({inputs:[{id:'x',name:'X'}]}).inputs,null);
});
test('profile strings/styles cannot inject markup or remote CSS resources',()=>{
  const p=Profile.read({apps:[{id:'x',name:'<Label>',appId:'org.example.x',bg:'url(https://example.invalid)',fg:'#112233'}]});
  assert.equal(p.apps[0].name,'Label');assert.equal(p.apps[0].bg,undefined);assert.equal(p.apps[0].fg,'#112233');
});
test('defaults retain known types, merge widgets, and reject unknown/prototype keys',()=>{
  const base={theme:'stock',textScale:1,enabled:true,widgets:{term:true,weather:true},appOrder:[]};
  const raw=JSON.parse('{"theme":"custom","textScale":"huge","enabled":false,"widgets":{"weather":false},"unknown":1,"__proto__":{"polluted":true}}');
  const d=Profile.defaults(base,raw);
  assert.equal(d.theme,'custom');assert.equal(d.textScale,1);assert.equal(d.enabled,false);
  assert.deepEqual(d.widgets,{term:true,weather:false});assert.equal(d.unknown,undefined);assert.equal(d.polluted,undefined);
  d.widgets.term=false;assert.equal(base.widgets.term,true);
});
test('brand appearances are inherited without mutating the source catalogs',()=>{
  const stock=[{id:'netflix',brand:'netflix',bg:'#123456',fg:'#eeeeee'}],copy=JSON.stringify(stock);
  const apps=Profile.apps(stock,Profile.read(profile).apps);
  assert.equal(apps[0].bg,'#123456');assert.equal(apps[0].name,'Local Player');assert.equal(JSON.stringify(stock),copy);
});
test('authored fallback catalogs and fresh defaults reach the real app',()=>{
  const t=boot({profile});assert.equal(t.tiles().length,2);assert.equal(t.focusedName(),'Local Player');
  assert.match(t.tiles()[0].innerHTML,/#e50914/,'known brand colors retained');
  assert.equal(t.ctx.__OMARCHY_CFG.theme,'miasma');assert.equal(t.ctx.__OMARCHY_CFG.textScale,1.15);
  assert.equal(t.ctx.__OMARCHY_CFG.widgets.weather,false);assert.equal(t.ctx.__OMARCHY_CFG.widgets.term,true);
  t.ctx.OmarchyTestAPI.switchWorkspace(1);assert.equal(t.inputTiles().length,2);
});
test('saved user settings win over profile defaults',()=>{
  const t=boot({profile,cfg:{theme:'nord',randomTheme:false,randomWallpaper:false,textScale:1,widgets:{term:false,weather:true}}});
  assert.equal(t.ctx.__OMARCHY_CFG.theme,'nord');assert.equal(t.ctx.__OMARCHY_CFG.textScale,1);
  assert.equal(t.ctx.__OMARCHY_CFG.widgets.weather,true);
});
test('optional terminal summary uses text and the real source app version',()=>{
  const t=boot({profile:{...profile,terminalSummary:'<local summary>'}});
  assert.match(t.terminalInfo(),/theme miasma\n<local summary>\nOmarchyTV 2\.13\.9/);
  assert.doesNotMatch(t.terminalInfo(),/Wi-Fi|42 min/);
});
test('installed Tizen app/source adapters still supersede authored fallbacks',()=>{
  const t=boot({profile,tizen:fakeTizen(),apps:[{id:'real',name:'Installed',tizenId:'installed.id'}],inputs:[{id:'actual',name:'Actual'}]});
  assert.equal(t.focusedName(),'Installed');t.ctx.OmarchyTestAPI.switchWorkspace(1);assert.equal(t.inputTiles().length,1);
});
