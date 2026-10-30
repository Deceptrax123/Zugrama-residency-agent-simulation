// Opt-in published Site check with synthetic data; no CV upload or model call.
if(process.env.RESIDENCY_LIVE_SITE!=='1'){console.log('SKIP: set RESIDENCY_LIVE_SITE=1 to check the published Site.');process.exit(0);}
const {chromium}=require('../.tools/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});let page,key;
try{
 page=await browser.newPage();await page.goto('https://zugrama-agent-residency.smudge0110.chatgpt.site/');
 await page.getByLabel('Name',{exact:true}).fill('Synthetic publication check');key=await page.evaluate(()=>localStorage.getItem('zugrama-private-draft-v1'));
 await page.locator('.journey ol button').nth(5).click();const choice=page.getByRole('checkbox',{name:'Let GPT use my agent’s own retrieved notes and bedtime reflections as conversation context.',exact:true});await choice.waitFor();assert.equal(await choice.isChecked(),true);await choice.uncheck();await page.getByLabel('Phrases to exclude from memory (optional, one per line)',{exact:true}).fill(['Private information '.repeat(12).trim(),...Array.from({length:24},(_,i)=>'Synthetic exclusion '+i)].join('\n'));
 await page.getByRole('button',{name:'Save draft ↗',exact:true}).click();await page.getByText('Draft saved. Come back whenever you’re ready.',{exact:true}).waitFor();
 await page.locator('.journey ol button').nth(3).click();await page.getByLabel('Public introduction',{exact:true}).fill('Synthetic publication verification only.');
 await page.locator('.journey ol button').nth(6).click();await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Save my introduction',exact:false}).click();
 await page.getByText('Your introduction is saved for the residency. The organiser can collect it from the site. You can return to edit it whenever you like.',{exact:true}).waitFor();
 assert.ok((await page.locator('.export-box').textContent()).includes('optionally download a copy for your records'));
 const saved=await page.evaluate(async(key)=>await(await fetch('/api/profile',{headers:{'X-Submission-Key':key}})).json(),key);assert.equal(saved.status,'reviewed');assert.equal(saved.memory.network_context,false);assert.equal(saved.memory.exclude_terms.length,25);assert.ok(saved.memory.exclude_terms[0].length>80);
 fs.writeFileSync('test-results/onboarding-live-readiness.json',JSON.stringify({passed:true,synthetic_only:true,model_calls:0,event_started:false,memory_opt_out_saved:true,long_and_numerous_exclusions_saved:true,download_optional:true},null,2));
 console.log('PASS published Site: anonymous signup, explicit own-memory choice and opt-out persistence, reviewed save, organiser handoff confirmation and optional personal download. No model call or event.');
}finally{
 if(key&&page){const status=await page.evaluate(async(key)=>(await fetch('/api/profile',{method:'DELETE',headers:{'X-Submission-Key':key}})).status,key);assert.equal(status,200);console.log('Synthetic publication record removed.');}
 await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
