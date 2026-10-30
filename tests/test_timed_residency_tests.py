import json
import sys
import tempfile
import unittest
from pathlib import Path
from residency.config import APP_ROOT
from residency.identity import validate_identity
from residency.identity_document import document
from tests.support import gateway,settings
from tests.test_identity_sandbox import persona
from tests.test_local_memory import FakeMemory
sys.path.insert(0,str(APP_ROOT/'scripts'))
import timed_residency_tests as runner


class TimedTests(unittest.TestCase):
    def setUp(self):
        (APP_ROOT/'.data').mkdir(exist_ok=True)

    def test_isolated_paced_run_has_audits_memories_reflections_and_no_replay(self):
        def reply(payload):
            ctx=json.loads(payload['messages'][-1]['content']);rooms=[r for r in ctx['conversations'] if r['joined']]
            action={'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]}
            if rooms:action['messages']=[{'conversation_id':rooms[0]['id'],'body':'We can discuss music and useful ideas.'}]
            else:action['start_conversations']=[{'with':next(p['id'] for p in ctx['directory'] if p['id']!=ctx['member_id']),'body':'What interests you?'}]
            return json.dumps(action)
        profiles=[]
        for slot in range(1,4):
            value=validate_identity(persona('Synthetic '+str(slot)))
            profiles.append({'slot':slot,'identity':value,'markdown':document(value),'budget':{'limit_usd':'10.00','reserve_usd':'1.90'},'memory_policy':{'network_context':True}})
        with tempfile.TemporaryDirectory(dir=APP_ROOT/'.data') as tmp,gateway() as backend,settings(hermes_url=backend.url,hermes_key='synthetic',hermes_model='gpt-5.6-terra') as cfg:
            backend.models=[{'id':'gpt-5.6-terra','root':'gpt-5.6-terra'}];backend.budget_guard='residency-usd-v1';backend.usage={'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100};backend.reply_factory=reply
            memory=FakeMemory();memory.health=lambda:{'status':'ready'}
            batch=Path(tmp);result=runner.run_trial(batch,1,profiles,cfg,target_seconds=1,max_calls=6,backend=runner.Hermes(cfg),memory=memory)
            self.assertEqual(result['status'],'completed',result)
            self.assertEqual(result['calls'],6);self.assertEqual(result['reflections'],3)
            self.assertEqual(result['request_audits'],6);self.assertEqual(result['response_audits'],6)
            self.assertEqual(result['context_audit_errors'],[]);self.assertEqual(result['held_usd'],0)
            self.assertAlmostEqual(result['estimated_usd'],.0192)
            self.assertTrue(result['notes']);self.assertTrue((batch/'run-01/communication.html').exists())
            with self.assertRaises(FileExistsError):runner.run_trial(batch,1,profiles,cfg,target_seconds=1,backend=backend,memory=FakeMemory())
            with self.assertRaises(ValueError):runner.run_trial(batch,3,profiles,cfg,target_seconds=1,backend=backend,memory=FakeMemory())


if __name__=='__main__':unittest.main()
