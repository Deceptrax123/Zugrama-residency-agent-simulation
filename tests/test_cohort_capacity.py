import json
import unittest
from unittest.mock import Mock

from residency.cohort import LiveCohort
from residency.identity import FIELDS,rows,validate_identity
from residency.identity_document import document
from residency.site_bridge import SiteBridge
from residency.markdown_memory import write_private
from residency.store import AppError
from tests.test_cohort import fixture,apply,export,import_payload
from tests.test_identity_sandbox import persona


class CapacityTests(unittest.TestCase):
    def test_expansion_preserves_existing_residents_and_imports_fifty_without_calls(self):
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(7,explicit=True)))
            before=rows(server.store)
            with server.store.db() as db:
                revisions=db.execute('SELECT count(*) FROM identity_revisions').fetchone()[0]
                imports=[tuple(r) for r in db.execute('SELECT * FROM cohort_imports ORDER BY slot')]
            server.sandbox=LiveCohort(server,50)
            self.assertEqual(rows(server.store),before)
            self.assertEqual(len(list(server.store.path.parent.glob('before-capacity-*.sqlite3'))),1)
            with server.store.db() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM identity_revisions').fetchone()[0],revisions)
                self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM cohort_imports ORDER BY slot')],imports)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            result=apply(server,client,import_payload(export(50,explicit=True)))
            self.assertEqual(len(result['imported_slots']),43)
            self.assertEqual(rows(server.store)[:7],before)
            self.assertEqual(len(server.event.personas),50)
            self.assertTrue(all(not server.memory.policy(p)['network_context'] for p in server.event.personas))
            self.assertEqual(server.sandbox.preview_import(server.sandbox.owner,import_payload(export(50,explicit=True)))['rows'][-1]['action'],'unchanged')
            with self.assertRaises(AppError):server.sandbox.preview_import(server.sandbox.owner,import_payload(export(51)))
            with self.assertRaises(ValueError):LiveCohort(server,51)
            with self.assertRaises(ValueError):LiveCohort(server,12)
            self.assertEqual(server.event.state['calls'],0);self.assertEqual(backend.records,[])

    def test_fifty_maximum_unicode_profiles_fit_gpt_and_hosted_views(self):
        with fixture(limit=50) as (server,client,backend,memory):
            for slot in range(1,51):
                value=validate_identity(persona(f'Resident {slot}'))
                for key,(_,maximum) in FIELDS.items():value[key]='🌱'*maximum
                value['name']=f'Resident {slot}'
                server.sandbox.save_agent(server.sandbox.owner,slot,value,document(value))
                with server.store.db() as db:db.execute('INSERT INTO cohort_imports VALUES(?,?,?,?)',('anonymous:'+str(slot).zfill(64),slot,'synthetic',0))
            event=server.event;event.state['event_id']='synthetic-capacity'
            packet=event.context(next(iter(event.personas)))
            self.assertLessEqual(len(json.dumps(packet,ensure_ascii=False).encode()),110000)
            self.assertEqual(packet['coverage']['directory_residents'],50)
            path=server.settings.data_dir/'bridge.json';write_private(path,json.dumps({'origin':'https://zugrama-agent-residency.smudge0110.chatgpt.site','token':'x'*48}))
            bridge=SiteBridge(server,path,Mock(return_value={'saved':True,'job':None}))
            snapshots=bridge.snapshots();self.assertEqual(len(snapshots),51)
            self.assertTrue(all(len(s['data']['directory'])==50 for s in snapshots))
            self.assertTrue(all(len(json.dumps(s['data'],ensure_ascii=False).encode())<=(600000 if s['owner_id']=='host' else 180000) for s in snapshots))
            self.assertEqual(backend.records,[])

    def test_large_publication_is_batched_below_transport_limit_with_host_last(self):
        with fixture(limit=50) as (server,client,backend,memory):
            path=server.settings.data_dir/'bridge.json';write_private(path,json.dumps({'origin':'https://zugrama-agent-residency.smudge0110.chatgpt.site','token':'x'*48}))
            transport=Mock(return_value={'saved':True,'job':None});bridge=SiteBridge(server,path,transport)
            snapshots=[{'owner_id':'host','data':{'body':'h'*590000}}]+[{'owner_id':'anonymous:'+str(n).zfill(64),'data':{'body':'🌱'*44000}} for n in range(50)]
            bridge.snapshots=Mock(return_value=snapshots);bridge.tick()
            batches=[call.args[0] for call in transport.call_args_list if call.args[0]['action']=='publish']
            self.assertGreater(len(batches),1)
            self.assertTrue(all(len(json.dumps(b,ensure_ascii=False).encode())<3800000 for b in batches))
            self.assertEqual(batches[-1]['snapshots'][-1]['owner_id'],'host')
            self.assertEqual(sum(len(b['snapshots']) for b in batches),51)
            self.assertTrue(all(len(b['owners'])==51 for b in batches))
            count=len(batches);bridge.tick()
            self.assertEqual(sum(call.args[0]['action']=='publish' for call in transport.call_args_list),count)
            self.assertEqual(backend.records,[])


if __name__=='__main__':unittest.main()
