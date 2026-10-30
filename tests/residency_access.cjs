// Local-only Sites + real Python bridge integration. All inference is synthetic.
const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const {registerHooks}=require('node:module');
registerHooks({resolve(specifier,context,next){if(specifier.startsWith('.')&&!/\.[a-z]+$/.test(specifier)&&context.parentURL){const url=new URL(specifier+'.ts',context.parentURL);if(fs.existsSync(url))return next(url.href,context);}return next(specifier,context);}});
const {chromium}=require('../.tools/node_modules/playwright');
const base='http://127.0.0.1:5175',hostKey='test-host-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',bridgeKey='qa-residency-bridge-only';
const keys=[crypto.randomBytes(32).toString('base64url'),crypto.randomBytes(32).toString('base64url')],owners=keys.map(k=>'anonymous:'+crypto.createHash('sha256').update(k).digest('hex'));
const header=key=>({'X-Submission-Key':key,Origin:base,'Content-Type':'application/json'}),hostHeaders={Authorization:'Bearer '+hostKey,Origin:base,'Content-Type':'application/json'};
async function api(route,headers,body){const response=await fetch(base+route,{headers,...(body===undefined?{}:{method:'POST',body:JSON.stringify(body)})});const raw=await response.text();let data;try{data=JSON.parse(raw);}catch{data={error:raw};}return {status:response.status,data};}
const bridge=body=>api('/api/residency/bridge',{Authorization:'Bearer '+bridgeKey,'Content-Type':'application/json'},body);
async function until(action,test){const stop=Date.now()+45000;while(Date.now()<stop){const value=await action();if(test(value))return value;await new Promise(r=>setTimeout(r,200));}throw Error('Timed out waiting for bridge state');}
(async()=>{let child,browser;try{
 const {emptyData,identityMarkdown}=await import('../onboarding_site/lib/identity.ts');const records=[];
 for(let n=0;n<2;n++){
  const data=emptyData();data.identity.name=n?'Access B':'Access A';data.identity.nickname=n?'B':'A';data.identity.introduction='Synthetic access test only.';data.identity.moral_compass=n?'PRIVATE-B-IDENTITY':'PRIVATE-A-IDENTITY';
  const status=n?'reviewed':'draft',markdown=n?identityMarkdown(data.identity):'';
  const saved=await api('/api/profile',header(keys[n]),{data,markdown,status,consent:!!n});assert.equal(saved.status,200);
  records.push({user_id:owners[n],status,data:JSON.stringify(data),markdown,updated_at:saved.data.updated_at,...(!n?{host_review:{approved:true,note:'Host approved this synthetic saved draft for the access test.'}}:{})});
 }
 assert.equal((await api('/api/residency',header(keys[0]))).status,403);
 assert.equal((await api('/api/residency',{})).status,401);assert.equal((await api('/api/residency/bridge',header(keys[0]),{action:'claim'})).status,401);
 const directory=[{id:'a',name:'Access A'},{id:'b',name:'Access B'}];
 const published=await bridge({action:'publish',snapshots:[{owner_id:'host',data:{role:'host',directory}},{owner_id:owners[0],data:{role:'resident',agent:{member_id:'a'},directory,secret:'PRIVATE-A-IDENTITY'}},{owner_id:owners[1],data:{role:'resident',agent:{member_id:'b'},directory,secret:'PRIVATE-B-IDENTITY'}}]});assert.equal(published.status,200,JSON.stringify(published.data));
 assert.equal((await api('/api/residency',header(keys[0]))).status,403);
 assert.equal((await bridge({action:'publish',owners:['host',...owners],snapshots:[{owner_id:owners[0],data:{role:'resident',agent:{member_id:'a'},directory,secret:'PRIVATE-A-IDENTITY',enrollment:{basis:'host_reviewed_draft',source_status:'draft'}}}]})).status,200);
 // A partial upload retains the other owner's snapshot and leaves it private.
 const completeOwners=['host',...owners];
 assert.equal((await bridge({action:'publish',owners:completeOwners,snapshots:[{owner_id:'host',data:{role:'host',directory}}]})).status,200);
 assert.ok(JSON.stringify((await api('/api/residency',header(keys[1]))).data).includes('PRIVATE-B-IDENTITY'));
 assert.equal((await bridge({action:'publish',owners:['host'],snapshots:[{owner_id:owners[0],data:{}}]})).status,400);
 const mine=await api('/api/residency?owner_id='+owners[1],header(keys[0]));assert.ok(JSON.stringify(mine.data).includes('PRIVATE-A-IDENTITY'));assert.ok(!JSON.stringify(mine.data).includes('PRIVATE-B-IDENTITY'));
 assert.equal((await api('/api/residency',header(keys[0]),{kind:'start',request_id:crypto.randomUUID(),max_calls:1,confirmed:true})).status,400);
 assert.equal((await api('/api/residency',header(keys[0]),{kind:'request',request_id:crypto.randomUUID(),body:'Bad override',owner_id:owners[1]})).status,400);
 const command={kind:'request',request_id:crypto.randomUUID(),body:'A deduplicated local API request',target_id:'b'};
 const responses=await Promise.all(Array.from({length:4},()=>api('/api/residency',header(keys[0]),command)));assert.equal(new Set(responses.map(r=>r.data.id)).size,1);
 const claims=await Promise.all([bridge({action:'claim'}),bridge({action:'claim'})]);const jobs=claims.map(r=>r.data.job).filter(Boolean);assert.equal(jobs.length,1);assert.equal(jobs[0].owner_id,owners[0]);assert.equal(jobs[0].payload.body,command.body);
 assert.equal((await bridge({action:'complete',id:jobs[0].id,lease_token:'wrong',status:'completed',result:{message:'bad'}})).data.saved,false);
 assert.equal((await bridge({action:'complete',id:jobs[0].id,lease_token:jobs[0].lease_token,status:'completed',result:{message:'Local API check complete'}})).data.saved,true);
 assert.equal((await api('/api/residency',hostHeaders,{kind:'start',request_id:crypto.randomUUID(),max_calls:2,npc_enabled:true,seven_days:false,confirmed:false})).status,400);
 assert.equal((await api('/api/residency',{'X-Submission-Key':keys[0],Origin:'https://other.example','Content-Type':'application/json'},command)).status,403);
 fs.writeFileSync('test-results/site-bridge-records.json',JSON.stringify(records));
 child=spawn('python3',['-B','scripts/site_bridge_fixture.py','--records',path.resolve('test-results/site-bridge-records.json'),'--report',path.resolve('test-results/site-bridge-fixture.json')],{cwd:process.cwd(),stdio:['ignore','pipe','pipe']});let output='';child.stdout.on('data',b=>output+=b);child.stderr.on('data',b=>output+=b);await until(async()=>{if(child.exitCode!==null)throw Error(output);return output;},s=>s.includes('BRIDGE_FIXTURE_READY'));
 await until(()=>api('/api/residency',header(keys[0])),r=>r.data.snapshot?.agent?.name==='Access A');
 browser=await chromium.launch({headless:true,args:['--no-sandbox']});const resident=await browser.newPage({viewport:{width:1280,height:900}});const errors=[];resident.on('pageerror',e=>errors.push(e.message));
 await resident.goto(base+'/resident#draft='+keys[0]);await resident.getByRole('heading',{name:'Ask your agent',exact:true}).waitFor();assert.ok(!resident.url().includes(keys[0]));assert.equal(await resident.getByRole('button',{name:'Start event ↗',exact:true}).count(),0);assert.ok(!(await resident.locator('body').textContent()).includes('PRIVATE-B-IDENTITY'));await resident.getByText('The organiser enrolled your agent from your saved draft.',{exact:false}).waitFor();
 await resident.getByLabel('Your request',{exact:true}).fill('PRIVATE-A-REQUEST: please explore this idea.');await resident.getByRole('button',{name:'Send to my agent ↗',exact:true}).click();
 await until(()=>api('/api/residency',header(keys[0])),r=>r.data.snapshot?.requests?.some(q=>q.body.includes('PRIVATE-A-REQUEST')));
 assert.equal((await api('/api/residency',header(keys[0]))).data.snapshot.event.calls,0);
 await api('/api/residency',header(keys[1]),{kind:'request',request_id:crypto.randomUUID(),body:'PRIVATE-B-REQUEST: an independent private idea',target_id:null});
 await until(()=>api('/api/residency',header(keys[1])),r=>r.data.snapshot?.requests?.some(q=>q.body.includes('PRIVATE-B-REQUEST')));
 const b=await api('/api/residency',header(keys[1]));assert.ok(!JSON.stringify(b.data).includes('PRIVATE-A-REQUEST'));
 const host=await browser.newPage();host.on('pageerror',e=>errors.push(e.message));await host.goto(base+'/simulation#host='+hostKey);await host.getByRole('heading',{name:'Host controls',exact:true}).waitFor();assert.ok(!host.url().includes(hostKey));
 const start=host.getByRole('button',{name:'Start event ↗',exact:true});assert.equal(await start.isDisabled(),true);assert.equal(await host.getByLabel('Maximum calls per day',{exact:true}).count(),0);await host.getByRole('checkbox',{name:'Seven simulated days',exact:true}).uncheck();await host.getByRole('checkbox',{name:'I am ready to start this networking event.',exact:true}).check();await start.click();
 await until(()=>api('/api/residency',hostHeaders),r=>r.data.snapshot?.event?.completed_calls===6&&r.data.snapshot.event.worker_count===0);
 await until(()=>api('/api/residency',header(keys[0])),r=>r.data.snapshot?.notes?.length>0);await resident.getByText('A synthetic conversation about shared interests.',{exact:true}).first().waitFor();
 await resident.getByRole('heading',{name:'Your network',exact:true}).waitFor();await resident.getByRole('heading',{name:'Topics visited',exact:true}).waitFor();await resident.getByRole('heading',{name:'Information flow',exact:true}).waitFor();
 const insight=(await api('/api/residency',header(keys[0]))).data.snapshot.insights;assert.ok(insight.windows[0].topics.length);assert.ok(insight.windows[0].graph.edges.length);assert.ok(insight.windows[0].timeline.length);
 await resident.locator('.activity-directory button').first().click();await resident.getByRole('button',{name:'Ask my agent to approach',exact:true}).waitFor();
 await resident.getByRole('button',{name:'5 min',exact:true}).click();assert.equal(await resident.getByRole('button',{name:'5 min',exact:true}).getAttribute('aria-pressed'),'true');
 await host.getByRole('heading',{name:'Communication over time',exact:true}).waitFor();await host.getByLabel('Sliding window',{exact:true}).selectOption('60');
 await resident.setViewportSize({width:390,height:844});assert.equal(await resident.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await resident.screenshot({path:'test-results/resident-access-mobile.png',fullPage:true});
 await host.setViewportSize({width:390,height:844});assert.equal(await host.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await host.screenshot({path:'test-results/host-access-mobile.png',fullPage:true});assert.deepEqual(errors,[]);
 await resident.getByRole('heading',{name:'Research & code',exact:true}).waitFor();await resident.getByRole('heading',{name:'Synthetic shared board',exact:true}).first().waitFor();assert.ok(await resident.locator('.board-drawing circle').count());assert.ok(await resident.locator('.board-equation .katex').count());assert.equal(await resident.locator('a[href^="javascript:"]').count(),0);assert.equal(await resident.locator('#shared-boards script').count(),0);
 const ownTools=(await api('/api/residency',header(keys[0]))).data.snapshot;assert.equal(ownTools.capabilities.python_run,true);assert.equal(ownTools.tool_runs.length,3);assert.ok(JSON.stringify(ownTools.tool_runs).includes('PRIVATE-CODE-0'));assert.ok(!JSON.stringify(ownTools).includes('PRIVATE-CODE-1'));assert.ok(ownTools.boards.length);
 const report=JSON.parse(fs.readFileSync('test-results/site-bridge-fixture.json'));assert.equal(report.real_model_calls,0);assert.equal(report.fake_model_calls,6);assert.equal(report.private_context_checks_passed,true);
 console.log('PASS resident isolation, host-only controls, uncapped Start, six fake networking calls, real sandboxed Python, synthetic search, private results retrieved by own agent, witnessed shared boards, safe equations and SVG, notes, graph and mobile UI. No real event or GPT inference.');
}finally{if(browser)await browser.close();if(child&&child.exitCode===null){child.kill('SIGTERM');await new Promise(r=>child.once('exit',r));}for(const key of keys){await fetch(base+'/api/profile',{method:'DELETE',headers:header(key)});}await bridge({action:'publish',snapshots:[]});}})().catch(e=>{console.error(e);process.exitCode=1;});
