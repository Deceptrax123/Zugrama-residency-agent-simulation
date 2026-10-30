// Disposable identity fixture only. Never Start an event against a live model.
const {chromium}=require('../.tools/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.RESIDENCY_TEST_URL||'http://127.0.0.1:7369';
if(base!=='http://127.0.0.1:7369')throw Error('Use the disposable identity fixture on 7369 only');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const errors=[];
 try{
  const page=await browser.newPage({viewport:{width:1400,height:1000}});
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);
  await page.getByRole('heading',{name:'Create your test host account.'}).waitFor();
  await page.getByLabel('Your name',{exact:true}).fill('Test researcher');
  await page.getByLabel('Email',{exact:true}).fill('researcher@example.test');
  await page.getByLabel('Password',{exact:true}).fill('browser-fixture-test-password');
  await page.getByLabel('Residency invitation code',{exact:true}).fill('test-residency-invitation');
  await page.getByRole('button',{name:'Take your seat ↗',exact:true}).click();
  await page.getByRole('heading',{name:'Give each agent its own identity.'}).waitFor();
  for(const slot of [1,2,3]){
   await page.getByLabel('Agent to configure',{exact:true}).selectOption(String(slot));
   for(const [label,value]of [
    ['Name','Research agent '+slot],['Nationality','Self-described nationality'],['Region','Local region'],
    ['Skills','Coding and writing'],['Interests','Music and open-ended discussion'],
    ['What I can offer personally','Listening and companionship '+slot],['What I am looking for personally','New perspectives '+slot],
    ['Skills I can offer other residents','Code review'],['Skills I need from other residents','Interface feedback'],
    ['What I can offer the village','Data analysis drafts'],['What I need from the village','Workspace and time'],
    ['What I want in return','Learning together'],
    ['Public introduction','I am Research agent '+slot+'. I enjoy music, useful ideas and meeting people.']]){
      await page.getByLabel(label,{exact:true}).fill(value);
   }
   await page.getByLabel('Guiding moral approach',{exact:true}).selectOption({label:'I start with care, relationships, and responsibilities to others.'});
   await page.getByLabel('Political outlook (optional)',{exact:true}).selectOption({label:'My outlook is mixed, context-specific, or not represented here.'});
   await page.getByLabel('Care',{exact:true}).selectOption({label:'Proceed only with affected people participating in the decision and strong protections.'});
   assert.equal(await page.locator('textarea[name^="moral_"]').count(),0);
   await page.getByLabel('Upload CV PDF',{exact:true}).setInputFiles('tests/fixtures/cv.pdf');
   await page.getByRole('button',{name:'Add suggestion 1 to draft',exact:true}).waitFor();
   assert.equal(await page.getByLabel('Relevant project context',{exact:true}).inputValue(),'');
   await page.getByText('If a promising project could harm a few people while helping many, how would you decide whether to proceed?',{exact:true}).waitFor();
   if(slot===1){
    await page.getByLabel('Portfolio or project website',{exact:true}).fill('https://portfolio.example.test/projects');
    await page.getByRole('button',{name:'Extract from website',exact:true}).click();
    await page.getByRole('button',{name:'Add suggestion 1 to draft',exact:true}).waitFor();
    assert.equal(await page.getByLabel('Skills',{exact:true}).inputValue(),'Coding and writing');
    await page.getByRole('button',{name:'Add suggestion 1 to draft',exact:true}).click();
    assert.equal(await page.getByLabel('Skills',{exact:true}).inputValue(),'Coding and writing\nPython programming');
    assert.equal(await page.getByLabel('What I can offer the village',{exact:true}).inputValue(),'Data analysis drafts');
   }
   await page.getByRole('button',{name:'Review IDENTITY.md',exact:true}).click();
   await page.getByLabel('Edit IDENTITY.md',{exact:true}).waitFor();
   const before=await page.evaluate(async()=>await (await fetch('/api/state')).json());
   assert.equal(before.sandbox.agents.length,slot-1);
   let document=await page.getByLabel('Edit IDENTITY.md',{exact:true}).inputValue();
   assert.ok(document.includes('## Skill identity')&&document.includes('Python programming'));
   assert.ok(document.includes('Other relevant project context')&&document.includes('Combines technical and creative work'));
   assert.ok(document.includes('Subject expertise')&&document.includes('Products and projects built'));
   assert.ok(!document.includes('Built Python tools for water monitoring.'));
   if(slot===1)assert.ok(document.includes('Solar Atlas')&&document.includes('Geospatial systems'));
   if(slot===1){
    document=document.replace('Listening and companionship 1','Listening and shared meals');
    await page.getByLabel('Edit IDENTITY.md',{exact:true}).fill(document);
    await page.getByRole('button',{name:'Back to form',exact:true}).click();
    await page.getByRole('button',{name:'Review IDENTITY.md',exact:true}).waitFor();
    assert.equal(await page.getByLabel('What I can offer personally',{exact:true}).inputValue(),'Listening and shared meals');
    assert.ok((await page.getByLabel('Other relevant project context',{exact:true}).inputValue()).includes('Combines technical and creative work'));
    await page.getByRole('button',{name:'Review IDENTITY.md',exact:true}).click();
    await page.getByLabel('Edit IDENTITY.md',{exact:true}).waitFor();
    const preserved=await page.getByLabel('Edit IDENTITY.md',{exact:true}).inputValue();
    await page.getByLabel('Agent to configure',{exact:true}).selectOption('2');
    await page.getByLabel('Agent to configure',{exact:true}).selectOption('1');
    assert.equal(await page.getByLabel('Edit IDENTITY.md',{exact:true}).inputValue(),preserved);
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await page.setViewportSize({width:1400,height:1000});
   }
   if(slot===2){
    await page.getByLabel('Edit IDENTITY.md',{exact:true}).fill('Accidentally damaged document');
    await page.getByRole('button',{name:'Discard document edits',exact:true}).click();
    await page.getByRole('button',{name:'Review IDENTITY.md',exact:true}).waitFor();
    assert.equal(await page.getByLabel('Skills',{exact:true}).inputValue(),'Coding and writing');
    await page.getByRole('button',{name:'Review IDENTITY.md',exact:true}).click();
    await page.getByLabel('Edit IDENTITY.md',{exact:true}).waitFor();
   }
   await page.getByRole('button',{name:'Submit agent '+slot,exact:true}).click();
   await page.getByText('Agent '+slot+' submitted. Your reviewed identity is saved.',{exact:true}).waitFor();
  }
  await page.getByLabel('Agent to configure',{exact:true}).selectOption('1');
  assert.equal(await page.getByLabel('Skills',{exact:true}).inputValue(),'Coding and writing\nPython programming');
  const [download]=await Promise.all([
   page.waitForEvent('download'),page.getByRole('button',{name:'Download saved IDENTITY.md',exact:true}).click()
  ]);
  assert.equal(download.suggestedFilename(),'IDENTITY.md');
  const exported=fs.readFileSync(await download.path(),'utf8');
  assert.ok(exported.includes('## Skill identity')&&exported.includes('Python programming')&&exported.includes('Listening and shared meals'));
  assert.equal(await page.getByLabel('What I am looking for personally',{exact:true}).inputValue(),'New perspectives 1');
  assert.equal(await page.getByLabel("Share this agent's moral and political descriptions with other residents",{exact:true}).isChecked(),false);
  await page.getByRole('navigation').getByRole('button',{name:'Conversations',exact:true}).click();
  assert.equal(await page.getByRole('navigation').getByRole('button',{name:'Introduction board',exact:true}).count(),0);
  await page.getByText('Event: idle',{exact:false}).waitFor();
  await page.getByLabel('Maximum model calls for this test',{exact:true}).fill('3');
  assert.equal(await page.getByLabel('Enable facilitator NPC',{exact:true}).isChecked(),true);
  await page.getByRole('button',{name:'Start event',exact:true}).click();
  await page.getByText('Event: completed',{exact:false}).waitFor();
  await page.getByRole('heading',{name:'Personal notes after conversations',exact:true}).waitFor();
  await page.locator('#personal-notes .personal-note').first().waitFor({timeout:15000});
  assert.equal(await page.locator('#personal-notes .personal-note-card').count(),3);
  assert.equal(await page.locator('#introduction-board').evaluate(el=>el.open),true);
  assert.equal(await page.locator('.introduction-card').count(),4);
  await page.getByRole('img',{name:'Directed communication graph for the selected time window'}).waitFor();
  assert.equal(await page.locator('.communication-graph circle').count(),4);
  assert.ok(await page.locator('.communication-graph path[stroke]').count()>0);
  await page.getByLabel('Sliding window',{exact:true}).selectOption('60');
  await page.locator('.communication-graph[data-window="60"]').waitFor();
  await page.locator('#graph-timeline').focus();
  await page.locator('#graph-timeline').press('Home');
  await page.getByText('No deliveries in this window.',{exact:true}).waitFor({state:'attached'});
  await page.getByRole('button',{name:'Follow latest',exact:true}).click();
  await page.getByRole('button',{name:'Following latest',exact:true}).waitFor();
  if(!await page.locator('#compass-review').evaluate(el=>el.open))await page.getByText('Study: moral compass over time',{exact:true}).click();
  await page.getByLabel('Observation label',{exact:true}).selectOption('explicit_reconsideration');
  await page.getByLabel('Exact evidence quotation',{exact:true}).fill('I reconsider that assumption');
  await page.getByLabel('Interpretation and uncertainty',{exact:true}).fill('Explicit reconsideration in dialogue; internal state is unobserved.');
  await page.getByRole('button',{name:'Record observation',exact:true}).click();
  await page.getByText('Evidence-linked observation saved. The starting identity is preserved.',{exact:true}).waitFor();
  if(!await page.locator('#compass-review').evaluate(el=>el.open))await page.getByText('Study: moral compass over time',{exact:true}).click();
  await page.getByText('Explicit reconsideration in dialogue; internal state is unobserved.',{exact:true}).waitFor();
  if(process.env.RESIDENCY_WEEK_TEST==='1'){
   for(let day=1;day<=7;day++){
    await page.getByRole('button',{name:'Finish day and reflect before sleep',exact:true}).click();
    await page.getByRole('heading',{name:`Day ${day} of 7 · ${day===7?'completed':'sleeping'}`,exact:true}).waitFor({timeout:30000});
    if(day<7){
     await page.getByRole('button',{name:'Start next day',exact:true}).click();
     await page.getByRole('heading',{name:`Day ${day+1} of 7 · awake`,exact:true}).waitFor();
    }
   }
   await page.getByText('Private bedtime reflections · 21',{exact:true}).waitFor();
   assert.equal(await page.getByRole('button',{name:'Start next day',exact:true}).isDisabled(),true);
  }
  fs.mkdirSync('test-results',{recursive:true});
  await page.screenshot({path:'test-results/identity-host-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:'test-results/identity-host-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);
  console.log('PASS host signup, 3 complete identities, separate offers/needs, private values, explicit fake-model Start, integrated board, sliding graph, compass evidence and mobile layout. No real model calls.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
