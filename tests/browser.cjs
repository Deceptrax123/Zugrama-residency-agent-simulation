// Real browser integration tests against scripts/browser_fixture.py only.
const {chromium} = require('../.tools/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.RESIDENCY_TEST_URL || 'http://127.0.0.1:7349';
const errors = [];
const results = [];
const output = path.join(__dirname, '..', 'test-results');
fs.mkdirSync(output,{recursive:true});

async function check(label, callback) {
  await callback(); results.push(label); console.log(`PASS ${label}`);
}
async function waitText(page, value) { await page.getByText(value,{exact:false}).first().waitFor(); }
async function join(page, name, email) {
  page.on('pageerror', error=>errors.push(error.message));
  await page.goto(base);
  await page.getByLabel('Your name',{exact:true}).fill(name);
  await page.getByLabel('Email',{exact:true}).fill(email);
  await page.getByLabel('Password',{exact:true}).fill('browser-test-password');
  await page.getByLabel('Residency invitation code',{exact:true}).fill('test-residency-invitation');
  await page.getByRole('button',{name:'Take your seat'}).click();
  await page.getByRole('heading',{name:'Find a little common ground.'}).waitFor();
}
async function nav(page, label) { await page.getByRole('navigation',{name:'Main navigation'}).getByRole('button',{name:label,exact:true}).click(); }
async function refresh(page) { await page.getByRole('button',{name:'Refresh residency'}).click(); }

(async()=>{
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  const adaContext = await browser.newContext({viewport:{width:1440,height:1000}});
  const bobContext = await browser.newContext({viewport:{width:1280,height:950}});
  const eveContext = await browser.newContext({viewport:{width:390,height:844},isMobile:true});
  const ada = await adaContext.newPage(), bob = await bobContext.newPage(), eve = await eveContext.newPage();
  try {
    await check('member onboarding in independent browser sessions',async()=>{
      await join(ada,'Ada','ada-browser@example.test');
      await join(bob,'Bob','bob-browser@example.test');
      await join(eve,'Eve','eve-browser@example.test');
    });
    await check('profile editing, search, and persistent reload',async()=>{
      await nav(ada,'Your profile');
      await ada.getByLabel('A little about you').fill('I build robotics experiments.');
      await ada.getByLabel('What are you looking for?').fill('Controls and causal inference');
      await ada.getByLabel('What can you offer?').fill('Statistics');
      await ada.getByRole('button',{name:'Save profile'}).click();
      await waitText(ada,'Your profile is saved.');
      await ada.reload();
      await ada.getByRole('heading',{name:'Find a little common ground.'}).waitFor();
      await ada.getByLabel('Search residents').fill('causal');
      await waitText(ada,'I build robotics experiments.');
      assert.equal(await ada.locator('.grid .card').count(),1);
      await ada.getByLabel('Search residents').fill('');
    });
    await check('two residents collaborate on a problem and only author resolves it',async()=>{
      await nav(ada,'Problem board');
      await ada.getByLabel('A short title').fill('How do we evaluate a robot policy?');
      await ada.getByLabel('Context and the help you’re looking for').fill('Need a useful baseline before our next experiment.');
      await ada.getByRole('button',{name:'Share with residents'}).click();
      await ada.getByRole('heading',{name:'How do we evaluate a robot policy?'}).waitFor();
      await refresh(bob); await nav(bob,'Problem board');
      await bob.getByLabel('Reply to How do we evaluate a robot policy?').fill('Start with a fixed policy baseline.');
      await bob.getByRole('button',{name:'Reply',exact:true}).click();
      await waitText(bob,'Start with a fixed policy baseline.');
      assert.equal(await bob.getByRole('button',{name:'Mark as solved'}).count(),0);
      await refresh(ada); await waitText(ada,'Start with a fixed policy baseline.');
      await ada.getByRole('button',{name:'Mark as solved'}).click();
      await ada.getByRole('button',{name:'Reopen problem'}).waitFor();
    });
    await check('private direct message delivery and third-member exclusion',async()=>{
      await nav(ada,'Residents');
      await ada.locator('.card').filter({has:ada.getByRole('heading',{name:'Bob',exact:true})}).getByRole('button',{name:'Say hello'}).click();
      await ada.getByLabel('Your direct message').fill('Private robotics hello');
      await ada.getByRole('button',{name:'Send',exact:false}).click();
      await waitText(ada,'Private robotics hello');
      await refresh(bob); await nav(bob,'Messages');
      await waitText(bob,'Private robotics hello');
      await nav(eve,'Messages');
      assert.equal(await eve.getByText('Private robotics hello',{exact:false}).count(),0);
    });
    await check('Hermes chat goes through real app HTTP adapter and persists privately',async()=>{
      await nav(ada,'Think with Hermes');
      await ada.getByLabel('Message for Hermes').fill('Help with my robot evaluation.');
      await ada.getByRole('button',{name:'Ask Hermes',exact:false}).click();
      await waitText(ada,'Talk with another resident about a small, testable next step.');
      await ada.reload(); await ada.getByRole('heading',{name:'Find a little common ground.'}).waitFor();
      await nav(ada,'Think with Hermes');
      await waitText(ada,'Help with my robot evaluation.');
      await nav(bob,'Think with Hermes');
      assert.equal(await bob.getByText('Help with my robot evaluation.',{exact:false}).count(),0);
    });
    await check('participant HTML stays text rather than executing',async()=>{
      await nav(ada,'Problem board');
      await ada.getByLabel('A short title').fill('<img src=x onerror="window.injected=true">');
      await ada.getByLabel('Context and the help you’re looking for').fill('<script>window.injected=true</script>');
      await ada.getByRole('button',{name:'Share with residents'}).click();
      await ada.getByRole('heading',{name:'<img src=x onerror="window.injected=true">'}).waitFor();
      assert.equal(await ada.evaluate(()=>Boolean(window.injected)),false);
      assert.equal(await ada.locator('.problem-card img').count(),0);
    });
    await check('residents share code and iterate with multiline pseudocode safely',async()=>{
      await nav(ada,'Problem board');
      const code = 'def choose_song(songs):\n    return songs[0]\n';
      await ada.getByLabel('A short title').fill('A music practice helper');
      await ada.getByLabel('Context and the help you’re looking for').fill(`Let’s work on this together.\n\n\x60\x60\x60python\n${code}\x60\x60\x60`);
      await ada.getByRole('button',{name:'Share with residents'}).click();
      const draft = ada.locator('.problem-card').filter({has:ada.getByRole('heading',{name:'A music practice helper',exact:true})});
      await draft.locator('pre code').waitFor();
      assert.equal(await draft.locator('pre code').textContent(),code);
      await refresh(bob); await nav(bob,'Problem board');
      const reply = bob.getByLabel('Reply to A music practice helper');
      assert.equal(await reply.evaluate(el=>el.tagName),'TEXTAREA');
      const pseudocode = 'IF songs is empty\n    RETURN no_selection\nELSE\n    RETURN first_song\n';
      await reply.fill(`A fallback idea:\n\x60\x60\x60text\n${pseudocode}\x60\x60\x60\n\x60\x60\x60html\n<script>window.injected=true</script>\n\x60\x60\x60`);
      await bob.locator('.problem-card').filter({has:bob.getByRole('heading',{name:'A music practice helper',exact:true})}).getByRole('button',{name:'Reply',exact:true}).click();
      await refresh(ada);
      await draft.locator('.comment pre code').first().waitFor();
      assert.equal(await draft.locator('.comment pre code').first().textContent(),pseudocode);
      assert.equal(await draft.locator('script').count(),0);
      assert.equal(await ada.evaluate(()=>Boolean(window.injected)),false);
      await nav(ada,'Think with Hermes');
      await ada.getByLabel('Message for Hermes').fill(`Review this code:\n\x60\x60\x60python\n${code}\x60\x60\x60`);
      await ada.getByRole('button',{name:'Ask Hermes',exact:false}).click();
      await ada.locator('#assistant-log .mine pre code').waitFor();
      assert.equal(await ada.locator('#assistant-log .mine pre code').textContent(),code);
      await refresh(eve); await nav(eve,'Problem board');
      assert.equal(await eve.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
    });
    await check('mobile navigation and layout fit the viewport',async()=>{
      for(const label of ['Residents','Conversations','Problem board','Messages','Think with Hermes','Memory','Your profile']) {
        await nav(eve,label);
        assert.equal(await eve.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,`${label} overflows`);
      }
      await nav(eve,'Residents');
      await eve.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
    });
    await check('local memory preserves two-hop attribution without the original private conversation',async()=>{
      await nav(bob,'Messages');
      await bob.getByRole('button',{name:'Eve',exact:true}).click();
      await bob.getByLabel('Your direct message').fill('Ada suggested a rainwater prototype for the village.');
      await bob.getByRole('button',{name:'Send',exact:false}).click();
      await waitText(bob,'Ada suggested a rainwater prototype for the village.');
      await refresh(eve); await nav(eve,'Memory');
      await eve.getByRole('button',{name:'Extract next batch locally'}).click();
      await eve.locator('.memory-card').waitFor();
      await waitText(eve,'Ada → Bob → Eve');
      await waitText(eve,'Relayed claim.');
      assert.equal(await eve.getByText('Private robotics hello',{exact:false}).count(),0);
      await eve.getByRole('button',{name:'Pin',exact:true}).click();
      await eve.getByRole('button',{name:'Unpin',exact:true}).waitFor();
      await eve.getByLabel('Search memory',{exact:true}).fill('rainwater');
      await eve.getByRole('button',{name:'Search notes',exact:true}).click();
      await eve.locator('.memory-card').waitFor();
      await eve.getByRole('button',{name:'Unpin',exact:true}).waitFor();
      assert.equal(await eve.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
      await eve.screenshot({path:path.join(output,'memory-mobile.png'),fullPage:true});
      await eve.getByRole('button',{name:'Hide note',exact:true}).click();
      await waitText(eve,'No notes here yet.');
    });
    await check('memory priorities and human-selected quotations persist',async()=>{
      await nav(bob,'Memory');
      await bob.getByText('Your importance priorities',{exact:true}).click();
      await bob.getByLabel('What should matter to your agent?',{exact:true}).fill('Remember music interests and useful introductions.');
      await bob.getByLabel('Topics to prioritize (one per line or separated by commas)',{exact:true}).fill('music, rainwater');
      await bob.getByLabel('commitments importance',{exact:true}).selectOption('3');
      await bob.getByRole('button',{name:'Save memory priorities'}).click();
      await waitText(bob,'Memory priorities saved.');
      await bob.getByText('Your importance priorities',{exact:true}).click();
      assert.equal(await bob.getByLabel('What should matter to your agent?',{exact:true}).inputValue(),'Remember music interests and useful introductions.');
      await bob.getByText('Select a quotation yourself',{exact:true}).click();
      await bob.getByRole('button',{name:'Load my conversation sources'}).click();
      const quote = await bob.locator('.source-preview').textContent();
      await bob.getByLabel('Exact quotation',{exact:true}).fill(quote);
      await bob.getByLabel('Memory statement',{exact:true}).fill('A personally selected conversation note.');
      await bob.getByRole('button',{name:'Save selected note',exact:true}).click();
      await waitText(bob,'A personally selected conversation note.');
      await bob.reload(); await bob.getByRole('heading',{name:'Find a little common ground.'}).waitFor();
      await nav(bob,'Memory');
      await waitText(bob,'A personally selected conversation note.');
    });
    await check('public introduction board is shared and introductions stay escaped',async()=>{
      for (const [resident, text] of [[ada,'I enjoy mathematical ideas and music.'],[bob,'I am skilled in Python prototypes.'],[eve,'I am curious about <script>window.injected=true</script> music.']]) {
        await nav(resident,'Conversations');
        await resident.locator('#introduction-board > summary').click();
        await resident.getByLabel('Your introduction',{exact:true}).fill(text);
        await resident.getByRole('button',{name:'Post introduction',exact:true}).click();
        await waitText(resident,'Your introduction is on the board.');
      }
      await refresh(ada);
      await ada.locator('.introduction-card').nth(2).waitFor();
      assert.equal(await ada.locator('.introduction-card').count(),3);
      assert.equal(await ada.locator('.introduction-card script').count(),0);
      assert.equal(await ada.evaluate(()=>Boolean(window.injected)),false);
      assert.equal(await ada.getByRole('button',{name:'Post introduction',exact:true}).count(),0);
    });
    await check('joined conversations hide prior history and leave gaps from UI and memory',async()=>{
      const bobIntro=ada.locator('.introduction-card').filter({has:ada.getByRole('heading',{name:'Bob',exact:true})});
      await bobIntro.getByRole('button',{name:'Start a conversation',exact:true}).click();
      await ada.getByLabel('Message to conversation',{exact:true}).fill('BEFORE-JOIN-831 private prototype details.');
      await ada.getByRole('button',{name:'Send to conversation',exact:true}).click();
      await waitText(ada,'BEFORE-JOIN-831');
      await refresh(eve); await nav(eve,'Conversations');
      await eve.getByRole('button',{name:'View presence',exact:true}).click();
      assert.equal(await eve.getByText('BEFORE-JOIN-831',{exact:false}).count(),0);
      await eve.getByRole('button',{name:'Join conversation',exact:true}).click();
      assert.equal(await eve.getByText('BEFORE-JOIN-831',{exact:false}).count(),0);
      await refresh(bob); await nav(bob,'Conversations');
      await bob.getByRole('button',{name:'Open conversation',exact:true}).click();
      await bob.getByLabel('Message to conversation',{exact:true}).fill('Ada suggested a shared music prototype for the residency.');
      await bob.getByRole('button',{name:'Send to conversation',exact:true}).click();
      await waitText(bob,'shared music prototype');
      await refresh(eve); await waitText(eve,'shared music prototype');
      await nav(eve,'Memory'); await eve.getByRole('button',{name:'Show all notes',exact:true}).click();
      const relay=eve.locator('.memory-card').filter({hasText:'shared music prototype'});
      await relay.waitFor();
      assert.ok((await relay.textContent()).includes('Ada → Bob → Eve'));
      assert.equal(await eve.getByText('BEFORE-JOIN-831',{exact:false}).count(),0);
      await nav(eve,'Conversations');
      await eve.getByRole('button',{name:'Leave conversation',exact:true}).click();
      await ada.getByLabel('Message to conversation',{exact:true}).fill('WHILE-AWAY-832 private music ideas.');
      await ada.getByRole('button',{name:'Send to conversation',exact:true}).click();
      await waitText(ada,'WHILE-AWAY-832');
      await eve.getByRole('button',{name:'Join conversation',exact:true}).click();
      assert.equal(await eve.getByText('WHILE-AWAY-832',{exact:false}).count(),0);
      await nav(eve,'Memory');
      assert.equal(await eve.getByText('WHILE-AWAY-832',{exact:false}).count(),0);
      assert.equal(await eve.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
      await eve.screenshot({path:path.join(output,'joined-conversation-memory-mobile.png'),fullPage:true});
    });
    await check('logout, login, and saved account data',async()=>{
      await nav(bob,'Your profile');
      await bob.getByRole('button',{name:'Sign out',exact:true}).click();
      await bob.getByRole('button',{name:'Sign in',exact:true}).click();
      await bob.getByLabel('Email',{exact:true}).fill('bob-browser@example.test');
      await bob.getByLabel('Password',{exact:true}).fill('browser-test-password');
      await bob.getByRole('button',{name:'Sign in ↗',exact:true}).click();
      await bob.getByRole('heading',{name:'Find a little common ground.'}).waitFor();
    });
    assert.deepEqual(errors,[],'Browser runtime errors');
    await nav(ada,'Residents'); await refresh(ada);
    await ada.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
    fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify({passed:results.length,results,errors},null,2));
    console.log(`${results.length} browser flows passed; no page errors.`);
  } catch(error) {
    await ada.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});
    throw error;
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
