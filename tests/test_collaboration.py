import json,threading,unittest
from unittest.mock import Mock
from residency.agent_tools import AgentTools
from residency.store import AppError
from tests.test_cohort import fixture,apply,export,import_payload,settle

class CollaborationTests(unittest.TestCase):
 def prepare(self,server):
  apply(server,None,import_payload(export(3)));server.agent_tools=AgentTools(server,search=Mock());event=server.event;event.state.update(event_id='optional-continuity',status='running');a,b,c=event.personas
  room=server.store.conversation_action(a,{'start_conversations':[{'with':b,'body':'An earlier conversation about a musical game'}]})['created_conversations'][0];event.rooms.add(room)
  return event,(a,b,c),room,server.agent_tools.collaboration
 def test_private_notes_revision_md_repair_permission_changes_and_event_scope(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c),room,store=self.prepare(server);server.memory.set_policy(a,{'network_context':True});before=json.dumps(event.personas[a],sort_keys=True)
   source=store.witnessed(a)[0]['id'];args={'peer_id':b,'text':'A fallible impression: Bob enjoys music','expected_revision':0,'source_message_ids':[source]}
   self.assertEqual(store.note_write(a,args)['revision'],1);self.assertIn('enjoys music',store.note_read(a,{'peer_id':b})['text']);self.assertFalse(store.note_read(c,{'peer_id':b})['found'])
   with self.assertRaises(AppError):store.note_write(a,args)
   path=next((server.settings.data_dir/'collaboration').rglob('*.md'));self.assertEqual(path.stat().st_mode&0o777,0o600);path.write_text('damaged');self.assertIn('enjoys music',store.note_read(a,{'peer_id':b})['text']);self.assertIn('collaboration-record',path.read_text())
   server.agent_tools.run(a,5,[{'name':'person_note_read','arguments':{'peer_id':b}}]);self.assertIn('enjoys music',json.dumps(server.agent_tools.context(a)))
   server.memory.set_policy(a,{'network_context':False});self.assertNotIn('enjoys music',json.dumps(server.agent_tools.context(a)))
   with self.assertRaises(AppError):store.note_read(a,{'peer_id':b})
   server.memory.set_policy(a,{'network_context':True,'exclude_terms':['music']});self.assertNotIn('enjoys music',json.dumps(server.agent_tools.context(a)))
   server.memory.set_policy(a,{'exclude_terms':[],'capture_conversations':False})
   with self.assertRaises(AppError):store.note_write(a,{**args,'expected_revision':1})
   self.assertEqual(before,json.dumps(event.personas[a],sort_keys=True));event.state['event_id']='another';self.assertFalse(store.note_read(a,{'peer_id':b})['found']);self.assertEqual(backend.records,[])
 def test_witnessed_recall_late_joins_leave_gaps_and_targeted_pagination(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c),room,store=self.prepare(server)
   server.store.conversation_action(c,{'join_conversations':[room]});server.store.conversation_action(b,{'messages':[{'conversation_id':room,'body':'VISIBLE-C'}]});server.store.conversation_action(c,{'leave_conversations':[room]});server.store.conversation_action(b,{'messages':[{'conversation_id':room,'body':'PRIVATE-GAP'}]});server.store.conversation_action(c,{'join_conversations':[room]});server.store.conversation_action(a,{'messages':[{'conversation_id':room,'body':'AFTER-REJOIN'}]})
   recall=store.recall(c,{'conversation_id':room,'limit':1});self.assertEqual(recall['messages'][0]['body'],'AFTER-REJOIN');earlier=store.recall(c,{'conversation_id':room,'before_seq':recall['earlier_before_seq']});self.assertIn('VISIBLE-C',json.dumps(earlier));self.assertNotIn('PRIVATE-GAP',json.dumps(earlier));self.assertNotIn('musical game',json.dumps(earlier));self.assertIn(a,[r['peer_id'] for r in store.context(c)['encounter_index']]);self.assertIn('musical game',json.dumps(store.recall(b,{'peer_id':a})))
   with self.assertRaises(AppError):store.note_write(c,{'peer_id':a,'text':'No access','expected_revision':0,'source_message_ids':[store.witnessed(a)[0]['id']]})
 def test_shared_revision_visibility_handoffs_conflicts_and_long_pages(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c),room,store=self.prepare(server);r=store.workspace_write(a,{'conversation_id':room,'title':'Optional musical game','state':'Initial position'},True);wid=r['workspace_id'];self.assertEqual(store.workspace_read(b,{'workspace_id':wid})['text'],'Initial position')
   with self.assertRaises(AppError):store.workspace_read(c,{'workspace_id':wid})
   server.store.conversation_action(c,{'join_conversations':[room]})
   with self.assertRaises(AppError):store.workspace_read(c,{'workspace_id':wid})
   store.workspace_write(b,{'workspace_id':wid,'expected_revision':1,'state':'Explicit handoff: initial position; c is joining'})
   self.assertEqual(store.workspace_read(c,{'workspace_id':wid})['revision'],2);server.store.conversation_action(a,{'leave_conversations':[room]});store.workspace_write(b,{'workspace_id':wid,'expected_revision':2,'state':'State during a gap'});server.store.conversation_action(a,{'join_conversations':[room]});self.assertEqual(store.workspace_read(a,{'workspace_id':wid})['revision'],2)
   with self.assertRaises(AppError):store.workspace_write(a,{'workspace_id':wid,'expected_revision':2,'state':'Stale update'})
   long='🎶x'*5000;store.workspace_write(b,{'workspace_id':wid,'expected_revision':3,'state':long,'status':'paused'});offset=0;parts=[]
   while True:
    page=store.workspace_read(a,{'workspace_id':wid,'offset':offset});self.assertLessEqual(len(json.dumps(page,ensure_ascii=False).encode()),10000);parts.append(page['text']);offset=page['next_offset']
    if offset is None:break
   self.assertEqual(''.join(parts),long);self.assertEqual(event.state['message_count'],4);self.assertEqual(len(list((server.settings.data_dir/'collaboration').rglob('*.md'))),4)
   with self.assertRaises(AppError):store.workspace_write(a,{'conversation_id':'other','title':'No room','state':'blocked'},True)
   self.assertEqual(len(store.visible_workspaces(a)),1)
 def test_simultaneous_updates_are_atomic_and_failed_capture_does_not_replay(self):
  with fixture() as (server,client,backend,memory):
   event,(a,b,c),room,store=self.prepare(server);wid=store.workspace_write(a,{'conversation_id':room,'title':'Code','state':'v1'},True)['workspace_id'];barrier=threading.Barrier(2);results=[]
   def update(owner):
    barrier.wait()
    try:results.append(store.workspace_write(owner,{'workspace_id':wid,'expected_revision':1,'state':owner}))
    except AppError as e:results.append(e)
   ts=[threading.Thread(target=update,args=(o,)) for o in (a,b)]
   for t in ts:t.start()
   for t in ts:t.join(5)
   self.assertEqual(sum(isinstance(r,dict) for r in results),1);self.assertEqual(event.state['message_count'],2)
   server.capture_conversations=Mock(side_effect=RuntimeError('synthetic capture failure'));server.agent_tools.run(a,9,[{'name':'workspace_update','arguments':{'workspace_id':wid,'expected_revision':2,'state':'checkpoint after capture error'}}]);server.agent_tools.run(a,9,[{'name':'workspace_update','arguments':{'workspace_id':wid,'expected_revision':2,'state':'MUST NOT REPLAY'}}]);self.assertEqual(store.workspace_read(b,{'workspace_id':wid})['revision'],3);self.assertEqual(event.state['message_count'],3);self.assertEqual(server.agent_tools.history(a)[0]['status'],'completed');self.assertEqual(backend.records,[])

