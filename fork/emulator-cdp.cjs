// Node 22+ client for this isolated VM only. No browser profile or LAN target.
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),base=path.join(root,'.local/emulator');
async function connect(app='com.omarchytv.home'){
 if(typeof WebSocket!=='function')throw Error('Use Node 22+ for the VM inspector client');
 const config=JSON.parse(fs.readFileSync(path.join(base,'config.json'),'utf8'));
 if(config.bind!=='127.0.0.1')throw Error('Only a localhost VM is supported');
 const port=config.ports.inspector;
 const targets=await(await fetch('http://127.0.0.1:'+port+'/json/list',{redirect:'error',signal:AbortSignal.timeout(5000)})).json();
 const matches=targets.filter(t=>t.type==='page'&&t.url.endsWith('/'+app+'/index.html'));
 if(matches.length!==1)throw Error('Expected one VM app target; found '+matches.length);
 const target=matches[0],u=new URL(target.webSocketDebuggerUrl);
 if(u.hostname!=='127.0.0.1'||Number(u.port)!==port)throw Error('Refusing a non-VM inspector target');
 const ws=new WebSocket(u.href),pending=new Map(),events=[];let id=0;
 await new Promise((ok,no)=>{const timer=setTimeout(()=>no(Error('VM inspector handshake timed out')),5000);ws.addEventListener('open',()=>{clearTimeout(timer);ok();},{once:true});ws.addEventListener('error',()=>{clearTimeout(timer);no(Error('VM inspector connection failed'));},{once:true});});
 ws.addEventListener('message',e=>{const m=JSON.parse(e.data),p=pending.get(m.id);if(p){pending.delete(m.id);clearTimeout(p.timer);m.error?p.no(Error(JSON.stringify(m.error))):p.ok(m.result);}else if(m.method&&events.length<1000)events.push(m);});
 function call(method,params={}){return new Promise((ok,no)=>{const n=++id,timer=setTimeout(()=>{pending.delete(n);no(Error('VM inspector timed out: '+method));},15000);pending.set(n,{ok,no,timer});ws.send(JSON.stringify({id:n,method,params}));});}
 async function evaluate(expression){const r=await call('Runtime.evaluate',{expression,returnByValue:true});if(r.wasThrown||r.exceptionDetails)throw Error(JSON.stringify(r));return r.result.value;}
 return{target,call,evaluate,events,close:()=>ws.close()};
}
module.exports={connect};
if(require.main===module)(async()=>{let c;try{c=await connect();const expression=process.argv[2]||'({title:document.title,userAgent:navigator.userAgent,hidden:document.hidden,theme:window.__OMARCHY_CFG&&window.__OMARCHY_CFG.theme})';console.log(JSON.stringify(await c.evaluate(expression),null,2));}
 catch(error){console.error(error.message);process.exitCode=1;}finally{if(c)c.close();}})();
