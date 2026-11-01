const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app/compat.js'), 'utf8');

for (const display of ['none', 'flex', 'inline-flex', '']) {
  test('legacy theme rewrites preserve runtime display=' + JSON.stringify(display), () => {
    const attrs = {style:'color:var(--t-accent)'};
    const overlay = {
      nodeType:1,style:{display:''},querySelectorAll:()=>[],
      getAttribute:k=>attrs[k] || null,
      setAttribute(k,v) {attrs[k]=v;if(k==='style')this.style.display='';}
    };
    const style = {textContent:':root{--t-accent:#123456}.box{color:var(--t-accent)}'};
    const timers = [];
    function Declaration() {}
    Declaration.prototype.setProperty = function() {};
    const supports = {supports:()=>false};
    const body = {nodeType:1,style:{display:''},querySelectorAll:()=>[overlay],getAttribute:()=>null};
    const ctx = {window:{CSS:supports,fetch(){},addEventListener(){}},CSS:supports,
      CSSStyleDeclaration:Declaration,document:{body,querySelector:()=>style,querySelectorAll:()=>[]},
      MutationObserver:function(){this.observe=function(){};},setTimeout:f=>timers.push(f)};
    vm.runInNewContext(source,ctx);
    assert.equal(attrs['data-compat-style'],'color:var(--t-accent)');
    overlay.style.display=display;
    new Declaration().setProperty('--t-accent','#abcdef');
    while(timers.length)timers.shift()();
    assert.equal(overlay.style.display,display);
    assert.equal(attrs.style,'color:#abcdef');
    overlay.style.display=display==='none'?'flex':'none';
    const next=overlay.style.display;
    new Declaration().setProperty('--t-accent','#fedcba');
    while(timers.length)timers.shift()();
    assert.equal(overlay.style.display,next,'subsequent visibility changes are preserved too');
  });
}
