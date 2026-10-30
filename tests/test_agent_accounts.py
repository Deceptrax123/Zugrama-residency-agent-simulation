import json
import threading
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from residency.budgets import AgentAccounts, dollars
from residency.gateway_guard import bound_native
from residency.store import AppError
from tests import test_identity_sandbox as fixtures
from tests.test_host_event import silent


class AgentAccountTests(unittest.TestCase):
    setUp=fixtures.IdentitySandboxTests.setUp
    prepare=fixtures.IdentitySandboxTests.prepare
    settle=fixtures.IdentitySandboxTests.settle

    def configure(self,owner,limit='10',reserve='1.90'):
        return self.sandbox.accounts.configure(self.host,{'owner_id':owner,'limit_usd':limit,'reserve_usd':reserve})

    def ready(self):
        event,people=self.prepare()
        self.server.sandbox=self.sandbox
        self.server.hermes=SimpleNamespace(check=lambda:None,request=lambda *args,**kwargs:{'residency_budget_guard':'residency-usd-v1'})
        return event,people,self.sandbox.accounts

    def test_money_validation_and_exact_microusd_ledger(self):
        event,(a,b,c),accounts=self.ready()
        for bad in ('NaN','Infinity','-1','0.001',True,None,10001):
            with self.assertRaises(AppError):dollars(bad)
        self.configure(a)
        entry=accounts.reserve(a,'test',1,[])
        self.assertEqual(accounts.wallet(a)['held_usd'],1900000)
        accounts.settle(entry,{'usage':{'prompt_tokens':1000,'completion_tokens':250,'total_tokens':1250}})
        accounts.settle(entry,{'usage':{'prompt_tokens':1000,'completion_tokens':250,'total_tokens':1250}})
        wallet=accounts.wallet(a)
        self.assertEqual(wallet['spent_usd'],5000)
        self.assertEqual(wallet['held_usd'],0)
        self.assertEqual(wallet['total_tokens'],1250)
        self.assertEqual(accounts.view(self.host)['agents'][0]['wallet']['spent_usd'],.005)
        self.assertIsNone(accounts.view(self.host)['actual_provider_charge'])

    def test_reservation_concurrency_unknown_usage_and_restart(self):
        _,(a,b,c),accounts=self.ready();self.configure(a,'2','0')
        entries=[]
        threads=[threading.Thread(target=lambda:entries.append(accounts.reserve(a,'test',1,[]))) for _ in range(3)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(sum(isinstance(e,dict) for e in entries),1)
        entry=next(e for e in entries if isinstance(e,dict))
        accounts.settle(entry,{'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':1}})
        self.assertEqual(accounts.wallet(a)['held_usd'],1900000)
        restored=AgentAccounts(self.server)
        self.assertEqual(restored.wallet(a)['held_usd'],1900000)
        self.assertEqual(restored.wallet(a)['state'],'paused')
        with self.assertRaises(AppError):self.configure(a,'1','0')

    def test_guard_not_present_never_reserves_or_dispatches(self):
        _,(a,b,c),accounts=self.ready();self.configure(a)
        self.server.hermes.request=lambda *args,**kwargs:{}
        with self.assertRaises(AppError):accounts.reserve(a,'test',1,[])
        self.assertEqual(accounts.wallet(a)['held_usd'],0)

    def test_native_guard_rejects_unbounded_inputs_tools_hidden_context_and_rates(self):
        base={'model':'gpt-5.6-terra','input':[{'role':'user','content':'Hi'}]}
        self.assertEqual(bound_native(base),base)
        for bad in ({**base,'input':'x'*131073},{**base,'tools':[{}]}, {**base,'previous_response_id':'hidden'}, {**base,'service_tier':'priority'}, {**base,'model':'other'}):
            with self.assertRaises(RuntimeError):bound_native(bad)

    def test_final_wrapup_decision_and_peers_continue(self):
        event,(a,b,c),accounts=self.ready()
        self.configure(a,'2','1.90')
        self.configure(b,'0','0');self.configure(c,'0','0')
        seen=[]
        def decision(member,call,context):
            seen.append((member,context['budget']['phase']))
            accounts.settle(event.account_entries[call],{'usage':{'prompt_tokens':100,'completion_tokens':100,'total_tokens':200}})
            return {**silent(),'start_conversations':[{'with':b,'body':'I am wrapping up. Thank you.'}],'budget_choice':'end'}
        with patch.object(event,'_decision',side_effect=decision):
            event.start(self.host,{'max_calls':10,'npc_enabled':False});self.settle(event)
        self.assertEqual(seen,[(a,'wrap_up')])
        self.assertEqual(accounts.wallet(a)['state'],'ended')
        ledger=accounts.view(self.host)['agents'][0]['usage'][0]
        self.assertEqual(ledger['purpose'],'wrap_up')
        self.assertEqual(len(ledger['links']),1)
        self.assertEqual(event.state['completed_calls'],1)
        self.assertNotEqual(event.state['status'],'failed')

    def test_private_requests_are_only_in_own_context_and_not_auto_sent(self):
        event,(a,b,c),accounts=self.ready()
        accounts.message(self.host,{'owner_id':a,'target_id':b,'body':'PRIVATE HUMAN REQUIREMENT Ask about a music prototype'})
        self.assertEqual(self.server.event.threads,[])
        self.assertIn('PRIVATE HUMAN REQUIREMENT',json.dumps(event.context(a)))
        self.assertNotIn('PRIVATE HUMAN REQUIREMENT',json.dumps(event.context(b)))
        request=accounts.requests(a)[0]
        update={'id':request['id'],'status':'declined','response':'I would prefer to explore another topic.'}
        accounts.updates(a,[update]);accounts.apply_updates(a,[update])
        self.assertEqual(accounts.requests(a),[])
        with self.assertRaises(AppError):accounts.updates(b,[update])
        for payload in ({'owner_id':a,'target_id':a,'body':'test'},{'owner_id':'outside','target_id':b,'body':'test'}):
            with self.assertRaises(AppError):accounts.message(self.host,payload)
        with self.assertRaises(AppError):accounts.message(b,{'owner_id':a,'target_id':b,'body':'test'})
        with self.assertRaises(AppError):accounts.view(a)
