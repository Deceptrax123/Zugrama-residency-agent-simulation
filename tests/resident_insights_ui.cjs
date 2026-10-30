// Synthetic presentation fixture only; no API writes, model calls or events.
const {chromium}=require('../.tools/node_modules/playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),{execFileSync}=require('node:child_process');
const base=process.env.RESIDENCY_INSIGHTS_UI_URL||'http://127.0.0.1:5175';
if(!['http://127.0.0.1:5175','https://zugrama-agent-residency.smudge0110.chatgpt.site'].includes(base))throw Error('Use the local preview or the known Zugrama Site only.');
const state=JSON.parse(execFileSync('python3',['-B','-c',`
import sys,json,time
sys.path.insert(0,'.')
from residency.communication_insights import communication_insights
now=time.time()
people=[{'id':'a','name':'Ada Rao','nickname':'Ada','introduction':'I work with water systems and enjoy building things with others.','skills_offer_people':'Water-quality monitoring and field research','skills_need_people':'Sensor prototypes and data visualization','subject_expertise':'Drinking water systems','interests':'Ecology, ceramics and cycling'}, {'id':'b','name':'Nikhil Sen','nickname':'Nikhil','introduction':'I build tools and explore how communities share knowledge.','skills_offer_people':'Python prototypes and collaborative design'}, {'id':'c','name':'Lea Kapoor','nickname':'Lea','introduction':'I enjoy research, small experiments and unexpected conversations.'}]
def m(seq,sender,body,room,at):return {'seq':seq,'id':'message-'+str(seq),'sender_id':sender,'body':body,'conversation_id':room,'created_at':at}
messages=[m(1,'a','PRIVATE-ORIGINAL-ACACIA','ab',now-300),m(2,'b','Ada mentioned water quality monitoring. We could connect the sensor readings to a shared notebook.','bc',now-120),m(3,'c','Water quality monitoring sounds useful. Could we write a small prototype together?','bc',now-100),m(4,'c','I am exploring soil moisture sensors and a lightweight monitoring dashboard.','ac',now-25),m(5,'a','Soil moisture sensors can inform irrigation decisions. Let us compare the measurements before drafting a proposal.','ac',now-10)]
visits=[{'conversation_id':room,'member_id':person,'joined_after_seq':start,'left_after_seq':None} for room,person,start in [('ab','a',0),('ab','b',0),('bc','b',1),('bc','c',1),('ac','a',3),('ac','c',3)]]
insights=communication_insights('c',messages,visits,people,now)
view={'role':'resident','agent':{'member_id':'c','name':'Lea Kapoor'},'directory':people,'event':{'status':'completed','calls':12,'completed_calls':12,'worker_count':0,'event_id':'synthetic-preview'},'cycle':{'day':2,'phase':'sleeping'},'insights':insights,'messages':messages[1:],'wallet':{'limit_usd':10,'spent_usd':1.12,'held_usd':0,'remaining_usd':8.88,'total_tokens':3212,'state':'ready'},'identity_markdown':'# Identity\\n\\nLea Kapoor\\nSynthetic UI fixture only.','requests':[],'notes':[{'id':'note-1','memory':'Nikhil shared an idea about water-quality monitoring and a shared notebook. I want to compare measurements before committing.','sources':[{'key':'message-2','speaker_id':'b','body':messages[1]['body']}]}],'reflections':[],'network_context':True}
print(json.dumps({'snapshot':view,'updated_at':now*1000,'heartbeat_at':now*1000,'commands':[]}))
`],{encoding:'utf8'}));
(async()=>{const browser=await chromium.launch({headless:true,args:['--no-sandbox']});try{
 const page=await browser.newPage({viewport:{width:1512,height:1100},deviceScaleFactor:1});const errors=[];page.on('pageerror',e=>errors.push(e.message));let writes=0;
 await page.route('**/api/residency',route=>{if(route.request().method()!=='GET')writes++;return route.fulfill({json:state});});
 await page.goto(base+'/resident#draft='+'A'.repeat(43));await page.getByRole('heading',{name:'Your network',exact:true}).waitFor();
 assert.ok(!(await page.locator('body').textContent()).includes('PRIVATE-ORIGINAL-ACACIA'));await page.getByRole('heading',{name:'References to other residents',exact:true}).waitFor();await page.getByText('Named reference · original exchange unverified',{exact:true}).waitFor();
 await page.locator('.activity-directory button').filter({hasText:'Ada Rao'}).click();await page.getByRole('heading',{name:'Ada Rao',exact:true}).waitFor();await page.getByText('Water-quality monitoring and field research',{exact:true}).waitFor();
 await page.screenshot({path:'test-results/resident-insights-desktop.png'});await page.locator('#topics').screenshot({path:'test-results/resident-topics-evidence.png'});
 await page.getByRole('button',{name:'1 min',exact:true}).click();assert.equal(await page.locator('.activity-metrics article').first().locator('strong').textContent(),'1');assert.equal(await page.locator('.activity-metrics article').nth(1).locator('strong').textContent(),'1');
 await page.getByRole('button',{name:'All event',exact:true}).click();await page.getByRole('button',{name:'Ask my agent to approach',exact:true}).click();assert.equal(await page.getByLabel('Resident to approach (optional)',{exact:true}).inputValue(),'a');assert.equal(writes,0);
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);await page.locator('#network').scrollIntoViewIfNeeded();await page.screenshot({path:'test-results/resident-insights-mobile.png'});await page.locator('#information-flow').scrollIntoViewIfNeeded();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.deepEqual(errors,[]);
 console.log('PASS desktop/mobile resident dashboard, source-linked topics, time-window filters, direct network links, public peer profile, explicitly unverified named references, no hidden original, approach action without sending, zero API writes. Synthetic UI fixture.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
