from dataclasses import replace
import json
import sys
import unittest
from unittest.mock import patch

from residency.agent_tools import AgentTools
from residency.budgets import CALL_HOLD
from residency.gateway_guard import bound_native,MAX_INPUT_BYTES
from tests.test_cohort import fixture,apply,export,import_payload,settle
from tests.test_host import load,SCRIPTS,host


class SolMigrationTests(unittest.TestCase):
    def test_live_sol_override_does_not_change_cv_model_and_unknown_model_fails_closed(self):
        with patch.dict(sys.modules,{'host':host}):runtime=load('sol_runtime_settings',SCRIPTS/'runtime_settings.py')
        with patch.object(runtime,'read_env',return_value={'HERMES_MODEL':'gpt-5.6-terra'}):
            self.assertEqual(runtime.gateway_settings(runtime.ROOT/'.data/test-sol','synthetic-invitation',model='gpt-6.1-sol').hermes_model,'gpt-6.1-sol')
            self.assertEqual(runtime.gateway_settings(runtime.ROOT/'.data/test-cv','synthetic-invitation').hermes_model,'gpt-5.6-terra')
            with self.assertRaises(ValueError):runtime.gateway_settings(runtime.ROOT/'.data/test-sol','synthetic-invitation',model='unknown')

    def test_sol_guard_retains_single_input_tools_and_standard_tier_bounds(self):
        base={'model':'gpt-6.1-sol','input':[{'role':'user','content':'Synthetic model check'}]}
        self.assertEqual(bound_native(base),base)
        for extra in ({'input':'x'*(MAX_INPUT_BYTES+1)},{'tools':[{}]},{'previous_response_id':'hidden'},{'service_tier':'priority'}):
            with self.assertRaises(RuntimeError):bound_native({**base,**extra})
        self.assertGreaterEqual(CALL_HOLD,(MAX_INPUT_BYTES+8192)*2*1.25+128000*10)

    def test_sol_networking_tools_and_exact_usd_ledger_without_touching_allowances(self):
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(2)))
            server.settings=replace(server.settings,hermes_model='gpt-6.1-sol');server.hermes.settings=server.settings
            backend.models.append({'id':'gpt-6.1-sol','root':'gpt-6.1-sol'})
            server.agent_tools=AgentTools(server);counts={}
            def reply(payload):
                self.assertEqual(payload['model'],'gpt-6.1-sol');context=json.loads(payload['messages'][-1]['content']);owner=context['member_id'];counts[owner]=counts.get(owner,0)+1
                action={'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]}
                if counts[owner]==1:action['tool_calls']=[{'name':'python_run','arguments':{'code':'result=6*7'}}]
                else:
                    self.assertEqual(context['tool_results'][0]['result']['data']['result'],42);action['budget_choice']='end'
                return json.dumps(action)
            backend.reply_factory=reply
            server.sandbox.start(server.sandbox.owner,{'npc_enabled':False});settle(server.event)
            self.assertEqual(server.event.state['status'],'completed');self.assertEqual(len(backend.records),4)
            accounts=server.sandbox.accounts.view(server.sandbox.owner);self.assertEqual(accounts['rates']['output_per_million'],10)
            for row in accounts['agents']:
                self.assertEqual(row['wallet']['limit_usd'],10);self.assertEqual(row['wallet']['reserve_usd'],1.90)
                self.assertEqual(row['wallet']['total_tokens'],2200);self.assertEqual(row['wallet']['spent_usd'],.006)
                self.assertEqual(row['wallet']['held_usd'],0)
            self.assertEqual(len(server.agent_tools.history()),2)


if __name__=='__main__':unittest.main()
