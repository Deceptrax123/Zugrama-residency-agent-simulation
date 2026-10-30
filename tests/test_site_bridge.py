import json
import unittest
from unittest.mock import Mock
from residency.site_bridge import SiteBridge
from residency.markdown_memory import write_private
from tests.test_cohort import fixture,apply,import_payload,export


class SiteBridgeTests(unittest.TestCase):
    def bridge(self,server,transport=None):
        path=server.settings.data_dir/'site-bridge.json'
        write_private(path,json.dumps({'origin':'https://zugrama-agent-residency.smudge0110.chatgpt.site','token':'x'*48}))
        return SiteBridge(server,path,transport or Mock(return_value={'saved':True,'job':None}))

    def test_idle_publish_is_scoped_and_connection_never_starts_event(self):
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(3)));bridge=self.bridge(server)
            snapshots=bridge.snapshots();self.assertEqual(len(snapshots),4)
            people=list(server.event.personas);a,b,c=people
            job={'id':'resident-one','owner_id':'anonymous:synthetic-0','kind':'request','payload':{'body':'PRIVATE-HUMAN-A','target_id':b},'lease_token':'lease','created_at':9999999999999}
            bridge.handle(job);bridge.handle(job)
            a_view=next(x['data'] for x in bridge.snapshots() if x['owner_id']=='anonymous:synthetic-0')
            b_view=next(x['data'] for x in bridge.snapshots() if x['owner_id']=='anonymous:synthetic-1')
            self.assertIn('PRIVATE-HUMAN-A',json.dumps(a_view));self.assertNotIn('PRIVATE-HUMAN-A',json.dumps(b_view))
            self.assertNotIn('agents',b_view);self.assertNotIn('graphs',b_view)
            self.assertEqual(len(server.sandbox.accounts.requests(a)),1);self.assertEqual(server.event.state['calls'],0);self.assertEqual(backend.records,[])
            bridge.tick();self.assertTrue(bridge.transport.called);self.assertEqual(server.event.state['status'],'idle')

    def test_private_room_notes_and_reflections_do_not_enter_peer_view(self):
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(3)));bridge=self.bridge(server)
            event=server.event;event.state['event_id']='bridge-isolation';a,b,c=list(event.personas)
            room=server.store.conversation_action(a,{'start_conversations':[{'with':b,'body':'PRIVATE-AB-TOPIC'}]});event.rooms.update(room['created_conversations'])
            server.capture_conversations([a,b]);server.semantic.queue.join()
            views={x['owner_id']:x['data'] for x in bridge.snapshots()}
            self.assertIn('PRIVATE-AB-TOPIC',json.dumps(views['anonymous:synthetic-0']))
            self.assertNotIn('PRIVATE-AB-TOPIC',json.dumps(views['anonymous:synthetic-2']))
            self.assertTrue(views['anonymous:synthetic-0']['notes']);self.assertEqual(views['anonymous:synthetic-2']['notes'],[])
            self.assertNotIn('moral_compass',json.dumps(views['anonymous:synthetic-2']['directory']))

    def test_resident_cannot_control_event_and_restart_does_not_replay(self):
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(2)));bridge=self.bridge(server)
            job={'id':'bad-start','owner_id':'anonymous:synthetic-0','kind':'start','payload':{'max_calls':1},'lease_token':'lease','created_at':9999999999999}
            bridge.handle(job)
            with server.store.db() as db:
                self.assertEqual(db.execute('SELECT status FROM site_command_receipts WHERE id=?',('bad-start',)).fetchone()[0],'failed')
                db.execute("INSERT INTO site_command_receipts VALUES('interrupted','started',NULL,'old-lease',0)")
            restored=self.bridge(server);restored.execute=Mock(side_effect=AssertionError('Must not replay'))
            restored.handle({'id':'interrupted','owner_id':'host','kind':'start','payload':{},'lease_token':'old-lease','created_at':1})
            restored.acknowledge();self.assertFalse(restored.execute.called)
            self.assertEqual(server.event.state['calls'],0);self.assertEqual(backend.records,[])
            with server.store.db() as db:self.assertEqual(db.execute("SELECT status FROM site_command_receipts WHERE id='interrupted'").fetchone()[0],'uncertain')

    def test_payload_limits_and_blocked_target_without_starting_networking(self):
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(2)));bridge=self.bridge(server)
            for target in ('nonexistent',list(server.event.personas)[0]):
                job={'id':'bad-'+target,'owner_id':'anonymous:synthetic-0','kind':'request','payload':{'body':'A request','target_id':target},'lease_token':'lease','created_at':9999999999999};bridge.handle(job)
                with server.store.db() as db:self.assertEqual(db.execute('SELECT status FROM site_command_receipts WHERE id=?',(job['id'],)).fetchone()[0],'failed')
            view={'agents':[{'identity_markdown':'x'*90000,'notes':[{'memory':'y'*5000} for _ in range(30)],'account':{'usage':[{}]*30,'requests':[{}]*30}} for _ in range(12)],'feed':[{'body':'z'*4000}]*80}
            bounded=bridge.bounded(view,600000);self.assertLessEqual(len(json.dumps(bounded,ensure_ascii=False).encode()),600000);self.assertTrue(bounded['coverage']['trimmed'])

    def test_resident_ledger_and_room_previews_remain_bounded(self):
        view={'usage':[{'links':['x'*4000]*4} for _ in range(30)],
              'requests':[{'body':'y'*2000} for _ in range(30)],
              'rooms':[{'id':str(i),'topic':'z'*4000} for i in range(80)],
              'wallet':{'spent_usd':2.5},
              'semantic_analysis':{'report':{'summary':'Keep report'},'sources':[]}}
        original=json.loads(json.dumps(view))
        bounded=SiteBridge.bounded(view,180000)
        self.assertLessEqual(len(json.dumps(bounded,ensure_ascii=False).encode()),180000)
        self.assertTrue(bounded['coverage']['trimmed'])
        self.assertEqual(bounded['wallet'],original['wallet'])
        self.assertEqual(bounded['semantic_analysis'],original['semantic_analysis'])
        self.assertEqual(view,original)

    def test_large_room_previews_trim_in_batches_and_preserve_newest_ledger_entries(self):
        from unittest.mock import patch
        view={'rooms':[{'id':str(i),'topic':'x'*1000} for i in range(1500)],
              'usage':[{'id':str(i),'links':['y'*4000]} for i in range(30)]}
        original=json.dumps
        with patch('residency.site_bridge.json.dumps', wraps=original) as encoded:
            bounded=SiteBridge.bounded(view,180000)
        self.assertLessEqual(len(original(bounded).encode()),180000)
        self.assertLess(encoded.call_count,40)
        self.assertTrue(bounded['coverage']['trimmed'])


if __name__=='__main__':unittest.main()
