import json
import unittest
from unittest.mock import patch

from residency.npc import Facilitator
from tests.test_cohort import fixture, apply, export, import_payload, settle


class EventRecoveryTests(unittest.TestCase):
    def test_large_directory_retains_recent_conversation_and_private_values_stay_private(self):
        with fixture() as (server, client, backend, memory):
            apply(server, client, import_payload(export(2)))
            event = server.event; a, b = event.personas
            server.bounded_context = True
            event.state['event_id'] = 'large-directory-context'
            snapshot = server.store.snapshot(a)
            # A realistic large public directory, rather than a mock of the
            # bounding implementation: the witness's messages must survive it.
            for i in range(19):
                member = 'extra-' + str(i)
                event.personas[member] = {'name': member,
                    **{k: '界'*2000 for k in ('cv','cv_notes','skills','interests','subject_expertise',
                        'products_built','personal_offer','personal_seeking','skills_offer_people',
                        'skills_need_people','environment_offer','environment_need','reciprocity','introduction')},
                    'political_standing': 'NEVER-SHARE-THIS'}
                snapshot['members'].append({'id': member, 'name': member})
            snapshot['conversation_messages'] = [{'id': str(i), 'conversation_id': 'visible-room',
                'sender_id': a if i % 2 else b, 'body': f'Conversation detail {i}: '+('é'*450)} for i in range(20)]
            event.rooms.add('visible-room'); event.board_seen.add(a)
            with patch.object(server.store, 'snapshot', return_value=snapshot):
                context = event.context(a)
            self.assertEqual(context['total_witnessed_event_messages'], 20)
            self.assertGreaterEqual(len(context['recent_messages']), 4)
            self.assertEqual(context['recent_messages'][-1]['id'], '19')
            self.assertEqual(context['coverage']['history_included'], len(context['recent_messages']))
            self.assertLessEqual(len(json.dumps(context, ensure_ascii=False).encode()), 110000)
            self.assertNotIn('NEVER-SHARE-THIS', json.dumps(context))
            self.assertEqual(backend.records, [])

    def test_explicit_resume_recovers_failed_event_without_resetting_history(self):
        with fixture() as (server, client, backend, memory):
            apply(server, client, import_payload(export(2)))
            event = server.event; a, b = event.personas
            room = server.store.conversation_action(a, {'start_conversations': [{'with': b, 'body': 'Earlier conversation'}]})
            event.rooms.update(room['created_conversations'])
            event.state.update(status='failed', event_id='recover-same-event', calls=7, completed_calls=6,
                message_count=1, max_calls=None, error='Facilitator failed', starting_identities=event.personas)
            event._save()
            backend.reply = json.dumps({'wait_seconds': 0, 'start_conversations': [], 'join_conversations': [],
                'messages': [], 'leave_conversations': [], 'budget_choice': 'end'})
            event.resume(server.sandbox.owner); settle(event)
            self.assertEqual(event.state['event_id'], 'recover-same-event')
            self.assertGreater(event.state['completed_calls'], 6)
            self.assertEqual(event.state['message_count'], 1)
            self.assertIn(room['created_conversations'][0], event.rooms)
            self.assertIsNone(event.state['error'])

    def test_facilitator_failure_isolated_for_live_resilient_events(self):
        with fixture() as (server, client, backend, memory):
            apply(server, client, import_payload(export(2)))
            event = server.event; server.resilient_events = True
            event.state.update(status='running', event_id='npc-failure')
            with patch.object(event.npc, 'run', side_effect=RuntimeError('Synthetic NPC failure')):
                event._npc_worker()
            self.assertEqual(event.state['status'], 'running')
            self.assertFalse(event.stop_flag.is_set())
            self.assertFalse(event.npc.enabled)
            self.assertIn(event.npc.member_id, event.state['agent_errors'])
            path = event.directory/'facilitator-error.log'
            self.assertIn('Synthetic NPC failure', path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(backend.records, [])

    def test_facilitator_can_rotate_after_more_than_three_invitations_and_restores_cap(self):
        with fixture() as (server, client, backend, memory):
            apply(server, client, import_payload(export(2)))
            event = server.event; a, b = event.personas; npc = event.npc
            for i in range(5):
                result = server.store.conversation_action(a, {'start_conversations': [{'with': npc.member_id, 'body': 'Invitation '+str(i)}]})
                room = result['created_conversations'][0]; event.rooms.add(room)
                server.store.conversation_action(b, {'join_conversations': [room]})
            npc.step()
            joined = [r for r in server.store.conversation_state(npc.member_id)['conversations'] if r['joined']]
            self.assertEqual(len(joined), 1)
            event.state['npc_questions'] = [{'conversation_id': joined[0]['id'], 'at': i} for i in range(6)]
            restored = Facilitator(event, npc.member_id)
            self.assertEqual(len(restored.questions), 6)
            self.assertEqual(restored.last_question[joined[0]['id']], 5)
            self.assertEqual(backend.records, [])
