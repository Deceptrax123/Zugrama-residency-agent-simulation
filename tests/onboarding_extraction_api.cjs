// Synthetic local D1/R2 integration. No provider calls or actual resident data.
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const fs=require('node:fs');
const base='http://127.0.0.1:5175';
const worker={Authorization:'Bearer qa-extraction-worker-only','Content-Type':'application/json'};
const draft=key=>({'X-Submission-Key':key,Origin:base,'Content-Type':'application/json'});
const keys=[crypto.randomBytes(32).toString('base64url'),crypto.randomBytes(32).toString('base64url')];
const pdf=fs.readFileSync('tests/fixtures/cv.pdf');
const data=JSON.parse(fs.readFileSync('test-results/onboarding-preview-export.json'));
async function send(path,headers,body,method='POST'){
 const response=await fetch(base+path,{method,headers,...(body===undefined?{}:{body:JSON.stringify(body)})});
 // Drain error responses as well as JSON results before reusing pooled sockets.
 return new Response(await response.arrayBuffer(),{status:response.status,headers:response.headers});
}
async function queue(key,retry=false){const response=await send('/api/cv/extract',draft(key),{retry});assert.equal(response.status,200);return response.json();}
async function upload(key){const response=await fetch(base+'/api/cv',{method:'PUT',headers:{...draft(key),'Content-Type':'application/pdf','X-File-Name':'synthetic.pdf'},body:pdf});assert.equal(response.status,200);}
(async()=>{try{
 for(const key of keys)assert.equal((await send('/api/profile',draft(key),{data:{identity:data.identity,budget:data.budget,memory:data.memory},status:'draft',markdown:'',consent:false})).status,200);
 await upload(keys[0]);
 assert.equal((await send('/api/extractor/claim',draft(keys[0]),{})).status,401);
 assert.equal((await send('/api/extractor/claim',{Authorization:'Bearer wrong'},{})).status,401);
 const forbidden=await send('/api/cv/extract',{'X-Submission-Key':keys[0],Origin:'https://other.example','Content-Type':'application/json'},{retry:false});
 assert.equal(forbidden.status,403,await forbidden.text());
 const queued=await Promise.all(Array.from({length:5},()=>queue(keys[0])));assert.equal(new Set(queued.map(value=>value.job.id)).size,1);
 const other=await(await send('/api/cv/extract',draft(keys[1]),undefined,'GET')).json();assert.equal(other.job,null);
 const claims=await Promise.all([send('/api/extractor/claim',worker,{}),send('/api/extractor/claim',worker,{})]);
 const jobs=(await Promise.all(claims.map(response=>response.json()))).map(value=>value.job).filter(Boolean);assert.equal(jobs.length,1);let job=jobs[0];
 const completion={id:job.id,lease_token:job.lease_token,status:'completed',result:{model:'gpt-5.6-terra',suggestions:[{field:'skills',text:'Synthetic capability',quote:'No exact quote gate'}]}};
 assert.equal((await send('/api/extractor/complete',worker,{...completion,lease_token:'wrong'})).status,404);
 assert.equal((await send('/api/extractor/complete',worker,{...completion,result:{...completion.result,model:'qwen'}})).status,400);
 assert.equal((await send('/api/extractor/complete',worker,completion)).status,200);
 const done=await queue(keys[0]);assert.equal(done.job.status,'completed');assert.equal(done.job.id,job.id);assert.equal(done.job.result.suggestions[0].text,'Synthetic capability');assert.ok(!JSON.stringify(done).includes(job.lease_token));assert.ok(!JSON.stringify(done).includes('cv_key'));
 await queue(keys[0],true);job=(await(await send('/api/extractor/claim',worker,{})).json()).job;
 assert.equal((await send('/api/extractor/complete',worker,{id:job.id,lease_token:job.lease_token,status:'failed',error:'Synthetic extraction failure'})).status,200);
 assert.equal((await(await send('/api/cv/extract',draft(keys[0]),undefined,'GET')).json()).job.error,'Synthetic extraction failure');
 await queue(keys[0],true);job=(await(await send('/api/extractor/claim',worker,{})).json()).job;
 await upload(keys[0]);assert.equal((await send('/api/extractor/complete',worker,{...completion,id:job.id,lease_token:job.lease_token})).status,409);
 assert.equal((await(await send('/api/cv/extract',draft(keys[0]),undefined,'GET')).json()).job,null);
 await queue(keys[0]);job=(await(await send('/api/extractor/claim',worker,{})).json()).job;
 await send('/api/profile',draft(keys[0]),undefined,'DELETE');
 assert.equal((await send('/api/extractor/complete',worker,{...completion,id:job.id,lease_token:job.lease_token})).status,404);
 console.log('PASS worker auth, Origin, concurrent queue deduplication and exclusive claim, owner isolation, fixed model, result delivery/reuse, explicit retry, replaced-PDF rejection and delete cascade. No model calls.');
}finally{for(const key of keys)await send('/api/profile',draft(key),undefined,'DELETE');}})().catch(error=>{console.error(error);process.exitCode=1;});
