const assert=require('node:assert/strict'),fs=require('node:fs'),{chromium}=require('../.tools/node_modules/playwright');
const base='http://127.0.0.1:7396',code='11111111-22222222-33333333-44444444';
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 for(const mode of ['resident','host']){
  const context=await browser.newContext({viewport:{width:390,height:844}}),p=await context.newPage(),posts=[],errors=[];p.setDefaultTimeout(20000);p.on('pageerror',e=>errors.push(e.message));let key='';
  await p.route('**/api/residency/recovery',async route=>{const payload=route.request().postDataJSON();posts.push(payload);assert.equal(payload.action,'redeem');assert.equal(payload.code,code);assert.match(payload.access_key,/^[A-Za-z0-9_-]{43}$/);key=payload.access_key;await route.fulfill({json:{restored:true}});});
  await p.route('**/api/residency',async route=>{assert.equal(route.request().headers()['x-submission-key'],key);await route.fulfill({json:{snapshot:{role:'resident',agent:{member_id:'a',name:'Recovery entry fixture'},event:{status:'running',calls:2,completed_calls:2,worker_count:2,event_id:'fixture'},cycle:{phase:'awake',day:1},directory:[],notes:[],messages:[]},commands:[],heartbeat_at:Date.now()}});});
  await p.goto(base+(mode==='host'?'/simulation':'/resident'));await p.locator('#access-link').fill(code);await p.getByRole('button',{name:mode==='host'?'Open host controls ↗':'Open my agent ↗',exact:true}).click();
  if(mode==='host'){await p.waitForURL('**/resident*');await p.getByLabel('One-time recovery code',{exact:true}).waitFor();assert.equal(await p.getByLabel('One-time recovery code',{exact:true}).inputValue(),code);assert.equal(posts.length,0);assert.ok(!p.url().includes(code));await p.getByRole('button',{name:'Recover my agent',exact:true}).click();}
  await p.getByRole('heading',{name:'Recovery entry fixture’s agent.',exact:true}).waitFor().catch(async e=>{console.log({mode,errors,body:(await p.locator('body').innerText()).slice(0,1800)});throw e;});assert.equal(posts.length,1);assert.equal(await p.getByRole('button',{name:'Start event ↗',exact:true}).count(),0);assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.deepEqual(errors,[]);await context.close();
 }
 console.log('PASS main resident field redeems recovery codes; host entry routes to prefilled resident recovery without automatic redemption; no host controls or simulation commands.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
