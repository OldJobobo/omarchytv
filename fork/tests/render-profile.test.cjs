const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {render,dataObject}=require('../render-profile.cjs');
function fixture(logo,check){
  const base=path.resolve(__dirname,'../../.local/test-tmp');fs.mkdirSync(base,{recursive:true});
  const dir=fs.mkdtempSync(path.join(base,'logo-'));
  try{
    const app=path.join(dir,'app'),profile=path.join(dir,'profile');fs.mkdirSync(app);fs.mkdirSync(profile);
    fs.writeFileSync(path.join(app,'data.js'),'window.OMARCHY_DATA = {"themes":{},"logo":"original"};');
    fs.writeFileSync(path.join(app,'homeprofile.js'),'exports.read=function(){return {}};');
    fs.writeFileSync(path.join(app,'theme.js'),'exports.resolve=function(){};');
    fs.writeFileSync(path.join(app,'index.html'),'');
    fs.writeFileSync(path.join(app,'appinfo.json'),'{"version":"1.0.0"}');
    fs.writeFileSync(path.join(app,'omarchy_themes.json'),'{}');
    fs.writeFileSync(path.join(profile,'catalog.json'),'{"wallpapers":{}}');
    fs.writeFileSync(path.join(profile,'profile.json'),JSON.stringify({schema:1,terminalLogo:logo}));
    check(()=>{render(app,profile);return dataObject(fs.readFileSync(path.join(app,'data.js'),'utf8')).logo;});
  }finally{fs.rmSync(dir,{recursive:true,force:true});}
}
test('optional terminal logo preserves stock branding',()=>fixture(undefined,run=>assert.equal(run(),'original')));
test('terminal logo retains exact authored block art',()=>fixture(' ███ \n█   █',run=>assert.equal(run(),' ███ \n█   █')));
test('terminal logo rejects malformed or unbounded data',()=>{
  for(const logo of ['', '   ', 42, 'x'.repeat(4097),'bad\u0000logo'])fixture(logo,run=>assert.throws(run,/Invalid terminal logo/));
});