class OptionalWorkflowTests(unittest.TestCase):
 def test_fake_networking_turns_save_then_resume_shared_game_without_extra_model_calls(self):
  with fixture() as (server,client,backend,memory):
   apply(server,client,import_payload(export(2)));server.agent_tools=AgentTools(server);counts={};players=list(server.event.personas);creator=players[0]
   def reply(payload):
    ctx=json.loads(payload['messages'][-1]['content']);owner=ctx['member_id'];counts[owner]=counts.get(owner,0)+1;n=counts[owner]
    action={'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]}
    if owner!=creator:action['budget_choice']='end';return json.dumps(action)
    if n==1:action['start_conversations']=[{'with':players[1],'body':'Would you like to play a musical game?'}]
    elif n==2:
     room=ctx['action_options']['joined_conversation_ids'][0];action['tool_calls']=[{'name':'workspace_create','arguments':{'conversation_id':room,'title':'Our optional game','state':'Turn 1: a C major phrase; next player chooses a variation'}},{'name':'person_note_write','arguments':{'peer_id':players[1],'expected_revision':0,'text':'I invited this person to a musical game; no preference confirmed yet.'}}]
    elif n==3:
     self.assertEqual(len(ctx['workspace_index']),1);self.assertEqual(len(ctx['person_notes_index']),1);action['tool_calls']=[{'name':'workspace_read','arguments':{'workspace_id':ctx['workspace_index'][0]['workspace_id']}}]
    elif n==4:
     self.assertIn('C major phrase',json.dumps(ctx['tool_results']));action['tool_calls']=[{'name':'workspace_update','arguments':{'workspace_id':ctx['workspace_index'][0]['workspace_id'],'expected_revision':1,'state':'Turn 2: a proposed G major variation; awaiting collaborator'}}]
    else:
     self.assertEqual(ctx['workspace_index'][0]['revision'],2);action['budget_choice']='end'
    return json.dumps(action)
   backend.reply_factory=reply;server.sandbox.start(server.sandbox.owner,{'npc_enabled':False});settle(server.event)
   self.assertEqual(server.event.state['status'],'completed');self.assertEqual(len(backend.records),6);self.assertEqual(len(list(server.audit_directory.glob('*/*/request.json'))),6)
   self.assertEqual(len(server.agent_tools.history()),4);self.assertEqual(len(list((server.settings.data_dir/'collaboration').rglob('*.md'))),3)
   with server.store.db() as db:
    self.assertEqual(db.execute('SELECT count(*) FROM workspace_revisions').fetchone()[0],2)
    links=[link for row in db.execute('SELECT links FROM agent_usage') for link in json.loads(row[0])];self.assertEqual(sum(link['kind']=='tool' for link in links),4);self.assertEqual(sum(link['kind']=='produced' for link in links),3)

if __name__=='__main__':unittest.main()
