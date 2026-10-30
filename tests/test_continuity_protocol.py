import json
import unittest
from unittest.mock import patch

from residency.agent_tools import AgentTools
from tests.test_cohort import fixture, apply, export, import_payload, settle


class ContinuityProtocolTests(unittest.TestCase):
    def test_old_unanswered_witnessed_thread_is_in_context(self):
        with fixture() as (server, client, backend, memory):
            apply(server, client, import_payload(export(2)))
            server.continue_existing_rooms=True; server.bounded_context=True
            event=server.event; a,b=event.personas
            event.state['event_id']='thread-context'; event.board_seen.add(a)
            room=server.store.conversation_action(a, {'start_conversations':[{'with':b,'body':'Which test should we write?'}]})['created_conversations'][0]
            event.rooms.add(room)
            answer=server.store.conversation_action(b, {'messages':[{'conversation_id':room,'body':'Let us test the soil-water sensor calibration.'}]})['messages'][0]
            # Newer one-sided openings must not displace this unanswered thread.
            for i in range(15):
                new=server.store.conversation_action(a, {'start_conversations':[{'with':b,'body':'Later opening '+str(i)}]})
                event.rooms.update(new['created_conversations'])
            context=event.context(a)
            self.assertEqual(context['conversation_threads'][0]['conversation_id'], room)
            self.assertTrue(context['conversation_threads'][0]['latest_from_peer'])
            self.assertIn(answer['id'],json.dumps(context['conversation_threads']))
            self.assertIn(room,context['action_options']['joined_conversation_ids'])
            self.assertEqual(backend.records, [])

    def test_synthetic_agents_continue_one_room_and_create_real_shared_artifact(self):
        with fixture() as (server, client, backend, memory):
            apply(server, client, import_payload(export(2)))
            server.continue_existing_rooms=True; server.bounded_context=True
            server.agent_tools=AgentTools(server,code=lambda code:{'ok':True,'stdout':'2\n','result':2})
            captured=[]
            def reply(payload):
                captured.append(payload);context=json.loads(payload['messages'][-1]['content'])
                action={'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]}
                joined=context['action_options']['joined_conversation_ids']
                if joined:
                    room=joined[0]
                    action['messages']=[{'conversation_id':room,'body':'Here is a concrete draft; please challenge the assumptions.'}]
                    action['tool_calls']=[{'name':'board_add','arguments':{'conversation_id':room,'title':'Shared calculation draft','text':'def add(a, b): return a + b'}},
                                          {'name':'python_run','arguments':{'code':'result = 1 + 1; print(result)'}}]
                else:
                    peer=next(p for p in context['action_options']['peer_ids'] if p!=server.event.npc.member_id)
                    action['start_conversations']=[{'with':peer,'body':'What small calculation could we test together?'}]
                return json.dumps(action)
            backend.reply_factory=reply
            server.sandbox.start(server.sandbox.owner,{'max_calls':6,'seven_days':False,'npc_enabled':False});settle(server.event)
            self.assertEqual(server.event.state['protocol'],'conversation-continuity-v2')
            self.assertEqual(len(server.event.rooms),1)
            self.assertTrue(any('conversation_threads' in json.loads(p['messages'][-1]['content']) for p in captured))
            self.assertTrue(all('develop earlier ideas' in p['messages'][0]['content'] for p in captured))
            self.assertTrue(server.agent_tools.boards())
            self.assertTrue(any(r['name']=='python_run' and r['status']=='completed' for r in server.agent_tools.history()))
