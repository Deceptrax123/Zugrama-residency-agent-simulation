"""Offline harness checks only. Never starts a trial loop or a model process."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from residency.config import APP_ROOT, Settings
from residency.memory import ConversationMemory, local_extract
from residency.store import Store

spec = importlib.util.spec_from_file_location('persona_trial', APP_ROOT / 'scripts/persona_trial.py')
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


class PersonaTrialTests(unittest.TestCase):
    def setUp(self):
        (APP_ROOT / '.data').mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='trial-harness-check-', dir=APP_ROOT / '.data')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        replacement = patch.object(trial, 'TRIALS', self.root / 'trials')
        replacement.start()
        self.addCleanup(replacement.stop)
        # An accidental invocation fails instead of consuming model calls.
        no_process = patch.object(trial.subprocess, 'Popen', side_effect=AssertionError('No model process allowed in offline checks'))
        no_process.start()
        self.addCleanup(no_process.stop)

    def test_fixture_matches_exact_archived_starting_profiles_only(self):
        data, config = trial.fixture()
        archive = trial.read_json(APP_ROOT.parent / data['source'])
        self.assertEqual(data['personas'], [a['persona'] for a in archive['state']['agents']])
        self.assertEqual(data['source_run_id'], archive['state']['runId'])
        self.assertEqual(len(data['personas']), 9)
        self.assertEqual(config['model'], 'gpt-5.6-terra')
        self.assertFalse(config['automatic_start'])
        self.assertIsNone(config['fallback_model'])
        self.assertNotIn('messages', data)
        self.assertNotIn('notes', data)

    def test_plan_never_creates_a_trial_or_invokes_a_model(self):
        preview = trial.plan()
        self.assertEqual(preview['model_calls'], 0)
        self.assertFalse(preview['model_access_tested'])
        self.assertFalse(trial.TRIALS.exists())

    def test_preparation_is_idle_and_refuses_to_overwrite(self):
        result = trial.prepare('trial-one', decisions=9, seed=7)
        directory = trial.trial_path('trial-one')
        self.assertEqual(result['model_calls'], 0)
        manifest, profiles, accounts = trial.load_trial(directory)
        self.assertEqual(manifest['status'], 'prepared')
        self.assertEqual(manifest['attempted_calls'], 0)
        self.assertEqual(manifest['configuration']['max_decisions'], 9)
        self.assertEqual(len(accounts), len(profiles))
        self.assertEqual((directory / 'accounts.json').stat().st_mode & 0o777, 0o600)
        store = Store(Settings(data_dir=directory / 'state', join_code='offline-check-only'))
        state = store.snapshot(accounts[0]['member_id'])
        self.assertEqual(state['messages'], [])
        self.assertEqual(state['assistant_turns'], [])
        self.assertEqual(ConversationMemory(store).units(accounts[0]['member_id']), [])
        self.assertFalse((directory / 'calls').exists())
        original = (directory / 'manifest.json').read_bytes()
        with self.assertRaises(FileExistsError):
            trial.prepare('trial-one')
        self.assertEqual((directory / 'manifest.json').read_bytes(), original)

    def test_path_and_budget_validation_happen_before_preparation(self):
        for name in ('../live', '/tmp/outside', '.data', '', 'a/b'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                trial.prepare(name)
        for decisions in (0, 8, 1001):
            with self.subTest(decisions=decisions), self.assertRaises(ValueError):
                trial.prepare('invalid', decisions=decisions)
        self.assertFalse(trial.TRIALS.exists())

    def test_context_contains_only_own_trial_messages_and_attributed_notes(self):
        trial.prepare('context-check')
        directory = trial.trial_path('context-check')
        manifest, profiles, accounts = trial.load_trial(directory)
        first, second, third = [a['member_id'] for a in accounts[:3]]
        store = Store(Settings(data_dir=directory / 'state', join_code='offline-check-only'))
        memory = ConversationMemory(store)
        result = store.conversation_action(first, {'start_conversations':[
            {'with':second,'body':'UNSHARED-ORIGINAL-111 private statement.'}]})
        room = result['created_conversations'][0]
        store.conversation_action(third, {'join_conversations':[room]})
        relay = profiles[0]['name'] + ' suggested accessible music education.'
        store.conversation_action(second, {'messages':[{'conversation_id':room,'body':relay}]})
        memory.process(third, local_extract)
        context = trial.context_for(store, memory, third, profiles[2], manifest['configuration'])
        serialized = json.dumps(context)
        self.assertNotIn('UNSHARED-ORIGINAL-111', serialized)
        self.assertIn(relay, serialized)
        self.assertEqual(context['private_memory'][0]['path'], [first, second, third])
        disabled = {**manifest['configuration'], 'memory': False}
        self.assertEqual(trial.context_for(store, memory, third, profiles[2], disabled)['private_memory'], [])
        self.assertIn('Village problems are optional', trial.prompt_for(context, 'Dhun context', disabled))

    def test_action_validation_accepts_silence_and_rejects_invalid_entire_action(self):
        config = trial.fixture()[1]
        empty = {'introduction':'','start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]}
        self.assertEqual(trial.validate_action(empty, 'a', {'a', 'b'}, config), empty)
        for action in ({**empty,'start_conversations':[{'with':'a','body':'self'}]},
                {**empty,'start_conversations':[{'with':'missing','body':'unknown'}]},
                {**empty,'messages':[{'conversation_id':'room','body':'x' * 4001}]},
                {**empty,'shell':'anything'}, {**empty,'messages':'invalid'}):
            with self.subTest(action=str(action)[:80]), self.assertRaises(ValueError):
                trial.validate_action(action, 'a', {'a', 'b'}, config)

    def test_introduction_phase_requires_only_an_intro_and_board_is_explicitly_scoped(self):
        config = trial.fixture()[1]
        intro = {'introduction':'I enjoy mathematical ideas.','start_conversations':[],
                 'join_conversations':[],'messages':[],'leave_conversations':[]}
        self.assertEqual(trial.validate_action(intro,'a',{'a','b'},config,'introduce'),intro)
        with self.assertRaises(ValueError):
            trial.validate_action({**intro,'start_conversations':[{'with':'b','body':'Too early.'}]},'a',{'a','b'},config,'introduce')
        with self.assertRaises(ValueError):
            trial.validate_action(intro,'a',{'a','b'},config,'network')
        trial.prepare('board-check')
        directory = trial.trial_path('board-check')
        manifest, profiles, accounts = trial.load_trial(directory)
        store = Store(Settings(data_dir=directory/'state',join_code='offline-check-only'))
        store.introduce(accounts[0]['member_id'],{'body':'I enjoy mathematical ideas.'})
        memory = ConversationMemory(store)
        memory.capture_conversations(accounts[1]['member_id'])
        args = (store,memory,accounts[1]['member_id'],profiles[1],manifest['configuration'])
        self.assertEqual(trial.context_for(*args,phase='introduce')['private_memory'],[])
        self.assertEqual(len(trial.context_for(*args,show_introductions=True)['introduction_board']),1)
        self.assertEqual(trial.context_for(*args,show_introductions=False)['introduction_board'],[])

    def test_codex_command_is_explicit_terra_with_no_tools_or_stronger_fallback(self):
        command = trial.model_command(self.root, self.root / 'output.json', 'gpt-5.6-terra')
        self.assertEqual(command[command.index('--model') + 1], 'gpt-5.6-terra')
        for flag in ('--ephemeral', '--ignore-user-config', '--ignore-rules', '--output-schema'):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index('--sandbox') + 1], 'read-only')
        for tool in ('shell_tool', 'unified_exec', 'apps', 'memories', 'plugins', 'multi_agent'):
            self.assertIn(tool, command)
            self.assertEqual(command[command.index(tool)-1], '--disable')
        self.assertNotIn('gpt-6.1-sol', ' '.join(command))
        with patch.dict(os.environ, {'OPENAI_API_KEY':'secret', 'HERMES_API_KEY':'secret', 'RESIDENCY_JOIN_CODE':'secret'}):
            environment = trial.model_environment()
        for key in ('OPENAI_API_KEY', 'HERMES_API_KEY', 'RESIDENCY_JOIN_CODE'):
            self.assertNotIn(key, environment)

    def test_changed_context_is_detected_before_a_trial_can_run(self):
        trial.prepare('integrity-check')
        directory = trial.trial_path('integrity-check')
        (directory / 'USER.md').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'changed after preparation'):
            trial.load_trial(directory)


if __name__ == '__main__':
    unittest.main()
