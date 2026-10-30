from dataclasses import replace
import copy,json,time,unittest
from unittest.mock import patch
from residency.semantic_insights import SemanticInsights,validate_report
from residency.store import AppError
from tests.test_cohort import fixture,apply,export,import_payload

class SemanticTests(unittest.TestCase):
 def test_model_report_scope_cache_usage_and_no_networking_start(self):
  with fixture() as (server,client,backend,memory):
   apply(server,client,import_payload(export(2)));event=server.event
   owners=list(event.personas);action=server.store.conversation_action(owners[0],{'start_conversations':[{'with':owners[1],'body':'A proposal about shared water monitoring.'}],'join_conversations':[],'messages':[],'leave_conversations':[]})
   event.rooms.update(action['created_conversations']);event.state.update(event_id='analysis-fixture',status='completed');event._save()
   server.settings=replace(server.settings,hermes_model='gpt-6.1-sol');backend.models.append({'id':'gpt-6.1-sol','root':'gpt-6.1-sol'})
   analyzer=SemanticInsights(server);packets=analyzer.packets();self.assertEqual(len(packets),3)
   def reply(payload):
    self.assertEqual(payload['model'],'gpt-6.1-sol');context=json.loads(payload['messages'][-1]['content']);m=context['messages'][0]
    return json.dumps({'summary':'A proposed collaboration, not an executed project.','topics':[{'id':'t1','label':'Community measurement','summary':'A proposal','message_ids':[m['id']]}],'topic_flow':[],'ideas':[],'lineage':[],'communities':[],'uncertainties':['No demonstrated relay.']})
   backend.reply_factory=reply;analyzer.start(server.sandbox.owner,{'confirmed':True});analyzer.thread.join(10)
   self.assertEqual(analyzer.status()['status'],'completed');self.assertEqual(analyzer.status()['calls'],3);self.assertGreater(analyzer.status()['tokens'],0)
   self.assertEqual(event.state['status'],'completed');self.assertEqual(event.state['calls'],0)
   for p in packets:self.assertEqual(analyzer.get('analysis-fixture',p['scope'])['model'],'gpt-6.1-sol')
   analyzer.start(server.sandbox.owner,{'confirmed':True});analyzer.thread.join(10);self.assertEqual(analyzer.status()['calls'],0)
   report=analyzer.get('analysis-fixture','host')['report'];bad=copy.deepcopy(report);bad['topics'][0]['message_ids']=['hidden']
   with self.assertRaises(AppError):validate_report(bad,packets[0]['messages'],packets[0]['people'])
   hidden=server.store.conversation_action(owners[0],{'start_conversations':[{'with':owners[1],'body':'Before a late join'}],'join_conversations':[],'messages':[],'leave_conversations':[]})
   # Removing an owner's joined visit makes that room absent from its input packet.
   room=hidden['created_conversations'][0];event.rooms.add(room)
   with server.store.db() as db:db.execute('DELETE FROM conversation_visits WHERE conversation_id=? AND member_id=?',(room,owners[1]))
   scoped=next(p for p in analyzer.packets() if p['scope']==owners[1]);self.assertNotIn('Before a late join',json.dumps(scoped))

 def test_analysis_quota_keeps_networking_stopped_and_does_not_retry(self):
  with fixture() as (server,client,backend,memory):
   apply(server,client,import_payload(export(2)));event=server.event;owners=list(event.personas)
   action=server.store.conversation_action(owners[0],{'start_conversations':[{'with':owners[1],'body':'An idea'}],'join_conversations':[],'messages':[],'leave_conversations':[]});event.rooms.update(action['created_conversations']);event.state.update(event_id='quota-analysis',status='paused_quota');event._save()
   analyzer=SemanticInsights(server);real=server.hermes.request;calls=[]
   def request(path,payload=None,headers=None,timeout=None):
    if path=='/v1/chat/completions':calls.append(payload);return {'residency_provider_error':{'code':'usage_limit_reached'}}
    return real(path,payload,headers,timeout)
   with patch.object(server.hermes,'request',side_effect=request):analyzer.start(server.sandbox.owner,{'confirmed':True});analyzer.thread.join(10)
   self.assertEqual(len(calls),1);self.assertEqual(analyzer.status()['status'],'paused_quota');self.assertEqual(analyzer.status()['held_usd'],0);self.assertEqual(event.state['calls'],0)
