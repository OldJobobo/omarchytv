// Local build-time data composition. Never evaluates a device or data.js script.
const fs=require('node:fs'),path=require('node:path'),acorn=require('acorn');
const json=p=>JSON.parse(fs.readFileSync(p,'utf8'));
function dataObject(src){
  const ast=acorn.parse(src,{ecmaVersion:5});
  const assignment=ast.body.find(n=>n.type==='ExpressionStatement'&&n.expression.type==='AssignmentExpression'&&
    n.expression.left.type==='MemberExpression'&&n.expression.left.object.name==='window'&&n.expression.left.property.name==='OMARCHY_DATA');
  if(!assignment)throw Error('data.js assignment changed; review the upstream data seam');
  const value=assignment.expression.right;
  return JSON.parse(src.slice(value.start,value.end));
}
function render(app,profileDir){
  const profile=json(path.join(profileDir,'profile.json')),catalog=json(path.join(profileDir,'catalog.json'));
  if(profile.schema!==1)throw Error('Unsupported local profile schema');
  const api=require(path.join(app,'homeprofile.js')),home=api.read(profile.home);
  if(profile.home&&((profile.home.apps&&!home.apps)||(profile.home.inputs&&!home.inputs)))throw Error('Malformed Home profile catalog');
  const data=dataObject(fs.readFileSync(path.join(app,'data.js'),'utf8'));
  const themes=Object.assign({},data.themes);
  for(const name of profile.excludedThemes||[])delete themes[name];
  for(const [name,colors] of Object.entries(catalog.extraThemes||{})){
    if(!/^[a-z0-9-]+$/.test(name))throw Error('Invalid extra-theme identifier');
    for(const [key,value] of Object.entries(colors))if(key!=='mode'&&!/^#[0-9a-f]{6}$/i.test(value))throw Error('Invalid palette token: '+name+'.'+key);
    themes[name]=colors;
  }
  const wallpapers={};
  for(const name of Object.keys(themes))wallpapers[name]=catalog.wallpapers[name]||[];
  data.themes=themes;data.wallpapers=wallpapers;data.wallpaperIntros={};
  if(profile.terminalLogo!==undefined){
    if(typeof profile.terminalLogo!=='string'||!profile.terminalLogo.trim()||profile.terminalLogo.length>4096||/[\x00-\x09\x0b-\x1f\x7f]/.test(profile.terminalLogo))throw Error('Invalid terminal logo');
    data.logo=profile.terminalLogo;
  }
  const version=json(path.join(app,'appinfo.json')).version;data.version=version;data.homeProfile=profile.home||{};
  if(home.defaults&&home.defaults.theme&&!themes[home.defaults.theme])throw Error('Profile default theme is absent');
  fs.writeFileSync(path.join(app,'data.js'),'window.OMARCHY_DATA = '+JSON.stringify(data)+';\n');
  const old=json(path.join(app,'omarchy_themes.json'));
  old.themes=themes;old.wallpapers=wallpapers;old.wallpaperIntros={};
  fs.writeFileSync(path.join(app,'omarchy_themes.json'),JSON.stringify(old,null,2)+'\n');
  const info=json(path.join(app,'appinfo.json'));
  if(typeof profile.inspectable==='boolean')info.inspectable=profile.inspectable;
  fs.writeFileSync(path.join(app,'appinfo.json'),JSON.stringify(info,null,2)+'\n');
  // Check every entrypoint script, including profile data, against the real ES5 grammar.
  const html=fs.readFileSync(path.join(app,'index.html'),'utf8');
  const scripts=[...html.matchAll(/<script\b[^>]*src=["']([^"']+)["']/gi)].map(m=>m[1]);
  for(const script of scripts){
    if(/^(?:https?:)?\/\//i.test(script)||script.includes('..'))throw Error('Nonlocal entrypoint script: '+script);
    const file=path.join(app,script);if(!fs.existsSync(file))throw Error('Missing entrypoint script: '+script);
    acorn.parse(fs.readFileSync(file,'utf8'),{ecmaVersion:5,allowReserved:true});
  }
  const resolver=require(path.join(app,'theme.js'));
  for(const colors of Object.values(themes))resolver.resolve(colors);
  return {version,palettes:Object.keys(themes).length,wallpapers:Object.values(wallpapers).reduce((n,a)=>n+a.length,0),
    apps:home.apps?home.apps.length:null,inputs:home.inputs?home.inputs.length:null,entrypointScripts:scripts};
}
module.exports={dataObject,render};
if(require.main===module){try{console.log(JSON.stringify(render(path.resolve(process.argv[2]),path.resolve(process.argv[3]))));}
  catch(error){console.error(error.stack);process.exitCode=1;}}
