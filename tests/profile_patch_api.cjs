// Disposable Site profile only. No real participant, GPT call or event command.
const assert=require('node:assert/strict'),crypto=require('node:crypto');
const {registerHooks}=require('node:module'),fs=require('node:fs');
registerHooks({resolve(specifier,context,next){if(specifier.startsWith('.')&&!/\.[a-z]+$/.test(specifier)&&context.parentURL){const url=new URL(specifier+'.ts',context.parentURL);if(fs.existsSync(url))return next(url.href,context);}return next(specifier,context);}});
const base='http://127.0.0.1:5175',key=crypto.randomBytes(32).toString('base64url'),owner='anonymous:'+crypto.createHash('sha256').update(key).digest('hex');
const own={'X-Submission-Key':key,Origin:base,'Content-Type':'application/json'},admin={Authorization:'Bearer qa-profile-admin-only','Content-Type':'application/json'};
async function api(path,headers,body,method){const response=await fetch(base+path,{headers,method:method||(body?'POST':'GET'),...(body?{body:JSON.stringify(body)}:{})});return {status:response.status,data:await response.json()};}
(async()=>{try{
 const {emptyData,identityMarkdown,parseIdentityMarkdown}=await import('../onboarding_site/lib/identity.ts');const data=emptyData();Object.assign(data.identity,{name:'Synthetic profile patch',introduction:'Testing only',personal_seeking:'qwsqws',environment_need:'sqswq',reciprocity:'sqwsqws',moral_compass:'PRIVATE-VALUES'});delete data.memory.network_context;
 assert.equal((await api('/api/profile',own,{data,markdown:identityMarkdown(data.identity),status:'reviewed',consent:true})).status,200);
 const route='/api/organiser/contributions',read={action:'read',user_id:owner};assert.equal((await api(route,own,read)).status,401);
 const before=(await api(route,admin,read)).data.submission;
 const patch={personal_offer:'Model design and research support',personal_seeking:'Research collaborators',environment_need:'Practical feedback',reciprocity:'Knowledge exchange',skills:'Graph ML and computer vision',cv:'Brief relevant project context',source_website:'https://example.test'};
 const update={action:'patch',user_id:owner,expected_updated_at:before.updated_at,confirmed:true,patch};
 assert.equal((await api(route,admin,{...update,confirmed:false})).status,400);
 assert.equal((await api(route,admin,{...update,patch:{political_standing:'Override'}})).status,400);
 assert.equal((await api(route,admin,{...update,patch:{name:'Override'}})).status,400);
 assert.equal((await api(route,admin,update)).status,200);
 assert.equal((await api(route,admin,update)).status,409);
 const saved=(await api('/api/profile',own)).data,expected=structuredClone(data);Object.assign(expected.identity,patch);
 assert.deepEqual(saved.identity,expected.identity);assert.deepEqual(saved.budget,data.budget);assert.deepEqual(saved.memory,{...data.memory,network_context:false});assert.equal(saved.status,'reviewed');assert.deepEqual(parseIdentityMarkdown(saved.markdown),expected.identity);
 assert.ok(!/qwsqws|sqswq|sqwsqws/.test(saved.markdown));
 console.log('PASS authenticated profile patch, field restrictions, explicit confirmation, stale-write rejection, seven placeholder fields, Markdown/data consistency, and preserved private values, budget and memory. Synthetic profile only.');
}finally{await api('/api/profile',own,null,'DELETE');}})().catch(e=>{console.error(e);process.exitCode=1;});
