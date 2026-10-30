import json
import sqlite3
from contextlib import contextmanager
import unittest
from unittest.mock import Mock,patch
from residency.local_mem0 import AgentMem0
from residency.store import AppError
from tests import test_identity_sandbox as fixtures
from tests.test_local_memory import FakeMemory


class MemoryRecoveryTests(unittest.TestCase):
    setUp=fixtures.IdentitySandboxTests.setUp
    prepare=fixtures.IdentitySandboxTests.prepare
    settle=fixtures.IdentitySandboxTests.settle

    def prepare_memory(self):
        event,people=self.prepare();event.state['event_id']='recovery-test';self.server.sandbox=self.sandbox
        from residency.memory import ConversationMemory
        self.server.memory=ConversationMemory(self.store)
        a,b,c=people
        result=self.store.conversation_action(a,{'start_conversations':[{'with':b,'body':'Music is an interest. PRIVATE-AB'}]});event.rooms.update(result['created_conversations'])
        client=FakeMemory();memory=AgentMem0(self.server,client);self.server.semantic=memory;self.addCleanup(memory.close)
        return event,people,client,memory,result['created_conversations'][0]

    def test_tail_sources_drain_without_new_messages_and_only_requested_owners_run(self):
        event,(a,b,c),client,memory,room=self.prepare_memory()
        for n in range(28):self.store.conversation_action(a,{'messages':[{'conversation_id':room,'body':f'Useful new idea {n}'}]})
        memory.enqueue([a]);memory.queue.join()
        captured={s['key'] for _,sources,_ in client.added for s in sources}
        self.assertEqual(captured,{s['key'] for s in memory.sources(a)});self.assertGreater(len(client.added),1)
        self.assertEqual({scope for scope,_,_ in client.added},{memory.scope(a)})

    def test_stale_file_rebuild_corruption_and_offline_lexical_retrieval(self):
        event,(a,b,c),client,memory,room=self.prepare_memory();memory.enqueue([a]);memory.queue.join()
        scope=memory.scope(a);source=memory.sources(a)[0]
        client.matches[scope].append({'id':'new-note','memory':'Python skill and music','metadata':{'source_keys':[source['key']]}})
        self.assertIn('new-note',{n['id'] for n in memory.search(self.host,a,'Python skill')['results']})
        memory.markdown_path(a).write_text('<!-- residency-note -->\n```json\nnot JSON\n```\n')
        self.assertTrue(memory.read_markdown(a)['results']);self.assertTrue(memory.markdown_path(a).with_suffix('.corrupt.md').exists())
        client.search=Mock(side_effect=AppError('Synthetic ranking outage'))
        result=memory.search(self.host,a,'Python');self.assertEqual(result['retrieval'],'local_markdown_lexical_fallback');self.assertEqual(result['results'][0]['id'],'new-note')
        self.server.network_memory_owners={a};self.assertTrue(event.context(a)['private_memory']);self.assertNotIn('private_memory',event.context(b))
        client.list_notes=Mock(side_effect=AppError('Synthetic list outage'));memory.markdown_path(a).unlink()
        result=memory.search(self.host,a,'Python');self.assertEqual(result['results'],[]);self.assertIn('warning',result)
        self.assertEqual(event.context(a)['private_memory'],[])

    def test_ranked_note_outside_bounded_list_is_materialized_and_recalled(self):
        event,(a,b,c),client,memory,room=self.prepare_memory();memory.enqueue([a]);memory.queue.join()
        source=memory.sources(a)[0]
        ranked={'id':'outside-list-page','memory':'A skill in music production','metadata':{'source_keys':[source['key']]}}
        client.search=Mock(return_value={'results':[ranked]})
        # Deliberately leave the bounded listing unchanged.
        result=memory.search(self.host,a,'music production')
        self.assertEqual(result['results'][0]['id'],'outside-list-page')
        self.assertIn('outside-list-page',{note['id'] for note in memory.read_markdown(a)['results']})

    def test_failed_extraction_is_not_retried_and_source_visibility_is_rechecked(self):
        event,(a,b,c),client,memory,room=self.prepare_memory();client.add=Mock(side_effect=AppError('Synthetic extraction outage'))
        memory.enqueue([a]);memory.queue.join();self.assertEqual(client.add.call_count,1)
        memory.enqueue([a]);memory.queue.join();self.assertEqual(client.add.call_count,1)
        with self.store.db() as db:self.assertEqual(db.execute("SELECT count(*) FROM mem0_sources WHERE status='failed'").fetchone()[0],len(memory.sources(a)))
        fake={'id':'forged','memory':'PRIVATE-AB','metadata':{'source_keys':[memory.sources(a)[0]['key']]}}
        self.assertEqual(memory._visible_notes(c,{'results':[fake]},self.server.memory.policy(c))['results'],[])

    def test_status_database_failure_does_not_kill_worker_or_replay_extraction(self):
        event,(a,b,c),client,memory,room=self.prepare_memory()
        real=memory._record_result
        with patch.object(memory,'_record_result',side_effect=sqlite3.OperationalError('database is locked')):
            memory.enqueue([a]);memory.queue.join()
        self.assertTrue(memory.thread.is_alive())
        count=len(client.added);self.assertEqual(count,1)
        memory.enqueue([a]);memory.queue.join();self.assertEqual(len(client.added),count)
        path=self.server.settings.data_dir/'memory-worker-error.log'
        self.assertIn('database is locked',path.read_text());self.assertEqual(path.stat().st_mode & 0o777,0o600)
        self.store.conversation_action(b,{'messages':[{'conversation_id':room,'body':'A new useful idea after the status write failure.'}]})
        memory.enqueue([a]);memory.queue.join()
        self.assertEqual(len(client.added),count+1);self.assertTrue(memory.thread.is_alive())
        with self.store.db() as db:self.assertGreater(db.execute("SELECT count(*) FROM mem0_sources WHERE status='completed'").fetchone()[0],0)

    def test_only_local_status_commit_retries_on_lock(self):
        event,(a,b,c),client,memory,room=self.prepare_memory()
        real_db=self.store.db;attempts=[]
        @contextmanager
        def busy_once():
            attempts.append(True)
            if len(attempts)==1:raise sqlite3.OperationalError('database is locked')
            with real_db() as db:yield db
        with patch.object(self.store,'db',busy_once):memory._record_result('unused',[],'completed',None)
        self.assertEqual(len(attempts),2);self.assertEqual(client.added,[])
