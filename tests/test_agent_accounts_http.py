import json
from dataclasses import replace
from tests import test_identity_http as fixtures
from tests.test_identity_sandbox import persona
from tests.test_host_event import silent
from tests.test_local_memory import FakeMemory
from residency.local_mem0 import AgentMem0
import unittest


class AgentAccountsHTTPTests(unittest.TestCase):
    setUp=fixtures.IdentityHTTPTests.setUp

    def test_existing_terra_agents_need_limits_before_more_networking(self):
        self.client.join()
        self.server.settings=replace(self.server.settings,hermes_model='gpt-5.6-terra')
        for slot in (1,2,3):
            self.client.request('/api/sandbox/agents','POST',{'slot':slot,'identity':persona(str(slot))})
        code,result,_=self.client.request('/api/event/start','POST',{'max_calls':1,'npc_enabled':False})
        self.assertEqual(code,409)
        self.assertIn('USD allowance',result['error'])
        self.assertEqual(self.gateway.records,[])

    def prepare(self):
        self.client.join()
        self.server.settings=replace(self.server.settings,hermes_model='gpt-5.6-terra')
        self.server.hermes.settings=self.server.settings
        self.gateway.models=[{'id':'gpt-5.6-terra','root':'gpt-5.6-terra'}]
        self.gateway.budget_guard='residency-usd-v1'
        self.gateway.usage={'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}
        for slot in (1,2,3):
            code,review,_=self.client.request('/api/sandbox/identity/review','POST',{'identity':persona(str(slot))})
            self.assertEqual(code,200)
            code,body,_=self.client.request('/api/sandbox/identity/submit','POST',{'slot':slot,'markdown':review['markdown'],'cv_evidence':[],'budget':{'limit_usd':'10','reserve_usd':'1.90'}})
            self.assertEqual(code,200,body)
        return list(self.server.event.personas)

    def test_signup_budget_request_model_usage_and_conversation_links(self):
        self.assertEqual(self.client.request('/api/agent-accounts')[0],401)
        a,b,c=self.prepare()
        request={'owner_id':a,'target_id':b,'body':'PRIVATE Ask about building a music prototype'}
        self.assertEqual(self.client.request('/api/agent-requests','POST',request,{'X-CSRF-Token':'bad'})[0],403)
        self.assertEqual(self.client.request('/api/agent-requests','POST',request)[0],200)
        self.assertEqual(self.gateway.records,[])
        def reply(payload):
            context=json.loads(payload['messages'][-1]['content'])
            target=next(p for p in context['action_options']['peer_ids'] if p in (a,b,c) and p!=context['member_id'])
            return json.dumps({**silent(),'start_conversations':[{'with':target,'body':'A useful idea to discuss'}]})
        self.gateway.reply_factory=reply
        self.assertEqual(self.client.request('/api/event/start','POST',{'max_calls':3,'npc_enabled':False})[0],200)
        for thread in self.server.event.threads:thread.join(5)
        state=self.client.request('/api/agent-accounts')[1]
        self.assertEqual(sum(agent['wallet']['total_tokens'] for agent in state['agents']),3300)
        self.assertAlmostEqual(sum(agent['wallet']['spent_usd'] for agent in state['agents']),.0096)
        self.assertEqual(sum(link['kind']=='produced' for agent in state['agents'] for item in agent['usage'] for link in item['links']),3)
        for record in self.gateway.records:
            context=json.loads(record['payload']['messages'][-1]['content'])
            self.assertEqual(bool(context['human_requests']),context['member_id']==a)
        self.assertTrue(all(agent['wallet']['held_usd']==0 for agent in state['agents']))
        token,csrf=self.server.store.new_session(b)
        headers={'Cookie':'residency_session='+token,'X-CSRF-Token':csrf}
        self.assertEqual(self.client.request('/api/agent-accounts',headers=headers)[0],403)
        self.assertEqual(self.client.request('/api/agent-budget','POST',{'owner_id':a,'limit_usd':20,'reserve_usd':2},headers)[0],403)

    def test_invalid_output_still_accounts_usage_and_unknown_response_keeps_hold(self):
        a,b,c=self.prepare()
        self.gateway.reply='invalid action'
        self.assertEqual(self.client.request('/api/event/start','POST',{'max_calls':1,'npc_enabled':False})[0],200)
        for thread in self.server.event.threads:thread.join(5)
        usage=[item for agent in self.client.request('/api/agent-accounts')[1]['agents'] for item in agent['usage']]
        self.assertEqual(len(usage),1);self.assertEqual(usage[0]['status'],'recorded')
        self.assertEqual(usage[0]['total_tokens'],1100);self.assertEqual(usage[0]['links'],[])
        self.gateway.reply=json.dumps(silent());self.gateway.usage=None
        self.client.request('/api/event/start','POST',{'max_calls':1,'npc_enabled':False})
        for thread in self.server.event.threads:thread.join(5)
        usage=[item for agent in self.client.request('/api/agent-accounts')[1]['agents'] for item in agent['usage']]
        unknown=next(item for item in usage if item['status']=='unknown')
        self.assertEqual(unknown['hold_usd'],1.9);self.assertIsNone(unknown['total_tokens'])

    def test_markdown_export_retrieval_visibility_and_scope(self):
        a,b,c=self.prepare();event=self.server.event;event.state['event_id']='markdown-test'
        fake=FakeMemory();self.server.semantic=AgentMem0(self.server,fake)
        result=self.server.store.conversation_action(a,{'start_conversations':[{'with':b,'body':'PRIVATE BEFORE JOIN a useful music idea'}]})
        room=result['created_conversations'][0];event.rooms.add(room)
        self.server.store.conversation_action(c,{'join_conversations':[room]})
        self.server.store.conversation_action(b,{'messages':[{'conversation_id':room,'body':'A new useful musical idea'}]})
        self.server.capture_conversations([a,b,c]);self.server.semantic.queue.join()
        code,export,_=self.client.request('/api/agent-memory/document?agent='+c)
        self.assertEqual(code,200);self.assertIn('# Personal conversation memory',export['markdown'])
        self.assertNotIn('PRIVATE BEFORE JOIN',export['markdown'])
        path=self.server.semantic.markdown_path(c)
        self.assertTrue(path.is_file());self.assertEqual(path.stat().st_mode&0o777,0o600)
        code,recall,_=self.client.request('/api/agent-memory?agent='+c+'&q=idea')
        self.assertEqual(code,200);self.assertTrue(recall['results'])
        self.assertEqual(recall['retrieval'],'local_markdown_with_mem0_semantic_ranking')
        self.assertEqual(self.client.request('/api/agent-memory/document?agent=../../etc/passwd')[0],400)
        token,csrf=self.server.store.new_session(b)
        self.assertEqual(self.client.request('/api/agent-memory/document?agent='+c,headers={'Cookie':'residency_session='+token})[0],403)
        self.server.memory.set_policy(c,{'recall_enabled':False})
        self.assertNotIn('An unverified useful idea',self.client.request('/api/agent-memory/document?agent='+c)[1]['markdown'])
