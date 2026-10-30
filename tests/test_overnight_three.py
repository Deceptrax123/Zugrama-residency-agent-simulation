"""Fake provider only: no live simulation is launched by these tests."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import sys

from residency.config import APP_ROOT
from residency.identity import markdown,validate_identity
from tests.support import gateway,settings
from tests.test_identity_sandbox import persona
from tests.test_local_memory import FakeMemory
sys.path.insert(0,str(APP_ROOT/'scripts'))
import overnight_three as runner


class OvernightThreeTests(unittest.TestCase):
    def test_two_isolated_weeks_have_hard_caps_reflections_ledgers_and_replay(self):
        def reply(payload):
            ctx=json.loads(payload['messages'][-1]['content'])
            self.assertNotIn('private_memory',ctx);self.assertNotIn('retrieved_memories',ctx)
            rooms=[r for r in ctx['conversations'] if r['joined']]
            action={'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]}
            if rooms:action['messages']=[{'conversation_id':rooms[0]['id'],'body':'I enjoy music and discussing useful ideas.'}]
            else:action['start_conversations']=[{'with':next(p['id'] for p in ctx['directory'] if p['id']!=ctx['member_id']),'body':'What would you enjoy discussing?'}]
            return json.dumps(action)
        with tempfile.TemporaryDirectory(dir=APP_ROOT/'.data') as tmp,gateway() as backend,settings(hermes_url=backend.url,hermes_key='synthetic-only',hermes_model=runner.MODEL) as config:
            batch=Path(tmp);backend.reply_factory=reply;backend.models=[{'id':runner.MODEL,'root':runner.MODEL}];backend.budget_guard='residency-usd-v1';backend.usage={'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}
            profiles=[]
            for slot,name in enumerate(('Synthetic One','Synthetic Two','Synthetic Three'),1):
                identity=validate_identity(persona(name));profiles.append({'slot':slot,'identity':identity,'markdown':markdown(identity),'memory_policy':None})
            initial=json.dumps(profiles,sort_keys=True);client=FakeMemory()
            reports=[]
            for number in (1,2):
                report=runner.run_trial(batch,number,profiles,config,time.monotonic()+120,memory=client);reports.append(report)
                self.assertEqual(report['status'],'completed',report)
                self.assertEqual(report['calls'],40);self.assertEqual(report['reflections'],21);self.assertEqual(report['total_tokens'],44000)
                self.assertTrue(report['identity_unchanged']);self.assertEqual(len(report['day_log']),7)
                directory=batch/f'run-{number:02d}'
                self.assertEqual(len(list((directory/'calls').glob('*/response.json'))),40)
                self.assertTrue((directory/'communication.html').is_file());self.assertTrue(json.loads((directory/'graph.json').read_text())['deliveries'])
                for slot in (1,2,3):
                    agent=directory/'agents'/str(slot)
                    self.assertTrue((agent/'MEMORY.md').is_file());self.assertEqual(len(list(agent.glob('REFLECTION-day-*.md'))),7)
                self.assertTrue(all(a['wallet']['held_usd']==0 for a in json.loads((directory/'accounts.json').read_text())['agents']))
            self.assertEqual(len(backend.records),80)
            self.assertEqual(initial,json.dumps(profiles,sort_keys=True))
            events=[json.loads((batch/f'run-{n:02d}'/'event.json').read_text())['event_id'] for n in (1,2)]
            self.assertNotEqual(*events)
            with self.assertRaises(ValueError):runner.run_trial(batch,3,profiles,config,time.monotonic()+120,memory=client)
            with self.assertRaises(FileExistsError):runner.run_trial(batch,1,profiles,config,time.monotonic()+120,memory=client)

    def test_attempted_batch_cannot_be_resumed_and_source_hash_is_checked(self):
        with tempfile.TemporaryDirectory(dir=APP_ROOT/'.data') as tmp:
            path=Path(tmp);runner.private_json(path/'manifest.json',{'status':'running','runs':[{'number':1}]})
            with patch.object(runner,'location',return_value=path),patch.object(runner,'run_trial') as launch:
                with self.assertRaises(ValueError):runner.run('ignored')
                launch.assert_not_called()
            runner.private_json(path/'manifest.json',{'status':'prepared','runs':[],'source_hash':'changed'})
            runner.private_json(path/'starting-personas.json',[])
            with patch.object(runner,'location',return_value=path),patch.object(runner,'run_trial') as launch:
                with self.assertRaises(ValueError):runner.run('ignored')
                launch.assert_not_called()
