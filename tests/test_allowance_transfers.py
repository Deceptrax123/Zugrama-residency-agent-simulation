import json,threading,time,unittest
from unittest.mock import patch
from residency.agent_tools import AgentTools
from residency.allowance_transfers import transfer,history
from residency.store import AppError
from tests.test_cohort import fixture,apply,export,import_payload,settle

class AllowanceTransferTests(unittest.TestCase):
 def prepare(self,server):
  apply(server,None,import_payload(export(3)));server.agent_tools=AgentTools(server);server.allowance_transfers_enabled=True;event=server.event;event.state.update(event_id='funding',status='running');return event,list(event.personas),server.sandbox.accounts
 def args(self,target,amount='2.00'):return {'to_member_id':target,'amount_usd':amount,'reason':'Continue a shared musical task if useful'}
 def test_transfer_conserves_allowance_has_private_owner_history_and_is_idempotent(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c),accounts=self.prepare(server);accounts_before=[accounts.wallet(o) for o in (a,b,c)]
   result=transfer(accounts,a,self.args(b),'receipt',1);self.assertTrue(result['saved']);self.assertEqual(accounts.wallet(a)['limit_usd'],8_000_000);self.assertEqual(accounts.wallet(b)['limit_usd'],12_000_000)
   self.assertEqual(sum(accounts.wallet(o)['limit_usd'] for o in (a,b,c)),sum(x['limit_usd'] for x in accounts_before));self.assertEqual(accounts.wallet(a)['base_limit_usd'],10_000_000)
   self.assertTrue(transfer(accounts,a,self.args(b),'receipt',1)['duplicate']);self.assertEqual(len(history(accounts,a,'funding')),1);self.assertEqual(history(accounts,c,'funding'),[])
   self.assertEqual(len(event.context(a)['own_allowance_transfers']),1);self.assertEqual(event.context(c)['own_allowance_transfers'],[]);self.assertEqual(backend.records,[])
   with self.assertRaises(AppError):transfer(accounts,a,self.args(c),'receipt',1)
   self.assertEqual(accounts.wallet(b)['ended'],0)
 def test_reserved_usage_and_wrap_up_cannot_be_donated_or_double_spent(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c),accounts=self.prepare(server);entry=accounts.reserve(a,'funding',1,[]);self.assertEqual(accounts.wallet(a)['transferable_usd'],6_200_000)
   with self.assertRaises(AppError):transfer(accounts,a,self.args(b,'6.21'),'over',2)
   transfer(accounts,a,self.args(b,'6.20'),'full',2);self.assertEqual(accounts.wallet(a)['remaining_usd'],1_900_000);self.assertEqual(accounts.wallet(a)['held_usd'],1_900_000)
   accounts.unknown(entry)
   with self.assertRaises(AppError):transfer(accounts,a,self.args(b,'0.01'),'reserve',3)
 def test_concurrent_donations_are_atomic_and_cannot_overdraw(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c),accounts=self.prepare(server);barrier=threading.Barrier(2);results=[]
   def give(target):
    barrier.wait()
    try:results.append(transfer(accounts,a,self.args(target,'6.00'),target,1))
    except AppError as e:results.append(e)
   threads=[threading.Thread(target=give,args=(o,)) for o in (b,c)]
   for t in threads:t.start()
   for t in threads:t.join(5);self.assertFalse(t.is_alive())
   self.assertEqual(sum(isinstance(r,dict) for r in results),1);self.assertEqual(accounts.wallet(a)['limit_usd'],4_000_000);self.assertEqual(sum(accounts.wallet(o)['limit_usd'] for o in (a,b,c)),30_000_000)
 def test_invalid_amounts_actors_contexts_and_ended_donors_are_rejected(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c),accounts=self.prepare(server)
   for amount in ('0','-1','1.001','NaN',True):
    with self.subTest(amount=amount):
     with self.assertRaises(AppError):transfer(accounts,a,self.args(b,amount),str(amount),1)
   for target in (a,'not-a-resident',event.npc.member_id):
    with self.assertRaises(AppError):transfer(accounts,a,self.args(target),str(target),1)
   with self.assertRaises(AppError):transfer(accounts,a,{**self.args(b),'from_owner':c},'spoof',1)
   room=server.store.conversation_action(a,{'start_conversations':[{'with':b,'body':'private room'}]})['created_conversations'][0];event.rooms.add(room)
   with self.assertRaises(AppError):transfer(accounts,a,{**self.args(c),'conversation_id':room},'hidden',1)
   accounts.end(a)
   with self.assertRaises(AppError):transfer(accounts,a,self.args(b),'ended',1)
 def test_receiving_funds_does_not_undo_voluntary_end_and_admin_cannot_remove_committed_donations(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c),accounts=self.prepare(server);accounts.end(b);transfer(accounts,a,self.args(b),'gift',1);self.assertEqual(accounts.wallet(b)['state'],'ended')
   accounts.configure(server.sandbox.owner,{'owner_id':a,'limit_usd':'2.00','reserve_usd':'0.00'});self.assertEqual(accounts.wallet(a)['limit_usd'],0)
   with self.assertRaises(AppError):accounts.configure(server.sandbox.owner,{'owner_id':a,'limit_usd':'1.00','reserve_usd':'0.00'})
 def test_real_network_tool_recovers_allowance_paused_resident_and_records_usage(self):
  with fixture() as (server,client,backend,memory):
   apply(server,client,import_payload(export(2)));server.agent_tools=AgentTools(server);server.allowance_transfers_enabled=True;event=server.event;a,b=event.personas;accounts=server.sandbox.accounts;accounts.configure(server.sandbox.owner,{'owner_id':b,'limit_usd':'0.00','reserve_usd':'0.00'});counts={}
   def reply(payload):
    ctx=json.loads(payload['messages'][-1]['content']);owner=ctx['member_id'];counts[owner]=counts.get(owner,0)+1
    action={'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]}
    if owner==a and counts[owner]==1:
     end=time.time()+4
     while b not in event.state.get('budget_pauses',{}) and time.time()<end:time.sleep(.005)
     self.assertIn(b,event.state.get('budget_pauses',{}));action['tool_calls']=[{'name':'budget_transfer','arguments':self.args(b,'3.00')}]
    else:
     if owner==b:self.assertEqual(ctx['budget']['received_usd'],3);self.assertEqual(ctx['budget']['limit_usd'],3)
     action['budget_choice']='end'
    return json.dumps(action)
   backend.reply_factory=reply;server.sandbox.start(server.sandbox.owner,{'npc_enabled':False});settle(event)
   self.assertEqual(event.state['status'],'completed');self.assertEqual(counts[b],1);self.assertEqual(len(history(accounts,a,event.state['event_id'])),1);self.assertEqual(len(backend.records),3)
   with server.store.db() as db:self.assertIn('allowance_transfer',db.execute('SELECT links FROM agent_usage WHERE owner_id=? ORDER BY call_number LIMIT 1',(a,)).fetchone()[0])
