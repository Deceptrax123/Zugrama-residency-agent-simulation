import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from residency.config import APP_ROOT, Settings
from residency.gateway_config import configure_gateway
from residency.memory import ConversationMemory
from residency.store import Store

spec = importlib.util.spec_from_file_location('residency_demo_three',APP_ROOT/'scripts/demo_three.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


class DemoThreeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='demo-three-check-',dir=APP_ROOT/'.data')
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        change=patch.object(demo,'DATA',self.root/'demo')
        change.start()
        self.addCleanup(change.stop)

    def test_manual_setup_has_three_logins_introductions_and_local_memory_without_model_calls(self):
        with patch.object(demo.subprocess,'Popen',side_effect=AssertionError('No model or worker launch allowed')):
            result=demo.setup()
            self.assertEqual(result['model_calls'],0)
            self.assertFalse(result['autonomous_agents'])
            self.assertTrue(demo.setup()['existing_data_preserved'])
        accounts=json.loads((demo.DATA/'accounts.json').read_text())
        self.assertEqual(len(accounts),3)
        self.assertEqual((demo.DATA/'accounts.json').stat().st_mode & 0o777,0o600)
        config=json.loads((demo.DATA/'demo.json').read_text())
        store=Store(Settings(data_dir=demo.DATA/'state',join_code=config['join_code']))
        memory=ConversationMemory(store)
        for account in accounts:
            token,_=store.login(account)
            self.assertEqual(store.authenticate(token)['member_id'],account['member_id'])
            state=store.snapshot(account['member_id'])
            self.assertEqual(len(state['members']),3)
            self.assertEqual(len(state['introductions']),3)
            self.assertEqual(state['assistant_turns'],[])
            self.assertEqual(state['conversations'],[])
            self.assertTrue(memory.units(account['member_id']))
            self.assertFalse(memory.view(account['member_id'])['external_processing'])

    def test_terra_config_keeps_native_hermes_and_removes_previous_provider_route(self):
        original={'model':{'provider':'nous','default':'old','base_url':'https://old.example'},
                  'fallback_providers':[{'model':'strong'}], 'memory':{'memory_enabled':True}}
        config=configure_gateway(original,'openai-codex','gpt-5.6-terra')
        self.assertEqual(config['model']['provider'],'openai-codex')
        self.assertEqual(config['model']['default'],'gpt-5.6-terra')
        self.assertEqual(config['model']['openai_runtime'],'auto')
        self.assertNotIn('base_url',config['model'])
        self.assertEqual(config['platform_toolsets']['api_server'],[])
        self.assertEqual(config['fallback_providers'],[])
        self.assertFalse(config['memory']['memory_enabled'])
        self.assertFalse(config['auxiliary']['background_review']['enabled'])
        self.assertEqual(config['platforms']['api_server']['extra']['model_routes']['gpt-5.6-terra'],
                         {'model':'gpt-5.6-terra','provider':'openai-codex'})
        self.assertEqual(original['model']['provider'],'nous')
        self.assertEqual(configure_gateway(config)['model']['provider'],'openai-codex')

    def test_gateway_configuration_rejects_unsupported_provider_and_malformed_model(self):
        with self.assertRaises(ValueError): configure_gateway({},'unknown','gpt-5.6-terra')
        with self.assertRaises(ValueError): configure_gateway({},'openai-codex','bad\nmodel')

    def test_stop_does_not_signal_an_unrelated_process(self):
        import os
        demo.DATA.mkdir()
        (demo.DATA/'process.json').write_text(json.dumps({'pid':os.getpid(),'port':7350}))
        with patch.object(demo.os,'kill') as kill:
            with self.assertRaises(ValueError): demo.stop()
        kill.assert_not_called()


if __name__=='__main__':
    unittest.main()
