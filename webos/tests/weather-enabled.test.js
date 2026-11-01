const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const src = fs.readFileSync(path.join(__dirname,'../app/app.js'),'utf8');
const start = src.indexOf('  function fetchWeather() {');
const end = src.indexOf('\n  // DEFAULT_APPS sorted',start);
assert.ok(start>=0 && end>start,'weather function seam moved; inspect before updating the fixture');
const fn = src.slice(start,end);
for(const enabled of [false,undefined,true]) {
  test('weather fetch is '+(enabled?'enabled':'disabled')+' when widgets.weather='+enabled,()=>{
    const calls=[];
    const ctx={cfg:{widgets:{weather:enabled},weatherLat:1,weatherLon:2},
      fetch:url=>{calls.push(url);return new Promise(()=>{});}};
    vm.runInNewContext(fn+'\nfetchWeather();',ctx);
    assert.equal(calls.length,enabled?1:0);
    if(enabled)assert.match(calls[0],/^https:\/\/api\.open-meteo\.com\/v1\/forecast\?/);
  });
}
