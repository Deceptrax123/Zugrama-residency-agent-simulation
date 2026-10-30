import json,threading,time,unittest
from residency.turn_queue import TurnQueue
from tests.test_cohort import fixture,apply,export,import_payload,settle
from residency.agent_tools import AgentTools

def until(predicate):
    end=time.monotonic()+3
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.005)
    raise AssertionError('Queue did not reach the expected state')

class TurnQueueTests(unittest.TestCase):
    def test_holders_cannot_barge_ahead_of_existing_waiters(self):
        gate=TurnQueue(1);cancel=threading.Event();order=[]
        self.assertTrue(gate.acquire(cancel=cancel,key='busy'))
        def enter(key):
            if gate.acquire(cancel=cancel,key=key):order.append(key);gate.release()
        threads=[]
        for i in range(8):
            t=threading.Thread(target=enter,args=(str(i),));t.start();threads.append(t)
            until(lambda:len(gate.snapshot()['waiting'])==i+1)
        gate.release()
        # The releasing worker immediately tries again, as a synchronous tool
        # completion can wake its owner without waiting for the chosen delay.
        self.assertTrue(gate.acquire(cancel=cancel,key='busy'));order.append('busy');gate.release()
        for t in threads:t.join(3);self.assertFalse(t.is_alive())
        self.assertEqual(order,[str(i) for i in range(8)]+['busy']);self.assertEqual(gate.snapshot()['active'],0)

    def test_cancelled_head_releases_its_place_and_parallelism_stays_bounded(self):
        gate=TurnQueue(2);stop=threading.Event();head_cancel=threading.Event();results=[]
        gate.acquire(cancel=stop,key='one');gate.acquire(cancel=stop,key='two')
        head=threading.Thread(target=lambda:results.append(('cancelled',gate.acquire(cancel=head_cancel,key='head'))));head.start();until(lambda:gate.snapshot()['waiting']==['head'])
        def follower():
            self.assertTrue(gate.acquire(cancel=stop,key='follower'));results.append(('follower',True));self.assertLessEqual(gate.snapshot()['active'],2);gate.release()
        tail=threading.Thread(target=follower);tail.start();until(lambda:gate.snapshot()['waiting']==['head','follower']);head_cancel.set();head.join(2);self.assertFalse(head.is_alive());gate.release();tail.join(2);self.assertFalse(tail.is_alive());gate.release()
        self.assertIn(('cancelled',False),results);self.assertIn(('follower',True),results);self.assertEqual(gate.snapshot()['waiting'],[])
        with self.assertRaises(RuntimeError):gate.release()

    def test_real_network_workers_with_hot_tools_all_get_admitted(self):
        with fixture(limit=21) as (server,client,backend,memory):
            apply(server,client,import_payload(export(21)));server.agent_tools=AgentTools(server,code=lambda code:{'ok':True,'result':42});entered=threading.Event();release=threading.Event();owners=[];lock=threading.Lock();capacity=server.event.gate.capacity
            def reply(payload):
                owner=json.loads(payload['messages'][-1]['content'])['member_id']
                with lock:owners.append(owner);n=len(owners)
                if n<=capacity:entered.set();release.wait(10)
                return json.dumps({'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[],'tool_calls':[{'name':'python_run','arguments':{'code':'result=42'}}]})
            # With three concurrent slots, request arrival can reorder after
            # admission while context is assembled. Observe the actual queue
            # handoff under its condition, rather than HTTP arrival order.
            admitted=[];acquire=server.event.gate.acquire
            def record_admission(**kwargs):
                with server.event.gate.condition:
                    granted=acquire(**kwargs)
                    if granted:admitted.append(kwargs['key'])
                    return granted
            server.event.gate.acquire=record_admission
            backend.reply_factory=reply
            try:
                server.sandbox.start(server.sandbox.owner,{'max_calls':42,'npc_enabled':False});self.assertTrue(entered.wait(3));until(lambda:len(server.event.gate.snapshot()['waiting'])==21-capacity)
            finally:release.set()
            settle(server.event);self.assertEqual(server.event.state['status'],'completed');self.assertEqual(len(owners),42)
            self.assertEqual(len(set(admitted[:21])),21);self.assertEqual(len(set(owners)),21);self.assertEqual(server.event.gate.snapshot()['waiting'],[]);self.assertEqual(server.event.gate.snapshot()['active'],0)
            self.assertEqual(server.event.state['completed_calls'],42);self.assertIsNone(server.event.state.get('agent_errors'))
