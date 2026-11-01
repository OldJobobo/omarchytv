/* Optional authored Home data. ES5, no I/O, timers, credentials or device assumptions.
 * DATA.homeProfile supplies fallback catalogs/defaults; saved preferences and
 * platform-installed-app adapters retain their existing precedence. */
(function(root){
  "use strict";
  function plain(v){return v && typeof v==="object" && !Array.isArray(v);}
  function id(v){return typeof v==="string" && /^[A-Za-z0-9_.@-]{1,128}$/.test(v);}
  function text(v){return typeof v==="string" && v.length>0 && v.length<=128 && !/[\x00-\x1f]/.test(v) ? v.replace(/[<>&"]/g,"") : null;}
  function color(v){return typeof v==="string" && /^#[0-9a-f]{6}$/i.test(v);}
  function catalog(value,inputs){
    if(!Array.isArray(value)||!value.length||value.length>(inputs?16:64))return null;
    var out=[],seen=Object.create(null);
    for(var i=0;i<value.length;i++){
      var a=value[i];if(!plain(a)||!id(a.id)||!id(a.appId)||!text(a.name)||seen[a.id])return null;
      seen[a.id]=true;var item={id:a.id,name:text(a.name),appId:a.appId};
      if(text(a.sub))item.sub=text(a.sub);
      if(!inputs){if(id(a.brand))item.brand=a.brand;if(color(a.bg))item.bg=a.bg;if(color(a.fg))item.fg=a.fg;}
      out.push(item);
    }
    return out;
  }
  function read(raw){
    if(!plain(raw)||(raw.schema!==undefined&&raw.schema!==1))return {};
    return {apps:catalog(raw.apps,false),inputs:catalog(raw.inputs,true),
      defaults:plain(raw.defaults)?raw.defaults:{},
      terminalSummary:typeof raw.terminalSummary==="string" && raw.terminalSummary.length<=1024 ? raw.terminalSummary : ""};
  }
  function defaults(base,overrides){
    var out={},p=plain(overrides)?overrides:{};
    Object.keys(base).forEach(function(k){
      var value=base[k],v=Object.prototype.hasOwnProperty.call(p,k)?p[k]:undefined;
      if(k==="widgets"){
        out[k]={};Object.keys(value).forEach(function(w){out[k][w]=plain(v)&&typeof v[w]==="boolean"?v[w]:value[w];});
      }else if(Array.isArray(value)){
        out[k]=Array.isArray(v)&&v.every(id)?v.slice():value.slice();
      }else if(typeof value==="number")out[k]=typeof v==="number"&&isFinite(v)?v:value;
      else if(typeof value==="boolean")out[k]=typeof v==="boolean"?v:value;
      else if(typeof value==="string"){
        out[k]=typeof v==="string"&&v.length<=2048?v:value;
        if(k==="promptUser"||k==="promptHost")out[k]=out[k].replace(/[<>&"\x00-\x1f]/g,"");
      }else out[k]=value;
    });
    return out;
  }
  function apps(stock,items){
    return items.map(function(a){
      var look=stock.filter(function(s){return s.id===a.id||s.brand===(a.brand||a.id);})[0]||{},out={};
      Object.keys(look).forEach(function(k){out[k]=look[k];});Object.keys(a).forEach(function(k){out[k]=a[k];});return out;
    });
  }
  var api={read:read,defaults:defaults,apps:apps};
  if(typeof module!=="undefined"&&module.exports)module.exports=api;else root.OmarchyHomeProfile=api;
})(typeof window!=="undefined"?window:this);
