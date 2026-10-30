// Disposable local fixture only; all networking and memory providers are fake.
const {chromium}=require('../.tools/node_modules/playwright');
const assert=require('node:assert/strict');
const base='http://127.0.0.1:7389';
async function waitState(page,check){const until=Date.now()+30000;while(Date.now()<until){const state=await page.evaluate(async()=>await(await fetch('/api/state')).json());if(check(state))return state;await page.waitForTimeout(100);}throw Error('Timed out waiting for a cohort state transition');}
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.getByLabel('Your name',{exact:true}).fill('Synthetic cohort host');await page.getByLabel('Email',{exact:true}).fill('cohort-browser@example.test');await page.getByLabel('Password',{exact:true}).fill('synthetic-browser-password');await page.getByLabel('Residency invitation code',{exact:true}).fill('test-residency-invitation');await page.getByRole('button',{name:'Take your seat ↗',exact:true}).click();
  await page.getByRole('heading',{name:'Import reviewed onboarding submissions',exact:true}).waitFor();assert.equal(await page.locator('#agent-slot option').count(),50);
  await page.getByLabel('Sites database export',{exact:true}).setInputFiles('test-results/cohort-import.json');await page.getByRole('button',{name:'Confirm reviewed cohort import',exact:true}).waitFor();
  let state=await page.evaluate(async()=>await(await fetch('/api/state')).json());assert.equal(state.sandbox.agents.length,0);assert.equal(state.event,null);
  await page.getByRole('button',{name:'Confirm reviewed cohort import',exact:true}).click();await page.getByText('Reviewed cohort imported. The event remains idle until Start.',{exact:true}).waitFor();
  state=await page.evaluate(async()=>await(await fetch('/api/state')).json());assert.equal(state.sandbox.agents.length,4);assert.equal(state.event.calls,0);
  await page.getByRole('button',{name:'Conversations',exact:true}).click();assert.equal(await page.getByLabel('Maximum model calls for this test',{exact:true}).count(),0);await page.evaluate(async()=>{const state=await(await fetch('/api/state')).json();const response=await fetch('/api/event/start',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},body:JSON.stringify({max_calls:4,npc_enabled:true,seven_days:true})});if(!response.ok)throw Error('Synthetic bounded test failed to start');});
  for(let day=1;day<=7;day++){
   await waitState(page,s=>s.cycle.day===day&&s.event.worker_count===0&&s.event.completed_calls>=day*4);
   await page.getByRole('button',{name:'Finish day and reflect before sleep',exact:true}).click();
   await waitState(page,s=>s.cycle.reflections.length===day*4&&!s.cycle.busy&&s.cycle.phase===(day===7?'completed':'sleeping'));
   if(day<7)await page.getByRole('button',{name:'Start next day',exact:true}).click();
  }
  state=await page.evaluate(async()=>await(await fetch('/api/state')).json());assert.equal(state.cycle.phase,'completed');assert.equal(state.event.calls,28);
  await page.getByRole('heading',{name:'Personal notes after conversations',exact:true}).waitFor();await page.waitForFunction(()=>document.querySelectorAll('.personal-note').length>0);await page.getByRole('heading',{name:'Communication over time',exact:true}).waitFor();assert.equal(await page.locator('.communication-graph svg circle').count(),5);
  await page.getByRole('button',{name:'My agents',exact:true}).click();await page.getByRole('heading',{name:'Resident 1',exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Save memory context choice',exact:true}).count(),4);
  const first=page.locator('.agent-account').first();await first.locator('input[name=network_context]').uncheck();await first.getByRole('button',{name:'Save memory context choice',exact:true}).click();await page.getByText('Memory context choice saved for later turns.',{exact:true}).waitFor();
  const accounts=await page.evaluate(async()=>await(await fetch('/api/agent-accounts')).json());assert.equal(accounts.agents[0].network_context,false);assert.equal(accounts.agents[1].network_context,true);
  await first.getByRole('button',{name:'Read MEMORY.md',exact:true}).click();await page.locator('.memory-document').waitFor();assert.ok((await page.locator('.memory-document').textContent()).includes('Personal conversation memory'));
  await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:'test-results/cohort-browser.png',fullPage:true});assert.deepEqual(errors,[]);
  console.log('PASS host signup, 50-slot cohort UI, reviewed JSON import preview/confirmation without Start, four residents/seven fake days, owned notes and reflections, graph, per-agent GPT-memory opt-out, Markdown access and mobile layout. No real inference.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
