const {chromium}=require('../.tools/node_modules/playwright');
const assert=require('node:assert/strict');
const base='http://127.0.0.1:7370';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});const errors=[];
 try{
  const page=await browser.newPage();page.on('pageerror',error=>errors.push(error.message));
  await page.goto(base);await page.getByLabel('Your name',{exact:true}).fill('Import test host');await page.getByLabel('Email',{exact:true}).fill('import-host@example.test');await page.getByLabel('Password',{exact:true}).fill('isolated-browser-fixture-password');await page.getByLabel('Residency invitation code',{exact:true}).fill('test-residency-invitation');await page.getByRole('button',{name:'Take your seat ↗',exact:true}).click();
  await page.getByLabel('Import saved onboarding file',{exact:true}).setInputFiles('test-results/onboarding-preview-export.json');
  await page.getByText('Saved onboarding imported into this draft. Review it, optionally extract CV suggestions with GPT, then submit.',{exact:true}).waitFor();
  assert.equal(await page.getByLabel('Name',{exact:true}).inputValue(),'Preview Resident');assert.equal(await page.getByLabel('Nickname',{exact:true}).inputValue(),'River');
  assert.equal(await page.getByLabel('Skills',{exact:true}).inputValue(),'Human-reviewed skills in design and Python\nSynthetic extracted skill');
  const before=await page.evaluate(async()=>await(await fetch('/api/state')).json());assert.equal(before.sandbox.agents.length,0);assert.equal(before.event,null);
  await page.getByRole('button',{name:'Review IDENTITY.md',exact:true}).click();
  await page.getByLabel('Edit IDENTITY.md',{exact:true}).waitFor();assert.equal(await page.getByLabel('Agent’s USD allowance',{exact:true}).inputValue(),'12.00');assert.equal(await page.getByLabel('Reserved for its final wrap-up decision',{exact:true}).inputValue(),'2.25');
  assert.ok((await page.getByLabel('Edit IDENTITY.md',{exact:true}).inputValue()).includes('Human-reviewed skills in design and Python'));
  await page.getByRole('button',{name:'Submit agent 1',exact:true}).click();await page.getByText('Agent 1 submitted. Your reviewed identity is saved.',{exact:true}).waitFor();
  const after=await page.evaluate(async()=>await(await fetch('/api/state')).json());assert.equal(after.sandbox.agents.length,1);assert.equal(after.event,null);
  const accounts=await page.evaluate(async()=>await(await fetch('/api/agent-accounts')).json());assert.equal(accounts.agents[0].wallet.limit_usd,12);assert.equal(accounts.agents[0].wallet.total_tokens,0);assert.equal(accounts.agents[0].usage.length,0);
  assert.deepEqual(errors,[]);console.log('PASS actual Zugrama export imported into an empty agent slot with reviewed identity, USD amounts and stored preferences; no event or model call.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
