import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from residency.end_questionnaire import (QuestionnaireRunner, build_packet,
    validate_answer, render_answer, ready, MODEL)
from residency.markdown_memory import document, write_private


class Gateway:
    def __init__(self, quota=False, unsupported=False):
        self.calls = []; self.quota = quota; self.unsupported = unsupported

    def check(self):
        return {'status': 'ready'}

    def request(self, path, payload=None, headers=None, timeout=None):
        if path == '/health':
            return {'residency_budget_guard': 'residency-usd-v1'}
        self.calls.append(payload)
        if self.quota:
            return {'residency_provider_error': {'code': 'usage_limit_reached'}}
        packet = json.loads(payload['messages'][-1]['content'])
        value = answers(packet)
        if self.unsupported:
            value['skills']['evidence'] = [{'message_id': 'secret', 'quote': 'private'}]
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(value)}}],
                'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}}


def answers(packet):
    evidence = [{'message_id': packet['messages'][0]['id'], 'quote': packet['messages'][0]['body'][:30]}] if packet['messages'] else []
    return {**{k: {'answer': 'This is supported, or no new learning was recorded.', 'evidence': copy.deepcopy(evidence)}
               for k in ('favorite', 'skills', 'interesting', 'problem_solving', 'interests')},
            'ranking': [c['id'] for c in packet['contacts']]}


class EndQuestionnaireTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name); (self.data/'state').mkdir()
        self.db = sqlite3.connect(self.data/'state/residency.sqlite3'); self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript('''
        CREATE TABLE conversation_messages(id TEXT,conversation_id TEXT,sender_id TEXT,body TEXT,created_at REAL,seq INTEGER);
        CREATE TABLE conversation_visits(conversation_id TEXT,member_id TEXT,joined_after_seq INTEGER,left_after_seq INTEGER);
        CREATE TABLE metadata(key TEXT,value TEXT);
        INSERT INTO metadata VALUES('instance_id','instance');
        CREATE TABLE memory_policies(owner_id TEXT,data TEXT);
        CREATE TABLE agent_requests(id TEXT PRIMARY KEY,owner_id TEXT,target_id TEXT,body TEXT,status TEXT,response TEXT,created_at REAL,event_id TEXT);
        INSERT INTO conversation_messages VALUES('old','room','b','PRIVATE BEFORE JOIN',1,1);
        INSERT INTO conversation_messages VALUES('one','room','b','I can explain soil moisture sensors.',2,2);
        INSERT INTO conversation_messages VALUES('two','room','a','I would like to learn that.',3,3);
        INSERT INTO conversation_messages VALUES('gap','room','b','PRIVATE AFTER LEAVE',4,4);
        INSERT INTO conversation_messages VALUES('hidden','other','c','SECRET OTHER ROOM',5,5);
        INSERT INTO conversation_visits VALUES('room','a',1,3);
        INSERT INTO conversation_visits VALUES('room','b',0,NULL);
        INSERT INTO conversation_visits VALUES('other','c',0,NULL);
        '''); self.db.commit()
        self.state = {'event_id': 'event', 'conversation_ids': ['room', 'other'],
                      'starting_identities': {'a': {'name': 'Alice'}, 'b': {'name': 'Bob'}, 'c': {'name': 'Cara'}}}

    def packet(self):
        return build_packet(self.db, self.state, 'a', self.data/'state')

    def test_scope_and_all_contacts_are_from_actual_visible_exchanges(self):
        packet = self.packet()
        self.assertEqual([m['id'] for m in packet['messages']], ['one', 'two'])
        self.assertEqual(packet['contacts'], [{'id': 'b', 'name': 'Bob'}])
        self.assertNotIn('PRIVATE', json.dumps(packet)); self.assertNotIn('SECRET', json.dumps(packet))

    def test_permission_and_note_provenance(self):
        scope = hashlib.sha256(b'instance:event:a').hexdigest()
        path = self.data/'state/agent-memory'/scope/'MEMORY.md'
        notes = [{'memory': 'Permitted note', 'metadata': {'source_keys': ['conversation:one']}},
                 {'memory': 'Hidden note', 'metadata': {'source_keys': ['conversation:hidden']}}]
        # Store the same machine-readable Markdown format used in production.
        write_private(path, document(notes))
        self.assertEqual(self.packet()['own_memories'], [])
        self.db.execute('INSERT INTO memory_policies VALUES(?,?)', ('a', json.dumps({'network_context': True}))); self.db.commit()
        self.assertEqual(self.packet()['own_memories'], [{'memory': 'Permitted note'}])

    def test_exact_quote_and_ranking_validation(self):
        packet = self.packet(); value = answers(packet)
        self.assertEqual(validate_answer(value, packet), value)
        value['skills']['evidence'][0]['quote'] = 'Fabricated learning'
        with self.assertRaises(ValueError): validate_answer(value, packet)
        value = answers(packet); value['ranking'] = ['c']
        with self.assertRaises(ValueError): validate_answer(value, packet)
        value = answers(packet); value['ranking'] = ['b', 'b']
        with self.assertRaises(ValueError): validate_answer(value, packet)

    def test_rank_names_only_and_evidence_attributed_in_markdown(self):
        packet = self.packet(); result = render_answer(answers(packet), packet)
        self.assertIn('1. Bob', result)
        self.assertIn('Speaker: Bob · Message: one · Conversation: room', result)
        self.assertNotIn('SECRET', result)

    def test_running_and_quota_alone_do_not_trigger(self):
        for status in ('running', 'stopping', 'paused_quota', 'interrupted', 'completed', 'stopped'):
            self.assertFalse(ready({'status': status, 'worker_count': 0}))
        self.assertFalse(ready({'status': 'running', 'worker_count': 0}, host_stop=True))
        self.assertFalse(ready({'status': 'stopped', 'worker_count': 1}, host_stop=True))
        self.assertTrue(ready({'status': 'stopped', 'worker_count': 0}, host_stop=True))

    def test_integration_delivers_privately_tracks_usage_and_does_not_repeat(self):
        gateway = Gateway(); runner = QuestionnaireRunner(self.data, gateway); runner.initialize()
        self.assertEqual(runner.run_owner(self.state, 'a', lambda: False), 'waiting_for_stop')
        self.assertEqual(gateway.calls, [])
        self.assertEqual(runner.run_owner(self.state, 'a', lambda: True), 'completed')
        self.assertEqual(runner.run_owner(self.state, 'a', lambda: True), 'completed')
        self.assertEqual(len(gateway.calls), 1); self.assertEqual(gateway.calls[0]['model'], MODEL)
        row = self.db.execute('SELECT * FROM agent_requests').fetchone()
        self.assertEqual(row['owner_id'], 'a'); self.assertEqual(row['status'], 'addressed')
        self.assertIn('End-of-event questionnaire', row['response'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM agent_requests WHERE owner_id="b"').fetchone()[0], 0)
        usage = self.db.execute('SELECT * FROM end_questionnaire_usage').fetchone()
        self.assertEqual(usage['status'], 'completed'); self.assertEqual(usage['cost_usd'], 700)
        self.assertEqual(usage['hold_usd'], 0)
        path = self.data/'state/questionnaires/event/a/ANSWER.md'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_quota_releases_hold_without_retry_and_unsupported_evidence_not_published(self):
        gateway = Gateway(quota=True); runner = QuestionnaireRunner(self.data, gateway); runner.initialize()
        self.assertEqual(runner.run_owner(self.state, 'a', lambda: True), 'paused_quota')
        self.assertEqual(runner.run_owner(self.state, 'a', lambda: True), 'rejected_quota')
        self.assertEqual(len(gateway.calls), 1)
        self.assertEqual(self.db.execute('SELECT hold_usd FROM end_questionnaire_usage').fetchone()[0], 0)
        bad = Gateway(unsupported=True); runner = QuestionnaireRunner(self.data, bad)
        self.assertEqual(runner.run_owner(self.state, 'b', lambda: True), 'failed_no_retry')
        self.assertEqual(self.db.execute('SELECT count(*) FROM agent_requests').fetchone()[0], 0)
        row = self.db.execute('SELECT status,cost_usd,hold_usd FROM end_questionnaire_usage WHERE owner_id="b"').fetchone()
        self.assertEqual(tuple(row), ('failed_answer', 700, 0))

    def test_large_history_preserves_all_messages_and_contact_coverage(self):
        self.db.executemany('INSERT INTO conversation_messages VALUES(?,?,?,?,?,?)',
            [('bulk'+str(i), 'room', 'b', 'δ'*4000, 2, 2) for i in range(30)])
        self.db.commit(); packet = self.packet()
        self.assertEqual(len(packet['messages']), 32)
        self.assertGreater(packet['coverage']['clipped_messages'], 0)
        self.assertLessEqual(len(json.dumps(packet).encode()), 85000)
        self.assertEqual(packet['contacts'], [{'id': 'b', 'name': 'Bob'}])

    def run_watch(self, statuses, authenticated_stop):
        from scripts import end_questionnaire as worker
        path = self.data/'state/host-event/state.json'; path.parent.mkdir()
        state = {**self.state, 'status': 'running'}; path.write_text(json.dumps(state))
        (self.data/'setup.json').write_text(json.dumps({'network_model': MODEL, 'join_code': 'synthetic'}))
        reader = Mock()
        reader.request.side_effect = lambda *args: {**json.loads(path.read_text()), 'worker_count': 0}
        reader.host_stopped_since.return_value = authenticated_stop
        runner = Mock(); runner.run_owner.return_value = 'completed'
        steps = iter(statuses)
        def tick(_):
            step = next(steps)
            state['status'] = step
            if step == 'event_changed': state['event_id'] = 'other'
            path.write_text(json.dumps(state))
        with patch.object(worker, 'DATA', self.data), patch.object(worker, 'HostReader', return_value=reader), \
             patch.object(worker, 'QuestionnaireRunner', return_value=runner), patch.object(worker, 'gateway_settings'), \
             patch.object(worker, 'Hermes'), patch.object(worker.time, 'sleep', side_effect=tick), patch('builtins.print'):
            worker.watch('event')
        job = json.loads((self.data/'state/questionnaires/event/status.json').read_text())
        return runner, job

    def test_watcher_delivers_all_agents_only_after_authenticated_host_stop(self):
        runner, job = self.run_watch(['stopping', 'stopped'], True)
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(runner.run_owner.call_count, 3)
        self.assertTrue(all(call.args[0]['status'] == 'stopped' for call in runner.run_owner.call_args_list))

    def test_watcher_does_not_dispatch_for_quota_or_process_stop_without_host_command(self):
        runner, job = self.run_watch(['paused_quota', 'stopping', 'stopped', 'event_changed'], False)
        self.assertFalse(runner.run_owner.called)
        self.assertEqual(job['status'], 'cancelled_event_changed')
