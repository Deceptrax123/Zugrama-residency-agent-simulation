from dataclasses import replace
import json,unittest
from unittest.mock import patch
from residency.agent_tools import AgentTools
from residency.store import AppError
from tests.test_cohort import fixture,apply,export,import_payload,settle
from tests.test_collaboration import CollaborationTests

class DelegationTests(unittest.TestCase):
 def prepare(self,server,backend):
  event,people,room,state=CollaborationTests().prepare(server);server.delegate_enabled=True
  server.settings=replace(server.settings,hermes_model='gpt-6.1-sol',hermes_reasoning_effort='high');server.hermes.settings=server.settings;backend.models.append({'id':'gpt-6.1-sol','root':'gpt-6.1-sol'});return event,people,room
 def test_helper_uses_same_model_high_scoped_context_budget_audit_and_code_tools(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c),room=self.prepare(server,backend);event.state['calls']=10
   private_room=server.store.conversation_action(b,{'start_conversations':[{'with':c,'body':'HIDDEN-TO-A'}]})['created_conversations'][0];event.rooms.add(private_room)
   before=server.sandbox.accounts.wallet(a)['spent_usd']
   def reply(payload):
    self.assertEqual(payload['model'],'gpt-6.1-sol');self.assertEqual(payload['model_options']['reasoning']['effort'],'high');self.assertNotIn('HIDDEN-TO-A',json.dumps(payload));self.assertNotIn('delegate',[x['name'] for x in json.loads(payload['messages'][-1]['content'])['tools']]);return json.dumps({'report':'I propose calculating the score; the tool has not run yet.','tool_calls':[{'name':'python_run','arguments':{'code':'result=7*6'}}]})
   backend.reply_factory=reply;server.agent_tools.run(a,10,[{'name':'delegate','arguments':{'task':'Calculate a game score'}}]);server.agent_tools.run(a,10,[{'name':'delegate','arguments':{'task':'Must not replay'}}])
   self.assertEqual(len(backend.records),1);self.assertGreater(server.sandbox.accounts.wallet(a)['spent_usd'],before);self.assertEqual(server.sandbox.accounts.wallet(a)['held_usd'],0);self.assertEqual(event.state['calls'],11);self.assertEqual(event.state['completed_calls'],1);self.assertEqual(event.state['thinking'],[]);self.assertEqual(server.agent_tools.history(a)[0]['result']['data']['result'],42)
   request=json.loads(next(server.audit_directory.glob('*/*/request.json')).read_text());self.assertEqual(request['kind'],'helper');self.assertEqual(request['parent_call_number'],10)
   with server.store.db() as db:
    usage=dict(db.execute('SELECT * FROM agent_usage').fetchone());self.assertEqual(usage['call_number'],11);self.assertIn('delegated',usage['links']);self.assertIn('python_run',usage['links']);self.assertEqual(usage['status'],'recorded')
 def test_recursive_or_writing_helpers_and_invisible_sources_cannot_run(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c),room=self.prepare(server,backend);event.state['calls']=1
   backend.reply_factory=lambda p:json.dumps({'report':'attempt','tool_calls':[{'name':'delegate','arguments':{'task':'recursive'}}]})
   server.agent_tools.run(a,1,[{'name':'delegate','arguments':{'task':'test'}}]);self.assertEqual(len(backend.records),1);self.assertEqual(server.agent_tools.history(a)[0]['status'],'failed');self.assertEqual(event.state['thinking'],[])
   server.agent_tools.run(c,3,[{'name':'delegate','arguments':{'task':'read hidden','source_message_ids':[server.agent_tools.collaboration.witnessed(a)[0]['id']]}}]);self.assertEqual(len(backend.records),1)
   with self.assertRaises(AppError):server.agent_tools.validate([{'name':'delegate','arguments':{}}]*2)
 def test_no_call_when_disabled_stopped_or_wrap_up_and_quota_pause_keeps_receipts(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c),room=self.prepare(server,backend);server.delegate_enabled=False;server.agent_tools.run(a,1,[{'name':'delegate','arguments':{'task':'blocked'}}]);self.assertEqual(backend.records,[])
   server.delegate_enabled=True;wallet=server.sandbox.accounts.wallet(a);server.sandbox.accounts.configure(server.sandbox.owner,{'owner_id':a,'limit_usd':'1.90','reserve_usd':'1.90'});server.agent_tools.run(a,2,[{'name':'delegate','arguments':{'task':'blocked reserve'}}]);self.assertEqual(backend.records,[])
   server.sandbox.accounts.configure(server.sandbox.owner,{'owner_id':a,'limit_usd':'10.00','reserve_usd':'1.90'});backend.reply_factory=lambda p:json.dumps({'report':'unused','tool_calls':[]})
   from residency.provider_limits import ProviderQuotaPause
   with patch('residency.delegation.check_completion',side_effect=ProviderQuotaPause()):server.agent_tools.run(a,3,[{'name':'delegate','arguments':{'task':'quota'}}])
   self.assertEqual(event.state['status'],'paused_quota');self.assertEqual(event.state['thinking'],[]);self.assertEqual(server.sandbox.accounts.wallet(a)['held_usd'],0)
 def test_fake_full_event_can_delegate_and_continue_parent_with_results(self):
  with fixture() as (server,client,backend,memory):
   apply(server,client,import_payload(export(2)));server.agent_tools=AgentTools(server);server.delegate_enabled=True;server.settings=replace(server.settings,hermes_reasoning_effort='high');server.hermes.settings=server.settings;counts={}
   def reply(payload):
    self.assertEqual(payload['model_options']['reasoning']['effort'],'high')
    if 'temporary helper' in payload['messages'][0]['content']:return json.dumps({'report':'Here is a context summary; no execution was needed.','tool_calls':[]})
    ctx=json.loads(payload['messages'][-1]['content']);owner=ctx['member_id'];counts[owner]=counts.get(owner,0)+1
    action={'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]}
    if counts[owner]==1:action['tool_calls']=[{'name':'delegate','arguments':{'task':'Summarize relevant context'}}]
    else:self.assertIn('context summary',json.dumps(ctx['tool_results']));action['budget_choice']='end'
    return json.dumps(action)
   backend.reply_factory=reply;server.sandbox.start(server.sandbox.owner,{'npc_enabled':False});settle(server.event);self.assertEqual(server.event.state['status'],'completed');self.assertEqual(len(backend.records),6);self.assertEqual(server.event.state['completed_calls'],6);self.assertEqual(server.event.state['reasoning_effort'],'high')
