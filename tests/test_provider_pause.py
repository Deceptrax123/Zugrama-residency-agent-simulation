from dataclasses import replace
import json,unittest
from unittest.mock import patch
from residency.provider_limits import ProviderQuotaPause,quota_detail,check_completion
from tests.test_cohort import fixture,apply,export,import_payload,settle

class QuotaPauseTests(unittest.TestCase):
 def test_quota_signal_is_explicit_and_generic_errors_are_not_classified_as_quota(self):
  class Error(Exception):body={'error':{'type':'usage_limit_reached','resets_at':12345,'plan_type':'private'}}
  detail=quota_detail(Error());self.assertEqual(detail['resets_at'],12345);self.assertNotIn('plan_type',detail)
  with self.assertRaises(ProviderQuotaPause):check_completion({'residency_provider_error':detail})
  self.assertIsNone(quota_detail(Exception('429')))

 def test_quota_pauses_all_workers_and_resume_keeps_event_rooms_and_ledger(self):
  with fixture() as (server,client,backend,memory):
   apply(server,client,import_payload(export(2)))
   real=server.hermes.request
   def request(path,payload=None,headers=None,timeout=None):
    if path=='/v1/chat/completions':return {'residency_provider_error':{'code':'usage_limit_reached','resets_at':12345},'hermes':{'failed':True}}
    return real(path,payload,headers,timeout)
   with patch.object(server.hermes,'request',side_effect=request):
    server.sandbox.start(server.sandbox.owner,{'npc_enabled':False,'seven_days':True});settle(server.event)
   event=server.event;event_id=event.state['event_id'];calls=event.state['calls']
   self.assertEqual(event.state['status'],'paused_quota');self.assertEqual(event.state['completed_calls'],0)
   with server.store.db() as db:self.assertEqual(db.execute("select count(*) from agent_usage where status='rejected' and hold_usd=0").fetchone()[0],calls)
   backend.reply=json.dumps({'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[],'budget_choice':'end'})
   event.resume(server.sandbox.owner);settle(event)
   self.assertEqual(event.state['event_id'],event_id);self.assertEqual(server.cycle.state['day'],1);self.assertEqual(event.state['status'],'completed');self.assertGreater(event.state['calls'],calls)
   self.assertEqual(event.state['completed_calls'],2)
