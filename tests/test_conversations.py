"""Local authorization and memory checks; no experiment or model invocation."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import unittest
from unittest.mock import patch

from residency.config import APP_ROOT
from residency.memory import AUTOMATIC_BATCH_KINDS, ConversationMemory, local_extract
from residency.store import AppError, Store
from tests.support import account, settings


class ConversationTests(unittest.TestCase):
    def setUp(self):
        (APP_ROOT / '.data').mkdir(exist_ok=True)
        context = settings()
        self.config = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.store = Store(self.config)
        self.people = []
        for name in ('Ada', 'Bob', 'Cara', 'Dan'):
            token, _ = self.store.register(account(name.lower() + '@example.test', name))
            self.people.append(self.store.authenticate(token)['member_id'])
        self.ada, self.bob, self.cara, self.dan = self.people
        self.memory = ConversationMemory(self.store)

    def start(self, body='A private opening before anyone else joins.'):
        result = self.store.conversation_action(self.ada, {'start_conversations':[{'with':self.bob, 'body':body}]})
        return result['created_conversations'][0]

    def send(self, room, body, actor=None):
        return self.store.conversation_action(actor or self.ada, {'messages':[{'conversation_id':room,'body':body}]})

    def test_event_continuation_reuses_direct_room_and_keeps_followup_visible(self):
        room = self.start('First question')
        result = self.store.conversation_action(self.bob, {'start_conversations':[
            {'with':self.ada,'body':'Answer to the first question'},
            {'with':self.ada,'body':'A concrete next step'}]}, reuse_direct_rooms={room})
        self.assertEqual(result['created_conversations'], [])
        self.assertEqual([m['conversation_id'] for m in result['messages']], [room,room])
        self.assertEqual([m['body'] for m in self.store.conversation_state(self.ada)['conversation_messages']],
                         ['First question','Answer to the first question','A concrete next step'])
        self.assertEqual(self.store.conversation_state(self.cara)['conversation_messages'], [])

    def test_continuation_never_uses_previous_event_group_or_leave_gap(self):
        old_room = self.start('Previous event private text')
        result = self.store.conversation_action(self.ada, {'start_conversations':[{'with':self.bob,'body':'New event'}]}, reuse_direct_rooms=set())
        room = result['created_conversations'][0]; self.assertNotEqual(room, old_room)
        self.store.conversation_action(self.cara, {'join_conversations':[room]})
        result = self.store.conversation_action(self.ada, {'start_conversations':[{'with':self.bob,'body':'Private, not for Cara'}]}, reuse_direct_rooms={room})
        direct = result['created_conversations'][0]; self.assertNotEqual(direct, room)
        self.assertNotIn('Private, not for Cara', json.dumps(self.store.conversation_state(self.cara)))
        self.store.conversation_action(self.bob, {'leave_conversations':[direct]})
        result = self.store.conversation_action(self.ada, {'start_conversations':[{'with':self.bob,'body':'Fresh contact after leaving'}]}, reuse_direct_rooms={direct})
        self.assertNotEqual(result['created_conversations'][0], direct)

    def test_duplicate_starts_within_one_action_create_one_room(self):
        result = self.store.conversation_action(self.ada, {'start_conversations':[
            {'with':self.bob,'body':'First thought'}, {'with':self.bob,'body':'Second thought'}]}, reuse_direct_rooms=set())
        self.assertEqual(len(result['created_conversations']), 1)
        self.assertEqual(len({m['conversation_id'] for m in result['messages']}), 1)

    def test_introductions_are_public_and_cannot_be_replaced(self):
        intro = self.store.introduce(self.ada, {'body':'I enjoy music and mathematical ideas.'})
        for person in self.people:
            self.assertEqual(self.store.snapshot(person)['introductions'][0]['id'], intro['id'])
            self.memory.capture_conversations(person)
            self.assertIn('music', json.dumps(self.memory.units(person)))
        with self.assertRaises(AppError) as error:
            self.store.introduce(self.ada, {'body':'A replacement.'})
        self.assertEqual(error.exception.status, 409)

    def test_public_presence_never_contains_message_text(self):
        room = self.start('PRIVATE-OPENING-714 not visible to Cara.')
        state = self.store.conversation_state(self.cara)
        self.assertEqual(state['conversations'][0]['id'], room)
        self.assertEqual(set(state['conversations'][0]['participants']), {self.ada, self.bob})
        self.assertEqual(state['conversation_messages'], [])
        self.assertNotIn('PRIVATE-OPENING-714', json.dumps(self.store.snapshot(self.cara)))
        self.assertNotIn('PRIVATE-OPENING-714', json.dumps(self.memory.sources(self.cara)))
        with self.assertRaises(AppError):
            self.send(room, 'Trying to write without joining.', self.cara)

    def test_join_has_no_history_backfill_even_with_identical_timestamps(self):
        with patch('residency.store.time.time', return_value=12345):
            room = self.start('OLD-PRIVATE-325 before joining.')
            self.store.conversation_action(self.cara, {'join_conversations':[room]})
            self.send(room, 'NEW-VISIBLE-326 after joining.')
        history = self.store.conversation_state(self.cara)['conversation_messages']
        self.assertEqual([m['body'] for m in history], ['NEW-VISIBLE-326 after joining.'])
        self.assertEqual(len(self.store.conversation_state(self.bob)['conversation_messages']), 2)
        self.assertEqual(self.store.conversation_state(self.dan)['conversation_messages'], [])

    def test_leave_and_rejoin_preserve_witnessed_messages_but_hide_the_gap(self):
        room = self.start()
        self.store.conversation_action(self.cara, {'join_conversations':[room]})
        self.send(room, 'First witnessed statement about a music prototype.')
        self.store.conversation_action(self.cara, {'leave_conversations':[room]})
        self.send(room, 'GAP-PRIVATE-568 never witnessed by Cara.')
        with self.assertRaises(AppError):
            self.send(room, 'Cannot speak while outside.', self.cara)
        self.store.conversation_action(self.cara, {'join_conversations':[room]})
        self.send(room, 'Second witnessed statement about a music prototype.')
        bodies = [m['body'] for m in self.store.conversation_state(self.cara)['conversation_messages']]
        self.assertEqual(len(bodies), 2)
        self.assertTrue(all('witnessed statement' in body for body in bodies))
        self.memory.capture_conversations(self.cara)
        self.assertNotIn('GAP-PRIVATE-568', json.dumps(self.memory.view(self.cara)))

    def test_joining_twice_does_not_reset_the_witnessed_window(self):
        room = self.start()
        self.store.conversation_action(self.cara, {'join_conversations':[room]})
        self.send(room, 'Keep this witnessed statement about music.')
        self.store.conversation_action(self.cara, {'join_conversations':[room]})
        self.assertEqual(len(self.store.conversation_state(self.cara)['conversation_messages']), 1)

    def test_a_later_invalid_action_rolls_back_earlier_messages_and_room_creation(self):
        with self.assertRaises(AppError):
            self.store.conversation_action(self.ada, {
                'start_conversations':[{'with':self.bob,'body':'Should be rolled back.'}],
                'messages':[{'conversation_id':'missing-room','body':'Invalid message.'}]})
        self.assertEqual(self.store.conversation_state(self.ada)['conversations'], [])
        self.assertEqual(self.store.conversation_state(self.bob)['conversation_messages'], [])

    def test_two_hop_memories_cite_only_accessible_relay_evidence(self):
        room = self.start('ORIGINAL-PRIVATE-221 aquifer coordinates.')
        self.store.conversation_action(self.cara, {'join_conversations':[room]})
        result = self.send(room, 'Ada suggested a rainwater prototype for the village.', self.bob)
        self.memory.capture_conversations(self.cara)
        note = self.memory.units(self.cara)[0]
        self.assertEqual(note['kind'], 'relayed_claim')
        self.assertEqual(note['path'], [self.ada,self.bob,self.cara])
        self.assertEqual(note['evidence'][0]['source_key'], 'conversation:' + result['messages'][0]['id'] + ':0')
        self.assertNotIn('ORIGINAL-PRIVATE-221', json.dumps(self.memory.view(self.cara)))
        self.assertEqual(self.memory.units(self.dan), [])

    def test_automatic_local_capture_can_be_disabled_without_affecting_history(self):
        self.memory.set_policy(self.cara, {'capture_conversations':False, 'auto_extract':True, 'auto_after':1})
        room = self.start()
        self.store.conversation_action(self.cara, {'join_conversations':[room]})
        self.send(room, 'I enjoy collaborative music improvisation.')
        self.memory.capture_conversations(self.cara)
        self.assertEqual(self.memory.units(self.cara), [])
        self.assertEqual(len(self.store.conversation_state(self.cara)['conversation_messages']), 1)
        self.assertFalse(self.memory.should_process(self.cara))
        self.store.message(self.bob, {'recipient_id':self.cara,'body':'I enjoy programming small puzzles.'})
        self.assertTrue(self.memory.should_process(self.cara))
        self.memory.process(self.cara,local_extract,source_kinds=AUTOMATIC_BATCH_KINDS)
        notes = self.memory.units(self.cara)
        self.assertIn('small puzzles',json.dumps(notes))
        self.assertNotIn('music improvisation',json.dumps(notes))

    def test_concurrent_join_and_send_follow_the_committed_sequence_boundary(self):
        room = self.start()
        barrier = threading.Barrier(2)
        def join():
            barrier.wait()
            self.store.conversation_action(self.cara, {'join_conversations':[room]})
        def send():
            barrier.wait()
            return self.send(room, 'A racing music prototype statement.')
        with ThreadPoolExecutor(2) as pool:
            joining, sending = pool.submit(join), pool.submit(send)
            joining.result()
            seq = sending.result()['messages'][0]['seq']
        with self.store.db() as db:
            boundary = db.execute('SELECT joined_after_seq FROM conversation_visits WHERE member_id=?', (self.cara,)).fetchone()[0]
        visible = self.store.conversation_state(self.cara)['conversation_messages']
        self.assertEqual(bool(visible), seq > boundary)


if __name__ == '__main__':
    unittest.main()
