// Local-only disposable profiles and snapshots. No model calls or event commands.
const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs'),{spawnSync}=require('node:child_process');
const {registerHooks}=require('node:module');
registerHooks({resolve(specifier,context,next){if(specifier.startsWith('.')&&!/\.[a-z]+$/.test(specifier)&&context.parentURL){const url=new URL(specifier+'.ts',context.parentURL);if(fs.existsSync(url))return next(url.href,context);}return next(specifier,context);}});
const {chromium}=require('../.tools/node_modules/playwright');
const base=process.env.RECOVERY_TEST_ORIGIN||'http://127.0.0.1:5175',hostKey='test-host-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',bridgeKey='qa-residency-bridge-only';
const newKey=()=>crypto.randomBytes(32).toString('base64url'),owner=key=>'anonymous:'+crypto.createHash('sha256').update(key).digest('hex');
const keys=[newKey(),newKey()],owners=keys.map(owner),members=[crypto.randomUUID(),crypto.randomUUID()];
const own=key=>({'X-Submission-Key':key,Origin:base,'Content-Type':'application/json'}),host={Authorization:'Bearer '+hostKey,Origin:base,'Content-Type':'application/json'},route='/api/residency/recovery';
async function api(path,headers={},body,method){const response=await fetch(base+path,{headers,method:method||(body?'POST':'GET'),...(body?{body:JSON.stringify(body)}:{})});const text=await response.text();let data;try{data=JSON.parse(text);}catch{data={error:text};}return {status:response.status,data,cache:response.headers.get('Cache-Control')};}
const bridge=body=>api('/api/residency/bridge',{Authorization:'Bearer '+bridgeKey,'Content-Type':'application/json'},body);
const issue=n=>api(route,host,{action:'issue',member_id:members[n]});
const redeem=(code,key=newKey())=>api(route,{Origin:base,'Content-Type':'application/json'},{action:'redeem',code,access_key:key});
function dbProbe(action){
 const result=spawnSync('python3',['-c',`
import json,sqlite3,pathlib,sys
args=json.load(sys.stdin);matches=[]
for path in pathlib.Path('onboarding_site/.wrangler/state/v3/d1').rglob('*.sqlite'):
 c=sqlite3.connect(path)
 if c.execute("select count(*) from sqlite_master where name='resident_recovery_codes'").fetchone()[0]:matches.append(c)
 else:c.close()
assert len(matches)==1
c=matches[0];c.execute('PRAGMA foreign_keys=ON')
if args['action']=='expire':
 row=c.execute('select data from submissions where user_id=?',(args['owners'][0],)).fetchone()
 assert row and json.loads(row[0])['identity']['name'].startswith('Recovery test ')
 c.execute('update resident_recovery_codes set expires_at=0 where owner_id=?',(args['owners'][0],));c.commit()
print(json.dumps({'codes':[dict(zip(['owner','hash','created','expires','used'],r)) for r in c.execute('select * from resident_recovery_codes where owner_id in (?,?)',args['owners'])],'keys':[dict(zip(['hash','owner','created'],r)) for r in c.execute('select * from resident_access_keys where owner_id in (?,?)',args['owners'])]}))
c.close()
`],{encoding:'utf8',input:JSON.stringify({action,owners})});
 assert.equal(result.status,0,result.stderr);return JSON.parse(result.stdout);
}
(async()=>{let browser;const errors=[];try{
 const {emptyData,identityMarkdown}=await import('../onboarding_site/lib/identity.ts');const profiles=[];
 for(let n=0;n<2;n++){const data=emptyData();Object.assign(data.identity,{name:'Recovery test '+n,nickname:'Same nickname',introduction:'Synthetic recovery fixture',moral_compass:'PRIVATE-IDENTITY-'+n});data.memory.network_context=false;profiles.push(data);assert.equal((await api('/api/profile',own(keys[n]),{data,markdown:identityMarkdown(data.identity),status:'reviewed',consent:true})).status,200);}
 const directory=members.map((id,n)=>({id,name:profiles[n].identity.name})),event={status:'idle',calls:0,completed_calls:0,worker_count:0,max_calls:null},cycle={phase:'idle',day:0};
 const snapshots=[{owner_id:'host',data:{role:'host',directory,event,cycle,agents:members.map((id,n)=>({member_id:id,name:profiles[n].identity.name}))}}];
 for(let n=0;n<2;n++)snapshots.push({owner_id:owners[n],data:{role:'resident',directory,event,cycle,agent:{member_id:members[n],name:profiles[n].identity.name},wallet:{limit_usd:10,spent_usd:0,held_usd:0,remaining_usd:10,total_tokens:0,state:'active'},notes:[{id:'n'+n,memory:'PRIVATE-MEMORY-'+n,sources:[]}],network_context:false,identity_markdown:identityMarkdown(profiles[n].identity),messages:[]}});
 assert.equal((await bridge({action:'publish',snapshots})).status,200);const commandsBefore=(await api('/api/residency',host)).data.commands;
 for(const headers of [{Origin:base,'Content-Type':'application/json'},own(keys[0]),{...host,Authorization:'Bearer '+bridgeKey}])assert.equal((await api(route,headers,{action:'issue',member_id:members[0]})).status,401);
 assert.equal((await api(route,{...host,Origin:'https://other.example'},{action:'issue',member_id:members[0]})).status,403);
 assert.equal((await api(route,host,{action:'issue',member_id:members[0],owner_id:owners[1]})).status,400);
 assert.equal((await api(route,host,{action:'issue',member_id:profiles[0].identity.name})).status,404);
 assert.equal((await api(route,host,{action:'issue',member_id:'host'})).status,404);
 assert.equal((await redeem('Same nickname')).status,400);
 const old=await issue(0),replacement=await issue(0);assert.equal(old.status,200);assert.equal(replacement.status,200);assert.equal(old.cache,'no-store');assert.notEqual(old.data.code,replacement.data.code);
 assert.equal((await redeem(old.data.code)).status,400);
 assert.equal((await api(route,{Origin:'https://other.example','Content-Type':'application/json'},{action:'redeem',code:replacement.data.code,access_key:newKey()})).status,403);
 // Known original keys cannot be remapped to another identity or consume a code.
 assert.equal((await redeem(replacement.data.code,keys[1])).status,400);
 const candidateKeys=Array.from({length:8},()=>newKey());
 const raced=await Promise.all(candidateKeys.map(k=>redeem(replacement.data.code,k)));assert.equal(raced.filter(r=>r.status===200).length,1);
 const recovered=candidateKeys[raced.findIndex(r=>r.status===200)];assert.equal((await redeem(replacement.data.code)).status,400);
 const mine=await api('/api/residency?owner_id='+owners[1],own(recovered));assert.equal(mine.status,200);assert.ok(JSON.stringify(mine.data).includes('PRIVATE-MEMORY-0'));assert.ok(!JSON.stringify(mine.data).includes('PRIVATE-MEMORY-1'));
 const profile=(await api('/api/profile',own(recovered))).data;assert.deepEqual(profile.identity,profiles[0].identity);assert.equal(profile.memory.network_context,false);
 assert.equal((await api('/api/residency',own(recovered),{kind:'start',request_id:crypto.randomUUID(),confirmed:true})).status,400);
 assert.equal((await api(route,own(recovered),{action:'issue',member_id:members[1]})).status,401);
 const snapshot=dbProbe('read');assert.equal(snapshot.keys.length,1);assert.ok(snapshot.codes[0].used);assert.ok(!JSON.stringify(snapshot).includes(replacement.data.code));assert.ok(!JSON.stringify(snapshot).includes(recovered));
 const expired=await issue(0);dbProbe('expire');assert.equal((await redeem(expired.data.code)).status,400);
 // Browser recovery even after onboarding created an unrelated unsaved local key.
 browser=await chromium.launch({headless:true,args:['--no-sandbox']});const hostPage=await browser.newPage();hostPage.on('pageerror',e=>errors.push(e.message));await hostPage.goto(base+'/simulation#host='+hostKey);
 const card=hostPage.locator('.live-resident-grid article').filter({has:hostPage.getByRole('heading',{name:profiles[0].identity.name,exact:true})});await card.getByRole('button',{name:'Create recovery code',exact:true}).click();const codeInput=card.getByLabel('Recovery code for '+profiles[0].identity.name,{exact:true});await codeInput.waitFor();const code=await codeInput.inputValue();assert.ok(code);
 const page=await browser.newPage({viewport:{width:390,height:844}});page.on('pageerror',e=>errors.push(e.message));await page.goto(base);await page.getByLabel('Name',{exact:true}).waitFor();const unrelated=await page.evaluate(()=>localStorage.getItem('zugrama-private-draft-v1'));await page.goto(base+'/resident');await page.getByText('Lost your link? Recover access',{exact:true}).click();await page.getByLabel('One-time recovery code',{exact:true}).fill(code);await page.getByRole('button',{name:'Recover my agent',exact:true}).click();await page.getByRole('heading',{name:profiles[0].identity.name+'’s agent.',exact:true}).waitFor();await page.getByText('PRIVATE-MEMORY-0',{exact:true}).waitFor();assert.ok(!(await page.locator('body').textContent()).includes('PRIVATE-MEMORY-1'));
 const savedKey=await page.evaluate(()=>localStorage.getItem('zugrama-private-draft-v1'));assert.notEqual(savedKey,unrelated);assert.notEqual(savedKey,keys[0]);assert.equal(await page.getByRole('button',{name:'Start event ↗',exact:true}).count(),0);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.reload();await page.getByRole('heading',{name:profiles[0].identity.name+'’s agent.',exact:true}).waitFor();await page.goto(base);await page.getByLabel('Name',{exact:true}).waitFor();assert.equal(await page.getByLabel('Name',{exact:true}).inputValue(),profiles[0].identity.name);
 await hostPage.setViewportSize({width:390,height:844});assert.equal(await hostPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.deepEqual(errors,[]);
 assert.deepEqual((await api('/api/residency',host)).data.commands,commandsBefore);assert.equal((await api('/api/residency',host)).data.snapshot.event.calls,0);
 // Existing original access remains valid; source records and privacy choices unchanged.
 assert.deepEqual((await api('/api/profile',own(keys[0]))).data.identity,profiles[0].identity);
 fs.writeFileSync('test-results/resident-recovery.json',JSON.stringify({passed:true,synthetic_only:true,model_calls:0,event_started:false,host_issuance:true,expiry:true,single_use:true,concurrent_redemptions:8,successful_race_redemptions:1,private_context:true,source_unchanged:true,original_key_preserved:true,browser_recovery:true,mobile:true},null,2));
 console.log('PASS host-issued recovery, authorization and CSRF, code replacement and expiry, eight-way single-use race, hashed storage, cross-resident isolation, existing identity/memory/privacy, browser persistence, onboarding access and mobile. No model calls or event commands.');
}finally{if(browser)await browser.close();for(const k of keys)await api('/api/profile',own(k),undefined,'DELETE');await bridge({action:'publish',snapshots:[]});const remaining=dbProbe('read');assert.equal(remaining.codes.length,0);assert.equal(remaining.keys.length,0);}})().catch(e=>{console.error(e);process.exitCode=1;});
