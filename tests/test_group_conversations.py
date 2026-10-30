import json,unittest
from residency.store import AppError
from residency.agent_tools import AgentTools
from tests.test_cohort import fixture,apply,export,import_payload,settle

class GroupConversationTests(unittest.TestCase):
 def prepare(self,server):
  apply(server,None,import_payload(export(6)));server.agent_tools=AgentTools(server);event=server.event;event.state.update(status='running',event_id='synthetic-group');return event,list(event.personas)
 def test_group_start_does_not_merge_dm_and_nonmembers_cannot_recall_or_read_state(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c,d,e,f)=self.prepare(server);store=server.store
   dm=store.conversation_action(a,{'start_conversations':[{'with':b,'body':'PRIVATE-DM'}]})['created_conversations'][0];event.rooms.add(dm)
   result=store.conversation_action(a,{'start_conversations':[{'with':[b,c,d],'body':'Group opening for four residents'}]},reuse_direct_rooms=event.rooms);room=result['created_conversations'][0];event.rooms.add(room)
   self.assertNotEqual(room,dm);self.assertEqual(set(result['affected_members']),{a,b,c,d})
   for member in (c,d):
    context=event.context(member);self.assertIn('Group opening for four residents',json.dumps(context));self.assertNotIn('PRIVATE-DM',json.dumps(context))
   for member in (e,f):self.assertNotIn('Group opening for four residents',json.dumps(event.context(member)))
   collab=server.agent_tools.collaboration;workspace=collab.workspace_write(a,{'conversation_id':room,'title':'Game','state':'GROUP-STATE'},True)
   server.agent_tools.run(a,1,[{'name':'board_add','arguments':{'conversation_id':room,'title':'GROUP-BOARD','text':'only witnessed collaborators'}}])
   self.assertNotIn('GROUP-BOARD',json.dumps(server.agent_tools.boards(e)));self.assertNotIn('Group opening',json.dumps(collab.recall(e,{'conversation_id':room})))
   with self.assertRaises(AppError):collab.workspace_read(e,{'workspace_id':workspace['workspace_id']})
   with self.assertRaises(AppError):store.conversation_action(e,{'messages':[{'conversation_id':room,'body':'Not joined'}]})
   store.conversation_action(e,{'join_conversations':[room]});self.assertEqual(len(store.conversation_state(e)['conversation_messages']),0)
   with self.assertRaises(AppError):collab.workspace_read(e,{'workspace_id':workspace['workspace_id']})
   store.conversation_action(b,{'messages':[{'conversation_id':room,'body':'AFTER-E-JOINED'}]});self.assertIn('AFTER-E-JOINED',json.dumps(event.context(e)));self.assertNotIn('GROUP-STATE',json.dumps(event.context(e)))
   self.assertEqual(len(next(r for r in store.conversation_state(a)['conversations'] if r['id']==room)['participants']),5)
   store.conversation_action(e,{'leave_conversations':[room]});store.conversation_action(b,{'messages':[{'conversation_id':room,'body':'GAP-PRIVATE'}]});store.conversation_action(e,{'join_conversations':[room]});self.assertNotIn('GAP-PRIVATE',json.dumps(event.context(e)));self.assertEqual(backend.records,[])
 def test_invalid_group_lists_fail_atomically_and_model_validator_rejects_outside_event(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c,d,e,f)=self.prepare(server)
   for peers in ([],[b,b],[a,b],[b,'missing'],[b,{}],None):
    with self.subTest(peers=peers):
     with self.assertRaises(AppError):server.store.conversation_action(a,{'start_conversations':[{'with':peers,'body':'Invalid'}]})
   self.assertEqual(server.store.conversation_state(a)['conversations'],[])
   action={'wait_seconds':0,'start_conversations':[{'with':[b,c,d,e,f],'body':'All six may talk together'}],'join_conversations':[],'messages':[],'leave_conversations':[]}
   self.assertEqual(event.validate(a,action)[0]['start_conversations'][0]['with'],[b,c,d,e,f])
   result=server.store.conversation_action(a,{'start_conversations':action['start_conversations']});room=result['created_conversations'][0];self.assertEqual(len(next(r for r in server.store.conversation_state(a)['conversations'] if r['id']==room)['participants']),6)
   with self.assertRaises(AppError):event.validate(a,{**action,'start_conversations':[{'with':[b,'outside-event'],'body':'blocked'}]})
 def test_fake_networking_model_creates_group_and_outsider_does_not_get_contents(self):
  with fixture() as (server,client,backend,memory):
   apply(server,client,import_payload(export(4)));server.agent_tools=AgentTools(server);a,b,c,d=server.event.personas;counts={}
   def reply(payload):
    ctx=json.loads(payload['messages'][-1]['content']);owner=ctx['member_id'];counts[owner]=counts.get(owner,0)+1
    result={'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]}
    if owner==a and counts[owner]==1:result['start_conversations']=[{'with':[b,c],'body':'GROUP-SECRET'}]
    else:
     if owner==d:self.assertNotIn('GROUP-SECRET',json.dumps(ctx))
     result['budget_choice']='end'
    return json.dumps(result)
   backend.reply_factory=reply;server.sandbox.start(server.sandbox.owner,{'npc_enabled':False});settle(server.event)
   self.assertEqual(server.event.state['status'],'completed');self.assertEqual(len(backend.records),5);self.assertEqual(len(server.event.rooms),1)
   self.assertIn('GROUP-SECRET',json.dumps(server.store.conversation_state(b)));self.assertNotIn('GROUP-SECRET',json.dumps(server.store.conversation_state(d)))
