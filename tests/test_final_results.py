import copy,json,unittest
from residency.final_results import check_refs,validate_assessment,questionnaire_context,ReportModel
from tests.test_end_questionnaire import EndQuestionnaireTests,answers
class FinalReportTests(EndQuestionnaireTests):
 def test_second_questionnaire_uses_only_witnessed_sources_and_public_starting_fields(self):
  self.state['starting_identities']['a'].update(political_outlook='PRIVATE POLITICS',moral_care='PRIVATE VALUES',cv='PRIVATE CV')
  packet=questionnaire_context(self.db,self.state,'a',self.data)
  self.assertNotIn('PRIVATE',json.dumps(packet));self.assertEqual(len(packet['questionnaires']),2);self.assertEqual(packet['own_memories'],[])
  value={'story':{'chapters':[{'message_ids':['one']}]},'networking':answers(packet),'judgment':{q['id']:{'answer':'Insufficient evidence for a change.','evidence':[],'paper_sections':[]} for q in packet['questionnaires'][1]['questions']}}
  self.assertEqual(validate_assessment(value,packet),value)
  value['judgment']['values']['evidence']=[{'message_id':'hidden','quote':'SECRET OTHER ROOM'}]
  with self.assertRaises(ValueError):validate_assessment(value,packet)
 def test_lineage_claims_cannot_invent_sources_agents_rooms_or_artifacts(self):
  good={'message_ids':['one'],'from_agent_id':'a','to_agent_id':'b','room_ids':['room'],'artifact_id':'board'}
  check_refs(good,[{'id':'one'}],[{'id':'a'},{'id':'b'}],['room'],['board'])
  for key,bad in [('message_ids',['secret']),('to_agent_id','c'),('room_ids',['other']),('artifact_id','missing')]:
   with self.subTest(key=key):
    with self.assertRaises(ValueError):check_refs({**good,key:bad},[{'id':'one'}],[{'id':'a'},{'id':'b'}],['room'],['board'])

class ReportDispatchTests(unittest.TestCase):
 def setUp(self):
  import tempfile
  from pathlib import Path
  from unittest.mock import patch
  import residency.final_results as reports
  self.reports=reports;self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name);reports.save(self.base/'state.json',{'event_id':'test'})
  self.state={'event_id':'test','status':'stopped','thinking':[]};real_load=reports.load
  self.patch=patch.object(reports,'load',side_effect=lambda p:self.state if Path(p)==reports.ROOT/'.data/live-residency/state/host-event/state.json' else real_load(p));self.patch.start();self.addCleanup(self.patch.stop)
  self.gateway=self.Gateway()
 class Gateway:
  def __init__(self):self.calls=[];self.response={'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}
  def check(self):pass
  def request(self,path,payload=None,headers=None,timeout=None):
   if path=='/health':return {'residency_budget_guard':'residency-usd-v1'}
   self.calls.append((path,headers));return self.response
 def test_running_event_and_oversized_packets_never_send_inference(self):
  model=ReportModel(self.base,self.gateway);self.state['status']='running'
  with self.assertRaises(RuntimeError):model.call('one','system',{},lambda x:x)
  self.state['status']='stopped'
  with self.assertRaises(ValueError):model.call('one','system',{'text':'x'*100000},lambda x:x)
  self.assertEqual(self.gateway.calls,[])
 def test_completed_analysis_is_cached_with_exact_cost_and_no_resident_wallet_write(self):
  model=ReportModel(self.base,self.gateway);self.assertEqual(model.call('one','system',{},lambda x:x),{'ok':True});self.assertEqual(model.call('one','system',{},lambda x:x),{'ok':True});self.assertEqual(len(self.gateway.calls),1);self.assertEqual(model.entries[0]['cost_usd'],400);self.assertEqual(model.entries[0]['hold_usd'],0)
 def test_unknown_dispatch_keeps_its_hold_and_cannot_be_replayed(self):
  model=ReportModel(self.base,self.gateway,budget_usd=1.9);self.gateway.response={'hermes':{'failed':True}}
  with self.assertRaises(Exception):model.call('one','system',{},lambda x:x)
  self.assertEqual(model.entries[0]['status'],'unknown');self.assertEqual(model.entries[0]['hold_usd'],1900000)
  with self.assertRaises(RuntimeError):model.call('one','system',{},lambda x:x)
  with self.assertRaises(RuntimeError):model.call('two','system',{},lambda x:x)
  self.assertEqual(len(self.gateway.calls),1)
 def test_quota_pauses_assessment_without_resuming_networking_or_fallback(self):
  from residency.provider_limits import ProviderQuotaPause
  model=ReportModel(self.base,self.gateway);self.gateway.response={'residency_provider_error':{'code':'usage_limit_reached'}}
  with self.assertRaises(ProviderQuotaPause):model.call('one','system',{},lambda x:x)
  self.assertTrue(model.stop.is_set());self.assertEqual(model.entries[0]['hold_usd'],0);self.assertEqual(self.state['status'],'stopped')

class RelayEvidenceTests(unittest.TestCase):
 def test_a_named_person_is_not_enough_for_a_temporally_witnessed_chain(self):
  from scripts.final_hops import validate_hops
  run={'people':[{'id':i} for i in ('a','b','c')],'messages':[{'id':'m1','sender_id':'a','recipients':['b'],'created_at':1,'conversation_id':'ab'},{'id':'m2','sender_id':'b','recipients':['c'],'created_at':2,'conversation_id':'bc'},{'id':'m3','sender_id':'c','recipients':['b'],'created_at':3,'conversation_id':'bc'}]}
  chain={'origin_agent_id':'a','intermediary_agent_id':'b','recipient_agent_id':'c','source_message_id':'m1','relay_message_id':'m2','receipt_message_id':'m3'};value={'chains':[chain],'unproven':[],'coverage':'Test'};self.assertEqual(validate_hops(value,run,{'m1','m2','m3'}),value)
  bad=copy.deepcopy(run);bad['messages'][0]['recipients']=[]
  with self.assertRaises(ValueError):validate_hops(value,bad,{'m1','m2','m3'})
  bad=copy.deepcopy(run);bad['messages'][0]['created_at']=4
  with self.assertRaises(ValueError):validate_hops(value,bad,{'m1','m2','m3'})
