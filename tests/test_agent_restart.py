import json
import time
import unittest
import uuid

from residency.store import AppError
from tests.test_cohort import fixture, apply, export, import_payload


def wait_for(predicate):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.02)
    raise AssertionError('Synthetic agent did not reach the expected state')


class AgentRestartTests(unittest.TestCase):
    def test_resume_after_stopping_with_an_isolated_agent_error_keeps_same_event(self):
        with fixture() as (server,client,backend,memory):
            from tests.test_cohort import settle
            apply(server,client,import_payload(export(2)))
            event=server.event
            event.state.update(status='completed_with_errors',event_id='same-after-reload',
                calls=3,completed_calls=2,message_count=0,max_calls=None,
                starting_identities=event.personas,agent_errors={next(iter(event.personas)):'Invalid partner'})
            backend.reply=json.dumps({'wait_seconds':0,'start_conversations':[],'join_conversations':[],
                'messages':[],'leave_conversations':[],'budget_choice':'end'})
            event.resume(server.sandbox.owner);settle(event)
            self.assertEqual(event.state['event_id'],'same-after-reload')
            self.assertGreater(event.state['completed_calls'],2)

    def prepare(self, server, client, backend):
        apply(server,client,import_payload(export(2)))
        event=server.event; a,b=event.personas; recovered=[]
        def reply(payload):
            ctx=json.loads(payload['messages'][-1]['content']);owner=ctx['member_id']
            action={'wait_seconds':3600,'start_conversations':[],'join_conversations':[], 'messages':[],'leave_conversations':[]}
            if owner==a:
                if not recovered:action['start_conversations']=[{'with':'invalid-member','body':'Invalid first action'}]
                else:
                    recovered.append(ctx)
                    joined=ctx['action_options']['joined_conversation_ids']
                    if joined:action['messages']=[{'conversation_id':joined[0],'body':'Recovered response, using the earlier conversation.'}]
            elif not ctx['action_options']['joined_conversation_ids']:
                action['start_conversations']=[{'with':a,'body':'An earlier question for the stopped agent.'}]
            return json.dumps(action)
        backend.reply_factory=reply
        server.sandbox.start(server.sandbox.owner,{'max_calls':None,'npc_enabled':False,'seven_days':False})
        wait_for(lambda:a in event.state.get('agent_errors',{}) and not event.member_threads[a].is_alive() and bool(event.rooms))
        return event,a,b,recovered

    def test_host_recovers_only_failed_agent_with_context_and_idempotency(self):
        with fixture() as (server,client,backend,memory):
            event,a,b,recovered=self.prepare(server,client,backend)
            event_id=event.state['event_id'];rooms=set(event.rooms);peer_thread=event.member_threads[b]
            peer_ledger=server.sandbox.accounts.wallet(b)
            recovered.append(True)
            payload={'event_id':event_id,'member_id':a,'request_id':str(uuid.uuid4()),'confirmed':True}
            code,result,_=client.request('/api/event/agent/restart','POST',payload)
            self.assertEqual(code,200,result);self.assertEqual(result['status'],'restarted')
            restarted_thread=event.member_threads[a]
            wait_for(lambda:any(m['sender_id']==a for m in server.store.conversation_state(a)['conversation_messages']))
            self.assertIs(event.member_threads[b],peer_thread);self.assertTrue(peer_thread.is_alive())
            self.assertTrue(restarted_thread.is_alive());self.assertFalse(event.stop_flag.is_set())
            self.assertEqual(event.state['status'],'running');self.assertEqual(event.state['event_id'],event_id)
            self.assertTrue(rooms<=event.rooms);self.assertNotIn(a,event.state.get('agent_errors',{}))
            self.assertTrue(any(isinstance(ctx,dict) and ctx['recent_messages'] for ctx in recovered))
            self.assertEqual(server.sandbox.accounts.wallet(b)['limit_usd'],peer_ledger['limit_usd'])
            code,result,_=client.request('/api/event/agent/restart','POST',payload)
            self.assertEqual(code,200,result);self.assertTrue(result['duplicate'])
            self.assertIs(event.member_threads[a],restarted_thread)
            self.assertEqual(len(event.state['agent_restarts']),1)

    def test_restart_requires_host_confirmation_current_event_and_available_allowance(self):
        with fixture() as (server,client,backend,memory):
            event,a,b,recovered=self.prepare(server,client,backend)
            payload={'event_id':event.state['event_id'],'member_id':a,'request_id':str(uuid.uuid4()),'confirmed':True}
            with self.assertRaises(AppError) as error:event.restart_agent(a,payload)
            self.assertEqual(error.exception.status,403)
            for bad in ({**payload,'confirmed':False},{**payload,'event_id':'old-event'},{**payload,'member_id':b}):
                with self.assertRaises(AppError):event.restart_agent(server.sandbox.owner,bad)
            code,result,_=client.request('/api/event/agent/restart','POST',payload,{'X-CSRF-Token':'wrong'})
            self.assertEqual(code,403)
            server.sandbox.accounts.configure(server.sandbox.owner,{'owner_id':a,'limit_usd':'1.00','reserve_usd':'0.00'})
            with self.assertRaises(AppError) as error:event.restart_agent(server.sandbox.owner,payload)
            self.assertEqual(error.exception.status,409)
            self.assertFalse(event.member_threads[a].is_alive())
            self.assertEqual(event.state['status'],'running');self.assertEqual(event.state.get('agent_restarts',[]),[])
