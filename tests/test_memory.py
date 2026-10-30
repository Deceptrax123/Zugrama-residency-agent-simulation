from concurrent.futures import ThreadPoolExecutor
import json
import threading
import unittest

from residency.config import APP_ROOT
from residency.memory import BATCH_CHARACTERS, BATCH_SOURCES, CATEGORIES, DEFAULT_FOCUS, ConversationMemory, default_policy, local_extract
from residency.store import AppError, Store
from tests.support import account, settings


class MemoryTests(unittest.TestCase):
    def setUp(self):
        (APP_ROOT / '.data').mkdir(exist_ok=True)
        context = settings()
        self.config = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        self.store = Store(self.config)
        self.people = {}
        for name in ('Ada', 'Bob', 'Cara', 'Dan'):
            token, _ = self.store.register(account(name.lower() + '@example.test', name))
            self.people[name] = self.store.authenticate(token)['member_id']
        self.ada, self.bob, self.cara, self.dan = (self.people[n] for n in ('Ada', 'Bob', 'Cara', 'Dan'))
        self.memory = ConversationMemory(self.store)

    def message(self, sender, recipient, body):
        return self.store.message(sender, {'recipient_id': recipient, 'body': body})

    def test_two_hop_claim_preserves_relay_and_never_reads_original_private_message(self):
        self.message(self.ada, self.bob, 'Unshared private aquifer coordinates are SECRET-112.')
        relay = self.message(self.bob, self.cara, 'Ada suggested a rainwater prototype for the village.')
        self.memory.process(self.cara, local_extract)
        notes = self.memory.units(self.cara)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]['kind'], 'relayed_claim')
        self.assertEqual(notes[0]['path'], [self.ada, self.bob, self.cara])
        self.assertEqual(notes[0]['evidence'][0]['source_key'], 'message:' + relay['id'] + ':0')
        self.assertNotIn('SECRET-112', json.dumps(self.memory.view(self.cara)))
        self.assertEqual(self.memory.units(self.dan), [])
        self.assertEqual(self.memory.recall(self.dan, 'rainwater'), [])
        self.assertEqual(self.memory.recall(self.cara, 'rainwater', peer_id=self.ada)[0]['path'][1], self.bob)

    def test_human_weights_topics_and_exclusions_control_selection_and_recall(self):
        self.message(self.bob, self.cara, 'I can help with rainwater collection. I enjoy jazz improvisation.')
        policy = self.memory.policy(self.cara)
        policy['weights']['interests'] = 0
        policy['topics'] = ['rainwater']
        policy['instructions'] = 'Prioritize rainwater collection'
        self.memory.set_policy(self.cara, policy)
        self.memory.process(self.cara, local_extract)
        notes = self.memory.units(self.cara)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]['category'], 'offers')
        self.assertGreater(notes[0]['importance'], .5)
        self.assertIn('topic matches', notes[0]['reason'])
        self.memory.set_policy(self.cara, {'exclude_terms': ['rainwater']})
        self.assertEqual(self.memory.recall(self.cara, 'collection'), [])

    def test_defaults_local_manual_and_priorities_are_isolated(self):
        self.assertFalse(self.memory.policy(self.ada)['auto_extract'])
        self.memory.set_policy(self.ada, {'instructions': 'Remember music interests'})
        self.assertEqual(self.memory.policy(self.bob)['instructions'], default_policy()['instructions'])
        self.assertFalse(self.memory.view(self.ada)['external_processing'])

    def test_chosen_focus_includes_stated_priorities_as_an_extractable_category(self):
        policy = self.memory.policy(self.cara)
        self.assertEqual({c for c, weight in policy['weights'].items() if weight == 2}, DEFAULT_FOCUS)
        self.message(self.bob, self.cara, 'My main priority is accessible music education.')
        self.memory.process(self.cara, local_extract)
        note = self.memory.units(self.cara)[0]
        self.assertEqual(note['category'], 'priorities')
        self.assertIn('accessible music education', note['summary'])

    def test_older_saved_policies_gain_new_category_without_losing_personal_choices(self):
        old = default_policy()
        old['weights'] = {c: 1 for c in CATEGORIES if c != 'priorities'}
        old['weights']['ideas'] = 0
        old['instructions'] = 'Remember only the things I choose.'
        old['exclude_terms'] = ['private code']
        with self.store.db() as db:
            db.execute('INSERT INTO memory_policies VALUES(?,?)', (self.cara, json.dumps(old)))
        loaded = self.memory.policy(self.cara)
        self.assertEqual(loaded['weights']['priorities'], 2)
        self.assertEqual(loaded['weights']['interests'], 1)
        self.assertEqual(loaded['weights']['ideas'], 0)
        self.assertEqual(loaded['instructions'], old['instructions'])
        self.assertEqual(loaded['exclude_terms'], old['exclude_terms'])
        self.memory.set_policy(self.cara, {'topics': ['music']})
        self.assertEqual(self.memory.policy(self.cara)['weights'], loaded['weights'])

    def test_rejects_forged_sources_and_quotes_atomically(self):
        msg = self.message(self.bob, self.cara, 'I can help with Python prototypes.')
        def bad(owner, job, payload):
            units = local_extract(owner, job, payload)
            units.append({**units[0], 'evidence': [{'source_key': 'message:other:0', 'quote': 'private'}]})
            return units
        with self.assertRaises(AppError):
            self.memory.process(self.cara, bad)
        self.assertEqual(self.memory.units(self.cara), [])
        self.assertEqual(len(self.memory.sources(self.cara)), 1)
        self.assertEqual(self.memory.view(self.cara)['last_job']['status'], 'failed')
        payload = {'source_key': 'message:' + msg['id'] + ':0', 'quote': 'Fabricated quote', 'summary': 'Fake', 'category': 'facts'}
        with self.assertRaises(AppError):
            self.memory.remember(self.cara, payload)

    def test_private_source_cannot_be_selected_by_third_member(self):
        msg = self.message(self.ada, self.bob, 'I enjoy private jazz sessions.')
        with self.assertRaises(AppError) as error:
            self.memory.remember(self.cara, {'source_key': 'message:' + msg['id'] + ':0'})
        self.assertEqual(error.exception.status, 404)

    def test_attribution_requires_explicit_speech_not_just_name(self):
        msg = self.message(self.bob, self.cara, 'I enjoy talking with Ada about music.')
        with self.assertRaises(AppError):
            self.memory.remember(self.cara, {'source_key': 'message:' + msg['id'] + ':0',
                'quote': msg['body'], 'summary': 'Ada likes music', 'category': 'interests', 'reported_origin': 'Ada'})

    def test_exact_duplicates_consolidate_evidence_and_hidden_notes_stay_hidden(self):
        for _ in range(2):
            self.message(self.bob, self.cara, 'I can help with Python prototypes.')
            self.memory.process(self.cara, local_extract)
        note = self.memory.units(self.cara)[0]
        self.assertEqual(len(self.memory.units(self.cara)), 1)
        self.assertEqual(len(note['evidence']), 2)
        self.memory.update_unit(self.cara, note['id'], {'hidden': True})
        self.message(self.bob, self.cara, 'I can help with Python prototypes.')
        self.memory.process(self.cara, local_extract)
        self.assertEqual(self.memory.units(self.cara), [])
        self.assertEqual(self.memory.recall(self.cara, 'Python'), [])
        self.assertEqual(len(self.memory.units(self.cara, include_hidden=True)), 1)

    def test_contradictions_preserve_separate_statements(self):
        self.message(self.bob, self.cara, 'I can help with Python on Tuesday.')
        self.memory.process(self.cara, local_extract)
        self.message(self.bob, self.cara, 'I cannot help with Python on Tuesday.')
        self.memory.process(self.cara, local_extract)
        self.assertEqual(len(self.memory.units(self.cara)), 2)

    def test_synthesis_preserves_alternate_wording_and_evidence(self):
        self.message(self.bob, self.cara, 'I can help with Python prototypes.')
        self.memory.process(self.cara, local_extract)
        first = self.memory.units(self.cara)[0]
        self.message(self.bob, self.cara, 'I can help build prototypes in Python.')
        def synthesize(owner, job, payload):
            units = local_extract(owner, job, payload)
            units[0]['merge_with'] = first['id']
            return units
        self.memory.process(self.cara, synthesize)
        note = self.memory.units(self.cara)[0]
        self.assertEqual(len(self.memory.units(self.cara)), 1)
        self.assertEqual(len(note['variants']), 2)
        self.assertEqual(len(note['evidence']), 2)

    def test_pin_ownership_recall_switch_and_hard_budget(self):
        self.message(self.bob, self.cara, 'I can help with Python prototypes. I enjoy jazz improvisation.')
        self.memory.process(self.cara, local_extract)
        note = next(n for n in self.memory.units(self.cara) if n['category'] == 'interests')
        with self.assertRaises(AppError) as error:
            self.memory.update_unit(self.ada, note['id'], {'pinned': True})
        self.assertEqual(error.exception.status, 404)
        self.memory.update_unit(self.cara, note['id'], {'pinned': True})
        self.assertEqual(self.memory.recall(self.cara, 'Python')[0]['id'], note['id'])
        self.assertEqual(self.memory.recall(self.cara, 'Python', budget=1), [])
        self.memory.set_policy(self.cara, {'recall_enabled': False})
        self.assertEqual(self.memory.recall(self.cara, 'Python'), [])

    def test_assistant_draft_never_becomes_a_human_statement(self):
        turn = self.store.begin_turn(self.cara, 'I need a prototype for my music tool.')
        self.store.finish_turn(turn, reply='I can help draft some Python code.')
        self.memory.process(self.cara, local_extract)
        self.assertEqual({n['kind'] for n in self.memory.units(self.cara)}, {'self_report', 'assistant_draft'})

    def test_batches_are_bounded_and_processed_once(self):
        for index in range(15):
            self.message(self.bob, self.cara, f'I can help with prototype number {index}. ' + 'a' * 7800)
        batch = self.memory.batch(self.cara)
        self.assertLessEqual(len(batch), BATCH_SOURCES)
        self.assertLessEqual(sum(len(s['body']) for s in batch), BATCH_CHARACTERS)
        self.assertTrue(any(s['key'].endswith(':3840') for s in self.memory.sources(self.cara)))
        result = self.memory.process(self.cara, local_extract)
        self.assertGreater(result['remaining'], 0)
        keys = {s['key'] for s in batch}
        self.assertTrue(keys.isdisjoint(s['key'] for s in self.memory.batch(self.cara)))

    def test_failure_pauses_automatic_work_until_explicit_retry(self):
        self.memory.set_policy(self.cara, {'auto_extract': True, 'auto_after': 1})
        self.message(self.bob, self.cara, 'I can help with Python prototypes.')
        self.assertTrue(self.memory.should_process(self.cara))
        def fail(*args):
            raise RuntimeError('sensitive internal diagnostic')
        with self.assertRaises(AppError):
            self.memory.process(self.cara, fail)
        self.assertFalse(self.memory.should_process(self.cara))
        self.assertNotIn('sensitive internal diagnostic', json.dumps(self.memory.view(self.cara)))
        self.memory.process(self.cara, local_extract)
        self.assertEqual(self.memory.view(self.cara)['last_job']['status'], 'completed')

    def test_concurrent_extraction_cannot_duplicate_a_batch(self):
        self.message(self.bob, self.cara, 'I can help with Python prototypes.')
        entered, release = threading.Event(), threading.Event()
        def blocked(owner, job, payload):
            entered.set()
            release.wait(3)
            return local_extract(owner, job, payload)
        with ThreadPoolExecutor(2) as executor:
            pending = executor.submit(self.memory.process, self.cara, blocked)
            self.assertTrue(entered.wait(2))
            try:
                with self.assertRaises(AppError) as error:
                    self.memory.process(self.cara, local_extract)
                self.assertEqual(error.exception.status, 409)
            finally:
                release.set()
            self.assertEqual(pending.result()['status'], 'completed')
        self.assertEqual(self.memory.process(self.cara, local_extract)['status'], 'idle')
        self.assertEqual(self.memory.view(self.cara)['extraction_attempts'], 1)

    def test_manual_selection_works_after_batch_and_exclusions_prevent_capture(self):
        msg = self.message(self.bob, self.cara, 'I can help with Python prototypes.')
        self.memory.process(self.cara, local_extract)
        self.memory.remember(self.cara, {'source_key': 'message:' + msg['id'] + ':0',
            'quote': msg['body'], 'summary': 'A human-selected programming offer.', 'category': 'offers'})
        self.assertEqual(len(self.memory.units(self.cara)), 2)
        self.memory.set_policy(self.cara, {'exclude_terms': ['Python']})
        with self.assertRaises(AppError):
            self.memory.remember(self.cara, {'source_key': 'message:' + msg['id'] + ':0',
                'quote': msg['body'], 'summary': 'An offer', 'category': 'offers'})

    def test_policy_validation(self):
        for payload in ({'auto_extract': 1}, {'auto_after': 0}, {'minimum_importance': float('nan')},
                        {'topics': 'water'}, {'weights': {}}, {'exclude_terms': ['x' * 100001]}):
            with self.subTest(payload=payload), self.assertRaises(AppError):
                self.memory.set_policy(self.cara, payload)


if __name__ == '__main__':
    unittest.main()
