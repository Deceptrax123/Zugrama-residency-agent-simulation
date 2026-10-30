import json
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from residency.config import APP_ROOT
from residency.event import HostEvent, SYSTEM
from residency.memory import ConversationMemory
from residency.store import AppError, Store
from tests.support import account, settings


def silent():
    return {'wait_seconds':0,'start_conversations':[],'join_conversations':[],
            'messages':[],'leave_conversations':[]}


class HostEventTests(unittest.TestCase):
    def setUp(self):
        (APP_ROOT/'.data').mkdir(exist_ok=True)
        context=settings()
        self.config=context.__enter__()
        self.addCleanup(context.__exit__,None,None,None)
        self.store=Store(self.config)
        self.people=[]
        for name in ('Asha','Kabir','Mira'):
            token,_=self.store.register(account(name.lower()+'@example.test',name))
            member=self.store.authenticate(token)['member_id']
            self.people.append(member)
            self.store.introduce(member,{'body':f'I am {name}. I enjoy music and interesting ideas.'})
        self.memory=ConversationMemory(self.store)
        self.server=SimpleNamespace(store=self.store,settings=self.config,
            capture_conversations=lambda ids:[self.memory.capture_conversations(member) for member in ids])
        self.directory=self.config.data_dir/'host-event'
        self.event=HostEvent(self.server,self.people[0],{m:{'name':str(i),'bio':'Fictional persona'} for i,m in enumerate(self.people)},self.directory)
        self.addCleanup(self.event.close)

    def settled(self):
        for thread in self.event.threads: thread.join(3)
        self.assertFalse(any(t.is_alive() for t in self.event.threads))

    def test_idle_by_default_and_only_host_can_start_or_stop(self):
        with patch.object(self.event,'_decision') as model:
            self.assertEqual(self.event.status(self.people[0])['status'],'idle')
            self.assertEqual(self.event.status(self.people[0])['calls'],0)
            for method in (lambda:self.event.start(self.people[1],{}),lambda:self.event.stop(self.people[1])):
                with self.assertRaises(AppError) as error: method()
                self.assertEqual(error.exception.status,403)
            model.assert_not_called()

    def test_call_cap_is_global_across_independent_workers(self):
        with patch.object(self.event,'_decision',return_value=silent()) as model:
            self.event.start(self.people[0],{'max_calls':2})
            self.settled()
        status=self.event.status(self.people[0])
        self.assertEqual(model.call_count,2)
        self.assertEqual(status['calls'],2)
        self.assertEqual(status['completed_calls'],2)
        self.assertEqual(status['status'],'completed')

    def test_stop_discards_inflight_action_and_does_not_start_another_call(self):
        entered,release=threading.Event(),threading.Event()
        def blocked(member,call,context):
            entered.set(); release.wait(3)
            peer=next(p for p in self.people if p!=member)
            return {**silent(),'start_conversations':[{'with':peer,'body':'I enjoy a useful music prototype.'}]}
        with patch.object(self.event,'_decision',side_effect=blocked) as model:
            self.event.start(self.people[0],{'max_calls':1})
            self.assertTrue(entered.wait(2))
            with self.assertRaises(AppError): self.event.start(self.people[0],{'max_calls':1})
            self.event.stop(self.people[0]); release.set(); self.settled()
        self.assertEqual(model.call_count,1)
        self.assertEqual(self.store.snapshot(self.people[0])['conversation_messages'],[])
        self.assertEqual(self.event.status(self.people[0])['status'],'stopped')

    def test_intro_barrier_and_budget_validation(self):
        for value in (0,61,True):
            with self.assertRaises(AppError): self.event.start(self.people[0],{'max_calls':value})
        with self.store.db() as db:
            db.execute('DELETE FROM introductions WHERE member_id=?',(self.people[2],))
        with self.assertRaises(AppError) as error: self.event.start(self.people[0],{})
        self.assertEqual(error.exception.status,409)

    def test_context_excludes_old_manual_histories_and_other_peoples_private_rooms(self):
        first,second,third=self.people
        self.store.message(first,{'recipient_id':second,'body':'OLD-DM-992 private history.'})
        old=self.store.conversation_action(first,{'start_conversations':[{'with':second,'body':'OLD-ROOM-993 private history.'}]})
        fresh=self.store.conversation_action(first,{'start_conversations':[{'with':second,'body':'UNJOINED-994 current private statement.'}]})
        room=fresh['created_conversations'][0]
        self.event.rooms.add(room)
        self.assertNotIn('OLD-DM-992',json.dumps(self.event.context(first)))
        self.assertNotIn('OLD-ROOM-993',json.dumps(self.event.context(first)))
        self.assertNotIn('UNJOINED-994',json.dumps(self.event.context(third)))
        self.store.conversation_action(third,{'join_conversations':[room]})
        self.store.conversation_action(second,{'messages':[{'conversation_id':room,'body':'Asha suggested a music prototype.'}]})
        context=self.event.context(third)
        self.assertIn('music prototype',json.dumps(context))
        self.assertNotIn('UNJOINED-994',json.dumps(context))
        self.assertNotIn('private_memory',context)
        self.assertNotIn('feed',context)
        self.assertEqual(self.event.status(third)['feed'],[])
        self.assertTrue(self.event.status(first)['feed'])
        self.assertNotIn(old['created_conversations'][0],json.dumps(context))
        private=self.store.conversation_action(second,{'start_conversations':[
            {'with':third,'body':'OPERATOR-ONLY-995 not witnessed by Asha.'}]})
        self.event.rooms.add(private['created_conversations'][0])
        self.assertIn('OPERATOR-ONLY-995',json.dumps(self.event.status(first)['feed']))
        self.assertNotIn('OPERATOR-ONLY-995',json.dumps(self.event.context(first)))

    def test_event_messages_feed_local_memory(self):
        def opening(member,call,context):
            peer=next(p for p in self.people if p!=member)
            return {**silent(),'start_conversations':[{'with':peer,'body':'I enjoy collaborative music prototypes.'}]}
        with patch.object(self.event,'_decision',side_effect=opening):
            self.event.start(self.people[0],{'max_calls':1}); self.settled()
        self.assertEqual(self.event.status(self.people[0])['message_count'],1)
        with self.store.db() as db:
            sender=db.execute('SELECT sender_id FROM conversation_messages').fetchone()[0]
        self.assertIn('collaborative music',json.dumps(self.memory.units(sender)))

    def test_invalid_model_action_stops_without_retry(self):
        with patch.object(self.event,'_decision',return_value={'bad':'output'}) as model:
            self.event.start(self.people[0],{'max_calls':1}); self.settled()
        self.assertEqual(model.call_count,1)
        self.assertEqual(self.event.status(self.people[0])['status'],'failed')

    def test_restart_never_resumes_a_running_event(self):
        self.directory.mkdir(exist_ok=True)
        (self.directory/'state.json').write_text(json.dumps({'status':'running','calls':1,'conversation_ids':[]}))
        restored=HostEvent(self.server,self.people[0],self.event.personas,self.directory)
        self.assertEqual(restored.status(self.people[0])['status'],'interrupted')
        self.assertEqual(restored.threads,[])

    def test_topics_and_schedule_are_not_assigned(self):
        self.assertIn('Choose your own topics',SYSTEM)
        self.assertIn('no imposed speaking order',SYSTEM)
        self.assertIn('do not invent a morning/night schedule',SYSTEM)


if __name__=='__main__': unittest.main()
