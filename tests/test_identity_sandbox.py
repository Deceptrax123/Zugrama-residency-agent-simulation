import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from residency.config import APP_ROOT
from residency.graph import communication_graph
from residency.identity import rows
from residency.memory import ConversationMemory
from residency.npc import agreement_score
from residency.sandbox import IdentitySandbox
from residency.store import AppError, Store
from tests.support import account, settings
from tests.test_host_event import silent


def persona(name='Agent One'):
    return {'name': name, 'introduction': f'I am {name}. I enjoy exploring useful ideas.',
            'nationality': 'Self-described nationality', 'region': 'Self-described region',
            'cv': 'Experience supplied by the human', 'skills': 'Python',
            'personal_offer': 'Listening and music', 'personal_seeking': 'Friendship',
            'skills_offer_people': 'Code review', 'skills_need_people': 'Design feedback',
            'environment_offer': 'Data analysis drafts', 'environment_need': 'Time and space',
            'moral_compass': 'PRIVATE-COMPASS-551 care and fairness',
            'political_standing': 'PRIVATE-POLITICS-552 explicitly supplied outlook'}


class IdentitySandboxTests(unittest.TestCase):
    def setUp(self):
        (APP_ROOT/'.data').mkdir(exist_ok=True)
        context = settings()
        self.config = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.store = Store(self.config)
        memory = ConversationMemory(self.store)
        self.server = SimpleNamespace(store=self.store, settings=self.config, event=None,
            capture_conversations=lambda ids: [memory.capture_conversations(m) for m in ids])
        self.sandbox = IdentitySandbox(self.server)
        token, _ = self.sandbox.signup(account('host@example.test', 'Human host'))
        self.host = self.store.authenticate(token)['member_id']
        self.addCleanup(lambda: self.server.event.close() if self.server.event else None)

    def prepare(self):
        for slot in (1, 2, 3): self.sandbox.save_agent(self.host, slot, persona(f'Agent {slot}'))
        return self.server.event, list(self.server.event.personas)

    def settle(self, event):
        for thread in event.threads: thread.join(3)
        self.assertFalse(any(thread.is_alive() for thread in event.threads))

    def test_host_signup_three_authored_agents_and_idle_startup(self):
        self.assertFalse(self.sandbox.status(self.host)['ready'])
        with self.assertRaises(AppError): self.sandbox.start(self.host, {})
        with self.assertRaises(AppError): self.sandbox.signup(account('another@example.test', 'Other'))
        event, people = self.prepare()
        self.assertNotIn(self.host, people)
        self.assertEqual(len(people), 3)
        self.assertEqual(event.state['status'], 'idle')
        self.assertEqual(event.threads, [])
        self.assertEqual(len(self.store.introductions()), 4)  # Three agents and disclosed NPC.

    def test_separate_offers_needs_and_private_values_in_own_context_only(self):
        event, people = self.prepare()
        context = event.context(people[0])
        self.assertIn('PRIVATE-COMPASS', json.dumps(context['persona']))
        self.assertNotIn('PRIVATE-COMPASS', json.dumps(context['directory']))
        self.assertNotIn('PRIVATE-POLITICS', json.dumps(self.store.snapshot(self.host)['members']))
        for key in ('personal_offer', 'personal_seeking', 'skills_offer_people', 'skills_need_people', 'environment_offer', 'environment_need'):
            self.assertTrue(context['persona'][key])
        self.sandbox.save_agent(self.host, 1, {**persona(), 'share_values': True})
        self.assertIn('PRIVATE-POLITICS', json.dumps(event.context(people[1])['directory']))

    def test_validation_authorization_and_revision_preservation(self):
        for slot in (0, 4, True):
            with self.assertRaises(AppError): self.sandbox.save_agent(self.host, slot, persona())
        with self.assertRaises(AppError): self.sandbox.save_agent('outsider', 1, persona())
        with self.assertRaises(AppError): self.sandbox.save_agent(self.host, 1, {**persona(), 'share_values': 'yes'})
        self.assertEqual(rows(self.store), [])
        self.sandbox.save_agent(self.host, 1, persona())
        member = rows(self.store)[0]['member_id']
        self.sandbox.save_agent(self.host, 1, {**persona(), 'name': 'Revised name'})
        self.assertEqual(rows(self.store)[0]['member_id'], member)
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM identity_revisions').fetchone()[0], 2)

    def test_start_baseline_immutable_and_no_edit_during_pending_call(self):
        import threading
        event, people = self.prepare()
        entered, release = threading.Event(), threading.Event()
        def blocked(*args):
            entered.set(); release.wait(3); return silent()
        with patch.object(event, '_decision', side_effect=blocked):
            self.sandbox.start(self.host, {'max_calls': 1, 'npc_enabled': False})
            self.assertTrue(entered.wait(2))
            with self.assertRaises(AppError): self.sandbox.save_agent(self.host, 1, persona('Changed'))
            event.stop(self.host); release.set(); self.settle(event)
        baseline = json.loads(json.dumps(event.state['starting_identities']))
        self.sandbox.save_agent(self.host, 1, persona('Changed'))
        self.assertEqual(event.state['starting_identities'], baseline)
        self.assertNotIn('starting_identities', event.status(people[0]))
        archive = event.directory/'events'/(event.state['event_id']+'.json')
        self.assertEqual(json.loads(archive.read_text())['starting_identities'], baseline)

    def test_graph_windows_use_actual_sequence_recipients_and_exclude_old_rooms(self):
        event, (a, b, c) = self.prepare()
        before = self.store.conversation_action(a, {'start_conversations': [{'with': b, 'body': 'OLD-MESSAGE'}]})
        result = self.store.conversation_action(a, {'start_conversations': [{'with': b, 'body': 'one'}]})
        room = result['created_conversations'][0]
        event.rooms.add(room)
        self.store.conversation_action(a, {'messages': [{'conversation_id': room, 'body': 'two'}]})
        self.store.conversation_action(c, {'join_conversations': [room]})
        self.store.conversation_action(c, {'messages': [{'conversation_id': room, 'body': 'three'}]})
        self.store.conversation_action(b, {'leave_conversations': [room]})
        self.store.conversation_action(a, {'messages': [{'conversation_id': room, 'body': 'four'}]})
        self.store.conversation_action(b, {'join_conversations': [room], 'messages': [{'conversation_id': room, 'body': 'five'}]})
        base = time.time()-20
        with self.store.db() as db:
            messages = db.execute('SELECT id FROM conversation_messages WHERE conversation_id=? ORDER BY seq', (room,)).fetchall()
            for i, row in enumerate(messages, 1): db.execute('UPDATE conversation_messages SET created_at=? WHERE id=?', (base+i, row['id']))
        event.state.update(event_id='graph-test', started_at=base, finished_at=base+5)
        graph = communication_graph(event, self.host, window=2, offset=3.5)
        counts = {(edge['source'], edge['target']): edge['count'] for edge in graph['edges']}
        self.assertEqual(counts, {(a, b): 1, (c, a): 1, (c, b): 1})
        graph = communication_graph(event, self.host, window=1, offset=4)
        self.assertEqual(graph['edges'], [{'source': a, 'target': c, 'count': 1}])
        self.assertNotIn('OLD-MESSAGE', json.dumps(graph))
        self.assertNotIn(before['created_conversations'][0], json.dumps(graph))
        with self.assertRaises(AppError): communication_graph(event, a)
        for value in ('nan', 'inf', -1, 0):
            with self.assertRaises(AppError): communication_graph(event, self.host, window=value)

    def test_npc_never_inspects_prejoin_agreement_then_intervenes_with_cooldown(self):
        event, (a, b, c) = self.prepare()
        result = self.store.conversation_action(a, {'start_conversations': [{'with': b, 'body': 'PREJOIN-SECRET I agree'}]})
        room = result['created_conversations'][0]
        event.rooms.add(room)
        for speaker in (b, a, b):
            self.store.conversation_action(speaker, {'messages': [{'conversation_id': room, 'body': 'I agree completely.'}]})
        now = time.time()
        event.npc.step(now)
        event.npc.step(now+1)
        self.assertEqual(event.npc.questions, [])
        self.assertNotIn('PREJOIN-SECRET', json.dumps(self.store.conversation_state(event.npc.member_id)))
        for speaker in (a, b, a, b):
            self.store.conversation_action(speaker, {'messages': [{'conversation_id': room, 'body': 'Absolutely, I agree.'}]})
        event.npc.step(now+2)
        self.assertEqual(event.npc.questions[0]['reason'], 'repeated_agreement')
        event.npc.step(now+3)
        self.assertEqual(len(event.npc.questions), 1)
        self.assertEqual(event.status(c)['npc']['questions'], [])
        self.assertNotIn('npc_questions', event.status(c))

    def test_npc_attention_rule_uses_only_witnessed_deliveries(self):
        event, (a, b, c) = self.prepare()
        result = self.store.conversation_action(a, {'start_conversations': [{'with': b, 'body': 'A starting idea.'}]})
        room = result['created_conversations'][0]
        event.rooms.add(room)
        now = time.time()
        event.npc.step(now)
        for _ in range(6):
            self.store.conversation_action(b, {'messages': [{'conversation_id': room, 'body': 'A question for you.'}]})
        event.npc.step(now+1)
        self.assertEqual(event.npc.questions[0]['reason'], 'attention_concentration')
        self.assertEqual(event.npc.questions[0]['attention_concentration'], 1)
        self.assertIn(event.personas[b]['name'], event.npc.questions[0]['body'])

    def test_agreement_heuristic_requires_multiple_speakers_and_excludes_qualified_agreement(self):
        msgs = [{'sender_id': str(i%2), 'body': 'I agree, but this assumption might fail.'} for i in range(4)]
        self.assertEqual(agreement_score(msgs), 0)
        self.assertEqual(agreement_score([{'sender_id': 'one', 'body': 'I agree'}]*4), 0)

    def test_compass_observation_requires_real_quote_and_does_not_change_identity(self):
        event, (a, b, c) = self.prepare()
        event.state.update(event_id='observation-test', starting_identities=json.loads(json.dumps(event.personas)))
        result = self.store.conversation_action(a, {'start_conversations': [{'with': b, 'body': 'I reconsider that view after your example.'}]})
        event.rooms.update(result['created_conversations'])
        payload = {'message_id': result['messages'][0]['id'], 'label': 'explicit_reconsideration',
                   'quote': 'I reconsider that view', 'note': 'Explicit language of change; scope is uncertain.'}
        before = rows(self.store)
        self.sandbox.observe_compass(self.host, payload)
        self.assertEqual(rows(self.store), before)
        self.assertEqual(len(self.sandbox.status(self.host)['compass_observations']), 1)
        for invalid in ({**payload, 'quote': 'fabricated evidence'}, {**payload, 'label': 'true belief changed'}):
            with self.assertRaises(AppError): self.sandbox.observe_compass(self.host, invalid)
        with self.assertRaises(AppError): self.sandbox.observe_compass(c, payload)
        self.assertNotIn('Explicit language of change', json.dumps(event.context(a)))


if __name__ == '__main__': unittest.main()
