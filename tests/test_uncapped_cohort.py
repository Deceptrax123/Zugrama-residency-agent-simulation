import json
from collections import Counter
import unittest

from tests.test_cohort import fixture,apply,export,import_payload,settle


class UncappedCohortTests(unittest.TestCase):
    def test_agents_can_exceed_sixty_calls_and_end_voluntarily_then_advance_day(self):
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(2)));counts=Counter()
            def reply(payload):
                member=json.loads(payload['messages'][-1]['content'])['member_id'];counts[member]+=1
                return json.dumps({'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[],
                    'budget_choice':'end' if counts[member]>=31 else 'continue'})
            backend.reply_factory=reply
            code,result,_=client.request('/api/event/start','POST',{'seven_days':True,'npc_enabled':False})
            self.assertEqual(code,200,result);settle(server.event)
            self.assertIsNone(server.event.state['max_calls']);self.assertEqual(server.event.state['completed_calls'],62)
            self.assertEqual(server.event.state['status'],'completed');self.assertTrue(all(server.sandbox.accounts.wallet(p)['ended'] for p in server.event.personas))
            server.cycle.before_sleep(server.sandbox.owner);server.cycle.thread.join(10)
            self.assertEqual(server.cycle.state['phase'],'sleeping')
            for owner in server.event.personas:server.sandbox.accounts.configure(server.sandbox.owner,{'owner_id':owner,'limit_usd':'10.00','reserve_usd':'1.90'})
            server.cycle.next_day(server.sandbox.owner);settle(server.event)
            self.assertEqual(server.cycle.state['day'],2);self.assertIsNone(server.event.state['max_calls'])
            self.assertEqual(server.event.state['completed_calls'],64);self.assertEqual(len(backend.records),64)

    def test_host_can_stop_uncapped_networking_with_a_pending_reply(self):
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(2)));backend.block=True
            backend.reply_factory=lambda payload:json.dumps({'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]})
            try:
                code,result,_=client.request('/api/event/start','POST',{'max_calls':None,'seven_days':False,'npc_enabled':False})
                self.assertEqual(code,200,result);self.assertTrue(backend.entered.wait(5))
                server.event.stop(server.sandbox.owner)
            finally:backend.release.set()
            settle(server.event);self.assertEqual(server.event.state['status'],'stopped');self.assertIsNone(server.event.state['max_calls'])
            self.assertLessEqual(len(backend.records),2)

    def test_uncapped_agents_still_pause_when_their_allowance_cannot_fund_a_call(self):
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(2)))
            for owner in server.event.personas:server.sandbox.accounts.configure(server.sandbox.owner,{'owner_id':owner,'limit_usd':'0.00','reserve_usd':'0.00'})
            server.sandbox.start(server.sandbox.owner,{'npc_enabled':False,'seven_days':False});settle(server.event)
            self.assertIsNone(server.event.state['max_calls']);self.assertEqual(server.event.state['status'],'completed')
            self.assertEqual(backend.records,[])


if __name__=='__main__':unittest.main()
