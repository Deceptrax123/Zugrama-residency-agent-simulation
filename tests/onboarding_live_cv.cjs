// Live CV-only smoke with a synthetic PDF. Does not create an agent or event.
if(process.env.RESIDENCY_LIVE_CV!=='1'){console.log('SKIP live CV smoke: set RESIDENCY_LIVE_CV=1 explicitly to use the configured GPT Terra connection.');process.exit(0);}
const {chromium}=require('../.tools/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base='https://zugrama-agent-residency.smudge0110.chatgpt.site';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});let page,key;
 try{
  page=await browser.newPage();await page.goto(base);await page.getByLabel('Name',{exact:true}).fill('Synthetic CV extraction check');await page.getByLabel('Nickname',{exact:true}).fill('Synthetic');
  key=await page.evaluate(()=>localStorage.getItem('zugrama-private-draft-v1'));
  await page.getByRole('button',{name:'Continue',exact:false}).click();
  await page.getByLabel('Skills',{exact:true}).fill('Existing typed skill');
  await page.locator('#cv-file').setInputFiles('tests/fixtures/cv.pdf');
  await page.getByText('PDF saved. GPT Terra will extract suggestions here for you to review.',{exact:true}).waitFor({timeout:45000});
  console.log('Synthetic PDF queued on published Site; waiting for the existing GPT Terra route.');
  await page.getByRole('heading',{name:'CV suggestions · GPT Terra',exact:true}).waitFor({timeout:240000});
  const skills=await page.getByLabel('Skills',{exact:true}).inputValue();assert.ok(skills.includes('Existing typed skill'));assert.ok(skills.length>'Existing typed skill'.length);
  const state=await page.evaluate(async(key)=>await(await fetch('/api/cv/extract',{headers:{'X-Submission-Key':key}})).json(),key);
  assert.equal(state.job.status,'completed');assert.equal(state.job.result.model,'gpt-5.6-terra');assert.ok(state.job.result.suggestions.length>0);
  await page.locator('.journey ol button').nth(3).click();await page.getByLabel('Public introduction',{exact:true}).fill('Synthetic verification only.');
  await page.locator('.journey ol button').nth(6).click();const md=await page.getByLabel('Your IDENTITY.md',{exact:true}).inputValue();assert.ok(md.includes('Existing typed skill'));assert.ok(md.includes(skills));
  await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Save my introduction',exact:false}).click();await page.getByRole('button',{name:'Download onboarding file ↧',exact:true}).waitFor();
  const stored=await page.evaluate(async(key)=>await(await fetch('/api/profile',{headers:{'X-Submission-Key':key}})).json(),key);assert.equal(stored.status,'reviewed');assert.equal(stored.identity.skills,skills);
  await page.screenshot({path:'test-results/onboarding-live-cv.png',fullPage:true});
  fs.writeFileSync('test-results/onboarding-live-cv.json',JSON.stringify({passed:true,model:state.job.result.model,suggestion_count:state.job.result.suggestions.length,typed_answers_preserved:true,reviewed_identity_saved:true,networking_event_started:false},null,2));
  console.log('PASS published PDF upload → authenticated host queue → actual GPT Terra extraction → editable suggestions → reviewed IDENTITY.md stored. Synthetic data only; no agent or event.');
 }finally{
  if(key&&page){const status=await page.evaluate(async(key)=>(await fetch('/api/profile',{method:'DELETE',headers:{'X-Submission-Key':key}})).status,key);assert.equal(status,200);console.log('Synthetic hosted submission, PDF and extraction result deleted.');}
  await browser.close();
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
