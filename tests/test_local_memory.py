import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from residency.local_mem0 import AgentMem0, LocalMemoryClient
from residency.memory import ConversationMemory
from residency.sleep_cycle import SleepCycle, validate_reflection
from residency.store import AppError
from tests import test_identity_sandbox as fixtures
from tests.test_host_event import silent


class FakeMemory:
    def __init__(self):self.added=[];self.reflected=[];self.matches={}
    def add(self,scope,sources,priorities):
        self.added.append((scope,sources,priorities))
        self.matches.setdefault(scope,[]).append({'id':str(len(self.added)), 'memory':'An unverified useful idea',
            'metadata':{'source_keys':[source['key'] for source in sources]}})
        return {'results':self.matches[scope]}
    def search(self,scope,query):return {'results':self.matches.get(scope,[])}
    def list_notes(self,scope):return {'results':self.matches.get(scope,[])}
    def reflect(self,payload):
        self.reflected.append(payload)
        ids=[source['id'] for source in payload['sources'][:1]]
        return {'summary':'Private before-sleep reflection.',
            'takeaways':[{'text':'A useful idea was discussed.','source_ids':ids}] if ids else [],
            'view_changes':[],'unresolved_questions':[],'tomorrow_intentions':[]}


class LocalMemoryTests(unittest.TestCase):
    prepare=fixtures.IdentitySandboxTests.prepare
    settle=fixtures.IdentitySandboxTests.settle
    def setUp(self):
        fixtures.IdentitySandboxTests.setUp(self)
        self.server.memory=ConversationMemory(self.store)
        self.server.sandbox=self.sandbox
        self.server.semantic=None;self.server.cycle=None
        self.client=FakeMemory()

    def test_local_transport_refuses_cloud_endpoint(self):
        with self.assertRaises(ValueError):LocalMemoryClient({'url':'https://api.mem0.ai','key':'unused'})

    def test_mem0_scope_source_visibility_and_capture_preference(self):
        event,(a,b,c)=self.prepare()
        event.state['event_id']='memory-test'
        result=self.store.conversation_action(a,{'start_conversations':[{'with':b,'body':'PRIVATE-BEFORE-JOIN-991 useful idea.'}]})
        room=result['created_conversations'][0];event.rooms.add(room)
        memory=AgentMem0(self.server,self.client);self.server.semantic=memory
        self.addCleanup(memory.close)
        self.assertNotEqual(memory.scope(a),memory.scope(b))
        self.assertEqual(memory.sources(c),[])
        self.store.conversation_action(c,{'join_conversations':[room]})
        self.store.conversation_action(b,{'messages':[{'conversation_id':room,'body':'Asha suggested a music prototype.'}]})
        memory.enqueue([c]);memory.queue.join()
        self.assertEqual(len(self.client.added),1)
        self.assertNotIn('PRIVATE-BEFORE-JOIN',json.dumps(self.client.added))
        result=memory.search(self.host,c,'music')
        self.assertTrue(result['results'])
        self.assertNotIn('PRIVATE-BEFORE-JOIN',json.dumps(result))
        notes=memory.notes(self.host)
        self.assertTrue(next(item for item in notes['agents'] if item['owner_id']==c)['notes'])
        self.assertNotIn('PRIVATE-BEFORE-JOIN',json.dumps(notes))
        with self.assertRaises(AppError):memory.notes(a)
        with self.assertRaises(AppError):memory.search(a,c,'music')
        self.server.memory.set_policy(c,{'capture_conversations':False})
        self.store.conversation_action(b,{'messages':[{'conversation_id':room,'body':'Another useful new idea.'}]})
        memory.enqueue([c]);memory.queue.join()
        self.assertEqual(len(self.client.added),1)

    def test_seven_days_keep_event_identity_rooms_and_reflect_once_per_agent(self):
        event,people=self.prepare()
        cycle=SleepCycle(self.server,self.client);self.server.cycle=cycle
        self.addCleanup(cycle.close)
        def decision(member,call,context):
            joined=[room for room in context['conversations'] if room['joined']]
            if joined:
                return {**silent(),'messages':[{'conversation_id':joined[0]['id'],'body':'I enjoy exploring this useful idea.'}]}
            return {**silent(),'start_conversations':[{'with':next(p for p in people if p!=member),'body':'I enjoy music and useful ideas.'}]}
        with patch.object(event,'_decision',side_effect=decision):
            cycle.start(self.host,{'max_calls':3,'npc_enabled':False})
            event_id=event.state['event_id'];baseline=json.dumps(event.state['starting_identities'],sort_keys=True)
            for day in range(1,8):
                self.settle(event)
                self.assertEqual(cycle.state['day'],day)
                cycle.before_sleep(self.host);cycle.thread.join(5)
                self.assertFalse(cycle.thread.is_alive())
                self.assertEqual(cycle.state['phase'],'completed' if day==7 else 'sleeping')
                self.assertEqual(len(self.client.reflected),day*3)
                self.assertEqual(event.state['event_id'],event_id)
                self.assertEqual(json.dumps(event.state['starting_identities'],sort_keys=True),baseline)
                if day<7:cycle.next_day(self.host)
        view=cycle.view(self.host)
        self.assertEqual(len(view['reflections']),21)
        self.assertIsNone(view['wall_clock_scale'])
        self.assertEqual(event.state['calls'],21)
        self.assertNotIn('Private before-sleep',json.dumps(event.context(people[0])))
        with self.assertRaises(AppError):cycle.next_day(self.host)

    def test_reflection_rejects_forged_evidence_and_never_changes_identity(self):
        sources=[{'id':'witnessed-1','body':'A source'}]
        valid={'summary':'A private thought.','takeaways':[{'text':'One point.','source_ids':['witnessed-1']}],
               'view_changes':[],'unresolved_questions':[],'tomorrow_intentions':[]}
        self.assertEqual(validate_reflection(valid,sources),valid)
        valid['takeaways'][0]['source_ids']=['someone-elses-private-message']
        with self.assertRaises(AppError):validate_reflection(valid,sources)

    def test_sleep_rejects_repeat_nonhost_and_restart_never_resumes(self):
        event,people=self.prepare()
        cycle=SleepCycle(self.server,self.client);self.server.cycle=cycle
        self.addCleanup(cycle.close)
        with patch.object(event,'_decision',return_value=silent()):
            cycle.start(self.host,{'max_calls':1,'npc_enabled':False});self.settle(event)
        with self.assertRaises(AppError):cycle.before_sleep(people[0])
        cycle.before_sleep(self.host);cycle.thread.join(5)
        with self.assertRaises(AppError):cycle.before_sleep(self.host)
        cycle.state['phase']='reflecting';cycle._save()
        restored=SleepCycle(self.server,self.client)
        self.assertEqual(restored.state['phase'],'interrupted')
        self.assertIsNone(restored.thread)

    def test_restart_preserves_completed_day_waiting_for_manual_bedtime(self):
        event,people=self.prepare()
        cycle=SleepCycle(self.server,self.client);self.server.cycle=cycle
        self.addCleanup(cycle.close)
        with patch.object(event,'_decision',return_value=silent()):
            cycle.start(self.host,{'max_calls':1,'npc_enabled':False});self.settle(event)
        self.assertEqual(event.state['status'],'completed')
        restored=SleepCycle(self.server,self.client)
        self.assertEqual(restored.state['phase'],'awake')
        self.assertIsNone(restored.thread)
        self.assertEqual(event.state['calls'],1)


if __name__=='__main__':unittest.main()
