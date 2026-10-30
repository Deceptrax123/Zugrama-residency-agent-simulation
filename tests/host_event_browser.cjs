// Only scripts/browser_fixture.py --host-event. Never use against the real demo.
const {chromium}=require('../.tools/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.RESIDENCY_TEST_URL||'http://127.0.0.1:7359';
if(!/^http:\/\/127\.0\.0\.1:(7359|7349)$/.test(base))throw Error('Use the disposable host-event fixture port only');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const errors=[];
 try{
  const host=await browser.newPage({viewport:{width:1400,height:1000}});
  const peer=await browser.newPage({viewport:{width:390,height:844}});
  for(const [page,email] of [[host,'asha@example.test'],[peer,'kabir@example.test']]){
   page.on('pageerror',e=>errors.push(e.message));
   await page.goto(base);
   await page.getByRole('button',{name:'Sign in',exact:true}).click();
   await page.getByLabel('Email',{exact:true}).fill(email);
   await page.getByLabel('Password',{exact:true}).fill('residency-demo-only-2026');
   await page.getByRole('button',{name:'Sign in ↗',exact:true}).click();
   await page.getByRole('heading',{name:'Find a little common ground.'}).waitFor();
   await page.getByRole('navigation').getByRole('button',{name:'Host event',exact:true}).click();
  }
  await host.getByText('Event: idle',{exact:false}).waitFor();
  assert.equal(await peer.getByRole('button',{name:'Start event',exact:true}).count(),0);
  assert.equal(await host.getByRole('button',{name:'Stop event',exact:true}).isDisabled(),true);
  await host.getByLabel('Maximum model calls for this test',{exact:true}).fill('1');
  await host.getByRole('button',{name:'Start event',exact:true}).click();
  await host.getByText('Event: completed',{exact:false}).waitFor();
  await host.getByText('I enjoy exploring useful ideas and music together.',{exact:true}).waitFor();
  assert.equal(await host.getByRole('button',{name:'Start event',exact:true}).isEnabled(),true);
  await peer.getByRole('button',{name:'Refresh residency'}).click();
  await peer.getByText('Event: completed',{exact:false}).waitFor();
  assert.equal(await peer.getByText('I enjoy exploring useful ideas and music together.',{exact:true}).count(),0);
  assert.equal(await peer.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);
  fs.mkdirSync('test-results',{recursive:true});
  await host.screenshot({path:'test-results/host-event-fixture.png',fullPage:true});
  console.log('PASS host-only Start, bounded fake-model run, local monitor, participant privacy, mobile layout; no real model calls.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
